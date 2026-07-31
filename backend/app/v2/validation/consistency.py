# Cross-field Consistency Validation


class ConsistencyValidator:
    def validate(self, fields: dict, pais: str) -> list[dict]:
        raise NotImplementedError("Implement in Phase 9")

    def validate_fianza_minimo(self, base: float, fianza_pct: float, minimo_pct: float) -> dict:
        raise NotImplementedError("Implement in Phase 9")

    def validate_categoria(self, categoria: str, descripcion: str) -> dict:
        raise NotImplementedError("Implement in Phase 9")
