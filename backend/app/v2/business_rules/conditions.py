# Business Rule Conditions


class Conditions:
    @staticmethod
    def field_not_empty(fields: dict, field_name: str) -> bool:
        raise NotImplementedError("Implement in Phase 8")

    @staticmethod
    def field_matches(fields: dict, field_name: str, pattern: str) -> bool:
        raise NotImplementedError("Implement in Phase 8")

    @staticmethod
    def country_is(fields: dict, pais: str) -> bool:
        raise NotImplementedError("Implement in Phase 8")
