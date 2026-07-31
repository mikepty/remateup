# Description Detector — Identifies property description sections


class DescriptionDetector:
    def detect(self, segmented_document: dict) -> list[dict]:
        raise NotImplementedError("Implement in Phase 5")

    def is_description(self, text: str) -> bool:
        raise NotImplementedError("Implement in Phase 5")
