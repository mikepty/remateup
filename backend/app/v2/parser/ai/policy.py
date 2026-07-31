"""FASE 11 — AI field policy and confidence gate.

- Defines which fields MAY be resolved by AI (AIResolver) and which must
  remain 100% deterministic (parser + knowledge only).
- AIConfidencePolicy maps an AI confidence value to a ParseResult status:

      confidence >= 0.95  -> FOUND
      0.80 <= confidence < 0.95 -> REQUIRES_REVIEW
      confidence < 0.80   -> NOT_FOUND
"""

AI_ALLOWED_FIELDS = frozenset({
    "fecha_remate",
    "hora",
    "lugar",
    "juzgado",
    "provincia",
    "municipio",
})

AI_FORBIDDEN_FIELDS = frozenset({
    "expediente",
    "finca",
    "precio_base",
    "base",
    "fianza",
    "minimo",
    "matricula",
})

FOUND_THRESHOLD = 0.95
REVIEW_MIN_THRESHOLD = 0.80


def is_field_allowed(field_name: str) -> bool:
    return field_name in AI_ALLOWED_FIELDS


def is_field_forbidden(field_name: str) -> bool:
    return field_name in AI_FORBIDDEN_FIELDS


class AIConfidencePolicy:
    FOUND = "FOUND"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    NOT_FOUND = "NOT_FOUND"

    @staticmethod
    def decide(confidence: float) -> str:
        try:
            c = float(confidence)
        except (TypeError, ValueError):
            return AIConfidencePolicy.REQUIRES_REVIEW
        c = max(0.0, min(1.0, c))
        if c >= FOUND_THRESHOLD:
            return AIConfidencePolicy.FOUND
        if c >= REVIEW_MIN_THRESHOLD:
            return AIConfidencePolicy.REQUIRES_REVIEW
        return AIConfidencePolicy.NOT_FOUND

    @staticmethod
    def is_allowed(field_name: str) -> bool:
        return is_field_allowed(field_name)
