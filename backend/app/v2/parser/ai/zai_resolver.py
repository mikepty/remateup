"""FASE 11 — ZAIResolver: real implementation of AIResolver using the
Z.ai API configured via environment variables.

Reads:
    ZAI_API_KEY          (mandatory, never hardcoded)
    ZAI_BASE_URL         (default: https://api.z.ai/api/paas/v4)
    ZAI_MODEL            (default: glm-4.7-flash)
    ZAI_TIMEOUT          (default: 30.0)
    ZAI_MAX_CALLS_PER_MINUTE (default: 60)

Methods required by the AIResolver interface:
    is_available()
    provider_name()
    resolve(...)
"""

import os
from typing import Any, Callable, Optional

from backend.app.v2.parser.ai.providers import OpenAICompatResolver, default_http_transport
from backend.app.v2.parser.ai.cache import AICache
from backend.app.v2.parser.ai.rate_limit import RateLimiter
from backend.app.v2.parser.ai.audit import AIAuditLog


DEFAULT_ZAI_BASE_URL = "https://api.z.ai/api/paas/v4"
DEFAULT_ZAI_MODEL = "glm-4.5-flash"


class ZAIResolver(OpenAICompatResolver):
    def __init__(
        self,
        cache: Optional[AICache] = None,
        rate_limiter: Optional[RateLimiter] = None,
        audit: Optional[AIAuditLog] = None,
        transport: Optional[Callable[[dict, float], dict]] = None,
        timeout: Optional[float] = None,
        max_tokens: int = 256,
        extra_payload: Optional[dict] = None,
    ):
        base_url = os.environ.get("ZAI_BASE_URL", DEFAULT_ZAI_BASE_URL)
        model = os.environ.get("ZAI_MODEL", DEFAULT_ZAI_MODEL)
        if transport is None:
            transport = default_http_transport(base_url, os.environ.get("ZAI_API_KEY", ""), model)
        if rate_limiter is None:
            rate_limiter = RateLimiter(
                max_calls_per_minute=int(os.environ.get("ZAI_MAX_CALLS_PER_MINUTE", "60")),
                timeout_seconds=float(os.environ.get("ZAI_TIMEOUT", "30.0")),
                max_retries=int(os.environ.get("ZAI_MAX_RETRIES", "2")),
            )
        default_extra = {"thinking": {"type": "disabled"}}
        super().__init__(
            provider_name="zai",
            base_url=base_url,
            key_env="ZAI_API_KEY",
            model_env="ZAI_MODEL",
            default_model=DEFAULT_ZAI_MODEL,
            cache=cache,
            rate_limiter=rate_limiter,
            audit=audit,
            transport=transport,
            timeout=timeout if timeout is not None else float(os.environ.get("ZAI_TIMEOUT", "30.0")),
            max_tokens=max_tokens,
            extra_payload=extra_payload if extra_payload is not None else default_extra,
        )
