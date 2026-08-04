"""FASE 7 — PipelineRunner: end-to-end production pipeline.

Pipeline order:
  Assembly → OCR → Mapping → Segmentation → Stitching → Newspaper Layout →
  Continuity → Parser → Knowledge → Validator → Normalizer → Confidence → Certification → Final JSON
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

from backend.app.v2.document.assembly import DocumentAssembly
from backend.app.v2.ocr.processor import OCRProcessor
from backend.app.v2.segmenter.newspaper_layout import NewspaperLayout
from backend.app.v2.segmenter.continuity import ContinuityEngine
from backend.app.v2.parser.factory import ParserFactory
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.knowledge.rules import RuleEngine
from backend.app.v2.knowledge.repository import KnowledgeRepository
from backend.app.v2.knowledge.integration import KnowledgeAwareWrapper
from backend.app.v2.validator.orchestrator import ValidationOrchestrator
from backend.app.v2.validator.models import Decision
from backend.app.v2.normalization.normalizer import FieldNormalizer
from backend.app.v2.confidence.final import FinalConfidenceCalculator
from backend.app.v2.certification.certifier import Certifier, CertDecision
from backend.app.v2.description.builder import build_descripcion_completa, build_descripcion_portada


PIPELINE_VERSION = "7.0.0"


def _ocr_page_to_text(page) -> str:
    if hasattr(page, "full_text"):
        return page.full_text
    txt = getattr(page, "text", "")
    if not txt and hasattr(page, "blocks"):
        txt = " ".join(b.text for b in page.blocks if hasattr(b, "text"))
    return txt


def _aviso_text(aviso) -> str:
    """Texto real de un aviso, sea DetectedAviso (expone full_text) o
    CompleteAviso (expone text, ver segmenter/models.py). Antes se hacía
    aviso.full_text if hasattr(...) else str(aviso): como CompleteAviso no
    tiene full_text, TODO aviso que pasó por el motor de continuidad (es
    decir, todos en Panamá) caía en str(aviso) y le pasaba el repr del
    dataclass entero -- no el texto -- al parser, knowledge y validator."""
    if hasattr(aviso, "full_text"):
        return aviso.full_text
    txt = getattr(aviso, "text", None)
    if txt is not None:
        return txt
    return str(aviso)


class StageResult:
    def __init__(self, name: str):
        self.name = name
        self.status = "pending"
        self.duration_ms = 0.0
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.metrics: dict = {}
        self.output: Any = None
        self.per_aviso_fields: list = []

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "duration_ms": round(self.duration_ms, 2),
            "warnings": self.warnings,
            "errors": self.errors,
            "metrics": self.metrics,
        }


class PipelineRunner:
    def __init__(self):
        for parent in reversed(Path(__file__).resolve().parents):
            env_candidate = parent / ".env"
            if env_candidate.exists():
                load_dotenv(dotenv_path=str(env_candidate))
                break

        self._assembly = DocumentAssembly()
        self._ocr = OCRProcessor()
        self._layout = NewspaperLayout()
        self._continuity = ContinuityEngine()
        self._parser_factory = ParserFactory()
        self._knowledge_repo = KnowledgeRepository()
        self._rule_engine = RuleEngine(repository=self._knowledge_repo)
        self._validator = ValidationOrchestrator()
        self._normalizer = FieldNormalizer()
        self._confidence = FinalConfidenceCalculator()
        self._certifier = Certifier()

    def process(
        self,
        file_paths: list[str],
        country: str,
        document_id: str = "",
        source_type: str = "",
    ) -> dict:
        stages: dict[str, StageResult] = {}
        result: dict[str, Any] = {
            "document_id": document_id or (os.path.basename(file_paths[0]) if file_paths else "unknown"),
            "country": country,
            "source_type": source_type,
            "files": file_paths,
            "stages": {},
            "fields": {},
            "validation": {},
            "normalization": {},
            "confidence": {},
            "certification": {},
            "final_json": {},
            "total_time_ms": 0,
            "errors": [],
            "warnings": [],
            "metrics": {},
            "version": PIPELINE_VERSION,
            "timestamp": datetime.utcnow().isoformat(),
        }

        overall_start = time.perf_counter()

        # 1. Assembly
        s = self._run_stage("assembly", stages, lambda: self._assembly.assemble(file_paths, country))
        source_doc = s.output
        if s.status == "error":
            return self._finalize(result, stages, overall_start)
        result["stages"]["assembly"] = s.to_dict()
        result["stages"]["assembly"]["pages"] = len(source_doc.pages) if hasattr(source_doc, "pages") else 0

        # 2. OCR
        s = StageResult("ocr")
        s.status = "running"
        start = time.perf_counter()
        try:
            ocr_docs = {}
            for i, page in enumerate(source_doc.pages):
                for frag in page.fragments:
                    path = frag.path
                    if path not in ocr_docs:
                        if path.lower().endswith(".pdf"):
                            ocr_doc = self._ocr.process_pdf(path)
                        else:
                            ocr_doc = self._ocr.process_image(path)
                        ocr_docs[path] = ocr_doc
            s.output = ocr_docs
            s.status = "success"
            s.metrics = {"files_processed": len(ocr_docs)}
        except Exception as e:
            s.status = "error"
            s.errors.append(str(e))
        s.duration_ms = (time.perf_counter() - start) * 1000
        stages["ocr"] = s
        result["stages"]["ocr"] = s.to_dict()
        if s.status == "error":
            return self._finalize(result, stages, overall_start)

        # 3. Mapping (performed during OCR via OCRMapper)
        s = StageResult("mapping")
        s.status = "success"
        s.duration_ms = 0.1
        s.metrics = {"method": "embedded_in_ocr", "status": "mapped"}
        stages["mapping"] = s
        result["stages"]["mapping"] = s.to_dict()

        # 4. Segmentation + 5. Stitching + 6. Newspaper Layout
        s = StageResult("segmentation")
        s.status = "running"
        start = time.perf_counter()
        try:
            ocr_docs = stages["ocr"].output
            ocr_pages_list = list(ocr_docs.values()) if isinstance(ocr_docs, dict) else []
            all_ocr_pages = []
            for ocr_doc in ocr_pages_list:
                if hasattr(ocr_doc, "pages"):
                    all_ocr_pages.extend(ocr_doc.pages)

            stitched_pages = None
            page_count = len(all_ocr_pages) // 2 + len(all_ocr_pages) % 2
            if country.upper() == "PA" and len(all_ocr_pages) > 0:
                try:
                    stitched_pages = self._layout.stitch_ocr_pages(all_ocr_pages, page_count) if hasattr(self._layout, "stitch_ocr_pages") else None
                    if stitched_pages is None:
                        from backend.app.v2.document.stitching import PageStitcher
                        stitcher = PageStitcher()
                        stitched_pages = stitcher.stitch_ocr_pages(all_ocr_pages, page_count)
                except Exception as e:
                    s.warnings.append(f"Stitching failed: {e}")
                    stitched_pages = None

            # Problema #7 (OCR parcial): si a alguna página le falta la mitad
            # superior o inferior (imagen impar, sin pareja), no se debe
            # tratar como una página completa. Se marca como warning aquí y
            # se fuerza REQUIRES_REVIEW/INCOMPLETE más adelante (etapa
            # validator) en vez de dejar que se certifique como si nada.
            partial_pages = [sp for sp in (stitched_pages or []) if getattr(sp, "is_partial", False)]
            if partial_pages:
                for sp in partial_pages:
                    s.warnings.append(
                        f"Página {sp.page_number} incompleta: falta la mitad "
                        f"{sp.missing_side} (imagen sin pareja). Se marca para revisión."
                    )
                result["metrics"]["ocr_parcial_detectado"] = True

            avisos_list = []
            if stitched_pages:
                for sp in stitched_pages:
                    detected = self._layout.segment(sp)
                    if isinstance(detected, list):
                        avisos_list.extend(detected)
                    elif hasattr(detected, "avisos"):
                        avisos_list.extend(detected.avisos)
            else:
                for ocr_doc in ocr_pages_list:
                    for page in getattr(ocr_doc, "pages", []):
                        text = _ocr_page_to_text(page)
                        if "AVISO DE REMATE" in text.upper() or "REMATE JUDICIAL" in text.upper():
                            from backend.app.v2.segmenter.models import DetectedAviso, DetectedSection
                            from backend.app.v2.document.models import SectionType
                            avisos_list.append(DetectedAviso(
                                header_text="AVISO DE REMATE",
                                sections=[DetectedSection(section_type=SectionType.AVISO_COMPLETO, text=text)],
                                confidence=0.8,
                            ))
            s.output = avisos_list
            s.status = "success"
            s.metrics = {"avisos_detected": len(avisos_list)}
        except Exception as e:
            s.status = "error"
            s.errors.append(str(e))
        s.duration_ms = (time.perf_counter() - start) * 1000
        stages["segmentation"] = s
        result["stages"]["segmentation"] = s.to_dict()
        if s.status == "error":
            return self._finalize(result, stages, overall_start)

        # 7. Continuity
        s = StageResult("continuity")
        s.status = "running"
        start = time.perf_counter()
        try:
            avisos_list = stages["segmentation"].output
            if avisos_list and any(hasattr(a, "position") for a in avisos_list):
                complete_avisos = self._continuity.detect_continuity(avisos_list)
            else:
                complete_avisos = avisos_list
            s.output = complete_avisos
            s.status = "success"
            s.metrics = {"avisos_after_merge": len(complete_avisos)}
        except Exception as e:
            s.status = "error"
            s.errors.append(str(e))
            s.output = stages["segmentation"].output
        s.duration_ms = (time.perf_counter() - start) * 1000
        stages["continuity"] = s
        result["stages"]["continuity"] = s.to_dict()

        # 8. Parser
        s = StageResult("parser")
        s.status = "running"
        start = time.perf_counter()
        try:
            parser = self._parser_factory.get_parser(country.upper(), "REMATE")
            wrapper = KnowledgeAwareWrapper(parser, rule_engine=self._rule_engine, repository=self._knowledge_repo)
            all_fields = {}
            # per_aviso_fields: lista con los campos de CADA aviso por
            # separado (problema #5, campos mezclados). all_fields se deja
            # intacto (mismo comportamiento de antes, primer valor
            # encontrado gana) para no romper a quien ya lo consume; esto
            # es aditivo, no un reemplazo.
            per_aviso_fields: list[dict] = []
            continuity_output = stages["continuity"].output if stages["continuity"].status == "success" else []
            for aviso in continuity_output or []:
                text = _aviso_text(aviso)
                ctx = ParserContext(country=country.upper(), document_type="REMATE", text=text)
                parse_results = wrapper.parse(ctx)
                single_aviso_fields = {}
                for fname, pr in parse_results.items():
                    if pr.is_found:
                        entry = {
                            "value": pr.value,
                            "confidence": pr.confidence,
                            "status": pr.status,
                            "evidence": pr.evidence,
                            "source": "parser",
                        }
                        single_aviso_fields[fname] = entry
                        if fname not in all_fields:
                            all_fields[fname] = entry
                if text.strip():
                    if country.upper() == "PA":
                        entry = {
                            "value": build_descripcion_completa(text),
                            "confidence": 1.0,
                            "status": "FOUND",
                            "evidence": "",
                            "source": "description_builder",
                        }
                        single_aviso_fields["descripcion_completa"] = entry
                        if "descripcion_completa" not in all_fields:
                            all_fields["descripcion_completa"] = entry
                    entry = {
                        "value": build_descripcion_portada(text),
                        "confidence": 1.0,
                        "status": "FOUND",
                        "evidence": "",
                        "source": "description_builder",
                    }
                    single_aviso_fields["descripcion"] = entry
                    if "descripcion" not in all_fields:
                        all_fields["descripcion"] = entry
                per_aviso_fields.append(single_aviso_fields)
            s.output = all_fields
            s.per_aviso_fields = per_aviso_fields
            s.per_aviso_texts = [
                _aviso_text(a)
                for a in (stages["continuity"].output or [])
            ]
            s.status = "success"
            s.metrics = {"fields_found": len(all_fields), "avisos_processed": len(per_aviso_fields)}
        except Exception as e:
            s.status = "error"
            s.errors.append(str(e))
        s.duration_ms = (time.perf_counter() - start) * 1000
        stages["parser"] = s
        result["stages"]["parser"] = s.to_dict()

        # 9. Knowledge
        s = StageResult("knowledge")
        s.status = "running"
        start = time.perf_counter()
        try:
            normalized = dict(stages["parser"].output) if stages["parser"].status == "success" else {}
            for fname, field_data in list(normalized.items()):
                rule_result = self._rule_engine.apply_rules(
                    field=fname,
                    text=" ".join(
                        _aviso_text(a)
                        for a in (stages["continuity"].output or [])
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
            s.output = normalized
            s.status = "success"
            s.metrics = {"rules_applied": len([v for v in normalized.values() if v.get("source") == "knowledge"])}
        except Exception as e:
            s.status = "error"
            s.errors.append(str(e))
            s.output = stages["parser"].output if stages["parser"].status == "success" else {}
        s.duration_ms = (time.perf_counter() - start) * 1000
        stages["knowledge"] = s
        result["stages"]["knowledge"] = s.to_dict()

        # 10. Validator (FASE 6.9)
        s = StageResult("validator")
        s.status = "running"
        start = time.perf_counter()
        try:
            aviso_text = " ".join(
                _aviso_text(a)
                for a in (stages["continuity"].output or [])
            )
            v_result = self._validator.validate_notice(
                aviso_id=result["document_id"],
                text=aviso_text,
                fields_found=stages["knowledge"].output if stages["knowledge"].status == "success" else {},
            )
            if result.get("metrics", {}).get("ocr_parcial_detectado"):
                # No inventar ni certificar avisos de una página incompleta:
                # se marca para revisión sin importar qué haya concluido el
                # resto de las reglas de validación (problema #7).
                v_result.decision = Decision.INCOMPLETE
            s.output = v_result
            s.status = "success"
            s.metrics = {"decision": v_result.decision.value, "score": v_result.score}
        except Exception as e:
            s.status = "error"
            s.errors.append(str(e))
        s.duration_ms = (time.perf_counter() - start) * 1000
        stages["validator"] = s
        result["stages"]["validator"] = s.to_dict()
        result["validation"] = s.output.to_dict() if s.status == "success" else {}

        # 11. Normalizer
        s = StageResult("normalizer")
        s.status = "running"
        start = time.perf_counter()
        try:
            knowledge_fields = stages["knowledge"].output if stages["knowledge"].status == "success" else {}
            normalized_fields = self._normalizer.normalize_all(knowledge_fields)
            s.output = normalized_fields
            s.status = "success"
            s.metrics = {"fields_normalized": len(normalized_fields)}
        except Exception as e:
            s.status = "error"
            s.errors.append(str(e))
            s.output = stages["knowledge"].output if stages["knowledge"].status == "success" else {}
        s.duration_ms = (time.perf_counter() - start) * 1000
        stages["normalizer"] = s
        result["stages"]["normalizer"] = s.to_dict()
        result["fields"] = s.output if s.status == "success" else {}
        result["normalization"] = {
            fname: fd.get("normalization", {}) for fname, fd in (s.output if isinstance(s.output, dict) else {}).items()
        }

        # 12. Confidence
        s = StageResult("confidence")
        s.status = "running"
        start = time.perf_counter()
        try:
            final_fields = {}
            normalized_fields = stages["normalizer"].output
            v_result = stages["validator"].output if stages["validator"].status == "success" else None
            for fname, fdata in normalized_fields.items():
                parser_conf = fdata.get("confidence", 0) if isinstance(fdata, dict) else 0
                norm_result = fdata.get("normalization", {}) if isinstance(fdata, dict) else {}
                validator_passed = v_result and any(
                    r.passed for r in v_result.rules_applied
                ) if v_result else False
                fc = self._confidence.build_field_confidence(
                    field_name=fname,
                    parser_confidence=parser_conf,
                    ocr_confidence=0.85,
                    normalization_result=norm_result,
                    knowledge_boost=0.1 if fdata.get("source") == "knowledge" else 0.0,
                    validator_passed=validator_passed,
                )
                fdata["confidence"] = fc["confidence"]
                fdata["confidence_reason"] = fc["confidence_reason"]
                fdata["confidence_sources"] = fc["confidence_sources"]
                final_fields[fname] = fdata

            overall_scores = {
                "ocr": 0.85,
                "segmentation": 0.8,
                "parser": stages["parser"].output and sum(
                    f.get("confidence", 0) for f in stages["parser"].output.values()
                ) / max(len(stages["parser"].output), 1) if stages["parser"].output else 0,
                "normalization": 1.0 if stages["normalizer"].status == "success" else 0,
                "validation": v_result.score if v_result else 0,
                "knowledge": 0.9,
            }
            final_conf = self._confidence.calculate(overall_scores)
            s.output = final_conf
            s.status = "success"
            s.metrics = {"final_confidence": final_conf, "per_field": {k: v.get("confidence", 0) for k, v in final_fields.items()}}
        except Exception as e:
            s.status = "error"
            s.errors.append(str(e))
        s.duration_ms = (time.perf_counter() - start) * 1000
        stages["confidence"] = s
        result["stages"]["confidence"] = s.to_dict()
        result["confidence"] = s.output if s.status == "success" else 0

        # 13. Certification
        s = StageResult("certification")
        s.status = "running"
        start = time.perf_counter()
        try:
            cert_doc = self._certifier.build_certification(
                document_id=result["document_id"],
                source_type=result.get("source_type", ""),
                country=country,
                pipeline_result=result,
                knowledge_version="6.5.0",
                validator_version="6.9.0",
            )
            s.output = cert_doc
            s.status = "success"
            s.metrics = {"decision": cert_doc.all_avisos[0].decision.value if cert_doc.all_avisos else "unknown"}
        except Exception as e:
            s.status = "error"
            s.errors.append(str(e))
        s.duration_ms = (time.perf_counter() - start) * 1000
        stages["certification"] = s
        result["stages"]["certification"] = s.to_dict()

        # 14. Final JSON
        s = StageResult("final_json")
        s.status = "running"
        start = time.perf_counter()
        try:
            final = self._build_final_json(result, stages)
            s.output = final
            s.status = "success"
        except Exception as e:
            s.status = "error"
            s.errors.append(str(e))
        s.duration_ms = (time.perf_counter() - start) * 1000
        stages["final_json"] = s
        result["stages"]["final_json"] = s.to_dict()
        result["final_json"] = s.output if s.status == "success" else {}

        self._finalize(result, stages, overall_start)
        return result

    def _run_stage(self, name: str, stages: dict, fn) -> StageResult:
        s = StageResult(name)
        s.status = "running"
        start = time.perf_counter()
        try:
            s.output = fn()
            s.status = "success"
        except Exception as e:
            s.status = "error"
            s.errors.append(str(e))
        s.duration_ms = (time.perf_counter() - start) * 1000
        stages[name] = s
        return s

    def _build_final_json(self, result: dict, stages: dict) -> dict:
        cert_stage = stages.get("certification")
        cert_doc = cert_stage.output if cert_stage and cert_stage.status == "success" else None

        parser_stage = stages.get("parser")
        avisos_out = []
        if parser_stage and parser_stage.status == "success":
            aviso_texts = getattr(parser_stage, "per_aviso_texts", []) or []
            for i, fields in enumerate(getattr(parser_stage, "per_aviso_fields", []) or []):
                avisos_out.append({
                    "aviso_index": i,
                    "fields": fields,
                    "text": aviso_texts[i] if i < len(aviso_texts) else "",
                })

        return {
            "document": {
                "document_id": result["document_id"],
                "country": result["country"],
                "source_type": result["source_type"],
                "files": result["files"],
                "version": result["version"],
            },
            "avisos": avisos_out,
            "processing": {
                "timestamp": result["timestamp"],
                "total_time_ms": result["total_time_ms"],
                "stages": {k: v.to_dict() for k, v in stages.items()},
            },
            "stages": {k: v.to_dict() for k, v in stages.items()},
            "metrics": result.get("metrics", {}),
            "validation": result.get("validation", {}),
            "knowledge": result.get("stages", {}).get("knowledge", {}).get("metrics", {}),
            "certification": cert_doc.to_dict() if cert_doc else {},
            "performance": {
                "total_time_ms": result["total_time_ms"],
                "stage_times_ms": {k: v.duration_ms for k, v in stages.items()},
            },
            "warnings": result["warnings"],
            "errors": result["errors"],
            "statistics": {
                "fields_found": len(result.get("fields", {})),
                "avisos_detected": result.get("stages", {}).get("segmentation", {}).get("metrics", {}).get("avisos_detected", 0),
            },
            "field_confidence": {
                fname: {
                    "confidence": fd.get("confidence", 0),
                    "confidence_reason": fd.get("confidence_reason", ""),
                    "confidence_sources": fd.get("confidence_sources", {}),
                }
                for fname, fd in result.get("fields", {}).items()
            },
            "rules_applied": result.get("validation", {}).get("rules_applied", []),
            "rules_failed": result.get("validation", {}).get("rules_failed", []),
            "duplicates": result.get("validation", {}).get("duplicate_info"),
            "parser": result.get("stages", {}).get("parser", {}).get("metrics", {}),
            "normalization": result.get("normalization", {}),
            "validator": result.get("validation", {}),
        }

    def _finalize(self, result: dict, stages: dict, overall_start: float) -> dict:
        stage_times = {k: v.duration_ms for k, v in stages.items()}
        result["total_time_ms"] = round(sum(stage_times.values()), 2)
        result["metrics"] = {
            **result.get("metrics", {}),
            "stage_count": len(stages),
            "stages_completed": sum(1 for v in stages.values() if v.status == "success"),
            "stages_failed": sum(1 for v in stages.values() if v.status == "error"),
            "stages_with_warnings": sum(1 for v in stages.values() if v.warnings),
        }
        result["errors"] = [e for s in stages.values() for e in s.errors]
        result["warnings"] = [w for s in stages.values() for w in s.warnings]
        return result

    def export_duplicate_state(self) -> list[dict]:
        """Memoria de avisos vistos por el validador, lista para persistir
        (ej. guardarla junto al documento en DB) y restaurar en una corrida
        futura con load_duplicate_state(), habilitando deduplicación entre
        documentos procesados en sesiones distintas."""
        return self._validator.export_duplicate_state()

    def load_duplicate_state(self, state: list[dict]) -> None:
        """Restaura memoria de avisos vistos de una sesión anterior."""
        self._validator.load_duplicate_state(state)

    def process_batch(self, documents: list[dict]) -> list[dict]:
        results = []
        for doc in documents:
            r = self.process(
                doc.get("files", []),
                doc.get("country", "PA"),
                document_id=doc.get("id", ""),
                source_type=doc.get("source_type", ""),
            )
            results.append(r)
        return results
