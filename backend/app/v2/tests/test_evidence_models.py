from backend.app.v2.evidence.models import (
    Evidence, ExtractedField, EvidenceType, ExtractionState,
)


class TestEvidenceModels:
    def test_evidence_creation(self):
        ev = Evidence(
            field_name="expediente",
            value="12345",
            raw_value="12 345",
            state=ExtractionState.FOUND,
            evidence_type=EvidenceType.OCR_TEXT,
            confidence=0.95,
            source="vision_ocr",
        )
        assert ev.field_name == "expediente"
        assert ev.state == ExtractionState.FOUND
        assert ev.to_dict()["value"] == "12345"

    def test_extracted_field_states(self):
        f = ExtractedField(
            field_name="base",
            value=None,
            raw_value=None,
            state=ExtractionState.NOT_FOUND,
            evidence=[],
            confidence=0.0,
        )
        assert f.state == ExtractionState.NOT_FOUND
        assert f.value is None

        f2 = ExtractedField(
            field_name="base",
            value=100000.0,
            raw_value="100,000",
            state=ExtractionState.FOUND,
            evidence=[Evidence(field_name="base", value=100000.0, state=ExtractionState.FOUND)],
            confidence=0.9,
        )
        assert f2.state == ExtractionState.FOUND
        assert f2.value == 100000.0
