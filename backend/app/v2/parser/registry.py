from typing import Optional

from backend.app.v2.parser.base import ParserInterface


class ParserRegistry:
    def __init__(self):
        self._parsers: dict[tuple[str, str], ParserInterface] = {}

    def register(self, parser: ParserInterface):
        key = (parser.country.upper(), parser.document_type.upper())
        self._parsers[key] = parser

    def get(self, country: str, document_type: str) -> Optional[ParserInterface]:
        key = (country.upper(), document_type.upper())
        return self._parsers.get(key)

    def get_all(self) -> list[ParserInterface]:
        return list(self._parsers.values())

    def has_parser(self, country: str, document_type: str) -> bool:
        return self.get(country, document_type) is not None

    def unregister(self, country: str, document_type: str):
        key = (country.upper(), document_type.upper())
        self._parsers.pop(key, None)

    @property
    def count(self) -> int:
        return len(self._parsers)
