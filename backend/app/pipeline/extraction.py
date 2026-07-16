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
    "prevista", "superficie", "finca_matr", "codigo_ubicacion", "provincia", "plano", "base",
    "fianza_porcentaje", "minimo_porcentaje", "fianza", "minimo", "codigo_fuente",
    "codigo_prensa", "email_observaciones",
]

CATEGORIAS_VALIDAS = ["CASA", "APARTAMENTO", "TERRENO", "VEHICULO", "MISCELANEO"]

SYSTEM_PROMPT = "Responde SOLO con un array JSON válido. Sin texto, sin explicaciones, sin markdown."

def _construir_prompt(pais: str, multiples_imagenes: bool = False, num_tiles: int = 0) -> str:
    campos_str = ", ".join(CAMPOS)

    prompt = f"""Analiza las imágenes adjuntas y extrae SOLO la información que puedas LEER DIRECTAMENTE del texto visible.

PROHIBIDO inventar datos. Si no puedes leer un dato claramente, usa null. Si NO hay avisos de remate legibles, devuelve [].

Busca avisos de REMATE JUDICIAL (tienen: valor base, fianza, postura mínima, fecha, bien descrito, juzgado, demandante, demandado). Ignora otros edictos (citaciones, sucesiones, notificaciones).

Devuelve un array JSON. Cada aviso:
{{"datos": {{{campos_str}}}, "confianza": {{mismas claves, valor 0-1}}}}

pais: {"1" if pais == "PA" else "2"}, fecha: YYYY-MM-DD (año 2026), hora: HH:MM
categoria: CASA/APARTAMENTO/TERRENO/VEHICULO/MISCELANEO
base: número plano sin $ ni comas (ej: 150000.00)
fianza_porcentaje: {"10/20/25" if pais == "PA" else "40"}
minimo_porcentaje: 66.67(2/3)/50(mitad)/100(total)
codigo_prensa: {"LP/ML/LE" if pais == "PA" else "SEJ"}-YYYY-MM-DD-PXX o null
prevista: "[Área], [Nombre PH], Corr: [X], Dist: [Y]" para Google Maps"""

    if multiples_imagenes and num_tiles > 1:
        prompt += f"""

IMPORTANTE: Se adjuntan {num_tiles} imágenes que son FRAGMENTOS (mosaicos) de UNA SOLA página de periódico, ordenados de ARRIBA hacia ABAJO e IZQUIERDA a DERECHA. El texto está en COLUMNAS verticales que se leen de arriba a abajo. Un mismo aviso puede aparecer partido entre dos fragmentos que se solapan -- en ese caso es UN SOLO aviso, NO lo dupliques. Cada aviso tiene un EXPEDIENTE y FINCA únicos; si ves el mismo expediente/finca en dos fragmentos, es el MISMO aviso. Reconstruye el texto completo de cada aviso uniendo los fragmentos."""

    if pais == "PA":
        prompt += "\nContexto: periódico panameño (La Prensa, La Estrella), sección judicial. Los remates dicen 'AVISO DE REMATE', 'BASE DEL REMATE', 'AVALÚO', 'FIANZA', 'POSTURA'."
    else:
        prompt += "\nContexto: PDF Colombia, tabla de remates. fianza siempre 40%."

    return prompt

    if multiples_imagenes:
        prompt += """

Las 2 imágenes son la MISMA página (superior + inferior). Trátalas como un lienzo continuo. Fusiona avisos que empiezan arriba y terminan abajo."""

    if pais == "PA":
        prompt += """

Contexto: periódico panameño, sección judicial. Solo extrae REMATES (tienen "AVISO DE REMATE", "BASE", "FIANZA", "POSTURA MÍNIMA"). Ignora todo lo demás."""
    else:
        prompt += """

Contexto: PDF de remates Colombia. Cada aviso tiene juzgado, expediente, avalúo, porcentaje mínimo. fianza_porcentaje siempre 40."""

    return prompt


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

    for item in resultado:
        item.setdefault("datos", {})
        item.setdefault("confianza", {})
        for campo in CAMPOS:
            item["datos"].setdefault(campo, None)
            item["confianza"].setdefault(campo, 0.0)

    return resultado


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


def extraer(archivo_paths, pais: str = "PA") -> list[dict]:
    """Punto de entrada. Acepta path(s) de imagen o PDF."""
    if isinstance(archivo_paths, str):
        archivo_paths = [archivo_paths]

    archivo_path = archivo_paths[0]
    ext = archivo_path.split(".")[-1].lower()

    # Colombia + PDF: intentar parser local primero, si no hay texto usar Claude por bloques
    if pais == "CO" and ext == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(archivo_path)
        texto_test = (reader.pages[0].extract_text() or "").strip() if reader.pages else ""

        if len(texto_test) > 50:
            # PDF con texto seleccionable: usar parser local (gratis)
            from . import pdf_colombia_parser
            print(f"[extraction] Colombia PDF con texto: usando parser local (gratis)")
            resultado = pdf_colombia_parser.extraer_desde_pdf(archivo_path)
            print(f"[extraction] Parser local extrajo {len(resultado)} aviso(s)")
            return resultado
        else:
            # PDF escaneado (solo imágenes): usar Claude por bloques
            print(f"[extraction] Colombia PDF escaneado: usando Claude por bloques")
            total_paginas = pdf_utils.contar_paginas(archivo_path)
            bloques = pdf_utils.dividir_en_bloques(archivo_path, paginas_por_bloque=5)
            resultado_total = []
            try:
                for i, bloque_path in enumerate(bloques, 1):
                    try:
                        parcial = _extraer_una_llamada([bloque_path], pais)
                        print(f"[extraction] Bloque {i}/{len(bloques)}: {len(parcial)} aviso(s).")
                        resultado_total.extend(parcial)
                    except Exception as e:
                        print(f"[extraction] ERROR bloque {i}: {e}")
            finally:
                pdf_utils.limpiar_bloques(bloques)
            return resultado_total

    # Varias imágenes de la misma página (Panamá: superior + inferior).
    # El tiler las apila en una sola página y las divide en tiles legibles,
    # que se envían juntos en UNA llamada. Se deduplica por finca/expediente.
    if len(archivo_paths) > 1:
        resultado = _extraer_una_llamada(archivo_paths, pais)
        return _deduplicar(resultado)

    if ext != "pdf":
        # Imagen única -> también se divide en tiles legibles
        resultado = _extraer_una_llamada([archivo_path], pais)
        return _deduplicar(resultado)

    # PDF grande no-Colombia: dividir en bloques
    total_paginas = pdf_utils.contar_paginas(archivo_path)
    if total_paginas <= pdf_utils.PAGINAS_POR_BLOQUE:
        return _extraer_una_llamada([archivo_path], pais)

    print(f"[extraction] PDF de {total_paginas} págs, dividiendo en bloques.")
    bloques = pdf_utils.dividir_en_bloques(archivo_path)
    resultado_total = []
    try:
        for i, bloque_path in enumerate(bloques, 1):
            try:
                parcial = _extraer_una_llamada([bloque_path], pais)
                print(f"[extraction] Bloque {i}/{len(bloques)}: {len(parcial)} aviso(s).")
                resultado_total.extend(parcial)
            except Exception as e:
                print(f"[extraction] ERROR bloque {i}: {e}")
    finally:
        pdf_utils.limpiar_bloques(bloques)

    return resultado_total
