"""FASE 11 — AI integration layer (Parte 8).

Flow:

    Parser
      ↓
    Knowledge
      ↓
    AIResolver (only fallback for REQUIRES_REVIEW / NOT_FOUND on allowed fields)
      ↓
    Validator
      ↓
    Certification

The Parser is never modified. AIResolver only acts when the parser/knowledge
result is REQUIRES_REVIEW or NOT_FOUND and ONLY for fields allowed by
AIConfidencePolicy. Found results with high confidence are never replaced.

Knowledge Safety (Parte 13): AI responses NEVER create rules, NEVER modify
rules, NEVER learn automatically, NEVER increase Knowledge Engine confidence
and NEVER change training metrics. They are only recorded in the AI audit log.
"""

import time
from typing import Any, Optional

from backend.app.v2.parser.base import AIResolver
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.result import ParseResult
from backend.app.v2.parser.ai.policy import is_field_allowed, AI_ALLOWED_FIELDS
from backend.app.v2.parser.ai.providers import DEFAULT_REGISTRY, estimate_cost
from backend.app.v2.production.smoke import run_text_pipeline


def enrich_fields(
    fields: dict,
    text: str,
    country: str = "CO",
    document_id: str = "",
    resolver: Optional[AIResolver] = None,
    document_type: str = "REMATE",
) -> tuple[dict, dict]:
    """Applies the resolver to fallback-eligible fields.

    Returns (enriched_fields, ai_summary).
    """
    resolver = resolver or DEFAULT_REGISTRY.create_default()
    enriched = dict(fields)
    ai_fields: list[str] = []
    ai_time_ms = 0.0
    cache_before = _cache_stats(resolver)
    audit_before = _audit_count(resolver)

    ctx = ParserContext(
        country=country.upper(),
        document_type=document_type,
        text=text,
        metadata={"document_id": document_id},
    )

    candidates = [
        (fname, fdata) for fname, fdata in fields.items()
        if fdata.get("status", "") in ("REQUIRES_REVIEW", "NOT_FOUND") and is_field_allowed(fname)
    ]
    present = set(fields.keys())
    candidates += [
        (fname, {"value": None, "confidence": 0.0, "status": "NOT_FOUND"})
        for fname in AI_ALLOWED_FIELDS
        if fname not in present
    ]

    for fname, fdata in candidates:

        previous = ParseResult(
            field_name=fname,
            value=fdata.get("value"),
            status=fdata.get("status", "NOT_FOUND"),
            confidence=float(fdata.get("confidence", 0.0) or 0.0),
        )
        start = time.perf_counter()
        resolved = resolver.resolve(fname, ctx, previous_result=previous)
        elapsed_ms = (time.perf_counter() - start) * 1000
        ai_time_ms += elapsed_ms

        if resolved.is_found:
            enriched[fname] = {
                "value": resolved.value,
                "confidence": resolved.confidence,
                "status": "FOUND",
                "evidence": resolved.evidence,
                "source": "ai",
                "ai_provider": resolver.provider_name(),
                "ai_latency_ms": round(elapsed_ms, 2),
            }
            ai_fields.append(fname)

    cache_after = _cache_stats(resolver)
    cost_usd, total_ai_tokens = _cost_from_audit_delta(resolver, audit_before)

    summary = {
        "ai_fields": ai_fields,
        "ai_fields_count": len(ai_fields),
        "ai_time_ms": round(ai_time_ms, 2),
        "provider": resolver.provider_name(),
        "cache_hits": cache_after["hits"] - cache_before["hits"],
        "cache_misses": cache_after["misses"] - cache_before["misses"],
        "cost_usd": round(cost_usd, 6),
        "total_ai_tokens": total_ai_tokens,
        "deterministic_fields_count": len([f for f, d in enriched.items() if d.get("source") != "ai"]),
    }
    return enriched, summary


def _cache_stats(resolver: AIResolver) -> dict:
    cache = getattr(resolver, "_cache", None)
    if cache is None:
        return {"hits": 0, "misses": 0}
    return cache.stats()


def _audit_count(resolver: AIResolver) -> int:
    audit = getattr(resolver, "_audit", None)
    if audit is None:
        return 0
    return audit.count()


def _cost_from_audit_delta(resolver: AIResolver, before: int) -> tuple[float, int]:
    audit = getattr(resolver, "_audit", None)
    if audit is None:
        return 0.0, 0
    entries = audit.to_list()[before:]
    if not entries:
        return 0.0, 0
    cost = sum(estimate_cost(e["provider"], e["tokens"]) for e in entries)
    tokens = sum(e["tokens"]["total_tokens"] for e in entries)
    return cost, tokens


class AIEnhancedPipeline:
    """Composes Parser → Knowledge → AIResolver → Validator → Certification.

    Uses the existing text pipeline for Parser/Knowledge and re-runs
    Validator + Certification over the AI-enriched fields. No pipeline,
    parser, knowledge, validator or certification code is modified.
    """

    def __init__(self, resolver: Optional[AIResolver] = None):
        self._resolver = resolver

    @property
    def resolver(self) -> AIResolver:
        if self._resolver is None:
            self._resolver = DEFAULT_REGISTRY.create_default()
        return self._resolver

    def run_text(
        self,
        text: str,
        country: str = "CO",
        document_id: str = "",
        source_type: str = "text",
        use_ai: bool = True,
    ) -> dict:
        result = run_text_pipeline(
            text, country=country, document_id=document_id, source_type=source_type
        )

        if not use_ai:
            result["ai"] = {"enabled": False}
            return result

        start = time.perf_counter()
        fields = result.get("fields", {})
        enriched, summary = enrich_fields(
            fields,
            text,
            country=country,
            document_id=document_id,
            resolver=self.resolver,
        )
        ai_total_ms = (time.perf_counter() - start) * 1000
        summary["ai_time_ms"] = round(ai_total_ms, 2)

        result["fields"] = enriched
        if "knowledge" in result.get("stages", {}):
            result["stages"]["knowledge"]["output"] = enriched

        result = _revalidate_and_recertify(result, enriched, text)
        result["stages"]["ai_resolver"] = {
            "status": "success",
            "duration_ms": round(ai_total_ms, 2),
            "warnings": [],
            "errors": [],
            "metrics": summary,
        }

        result["ai"] = summary
        result["metrics"]["ai_fields"] = summary["ai_fields_count"]
        result["metrics"]["deterministic_fields"] = summary["deterministic_fields_count"]

        result["knowledge_safety"] = {
            "rules_created": 0,
            "rules_modified": 0,
            "learning_events": 0,
            "knowledge_confidence_increased": False,
            "training_metrics_changed": False,
            "ai_answers_only_in_audit_log": True,
        }
        return result

    def run_files(
        self,
        file_paths: list[str],
        country: str,
        document_id: str = "",
        source_type: str = "",
        use_ai: bool = True,
    ) -> dict:
        from backend.app.v2.pipeline.runner import PipelineRunner

        runner = PipelineRunner()
        result = runner.process(file_paths, country, document_id=document_id, source_type=source_type)

        if not use_ai:
            result["ai"] = {"enabled": False}
            return result

        aviso_text = " ".join(
            a.full_text if hasattr(a, "full_text") else str(a)
            for a in (result.get("stages", {}).get("continuity", {}).get("output") or [])
        )
        fields = result.get("fields", {})
        enriched, summary = enrich_fields(
            fields,
            aviso_text,
            country=country,
            document_id=result.get("document_id", document_id),
            resolver=self.resolver,
        )
        result["fields"] = enriched
        if "knowledge" in result.get("stages", {}):
            result["stages"]["knowledge"]["output"] = enriched

        if aviso_text:
            result = _revalidate_and_recertify(result, enriched, aviso_text)
        result["stages"]["ai_resolver"] = {
            "status": "success",
            "duration_ms": summary["ai_time_ms"],
            "warnings": [],
            "errors": [],
            "metrics": summary,
        }

        result["ai"] = summary
        result["knowledge_safety"] = {
            "rules_created": 0,
            "rules_modified": 0,
            "learning_events": 0,
            "knowledge_confidence_increased": False,
            "training_metrics_changed": False,
            "ai_answers_only_in_audit_log": True,
        }
        return result


def _revalidate_and_recertify(result: dict, fields: dict, text: str) -> dict:
    from backend.app.v2.validator.orchestrator import ValidationOrchestrator
    from backend.app.v2.certification.certifier import Certifier

    validator = ValidationOrchestrator()
    decision = validator.validate_notice(
        aviso_id=result.get("document_id", ""),
        text=text,
        fields_found=fields,
    )
    result["validation"] = decision.to_dict()
    if "validator" in result.get("stages", {}):
        result["stages"]["validator"]["metrics"] = {
            "decision": decision.decision.value,
            "score": decision.score,
        }
        result["stages"]["validator"]["status"] = "success"

    certifier = Certifier()
    cert_doc = certifier.build_certification(
        document_id=result.get("document_id", ""),
        source_type=result.get("source_type", ""),
        country=result.get("country", ""),
        pipeline_result=result,
        knowledge_version="6.5.0",
        validator_version="6.9.0",
    )
    result["certification"] = cert_doc.to_dict()
    if "certification" in result.get("stages", {}):
        result["stages"]["certification"]["metrics"] = {
            "decision": cert_doc.all_avisos[0].decision.value if cert_doc.all_avisos else "unknown"
        }
        result["stages"]["certification"]["status"] = "success"
    return result
