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

def _construir_prompt(pais: str, multiples_imagenes: bool = False) -> str:
    campos_str = ", ".join(CAMPOS)

    prompt = f"""Extrae avisos de REMATE JUDICIAL de las imágenes. Un remate tiene: valor base/avalúo + fianza + postura mínima + fecha + bien descrito + juzgado + demandante + demandado.

Ignora edictos, citaciones y otros avisos que NO sean subastas/remates.

REGLAS CRÍTICAS:
- NO dupliques avisos. Si el mismo remate aparece en ambas imágenes (porque se corta entre la parte superior e inferior), es UN SOLO aviso.
- Cada aviso de remate tiene un EXPEDIENTE o FINCA único. Si dos extractos tienen el mismo expediente/finca, son el MISMO aviso.
- Lee con cuidado TODOS los datos: base, fianza, porcentajes, demandante, demandado. No dejes campos vacíos si están visibles.
- SOLO transcribe datos VISIBLES. Si no puedes leer un dato, usa null. NUNCA inventes.

Devuelve un array JSON. Cada objeto tiene:
1. "datos": objeto con claves: {campos_str} (null si no aparece)
2. "confianza": objeto con las mismas claves, valor 0-1

Formato:
- pais: {"1 (Panamá)" if pais == "PA" else "2 (Colombia)"}
- fecha: YYYY-MM-DD, hora: HH:MM. Estamos en julio 2026. El periódico es de 2026.
- categoria: CASA, APARTAMENTO, TERRENO, VEHICULO o MISCELANEO
- base: número sin símbolo ni comas (ej: 150000.00)
- fianza_porcentaje: % para participar (PA: 10/20/25, CO: siempre 40)
- minimo_porcentaje: % postura mínima (66.67=dos terceras, 50=mitad, 100=total)
- fianza/minimo: monto calculado si está impreso, sino null
- descripcion: resumen 1-2 líneas "[Superficie], [Tipo], [Ubicación]"
- descripcion_completa: texto íntegro del bien
- prevista: texto para Google Maps "[Área], [Nombre PH/Urbanización], Corr: [X], Dist: [Y]"
- codigo_prensa: SIGLA-YYYY-MM-DD-PXX (LP/ML/LE para PA, SEJ para CO) o null
- email_observaciones: email si aparece, sino null"""

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
    prompt = _construir_prompt(pais, multiples_imagenes=len(archivo_paths) > 1)

    # Construir contenido
    content = []
    for p in archivo_paths:
        ext = p.split(".")[-1].lower()
        if ext == "pdf":
            data = pathlib.Path(p).read_bytes()
            content.append({
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf",
                           "data": base64.standard_b64encode(data).decode("utf-8")}
            })
        else:
            content.append(_preparar_imagen(p))
    content.append({"type": "text", "text": prompt})

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8192,
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

    # Varias imágenes de la misma página -> una llamada conjunta (Panamá)
    if len(archivo_paths) > 1:
        return _extraer_una_llamada(archivo_paths, pais)

    if ext != "pdf":
        return _extraer_una_llamada([archivo_path], pais)

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
