import unittest

from backend.app.v2.segmenter.models import (
    AvisoFragment, CompleteAviso, DetectedBlock, DetectedAviso, BoundingBox,
    DetectedSection,
)
from backend.app.v2.segmenter.continuity import ContinuityEngine
from backend.app.v2.document.models import SectionType


class TestAvisoFragmentModels(unittest.TestCase):
    def test_create_fragment(self):
        f = AvisoFragment(source_image="top.jpg", page_number=1, position="top")
        self.assertEqual(f.source_image, "top.jpg")
        self.assertEqual(f.position, "top")
        self.assertFalse(f.ends_incomplete)
        self.assertFalse(f.has_header)

    def test_fragment_to_dict(self):
        f = AvisoFragment(source_image="img.png", confidence=0.95, has_header=True)
        d = f.to_dict()
        self.assertEqual(d["source_image"], "img.png")
        self.assertTrue(d["has_header"])

    def test_fragment_with_blocks(self):
        b = DetectedBlock(text="test", bbox=BoundingBox(0, 0, 100, 50))
        f = AvisoFragment(blocks=[b], bbox=BoundingBox(0, 0, 100, 50))
        self.assertEqual(len(f.blocks), 1)


class TestCompleteAvisoModels(unittest.TestCase):
    def test_single_fragment(self):
        f = AvisoFragment(source_image="img.png")
        aviso = CompleteAviso(fragments=[f], text="test")
        self.assertFalse(aviso.is_reconstructed)
        self.assertEqual(aviso.fragment_count, 1)

    def test_reconstructed(self):
        f1 = AvisoFragment(source_image="top.jpg", position="top")
        f2 = AvisoFragment(source_image="bottom.jpg", position="bottom")
        aviso = CompleteAviso(fragments=[f1, f2], text="full text")
        self.assertTrue(aviso.is_reconstructed)
        self.assertEqual(aviso.fragment_count, 2)
        self.assertEqual(len(aviso.source_images), 2)

    def test_source_images(self):
        f1 = AvisoFragment(source_image="img1.png")
        f2 = AvisoFragment(source_image="img2.png")
        aviso = CompleteAviso(fragments=[f1, f2])
        self.assertIn("img1.png", aviso.source_images)
        self.assertIn("img2.png", aviso.source_images)

    def test_to_dict(self):
        f1 = AvisoFragment(source_image="top.jpg", position="top")
        f2 = AvisoFragment(source_image="bottom.jpg", position="bottom")
        aviso = CompleteAviso(fragments=[f1, f2], text="texto del aviso",
                               confidence=0.95, aviso_type="continuacion_aviso",
                               continuity_signals=["hyphenated_word"])
        d = aviso.to_dict()
        self.assertTrue(d["is_reconstructed"])
        self.assertEqual(d["aviso_type"], "continuacion_aviso")
        self.assertIn("hyphenated_word", d["continuity_signals"])


class TestContinuityEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ContinuityEngine()

    def test_empty_fragments(self):
        result = self.engine.detect_continuity([])
        self.assertEqual(result, [])

    def test_single_top_fragment(self):
        f = AvisoFragment(source_image="top.jpg", position="top",
                          bbox=BoundingBox(0, 0, 500, 500), confidence=0.95,
                          has_header=True)
        result = self.engine.detect_continuity([f])
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].is_reconstructed)

    def test_no_continuation_new_header_in_bottom(self):
        top = AvisoFragment(source_image="top.jpg", position="top",
                            bbox=BoundingBox(0, 0, 500, 400), confidence=0.9,
                            has_header=True, trailing_text="texto del aviso superior",
                            leading_text="texto del aviso superior")
        bottom = AvisoFragment(source_image="bottom.jpg", position="bottom",
                               bbox=BoundingBox(0, 500, 500, 1000), confidence=0.9,
                               has_header=True, trailing_text="AVISO DE REMATE",
                               leading_text="AVISO DE REMATE")
        result = self.engine.detect_continuity([top, bottom])
        self.assertEqual(len(result), 2)
        self.assertFalse(result[0].is_reconstructed)
        self.assertFalse(result[1].is_reconstructed)

    def test_continuation_with_hyphen(self):
        top = AvisoFragment(source_image="top.jpg", position="top",
                            bbox=BoundingBox(0, 0, 500, 400), confidence=0.9,
                            has_header=True, ends_with_hyphen=True,
                            trailing_text="texto corta-",
                            leading_text="texto corta-")
        bottom = AvisoFragment(source_image="bottom.jpg", position="bottom",
                               bbox=BoundingBox(0, 400, 500, 800), confidence=0.85,
                               has_header=False, leading_text="do por el guion",
                               trailing_text="do por el guion")
        result = self.engine.detect_continuity([top, bottom])
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].is_reconstructed)
        self.assertIn("hyphenated_word", result[0].continuity_signals)
        self.assertEqual(result[0].fragment_count, 2)

    def test_continuation_lowercase_start(self):
        top = AvisoFragment(source_image="top.jpg", position="top",
                            bbox=BoundingBox(0, 0, 500, 300), confidence=0.9,
                            has_header=True, ends_incomplete=True,
                            trailing_text="EL JUZGADO PRIMERO DE",
                            leading_text="EL JUZGADO PRIMERO DE")
        bottom = AvisoFragment(source_image="bottom.jpg", position="bottom",
                               bbox=BoundingBox(0, 300, 500, 600), confidence=0.85,
                               has_header=False, leading_text="panamá hace saber",
                               trailing_text="panamá hace saber")
        result = self.engine.detect_continuity([top, bottom])
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].is_reconstructed)
        self.assertIn("lowercase_start", result[0].continuity_signals)

    def test_continuation_column_aligned(self):
        top = AvisoFragment(source_image="top.jpg", position="top",
                            bbox=BoundingBox(100, 0, 400, 300), confidence=0.9,
                            has_header=True, ends_incomplete=True,
                            trailing_text="continúa en la",
                            leading_text="continúa en la")
        bottom = AvisoFragment(source_image="bottom.jpg", position="bottom",
                               bbox=BoundingBox(100, 300, 400, 600), confidence=0.85,
                               has_header=False, leading_text="siguiente imagen",
                               trailing_text="siguiente imagen")
        result = self.engine.detect_continuity([top, bottom])
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].is_reconstructed)
        self.assertIn("column_alignment", result[0].continuity_signals)

    def test_no_continuation_different_columns(self):
        top = AvisoFragment(source_image="top.jpg", position="top",
                            bbox=BoundingBox(0, 0, 300, 300), confidence=0.9,
                            has_header=True,
                            trailing_text="aviso en columna izquierda",
                            leading_text="aviso en columna izquierda")
        bottom = AvisoFragment(source_image="bottom.jpg", position="bottom",
                               bbox=BoundingBox(600, 300, 900, 600), confidence=0.9,
                               has_header=True, trailing_text="AVISO DE REMATE",
                               leading_text="AVISO DE REMATE")
        result = self.engine.detect_continuity([top, bottom])
        self.assertEqual(len(result), 2)

    def test_label_value_continuity(self):
        top = AvisoFragment(source_image="top.jpg", position="top",
                            bbox=BoundingBox(0, 0, 500, 300), confidence=0.9,
                            has_header=True,
                            trailing_text="FINCA N° 30269",
                            leading_text="FINCA N° 30269")
        bottom = AvisoFragment(source_image="bottom.jpg", position="bottom",
                               bbox=BoundingBox(0, 300, 500, 600), confidence=0.85,
                               has_header=False, leading_text="Base: $150,000",
                               trailing_text="Base: $150,000")
        result = self.engine.detect_continuity([top, bottom])
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].is_reconstructed)

    def test_build_fragment_from_aviso(self):
        aviso = DetectedAviso(
            header_text="AVISO DE REMATE",
            sections=[DetectedSection(section_type=SectionType.HEADER, text="AVISO DE REMATE")],
            bbox=BoundingBox(0, 0, 500, 200), confidence=0.95,
        )
        fragment = self.engine.build_fragment_from_aviso(
            aviso, source_image="test.jpg", page_number=1, position="top"
        )
        self.assertEqual(fragment.source_image, "test.jpg")
        self.assertEqual(fragment.position, "top")
        self.assertTrue(fragment.has_header)
        self.assertEqual(fragment.confidence, 0.95)

    def test_continuity_score(self):
        top = AvisoFragment(bbox=BoundingBox(0, 0, 500, 300), confidence=0.9,
                            has_header=True, ends_with_hyphen=True)
        bottom = AvisoFragment(bbox=BoundingBox(0, 300, 500, 600), confidence=0.85,
                               has_header=False)
        score = self.engine._continuity_score(top, bottom)
        self.assertGreater(score, 0)

    def test_continuity_score_bottom_has_header(self):
        top = AvisoFragment(bbox=BoundingBox(0, 0, 500, 300), confidence=0.9,
                            has_header=True)
        bottom = AvisoFragment(bbox=BoundingBox(0, 300, 500, 600), confidence=0.85,
                               has_header=True)
        score = self.engine._continuity_score(top, bottom)
        self.assertEqual(score, -1.0)

    def test_merge_hyphenated_text(self):
        top = AvisoFragment(trailing_text="texto corta-")
        bottom = AvisoFragment(leading_text="do")
        merged = self.engine._merge_texts(top, bottom, ["hyphenated_word"])
        self.assertEqual(merged, "texto cortado")


if __name__ == "__main__":
    unittest.main()
