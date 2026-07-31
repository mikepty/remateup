# Duplicate Detection


class DuplicateDetector:
    def is_duplicate(self, fields: dict, existing_avisos: list[dict]) -> dict:
        raise NotImplementedError("Implement in Phase 9")

    def is_republication(self, fields: dict, existing_avisos: list[dict]) -> dict:
        raise NotImplementedError("Implement in Phase 9")

    def find_similar(self, fields: dict, existing_avisos: list[dict]) -> list[dict]:
        raise NotImplementedError("Implement in Phase 9")
