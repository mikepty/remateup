"""
Tests with real-world text patterns from La Prensa (Panama) and SEJURE (Colombia).
Verifies parser accuracy against actual document formats.
"""

import unittest

from backend.app.v2.parser.factory import ParserFactory
from backend.app.v2.parser.context import ParserContext


class TestPanamaRealPatterns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.factory = ParserFactory()
        cls.parser = cls.factory.get_parser("PA", "REMATE")
        cls.assertIsNotNone(cls.parser, "PA REMATE parser must be registered")

    def test_expediente_with_n_and_dash(self):
        text = "AVISO DE REMATE\nEXPEDIENTE N° 32852-2026\nFINCA 514582\nBASE: B/.85,000.00"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["expediente"].is_found)
        self.assertIn("32852", results["expediente"].value)

    def test_expediente_with_colon(self):
        text = "AVISO DE REMATE\nExpediente: 15678-2026\nFinca 23456"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["expediente"].is_found)
        self.assertIn("15678", results["expediente"].value)

    def test_finca_with_n_keyword(self):
        text = "AVISO DE REMATE\nFINCA N° 90123\nBASE: B/.45,000.00"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["finca"].is_found)
        self.assertIn("90123", results["finca"].value)

    def test_finca_lowercase(self):
        text = "AVISO DE REMATE\nFinca 78901\nBASE: B/.120,000.00"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["finca"].is_found)
        self.assertIn("78901", results["finca"].value)

    def test_base_with_b_slash(self):
        text = "AVISO DE REMATE\nFINCA 514582\nBASE: B/.85,000.00"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["precio_base"].is_found)
        self.assertIn("85,000", results["precio_base"].value)

    def test_valor_base_instead_of_base(self):
        text = "AVISO DE REMATE\nFINCA 34567\nVALOR BASE: B/.200,000.00"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["precio_base"].is_found)
        self.assertIn("200,000", results["precio_base"].value)

    def test_base_without_b_slash(self):
        text = "AVISO DE REMATE\nFINCA 55555\nBASE: 30,000.00"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["precio_base"].is_found)
        self.assertIn("30,000", results["precio_base"].value)

    def test_fecha_remate_full(self):
        text = "AVISO DE REMATE\nFECHA DE REMATE: 15 DE SEPTIEMBRE DE 2026"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["fecha_remate"].is_found)
        self.assertIn("SEPTIEMBRE", results["fecha_remate"].value)

    def test_fecha_probable(self):
        text = "AVISO DE REMATE\nFECHA PROBABLE DE REMATE: 22 DE OCTUBRE DE 2026"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["fecha_remate"].is_found)
        self.assertIn("OCTUBRE", results["fecha_remate"].value)

    def test_demandante_company_name(self):
        text = "AVISO DE REMATE\nDEMANDANTE: PROMOTORA STAGE TOWERS S.A.\nFINCA 514582"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["demandante"].is_found)
        self.assertIn("PROMOTORA", results["demandante"].value)

    def test_demandado_with_appellidos(self):
        text = "AVISO DE REMATE\nDEMANDADO: EINAR GONZALEZ BATISTA\nFINCA 514582"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["demandado"].is_found)
        self.assertIn("GONZALEZ", results["demandado"].value)

    def test_full_aviso_all_fields(self):
        text = """
        AVISO DE REMATE
        EXPEDIENTE N° 32852-2026
        JUZGADO DECIMO DE CIRCUITO
        LA FINCA N° 514582
        BASE: B/.85,000.00
        FECHA DE REMATE: 15 DE SEPTIEMBRE DE 2026
        DEMANDANTE: PROMOTORA STAGE TOWERS S.A.
        DEMANDADO: EINAR GONZALEZ BATISTA
        """
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        for field in self.parser.supported_fields:
            self.assertTrue(results[field].is_found, f"{field} should be FOUND in full aviso")

    def test_edicto_emplazatorio_no_remate_fields(self):
        text = "EDICTO EMPLAZATORIO\nExpediente N° 77777-2026\nFINCA NO APLICA"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        # expediente can still be found but remate-specific fields should not
        self.assertTrue(results["expediente"].is_found)
        self.assertFalse(results["finca"].is_found)  # "NO APLICA" is not a valid finca number
        self.assertTrue(results["precio_base"].is_not_found)
        self.assertTrue(results["fecha_remate"].is_not_found)

    def test_incomplete_aviso_missing_fields(self):
        text = "AVISO DE REMATE\nEXPEDIENTE: 99999-2026\nFINCA 55555\nBASE: B/.30,000.00"
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["expediente"].is_found)
        self.assertTrue(results["finca"].is_found)
        self.assertTrue(results["precio_base"].is_found)
        self.assertTrue(results["fecha_remate"].is_not_found)
        self.assertTrue(results["demandante"].is_not_found)
        self.assertTrue(results["demandado"].is_not_found)


class TestColombiaRealPatterns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.factory = ParserFactory()
        cls.parser = cls.factory.get_parser("CO", "REMATE")
        cls.assertIsNotNone(cls.parser, "CO REMATE parser must be registered")

    def test_matricula_inmobiliaria(self):
        text = "AVISO DE REMATE\nMATRÍCULA INMOBILIARIA N° 050-123456\nAVALÚO: $500,000,000"
        ctx = ParserContext(country="CO", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["finca"].is_found)
        self.assertIn("050-123456", results["finca"].value)

    def test_matricula_without_accent(self):
        text = "AVISO DE REMATE\nMATRICULA INMOBILIARIA No. 050-789012\nAVALUO: $350,000,000"
        ctx = ParserContext(country="CO", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["finca"].is_found)
        self.assertIn("050-789012", results["finca"].value)

    def test_avaluo_comercial(self):
        text = "AVISO DE REMATE\nAVALÚO COMERCIAL: $500,000,000\nMATRÍCULA 050-123456"
        ctx = ParserContext(country="CO", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["precio_base"].is_found)
        self.assertIn("500", results["precio_base"].value)

    def test_avaluo_simple(self):
        text = "AVISO DE REMATE\nAVALUO: $350,000,000\nMATRICULA 050-789012"
        ctx = ParserContext(country="CO", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["precio_base"].is_found)

    def test_expediente_co_pattern(self):
        text = "AVISO DE REMATE\nEXPEDIENTE N° 2025-00456\nMATRÍCULA 050-123456"
        ctx = ParserContext(country="CO", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["expediente"].is_found)

    def test_expediente_radicado(self):
        text = "AVISO DE REMATE\nRADICADO: 2026-00789\nMATRICULA 050-789012"
        ctx = ParserContext(country="CO", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["expediente"].is_found)

    def test_fecha_remate_co(self):
        text = "AVISO DE REMATE\nFECHA DE REMATE: 20 DE DICIEMBRE DE 2026\nMATRÍCULA 050-123456"
        ctx = ParserContext(country="CO", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        self.assertTrue(results["fecha_remate"].is_found)

    def test_full_co_aviso(self):
        text = """
        AVISO DE REMATE
        EXPEDIENTE N° 2025-00456
        MATRÍCULA INMOBILIARIA N° 050-123456
        AVALÚO COMERCIAL: $500,000,000
        FECHA DE REMATE: 20 DE DICIEMBRE DE 2026
        DEMANDANTE: BANCO DE BOGOTA
        DEMANDADO: PEDRO PABLO PEREZ LOPEZ
        FIANZA DEL POSTOR: 40%
        PORCENTAJE MÍNIMO DE LA POSTURA: 70%
        """
        ctx = ParserContext(country="CO", document_type="REMATE", text=text)
        results = self.parser.parse(ctx)
        for field in self.parser.supported_fields:
            self.assertTrue(results[field].is_found, f"{field} should be FOUND in full CO aviso")


if __name__ == "__main__":
    unittest.main()
