"""FASE 11 — Tests: ZAIResolver, Cache, RateLimiter, ConfidencePolicy,
Auditoría, JSON parsing, Timeout, Retry, Integración, Dataset Runner.

No existing test is removed; all previous phases must keep passing.
"""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.v2.parser.ai.policy import (
    AIConfidencePolicy,
    is_field_allowed,
    AI_ALLOWED_FIELDS,
    AI_FORBIDDEN_FIELDS,
)
from backend.app.v2.parser.ai.prompt import build_ai_prompt, parse_ai_json, prompt_hash, response_hash
from backend.app.v2.parser.ai.cache import AICache, cache_key
from backend.app.v2.parser.ai.rate_limit import RateLimiter, RateLimitError
from backend.app.v2.parser.ai.audit import AIAuditLog
from backend.app.v2.parser.ai.zai_resolver import ZAIResolver
from backend.app.v2.parser.ai.providers import (
    LocalResolver,
    AIResolverRegistry,
    DEFAULT_REGISTRY,
    estimate_cost,
)
from backend.app.v2.parser.ai.integration import AIEnhancedPipeline, enrich_fields
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.result import ParseResult
from backend.app.v2.evaluation.production.runner import ProductionDatasetRunner
from backend.app.v2.evaluation.production.comparison import compare_corpus, compare_document
from backend.app.v2.evaluation.production.report import generate_production_validation, build_markdown


def fake_transport(confidence: float, value: str = "10:30 AM", content: str = None):
    def transport(payload, timeout):
        body = content if content is not None else json.dumps(
            {"value": value, "confidence": confidence, "reason": "test reason"}
        )
        return {
            "content": body,
            "model": "glm-test",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "latency_ms": 1.0,
        }

    return transport


class TestAIConfidencePolicy:
    def test_found_threshold(self):
        assert AIConfidencePolicy.decide(0.95) == "FOUND"
        assert AIConfidencePolicy.decide(0.99) == "FOUND"
        assert AIConfidencePolicy.decide(1.0) == "FOUND"

    def test_review_band(self):
        assert AIConfidencePolicy.decide(0.94) == "REQUIRES_REVIEW"
        assert AIConfidencePolicy.decide(0.80) == "REQUIRES_REVIEW"

    def test_not_found_below(self):
        assert AIConfidencePolicy.decide(0.79) == "NOT_FOUND"
        assert AIConfidencePolicy.decide(0.0) == "NOT_FOUND"

    def test_invalid_confidence(self):
        assert AIConfidencePolicy.decide(None) == "REQUIRES_REVIEW"
        assert AIConfidencePolicy.decide("abc") == "REQUIRES_REVIEW"

    def test_allowed_fields(self):
        assert {"fecha_remate", "hora", "lugar", "juzgado", "provincia", "municipio"} == set(AI_ALLOWED_FIELDS)
        for f in AI_ALLOWED_FIELDS:
            assert is_field_allowed(f)
        for f in AI_FORBIDDEN_FIELDS:
            assert not is_field_allowed(f)
        assert not is_field_allowed("demandante")


class TestAIPrompt:
    def _ctx(self):
        return ParserContext(country="CO", document_type="REMATE", text="HORA: 10:30 AM\nAVISO")

    def test_prompt_contains_required_parts(self):
        prompt = build_ai_prompt("hora", self._ctx())
        assert "CO" in prompt["user"]
        assert "REMATE" in prompt["user"]
        assert "hora" in prompt["user"]
        assert "HORA: 10:30 AM" in prompt["user"]
        assert prompt["country"] == "CO"
        assert prompt["document_type"] == "REMATE"
        assert prompt["field_name"] == "hora"

    def test_json_only_instruction(self):
        prompt = build_ai_prompt("hora", self._ctx())
        assert "exclusively JSON" in prompt["system"] or "single valid JSON object" in prompt["system"]
        assert '"confidence"' in prompt["system"]

    def test_existing_evidence_included(self):
        prev = ParseResult(field_name="hora", value="10:30 AM", status="REQUIRES_REVIEW", confidence=0.5)
        prompt = build_ai_prompt("hora", self._ctx(), previous_result=prev)
        assert "10:30 AM" in prompt["user"]

    def test_hashes(self):
        prompt = build_ai_prompt("hora", self._ctx())
        assert prompt_hash(prompt) == prompt_hash(prompt)
        assert prompt_hash(prompt) != prompt_hash(build_ai_prompt("lugar", self._ctx()))
        assert response_hash({"a": 1}) == response_hash({"a": 1})


class TestParseAIJson:
    def test_valid_json(self):
        data = parse_ai_json('{"value": "10:30 AM", "confidence": 0.9, "reason": "ok"}')
        assert data["value"] == "10:30 AM"
        assert data["confidence"] == 0.9
        assert data["reason"] == "ok"

    def test_fenced_json(self):
        data = parse_ai_json('```json\n{"value": "x", "confidence": 0.9, "reason": "r"}\n```')
        assert data["value"] == "x"

    def test_json_embedded_in_prose(self):
        data = parse_ai_json('Here is the answer: {"value": "y", "confidence": 0.8, "reason": "r"} done')
        assert data["value"] == "y"

    def test_invalid_json(self):
        assert parse_ai_json("no es json") is None
        assert parse_ai_json("") is None
        assert parse_ai_json(None) is None

    def test_missing_keys(self):
        assert parse_ai_json('{"value": "x"}') is None
        assert parse_ai_json('{"confidence": 0.9}') is None
        assert parse_ai_json('[1, 2, 3]') is None


class TestAICache:
    def test_key_stable(self):
        k1 = cache_key("hora", "texto", "CO")
        k2 = cache_key("hora", "texto", "CO")
        k3 = cache_key("hora", "texto", "PA")
        k4 = cache_key("lugar", "texto", "CO")
        assert k1 == k2
        assert k1 != k3
        assert k1 != k4
        assert len(k1) == 64

    def test_hit_miss(self):
        cache = AICache()
        ctx = ParserContext(country="CO", text="texto")
        key = cache.key("hora", ctx)
        assert cache.get(key) is None
        assert cache.stats()["misses"] == 1
        cache.set(key, "10:30 AM", 0.98, "zai", model="glm-test", decision="FOUND")
        entry = cache.get(key)
        assert entry["value"] == "10:30 AM"
        assert entry["provider"] == "zai"
        assert cache.stats()["hits"] == 1

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "cache.json")
            cache = AICache(path=path)
            ctx = ParserContext(country="CO", text="t")
            key = cache.key("hora", ctx)
            cache.set(key, "v", 0.9, "zai")
            cache.save()
            cache2 = AICache(path=path)
            assert cache2.get(key)["value"] == "v"

    def test_max_entries(self):
        cache = AICache(max_entries=2)
        for i in range(5):
            ctx = ParserContext(country="CO", text=f"t{i}")
            cache.set(cache.key("hora", ctx), f"v{i}", 0.9, "zai")
        assert cache.stats()["size"] <= 2


class TestRateLimiter:
    def test_timeout(self):
        limiter = RateLimiter(timeout_seconds=0.2, max_retries=0)
        with pytest.raises(RateLimitError):
            limiter.execute(lambda: time.sleep(1.0))

    def test_retry_then_success(self):
        limiter = RateLimiter(timeout_seconds=5.0, max_retries=3, backoff_base=0.0)
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("temporary")
            return "ok"

        result, attempts = limiter.execute(flaky)
        assert result == "ok"
        assert attempts == 3
        stats = limiter.stats()
        assert stats["retries"] >= 2

    def test_retries_exhausted(self):
        limiter = RateLimiter(timeout_seconds=5.0, max_retries=1, backoff_base=0.0)

        def always_fails():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            limiter.execute(always_fails)
        assert limiter.stats()["errors"] >= 2

    def test_stats(self):
        limiter = RateLimiter(max_calls_per_minute=100, max_retries=0)
        limiter.execute(lambda: "ok")
        assert limiter.stats()["calls"] == 1


class TestZAIResolver:
    def _resolver(self, transport, tmp_path, audit_path=None):
        cache = AICache(path=str(Path(tmp_path) / "ai_cache.json"))
        audit = AIAuditLog(path=audit_path or str(Path(tmp_path) / "ai_audit.jsonl"))
        return ZAIResolver(
            cache=cache,
            audit=audit,
            transport=transport,
            rate_limiter=RateLimiter(max_calls_per_minute=1000, max_retries=0, timeout_seconds=5.0),
        )

    def test_provider_name(self, tmp_path):
        r = self._resolver(fake_transport(0.95), tmp_path)
        assert r.provider_name() == "zai"

    def test_is_available_requires_key(self, tmp_path):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ZAI_API_KEY", None)
            r = self._resolver(fake_transport(0.95), tmp_path)
            assert not r.is_available()
        os.environ["ZAI_API_KEY"] = "test-key"
        try:
            assert self._resolver(fake_transport(0.95), tmp_path).is_available()
        finally:
            os.environ.pop("ZAI_API_KEY", None)

    def test_resolve_found(self, tmp_path):
        os.environ["ZAI_API_KEY"] = "test-key"
        try:
            r = self._resolver(fake_transport(0.98), tmp_path)
            ctx = ParserContext(country="CO", text="HORA: 10:30 AM")
            result = r.resolve("hora", ctx)
            assert result.is_found
            assert result.value == "10:30 AM"
            assert result.confidence == 0.98
            assert result.evidence[0]["source"] == "ai"
        finally:
            os.environ.pop("ZAI_API_KEY", None)

    def test_resolve_review_band(self, tmp_path):
        os.environ["ZAI_API_KEY"] = "test-key"
        try:
            r = self._resolver(fake_transport(0.85), tmp_path)
            result = r.resolve("hora", ParserContext(country="CO", text="x"))
            assert result.requires_review
        finally:
            os.environ.pop("ZAI_API_KEY", None)

    def test_resolve_not_found_below(self, tmp_path):
        os.environ["ZAI_API_KEY"] = "test-key"
        try:
            r = self._resolver(fake_transport(0.5), tmp_path)
            result = r.resolve("hora", ParserContext(country="CO", text="x"))
            assert result.is_not_found
        finally:
            os.environ.pop("ZAI_API_KEY", None)

    def test_invalid_json_requires_review(self, tmp_path):
        os.environ["ZAI_API_KEY"] = "test-key"
        try:
            r = self._resolver(fake_transport(0.9, content="free text answer"), tmp_path)
            result = r.resolve("hora", ParserContext(country="CO", text="x"))
            assert result.requires_review
            audit = r._audit.to_list()
            assert audit and audit[-1]["status"] == "invalid_json"
        finally:
            os.environ.pop("ZAI_API_KEY", None)

    def test_forbidden_field_never_calls_transport(self, tmp_path):
        os.environ["ZAI_API_KEY"] = "test-key"
        try:
            called = {"n": 0}

            def spy(payload, timeout):
                called["n"] += 1
                return fake_transport(0.98)(payload, timeout)

            r = self._resolver(spy, tmp_path)
            prev = ParseResult(field_name="expediente", value="123", status="NOT_FOUND")
            result = r.resolve("expediente", ParserContext(country="CO", text="x"), previous_result=prev)
            assert called["n"] == 0
            assert result is prev
        finally:
            os.environ.pop("ZAI_API_KEY", None)

    def test_cache_avoids_repeated_calls(self, tmp_path):
        os.environ["ZAI_API_KEY"] = "test-key"
        try:
            called = {"n": 0}

            def spy(payload, timeout):
                called["n"] += 1
                return fake_transport(0.98)(payload, timeout)

            r = self._resolver(spy, tmp_path)
            ctx = ParserContext(country="CO", text="HORA: 10:30 AM")
            r.resolve("hora", ctx)
            r.resolve("hora", ctx)
            assert called["n"] == 1
        finally:
            os.environ.pop("ZAI_API_KEY", None)

    def test_audit_fields_and_no_api_key(self, tmp_path):
        os.environ["ZAI_API_KEY"] = "test-key"
        try:
            r = self._resolver(fake_transport(0.98), tmp_path)
            r.resolve("hora", ParserContext(country="CO", text="HORA: 10:30 AM", metadata={"document_id": "doc-1"}))
            entries = r._audit.to_list()
            assert len(entries) == 1
            e = entries[0]
            assert e["provider"] == "zai"
            assert e["modelo"]
            assert e["tokens"]["total_tokens"] == 15
            assert e["latencia_ms"] > 0
            assert len(e["prompt_hash"]) == 64
            assert len(e["response_hash"]) == 64
            assert e["confidence"] == 0.98
            assert e["campo"] == "hora"
            assert e["documento"] == "doc-1"
            assert e["decision"] == "FOUND"
            serialized = json.dumps(e).lower()
            assert "api_key" not in serialized
            assert "7e332f24" not in serialized
        finally:
            os.environ.pop("ZAI_API_KEY", None)


class TestLocalResolver:
    def test_resolves_allowed_fields(self):
        r = LocalResolver()
        ctx = ParserContext(country="CO", text="HORA: 10:30 AM\nLUGAR: SALA DE REMATES\nJUZGADO: JUZGADO CIVIL DE BOGOTÁ")
        assert r.resolve("hora", ctx).is_found
        assert r.resolve("hora", ctx).value == "10:30 AM"
        assert r.resolve("lugar", ctx).is_found
        assert r.resolve("juzgado", ctx).is_found
        assert r.provider_name() == "local"
        assert r.is_available()

    def test_not_found(self):
        r = LocalResolver()
        result = r.resolve("hora", ParserContext(country="CO", text="sin hora"))
        assert result.is_not_found

    def test_forbidden_field(self):
        r = LocalResolver()
        prev = ParseResult(field_name="expediente", value="123", status="REQUIRES_REVIEW")
        assert r.resolve("expediente", ParserContext(country="CO", text="x"), previous_result=prev) is prev


class TestRegistry:
    def test_default_without_key(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ZAI_API_KEY", None)
            os.environ.pop("AI_PROVIDER", None)
            assert DEFAULT_REGISTRY.default_name() == "local"

    def test_default_with_key(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ["ZAI_API_KEY"] = "k"
            os.environ.pop("AI_PROVIDER", None)
            assert DEFAULT_REGISTRY.default_name() == "zai"
            os.environ.pop("ZAI_API_KEY", None)

    def test_register_custom(self):
        registry = AIResolverRegistry()

        class CustomResolver(LocalResolver):
            def provider_name(self):
                return "custom"

        registry.register("custom", CustomResolver)
        assert "custom" in registry.list_names()
        assert registry.get("custom").provider_name() == "custom"
        with pytest.raises(KeyError):
            registry.get("does_not_exist")


class TestAuditLog:
    def test_record_and_stats(self, tmp_path):
        path = str(Path(tmp_path) / "audit.jsonl")
        log = AIAuditLog(path=path)
        log.record("zai", "glm-test", {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                   12.5, "a" * 64, "b" * 64, 0.9, "hora", "doc-1", "FOUND")
        assert log.count() == 1
        stats = log.stats()
        assert stats["entries"] == 1
        assert stats["total_tokens"] == 15
        assert stats["by_provider"] == {"zai": 1}
        assert Path(path).exists()

    def test_never_stores_key(self, tmp_path):
        log = AIAuditLog(path=str(Path(tmp_path) / "audit.jsonl"))
        log.record("zai", "m", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                   1.0, "p" * 64, "r" * 64, 0.9, "hora", "d", "FOUND")
        raw = Path(log.path()).read_text(encoding="utf-8")
        assert "api_key" not in raw.lower()
        assert "ZAI_API_KEY" not in raw


class TestCostEstimate:
    def test_free_tier_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ZAI_PRICE_INPUT_PER_1M", None)
            os.environ.pop("ZAI_PRICE_OUTPUT_PER_1M", None)
            assert estimate_cost("zai", {"prompt_tokens": 1000, "completion_tokens": 500}) == 0.0

    def test_configured_rates(self):
        with patch.dict(os.environ, {"ZAI_PRICE_INPUT_PER_1M": "0.5", "ZAI_PRICE_OUTPUT_PER_1M": "1.5"}, clear=False):
            cost = estimate_cost("zai", {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000})
            assert cost == 2.0


class TestIntegration:
    def test_enrich_fields_only_fallback_and_allowed(self):
        fields = {
            "expediente": {"value": "2025-00456", "confidence": 0.95, "status": "FOUND", "source": "parser"},
            "hora": {"value": None, "confidence": 0.0, "status": "NOT_FOUND"},
            "demandante": {"value": None, "confidence": 0.0, "status": "NOT_FOUND"},
        }
        text = "HORA: 10:30 AM"
        enriched, summary = enrich_fields(fields, text, country="CO", resolver=LocalResolver())
        assert enriched["expediente"]["source"] == "parser"
        assert enriched["hora"]["status"] == "FOUND"
        assert enriched["hora"]["source"] == "ai"
        assert "demandante" not in [f for f, d in enriched.items() if d.get("source") == "ai"]
        assert summary["ai_fields"] == ["hora"]

    def test_never_replaces_high_confidence_found(self):
        fields = {
            "fecha_remate": {"value": "20 DE DICIEMBRE DE 2026", "confidence": 0.95, "status": "FOUND", "source": "parser"},
        }
        enriched, summary = enrich_fields(fields, "FECHA DE REMATE: 20 DE DICIEMBRE DE 2026",
                                          country="CO", resolver=LocalResolver())
        assert enriched["fecha_remate"]["source"] == "parser"
        assert summary["ai_fields_count"] == 0

    def test_pipeline_run_text(self):
        text = (
            "AVISO DE REMATE\nEXPEDIENTE N° 2025-00456\nDEMANDANTE: BANCO\n"
            "DEMANDADO: PEREZ\nAVALÚO COMERCIAL: $500,000,000\n"
            "FECHA DE REMATE: 20 DE DICIEMBRE DE 2026\n"
            "FIANZA DEL POSTOR: 40%\nPORCENTAJE MÍNIMO DE LA POSTURA: 70%\n"
        )
        pipeline = AIEnhancedPipeline(resolver=LocalResolver())
        result = pipeline.run_text(text, country="CO", document_id="doc-x")
        assert result["ai"]["provider"] == "local"
        assert result["knowledge_safety"]["rules_created"] == 0
        assert result["knowledge_safety"]["ai_answers_only_in_audit_log"] is True
        assert "stages" in result and "ai_resolver" in result["stages"]

    def test_knowledge_safety_no_rules_created(self):
        from backend.app.v2.knowledge.repository import KnowledgeRepository

        repo = KnowledgeRepository()
        before = repo.get_rules()
        pipeline = AIEnhancedPipeline(resolver=LocalResolver())
        pipeline.run_text(
            "AVISO DE REMATE\nEXPEDIENTE N° 2025-00001\nHORA: 09:00 AM",
            country="CO", document_id="safety-test",
        )
        after = repo.get_rules()
        assert len(after) == len(before)


class TestDatasetRunner:
    def test_run_text_file(self, tmp_path):
        file = Path(tmp_path) / "2025-99999.txt"
        file.write_text(
            "AVISO DE REMATE\nEXPEDIENTE N° 2025-99999\nDEMANDANTE: X\nDEMANDADO: Y\n"
            "AVALÚO COMERCIAL: $100,000\nHORA: 08:00 AM\n",
            encoding="utf-8",
        )
        runner = ProductionDatasetRunner(use_ai=True, resolver=LocalResolver())
        result = runner.run_file(str(file), "CO", document_id="2025-99999")
        assert result["fields"]["expediente"]["value"] == "2025-99999"
        assert "hora" in result.get("ai", {}).get("ai_fields", [])

    def test_run_directory_summary(self):
        from backend.app.v2.evaluation.production.runner import SAMPLES_DIR

        runner = ProductionDatasetRunner(use_ai=True, resolver=LocalResolver())
        run = runner.run_directory(str(SAMPLES_DIR / "co"), "CO")
        assert run["total_files"] == 16
        assert run["processed"] == 16
        assert run["failed"] == 0
        summary = runner.summary(run)
        assert summary["documentos"] == 16
        assert summary["avisos_encontrados"] == 16
        assert summary["campos_ia"] >= 0
        assert summary["tiempo_promedio_ms"] > 0

    def test_comparison_totals(self):
        from backend.app.v2.evaluation.production.runner import SAMPLES_DIR

        comp = compare_corpus(str(SAMPLES_DIR / "co"), country="CO")
        assert comp["documents"] == 16
        assert set(comp["parser_only"].keys()) == {"per_field", "totals"}
        assert set(comp["parser_plus_ai"].keys()) == {"per_field", "totals"}
        assert comp["parser_only"]["totals"]["tp"] >= 0
        assert comp["parser_plus_ai"]["totals"]["tp"] >= 0

    def test_compare_document_counts(self):
        predicted = {"expediente": {"value": "2025-00001", "status": "FOUND"},
                     "demandante": {"value": "OTRO", "status": "FOUND"}}
        expected = {"expediente": "2025-00001", "demandante": "BANCO X"}
        doc = compare_document(predicted, expected, ["expediente", "demandante"])
        assert doc["expediente"] == {"tp": 1, "fp": 0, "fn": 0}
        assert doc["demandante"] == {"tp": 0, "fp": 1, "fn": 0}

    def test_report_generation(self, tmp_path):
        report = {
            "dataset": "test",
            "provider": "local",
            "summary": {
                "documentos": 3,
                "avisos_encontrados": 3,
                "avisos_validos": 3,
                "descartados": 0,
                "duplicados": 0,
                "campos_por_documento": [{"document_id": "d1", "campos": ["expediente"], "cantidad": 1}],
                "campos_ia": 1,
                "campos_deterministas": 5,
                "tiempo_promedio_ms": 10.5,
                "tiempo_ia_ms": 3.2,
                "costo_estimado_usd": 0.0,
                "cache_hit": 2,
                "cache_miss": 1,
            },
            "comparison": {
                "parser_only": {"per_field": {}, "totals": {"tp": 1, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0}},
                "parser_plus_ai": {"per_field": {}, "totals": {"tp": 1, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0}},
            },
            "errors": [],
        }
        out_dir = Path(tmp_path) / "output"
        paths = generate_production_validation(report, output_dir=out_dir)
        assert (out_dir / "production_validation.json").exists()
        assert (out_dir / "production_validation.md").exists()
        md = build_markdown(report)
        assert "Solo Parser" in md
        assert "documentos" in md.lower()
