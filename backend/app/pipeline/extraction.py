"""
Agente de Extracción — usa Claude (Anthropic) para leer imágenes/PDFs de
avisos de remate judicial y extraer datos estructurados.
"""
import json
import base64
import pathlib
from ..config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from . import pdf_utils

CAMPOS = [
    "pais", "codigo", "fecha", "hora", "proceso", "expediente", "lugar", "categoria",
    "demandante", "demandado", "lote_casa", "descripcion", "descripcion_completa",
    "prevista", "superficie", "finca_matr", "codigo_ubicacion_prensa", "provincia", "plano", "base",
    "fianza_porcentaje", "minimo_porcentaje", "fianza", "minimo", "codigo_fuente",
    "codigo_prensa", "email_observaciones",
]

CATEGORIAS_VALIDAS = ["CASA", "APARTAMENTO", "TERRENO", "VEHICULO", "MISCELANEO"]

SYSTEM_PROMPT = "Responde SOLO con un array JSON válido. Sin texto, sin explicaciones, sin markdown."


def _cargar_aprendizaje(pais: str) -> str:
    """Construye un bloque de APRENDIZAJE a partir de las correcciones del cliente.

    IMPORTANTE: NO inyecta valores específicos (nombres, fincas, montos) de
    correcciones pasadas, porque eso hace que el modelo "filtre" datos de avisos
    anteriores dentro de la extracción nueva (contaminación). En vez de eso, solo
    indica QUÉ campos suele fallar para que el modelo les preste más atención,
    leyendo SIEMPRE del texto del aviso actual."""
    pais_code = 1 if pais == "PA" else 2 if pais == "CO" else None
    if pais_code is None:
        return ""

    try:
        from ..database import SessionLocal
        from ..models import Correccion
        db = SessionLocal()
        try:
            correcciones = (db.query(Correccion)
                            .filter(Correccion.pais == pais_code)
                            .order_by(Correccion.creado_en.desc())
                            .limit(200).all())
        finally:
            db.close()
    except Exception as e:
        print(f"[extraction] No se pudo cargar aprendizaje: {e}")
        return ""

    if not correcciones:
        return ""

    from collections import Counter
    conteo = Counter(c.campo for c in correcciones)
    vacios = Counter(c.campo for c in correcciones if c.era_vacio)

    lineas = []
    for campo, veces in conteo.most_common(10):
        nv = vacios.get(campo, 0)
        if nv >= max(1, veces / 2):
            lineas.append(f"- {campo}: suele quedar VACÍO. Búscalo con cuidado en el texto del aviso y extráelo si está presente.")
        else:
            lineas.append(f"- {campo}: suele extraerse mal. Léelo con cuidado, EXACTO del texto del aviso actual.")

    bloque = (
        "\n\n=== APRENDIZAJE (campos que sueles fallar) ===\n"
        "Estos campos han necesitado corrección en subidas anteriores. Préstales atención especial.\n"
        "REGLA CRÍTICA: NO copies valores de otros avisos ni de subidas anteriores. "
        "Cada dato debe leerse DIRECTAMENTE del texto del aviso que estás procesando AHORA:\n"
        + "\n".join(lineas)
    )
    return bloque

def _construir_prompt(pais: str, multiples_imagenes: bool = False, num_tiles: int = 0) -> str:
    campos_str = ", ".join(CAMPOS)
    aprendizaje = _cargar_aprendizaje(pais)

    prompt = f"""Eres un extractor de datos. Lee el texto de las imágenes y extrae los avisos de REMATE JUDICIAL.

Un AVISO DE REMATE se identifica porque dice "AVISO DE REMATE", "REMATE", "SUBASTA", "BASE DEL REMATE", "AVALÚO", "FIANZA", "POSTURA MÍNIMA". Ignora edictos emplazatorios de citación, sucesiones y notificaciones que NO sean remates.

Extrae CADA aviso de remate que encuentres, aunque su texto esté repartido en varios fragmentos. Une los fragmentos para reconstruir cada aviso.

REGLAS:
- Transcribe SOLO lo que leas en las imágenes. Si un dato no está, usa null.
- NUNCA inventes datos de otras fuentes ni mezcles datos de avisos distintos.
- Cada aviso es una UNIDAD: demandante y demandado son del MISMO remate (aparecen juntos, ej. "BANCO X Vs. PERSONA Y"). NO mezcles el demandante de un remate con el demandado de otro. NO uses colindantes/vecinos como partes.
- Varias propiedades con UNA sola base = UN aviso (agrúpalas). Diferentes bases = avisos separados.
- finca_matr = número de finca/folio; codigo_ubicacion_prensa = código de ubicación (distinto). No los confundas.
- TRANSCRIBE los nombres propios (edificios, PH, urbanizaciones, personas, juzgados) EXACTAMENTE como aparecen. NUNCA los cambies por nombres más comunes o parecidos (ej. si dice "COLUMBUS" escribe "COLUMBUS", NO "Colosal").
- NUNCA devuelvas texto explicativo, notas ni mensajes como si fueran un aviso. Si NO encuentras ningún remate, devuelve exactamente: []
- Extrae aunque falten algunos datos: si ves un remate pero no todos sus campos, inclúyelo con los datos que tengas y null en el resto.

Devuelve un array JSON. Cada aviso:
{{"datos": {{{campos_str}}}, "confianza": {{mismas claves, valor 0-1}}}}

pais: {"1" if pais == "PA" else "2"}, fecha: YYYY-MM-DD (año 2026), hora: HH:MM
expediente: el número de expediente TAL CUAL aparece impreso en el aviso, completo (con año y guiones si los tiene). NO lo abrevies ni modifiques.
codigo_ubicacion_prensa: el CÓDIGO DE UBICACIÓN impreso junto/después de la finca o folio (ej. "Finca 155700, Código de Ubicación 8900" -> "8900"). NO es el código de provincia. Si no aparece, null.
categoria: CASA/APARTAMENTO/TERRENO/VEHICULO/MISCELANEO
=== MONTOS (búscalos con cuidado; el OCR puede traerlos borrosos) ===
Casi todo remate indica valor base, fianza y postura mínima; búscalos e inclúyelos. PERO si el OCR los trae ilegibles o incompletos, deja ese campo en null e IGUAL incluye el aviso. Lo que define un remate es su ENCABEZADO ("AVISO DE REMATE"/"REMATE"/"SUBASTA"), NO que los números se lean bien. NUNCA descartes un remate por no poder leer sus montos.
base: el avalúo o base del remate. Búscalo tras "BASE DEL REMATE", "AVALÚO", "avaluado(a) en", "valor base", "por la suma de", "B/." o "$". Número plano sin $ ni comas ni B/. (ej: 150000.00).
fianza_porcentaje: {"10/20/25" if pais == "PA" else "40"} -- % del depósito/consignación para participar. Búscalo tras "FIANZA", "consignar", "consignación", "depósito previo", "para participar" ({"Panamá: 10, 20 o 25" if pais == "PA" else "Colombia: siempre 40"}).
minimo_porcentaje: 66.67(2/3)/50(mitad)/100(total) -- postura mínima admisible. Búscala tras "POSTURA MÍNIMA", "posturas admisibles", "no se admiten posturas inferiores", "dos terceras partes"(=66.67), "la mitad"(=50), "avalúo total"(=100).
codigo_prensa: {"LP/ML/LE" if pais == "PA" else "SEJ"}-YYYY-MM-DD-PXX o null
prevista: "[Área], [Nombre PH], Corr: [X], Dist: [Y]" para Google Maps{aprendizaje}"""

    if multiples_imagenes and num_tiles > 1:
        prompt += f"""

Se adjuntan {num_tiles} FRAGMENTOS de UNA página de periódico, ordenados de ARRIBA a ABAJO e IZQUIERDA a DERECHA. El texto está en COLUMNAS verticales (se leen de arriba a abajo, y cada columna continúa en el fragmento de abajo). Un aviso puede empezar en un fragmento y seguir en el de abajo -- ÚNELOS en un solo aviso. Si el mismo expediente/finca aparece en 2 fragmentos (por el solape), es UN SOLO aviso, no lo dupliques."""

    if pais == "PA":
        prompt += "\nContexto: periódico panameño (La Prensa, La Estrella). Panamá: fianza 10/20/25%."
    else:
        prompt += "\nContexto: tabla de remates Colombia. fianza siempre 40%."

    return prompt


def _construir_prompt_texto(pais: str) -> str:
    """Prompt para estructurar TEXTO ya extraído por OCR (no imágenes)."""
    campos_str = ", ".join(CAMPOS)
    aprendizaje = _cargar_aprendizaje(pais)
    return f"""Abajo tienes el TEXTO extraído por OCR de una o varias páginas CONSECUTIVAS de periódico de remates judiciales de {"Panamá" if pais == "PA" else "Colombia"}. Las páginas vienen EN ORDEN y el texto de una página continúa en la siguiente (puede haber varias imágenes: mitad superior y mitad inferior de cada página, y luego la página siguiente). Léelo como un solo flujo continuo.

Tu tarea: identificar los avisos de REMATE JUDICIAL en el texto y estructurarlos en JSON, captando el 100% de los datos de cada aviso.

Un AVISO DE REMATE se reconoce por su ENCABEZADO: dice "AVISO DE REMATE", "REMATE" o "SUBASTA" (aunque el OCR lo traiga dañado, ej. "AVISO DE BENATE" o "AVISO DE HEMATE" = AVISO DE REMATE). Normalmente trae base/avalúo, fianza, postura mínima, fecha, bien y juzgado. IGNORA los EDICTOS (emplazatorios, de citación, de sucesión) y notificaciones: esos empiezan con "EDICTO" o "EDICTO EMPLAZATORIO" y NO son remates.
IMPORTANTE: en una misma página (sobre todo en clasificados) puede haber MUCHOS edictos y solo unos pocos remates mezclados. Extrae TODOS los remates que encuentres aunque estén rodeados de edictos; NO descartes un remate solo porque hay muchos edictos alrededor o porque el texto está desordenado.

=== REGLAS DE SEPARACIÓN Y AGRUPACIÓN (MUY IMPORTANTE) ===
- Cada aviso de remate es una UNIDAD INDEPENDIENTE. NO mezcles datos de avisos distintos ni de edictos vecinos. Todos los datos de un aviso (demandante, demandado, finca, base, etc.) deben salir del MISMO bloque de texto del MISMO remate.
- El demandante y el demandado pertenecen AL MISMO remate y suelen aparecer juntos (ej. "BANCO X Vs. PERSONA Y" o "demandante... contra... demandado..."). NUNCA tomes el demandante de un remate y el demandado de otro aviso/edicto distinto.
- NO uses nombres de COLINDANTES o vecinos (los que "lindan" o "colindan" con la propiedad, mencionados en los linderos) como demandante ni demandado. Los colindantes NO son las partes del remate.
- Varias propiedades con UN SOLO valor base/avalúo compartido = UN SOLO remate: agrúpalas TODAS en un mismo aviso y descríbelas juntas en la descripción.
- Varias propiedades con DIFERENTES valores base = avisos SEPARADOS (uno por cada base), aunque compartan demandante y demandado.
- CONTINUACIÓN ENTRE PÁGINAS (SOLO si de verdad ocurre): un mismo aviso puede EMPEZAR al final de una página/imagen y SEGUIR al inicio de la siguiente. Únelos en UN SOLO aviso SOLO cuando sea EVIDENTE que son el MISMO remate cortado (mismo expediente, misma finca y mismo demandante/demandado). Si cada aviso ya está completo por sí mismo, trátalos como INDEPENDIENTES: NO busques ni inventes una continuación que no existe, y NO fusiones dos remates distintos. Unir una continuación significa reunir las partes del MISMO aviso, NUNCA copiar campos de un aviso a otro. Si no hay ninguna continuación real, no pasa nada: cada aviso queda por separado.

REGLAS:
- Usa SOLO el texto proporcionado abajo. Si un dato no está en el texto de ESE aviso, usa null. NUNCA rellenes un campo faltante con datos de otro aviso, de otra página, de otro documento, de subidas anteriores ni de tu conocimiento general. Es NORMAL y CORRECTO dejar campos en null cuando el periódico no los trae; es preferible un null antes que un dato inventado o prestado de otro aviso.
- El texto puede venir MUY dañado por el OCR (letras y números mezclados, palabras partidas, tildes raras), sobre todo en páginas de clasificados densas. Aun así, identifica cada bloque de remate por su encabezado y extrae lo que sea legible; deja en null solo lo que de verdad no puedas leer. Agrupa con cuidado los datos de cada aviso sin mezclar con avisos contiguos, y NO inventes para rellenar lo ilegible.
- Extrae TODOS los remates que encuentres y llena TODOS los campos que estén presentes en el texto (no dejes vacío lo que sí aparece).
- TRANSCRIBE los nombres propios (edificios, PH, urbanizaciones, personas, juzgados) EXACTAMENTE letra por letra como aparecen en el texto. NUNCA los cambies por nombres más comunes o parecidos (ej. si dice "PH COLUMBUS" escribe "COLUMBUS", NO "Colosal"). Copia el nombre tal cual.
- finca_matr es el NÚMERO DE FINCA/FOLIO (ej. "13-209", "155700"). codigo_ubicacion_prensa es el CÓDIGO DE UBICACIÓN, un dato DISTINTO. NO pongas el código de ubicación en la finca ni viceversa; son campos separados.
- NUNCA inventes. Si no hay remates, devuelve [].

Devuelve un array JSON. Cada aviso:
{{"datos": {{{campos_str}}}, "confianza": {{mismas claves, valor 0-1}}}}

pais: {"1" if pais == "PA" else "2"}, fecha: YYYY-MM-DD (año 2026), hora: HH:MM
expediente: el número de expediente TAL CUAL aparece impreso en el aviso, completo (con año y guiones si los tiene, ej: "3286/2025", "07-353-2024"). NO lo abrevies ni modifiques.
finca_matr: número de finca (Panamá) o matrícula inmobiliaria (Colombia).
codigo_ubicacion_prensa: el CÓDIGO DE UBICACIÓN que aparece impreso en el aviso, normalmente JUNTO/DESPUÉS del número de finca o folio (ej. en "Finca 155700, Código de Ubicación 8900" -> "8900"). Es un dato REAL del periódico, NO es el código de provincia. Si no aparece, usa null.
categoria: CASA/APARTAMENTO/TERRENO/VEHICULO/MISCELANEO
=== MONTOS (búscalos con cuidado; el OCR puede traerlos borrosos) ===
Casi todo remate indica valor base, fianza y postura mínima; búscalos e inclúyelos. PERO si el OCR los trae ilegibles o incompletos, deja ese campo en null e IGUAL incluye el aviso. Lo que define un remate es su ENCABEZADO ("AVISO DE REMATE"/"REMATE"/"SUBASTA"), NO que los números se lean bien. NUNCA descartes un remate por no poder leer sus montos.
base: el avalúo o base del remate. Búscalo tras "BASE DEL REMATE", "AVALÚO", "avaluado(a) en", "valor base", "por la suma de", "B/." o "$". Número plano sin $ ni comas ni B/. (ej: 150000.00).
fianza_porcentaje: {"10/20/25" if pais == "PA" else "40"} -- % del depósito/consignación para participar. Búscalo tras "FIANZA", "consignar", "consignación", "depósito previo", "para participar" ({"Panamá: 10, 20 o 25" if pais == "PA" else "Colombia: siempre 40"}).
minimo_porcentaje: 66.67(2/3)/50(mitad)/100(total) -- postura mínima admisible. Búscala tras "POSTURA MÍNIMA", "posturas admisibles", "no se admiten posturas inferiores", "dos terceras partes"(=66.67), "la mitad"(=50), "avalúo total"(=100).
codigo_prensa: {"LP/ML/LE" if pais == "PA" else "SEJ"}-YYYY-MM-DD-PXX o null
prevista: "[Área], [Nombre PH], Corr: [X], Dist: [Y]" para Google Maps{aprendizaje}"""


def _estructurar_texto_ocr(texto_ocr: str, pais: str = "PA", intento: int = 0) -> list[dict]:
    """Envía TEXTO (ya extraído por OCR) a Claude para estructurarlo en avisos.
    Es text-only: barato, rápido y sin alucinaciones (Claude tiene el texto real)."""
    import time
    import anthropic

    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY no configurada")
    if not texto_ocr or len(texto_ocr.strip()) < 20:
        print("[extraction] Texto OCR vacío o muy corto")
        return []

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=600.0)
    prompt = _construir_prompt_texto(pais)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=16384,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"{prompt}\n\n=== TEXTO OCR ===\n{texto_ocr}"}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
    except Exception as e:
        error_str = str(e).lower()
        if any(x in error_str for x in ["429", "rate", "overloaded", "529", "capacity"]):
            if intento < 3:
                wait_time = 20 * (intento + 1)
                print(f"[extraction] Rate limit. Reintento {intento+1}/3, espera {wait_time}s...")
                time.sleep(wait_time)
                return _estructurar_texto_ocr(texto_ocr, pais, intento + 1)
        raise

    text = text.strip().replace("```json", "").replace("```", "").strip()
    print(f"[extraction] Claude estructuró ({len(text)} chars): {text[:200]}")

    if not text or text.strip() == "[]":
        return []
    if not text.startswith("["):
        idx = text.find("[")
        if idx != -1:
            text = text[idx:]

    resultado = _parsear_json(text)
    for item in resultado:
        item.setdefault("datos", {})
        item.setdefault("confianza", {})
        for campo in CAMPOS:
            item["datos"].setdefault(campo, None)
            item["confianza"].setdefault(campo, 0.0)
    return resultado


def _parsear_json(texto: str) -> list[dict]:
    """Parsea JSON con recuperación de respuestas truncadas."""
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass

    # Intentar recuperar JSON truncado
    ultimo_cierre = texto.rfind("}")
    if ultimo_cierre == -1:
        raise ValueError(f"Sin JSON válido en respuesta. Primeros 200 chars: {texto[:200]}")

    texto_recortado = texto[:ultimo_cierre + 1] + "]"
    try:
        resultado = json.loads(texto_recortado)
        print(f"[extraction] Respuesta truncada, recuperados {len(resultado)} aviso(s).")
        return resultado
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON no parseable. Error: {e}. Primeros 300 chars: {texto[:300]}")


def _preparar_imagen(archivo_path: str) -> dict:
    """Convierte imagen a formato Claude."""
    ext = archivo_path.split(".")[-1].lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/jpeg")
    data = pathlib.Path(archivo_path).read_bytes()
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": mime,
                   "data": base64.standard_b64encode(data).decode("utf-8")}
    }


def _extraer_una_llamada(archivo_paths: list[str], pais: str = "PA", intento: int = 0) -> list[dict]:
    """Hace una llamada a Claude y devuelve lista de avisos extraídos."""
    import time
    import anthropic

    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY no configurada")

    print(f"[extraction] Modelo: {CLAUDE_MODEL}, archivos: {len(archivo_paths)}")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=600.0)

    # Detectar si son imágenes (no PDF)
    es_pdf = archivo_paths[0].split(".")[-1].lower() == "pdf"

    content = []
    if es_pdf:
        # PDF: enviar directo
        prompt = _construir_prompt(pais, multiples_imagenes=False)
        for p in archivo_paths:
            data = pathlib.Path(p).read_bytes()
            content.append({
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf",
                           "data": base64.standard_b64encode(data).decode("utf-8")}
            })
        content.append({"type": "text", "text": prompt})
    else:
        # IMÁGENES: dividir en tiles legibles (evita que Anthropic reduzca
        # la resolución y el texto quede ilegible -> causa de alucinaciones)
        from . import image_tiler
        tiles = image_tiler.generar_tiles(archivo_paths)
        prompt = _construir_prompt(pais, multiples_imagenes=True, num_tiles=len(tiles))
        content.extend(tiles)
        content.append({"type": "text", "text": prompt})

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=16384,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
    except Exception as e:
        error_str = str(e).lower()
        if any(x in error_str for x in ["429", "rate", "overloaded", "529", "capacity"]):
            if intento < 3:
                wait_time = 20 * (intento + 1)
                print(f"[extraction] Rate limit. Reintento {intento+1}/3, espera {wait_time}s...")
                time.sleep(wait_time)
                return _extraer_una_llamada(archivo_paths, pais, intento + 1)
        raise

    text = text.strip().replace("```json", "").replace("```", "").strip()
    print(f"[extraction] Respuesta ({len(text)} chars): {text[:300]}")

    if not text or len(text) < 2:
        raise ValueError(f"Respuesta vacía de Claude: '{text}'")

    # [] es respuesta válida (0 remates encontrados)
    if text.strip() == "[]":
        print("[extraction] Claude no encontró avisos de remate en las imágenes.")
        return []

    # Extraer JSON si hay texto antes
    if not text.startswith("["):
        idx = text.find("[")
        if idx != -1:
            text = text[idx:]
        else:
            idx = text.find("{")
            if idx != -1:
                text = "[" + text[idx:]
                if not text.rstrip().endswith("]"):
                    text = text.rstrip() + "]"

    resultado = _parsear_json(text)

    # Filtrar respuestas "meta": Claude a veces mete explicaciones/notas en los
    # campos en vez de devolver []. Detectamos frases típicas y las descartamos.
    frases_meta = [
        "no se pueden leer", "no se puede leer", "no hay avisos", "la página contiene",
        "el texto es muy denso", "está fragmentado", "no son remates", "sin avisos de remate",
        "edictos emplazatorios", "no se encontr", "no se identific", "texto ilegible",
        "no legible", "datos suficientes",
    ]
    filtrados = []
    for item in resultado:
        d = item.get("datos", {})
        # Concatenar campos de texto largos para revisar
        blob = " ".join(str(d.get(c) or "") for c in ["descripcion", "descripcion_completa", "email_observaciones"]).lower()
        if any(frase in blob for frase in frases_meta):
            print(f"[extraction] Descartada respuesta meta/explicativa (no es un aviso real)")
            continue
        filtrados.append(item)
    resultado = filtrados

    for item in resultado:
        item.setdefault("datos", {})
        item.setdefault("confianza", {})
        for campo in CAMPOS:
            item["datos"].setdefault(campo, None)
            item["confianza"].setdefault(campo, 0.0)

    return resultado


def _tiene_indicios_remate(texto: str) -> bool:
    """True si el texto OCR contiene señales claras de que hay avisos de remate."""
    if not texto:
        return False
    t = texto.upper()
    indicios = ["REMATE", "SUBASTA", "BASE DEL REMATE", "AVALUO", "AVALÚO",
                "POSTURA", "SE VENDERA", "SE VENDERÁ", "MEJOR POSTOR"]
    return sum(1 for i in indicios if i in t) >= 1


def _deduplicar(avisos: list[dict]) -> list[dict]:
    """Elimina avisos duplicados (mismo expediente+finca) que pueden aparecer
    en tiles que se solapan."""
    vistos = set()
    unicos = []
    for item in avisos:
        d = item.get("datos", {})
        finca = str(d.get("finca_matr") or "").strip()
        exp = str(d.get("expediente") or "").strip()
        clave = f"{finca}|{exp}"
        # Si no tiene ni finca ni expediente, no podemos deduplicar -> incluir
        if clave == "|":
            unicos.append(item)
            continue
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(item)
        else:
            print(f"[extraction] Duplicado descartado: exp={exp}, finca={finca}")
    return unicos


# En textos MUY largos y densos (varias imágenes / clasificados) Claude a veces
# devuelve [] aunque haya remates. Por eso el texto se procesa en trozos <= este
# tamaño y se combinan los resultados (la deduplicación quita repetidos del solape).
# Recordar: cada PÁGINA de periódico son 2 imágenes (superior + inferior) ~= 40k
# caracteres. El límite se fija en 45k para que una página completa quepa en UN
# trozo (no se parte a la mitad), y el solape (8k) es amplio para que un remate que
# sigue de una página a la siguiente no se corte entre trozos.
LIMITE_CHARS_POR_LLAMADA = 45000
OVERLAP_CHARS = 8000


def _dividir_texto(texto: str, limite: int = LIMITE_CHARS_POR_LLAMADA, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Divide un texto largo en trozos <= limite, cortando en un salto de línea
    cuando es posible, con un solape para no partir un aviso entre dos trozos."""
    if len(texto) <= limite:
        return [texto]
    trozos = []
    inicio = 0
    n = len(texto)
    while inicio < n:
        fin = min(inicio + limite, n)
        if fin < n:
            # Buscar un corte "limpio" hacia atrás (doble salto, luego simple)
            corte = texto.rfind("\n\n", inicio + limite - overlap, fin)
            if corte == -1:
                corte = texto.rfind("\n", inicio + limite - overlap, fin)
            if corte != -1 and corte > inicio:
                fin = corte
        trozos.append(texto[inicio:fin])
        if fin >= n:
            break
        inicio = max(fin - overlap, inicio + 1)  # solape para no cortar un aviso
    return trozos


def _estructurar_texto_largo(texto_ocr: str, pais: str = "PA") -> list[dict]:
    """Estructura texto OCR que puede ser largo. Si excede el límite, lo procesa
    en trozos con solape y combina; si no, hace una sola llamada. La deduplicación
    posterior (en extraer) elimina los repetidos que caigan en el solape."""
    if not texto_ocr:
        return []
    trozos = _dividir_texto(texto_ocr)
    if len(trozos) == 1:
        return _estructurar_texto_ocr(texto_ocr, pais)
    print(f"[extraction] Texto largo ({len(texto_ocr)} chars) -> {len(trozos)} trozos de <= {LIMITE_CHARS_POR_LLAMADA}")
    combinado = []
    for i, trozo in enumerate(trozos, 1):
        try:
            parcial = _estructurar_texto_ocr(trozo, pais)
            print(f"[extraction] Trozo {i}/{len(trozos)}: {len(parcial)} aviso(s)")
            combinado.extend(parcial)
        except Exception as e:
            print(f"[extraction] ERROR trozo {i}: {e}")
    return combinado


def extraer(archivo_paths, pais: str = "PA", salida_ocr: dict = None) -> list[dict]:
    """Punto de entrada. Acepta path(s) de imagen o PDF.

    Flujo principal (con Google Vision):
    - Imágenes (Panamá): Vision OCR transcribe el texto -> Claude lo estructura.
    - PDF Colombia con texto: parser local gratuito.
    - PDF Colombia escaneado: Vision OCR (renderiza páginas) -> Claude estructura.

    Si Vision no está configurado, cae al método anterior (imágenes a Claude).

    salida_ocr: dict opcional; si se provee, se guarda el texto OCR en
    salida_ocr["texto"] (para almacenarlo como fuente de aprendizaje).
    """
    from ..config import GOOGLE_VISION_API_KEY

    if salida_ocr is None:
        salida_ocr = {}

    if isinstance(archivo_paths, str):
        archivo_paths = [archivo_paths]

    archivo_path = archivo_paths[0]
    ext = archivo_path.split(".")[-1].lower()

    # === COLOMBIA PDF (uno o varios) ===
    if pais == "CO" and ext == "pdf":
        from pypdf import PdfReader
        pdfs = [p for p in archivo_paths if p.split(".")[-1].lower() == "pdf"]
        resultado_total = []
        textos_ocr = []

        for p in pdfs:
            try:
                reader = PdfReader(p)
                texto_test = (reader.pages[0].extract_text() or "").strip() if reader.pages else ""
            except Exception:
                texto_test = ""

            if len(texto_test) > 50:
                # PDF con texto seleccionable: parser local (gratis)
                from . import pdf_colombia_parser
                print(f"[extraction] Colombia PDF con texto: parser local (gratis) -> {p}")
                resultado_total.extend(pdf_colombia_parser.extraer_desde_pdf(p))
            elif GOOGLE_VISION_API_KEY:
                # PDF escaneado: Vision OCR (acumular texto para estructurar juntos)
                from . import ocr_vision
                print(f"[extraction] Colombia PDF escaneado: Vision OCR -> {p}")
                textos_ocr.append(ocr_vision.ocr_pdf(p))
            else:
                # Sin Vision: fallback a Claude por bloques
                print(f"[extraction] Colombia PDF escaneado (sin Vision): Claude por bloques -> {p}")
                bloques = pdf_utils.dividir_en_bloques(p, paginas_por_bloque=5)
                try:
                    for i, bloque_path in enumerate(bloques, 1):
                        try:
                            resultado_total.extend(_extraer_una_llamada([bloque_path], pais))
                        except Exception as e:
                            print(f"[extraction] ERROR bloque {i}: {e}")
                finally:
                    pdf_utils.limpiar_bloques(bloques)

        # Estructurar de una vez todo el texto OCR acumulado (varios PDFs escaneados)
        if textos_ocr:
            texto = "\n\n".join(textos_ocr)
            salida_ocr["texto"] = texto
            estructurado = _estructurar_texto_largo(texto, pais)
            if not estructurado and _tiene_indicios_remate(texto):
                print("[extraction] 0 avisos pero hay indicios de remate. Reintentando...")
                estructurado = _estructurar_texto_largo(texto, pais)
            resultado_total.extend(estructurado)

        print(f"[extraction] Colombia: {len(resultado_total)} aviso(s) de {len(pdfs)} PDF(s)")
        return _deduplicar(resultado_total)

    # === IMÁGENES (Panamá: superior + inferior, o imagen única) ===
    if ext != "pdf":
        if GOOGLE_VISION_API_KEY:
            from . import ocr_vision
            print(f"[extraction] {len(archivo_paths)} imagen(es): Vision OCR -> Claude")
            texto = ocr_vision.ocr_multiples_imagenes(archivo_paths)
            salida_ocr["texto"] = texto
            resultado = _estructurar_texto_largo(texto, pais)
            # Reintento: si devolvió 0 pero el texto claramente tiene remates
            if not resultado and _tiene_indicios_remate(texto):
                print("[extraction] 0 avisos pero hay indicios de remate. Reintentando...")
                resultado = _estructurar_texto_largo(texto, pais)
            return _deduplicar(resultado)
        # Sin Vision: fallback a tiles
        print("[extraction] Imágenes (sin Vision): tiles a Claude")
        resultado = _extraer_una_llamada(archivo_paths, pais)
        return _deduplicar(resultado)

    # === PDF no-Colombia (raro) ===
    if GOOGLE_VISION_API_KEY:
        from . import ocr_vision
        texto = ocr_vision.ocr_pdf(archivo_path)
        salida_ocr["texto"] = texto
        return _deduplicar(_estructurar_texto_largo(texto, pais))

    total_paginas = pdf_utils.contar_paginas(archivo_path)
    if total_paginas <= pdf_utils.PAGINAS_POR_BLOQUE:
        return _extraer_una_llamada([archivo_path], pais)
    bloques = pdf_utils.dividir_en_bloques(archivo_path)
    resultado_total = []
    try:
        for i, bloque_path in enumerate(bloques, 1):
            try:
                resultado_total.extend(_extraer_una_llamada([bloque_path], pais))
            except Exception as e:
                print(f"[extraction] ERROR bloque {i}: {e}")
    finally:
        pdf_utils.limpiar_bloques(bloques)
    return resultado_total
