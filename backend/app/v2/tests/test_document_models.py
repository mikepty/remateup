import unittest

from backend.app.v2.document.models import (
    Document, Page, Section, Field, SectionType, DocumentType,
)


class TestDocument(unittest.TestCase):
    def test_create_empty_document(self):
        doc = Document()
        self.assertIsNone(doc.id)
        self.assertEqual(doc.document_type, DocumentType.UNKNOWN)
        self.assertEqual(doc.pais, "")
        self.assertEqual(doc.total_pages, 0)
        self.assertEqual(doc.total_fields, 0)
        self.assertEqual(doc.status, "pending")

    def test_create_panama_document(self):
        doc = Document(pais="PA", document_type=DocumentType.NEWSPAPER_PAGE)
        self.assertEqual(doc.pais, "PA")
        self.assertEqual(doc.document_type, DocumentType.NEWSPAPER_PAGE)

    def test_add_field(self):
        doc = Document()
        doc.add_field("expediente", "12345", confidence=0.95, state="found")
        self.assertTrue(doc.has_field("expediente"))
        self.assertEqual(doc.get_field("expediente").value, "12345")
        self.assertEqual(doc.fields["expediente"].confidence, 0.95)
        self.assertEqual(doc.fields["expediente"].state, "found")

    def test_field_default_state(self):
        doc = Document()
        doc.add_field("base")
        field = doc.get_field("base")
        self.assertIsNotNone(field)
        self.assertIsNone(field.value)
        self.assertEqual(field.state, "not_found")
        self.assertTrue(field.is_empty())

    def test_field_set_found(self):
        field = Field(name="base")
        field.set_found(150000.0, confidence=0.95)
        self.assertEqual(field.value, 150000.0)
        self.assertEqual(field.confidence, 0.95)
        self.assertEqual(field.state, "found")

    def test_field_set_not_found(self):
        field = Field(name="demandante", value="Juan", state="found")
        field.set_not_found()
        self.assertIsNone(field.value)
        self.assertEqual(field.state, "not_found")

    def test_field_requires_review(self):
        field = Field(name="finca_matr")
        field.set_requires_review("30269", confidence=0.45)
        self.assertEqual(field.value, "30269")
        self.assertEqual(field.state, "requires_review")

    def test_missing_fields_property(self):
        doc = Document()
        doc.add_field("expediente", "123", state="found")
        doc.add_field("base", "100000", state="found")
        doc.add_field("demandante", state="not_found")
        doc.add_field("demandado", state="not_found")
        self.assertEqual(doc.found_fields, ["expediente", "base"])
        self.assertEqual(doc.missing_fields, ["demandante", "demandado"])
        self.assertEqual(doc.total_fields, 4)

    def test_average_field_confidence(self):
        doc = Document()
        doc.add_field("expediente", "123", confidence=0.95, state="found")
        doc.add_field("base", "100000", confidence=0.85, state="found")
        doc.add_field("demandante", state="not_found")
        self.assertEqual(doc.average_field_confidence, 0.9)

    def test_add_page(self):
        doc = Document()
        page = Page(number=1, width=2000, height=3000, text="some text")
        doc.add_page(page)
        self.assertEqual(doc.total_pages, 1)
        self.assertEqual(doc.pages[0].number, 1)
        self.assertEqual(doc.pages[0].area(), 6000000)

    def test_add_section(self):
        doc = Document()
        section = Section(section_type=SectionType.VALORES, text="Base: 100000", page=1, confidence=0.9)
        doc.add_section(section)
        self.assertEqual(len(doc.sections), 1)
        self.assertEqual(doc.sections[0].section_type, SectionType.VALORES)

    def test_merge_field_keeps_best(self):
        doc = Document()
        doc.add_field("base", "100000", confidence=0.9, state="found")
        better = Field(name="base", value="150000", confidence=0.95, state="found")
        doc.merge_field("base", better)
        self.assertEqual(doc.get_field("base").value, "150000")
        self.assertEqual(doc.get_field("base").confidence, 0.95)

    def test_merge_field_keeps_existing_if_better(self):
        doc = Document()
        doc.add_field("base", "100000", confidence=0.9, state="found")
        worse = Field(name="base", value="50000", confidence=0.6, state="found")
        doc.merge_field("base", worse)
        self.assertEqual(doc.get_field("base").value, "100000")
        self.assertEqual(doc.get_field("base").confidence, 0.9)

    def test_to_dict(self):
        doc = Document(pais="PA")
        doc.add_field("expediente", "123", state="found")
        d = doc.to_dict()
        self.assertEqual(d["pais"], "PA")
        self.assertEqual(d["found_fields"], 1)
        self.assertIn("fields", d)

    def test_field_add_evidence(self):
        field = Field(name="base", value=100000.0)
        field.add_evidence({"source": "ocr_text", "confidence": 0.9})
        field.add_evidence({"source": "label_value", "confidence": 0.95})
        self.assertEqual(len(field.evidence), 2)

    def test_field_add_transformation(self):
        field = Field(name="base", raw_value="$100,000.00")
        field.add_transformation("remove_currency_symbol")
        field.add_transformation("remove_thousands_separator")
        self.assertEqual(len(field.transformations), 2)

    def test_page_empty(self):
        page = Page(number=1)
        self.assertTrue(page.is_empty())
        page.text = "content"
        self.assertFalse(page.is_empty())


class TestSection(unittest.TestCase):
    def test_section_to_dict(self):
        s = Section(section_type=SectionType.HEADER, text="AVISO DE REMATE", page=1, confidence=0.98)
        d = s.to_dict()
        self.assertEqual(d["section_type"], "header")
        self.assertEqual(d["text"], "AVISO DE REMATE")
        self.assertEqual(d["confidence"], 0.98)


class TestDocumentType(unittest.TestCase):
    def test_valid_types(self):
        self.assertEqual(DocumentType.NEWSPAPER_PAGE.value, "newspaper_page")
        self.assertEqual(DocumentType.PDF_TABULAR.value, "pdf_tabular")
        self.assertEqual(DocumentType.PDF_SCANNED.value, "pdf_scanned")


class TestAllowedStates(unittest.TestCase):
    def test_states_are_restricted(self):
        from backend.app.v2.document.models import PARSER_ALLOWED_STATES
        self.assertIn("found", PARSER_ALLOWED_STATES)
        self.assertIn("not_found", PARSER_ALLOWED_STATES)
        self.assertIn("requires_review", PARSER_ALLOWED_STATES)
        self.assertEqual(len(PARSER_ALLOWED_STATES), 3)


if __name__ == "__main__":
    unittest.main()
