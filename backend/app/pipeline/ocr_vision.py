"""
OCR con Google Cloud Vision (DOCUMENT_TEXT_DETECTION).

Transcribe TODO el texto de imágenes/PDFs de periódicos de remate.
A diferencia de los modelos multimodales (Claude/Gemini), Vision transcribe
píxel por píxel y NO inventa datos. Está diseñado para documentos densos.

Usa la API REST con API key (no requiere archivos de credenciales).
"""
import base64
import pathlib
import requests
from ..config import GOOGLE_VISION_API_KEY

VISION_URL = "https://vision.googleapis.com/v1/images:annotate"


def _texto_de_bloque(block: dict) -> str:
    """Reconstruye el texto de un bloque. Cada 'word' de Vision es una palabra;
    concatenamos sus símbolos (caracteres) sin espacio y separamos las palabras
    con un espacio (o salto de línea según el break detectado)."""
    partes = []
    for para in block.get("paragraphs", []):
        for word in para.get("words", []):
            syms = word.get("symbols", [])
            palabra = "".join(s.get("text", "") for s in syms)
            partes.append(palabra)
            brk = ""
            if syms:
                brk = ((syms[-1].get("property", {}) or {}).get("detectedBreak", {}) or {}).get("type", "")
            if brk in ("EOL_SURE_SPACE", "LINE_BREAK"):
                partes.append("\n")
            elif brk == "HYPHEN":
                partes.append("")  # palabra cortada a fin de línea: unir sin espacio
            else:
                partes.append(" ")  # por defecto, separar palabras con espacio
    return "".join(partes)


def _reconstruir_por_columnas(anotacion: dict) -> str:
    """Reordena los bloques por COLUMNA (izquierda->derecha) y, dentro de cada
    columna, de arriba->abajo. Esto evita que Vision mezcle (interleave) las
    columnas de un periódico, que es lo que destroza los avisos de remate.

    En páginas de una sola columna el resultado es prácticamente igual al texto
    plano (todos los bloques caen en la misma columna y se ordenan por y)."""
    bloques = []
    ancho = 0
    for page in anotacion.get("pages", []):
        ancho = max(ancho, page.get("width", 0) or 0)
        for block in page.get("blocks", []):
            verts = (block.get("boundingBox", {}) or {}).get("vertices", []) or []
            xs = [v.get("x", 0) for v in verts]
            ys = [v.get("y", 0) for v in verts]
            if not xs or not ys:
                continue
            texto = _texto_de_bloque(block).strip()
            if texto:
                bloques.append({"x": min(xs), "y": min(ys), "texto": texto})
                ancho = max(ancho, max(xs))
    if not bloques:
        return ""

    # Detectar columnas agrupando los bordes izquierdos (x) con una tolerancia.
    # Aumentada a 15% del ancho para periódicos con columnas anchas
    tol = max(ancho * 0.15, 50)
    xs_orden = sorted(b["x"] for b in bloques)
    centros = []  # x representativo de cada columna, de izquierda a derecha
    for x in xs_orden:
        if not centros or x - centros[-1] > tol:
            centros.append(x)

    def col_idx(x):
        best, best_d = 0, None
        for i, cx in enumerate(centros):
            d = abs(x - cx)
            if best_d is None or d < best_d:
                best_d, best = d, i
        return best

    for b in bloques:
        b["col"] = col_idx(b["x"])
    bloques.sort(key=lambda b: (b["col"], b["y"]))
    return "\n".join(b["texto"] for b in bloques)


def _extraer_palabras(anotacion: dict) -> tuple[list[dict], int]:
    """Lista plana de PALABRAS con su caja (x0,y0,x1,y1), texto y tipo de break.
    Trabajar a nivel de palabra permite reordenar bien incluso cuando Vision
    fusionó varias columnas dentro de un mismo bloque/línea."""
    palabras = []
    ancho = 0
    for page in anotacion.get("pages", []):
        ancho = max(ancho, page.get("width", 0) or 0)
        for block in page.get("blocks", []):
            for para in block.get("paragraphs", []):
                for word in para.get("words", []):
                    syms = word.get("symbols", [])
                    texto = "".join(s.get("text", "") for s in syms)
                    if not texto.strip():
                        continue
                    verts = (word.get("boundingBox", {}) or {}).get("vertices", []) or []
                    xs = [v.get("x", 0) for v in verts]
                    ys = [v.get("y", 0) for v in verts]
                    if not xs or not ys:
                        continue
                    brk = ""
                    if syms:
                        brk = ((syms[-1].get("property", {}) or {}).get("detectedBreak", {}) or {}).get("type", "")
                    palabras.append({"x0": min(xs), "x1": max(xs), "y0": min(ys),
                                     "y1": max(ys), "t": texto, "brk": brk})
                    ancho = max(ancho, max(xs))
    return palabras, ancho


def _detectar_columnas(palabras: list[dict], ancho: int) -> list[tuple[int, int]]:
    """Detecta los límites [x_ini, x_fin) de cada columna con un perfil de
    proyección horizontal: los canalones del periódico son franjas verticales
    casi sin palabras. Ignora palabras muy grandes (titulares que cruzan
    columnas) para que no tapen los canalones."""
    if not palabras or ancho <= 0:
        return []
    alturas = sorted(p["y1"] - p["y0"] for p in palabras)
    h_med = alturas[len(alturas) // 2] or 1
    cuerpo = [p for p in palabras if (p["y1"] - p["y0"]) <= 2.5 * h_med] or palabras

    BIN = 8
    nbins = ancho // BIN + 2
    cobertura = [0] * nbins
    for p in cuerpo:
        for b in range(p["x0"] // BIN, min(p["x1"] // BIN, nbins - 1) + 1):
            cobertura[b] += 1
    pico = max(cobertura)
    if pico == 0:
        return []
    umbral = max(2, pico * 0.03)

    columnas = []
    en_col, ini = False, 0
    for i, c in enumerate(cobertura):
        if c >= umbral and not en_col:
            en_col, ini = True, i
        elif c < umbral and en_col:
            en_col = False
            columnas.append((ini * BIN, i * BIN))
    if en_col:
        columnas.append((ini * BIN, nbins * BIN))
    # Descartar franjas demasiado angostas (ruido/filetes)
    columnas = [c for c in columnas if c[1] - c[0] > ancho * 0.04]
    return columnas


def _reconstruir_por_palabras(anotacion: dict) -> str:
    """Reordena el texto PALABRA por PALABRA: asigna cada palabra a su columna
    (detectada por perfil de proyección), agrupa en líneas dentro de la columna
    y lee columna por columna, de arriba a abajo. Arregla las páginas donde
    Vision entrelazó columnas dentro de un mismo bloque (lo que el reordenado
    por bloques no puede corregir). Devuelve "" si no detecta 2+ columnas."""
    palabras, ancho = _extraer_palabras(anotacion)
    columnas = _detectar_columnas(palabras, ancho)
    if len(columnas) < 2:
        return ""

    def col_de(p):
        cx = (p["x0"] + p["x1"]) / 2
        for i, (a, b) in enumerate(columnas):
            if a <= cx < b:
                return i
        # Fuera de toda columna: la más cercana por centro
        return min(range(len(columnas)),
                   key=lambda i: abs(cx - (columnas[i][0] + columnas[i][1]) / 2))

    alturas = sorted(p["y1"] - p["y0"] for p in palabras)
    h_med = alturas[len(alturas) // 2] or 10

    grupos = [[] for _ in columnas]
    for p in palabras:
        grupos[col_de(p)].append(p)

    partes = []
    for grupo in grupos:
        if not grupo:
            continue
        grupo.sort(key=lambda p: (p["y0"], p["x0"]))
        # Agrupar en líneas: misma línea si el tope está cerca del de la línea actual
        lineas, actual, y_linea = [], [], None
        for p in grupo:
            if actual and p["y0"] - y_linea > 0.6 * h_med:
                lineas.append(actual)
                actual = []
            if not actual:
                y_linea = p["y0"]
            actual.append(p)
        if actual:
            lineas.append(actual)
        for linea in lineas:
            linea.sort(key=lambda p: p["x0"])
            for p in linea:
                partes.append(p["t"])
                partes.append("" if p["brk"] == "HYPHEN" else " ")
            if partes and partes[-1] == " ":
                partes[-1] = "\n"
        partes.append("\n")
    return "".join(partes).strip()


def _ocr_imagen_bytes(data: bytes) -> str:
    """Envía una imagen (bytes) a Vision y devuelve el texto detectado."""
    if not GOOGLE_VISION_API_KEY:
        raise RuntimeError("GOOGLE_VISION_API_KEY no configurada")

    b64 = base64.standard_b64encode(data).decode("utf-8")
    body = {
        "requests": [{
            "image": {"content": b64},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            "imageContext": {"languageHints": ["es"]},
        }]
    }
    resp = requests.post(
        f"{VISION_URL}?key={GOOGLE_VISION_API_KEY}",
        json=body,
        timeout=120,
    )
    resp.raise_for_status()
    data_json = resp.json()
    respuestas = data_json.get("responses", [{}])
    if not respuestas:
        return ""
    r0 = respuestas[0]
    if "error" in r0:
        raise RuntimeError(f"Vision API error: {r0['error'].get('message', 'desconocido')}")
    anotacion = r0.get("fullTextAnnotation", {})
    plano = anotacion.get("text", "") or ""
    # Intentar reconstrucción por palabras primero (más precisa: corrige
    # entrelazado de columnas dentro de un mismo bloque de Vision).
    try:
        por_palabras = _reconstruir_por_palabras(anotacion)
    except Exception as e:
        print(f"[ocr_vision] Reconstruccion por palabras fallo: {e}")
        por_palabras = ""
    if por_palabras:
        return por_palabras
    # Fallback: reconstrucción por bloques (funciona bien en páginas donde
    # Vision no entrelazó columnas dentro de un bloque).
    try:
        por_columnas = _reconstruir_por_columnas(anotacion)
    except Exception as e:
        print(f"[ocr_vision] Reconstruccion por columnas fallo, uso texto plano: {e}")
        por_columnas = ""
    if por_columnas and len(por_columnas) >= 0.85 * len(plano):
        return por_columnas
    return plano


def ocr_imagen(ruta: str) -> str:
    """OCR de un archivo de imagen."""
    data = pathlib.Path(ruta).read_bytes()
    return _ocr_imagen_bytes(data)


def ocr_multiples_imagenes(rutas: list[str]) -> str:
    """OCR de varias imágenes (ej. superior + inferior de una página).
    Devuelve el texto concatenado en orden."""
    partes = []
    for i, ruta in enumerate(rutas):
        texto = ocr_imagen(ruta)
        partes.append(texto)
        # Log primeras lineas para debug
        lineas = texto.split('\n')[:5]
        print(f"[ocr_vision] Imagen {i+1}: {len(texto)} caracteres, primeras lineas: {' | '.join(lineas[:3])}")
    return "\n\n".join(partes)


def ocr_pdf(ruta_pdf: str) -> str:
    """OCR de un PDF escaneado: renderiza cada página a imagen con PyMuPDF
    y las procesa con Vision. Devuelve el texto completo."""
    import fitz  # PyMuPDF

    doc = fitz.open(ruta_pdf)
    partes = []
    for num, pagina in enumerate(doc, 1):
        # Renderizar a imagen de alta resolución (zoom 2x = ~144 DPI)
        matriz = fitz.Matrix(2.0, 2.0)
        pix = pagina.get_pixmap(matrix=matriz)
        img_bytes = pix.tobytes("png")
        try:
            texto = _ocr_imagen_bytes(img_bytes)
            partes.append(f"--- PÁGINA {num} ---\n{texto}")
            print(f"[ocr_vision] PDF página {num}: {len(texto)} caracteres")
        except Exception as e:
            print(f"[ocr_vision] ERROR página {num}: {e}")
    doc.close()
    return "\n\n".join(partes)
