# Description Normalizer — Normalizes property description while preserving raw_text


class DescriptionNormalizer:
    def normalize(self, raw_text: str) -> dict:
        raise NotImplementedError("Implement in Phase 5")

    def extract_location(self, text: str) -> dict:
        raise NotImplementedError("Implement in Phase 5")

    def extract_area(self, text: str) -> dict:
        raise NotImplementedError("Implement in Phase 5")
