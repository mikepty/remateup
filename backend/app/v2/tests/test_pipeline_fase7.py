"""FASE 7 integration tests — PipelineRunner, Normalization, Confidence, Certification."""

import unittest
from unittest.mock import MagicMock, patch

from backend.app.v2.pipeline.runner import PipelineRunner, StageResult, PIPELINE_VERSION
from backend.app.v2.normalization.normalizer import FieldNormalizer, FIELD_NORMALIZERS
from backend.app.v2.normalization.dates import DateNormalizer
from backend.app.v2.normalization.currency import CurrencyNormalizer
from backend.app.v2.normalization.numbers import NumberNormalizer
from backend.app.v2.normalization.names import NameNormalizer
from backend.app.v2.normalization.locations import LocationNormalizer
from backend.app.v2.normalization.text import TextNormalizer
from backend.app.v2.confidence.final import FinalConfidenceCalculator
from backend.app.v2.confidence.ocr import OCRConfidenceScorer
from backend.app.v2.confidence.parser import ParserConfidenceScorer
from backend.app.v2.confidence.segment import SegmentationConfidenceScorer
from backend.app.v2.confidence.normalization import NormalizationConfidenceScorer
from backend.app.v2.confidence.knowledge import KnowledgeConfidenceAdjuster
from backend.app.v2.certification.models import CertDocument, CertAviso, CertField, CertDecision
from backend.app.v2.certification.certifier import Certifier
from backend.app.v2.certification.report import ProductionReportGenerator


class TestStageResult(unittest.TestCase):
    def test_init(self):
        s = StageResult("test")
        self.assertEqual(s.name, "test")
        self.assertEqual(s.status, "pending")
        self.assertEqual(s.duration_ms, 0.0)
        self.assertEqual(s.warnings, [])
        self.assertEqual(s.errors, [])

    def test_to_dict(self):
        s = StageResult("test")
        s.status = "success"
        s.duration_ms = 10.5
        d = s.to_dict()
        self.assertEqual(d["status"], "success")
        self.assertEqual(d["duration_ms"], 10.5)
        self.assertEqual(d["warnings"], [])


class TestDateNormalizer(unittest.TestCase):
    def setUp(self):
        self.norm = DateNormalizer()

    def test_iso_date(self):
        result = self.norm.normalize("2024-07-15")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized"], "2024-07-15")
        self.assertEqual(result["format"], "ISO")

    def test_spanish_date(self):
        result = self.norm.normalize("15 DE JULIO DE 2026")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized"], "2026-07-15")
        self.assertEqual(result["format"], "SPANISH")

    def test_dot_date(self):
        result = self.norm.normalize("15.07.2026")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized"], "2026-07-15")

    def test_slash_date(self):
        result = self.norm.normalize("15/07/2026")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized"], "2026-07-15")

    def test_invalid_date(self):
        result = self.norm.normalize("99-99-9999")
        self.assertFalse(result["success"])

    def test_empty(self):
        result = self.norm.normalize("")
        self.assertFalse(result["success"])


class TestCurrencyNormalizer(unittest.TestCase):
    def setUp(self):
        self.norm = CurrencyNormalizer()

    def test_simple_amount(self):
        result = self.norm.normalize("$100,000")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized"], 100000.0)

    def test_b_format(self):
        result = self.norm.normalize("B/. 20,000")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized"], 20000.0)

    def test_usd(self):
        result = self.norm.normalize("USD 1,500.00")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized"], 1500.0)
        self.assertEqual(result["currency"], "USD")

    def test_colombian_format(self):
        result = self.norm.normalize("$181.080.000,00")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized"], 181080000.0)

    def test_empty(self):
        result = self.norm.normalize("")
        self.assertFalse(result["success"])


class TestNumberNormalizer(unittest.TestCase):
    def setUp(self):
        self.norm = NumberNormalizer()

    def test_simple(self):
        result = self.norm.normalize("82699")
        self.assertTrue(result["success"])
        self.assertEqual(result["float"], 82699.0)

    def test_decimal(self):
        result = self.norm.normalize("40.5")
        self.assertTrue(result["success"])
        self.assertEqual(result["float"], 40.5)

    def test_comma_decimal(self):
        result = self.norm.normalize("40,5")
        self.assertTrue(result["success"])
        self.assertEqual(result["float"], 40.5)

    def test_thousands(self):
        result = self.norm.normalize("1,000,000")
        self.assertTrue(result["success"])
        self.assertEqual(result["float"], 1000000.0)

    def test_empty(self):
        result = self.norm.normalize("")
        self.assertFalse(result["success"])


class TestNameNormalizer(unittest.TestCase):
    def setUp(self):
        self.norm = NameNormalizer()

    def test_simple_name(self):
        result = self.norm.normalize("JUAN PEREZ")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized"], "Juan Perez")

    def test_comma_name(self):
        result = self.norm.normalize("PEREZ, JUAN")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized"], "Juan Perez")

    def test_legal_entity(self):
        result = self.norm.normalize("FINANCIERA FAMILIAR, S.A.")
        self.assertTrue(result["success"])

    def test_extract_parts(self):
        parts = self.norm.extract_parts("Juan Perez Gomez")
        self.assertEqual(parts["first_name"], "Juan")
        self.assertEqual(parts["last_name"], "Gomez")


class TestLocationNormalizer(unittest.TestCase):
    def setUp(self):
        self.norm = LocationNormalizer()

    def test_province_panama(self):
        result = self.norm.normalize("PANAMA")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized_province"], "Panamá")

    def test_province_colombia(self):
        result = self.norm.normalize("ANTIOQUIA")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized_province"], "Antioquia")

    def test_city(self):
        result = self.norm.normalize("BOGOTA")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized_city"], "Bogota")


class TestTextNormalizer(unittest.TestCase):
    def setUp(self):
        self.norm = TextNormalizer()

    def test_clean_whitespace(self):
        result = self.norm.normalize("  Hola    Mundo  ")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized"], "Hola Mundo")

    def test_clean_ocr_artifacts(self):
        text = "Hola\x00Mundo"
        result = self.norm.normalize(text)
        self.assertNotIn("\x00", result["normalized"])

    def test_strip_quotes(self):
        text = '"Hola Mundo"'
        result = self.norm.normalize(text)
        self.assertEqual(result["normalized"], "Hola Mundo")


class TestFieldNormalizer(unittest.TestCase):
    def setUp(self):
        self.norm = FieldNormalizer()

    def test_normalize_fecha(self):
        result = self.norm.normalize_field("fecha_remate", "15 DE JULIO DE 2026")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized"], "2026-07-15")

    def test_normalize_currency(self):
        result = self.norm.normalize_field("precio_base", "$100,000")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized"], 100000.0)

    def test_normalize_number(self):
        result = self.norm.normalize_field("finca", "82699")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized"], "82699")

    def test_normalize_name(self):
        result = self.norm.normalize_field("demandante", "JUAN PEREZ")
        self.assertTrue(result["success"])
        self.assertEqual(result["normalized"], "Juan Perez")

    def test_normalize_unknown_field(self):
        result = self.norm.normalize_field("unknown_field", "test value")
        self.assertTrue(result["success"])

    def test_normalize_all(self):
        fields = {
            "fecha_remate": {"value": "15 DE JULIO DE 2026", "confidence": 0.95},
            "precio_base": {"value": "$100,000", "confidence": 0.95},
            "finca": {"value": "82699", "confidence": 0.95},
        }
        result = self.norm.normalize_all(fields)
        self.assertEqual(result["fecha_remate"]["normalized"], "2026-07-15")
        self.assertEqual(result["precio_base"]["normalized"], 100000.0)
        self.assertEqual(result["finca"]["normalized"], "82699")


class TestOCRConfidenceScorer(unittest.TestCase):
    def test_score(self):
        scorer = OCRConfidenceScorer()
        ocr_doc = {"pages": [{"words": [{"confidence": 0.9}, {"confidence": 0.8}]}]}
        score = scorer.score(ocr_doc)
        self.assertAlmostEqual(score, 0.85, places=2)

    def test_empty(self):
        scorer = OCRConfidenceScorer()
        self.assertEqual(scorer.score({}), 0.0)


class TestParserConfidenceScorer(unittest.TestCase):
    def test_score(self):
        scorer = ParserConfidenceScorer()
        result = {"fields": {
            "expediente": {"confidence": 0.95, "status": "FOUND"},
            "finca": {"confidence": 0.95, "status": "FOUND"},
        }}
        score = scorer.score(result)
        self.assertAlmostEqual(score, 0.95, places=2)

    def test_per_field(self):
        scorer = ParserConfidenceScorer()
        fields = {"expediente": {"confidence": 0.95, "status": "FOUND"},
                  "finca": {"confidence": 0.5, "status": "REQUIRES_REVIEW"}}
        result = scorer.per_field_confidence(fields)
        self.assertEqual(result["expediente"], 0.95)
        self.assertEqual(result["finca"], 0.0)


class TestSegmentationConfidenceScorer(unittest.TestCase):
    def test_score(self):
        scorer = SegmentationConfidenceScorer()
        result = {"avisos": [{"confidence": 0.9}, {"confidence": 0.8}]}
        score = scorer.score(result)
        self.assertAlmostEqual(score, 0.85, places=2)


class TestNormalizationConfidenceScorer(unittest.TestCase):
    def test_score(self):
        scorer = NormalizationConfidenceScorer()
        result = {"fecha": {"success": True}, "base": {"success": False}}
        score = scorer.score(result)
        self.assertAlmostEqual(score, 0.5, places=2)


class TestKnowledgeConfidenceAdjuster(unittest.TestCase):
    def test_adjust_with_evidence(self):
        adj = KnowledgeConfidenceAdjuster()
        evidence = [{"source": "knowledge", "confidence": 0.9}]
        result = adj.adjust("expediente", 0.8, evidence)
        self.assertGreater(result, 0.8)

    def test_adjust_without_evidence(self):
        adj = KnowledgeConfidenceAdjuster()
        result = adj.adjust("expediente", 0.8, [])
        self.assertEqual(result, 0.8)


class TestFinalConfidenceCalculator(unittest.TestCase):
    def test_calculate(self):
        calc = FinalConfidenceCalculator()
        scores = {"ocr": 0.9, "parser": 0.8, "segmentation": 0.7,
                  "normalization": 1.0, "validation": 0.9, "knowledge": 0.8}
        result = calc.calculate(scores)
        self.assertGreater(result, 0.7)
        self.assertLessEqual(result, 1.0)

    def test_per_field(self):
        calc = FinalConfidenceCalculator()
        field_scores = {
            "expediente": {"ocr": 0.9, "parser": 0.95, "segmentation": 0.8,
                          "normalization": 1.0, "validation": 1.0, "knowledge": 0.9},
        }
        result = calc.per_field_final(field_scores)
        self.assertIn("expediente", result)
        self.assertGreater(result["expediente"], 0.7)

    def test_build_field_confidence(self):
        calc = FinalConfidenceCalculator()
        result = calc.build_field_confidence(
            field_name="expediente",
            parser_confidence=0.95,
            ocr_confidence=0.85,
            normalization_result={"success": True},
            knowledge_boost=0.1,
            validator_passed=True,
        )
        self.assertIn("confidence", result)
        self.assertIn("confidence_reason", result)
        self.assertIn("confidence_sources", result)
        self.assertGreater(result["confidence"], 0.7)


class TestCertifier(unittest.TestCase):
    def test_build_certification_valid(self):
        certifier = Certifier()
        pipeline_result = {
            "document_id": "test_001",
            "fields": {
                "expediente": {"value": "123/2024", "confidence": 0.95, "status": "FOUND",
                               "evidence": [], "source": "parser", "normalization": {"success": True}},
            },
            "validation": {
                "decision": "VALID",
                "score": 0.85,
                "header_detected": "AVISO DE REMATE",
                "header_valid": True,
                "inconsistencies": [],
                "duplicate_info": {"level": "UNIQUE", "matched_on": [], "matched_notice_id": None, "similarity": 0.0},
                "rules_applied": [{"rule_name": "valid_header", "passed": True, "weight": 0.25}],
                "rules_failed": [],
            },
            "stages": {"validation": {"present": ["expediente"], "missing": []}},
            "total_time_ms": 1000,
            "errors": [],
        }
        doc = certifier.build_certification("test_001", "newspaper_images", "PA", pipeline_result)
        self.assertEqual(doc.document_id, "test_001")
        self.assertEqual(len(doc.all_avisos), 1)
        self.assertEqual(doc.all_avisos[0].decision, CertDecision.VALID)
        self.assertEqual(doc.valid_count, 1)

    def test_build_certification_invalid(self):
        certifier = Certifier()
        pipeline_result = {
            "document_id": "test_002",
            "fields": {},
            "validation": {"decision": "INVALID", "score": 0.2},
            "stages": {"validation": {"present": [], "missing": []}},
            "total_time_ms": 500,
            "errors": [],
        }
        doc = certifier.build_certification("test_002", "pdf_tabular", "CO", pipeline_result)
        self.assertEqual(doc.all_avisos[0].decision, CertDecision.INVALID)
        self.assertEqual(doc.invalid_count, 1)


class TestProductionReportGenerator(unittest.TestCase):
    def test_generate(self):
        gen = ProductionReportGenerator()
        doc = CertDocument(
            document_id="test_001",
            country="PA",
            all_avisos=[
                CertAviso(id="a1", decision=CertDecision.VALID, score=0.9),
                CertAviso(id="a2", decision=CertDecision.INCOMPLETE, score=0.5),
            ],
            total_time_ms=1000,
        )
        report = gen.generate([doc])
        self.assertEqual(report["documents_processed"], 1)
        self.assertEqual(report["total_avisos"], 2)
        self.assertEqual(report["aviso_decisions"]["valid"], 1)
        self.assertEqual(report["aviso_decisions"]["incomplete"], 1)
        self.assertIn("performance", report)
        self.assertIn("coverage", report)


class TestPipelineRunner(unittest.TestCase):
    def test_init(self):
        runner = PipelineRunner()
        self.assertIsNotNone(runner)

    def test_stage_result(self):
        s = StageResult("test")
        s.status = "success"
        s.duration_ms = 10.0
        self.assertEqual(s.name, "test")
        self.assertEqual(s.status, "success")

    def test_version(self):
        self.assertEqual(PIPELINE_VERSION, "7.0.0")


class TestNoMixingBetweenAvisos(unittest.TestCase):
    """Regresion del problema #5 (campos mezclados): antes, el parser
    mezclaba en un solo dict los campos de TODOS los avisos de un
    documento (expediente del aviso 1 + finca del aviso 2, etc, primer
    valor encontrado ganaba y el resto se perdia silenciosamente)."""

    def _run_with_two_avisos(self):
        from backend.app.v2.segmenter.models import CompleteAviso

        aviso1_text = ("AVISO DE REMATE\nEXPEDIENTE N\u00b0 11111-2026\n"
                       "AVAL\u00daO COMERCIAL: $50,000.00")
        aviso2_text = ("AVISO DE REMATE\nEXPEDIENTE N\u00b0 22222-2026\n"
                       "FINCA 999888")
        fake_avisos = [MagicMock(position="top"), MagicMock(position="bottom")]

        runner = PipelineRunner()
        fake_fragment = MagicMock()
        fake_fragment.path = "fake_top.jpg"
        fake_page_in = MagicMock()
        fake_page_in.fragments = [fake_fragment]
        fake_ocr_page = MagicMock()
        fake_ocr_doc = MagicMock()
        fake_ocr_doc.pages = [fake_ocr_page]

        with patch.object(runner._assembly, "assemble",
                           return_value=MagicMock(pages=[fake_page_in])), \
             patch.object(runner._ocr, "process_image", return_value=fake_ocr_doc), \
             patch("backend.app.v2.document.stitching.PageStitcher.stitch_ocr_pages",
                   return_value=[MagicMock()]), \
             patch.object(runner._layout, "segment", return_value=fake_avisos), \
             patch.object(runner._continuity, "detect_continuity",
                           return_value=[CompleteAviso(text=aviso1_text),
                                         CompleteAviso(text=aviso2_text)]):
            result = runner.process(["fake_top.jpg", "fake_bottom.jpg"],
                                     country="PA", document_id="doc1")
        return result

    def test_each_aviso_keeps_its_own_expediente(self):
        result = self._run_with_two_avisos()
        avisos = result["final_json"]["avisos"]
        self.assertEqual(len(avisos), 2)
        exp0 = avisos[0]["fields"].get("expediente", {}).get("value", "")
        exp1 = avisos[1]["fields"].get("expediente", {}).get("value", "")
        self.assertIn("11111", exp0)
        self.assertIn("22222", exp1)

    def test_finca_not_leaked_into_first_aviso(self):
        # El aviso 1 no tiene "FINCA" en su texto: no debe aparecer en sus
        # campos aunque el aviso 2 si la tenga.
        result = self._run_with_two_avisos()
        avisos = result["final_json"]["avisos"]
        self.assertNotIn("finca", avisos[0]["fields"])
        self.assertIn("finca", avisos[1]["fields"])

    def test_each_aviso_gets_its_own_descripcion(self):
        result = self._run_with_two_avisos()
        avisos = result["final_json"]["avisos"]
        d0 = avisos[0]["fields"]["descripcion_completa"]["value"]
        d1 = avisos[1]["fields"]["descripcion_completa"]["value"]
        self.assertIn("11111", d0)
        self.assertNotIn("22222", d0)
        self.assertIn("22222", d1)
        self.assertNotIn("11111", d1)

    def test_flat_fields_dict_kept_for_backward_compatibility(self):
        # result["fields"] (el dict plano de siempre) sigue existiendo con
        # el comportamiento anterior (primer aviso encontrado gana), para
        # no romper a quien ya lo consume.
        result = self._run_with_two_avisos()
        self.assertIn("expediente", result["fields"])


class TestPartialOCRDetection(unittest.TestCase):
    """Problema #7: si falta la mitad de una página (imagen impar sin
    pareja), no debe certificarse como si la página estuviera completa."""

    def test_partial_page_forces_incomplete_decision(self):
        from backend.app.v2.segmenter.models import CompleteAviso
        from backend.app.v2.document.stitching import StitchedPage, FragmentMapping
        from backend.app.v2.validator.models import Decision

        runner = PipelineRunner()
        fake_fragment = MagicMock()
        fake_fragment.path = "fake_top.jpg"
        fake_page_in = MagicMock()
        fake_page_in.fragments = [fake_fragment]
        fake_ocr_page = MagicMock()
        fake_ocr_doc = MagicMock()
        fake_ocr_doc.pages = [fake_ocr_page]

        partial_stitched = StitchedPage(
            page_number=1,
            fragment_mapping=FragmentMapping(page_number=1, top_height=0, bottom_height=3000),
        )
        fake_avisos = [MagicMock(position="top")]

        with patch.object(runner._assembly, "assemble",
                           return_value=MagicMock(pages=[fake_page_in])), \
             patch.object(runner._ocr, "process_image", return_value=fake_ocr_doc), \
             patch("backend.app.v2.document.stitching.PageStitcher.stitch_ocr_pages",
                   return_value=[partial_stitched]), \
             patch.object(runner._layout, "segment", return_value=fake_avisos), \
             patch.object(runner._continuity, "detect_continuity",
                           return_value=[CompleteAviso(text="AVISO DE REMATE\nEXPEDIENTE N\u00b0 1")]):
            result = runner.process(["fake_top.jpg"], country="PA", document_id="doc1")

        self.assertTrue(result["metrics"].get("ocr_parcial_detectado"))
        self.assertEqual(result["validation"]["decision"], Decision.INCOMPLETE.value)
        seg_warnings = result["stages"]["segmentation"]["warnings"]
        self.assertTrue(any("incompleta" in w for w in seg_warnings))

    def test_complete_page_not_marked_incomplete(self):
        # Contraprueba: una página completa (sin partial_pages) no debe
        # forzar INCOMPLETE por esta lógica.
        from backend.app.v2.segmenter.models import CompleteAviso
        from backend.app.v2.document.stitching import StitchedPage, FragmentMapping

        runner = PipelineRunner()
        fake_fragment = MagicMock()
        fake_fragment.path = "fake_top.jpg"
        fake_page_in = MagicMock()
        fake_page_in.fragments = [fake_fragment]
        fake_ocr_page = MagicMock()
        fake_ocr_doc = MagicMock()
        fake_ocr_doc.pages = [fake_ocr_page]

        complete_stitched = StitchedPage(
            page_number=1,
            fragment_mapping=FragmentMapping(page_number=1, top_height=3000, bottom_height=3000),
        )
        fake_avisos = [MagicMock(position="top")]

        with patch.object(runner._assembly, "assemble",
                           return_value=MagicMock(pages=[fake_page_in])), \
             patch.object(runner._ocr, "process_image", return_value=fake_ocr_doc), \
             patch("backend.app.v2.document.stitching.PageStitcher.stitch_ocr_pages",
                   return_value=[complete_stitched]), \
             patch.object(runner._layout, "segment", return_value=fake_avisos), \
             patch.object(runner._continuity, "detect_continuity",
                           return_value=[CompleteAviso(text="AVISO DE REMATE\nEXPEDIENTE N\u00b0 1")]):
            result = runner.process(["fake_top.jpg"], country="PA", document_id="doc1")

        self.assertNotIn("ocr_parcial_detectado", result["metrics"])


class TestAvisoTextExtraction(unittest.TestCase):
    """Regresión: el parser/knowledge/validator recibían str(aviso) (el repr
    del dataclass) en vez del texto real para todo aviso que pasó por el
    motor de continuidad (CompleteAviso no tiene .full_text, solo .text)."""

    def test_complete_aviso_uses_text_attribute_not_repr(self):
        from backend.app.v2.pipeline.runner import _aviso_text
        from backend.app.v2.segmenter.models import CompleteAviso

        aviso = CompleteAviso(text="EXPEDIENTE N 12345 AVALUO COMERCIAL: $100.000.00")
        extracted = _aviso_text(aviso)
        self.assertEqual(extracted, "EXPEDIENTE N 12345 AVALUO COMERCIAL: $100.000.00")
        self.assertNotIn("CompleteAviso(", extracted)

    def test_detected_aviso_still_uses_full_text(self):
        from backend.app.v2.pipeline.runner import _aviso_text
        from backend.app.v2.segmenter.models import DetectedAviso, DetectedSection

        aviso = DetectedAviso(
            header_text="AVISO DE REMATE",
            sections=[DetectedSection(text="EXPEDIENTE N 12345")],
        )
        extracted = _aviso_text(aviso)
        self.assertEqual(extracted, "AVISO DE REMATE\nEXPEDIENTE N 12345")

    def test_parser_stage_finds_fields_in_complete_aviso_text(self):
        # Antes de este fix, el parser real recibía el repr de CompleteAviso
        # (vía _aviso_text) y no encontraba ningún campo. Se prueba con el
        # mismo helper que usa pipeline/runner.py en las etapas de parser,
        # knowledge y validator.
        from backend.app.v2.pipeline.runner import _aviso_text
        from backend.app.v2.segmenter.models import CompleteAviso
        from backend.app.v2.parser.factory import ParserFactory
        from backend.app.v2.parser.context import ParserContext

        aviso = CompleteAviso(
            text="AVISO DE REMATE\nEXPEDIENTE N\u00b0 32852-2026\n"
                 "AVAL\u00daO COMERCIAL: $85,000.00")
        text = _aviso_text(aviso)
        parser = ParserFactory().get_parser("PA", "REMATE")
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        results = parser.parse(ctx)
        self.assertTrue(results["expediente"].is_found)
        self.assertTrue(results["precio_base"].is_found)


if __name__ == "__main__":
    unittest.main()
