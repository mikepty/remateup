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
    columnas) para que no tapen los canalones.

    CRÍTICO: el umbral es ESTRICTO. Un canalón solo califica si es una franja
    VACÍA (cobertura < 1% del pico) de al menos 2% del ancho de la página.
    Las sangrías/espacios de párrafos alineados crean franjas débiles de
    1-3 bins: si se toman como canalones se generan columnas fantasma y el
    reordenado por palabras entremezcla los avisos de páginas de ancho
    completo (texto justificado sin columnas reales)."""
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
    umbral = max(1, pico * 0.01)
    ancho_min_canalon = max(3, int(ancho * 0.02 / BIN))

    columnas = []
    en_col, ini = False, 0
    canalon_ini = None
    for i, c in enumerate(cobertura):
        if c >= umbral:
            if not en_col:
                en_col, ini = True, i
            canalon_ini = None
        elif en_col:
            # Dentro de un posible canalón: se confirma solo si llega a la
            # longitud mínima. Un canalón corto (sangría de párrafo alineada)
            # NO corta la columna: se ignora y la columna continúa.
            if canalon_ini is None:
                canalon_ini = i
            if i - canalon_ini >= ancho_min_canalon:
                columnas.append((ini * BIN, canalon_ini * BIN))
                en_col = False
    if en_col:
        columnas.append((ini * BIN, nbins * BIN))
    # Descartar franjas demasiado angostas (ruido/filetes)
    columnas = [c for c in columnas if c[1] - c[0] > ancho * 0.04]
    return columnas


def _reconstruir_por_palabras(anotacion: dict) -> str:
    """Reordena el texto PALABRA por PALABRA leyéndolo columna por columna
    (izquierda->derecha, arriba->abajo dentro de cada columna), usando las
    columnas REALES detectadas por _detectar_columnas (canalones estrictos).

    SOLO debe llamarse cuando hay 2+ columnas reales (ver _ocr_imagen_bytes):
    con columnas fantasma el texto de una página de ancho completo se
    entremezcla línea a línea y los avisos quedan partidos."""
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


def _reconstruir_lienzo_vertical(anotaciones: list[dict]) -> str:
    """Reconstruye el texto de 2 imágenes (superior + inferior) como un lienzo
    vertical único donde las columnas continúan de la primera a la segunda.
    
    Estrategia:
    1. Extraer palabras con coordenadas de ambas imágenes
    2. Detectar columnas en la imagen superior
    3. Offset vertical: palabras de img2.y += altura_img1
    4. Reordenar todas las palabras por columna, luego por y
    5. Reconstruir texto respetando el flujo columnar vertical
    """
    if len(anotaciones) != 2:
        # Fallback: si no son exactamente 2, procesar independiente
        resultado = "\n\n".join(_reconstruir_por_columnas(a) for a in anotaciones if a)
        return resultado
    
    anotacion_superior = anotaciones[0]
    anotacion_inferior = anotaciones[1]
    
    # Extraer palabras de ambas imágenes
    palabras_sup, ancho_sup = _extraer_palabras(anotacion_superior)
    palabras_inf, ancho_inf = _extraer_palabras(anotacion_inferior)
    
    # Liberar anotaciones originales
    del anotacion_superior, anotacion_inferior
    
    if not palabras_sup and not palabras_inf:
        return ""
    
    # Calcular altura de imagen superior para offset vertical
    if palabras_sup:
        altura_superior = max(p["y1"] for p in palabras_sup)
    else:
        altura_superior = 0
    
    # Offset vertical: mover palabras de imagen inferior hacia abajo
    for p in palabras_inf:
        p["y0"] += altura_superior
        p["y1"] += altura_superior
    
    # Combinar todas las palabras
    todas_palabras = palabras_sup + palabras_inf
    del palabras_sup, palabras_inf  # Liberar listas originales
    
    ancho_total = max(ancho_sup, ancho_inf)
    
    if not todas_palabras:
        return ""
    
    # Detectar columnas en el conjunto completo
    columnas = _detectar_columnas(todas_palabras, ancho_total)
    
    if not columnas:
        # Fallback: sin columnas detectables, ordenar por y globalmente
        todas_palabras.sort(key=lambda p: (p["y0"], p["x0"]))
        partes = []
        for p in todas_palabras:
            partes.append(p["t"])
            partes.append("" if p["brk"] == "HYPHEN" else " ")
        resultado = "".join(partes).strip()
        del todas_palabras, partes
        return resultado
    
    print(f"[ocr_vision] Lienzo vertical: {len(columnas)} columnas detectadas, "
          f"{len(todas_palabras)} palabras totales")
    
    # Asignar cada palabra a su columna
    def col_de(p):
        cx = (p["x0"] + p["x1"]) / 2
        return min(range(len(columnas)),
                   key=lambda i: abs(cx - (columnas[i][0] + columnas[i][1]) / 2))
    
    alturas = sorted(p["y1"] - p["y0"] for p in todas_palabras)
    h_med = alturas[len(alturas) // 2] or 10
    
    grupos = [[] for _ in columnas]
    for p in todas_palabras:
        grupos[col_de(p)].append(p)
    
    del todas_palabras  # Liberar después de agrupar
    
    partes = []
    for idx_col, grupo in enumerate(grupos):
        if not grupo:
            continue
        # Ordenar por y dentro de la columna (vertical)
        grupo.sort(key=lambda p: (p["y0"], p["x0"]))
        
        # Agrupar en líneas
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
        partes.append("\n\n")  # Separador entre columnas
    
    resultado = "".join(partes).strip()
    del grupos, partes, lineas
    return resultado


def _ocr_imagen_bytes_raw(data: bytes) -> dict:
    """Envía una imagen (bytes) a Vision y devuelve la anotación RAW completa."""
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
        return {}
    r0 = respuestas[0]
    if "error" in r0:
        raise RuntimeError(f"Vision API error: {r0['error'].get('message', 'desconocido')}")
    return r0.get("fullTextAnnotation", {})


def _ocr_imagen_bytes(data: bytes) -> str:
    """Envía una imagen (bytes) a Vision y devuelve el texto detectado."""
    anotacion = _ocr_imagen_bytes_raw(data)
    plano = anotacion.get("text", "") or ""
    # Reconstrucción por palabras SOLO cuando hay columnas reales (canalones
    # estrictamente vacíos detectados por proyección). En páginas de ancho
    # completo (avisos justificados sin columnas) el detector NO debe hallar
    # columnas: reordenar ahí con columnas fantasma entremezcla los avisos
    # línea a línea y descuaja montos y expedientes.
    try:
        palabras_check, ancho_check = _extraer_palabras(anotacion)
        hay_columnas = len(_detectar_columnas(palabras_check, ancho_check)) >= 2
    except Exception as e:
        print(f"[ocr_vision] Deteccion de columnas fallo: {e}")
        hay_columnas = False
    if hay_columnas:
        try:
            por_palabras = _reconstruir_por_palabras(anotacion)
        except Exception as e:
            print(f"[ocr_vision] Reconstruccion por palabras fallo: {e}")
            por_palabras = ""
        if por_palabras:
            return por_palabras
    # Sin columnas reales: el orden de lectura de Vision (texto plano) es el
    # correcto para páginas de ancho completo. NO se intenta reordenar por
    # bloques: su detección laxa vuelve a crear columnas fantasma y
    # entremezcla los avisos.
    return plano


def ocr_imagen(ruta: str) -> str:
    """OCR de un archivo de imagen."""
    data = pathlib.Path(ruta).read_bytes()
    return _ocr_imagen_bytes(data)


def ocr_multiples_imagenes(rutas: list[str]) -> str:
    """OCR de varias imágenes (ej. superior + inferior de una página).
    
    Si son 2 imágenes (típico de Panamá: mitad superior + inferior de una
    página vertical), las reconstruye como un lienzo vertical único donde las
    columnas continúan de la imagen superior a la inferior.
    
    Si es 1 imagen o 3+, las procesa independientemente y concatena."""
    if len(rutas) == 2:
        # Caso especial: 2 imágenes = mitades superior/inferior de UNA página
        # Obtener anotaciones RAW de Vision para reconstruir el lienzo completo
        anotaciones = []
        for i, ruta in enumerate(rutas):
            data = pathlib.Path(ruta).read_bytes()
            anotacion = _ocr_imagen_bytes_raw(data)
            anotaciones.append(anotacion)
            print(f"[ocr_vision] Imagen {i+1} ({ruta}): anotación obtenida")
            del data  # Liberar memoria de imagen
        
        # Reconstruir como lienzo vertical: columnas de img1 continúan en img2
        texto = _reconstruir_lienzo_vertical(anotaciones)
        del anotaciones  # Liberar anotaciones grandes
        lineas = texto.split('\n')[:5]
        print(f"[ocr_vision] Lienzo vertical reconstruido: {len(texto)} caracteres, primeras lineas: {' | '.join(lineas[:3])}")
        return texto
    
    # Caso general: 1 imagen o 3+ imágenes → procesar independiente
    partes = []
    for i, ruta in enumerate(rutas):
        texto = ocr_imagen(ruta)
        partes.append(texto)
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
