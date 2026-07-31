from typing import Optional

from backend.app.v2.parser.base import ParserInterface
from backend.app.v2.parser.registry import ParserRegistry
from backend.app.v2.parser.documents.panama_remate import PanamaRemateParser
from backend.app.v2.parser.documents.colombia_remate import ColombiaRemateParser


_DEFAULT_PARSERS = [PanamaRemateParser, ColombiaRemateParser]


class ParserFactory:
    def __init__(self, registry: Optional[ParserRegistry] = None):
        self._registry = registry or ParserRegistry()
        self._register_defaults()

    def _register_defaults(self):
        for parser_cls in _DEFAULT_PARSERS:
            self._registry.register(parser_cls())

    def get_parser(self, country: str, document_type: str) -> Optional[ParserInterface]:
        return self._registry.get(country, document_type)

    def has_parser(self, country: str, document_type: str) -> bool:
        return self._registry.has_parser(country, document_type)

    def register_parser(self, parser: ParserInterface):
        self._registry.register(parser)

    @property
    def registry(self) -> ParserRegistry:
        return self._registry
