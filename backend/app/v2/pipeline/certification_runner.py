"""FASE 6.8 — Certification Runner: end-to-end V2 pipeline with timing, auditing, and metrics.

Chains: Assembly → OCR → Stitching → Layout → Continuity → Parser → Knowledge → Validation → Result
Stub stages (normalization, confidence) are pass-through with timing measurement only."""

import json
import os
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from dotenv import load_dotenv

from backend.app.v2.document.assembly import DocumentAssembly
from backend.app.v2.document.stitching import PageStitcher
from backend.app.v2.ocr.processor import OCRProcessor
from backend.app.v2.parser.factory import ParserFactory
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.knowledge.rules import RuleEngine
from backend.app.v2.knowledge.repository import KnowledgeRepository
from backend.app.v2.knowledge.integration import KnowledgeAwareWrapper
from backend.app.v2.evidence.service import EvidenceService
from backend.app.v2.segmenter.newspaper_layout import NewspaperLayout
from backend.app.v2.segmenter.continuity import ContinuityEngine
from backend.app.v2.validator.orchestrator import ValidationOrchestrator


def _ocr_page_to_text(page) -> str:
    if hasattr(page, "full_text"):
        return page.full_text
    txt = getattr(page, "text", "")
    if not txt and hasattr(page, "blocks"):
        txt = " ".join(b.text for b in page.blocks if hasattr(b, "text"))
    return txt


class CertificationRunner:
    def __init__(self):
        for parent in reversed(Path(__file__).resolve().parents):
            env_candidate = parent / ".env"
            if env_candidate.exists():
                load_dotenv(dotenv_path=str(env_candidate))
                break
        self._assembly = DocumentAssembly()
        self._ocr = OCRProcessor()
        self._stitcher = PageStitcher()
        self._layout = NewspaperLayout()
        self._continuity = ContinuityEngine()
        self._parser_factory = ParserFactory()
        self._knowledge_repo = KnowledgeRepository()
        self._rule_engine = RuleEngine(repository=self._knowledge_repo)
        self._evidence = EvidenceService()
        self._validator = ValidationOrchestrator()
        self._timings: dict[str, float] = {}
        self._stage_results: dict[str, Any] = {}
        self._errors: list[dict] = []

    def _time_stage(self, name: str, fn, *args, **kwargs) -> Any:
        start = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
            self._timings[name] = round((time.perf_counter() - start) * 1000, 2)
            return result
        except Exception as e:
            elapsed = time.perf_counter() - start
            self._timings[name] = round(elapsed * 1000, 2)
            self._errors.append({"stage": name, "error": str(e)})
            raise

    def process(self, file_paths: list[str], country: str,
                document_id: str = "") -> dict:
        self._timings = {}
        self._stage_results = {}
        self._errors = []
        result: dict[str, Any] = {
            "document_id": document_id or os.path.basename(file_paths[0]) if file_paths else "unknown",
            "country": country,
            "files": file_paths,
            "stages": {},
            "fields": {},
            "timings_ms": {},
            "total_time_ms": 0,
            "errors": [],
        }

        try:
            # 1. Assembly
            source_doc = self._time_stage(
                "assembly", self._assembly.assemble, file_paths, country
            )
            self._stage_results["assembly"] = source_doc
            result["stages"]["assembly"] = {
                "pages": len(source_doc.pages),
                "type": source_doc.source_type.value if hasattr(source_doc.source_type, "value") else str(source_doc.source_type),
            }

            # 2. OCR
            ocr_docs = {}
            for i, page in enumerate(source_doc.pages):
                for frag in page.fragments:
                    path = frag.path
                    if path not in ocr_docs:
                        if path.lower().endswith(".pdf"):
                            ocr_doc = self._time_stage(
                                f"ocr_page_{i}", self._ocr.process_pdf, path
                            )
                        else:
                            ocr_doc = self._time_stage(
                                f"ocr_page_{i}", self._ocr.process_image, path
                            )
                        ocr_docs[path] = ocr_doc
            self._stage_results["ocr"] = ocr_docs
            ocr_pages_list = list(ocr_docs.values())
            total_ocr_pages = sum(len(d.pages) for d in ocr_docs.values() if hasattr(d, "pages"))
            result["stages"]["ocr"] = {
                "files_processed": len(ocr_docs),
                "total_pages": total_ocr_pages,
            }

            # 3. Stitching (Panama only)
            stitched_pages = None
            # Flatten OCRDocuments into individual OCRPages for stitcher
            all_ocr_pages: list = []
            for ocr_doc in ocr_pages_list:
                if hasattr(ocr_doc, "pages"):
                    all_ocr_pages.extend(ocr_doc.pages)
                else:
                    from backend.app.v2.ocr.models import OCRPage as _OCRPage
                    if isinstance(ocr_doc, _OCRPage):
                        all_ocr_pages.append(ocr_doc)

            if country.upper() == "PA" and len(all_ocr_pages) > 0:
                try:
                    page_count = len(all_ocr_pages) // 2 + len(all_ocr_pages) % 2
                    stitched_pages = self._time_stage(
                        "stitching", self._stitcher.stitch_ocr_pages, all_ocr_pages, page_count
                    )
                    self._stage_results["stitching"] = stitched_pages
                    result["stages"]["stitching"] = {
                        "stitched_pages": len(stitched_pages),
                    }
                except Exception:
                    stitched_pages = None
                    result["stages"]["stitching"] = {"stitched_pages": 0, "skipped": True}

            # 4. Layout Detection + Notice Detection
            avisos_list = []
            if stitched_pages:
                for sp in stitched_pages:
                    detected_avisos = self._time_stage(
                        "layout", self._layout.segment, sp
                    )
                    avisos_list.extend(detected_avisos if isinstance(detected_avisos, list) else [])
            else:
                for ocr_doc in ocr_pages_list:
                    for page_idx, page in enumerate(ocr_doc.pages):
                        text = _ocr_page_to_text(page)
                        if "AVISO DE REMATE" in text.upper() or "REMATE JUDICIAL" in text.upper():
                            from backend.app.v2.segmenter.models import DetectedAviso, DetectedSection
                            from backend.app.v2.document.models import SectionType
                            aviso = DetectedAviso(
                                header_text="AVISO DE REMATE",
                                sections=[DetectedSection(section_type=SectionType.AVISO_COMPLETO, text=text)],
                                confidence=0.8,
                            )
                            avisos_list.append(aviso)
            self._stage_results["layout"] = avisos_list
            result["stages"]["layout"] = {"avisos_detected": len(avisos_list)}

            # 5. Continuity
            complete_avisos = []
            has_fragments = any(
                hasattr(a, "position") for a in avisos_list
            )
            if has_fragments and len(avisos_list) > 1:
                try:
                    complete_avisos = self._time_stage(
                        "continuity", self._continuity.detect_continuity, avisos_list
                    )
                except Exception:
                    complete_avisos = avisos_list
            else:
                complete_avisos = avisos_list
            self._stage_results["continuity"] = complete_avisos
            result["stages"]["continuity"] = {"avisos_after_merge": len(complete_avisos)}

            # 6. Parsing
            parser = self._parser_factory.get_parser(country.upper(), "REMATE")
            wrapper = KnowledgeAwareWrapper(
                parser, rule_engine=self._rule_engine,
                repository=self._knowledge_repo,
            )
            all_fields = {}
            for aviso in complete_avisos:
                text = aviso.full_text if hasattr(aviso, "full_text") else str(aviso)
                ctx = ParserContext(
                    country=country.upper(), document_type="REMATE",
                    text=text,
                )
                parse_results = self._time_stage(
                    "parsing", wrapper.parse, ctx
                )
                for fname, pr in parse_results.items():
                    if pr.is_found and fname not in all_fields:
                        all_fields[fname] = {
                            "value": pr.value,
                            "confidence": pr.confidence,
                            "status": pr.status,
                            "evidence": pr.evidence,
                        }
            self._stage_results["parsing"] = all_fields
            result["stages"]["parsing"] = {
                "fields_found": len(all_fields),
                "fields": list(all_fields.keys()),
            }
            result["fields"] = all_fields

            # 7. Normalization (pass-through — stub)
            norm_start = time.perf_counter()
            normalized = dict(all_fields)
            self._timings["normalization"] = round((time.perf_counter() - norm_start) * 1000, 2)
            result["stages"]["normalization"] = {"status": "pass_through"}

            # 8. Knowledge Application
            knowledge_start = time.perf_counter()
            for fname, field_data in list(normalized.items()):
                rule_result = self._rule_engine.apply_rules(
                    field=fname,
                    text=" ".join(
                        a.full_text if hasattr(a, "full_text") else str(a)
                        for a in complete_avisos
                    ),
                )
                if rule_result and rule_result.is_found:
                    normalized[fname] = {
                        "value": rule_result.value,
                        "confidence": rule_result.confidence,
                        "status": "FOUND",
                        "evidence": rule_result.evidence,
                        "source": "knowledge",
                    }
            self._timings["knowledge"] = round((time.perf_counter() - knowledge_start) * 1000, 2)
            self._stage_results["knowledge"] = normalized
            result["stages"]["knowledge"] = {
                "rules_applied": len([v for v in normalized.values() if v.get("source") == "knowledge"]),
            }
            result["fields"] = normalized

            # 9. Validation (FASE 6.9 NoticeValidator)
            val_start = time.perf_counter()
            aviso_text = " ".join(
                a.full_text if hasattr(a, "full_text") else str(a)
                for a in complete_avisos
            )
            v_result = self._validator.validate_notice(
                aviso_id=result.get("document_id", ""),
                text=aviso_text,
                fields_found=normalized,
            )
            self._timings["validation"] = round((time.perf_counter() - val_start) * 1000, 2)
            result["stages"]["validation"] = {
                "decision": v_result.decision.value,
                "score": v_result.score,
                "header_valid": v_result.header_valid,
                "structural_valid": v_result.structural_valid,
                "fields_found": v_result.fields_found,
                "fields_missing": v_result.fields_missing,
                "inconsistencies": [i.to_dict() for i in v_result.inconsistencies],
                "duplicate_info": v_result.duplicate_info.to_dict() if v_result.duplicate_info else None,
                "rules_applied": len(v_result.rules_applied),
                "rules_failed": len(v_result.rules_failed),
            }
            result["validation"] = v_result.to_dict()

            # 10. Confidence (composite)
            conf_start = time.perf_counter()
            ocr_conf = 0.0
            ocr_count = 0
            for ocr_doc in ocr_pages_list:
                for page in getattr(ocr_doc, "pages", []):
                    for word in getattr(page, "words", []):
                        c = getattr(word, "confidence", 0) or 0
                        ocr_conf += c
                        ocr_count += 1
            avg_ocr_conf = round(ocr_conf / max(ocr_count, 1), 4)

            field_confidences = {}
            for fname, fdata in normalized.items():
                field_confidences[fname] = fdata.get("confidence", 0)

            field_conf_values = [v for v in field_confidences.values() if v > 0]
            avg_field_conf = round(
                sum(field_conf_values) / max(len(field_conf_values), 1), 4
            ) if field_conf_values else 0.0

            final_conf = round(avg_ocr_conf * 0.2 + avg_field_conf * 0.8, 4)
            self._timings["confidence"] = round((time.perf_counter() - conf_start) * 1000, 2)
            result["stages"]["confidence"] = {
                "ocr_avg": avg_ocr_conf,
                "field_avg": avg_field_conf,
                "final": final_conf,
            }
            result["confidence"] = final_conf

        except Exception as e:
            self._errors.append({"stage": "pipeline", "error": str(e)})
            result["errors"] = self._errors

        result["timings_ms"] = dict(self._timings)
        result["total_time_ms"] = round(sum(self._timings.values()), 2)
        result["errors"] = self._errors
        result["timestamp"] = datetime.utcnow().isoformat()
        return result

    def process_batch(self, documents: list[dict]) -> list[dict]:
        results = []
        for doc in documents:
            r = self.process(
                doc.get("files", []),
                doc.get("country", "PA"),
                document_id=doc.get("id", ""),
            )
            results.append(r)
        return results

    def summarize_batch(self, results: list[dict]) -> dict:
        total = len(results)
        fields_counter: Counter = Counter()
        errors_by_stage: Counter = Counter()
        confidences: list[float] = []
        total_times: list[float] = []
        per_stage_times: dict[str, list[float]] = {}

        for r in results:
            for fname in r.get("fields", {}):
                fields_counter[fname] += 1
            for e in r.get("errors", []):
                errors_by_stage[e.get("stage", "unknown")] += 1
            c = r.get("confidence", 0)
            if c:
                confidences.append(c)
            total_times.append(r.get("total_time_ms", 0))
            for stage, t in r.get("timings_ms", {}).items():
                per_stage_times.setdefault(stage, []).append(t)

        return {
            "total_documents": total,
            "fields_found": dict(fields_counter.most_common()),
            "fields_count": len(fields_counter),
            "errors": dict(errors_by_stage),
            "avg_confidence": round(sum(confidences) / max(len(confidences), 1), 4) if confidences else 0,
            "avg_total_time_ms": round(sum(total_times) / max(len(total_times), 1), 2) if total_times else 0,
                "avg_stage_times_ms": {
                    stage: round(sum(times) / len(times), 2)
                    for stage, times in per_stage_times.items()
                },
            "total_errors": sum(errors_by_stage.values()),
        }
