import unittest

from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.result import ParseResult
from backend.app.v2.parser.base import ParserInterface, AIResolver
from backend.app.v2.parser.registry import ParserRegistry
from backend.app.v2.parser.factory import ParserFactory
from backend.app.v2.parser.documents.panama_remate import PanamaRemateParser
from backend.app.v2.parser.documents.colombia_remate import ColombiaRemateParser


class TestParseResult(unittest.TestCase):
    def test_default_status(self):
        r = ParseResult(field_name="test")
        self.assertEqual(r.status, "NOT_FOUND")
        self.assertIsNone(r.value)
        self.assertEqual(r.confidence, 0.0)

    def test_set_found(self):
        r = ParseResult(field_name="finca")
        r.set_found("12345", confidence=0.95)
        self.assertTrue(r.is_found)
        self.assertEqual(r.value, "12345")
        self.assertEqual(r.confidence, 0.95)

    def test_set_not_found(self):
        r = ParseResult(field_name="test")
        r.set_found("value", 0.9)
        r.set_not_found()
        self.assertTrue(r.is_not_found)
        self.assertIsNone(r.value)

    def test_requires_review(self):
        r = ParseResult(field_name="test")
        r.set_requires_review("maybe", 0.4)
        self.assertTrue(r.requires_review)
        self.assertEqual(r.value, "maybe")

    def test_add_evidence(self):
        r = ParseResult(field_name="finca")
        r.add_evidence(source="text", method="regex", snippet="FINCA 1234", confidence=0.95)
        self.assertEqual(len(r.evidence), 1)
        self.assertEqual(r.evidence[0]["snippet"], "FINCA 1234")

    def test_invalid_status_raises(self):
        with self.assertRaises(ValueError):
            ParseResult(field_name="x", status="INVALID")

    def test_to_dict(self):
        r = ParseResult(field_name="finca")
        r.set_found("9999", 0.9)
        r.add_evidence("text", "regex", "FINCA 9999", 0.9)
        d = r.to_dict()
        self.assertEqual(d["field_name"], "finca")
        self.assertEqual(d["value"], "9999")
        self.assertEqual(d["status"], "FOUND")
        self.assertEqual(d["evidence_count"], 1)


class TestParserContext(unittest.TestCase):
    def test_create_context(self):
        ctx = ParserContext(
            country="PA",
            document_type="REMATE",
            text="AVISO DE REMATE\nFINCA 1234",
            sections=[{"type": "header", "text": "AVISO DE REMATE"}],
        )
        self.assertEqual(ctx.country, "PA")
        self.assertIn("FINCA 1234", ctx.text)
        self.assertEqual(len(ctx.sections), 1)

    def test_defaults(self):
        ctx = ParserContext()
        self.assertEqual(ctx.country, "")
        self.assertEqual(ctx.text, "")

    def test_to_dict(self):
        ctx = ParserContext(country="CO", text="test")
        d = ctx.to_dict()
        self.assertEqual(d["country"], "CO")
        self.assertEqual(d["text_length"], 4)


class TestPanamaRemateParser(unittest.TestCase):
    def setUp(self):
        self.parser = PanamaRemateParser()

    def test_supported_fields(self):
        fields = self.parser.supported_fields
        self.assertIn("expediente", fields)
        self.assertIn("finca", fields)
        self.assertIn("precio_base", fields)
        self.assertIn("fecha_remate", fields)
        self.assertIn("demandante", fields)
        self.assertIn("demandado", fields)

    def test_country_and_type(self):
        self.assertEqual(self.parser.country, "PA")
        self.assertEqual(self.parser.document_type, "REMATE")

    def test_extract_expediente(self):
        text = "AVISO DE REMATE\nExpediente N° 12345-2025\nFINCA 6789"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["expediente"].is_found)
        self.assertIn("12345", results["expediente"].value)

    def test_extract_finca(self):
        text = "AVISO DE REMATE\nFINCA 12345\nBASE: B/.50,000.00"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["finca"].is_found)
        self.assertIn("12345", results["finca"].value)

    def test_extract_precio_base(self):
        text = "AVISO DE REMATE\nFINCA 999\nBASE B/.25,000.00"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["precio_base"].is_found)
        self.assertIn("25,000", results["precio_base"].value)

    def test_extract_precio_base_simple(self):
        text = "AVISO DE REMATE\nBASE: 15000.00"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["precio_base"].is_found)

    def test_extract_fecha_remate(self):
        text = "AVISO DE REMATE\nFECHA DE REMATE: 15 DE AGOSTO DE 2026"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["fecha_remate"].is_found)
        self.assertIn("AGOSTO", results["fecha_remate"].value)

    def test_extract_demandante(self):
        text = "AVISO DE REMATE\nDEMANDANTE: JUAN PEREZ\nFINCA 123"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["demandante"].is_found)
        self.assertIn("JUAN PEREZ", results["demandante"].value)

    def test_extract_demandado(self):
        text = "AVISO DE REMATE\nDEMANDADO: MARIA GARCIA\nFINCA 456"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["demandado"].is_found)
        self.assertIn("MARIA GARCIA", results["demandado"].value)

    def test_field_not_found(self):
        text = "Este texto no tiene campos de remate"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        for field in self.parser.supported_fields:
            self.assertTrue(results[field].is_not_found,
                            f"{field} should be NOT_FOUND")

    def test_evidence_added_on_found(self):
        text = "AVISO DE REMATE\nFINCA 7777"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertGreater(len(results["finca"].evidence), 0)
        self.assertEqual(results["finca"].evidence[0]["source"], "text")
        self.assertEqual(results["finca"].evidence[0]["method"], "regex:finca")

    def test_all_fields_extracted(self):
        text = """
        AVISO DE REMATE
        Expediente N° 88888-2026
        FINCA 55555
        BASE B/.100,000.00
        FECHA DE REMATE: 30 DE SEPTIEMBRE DE 2026
        DEMANDANTE: CARLOS LOPEZ
        DEMANDADO: ANA MARTINEZ
        """
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        for field in self.parser.supported_fields:
            self.assertTrue(results[field].is_found, f"{field} should be FOUND")
            self.assertGreater(results[field].confidence, 0.5)

    def test_low_confidence_partial_match(self):
        text = "AVISO DE REMATE\nFINCA 1 2 3 4\nBASE: CIEN MIL"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["finca"].is_found)
        self.assertTrue(results["precio_base"].is_not_found)


class TestColombiaRemateParser(unittest.TestCase):
    def setUp(self):
        self.parser = ColombiaRemateParser()

    def test_country_and_type(self):
        self.assertEqual(self.parser.country, "CO")
        self.assertEqual(self.parser.document_type, "REMATE")

    def test_extract_matricula(self):
        text = "AVISO DE REMATE\nMATRÍCULA INMOBILIARIA N° 050-123456\nAVALÚO: $500,000,000"
        ctx = ParserContext(country="CO", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["finca"].is_found)
        self.assertIn("050", results["finca"].value)

    def test_extract_precio_base_co(self):
        text = "AVISO DE REMATE\nAVALÚO COMERCIAL: $350,000,000\nMATRÍCULA 050-789"
        ctx = ParserContext(country="CO", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["precio_base"].is_found)
        self.assertIn("350", results["precio_base"].value)

    def test_extract_demandante_co(self):
        text = "AVISO DE REMATE\nDEMANDANTE: PEDRO PABLO PEREZ\nRADICADO 2025-00123"
        ctx = ParserContext(country="CO", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["demandante"].is_found)
        self.assertIn("PEDRO", results["demandante"].value)

    def test_extract_expediente_co(self):
        text = "AVISO DE REMATE\nEXPEDIENTE N° 2025-00456\nMATRÍCULA 050-123"
        ctx = ParserContext(country="CO", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["expediente"].is_found)

    def test_extract_fecha_co(self):
        text = "AVISO DE REMATE\nFECHA DE REMATE: 20 DE DICIEMBRE DE 2026"
        ctx = ParserContext(country="CO", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["fecha_remate"].is_found)

    def test_not_found_co(self):
        text = "Texto sin información relevante"
        ctx = ParserContext(country="CO", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        for f in self.parser.supported_fields:
            self.assertTrue(results[f].is_not_found)


class TestParserRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = ParserRegistry()

    def test_register_and_get(self):
        parser = PanamaRemateParser()
        self.registry.register(parser)
        self.assertIsNotNone(self.registry.get("PA", "REMATE"))
        self.assertTrue(self.registry.has_parser("PA", "REMATE"))

    def test_get_nonexistent(self):
        self.assertIsNone(self.registry.get("XX", "UNKNOWN"))
        self.assertFalse(self.registry.has_parser("XX", "UNKNOWN"))

    def test_register_multiple(self):
        self.registry.register(PanamaRemateParser())
        self.registry.register(ColombiaRemateParser())
        self.assertEqual(self.registry.count, 2)

    def test_unregister(self):
        self.registry.register(PanamaRemateParser())
        self.assertTrue(self.registry.has_parser("PA", "REMATE"))
        self.registry.unregister("PA", "REMATE")
        self.assertFalse(self.registry.has_parser("PA", "REMATE"))

    def test_get_all(self):
        self.registry.register(PanamaRemateParser())
        self.registry.register(ColombiaRemateParser())
        self.assertEqual(len(self.registry.get_all()), 2)

    def test_case_insensitive(self):
        self.registry.register(PanamaRemateParser())
        self.assertTrue(self.registry.has_parser("pa", "remate"))
        self.assertIsNotNone(self.registry.get("Pa", "Remate"))


class TestParserFactory(unittest.TestCase):
    def setUp(self):
        self.factory = ParserFactory()

    def test_default_parsers_registered(self):
        self.assertTrue(self.factory.has_parser("PA", "REMATE"))
        self.assertTrue(self.factory.has_parser("CO", "REMATE"))

    def test_get_panama_parser(self):
        parser = self.factory.get_parser("PA", "REMATE")
        self.assertIsNotNone(parser)
        self.assertIsInstance(parser, PanamaRemateParser)

    def test_get_colombia_parser(self):
        parser = self.factory.get_parser("CO", "REMATE")
        self.assertIsNotNone(parser)
        self.assertIsInstance(parser, ColombiaRemateParser)

    def test_get_nonexistent(self):
        self.assertFalse(self.factory.has_parser("XX", "YYY"))
        self.assertIsNone(self.factory.get_parser("XX", "YYY"))

    def test_register_new_via_factory(self):
        class MockParser(ParserInterface):
            @property
            def country(self): return "MX"
            @property
            def document_type(self): return "TEST"
            @property
            def supported_fields(self): return ["test"]
            def parse(self, ctx): return {}
        self.factory.register_parser(MockParser())
        self.assertTrue(self.factory.has_parser("MX", "TEST"))

    def test_factory_registry(self):
        self.assertIsNotNone(self.factory.registry)
        self.assertEqual(self.factory.registry.count, 2)


class TestAIResolverInterface(unittest.TestCase):
    def test_interface_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            AIResolver()

    def test_concrete_resolver_can_be_created(self):
        class MockResolver(AIResolver):
            def resolve(self, field_name, context, previous_result=None):
                return ParseResult(field_name=field_name)
            def is_available(self): return False
            def provider_name(self): return "mock"
        r = MockResolver()
        self.assertFalse(r.is_available())
        self.assertEqual(r.provider_name(), "mock")

    def test_resolver_returns_parse_result(self):
        class MockResolver(AIResolver):
            def resolve(self, field_name, context, previous_result=None):
                r = ParseResult(field_name=field_name)
                r.set_found("ai_value", 0.6)
                return r
            def is_available(self): return True
            def provider_name(self): return "mock"
        r = MockResolver()
        ctx = ParserContext(text="test")
        result = r.resolve("finca", ctx)
        self.assertTrue(result.is_found)
        self.assertEqual(result.value, "ai_value")
        self.assertEqual(result.confidence, 0.6)


if __name__ == "__main__":
    unittest.main()
