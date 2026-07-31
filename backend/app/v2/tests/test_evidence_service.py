import unittest

from backend.app.v2.evidence.models import Evidence, ExtractionState, EvidenceType, ExtractedField
from backend.app.v2.evidence.service import EvidenceService


class TestEvidence(unittest.TestCase):
    def test_create_evidence(self):
        ev = Evidence(field_name="expediente", value="12345", raw_value="12 345",
                       state=ExtractionState.FOUND,
                       evidence_type=EvidenceType.OCR_TEXT,
                       confidence=0.95, source="vision_ocr")
        self.assertEqual(ev.field_name, "expediente")
        self.assertEqual(ev.value, "12345")
        self.assertEqual(ev.state, ExtractionState.FOUND)
        self.assertEqual(ev.to_dict()["confidence"], 0.95)

    def test_evidence_builder_pattern(self):
        ev = Evidence.builder() \
            .with_field("base") \
            .with_value(100000.0, raw_value="$100,000.00") \
            .with_confidence(0.9) \
            .from_source("ocr_vision") \
            .at_position(page=1, x0=100, y0=200, x1=300, y1=220)
        self.assertEqual(ev.field_name, "base")
        self.assertEqual(ev.value, 100000.0)
        self.assertEqual(ev.source, "ocr_vision")
        self.assertEqual(ev.page, 1)
        self.assertEqual(ev.bounding_box, {"x0": 100, "y0": 200, "x1": 300, "y1": 220})

    def test_evidence_low_confidence_triggers_review(self):
        ev = Evidence.builder() \
            .with_field("finca_matr") \
            .with_value("30269") \
            .with_confidence(0.45)
        self.assertEqual(ev.state, ExtractionState.REQUIRES_REVIEW)

    def test_evidence_empty_value_is_not_found(self):
        ev = Evidence.builder().with_field("demandado").with_value(None)
        self.assertEqual(ev.state, ExtractionState.NOT_FOUND)

    def test_evidence_with_transformation(self):
        ev = Evidence(field_name="base", value=100000.0)
        ev.add_transformation("remove_currency")
        ev.add_transformation("parse_float")
        self.assertEqual(len(ev.transformation_log), 2)
        self.assertIn("remove_currency", ev.transformation_log)


class TestExtractedField(unittest.TestCase):
    def test_not_found_factory(self):
        ef = ExtractedField.not_found("demandado")
        self.assertEqual(ef.field_name, "demandado")
        self.assertTrue(ef.is_not_found)
        self.assertIsNone(ef.value)

    def test_found_factory(self):
        ef = ExtractedField.found("base", 150000.0, confidence=0.95)
        self.assertTrue(ef.is_found)
        self.assertEqual(ef.value, 150000.0)
        self.assertEqual(ef.confidence, 0.95)

    def test_best_evidence(self):
        e1 = Evidence(field_name="base", value=100000.0, confidence=0.8)
        e2 = Evidence(field_name="base", value=150000.0, confidence=0.95)
        ef = ExtractedField(
            field_name="base", value=150000.0, raw_value=150000.0,
            state=ExtractionState.FOUND, evidence=[e1, e2], confidence=0.95,
        )
        best = ef.best_evidence
        self.assertIsNotNone(best)
        self.assertEqual(best.confidence, 0.95)
        self.assertEqual(best.value, 150000.0)

    def test_evidence_summary(self):
        e1 = Evidence(field_name="expediente", evidence_type=EvidenceType.OCR_TEXT)
        e2 = Evidence(field_name="expediente", evidence_type=EvidenceType.LABEL_VALUE_RELATION)
        ef = ExtractedField(
            field_name="expediente", value="123", raw_value="123",
            state=ExtractionState.FOUND, evidence=[e1, e2], confidence=0.9,
        )
        summary = ef.evidence_summary
        self.assertIn("2 sources", summary)
        self.assertIn("ocr_text", summary)


class TestEvidenceService(unittest.TestCase):
    def test_register_evidence(self):
        service = EvidenceService()
        ev = service.register_evidence(
            field_name="expediente", value="12345", raw_value="12 345",
            evidence_type=EvidenceType.OCR_TEXT, confidence=0.95, source="vision_ocr",
        )
        self.assertEqual(ev.field_name, "expediente")
        self.assertEqual(ev.confidence, 0.95)
        self.assertEqual(len(service._evidence_log), 1)

    def test_register_text_evidence(self):
        service = EvidenceService()
        ev = service.register_text_evidence("descripcion", "Casa en Panama")
        self.assertEqual(ev.field_name, "descripcion")
        self.assertEqual(ev.value, "Casa en Panama")
        self.assertEqual(ev.evidence_type, EvidenceType.OCR_TEXT)

    def test_register_label_value(self):
        service = EvidenceService()
        ev = service.register_label_value_evidence("finca_matr", "Finca:", "30269571", confidence=0.95)
        self.assertEqual(ev.field_name, "finca_matr")
        self.assertEqual(ev.value, "30269571")
        self.assertEqual(ev.evidence_type, EvidenceType.LABEL_VALUE_RELATION)

    def test_build_field_no_evidence(self):
        service = EvidenceService()
        ef = service.build_field("nonexistent")
        self.assertTrue(ef.is_not_found)
        self.assertEqual(ef.confidence, 0.0)

    def test_build_field_with_evidence(self):
        service = EvidenceService()
        service.register_evidence("base", "100000", "$100,000", EvidenceType.OCR_TEXT, 0.85, "ocr")
        service.register_evidence("base", "100000", "$100,000", EvidenceType.PARSER_PATTERN, 0.95, "parser")
        ef = service.build_field("base")
        self.assertTrue(ef.is_found)
        self.assertEqual(ef.value, "100000")
        self.assertEqual(ef.confidence, 0.95)

    def test_has_evidence(self):
        service = EvidenceService()
        self.assertFalse(service.has_evidence("base"))
        service.register_text_evidence("base", "100000")
        self.assertTrue(service.has_evidence("base"))

    def test_summary(self):
        service = EvidenceService()
        service.register_text_evidence("base", "100000")
        service.register_text_evidence("expediente", "123")
        s = service.summary()
        self.assertEqual(s["total_evidence"], 2)
        self.assertEqual(s["unique_fields"], 2)

    def test_clear(self):
        service = EvidenceService()
        service.register_text_evidence("base", "100000")
        service.clear()
        self.assertEqual(len(service._evidence_log), 0)
        self.assertEqual(service.summary()["total_evidence"], 0)


if __name__ == "__main__":
    unittest.main()
