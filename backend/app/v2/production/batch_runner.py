"""FASE 10 — Batch Runner.

Processes complete directories (images and PDFs) or batches of
text documents, returning individual results, batch summary,
errors and metrics.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from backend.app.v2.production.config import ProductionConfig, get_default
from backend.app.v2.production.logging import StructuredLogger
from backend.app.v2.production.smoke import run_text_pipeline

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
PDF_EXTENSIONS = {".pdf"}
TEXT_EXTENSIONS = {".txt", ".text"}


class BatchRunner:
    def __init__(self, config: Optional[ProductionConfig] = None,
                 logger: Optional[StructuredLogger] = None):
        self.config = config or get_default()
        self.logger = logger or StructuredLogger(log_path=self.config.log_file_path())

    def run_directory(self, input_dir: str, country: str,
                      extensions: Optional[set[str]] = None) -> dict:
        path = Path(input_dir)
        if not path.exists() or not path.is_dir():
            return self._summary([], [f"Directory not found: {input_dir}"], country)

        allowed = extensions or (IMAGE_EXTENSIONS | PDF_EXTENSIONS | TEXT_EXTENSIONS)
        files = sorted(
            f for f in path.rglob("*")
            if f.is_file() and f.suffix.lower() in allowed
        )
        if not files:
            return self._summary([], [f"No supported files in: {input_dir}"], country)

        results = []
        errors = []
        for file_path in files:
            result, error = self._process_file(file_path, country)
            if result is not None:
                results.append(result)
            if error:
                errors.append(error)
        return self._summary(results, errors, country)

    def run_text_batch(self, documents: list[dict], country: str = "CO") -> dict:
        results = []
        errors = []
        for doc in documents:
            text = doc.get("text", "")
            if not text:
                errors.append({"document_id": doc.get("id", "unknown"), "error": "empty text"})
                continue
            try:
                result = run_text_pipeline(
                    text,
                    country=country,
                    document_id=doc.get("id", ""),
                    source_type=doc.get("source_type", "text"),
                )
                results.append(result)
                self.logger.log_from_result(result)
            except Exception as e:
                errors.append({"document_id": doc.get("id", "unknown"), "error": str(e)})
        return self._summary(results, errors, country)

    def _process_file(self, file_path: Path, country: str):
        suffix = file_path.suffix.lower()
        try:
            if suffix in TEXT_EXTENSIONS:
                text = file_path.read_text(encoding="utf-8", errors="replace")
                result = run_text_pipeline(
                    text,
                    country=country,
                    document_id=file_path.stem,
                    source_type="text",
                )
            else:
                from backend.app.v2.pipeline.runner import PipelineRunner
                runner = PipelineRunner()
                result = runner.process(
                    [str(file_path)],
                    country,
                    document_id=file_path.stem,
                    source_type=suffix.lstrip("."),
                )
            self.logger.log_from_result(result)
            return result, None
        except Exception as e:
            return None, {"document_id": file_path.stem, "file": str(file_path), "error": str(e)}

    def _summary(self, results: list[dict], errors: list, country: str) -> dict:
        from backend.app.v2.production.metrics import collect_metrics
        total = len(results)
        failed = sum(1 for r in results if r.get("errors"))
        return {
            "batch_id": datetime.utcnow().strftime("%Y%m%dT%H%M%S"),
            "country": country,
            "timestamp": datetime.utcnow().isoformat(),
            "results": results,
            "summary": {
                "total_documents": total,
                "successful": total - failed,
                "failed": failed,
                "avisos_detected": sum(
                    int(r.get("stages", {}).get("segmentation", {}).get("metrics", {}).get("avisos_detected", 0))
                    for r in results
                ),
                "total_time_ms": round(sum(r.get("total_time_ms", 0.0) for r in results), 2),
            },
            "errors": errors,
            "metrics": collect_metrics(results),
        }

    def export_results(self, batch: dict, output_path: str) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(batch, f, indent=2, ensure_ascii=False, default=str)


def run_batch_directory(input_dir: str, country: str,
                        extensions: Optional[set[str]] = None) -> dict:
    return BatchRunner().run_directory(input_dir, country, extensions)
