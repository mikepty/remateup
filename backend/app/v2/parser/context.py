from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParserContext:
    country: str = ""
    document_type: str = ""
    text: str = ""
    sections: list[dict] = field(default_factory=list)
    blocks: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "country": self.country,
            "document_type": self.document_type,
            "text_length": len(self.text),
            "sections": len(self.sections),
            "blocks": len(self.blocks),
            "evidence": len(self.evidence),
        }
