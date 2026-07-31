from abc import ABC, abstractmethod
from typing import Any, Optional

from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.result import ParseResult


class ParserInterface(ABC):
    @abstractmethod
    def parse(self, context: ParserContext) -> dict[str, ParseResult]:
        ...

    @property
    @abstractmethod
    def supported_fields(self) -> list[str]:
        ...

    @property
    @abstractmethod
    def country(self) -> str:
        ...

    @property
    @abstractmethod
    def document_type(self) -> str:
        ...

    def extract_simple(self, text: str, pattern: str, field_name: str,
                       flags: int = 0) -> Optional[str]:
        import re
        m = re.search(pattern, text, flags)
        return m.group(1).strip() if m else None


class AIResolver(ABC):
    """Interface for AI-based fallback resolution.

    Implementations can use Z.ai, OpenRouter, HuggingFace, etc.
    Only invoked when deterministic parser confidence is below threshold.
    """

    @abstractmethod
    def resolve(self, field_name: str, context: ParserContext,
                previous_result: Optional[ParseResult] = None) -> ParseResult:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def provider_name(self) -> str:
        ...
