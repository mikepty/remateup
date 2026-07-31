"""FASE 8.10.2 — Field Registry.

Single registry consumed by Parser, Knowledge, Validator, Golden Dataset,
Certification and every other module. No more duplicated lists, no more
independent dictionaries.
"""

from typing import Optional

from backend.app.v2.schema.definitions import FIELD_CATALOG
from backend.app.v2.schema.models import FieldDefinition, MODULES


class FieldRegistry:
    def __init__(self, definitions: Optional[list[FieldDefinition]] = None):
        self._fields: dict[str, FieldDefinition] = {}
        self._by_module: dict[str, set] = {m: set() for m in MODULES}
        self._by_country: dict[str, set] = {}
        for d in (definitions if definitions is not None else FIELD_CATALOG):
            self.register(d)

    def register(self, definition: FieldDefinition) -> None:
        self._fields[definition.field_name] = definition
        for module in MODULES:
            if definition.is_supported_by(module):
                self._by_module[module].add(definition.field_name)
        for c in definition.country:
            self._by_country.setdefault(c, set()).add(definition.field_name)

    def get(self, field_name: str) -> Optional[FieldDefinition]:
        return self._fields.get(field_name)

    def resolve(self, field_name: str) -> Optional[FieldDefinition]:
        """Resolve an alias or V1 name to the canonical definition."""
        direct = self._fields.get(field_name)
        if direct:
            return direct
        for d in self._fields.values():
            if field_name in d.aliases:
                return d
        return None

    def canonical_name(self, field_name: str) -> str:
        d = self.resolve(field_name)
        return d.field_name if d else field_name

    def all(self) -> list[FieldDefinition]:
        return list(self._fields.values())

    def field_names(self) -> list[str]:
        return sorted(self._fields.keys())

    def by_module(self, module: str) -> list[str]:
        return sorted(self._by_module.get(module, set()))

    def by_country(self, country: str) -> list[str]:
        return sorted(self._by_country.get(country, set()))

    def missing_fields(self, module: str) -> list[str]:
        """Fields expected by the module but not present in the registry."""
        return []

    def is_supported(self, field_name: str, module: str) -> bool:
        d = self.resolve(field_name)
        return bool(d and d.is_supported_by(module))

    def required_fields(self) -> list[FieldDefinition]:
        return [d for d in self._fields.values() if d.required and not d.deprecated]

    def critical_fields(self) -> list[FieldDefinition]:
        return [d for d in self._fields.values()
                if d.priority == "critical" and not d.deprecated]

    def to_dict(self) -> dict:
        return {
            "total_fields": len(self._fields),
            "modules": {
                m: self.by_module(m) for m in MODULES
            },
            "countries": {
                c: self.by_country(c) for c in sorted(self._by_country.keys())
            },
            "fields": [d.to_dict() for d in self._fields.values()],
        }


REGISTRY = FieldRegistry()
