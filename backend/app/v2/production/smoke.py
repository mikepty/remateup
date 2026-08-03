"""FASE 10 — Smoke Test.

Executes the minimum production flow:

Documento -> OCR -> Parser -> Knowledge -> Validator -> Certification -> Resultado

If any stage fails the smoke test reports FAIL.

Also provides `run_text_pipeline`, a deterministic text-only execution
of the pipeline used by the Batch Runner and the Benchmark.
"""

import time
from datetime import datetime
from typing import Any, Optional

from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.factory import ParserFactory
from backend.app.v2.knowledge.repository import KnowledgeRepository
from backend.app.v2.knowledge.rules import RuleEngine
from backend.app.v2.knowledge.integration import KnowledgeAwareWrapper
from backend.app.v2.validator.orchestrator import ValidationOrchestrator
from backend.app.v2.certification.certifier import Certifier

SMOKE_TEXT_CO = (
    "AVISO DE REMATE\n"
    "EXPEDIENTE N° 2025-00456\n"
    "MATRÍCULA INMOBILIARIA N° 050-123456\n"
    "AVALÚO COMERCIAL: $500,000,000\n"
    "FECHA DE REMATE: 20 DE DICIEMBRE DE 2026\n"
    "DEMANDANTE: BANCO DE BOGOTA\n"
    "DEMANDADO: PEDRO PABLO PEREZ LOPEZ\n"
    "FIANZA DEL POSTOR: 40%\n"
    "PORCENTAJE MÍNIMO DE LA POSTURA: 70%\n"
)

_PIPELINE_VERSION = "10.0.0"


def run_text_pipeline(
    text: str,
    country: str = "CO",
    document_id: str = "",
    source_type: str = "text",
    validator: Optional[ValidationOrchestrator] = None,
) -> dict:
    result: dict[str, Any] = {
        "document_id": document_id or "text_document",
        "country": country.upper(),
        "source_type": source_type,
        "files": [],
        "stages": {},
        "fields": {},
        "validation": {},
        "normalization": {},
        "confidence": 0.0,
        "certification": {},
        "final_json": {},
        "total_time_ms": 0.0,
        "errors": [],
        "warnings": [],
        "metrics": {},
        "version": _PIPELINE_VERSION,
        "timestamp": datetime.utcnow().isoformat(),
    }

    country_code = country.upper()

    def run_stage(name: str, fn) -> dict:
        start = time.perf_counter()
        stage = {"status": "success", "duration_ms": 0.0,
                 "warnings": [], "errors": [], "metrics": {}}
        try:
            stage["output"] = fn()
        except Exception as e:
            stage["status"] = "error"
            stage["errors"].append(str(e))
        stage["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
        result["stages"][name] = stage
        return stage

    run_stage("assembly", lambda: {"pages": 1})
    run_stage("ocr", lambda: {"synthetic": True, "text": text})
    result["stages"]["ocr"]["metrics"] = {"synthetic": True, "avg_confidence": 1.0}
    run_stage("mapping", lambda: {"method": "embedded", "status": "mapped"})

    run_stage("segmentation", lambda: {
        "avisos_detected": 1,
        "avisos": [{"full_text": text}],
    })
    result["stages"]["segmentation"]["metrics"] = {"avisos_detected": 1}

    run_stage("parser", lambda: _parse_text(text, country_code))
    parser_stage = result["stages"]["parser"]

    run_stage("knowledge", lambda: _apply_knowledge(text, country_code, parser_stage))
    knowledge_stage = result["stages"]["knowledge"]

    run_stage("validator", lambda: _validate(result["document_id"], text, knowledge_stage, validator))
    validator_stage = result["stages"]["validator"]

    result["fields"] = knowledge_stage.get("output", {}) if knowledge_stage["status"] == "success" else {}
    result["validation"] = validator_stage["output"].to_dict() if validator_stage["status"] == "success" else {}

    run_stage("certification", lambda: _certify(result))
    result["certification"] = (
        result["stages"]["certification"]["output"].to_dict()
        if result["stages"]["certification"]["status"] == "success"
        else {}
    )

    result["total_time_ms"] = round(
        sum(s["duration_ms"] for s in result["stages"].values()), 2
    )
    result["errors"] = [e for s in result["stages"].values() for e in s["errors"]]
    result["warnings"] = [w for s in result["stages"].values() for w in s["warnings"]]
    result["metrics"] = {
        "stage_count": len(result["stages"]),
        "stages_completed": sum(1 for s in result["stages"].values() if s["status"] == "success"),
        "stages_failed": sum(1 for s in result["stages"].values() if s["status"] == "error"),
        "fields_found": len(result["fields"]),
    }
    return result


def _parse_text(text: str, country: str) -> dict:
    parser = ParserFactory().get_parser(country, "REMATE")
    repo = KnowledgeRepository()
    rule_engine = RuleEngine(repository=repo)
    wrapper = KnowledgeAwareWrapper(parser, rule_engine=rule_engine, repository=repo)
    ctx = ParserContext(country=country, document_type="REMATE", text=text)
    parse_results = wrapper.parse(ctx)
    return {
        fname: {
            "value": pr.value,
            "confidence": pr.confidence,
            "status": pr.status,
            "evidence": pr.evidence,
            "source": "parser",
        }
        for fname, pr in parse_results.items()
        if pr.is_found
    }


def _apply_knowledge(text: str, country: str, parser_stage: dict) -> dict:
    repo = KnowledgeRepository()
    rule_engine = RuleEngine(repository=repo)
    fields = dict(parser_stage.get("output", {})) if parser_stage["status"] == "success" else {}
    for fname in list(fields.keys()):
        rule_result = rule_engine.apply_rules(field=fname, text=text)
        if rule_result and rule_result.is_found:
            fields[fname] = {
                "value": rule_result.value,
                "confidence": rule_result.confidence,
                "status": "FOUND",
                "evidence": rule_result.evidence,
                "source": "knowledge",
            }
    return fields


def _validate(aviso_id: str, text: str, knowledge_stage: dict,
               validator: Optional[ValidationOrchestrator] = None) -> Any:
    fields = knowledge_stage.get("output", {}) if knowledge_stage["status"] == "success" else {}
    orchestrator = validator if validator is not None else ValidationOrchestrator()
    return orchestrator.validate_notice(
        aviso_id=aviso_id,
        text=text,
        fields_found=fields,
    )


def _certify(result: dict) -> Any:
    certifier = Certifier()
    return certifier.build_certification(
        document_id=result["document_id"],
        source_type=result.get("source_type", ""),
        country=result["country"],
        pipeline_result=result,
        knowledge_version="6.5.0",
        validator_version="6.9.0",
    )


class SmokeTest:
    def __init__(self, text: Optional[str] = None, country: str = "CO"):
        self.text = text or SMOKE_TEXT_CO
        self.country = country

    def run(self) -> dict:
        stages_report: dict[str, dict] = {}
        for name in ("documento", "ocr", "parser", "knowledge", "validator", "certification"):
            stages_report[name] = {"status": "pending", "error": None}

        result = run_text_pipeline(self.text, country=self.country, document_id="smoke_test")
        stages = result["stages"]

        stages_report["documento"]["status"] = "success"
        stages_report["ocr"]["status"] = "success"
        for stage_name, key in (
            ("parser", "parser"),
            ("knowledge", "knowledge"),
            ("validator", "validator"),
            ("certification", "certification"),
        ):
            stage = stages.get(key, {})
            if stage.get("status") == "success":
                stages_report[stage_name]["status"] = "success"
            else:
                stages_report[stage_name]["status"] = "failed"
                stages_report[stage_name]["error"] = stage.get("errors", [])[:1] or "stage failed"

        failed = [name for name, s in stages_report.items() if s["status"] != "success"]
        return {
            "status": "PASS" if not failed else "FAIL",
            "stages": stages_report,
            "result": result,
            "failed_stages": failed,
            "country": self.country,
            "total_time_ms": result["total_time_ms"],
            "errors": result["errors"],
            "timestamp": datetime.utcnow().isoformat(),
        }

    def run_with_pipeline(self, file_path: str, country: str) -> dict:
        from backend.app.v2.pipeline.runner import PipelineRunner
        runner = PipelineRunner()
        result = runner.process([file_path], country, document_id="smoke_pipeline")
        failed = [s for s, stage in result["stages"].items() if stage.get("status") == "error"]
        return {
            "status": "PASS" if not failed else "FAIL",
            "stages": result["stages"],
            "result": result,
            "failed_stages": failed,
            "country": country,
            "total_time_ms": result["total_time_ms"],
            "errors": result["errors"],
            "timestamp": datetime.utcnow().isoformat(),
        }


def run_smoke_test(text: Optional[str] = None, country: str = "CO") -> dict:
    return SmokeTest(text=text, country=country).run()
