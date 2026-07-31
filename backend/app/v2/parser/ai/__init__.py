"""FASE 11 — AIResolver package.

Everything AI-related stays encapsulated behind the `AIResolver` interface
(backend.app.v2.parser.base). The pipeline never knows a specific provider.
"""

from backend.app.v2.parser.ai.policy import (
    AIConfidencePolicy,
    AI_ALLOWED_FIELDS,
    AI_FORBIDDEN_FIELDS,
    is_field_allowed,
    is_field_forbidden,
)
from backend.app.v2.parser.ai.cache import AICache, cache_key
from backend.app.v2.parser.ai.rate_limit import RateLimiter, RateLimitError
from backend.app.v2.parser.ai.audit import AIAuditLog
from backend.app.v2.parser.ai.prompt import build_ai_prompt, parse_ai_json, prompt_hash, response_hash
from backend.app.v2.parser.ai.providers import (
    OpenAICompatResolver,
    LocalResolver,
    OpenRouterResolver,
    HuggingFaceResolver,
    AIResolverRegistry,
    DEFAULT_REGISTRY,
    register_provider,
    estimate_cost,
)

__all__ = [
    "AIConfidencePolicy",
    "AI_ALLOWED_FIELDS",
    "AI_FORBIDDEN_FIELDS",
    "is_field_allowed",
    "is_field_forbidden",
    "AICache",
    "cache_key",
    "RateLimiter",
    "RateLimitError",
    "AIAuditLog",
    "build_ai_prompt",
    "parse_ai_json",
    "prompt_hash",
    "response_hash",
    "OpenAICompatResolver",
    "LocalResolver",
    "OpenRouterResolver",
    "HuggingFaceResolver",
    "AIResolverRegistry",
    "DEFAULT_REGISTRY",
    "register_provider",
    "estimate_cost",
]
