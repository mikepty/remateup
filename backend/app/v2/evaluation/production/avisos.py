"""FASE 12 — Partes 1 y 2: segmentación real de PDFs multiaviso y validación aviso por aviso.

Diagnóstico auditado (Parte 1):

  OCR   : `OCRProcessor.process_pdf` (ocr/processor.py) obtiene el texto real por página
          (~31k caracteres por PDF) y lo une con separadores `--- PÁGINA N ---`, pero
          construye el OCRDocument final con `pages=[]` hardcodeado: los objetos página
          creados en el bucle se descartan (líneas 87-92 vs 96-100).
  Assembly/Mapper : no participan en la pérdida (el texto completo llega al full_text).
  Segmentation : `PipelineRunner` (pipeline/runner.py) solo itera `ocr_doc.pages`
          (líneas 190-201); con pages=[] nunca produce avisos para CO (0 avisos).
          Adicionalmente, el fallback exige el header "AVISO DE REMATE"/"REMATE JUDICIAL",
          ausente en los carteles tabulares reales.
  Continuity : no recibe avisos -> lista vacía.
  Certification Runner : sin avisos -> sin campos -> reconstrucción de UN aviso por parte
          del runner de evaluación (evaluation/production/runner.py `_run_pdf`), que
          alimenta todo el full_text como si fuera un único aviso.

Este módulo NO modifica OCR, parser, validator, knowledge ni certification.
Únicamente cambia el runner de evaluación: el texto OCR real (que ya contiene la
estructura de páginas y los marcadores de aviso "EJ ." / "DIV .") se segmenta en
avisos reales y cada aviso recorre pipeline individual contra Golden.
"""

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from backend.app.v2.evaluation.production.comparison import (
    FIELD_ALIASES,
    find_field,
    values_match,
)
from backend.app.v2.parser.ai.integration import AIEnhancedPipeline

PAGE_MARKER_RE = re.compile(r"^--- P[AÁ]GINA (\d+) ---\s*$", re.M)
AVISO_START_RE = re.compile(r"^\s*(?:EJ|DIV)\s*\.", re.M)
DIGITS_RE = re.compile(r"\d")


@dataclass
class PageRegion:
    pagina: int
    text: str
    start: int
    end: int


@dataclass
class AvisoBlock:
    pagina: int
    index: int
    start: int
    end: int
    text: str


def extract_pages(full_text: str) -> list[PageRegion]:
    """Divide el full_text real del OCR en páginas usando los separadores
    `--- PÁGINA N ---` que el propio OCR ya genera."""
    matches = list(PAGE_MARKER_RE.finditer(full_text))
    if not matches:
        if full_text.strip():
            return [PageRegion(pagina=1, text=full_text, start=0, end=len(full_text))]
        return []
    regions: list[PageRegion] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        text = full_text[start:end].strip("\n")
        if text.strip():
            regions.append(PageRegion(pagina=int(m.group(1)), text=text, start=start, end=end))
    return regions


def split_avisos(page_text: str) -> list[AvisoBlock]:
    """Divide el texto de una página en avisos usando los marcadores reales que
    inician cada aviso en los carteles de remate: `EJ .` / `DIV .`."""
    matches = list(AVISO_START_RE.finditer(page_text))
    blocks: list[AvisoBlock] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(page_text)
        text = page_text[m.start():end]
        blocks.append(AvisoBlock(pagina=0, index=i, start=m.start(), end=end, text=text))
    return blocks


def digit_positions(text: str) -> tuple[str, list[int]]:
    """Devuelve (cadena_de_digitos, posiciones_de_cada_digito_en_el_texto_original)."""
    chars: list[str] = []
    positions: list[int] = []
    for i, ch in enumerate(text):
        if ch.isdigit():
            chars.append(ch)
            positions.append(i)
    return "".join(chars), positions


def find_expediente(text: str, expediente: str) -> Optional[tuple[int, int]]:
    """Localiza el expediente (normalizado a dígitos) en el texto OCR real.
    Devuelve (start_char, end_char) o None. El OCR intercala espacios/digitos,
    por lo que la búsqueda se hace sobre el flujo de dígitos."""
    if not expediente:
        return None
    target = re.sub(r"[^\d]", "", str(expediente))
    if not target:
        return None
    stream, positions = digit_positions(text)
    idx = stream.find(target)
    if idx < 0:
        return None
    return positions[idx], positions[idx + len(target) - 1] + 1


def find_aviso_region(page_text: str, expediente: str) -> Optional[tuple[int, int]]:
    """Devuelve el rango de caracteres del aviso (bloque EJ/DIV) que contiene el
    expediente, o el rango del propio expediente si no hay bloque asociado."""
    span = find_expediente(page_text, expediente)
    if span is None:
        return None
    start, end = span
    blocks = split_avisos(page_text)
    for b in blocks:
        if b.start <= start < b.end:
            return b.start, b.end
    line_start = page_text.rfind("\n", 0, start) + 1
    line_end = page_text.find("\n", end)
    if line_end < 0:
        line_end = len(page_text)
    return line_start, line_end


def compare_aviso(predicted: dict, expected: dict, fields: list[str]) -> dict:
    """Compara un aviso individual contra su golden record.
    Devuelve per-field tp/fp/fn y precision/recall/F1 por aviso + errores."""
    per_field: dict[str, dict] = {}
    errores: list[dict] = []
    for field_name in fields:
        expected_value = expected.get(field_name)
        found = find_field(predicted, field_name)
        actual_value = found.get("value") if found else None
        actual_status = found.get("status") if found else "NOT_FOUND"

        if expected_value is None or expected_value == "":
            tp = fp = fn = 0
        elif values_match(expected_value, actual_value) and actual_status == "FOUND":
            tp, fp, fn = 1, 0, 0
        elif actual_status == "FOUND":
            tp, fp, fn = 0, 1, 0
            errores.append({
                "campo": field_name,
                "tipo": "FP",
                "esperado": str(expected_value),
                "obtenido": str(actual_value),
            })
        else:
            tp, fp, fn = 0, 0, 1
            errores.append({
                "campo": field_name,
                "tipo": "FN",
                "esperado": str(expected_value),
                "obtenido": None,
            })
        per_field[field_name] = {"tp": tp, "fp": fp, "fn": fn}

    tp = sum(v["tp"] for v in per_field.values())
    fp = sum(v["fp"] for v in per_field.values())
    fn = sum(v["fn"] for v in per_field.values())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "per_field": per_field,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "errores": errores,
    }


DEFAULT_COMPARISON_FIELDS = [
    "expediente", "demandante", "demandado", "precio_base",
    "fianza_porcentaje", "minimo_porcentaje", "fecha_remate",
]


def _cached_text(value) -> str:
    """Normaliza el valor cacheado (str con full_text o dict de real_ocr_texts.json)."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        full = value.get("full_text")
        if isinstance(full, str):
            return full
        page_map = value.get("page_map")
        if isinstance(page_map, dict):
            parts = [f"--- PÁGINA {pg} ---\n{txt}" for pg, txt in sorted(page_map.items(), key=lambda kv: int(kv[0]))]
            if parts:
                return "\n\n".join(parts)
    return ""


class AvisoRunner:
    """Runner de evaluación aviso-por-aviso (Parte 2).

    PDF
      -> OCR real (texto con separadores de página reales)
      -> N avisos (bloques anclados por expediente golden sobre la estructura real)
      -> pipeline individual por aviso (parser -> knowledge -> IA -> validator -> certification)
      -> comparación individual contra Golden (precision/recall/F1/errores por aviso)
    """

    def __init__(self, use_ai: bool = True, resolver=None, ocr_cache: Optional[dict] = None):
        self.use_ai = use_ai
        self._pipeline = AIEnhancedPipeline(resolver=resolver)
        self._ocr_cache = ocr_cache or {}

    def ocr_text(self, pdf_path: str) -> str:
        for key in (pdf_path, str(Path(pdf_path)), str(Path(pdf_path)).replace("\\", "/")):
            if key in self._ocr_cache:
                text = _cached_text(self._ocr_cache[key])
                if text:
                    return text
        name = Path(pdf_path).name
        for key, value in self._ocr_cache.items():
            if Path(str(key)).name == name:
                text = _cached_text(value)
                if text:
                    return text
        from backend.app.v2.ocr.processor import OCRProcessor

        doc = OCRProcessor().process_pdf(pdf_path)
        text = (doc.full_text or "").strip()
        self._ocr_cache[pdf_path] = text
        return text

    def locate_golden(self, pdf_path: str, country: str, golden_avisos: list[dict]) -> list[dict]:
        """Ancla cada aviso golden a su bloque real (página + segmento + texto)."""
        full_text = self.ocr_text(pdf_path)
        pages = extract_pages(full_text)
        located: list[dict] = []
        missed: list[dict] = []
        for aviso in golden_avisos:
            expediente = aviso.get("expediente") or ""
            span = find_expediente(full_text, expediente)
            if span is None:
                missed.append({"expediente": expediente, "motivo": "expediente_no_encontrado_en_ocr"})
                continue
            char_start, char_end = span
            page = next((p for p in pages if p.start <= char_start < p.end), None)
            if page is None:
                missed.append({"expediente": expediente, "motivo": "pagina_no_localizada"})
                continue
            region = find_aviso_region(page.text, expediente)
            if region is None:
                region = (char_start - page.start, char_end - page.start)
            block_start, block_end = region
            located.append({
                "expediente": expediente,
                "pagina": page.pagina,
                "segmento": f"chars:{block_start}-{block_end}",
                "text": page.text[block_start:block_end],
                "golden": aviso,
            })
        return located, missed

    def run_pdf(
        self,
        pdf_path: str,
        country: str,
        golden_avisos: Optional[list[dict]] = None,
        fields: Optional[list[str]] = None,
        document_id: str = "",
    ) -> dict:
        fields = fields or DEFAULT_COMPARISON_FIELDS
        full_text = self.ocr_text(pdf_path)
        pages = extract_pages(full_text)
        blocks_per_page = sum(len(split_avisos(p.text)) for p in pages)

        start = time.perf_counter()
        golden_avisos = golden_avisos or []
        located, missed = self.locate_golden(pdf_path, country, golden_avisos)

        avisos: list[dict] = []
        errors: list[dict] = []
        for i, item in enumerate(located):
            aviso_id = f"{Path(pdf_path).stem}_p{item['pagina']}_b{i}"
            block_text = item["text"]
            try:
                result = self._pipeline.run_text(
                    block_text,
                    country=country,
                    document_id=aviso_id,
                    source_type="aviso_block",
                    use_ai=self.use_ai,
                )
                comparison = compare_aviso(result.get("fields", {}), item["golden"], fields)
                cert = (result.get("certification", {}) or {}).get("all_avisos", [{}])
                avisos.append({
                    "aviso_id": aviso_id,
                    "expediente": item["expediente"],
                    "pagina": item["pagina"],
                    "segmento": item["segmento"],
                    "bbox": None,
                    "pipeline_result": result,
                    "comparison": comparison,
                    "certification_decision": cert[0].get("decision") if cert else "unknown",
                })
            except Exception as e:
                errors.append({"aviso_id": aviso_id, "expediente": item["expediente"], "error": str(e)})

        elapsed_ms = (time.perf_counter() - start) * 1000
        total_tp = sum(a["comparison"]["tp"] for a in avisos)
        total_fp = sum(a["comparison"]["fp"] for a in avisos)
        total_fn = sum(a["comparison"]["fn"] for a in avisos)
        p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
        r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0

        return {
            "documento": pdf_path,
            "document_id": document_id or Path(pdf_path).stem,
            "country": country,
            "pages_reales": len(pages),
            "bloques_reales_detectados": blocks_per_page,
            "golden_avisos": len(golden_avisos),
            "avisos_anclados": len(located),
            "avisos_procesados": len(avisos),
            "avisos_no_localizados": missed,
            "errores": errors,
            "avisos": avisos,
            "tiempo_ms": round(elapsed_ms, 2),
            "metrics": {
                "tp": total_tp,
                "fp": total_fp,
                "fn": total_fn,
                "precision": round(p, 4),
                "recall": round(r, 4),
                "f1": round(f1, 4),
            },
            "comparison_fields": fields,
        }

    def run_directory(self, pdf_paths: list[str], country: str, golden_by_pdf: dict, document_id_prefix: str = "") -> dict:
        results = []
        for pdf in pdf_paths:
            r = self.run_pdf(
                pdf,
                country,
                golden_avisos=golden_by_pdf.get(pdf, []),
                document_id=document_id_prefix + Path(pdf).stem,
            )
            results.append(r)
        return {
            "runner": "aviso_por_aviso",
            "country": country,
            "pdfs": pdf_paths,
            "results": results,
        }


def avisos_to_json(run: dict) -> str:
    return json.dumps(run, ensure_ascii=False, indent=1, default=str)
