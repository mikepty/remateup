"""FASE 11 — Production dataset runner (Parte 9).

Processes real documents:

    TXT  -> full pipeline via AIEnhancedPipeline.run_text
    JPG / PNG / PDF -> full pipeline via PipelineRunner + AI enrichment

Processes complete directories and produces per-document results, batch
summary, errors and metrics.
"""

import os
import time
from pathlib import Path
from typing import Any, Optional

from backend.app.v2.parser.ai.integration import AIEnhancedPipeline
from backend.app.v2.parser.ai.providers import AIResolverRegistry

TEXT_EXTENSIONS = {".txt"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
PDF_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | IMAGE_EXTENSIONS | PDF_EXTENSIONS

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
SAMPLES_DIR = BASE_DIR / "samples"


class ProductionDatasetRunner:
    def __init__(self, use_ai: bool = True, resolver=None):
        self.use_ai = use_ai
        self._resolver = resolver
        self._pipeline = AIEnhancedPipeline(resolver=resolver)
        self._registry = AIResolverRegistry()

    @property
    def resolver_provider(self) -> str:
        resolver = self._resolver or self._registry.create_default()
        return resolver.provider_name()

    def run_text(self, text: str, country: str, document_id: str = "", source_type: str = "text") -> dict:
        return self._pipeline.run_text(
            text,
            country=country,
            document_id=document_id,
            source_type=source_type,
            use_ai=self.use_ai,
        )

    def run_file(self, path: str, country: str, document_id: str = "") -> dict:
        file_path = Path(path)
        suffix = file_path.suffix.lower()
        if suffix in TEXT_EXTENSIONS:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            return self.run_text(text, country, document_id=document_id or file_path.stem, source_type="txt")
        if suffix in IMAGE_EXTENSIONS | PDF_EXTENSIONS:
            if suffix in PDF_EXTENSIONS:
                return self._run_pdf(path, country, document_id)
            return self._run_image(path, country, document_id)
        raise ValueError(f"Unsupported file type: {suffix}")

    def _run_pdf(self, path: str, country: str, document_id: str) -> dict:
        """Real OCR over the PDF; the OCR text drives the full downstream
        pipeline (Parser -> Knowledge -> AIResolver -> Validator -> Certification)."""
        from backend.app.v2.ocr.processor import OCRProcessor

        ocr_doc = OCRProcessor().process_pdf(path)
        text = (ocr_doc.full_text or "").strip()
        if not text:
            result = self._pipeline.run_files([path], country, document_id=document_id,
                                              source_type="pdf", use_ai=self.use_ai)
            result["errors"].append("OCR produced no text for PDF")
            return result
        result = self.run_text(text, country, document_id=document_id, source_type="ocr_pdf")
        result["files"] = [path]
        result["ocr"] = {"real": True, "text_length": len(text)}
        return result

    def _run_image(self, path: str, country: str, document_id: str) -> dict:
        """Full PipelineRunner over the image; falls back to the OCR-text
        flow when segmentation detects no avisos."""
        result = self._pipeline.run_files(
            [path], country, document_id=document_id, source_type="image", use_ai=self.use_ai
        )
        avisos_detected = (
            result.get("stages", {})
            .get("segmentation", {})
            .get("metrics", {})
            .get("avisos_detected", 0)
        )
        if avisos_detected > 0:
            return result
        from backend.app.v2.ocr.processor import OCRProcessor

        ocr_doc = OCRProcessor().process_image(path)
        text = (ocr_doc.full_text or "").strip()
        if not text:
            result["errors"].append("OCR produced no text for image")
            return result
        fallback = self.run_text(text, country, document_id=document_id, source_type="ocr_image")
        fallback["files"] = [path]
        fallback["ocr"] = {"real": True, "text_length": len(text), "pipeline_fallback": True}
        return fallback

    def run_directory(
        self,
        directory: str,
        country: str,
        extensions: Optional[set[str]] = None,
        max_files: Optional[int] = None,
    ) -> dict:
        exts = extensions or SUPPORTED_EXTENSIONS
        files = sorted(
            p for p in Path(directory).iterdir()
            if p.is_file() and p.suffix.lower() in exts
        )
        if max_files:
            files = files[:max_files]

        results: list[dict] = []
        errors: list[dict] = []
        total_ai_ms = 0.0
        start = time.perf_counter()

        for f in files:
            doc_id = f.stem
            try:
                r = self.run_file(str(f), country, document_id=doc_id)
                results.append(r)
                ai = r.get("ai", {})
                total_ai_ms += ai.get("ai_time_ms", 0.0) if isinstance(ai, dict) else 0.0
            except Exception as e:
                errors.append({"file": str(f), "error": str(e)})

        elapsed = (time.perf_counter() - start) * 1000

        return {
            "directory": str(directory),
            "country": country,
            "files": [str(f) for f in files],
            "total_files": len(files),
            "processed": len(results),
            "failed": len(errors),
            "errors": errors,
            "results": results,
            "elapsed_ms": round(elapsed, 2),
            "ai_time_ms": round(total_ai_ms, 2),
            "provider": self.resolver_provider,
            "use_ai": self.use_ai,
        }

    def summary(self, run: dict) -> dict:
        results = run.get("results", [])
        campos_por_documento: list[dict] = []
        campos_ia = 0
        campos_deterministas = 0
        avisos_encontrados = 0
        avisos_validos = 0
        descartados = 0
        duplicados = 0
        cache_hits = 0
        cache_misses = 0
        cost_usd = 0.0
        tiempo_total_ms = 0.0
        tiempo_ia_ms = 0.0

        for r in results:
            fields = r.get("fields", {})
            campos_por_documento.append({
                "document_id": r.get("document_id", ""),
                "campos": sorted(fields.keys()),
                "cantidad": len(fields),
            })
            ai = r.get("ai", {}) or {}
            campos_ia += ai.get("ai_fields_count", 0)
            campos_deterministas += ai.get("deterministic_fields_count", len(fields))
            cache_hits += ai.get("cache_hits", 0)
            cache_misses += ai.get("cache_misses", 0)
            cost_usd += ai.get("cost_usd", 0.0)
            tiempo_total_ms += r.get("total_time_ms", 0.0)
            tiempo_ia_ms += ai.get("ai_time_ms", 0.0)

            avisos_encontrados += (
                r.get("stages", {})
                .get("segmentation", {})
                .get("metrics", {})
                .get("avisos_detected", 1 if r.get("source_type") == "txt" else 0)
            )
            decision = (r.get("certification", {}) or {}).get("all_avisos", [{}])[0].get("decision", "") if r.get("certification") else ""
            if decision == "VALID":
                avisos_validos += 1
            elif decision in ("INVALID", "INCOMPLETE", "INCONSISTENT", "DUPLICATED", "LIKELY_DUPLICATED"):
                descartados += 1
            dup = (r.get("validation", {}) or {}).get("duplicate_info", {}) or {}
            if dup.get("level") in ("DUPLICATED", "LIKELY_DUPLICATED"):
                duplicados += 1

        n = max(len(results), 1)
        return {
            "documentos": len(results),
            "avisos_encontrados": avisos_encontrados,
            "avisos_validos": avisos_validos,
            "descartados": descartados,
            "duplicados": duplicados,
            "campos_por_documento": campos_por_documento,
            "campos_ia": campos_ia,
            "campos_deterministas": campos_deterministas,
            "tiempo_promedio_ms": round(tiempo_total_ms / n, 2),
            "tiempo_ia_ms": round(tiempo_ia_ms, 2),
            "costo_estimado_usd": round(cost_usd, 6),
            "cache_hit": cache_hits,
            "cache_miss": cache_misses,
            "provider": self.resolver_provider,
        }
