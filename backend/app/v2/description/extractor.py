# Description Extractor — Extracts structured entities from descriptions


class DescriptionExtractor:
    def extract(self, normalized_text: str) -> dict:
        raise NotImplementedError("Implement in Phase 5")

    def extract_entities(self, text: str) -> list[dict]:
        raise NotImplementedError("Implement in Phase 5")

    def extract_references(self, text: str) -> list[dict]:
        raise NotImplementedError("Implement in Phase 5")
