"""FASE 11 — Provider abstraction (Parte 14).

The rest of the system only knows the `AIResolver` interface
(backend.app.v2.parser.base.AIResolver). New providers can be registered
without modifying the pipeline:

- ZAIResolver          (Z.ai)
- OpenRouterResolver   (OpenRouter)
- HuggingFaceResolver  (HuggingFace Inference)
- LocalResolver        (deterministic offline fallback)

No provider-specific conditionals exist inside the pipeline.
"""

import os
import re
import time
from typing import Any, Callable, Optional

from backend.app.v2.parser.base import AIResolver
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.result import ParseResult
from backend.app.v2.parser.ai.policy import AIConfidencePolicy, is_field_allowed
from backend.app.v2.parser.ai.prompt import build_ai_prompt, parse_ai_json, prompt_hash, response_hash
from backend.app.v2.parser.ai.cache import AICache
from backend.app.v2.parser.ai.rate_limit import RateLimiter
from backend.app.v2.parser.ai.audit import AIAuditLog


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def estimate_cost(
    provider: str,
    tokens: dict,
    input_price_per_1m: Optional[float] = None,
    output_price_per_1m: Optional[float] = None,
) -> float:
    """Cost estimate in USD from token usage.

    Prices default to the free tier (0.0) and can be overridden per provider
    via environment variables: <PROVIDER>_PRICE_INPUT_PER_1M / _OUTPUT.
    """
    env_suffix = provider.upper().replace("-", "_")
    in_price = (
        input_price_per_1m
        if input_price_per_1m is not None
        else float(os.environ.get(f"{env_suffix}_PRICE_INPUT_PER_1M", 0.0))
    )
    out_price = (
        output_price_per_1m
        if output_price_per_1m is not None
        else float(os.environ.get(f"{env_suffix}_PRICE_OUTPUT_PER_1M", 0.0))
    )
    prompt_tokens = int(tokens.get("prompt_tokens", 0))
    completion_tokens = int(tokens.get("completion_tokens", 0))
    return round(
        prompt_tokens / 1_000_000 * in_price + completion_tokens / 1_000_000 * out_price,
        6,
    )


def default_http_transport(base_url: str, api_key: str, model: str):
    """Returns a callable that posts an OpenAI-compatible chat completion."""

    def transport(payload: dict, timeout: float) -> dict:
        import requests

        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        start = time.perf_counter()
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return {
            "content": content,
            "model": data.get("model", model),
            "usage": data.get("usage", {}),
            "latency_ms": (time.perf_counter() - start) * 1000,
        }

    return transport


class OpenAICompatResolver(AIResolver):
    """Generic OpenAI-compatible chat completions resolver.

    All provider specifics (base URL, key env var, model) are passed via
    constructor defaults that read from environment variables.
    """

    def __init__(
        self,
        provider_name: str,
        base_url: str,
        key_env: str,
        model_env: str,
        default_model: str,
        cache: Optional[AICache] = None,
        rate_limiter: Optional[RateLimiter] = None,
        audit: Optional[AIAuditLog] = None,
        transport: Optional[Callable[[dict, float], dict]] = None,
        timeout: float = 30.0,
        max_tokens: int = 256,
        extra_payload: Optional[dict] = None,
    ):
        self._provider = provider_name
        self._base_url = base_url
        self._key_env = key_env
        self._model_env = model_env
        self._default_model = default_model
        self._extra_payload = extra_payload or {}
        self._cache = cache if cache is not None else AICache()
        self._rate_limiter = rate_limiter if rate_limiter is not None else RateLimiter()
        self._audit = audit if audit is not None else AIAuditLog()
        self._transport = transport or default_http_transport(
            base_url, os.environ.get(key_env, ""), self.model
        )
        self._timeout = timeout
        self._max_tokens = max_tokens

    @property
    def model(self) -> str:
        return os.environ.get(self._model_env, self._default_model)

    def _api_key(self) -> str:
        return os.environ.get(self._key_env, "")

    def is_available(self) -> bool:
        return bool(self._api_key())

    def provider_name(self) -> str:
        return self._provider

    def _passthrough(self, field: str, previous_result: Optional[ParseResult]) -> ParseResult:
        if previous_result is not None:
            return previous_result
        return ParseResult(field_name=field, status="REQUIRES_REVIEW")

    def _from_cache(self, field: str, entry: dict, previous_result: Optional[ParseResult]) -> ParseResult:
        decision = AIConfidencePolicy.decide(entry.get("confidence", 0.0))
        result = ParseResult(field_name=field)
        if decision == AIConfidencePolicy.FOUND:
            result.set_found(
                entry.get("value"),
                confidence=entry.get("confidence", 0.0),
                evidence=[{
                    "source": "ai",
                    "method": f"ai:{entry.get('provider', self._provider)}:cache",
                    "snippet": str(entry.get("reason", ""))[:200],
                    "confidence": entry.get("confidence", 0.0),
                }],
            )
        elif decision == AIConfidencePolicy.REQUIRES_REVIEW:
            result.set_requires_review(entry.get("value"), confidence=entry.get("confidence", 0.0))
        else:
            result.set_not_found()
        return result

    def _error_result(self, field: str, previous_result: Optional[ParseResult], error: str) -> ParseResult:
        if previous_result is not None and not previous_result.is_not_found:
            return previous_result
        return ParseResult(field_name=field, status="REQUIRES_REVIEW")

    def _build_payload(self, prompt: dict) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]},
            ],
            "temperature": 0,
            "max_tokens": self._max_tokens,
            "response_format": {"type": "json_object"},
        }
        payload.update(self._extra_payload)
        return payload

    def resolve(
        self,
        field_name: str,
        context: ParserContext,
        previous_result: Optional[ParseResult] = None,
    ) -> ParseResult:
        if not is_field_allowed(field_name):
            return self._passthrough(field_name, previous_result)

        key = self._cache.key(field_name, context)
        cached = self._cache.get(key)
        if cached is not None:
            return self._from_cache(field_name, cached, previous_result)

        if not self.is_available():
            return self._passthrough(field_name, previous_result)

        prompt = build_ai_prompt(field_name, context, previous_result)
        payload = self._build_payload(prompt)
        p_hash = prompt_hash(prompt)
        start = time.perf_counter()

        try:
            response, _attempts = self._rate_limiter.execute(
                lambda: self._transport(payload, self._timeout)
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            self._audit.record(
                provider=self._provider,
                modelo=self.model,
                tokens={},
                latencia_ms=latency_ms,
                prompt_hash=p_hash,
                response_hash="error",
                confidence=0.0,
                campo=field_name,
                documento=context.metadata.get("document_id", ""),
                decision="REQUIRES_REVIEW",
                status="error",
                country=context.country,
            )
            return self._error_result(field_name, previous_result, str(e))

        latency_ms = response.get("latency_ms", (time.perf_counter() - start) * 1000)
        content = response.get("content", "")
        model = response.get("model", self.model)
        usage = response.get("usage", {})

        data = parse_ai_json(content)
        if data is None:
            self._audit.record(
                provider=self._provider,
                modelo=model,
                tokens=usage,
                latencia_ms=latency_ms,
                prompt_hash=p_hash,
                response_hash=response_hash(content),
                confidence=0.0,
                campo=field_name,
                documento=context.metadata.get("document_id", ""),
                decision="REQUIRES_REVIEW",
                status="invalid_json",
                country=context.country,
            )
            return self._error_result(field_name, previous_result, "invalid JSON response")

        confidence = _clamp01(data["confidence"])
        decision = AIConfidencePolicy.decide(confidence)

        result = ParseResult(field_name=field_name)
        evidence = [{
            "source": "ai",
            "method": f"ai:{self._provider}:{model}",
            "snippet": str(data.get("reason", ""))[:200],
            "confidence": confidence,
        }]
        if decision == AIConfidencePolicy.FOUND:
            result.set_found(data["value"], confidence=confidence, evidence=evidence)
        elif decision == AIConfidencePolicy.REQUIRES_REVIEW:
            result.set_requires_review(data["value"], confidence=confidence)
        else:
            result.set_not_found()

        self._audit.record(
            provider=self._provider,
            modelo=model,
            tokens=usage,
            latencia_ms=latency_ms,
            prompt_hash=p_hash,
            response_hash=response_hash(data),
            confidence=confidence,
            campo=field_name,
            documento=context.metadata.get("document_id", ""),
            decision=decision,
            status="success",
            country=context.country,
        )

        if decision != AIConfidencePolicy.NOT_FOUND:
            self._cache.set(
                key,
                value=data["value"],
                confidence=confidence,
                provider=self._provider,
                model=model,
                reason=str(data.get("reason", "")),
                decision=decision,
                document_id=context.metadata.get("document_id", ""),
            )
        return result


_LOCAL_PATTERNS = {
    "fecha_remate": [
        r"FECHA\s*(?:DE\s+REMATE|PROGRAMADA|SEÑALADA)?\s*[:\s]*(\d{1,2}\s+DE\s+[A-ZÁÉÍÓÚÑ]+\s+DE\s+\d{4})",
        r"REMATE\s*(?:EL\s+DÍA|SEÑALADO\s+PARA\s+EL)?\s*[:\s]*(\d{1,2}/\d{1,2}/\d{2,4})",
    ],
    "hora": [
        r"\bHORA\s*[:\s]*(\d{1,2}:\d{2}\s*(?:AM|PM|A\.M\.|P\.M\.)?)",
        r"\bHORA\s*[:\s]*(\d{1,2}\s*(?:Y\s*)?(?:MEDIA\s*)?(?:AM|PM|A\.M\.|P\.M\.)?)",
    ],
    "lugar": [
        r"\bLUGAR\s*[:\s]*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s,.\-0-9]+?)(?:\n|$)",
    ],
    "juzgado": [
        r"\bJUZGADO\s*[:\s]*([A-ZÁÉÍÓÚÑ0-9][A-ZÁÉÍÓÚÑ0-9\s,.\-]+?)(?:\n|$)",
        r"\bDESPACHO\s*[:\s]*([A-ZÁÉÍÓÚÑ0-9][A-ZÁÉÍÓÚÑ0-9\s,.\-]+?)(?:\n|$)",
    ],
    "provincia": [
        r"\bPROVINCIA\s*[:\s]*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]+?)(?:\n|$)",
    ],
    "municipio": [
        r"\bMUNICIPIO\s*[:\s]*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]+?)(?:\n|$)",
    ],
}

_LOCAL_CONFIDENCE = 0.96


class LocalResolver(AIResolver):
    """Deterministic offline resolver for allowed fields.

    Uses strict label-based patterns with fixed high confidence. It is the
    default provider when no external API key is configured, keeping every
    AIResolver-based flow testable without network access.
    """

    def is_available(self) -> bool:
        return True

    def provider_name(self) -> str:
        return "local"

    def resolve(
        self,
        field_name: str,
        context: ParserContext,
        previous_result: Optional[ParseResult] = None,
    ) -> ParseResult:
        if not is_field_allowed(field_name):
            return previous_result if previous_result is not None else ParseResult(
                field_name=field_name, status="REQUIRES_REVIEW"
            )
        patterns = _LOCAL_PATTERNS.get(field_name, [])
        for pattern in patterns:
            m = re.search(pattern, context.text, re.IGNORECASE | re.MULTILINE)
            if m:
                value = re.sub(r"\s+", " ", m.group(m.lastindex).strip()) if m.lastindex else m.group(0).strip()
                result = ParseResult(field_name=field_name)
                result.set_found(
                    value,
                    confidence=_LOCAL_CONFIDENCE,
                    evidence=[{
                        "source": "ai",
                        "method": "ai:local:regex",
                        "snippet": m.group(0)[:200],
                        "confidence": _LOCAL_CONFIDENCE,
                    }],
                )
                return result
        result = ParseResult(field_name=field_name)
        result.set_not_found()
        return result


class OpenRouterResolver(OpenAICompatResolver):
    def __init__(self, **kwargs):
        super().__init__(
            provider_name="openrouter",
            base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            key_env="OPENROUTER_API_KEY",
            model_env="OPENROUTER_MODEL",
            default_model="openrouter/auto",
            **kwargs,
        )


class HuggingFaceResolver(OpenAICompatResolver):
    def __init__(self, **kwargs):
        super().__init__(
            provider_name="huggingface",
            base_url=os.environ.get("HF_BASE_URL", "https://api-inference.huggingface.co/v1"),
            key_env="HF_API_KEY",
            model_env="HF_MODEL",
            default_model="HuggingFaceH4/zephyr-7b-beta",
            **kwargs,
        )


class AIResolverRegistry:
    """Registers provider factories. The pipeline only knows AIResolver."""

    def __init__(self):
        self._factories: dict[str, Callable[[], AIResolver]] = {}
        self._instances: dict[str, AIResolver] = {}
        self._register_builtin("local", LocalResolver)

    def _register_builtin(self, name: str, factory):
        self._factories[name] = factory

    def register(self, name: str, factory: Callable[[], AIResolver]):
        self._factories[name] = factory
        self._instances.pop(name, None)

    def get(self, name: str) -> AIResolver:
        if name not in self._factories:
            self._try_import_builtin(name)
        if name not in self._factories:
            raise KeyError(f"Unknown AI provider: {name}")
        if name not in self._instances:
            self._instances[name] = self._factories[name]()
        return self._instances[name]

    def _try_import_builtin(self, name: str):
        try:
            if name == "zai":
                from backend.app.v2.parser.ai.zai_resolver import ZAIResolver
                self._factories["zai"] = ZAIResolver
            elif name == "openrouter":
                self._factories["openrouter"] = OpenRouterResolver
            elif name == "huggingface":
                self._factories["huggingface"] = HuggingFaceResolver
        except ImportError:
            pass

    def list_names(self) -> list[str]:
        return sorted(self._factories.keys())

    def default_name(self) -> str:
        env_provider = os.environ.get("AI_PROVIDER", "").strip().lower()
        if env_provider:
            return env_provider
        if os.environ.get("ZAI_API_KEY"):
            return "zai"
        return "local"

    def create_default(self) -> AIResolver:
        return self.get(self.default_name())

    def reset(self):
        self._instances.clear()


DEFAULT_REGISTRY = AIResolverRegistry()


def register_provider(name: str, factory: Callable[[], AIResolver]):
    DEFAULT_REGISTRY.register(name, factory)
