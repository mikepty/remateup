"""
Agente de Extracción (equivalente al "OCR Agent" + "Information Extraction Agent"
de la propuesta original, simplificados en uno solo porque Gemini hace ambas
cosas en una sola llamada: lee la imagen/PDF Y estructura el texto).
"""
from google import genai
from google.genai import types
import json
import pathlib
from ..config import GEMINI_API_KEY, GEMINI_MODEL
from . import pdf_utils

CAMPOS = [
    "pais", "codigo", "fecha", "hora", "proceso", "expediente", "lugar", "categoria",
    "demandante", "demandado", "lote_casa", "descripcion",
    "superficie", "finca_matr", "codigo_ubicacion", "provincia", "plano", "base",
    "fianza_porcentaje", "minimo_porcentaje", "fianza", "minimo", "codigo_fuente",
]

CATEGORIAS_VALIDAS = ["CASA", "APARTAMENTO", "TERRENO", "VEHICULO", "MISCELANEO"]


def _construir_prompt(pais: str, multiples_imagenes: bool = False) -> str:
    base = f"""Eres un asistente experto en extracción de datos de avisos de remate judicial.
Analiza el/los documento(s) adjunto(s) y extrae la información en formato JSON.

Devuelve un array de objetos. Cada objeto representa UN remate a subir, según
estas reglas para agrupar o separar bienes (MUY IMPORTANTE, definidas por el cliente):

- ESCENARIO A -- varios bienes bajo UN SOLO valor base/avalúo: son parte del
  MISMO remate. NO los separes en objetos distintos. Ponlos todos juntos,
  descritos uno por uno, dentro de un único campo "descripcion" del mismo objeto.
- ESCENARIO B -- varios bienes, cada uno con su PROPIO valor base/avalúo
  independiente: sí van en objetos separados, uno por bien, aunque compartan
  expediente, demandante y demandado.
La señal para decidir cuál escenario aplica es: ¿hay un solo monto de base
para todos los bienes, o cada bien tiene su propio monto? Si tienes dudas
genuinas, trátalos como Escenario B (separados) y dilo con confianza baja.

Cada objeto debe tener DOS partes:
1. "datos": un objeto con EXACTAMENTE estas claves: {", ".join(CAMPOS)}
   (usa null si el dato no aparece en el documento, NUNCA inventes valores)
2. "confianza": un objeto con la MISMA estructura de claves, valor entre 0 y 1.

Reglas de formato:
- "pais": 1 para Panamá, 2 para Colombia.
- "fecha" en formato YYYY-MM-DD. "hora" en formato HH:MM.
- "categoria": debe ser EXACTAMENTE una de estas 5 palabras: {", ".join(CATEGORIAS_VALIDAS)}.
  CASA/APARTAMENTO/TERRENO son inmuebles obvios. VEHICULO es cualquier carro,
  moto, camión. MISCELANEO es todo lo demás que NO sea inmueble ni vehículo:
  muebles, joyas, materia prima, maquinaria, depósitos, equipos, etc.
- "base": el valor de avalúo/base, como número plano SIN símbolo de moneda,
  SIN comas ni puntos de miles. Ejemplo correcto: 39500.00
- "fianza_porcentaje": el PORCENTAJE de fianza que el aviso indica que hay que
  depositar para participar (normalmente aparece explícito en el texto, ej.
  "fianza del 10%" -> 10). Panamá usa 10, 20 o 25 (varía por aviso, leerlo del
  texto). Colombia es SIEMPRE 40 -- si no lo ves explícito en el texto de
  Colombia, igual responde 40 (es un valor fijo conocido).
- "minimo_porcentaje": el PORCENTAJE mínimo de la base con el que se puede
  ganar el remate, según lo que ordene el juzgado en el texto (ej. "no será
  inferior a las dos terceras partes" -> 66.67; "la mitad de la base" -> 50;
  "la totalidad del avalúo" -> 100). Este SÍ varía por aviso en ambos países,
  léelo con cuidado del texto.
- "fianza" y "minimo": SOLO si el aviso también imprime el MONTO en dinero ya
  calculado (no el porcentaje) además del porcentaje. Si el aviso solo da el
  porcentaje y no un monto en dinero, deja "fianza" y "minimo" en null --
  nuestro sistema los calcula automáticamente desde base + porcentaje.
- "descripcion_completa": la DESCRIPCIÓN COMPLETA del bien tal como aparece
  en el documento (dirección detallada, metros, referencias, todo el texto).
- "descripcion": RESUMEN corto (1-2 líneas) con los datos clave para la
  tarjeta. Formato: "[Superficie], [Tipo], [Dirección resumida], [Ubicación]."
- "codigo_fuente": si ves visible en la imagen algún código de identificación
  de la publicación, edición o página del periódico, inclúyelo aquí. Si no es
  visible, usa null (no es un campo crítico, se puede completar manualmente).
- Si el texto está borroso, cortado o ambiguo, refleja eso con confianza baja,
  NO adivines el valor con confianza alta.
- Responde ÚNICAMENTE con el array JSON, sin texto adicional, sin markdown."""

    if multiples_imagenes:
        base += """\n\nIMPORTANTE sobre las imágenes adjuntas: son DOS (o más) fotos de la
MISMA página de periódico, tomadas en partes porque la página es muy larga
para caber en una sola foto legible. Las imágenes están en orden: la primera
es la mitad SUPERIOR de la página, la siguiente es la mitad INFERIOR
(continúa exactamente donde termina la primera).

 Las imágenes muestran el texto en formato de COLUMNAS verticales (como un
periódico tradicional). Cada columna contiene múltiples avisos de remate
apilados verticalmente. Para leer correctamente:
1. Primero identifica todas las COLUMNAS visibles en cada imagen.
2. Lee cada columna de ARRIBA A BAJO, completando una columna antes de pasar
   a la siguiente.
3. Un aviso de remate puede empezar en la imagen superior y continuar en la
   inferior -- trátalas como una sola página continua.
4. Busca patrones como: "AVISO DE REMATE", "EDICTO EMPLAZATORIO", "JUZGADO",
   "EXPEDIENTE", "DEMANDANTE", "DEMANDADO", "VALOR BASE", "BIEN A REMATAR",
   "AVALÚO", "FIANZA", "POSTURA MÍNIMA", "TRES (3) VECES CONSECUTIVAS".
5. NO ignores avisos por estar parcialmente cortados entre imágenes -- si el
   encabezado está en una y el cuerpo en otra, combínalos en un solo aviso.
6. Procesa TODAS las columnas y TODOS los avisos visibles en ambas imágenes.
   La página típica de periódico tiene entre 4 y 8 columnas con varios avisos
   cada una -- espero encontrar MÚLTIPLES avisos, no solo uno."""

    if pais == "PA":
        base += """

CONTEXTO PA Panamá -- sección "BUSCAFÁCIL" / judicial de un periódico panameño
(La Prensa, El Panamá América, etc.). La página típica tiene:
- Encabezado de sección ("BUSCAFÁCIL", "BIENES RAICES", "VARIOS", etc.)
- Múltiples columnas con avisos judiciales mezclados con avisos comerciales.
- Los AVISOS DE REMATE se identifican por frases como:
  "AVISO DE REMATE", "EDICTO EMPLAZATORIO", "JUZGADO ... CIRCUITO CIVIL",
  "SUBASTA", "BIEN INMUEBLE", "VALOR DEL TRASPASO", "BASE DEL REMATE",
  "FIANZA", "POSTURA MÍNIMA", "DOS TERCERAS PARTES", "TRES VECES CONSECUTIVAS".
- Los avisos de remate SIEMPRE mencionan un JUZGADO (ej. "JUZGADO PRIMERO
  DE CIRCUITO CIVIL DE CHIRIQUI") y un PROCESO (ej. "EJECUTIVO HIPOTECARIO",
  "EJECUTIVO FISCAL", "SUCESIÓN INTESTADA").
- Ignora avisos comerciales (venta de carros, alquiler de locales, etc.).
- Ignora "EDICTO EMPLAZATORIO" que NO sean de remate (sucesiones, etc.).

 Campos específicos para Panamá:
- "lugar": el JUZGADO que ordena el remate (ej. "JUZGADO PRIMERO DE CIRCUITO
  CIVIL DE CHIRIQUI").
- "provincia": la PROVINCIA de Panamá donde está el bien (Bocas del Toro,
  Coclé, Colón, Chiriquí, Darién, Herrera, Los Santos, Panamá, Panamá Oeste,
  Veraguas). A veces viene en la dirección del inmueble.
- "descripcion": RESUMEN corto del bien como aparece en la app RemateHoy.
  Formato: "[Superficie], [Tipo propiedad], CORR: [Corregimiento], DIST: [Distrito], [Provincia]."
  Ejemplos:
  - "19 HEC 4926.62 M2, CORREGIMIENTO Y DISTRITO, GUALACA, CHIRIQUI."
  - "332 M2, PH PRINCESA Y CONDESA DEL MAR, CORR: BELLA VISTA, DIST: PANAMA."
  - "271.61 M2, LAGO EMPERADOR, CORR: JUAN DEMOSTENES AROSEMENA, DIST: ARRAIJAN."
  NO copies el texto completo del periódico -- resume en 1-2 líneas con los datos clave.
- "finca_matr": el número de FOLIO REAL / FINCA si aparece.
- "base": el monto del avalúo o valor base (ej. "$395,000.00" -> 395000.00).
- "fianza_porcentaje": el porcentaje de fianza (10, 20 o 25).
- "minimo_porcentaje": 66.67 (dos terceras partes), 50 (la mitad) o 100."""
    else:
        base += """

CONTEXTO CO Colombia -- tabla de remates judiciales de Colombia, en formato
imagen dentro de un PDF o fotografía de periódico. La página típica tiene:
- Múltiples columnas con avisos de remate en formato tabular.
- Cada aviso tiene: juzgado, expediente, demandante, demandado, dirección
  del inmueble, avalúo, porcentaje mínimo, categoría.
- Los avisos SIEMPRE mencionan un JUZGADO (ej. "1 C.C ESPINAL T.",
  "19 C.C. BOGOTA") y un NÚMERO DE EXPEDIENTE.

 Campos específicos para Colombia:
- "lugar": el JUZGADO que emite el aviso, casi siempre abreviado:
  "19 C.C. BOGOTA" (Juzgado 19 Circuito Civil de Bogotá),
  "3 C.C. PEREIRA" (Juzgado 3 Circuito Civil de Pereira).
  Busca patrón: número + "C.C." + ciudad.
- "provincia" (departamento): NO aparece como campo separado. Está INCRUSTADO
  al final de la dirección/descripción. Ejemplo:
  "CRA.10 No. 3-59, ESPINAL, TOLIMA" -> departamento = TOLIMA.
  Departamentos: Amazonas, Antioquia, Arauca, Atlántico, Bogotá, Bolívar,
  Boyacá, Caldas, Caquetá, Casanare, Cauca, Cesar, Chocó, Córdoba,
  Cundinamarca, Guainía, Guaviare, Huila, La Guajira, Magdalena, Meta,
  Nariño, Norte de Santander, Putumayo, Quindío, Risaralda, San Andrés y
  Providencia, Santander, Sucre, Tolima, Valle del Cauca, Vaupés, Vichada.
- "minimo_porcentaje": el juzgado SIEMPRE lo indica. Busca "X% del avalúo",
  "no será inferior a...", "postura mínima de...". Opciones comunes: 70%, 50%.
- "fianza_porcentaje": SIEMPRE 40% (fijo por ley en Colombia).
- "base": el monto del avalúo (ej. "$786,100,000" -> 786100000.00)."""
    return base


def _parsear_json_con_recuperacion(texto: str) -> list[dict]:
    """
    Intenta parsear el JSON normal. Si la respuesta viene cortada (documento
    muy largo, ej. el PDF de 75 páginas de Colombia, puede exceder el límite
    de tokens de salida del modelo), rescata todos los objetos COMPLETOS que
    sí llegaron bien, descartando solo el último objeto incompleto -- en vez
    de perder todo el documento por un solo aviso cortado a la mitad.
    """
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass

    ultimo_cierre = texto.rfind("}")
    if ultimo_cierre == -1:
        raise ValueError("La respuesta de Gemini no contiene ningún objeto JSON completo -- "
                          "reintenta, o si persiste, el documento puede ser demasiado grande "
                          "para una sola llamada (dividir en bloques de páginas).")

    texto_recortado = texto[:ultimo_cierre + 1] + "]"
    try:
        resultado = json.loads(texto_recortado)
        print(f"[extraction] AVISO: la respuesta de Gemini venía truncada. "
              f"Se recuperaron {len(resultado)} aviso(s) completos; "
              f"es posible que falten avisos del final del documento.")
        return resultado
    except json.JSONDecodeError as e:
        raise ValueError(f"No se pudo parsear ni siquiera con recuperación. "
                          f"El documento probablemente necesita dividirse en bloques de páginas. "
                          f"Error original: {e}")


def _preparar_contenido(archivo_path: str, client) -> object:
    """Convierte un archivo en el 'Part' que Gemini espera, usando Files API
    si es grande, o datos inline si es chico."""
    ext = archivo_path.split(".")[-1].lower()
    mime = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "pdf": "application/pdf"
    }.get(ext, "image/jpeg")

    tamano_mb = pathlib.Path(archivo_path).stat().st_size / (1024 * 1024)
    UMBRAL_FILES_API_MB = 15
    if tamano_mb > UMBRAL_FILES_API_MB:
        return client.files.upload(file=archivo_path)
    return types.Part.from_bytes(data=pathlib.Path(archivo_path).read_bytes(), mime_type=mime)


def _extraer_una_llamada(archivo_paths: list[str], pais: str = "PA", intento: int = 0) -> list[dict]:
    """
    Hace UNA llamada a Gemini sobre uno o más archivos que representan la
    MISMA unidad de contexto (ej. imagen única, o mitad superior + mitad
    inferior de una misma página de periódico). Devuelve una lista de dicts:
      { "datos": {...campos...}, "confianza": {...campos...} }
    """
    import time

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY no configurada")

    print(f"[extraction] API key: {GEMINI_API_KEY[:8]}...{GEMINI_API_KEY[-4:]} (longitud: {len(GEMINI_API_KEY)})")
    print(f"[extraction] Modelo: {GEMINI_MODEL}")

    client = genai.Client(api_key=GEMINI_API_KEY)
    contenidos = [_preparar_contenido(p, client) for p in archivo_paths]
    prompt = _construir_prompt(pais, multiples_imagenes=len(archivo_paths) > 1)

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[*contenidos, prompt],
            config=types.GenerateContentConfig(
                max_output_tokens=65536,
                http_options=types.HttpOptions(timeout=300_000),
            ),
        )
    except Exception as e:
        error_str = str(e).lower()
        # Si es rate limit o quota exceeded, reintentar con espera
        if ("429" in error_str or "quota" in error_str or "rate" in error_str or "exceeded" in error_str):
            if intento < 3:
                wait_time = 30 * (intento + 1)  # 30s, 60s, 90s
                print(f"[extraction] Rate limit alcanzado. Reintento {intento+1}/3, esperando {wait_time}s...")
                time.sleep(wait_time)
                return _extraer_una_llamada(archivo_paths, pais, intento + 1)
            else:
                print(f"[extraction] Rate limit persistente tras 3 reintentos.")
                raise
        raise

    text = response.text.strip().replace("```json", "").replace("```", "").strip()
    resultado = _parsear_json_con_recuperacion(text)

    for item in resultado:
        item.setdefault("datos", {})
        item.setdefault("confianza", {})
        for campo in CAMPOS:
            item["datos"].setdefault(campo, None)
            item["confianza"].setdefault(campo, 0.0)

    return resultado


def extraer(archivo_paths, pais: str = "PA") -> list[dict]:
    """
    Punto de entrada público. Acepta un solo path (string, compatibilidad
    con el código anterior) o una lista de paths.

    - Si es UN SOLO PDF con muchas páginas (ej. feed semanal de Colombia):
      se divide en bloques automáticamente para evitar respuestas truncadas.
    - Si son VARIAS imágenes (ej. mitad superior + mitad inferior de una
      página larga de periódico panameño): se mandan juntas en una sola
      llamada, indicándole a Gemini que son continuación una de otra.
    """
    if isinstance(archivo_paths, str):
        archivo_paths = [archivo_paths]

    # Caso: varias imágenes de la MISMA página (no PDFs) -> una sola llamada conjunta
    if len(archivo_paths) > 1:
        return _extraer_una_llamada(archivo_paths, pais)

    archivo_path = archivo_paths[0]
    ext = archivo_path.split(".")[-1].lower()
    if ext != "pdf":
        return _extraer_una_llamada([archivo_path], pais)

    total_paginas = pdf_utils.contar_paginas(archivo_path)
    if total_paginas <= pdf_utils.PAGINAS_POR_BLOQUE:
        return _extraer_una_llamada([archivo_path], pais)

    print(f"[extraction] PDF de {total_paginas} páginas -- dividiendo en bloques "
          f"de {pdf_utils.PAGINAS_POR_BLOQUE} para evitar respuestas truncadas.")
    bloques = pdf_utils.dividir_en_bloques(archivo_path)
    resultado_total = []
    try:
        for i, bloque_path in enumerate(bloques, 1):
            try:
                parcial = _extraer_una_llamada([bloque_path], pais)
                print(f"[extraction] Bloque {i}/{len(bloques)}: {len(parcial)} aviso(s).")
                resultado_total.extend(parcial)
            except Exception as e:
                print(f"[extraction] ERROR en bloque {i}/{len(bloques)}, se omite: {e}")
    finally:
        pdf_utils.limpiar_bloques(bloques)

    return resultado_total
