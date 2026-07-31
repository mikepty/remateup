import unittest

from backend.app.v2.ocr.models import OCRWord, OCRBlock
from backend.app.v2.segmenter.models import BoundingBox, DetectedBlock, DetectedSection, DetectedLine
from backend.app.v2.segmenter.line_detector import LineDetector
from backend.app.v2.segmenter.block_detector import BlockDetector
from backend.app.v2.segmenter.column_detector import ColumnDetector
from backend.app.v2.segmenter.section_detector import SectionDetector
from backend.app.v2.segmenter.scoring import SegmentationScorer
from backend.app.v2.segmenter.relationship_detector import RelationshipDetector
from backend.app.v2.document.models import SectionType


class TestLineDetector(unittest.TestCase):
    def setUp(self):
        self.detector = LineDetector()

    def test_empty_words(self):
        self.assertEqual(self.detector.detect_lines([]), [])

    def test_single_word(self):
        w = OCRWord(text="AVISO", confidence=0.98, x0=100, y0=200, x1=200, y1=220, page=1)
        lines = self.detector.detect_lines([w])
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].text, "AVISO")

    def test_two_words_same_line(self):
        w1 = OCRWord(text="AVISO", confidence=0.98, x0=100, y0=200, x1=200, y1=220, page=1)
        w2 = OCRWord(text="DE", confidence=0.95, x0=210, y0=200, x1=250, y1=220, page=1)
        lines = self.detector.detect_lines([w1, w2])
        self.assertEqual(len(lines), 1)

    def test_two_words_different_lines(self):
        w1 = OCRWord(text="AVISO", confidence=0.98, x0=100, y0=200, x1=200, y1=220, page=1)
        w2 = OCRWord(text="REMATE", confidence=0.97, x0=100, y0=300, x1=250, y1=320, page=1)
        lines = self.detector.detect_lines([w1, w2])
        self.assertEqual(len(lines), 2)

    def test_merge_split_words_normal(self):
        w1 = OCRWord(text="A", confidence=0.9, x0=100, y0=200, x1=110, y1=220, page=1)
        w2 = OCRWord(text="VIS", confidence=0.9, x0=115, y0=200, x1=135, y1=220, page=1)
        merged = self.detector.merge_split_words([w1, w2])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].text, "AVIS")

    def test_merge_split_words_no_merge(self):
        w1 = OCRWord(text="AVISO", confidence=0.98, x0=100, y0=200, x1=200, y1=220, page=1)
        w2 = OCRWord(text="DE", confidence=0.95, x0=300, y0=200, x1=340, y1=220, page=1)
        merged = self.detector.merge_split_words([w1, w2])
        self.assertEqual(len(merged), 2)

    def test_line_bounding_box(self):
        w1 = OCRWord(text="A", confidence=0.9, x0=100, y0=200, x1=110, y1=220, page=1)
        w2 = OCRWord(text="B", confidence=0.9, x0=120, y0=200, x1=130, y1=220, page=1)
        lines = self.detector.detect_lines([w1, w2])
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].bbox.x0, 100)
        self.assertEqual(lines[0].bbox.x1, 130)


class TestBlockDetector(unittest.TestCase):
    def setUp(self):
        self.detector = BlockDetector()

    def test_empty_lines(self):
        self.assertEqual(self.detector.detect([]), [])

    def test_single_line_block(self):
        line = DetectedLine(text="AVISO DE REMATE", bbox=BoundingBox(0, 0, 500, 30), confidence=0.95)
        blocks = self.detector.detect([line])
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].text, "AVISO DE REMATE")

    def test_two_close_lines_same_block(self):
        l1 = DetectedLine(text="Line 1", bbox=BoundingBox(0, 0, 100, 20), confidence=0.9, y_center=10)
        l2 = DetectedLine(text="Line 2", bbox=BoundingBox(0, 22, 100, 42), confidence=0.9, y_center=32)
        blocks = self.detector.detect([l1, l2])
        self.assertEqual(len(blocks), 1)
        self.assertIn("Line 1", blocks[0].text)
        self.assertIn("Line 2", blocks[0].text)

    def test_two_distant_lines_separate_blocks(self):
        l1 = DetectedLine(text="Line 1", bbox=BoundingBox(0, 0, 100, 20), confidence=0.9, y_center=10)
        l2 = DetectedLine(text="Line 2", bbox=BoundingBox(0, 200, 100, 220), confidence=0.9, y_center=210)
        blocks = self.detector.detect([l1, l2], page_height=500)
        self.assertEqual(len(blocks), 2)

    def test_block_bbox(self):
        l1 = DetectedLine(text="A", bbox=BoundingBox(0, 0, 50, 20), confidence=0.9, y_center=10)
        l2 = DetectedLine(text="B", bbox=BoundingBox(0, 22, 60, 42), confidence=0.9, y_center=32)
        blocks = self.detector.detect([l1, l2])
        self.assertEqual(blocks[0].bbox.x0, 0)
        self.assertEqual(blocks[0].bbox.y0, 0)
        self.assertEqual(blocks[0].bbox.x1, 60)
        self.assertEqual(blocks[0].bbox.y1, 42)


class TestColumnDetector(unittest.TestCase):
    def setUp(self):
        self.detector = ColumnDetector()

    def test_empty_blocks(self):
        cols = self.detector.detect([], 2000)
        self.assertEqual(len(cols), 1)
        self.assertEqual(len(cols[0].blocks), 0)

    def test_single_column(self):
        blocks = [
            DetectedBlock(text="Block 1", bbox=BoundingBox(100, 0, 300, 100)),
            DetectedBlock(text="Block 2", bbox=BoundingBox(100, 120, 300, 200)),
        ]
        cols = self.detector.detect(blocks, 2000)
        self.assertEqual(len(cols), 1)

    def test_two_columns(self):
        blocks = [
            DetectedBlock(text="Left 1", bbox=BoundingBox(50, 0, 300, 100)),
            DetectedBlock(text="Left 2", bbox=BoundingBox(50, 120, 300, 200)),
            DetectedBlock(text="Right 1", bbox=BoundingBox(800, 0, 1100, 100)),
            DetectedBlock(text="Right 2", bbox=BoundingBox(800, 120, 1100, 200)),
        ]
        cols = self.detector.detect(blocks, 2000)
        self.assertGreaterEqual(len(cols), 1)

    def test_assign_to_column(self):
        cols = [
            type('FakeCol', (), {'index': 0, 'bbox': BoundingBox(0, 0, 500, 1000)})(),
            type('FakeCol', (), {'index': 1, 'bbox': BoundingBox(600, 0, 1200, 1000)})(),
        ]
        idx = self.detector.assign_to_column(300, cols)
        self.assertEqual(idx, 0)

    def test_assign_to_column_outside(self):
        cols = [
            type('FakeCol', (), {'index': 0, 'bbox': BoundingBox(0, 0, 500, 1000)})(),
        ]
        idx = self.detector.assign_to_column(1000, cols)
        self.assertEqual(idx, 0)


class TestSectionDetector(unittest.TestCase):
    def setUp(self):
        self.detector = SectionDetector()

    def test_empty_blocks(self):
        sections = self.detector.detect_sections([])
        self.assertEqual(sections, [])

    def test_header_detection(self):
        block = DetectedBlock(text="AVISO DE REMATE", block_type="text",
                              bbox=BoundingBox(0, 0, 500, 30), confidence=0.98)
        sections = self.detector.detect_sections([block])
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].section_type, SectionType.HEADER)

    def test_portada_detection_short_no_header(self):
        short_text = "FINCA 12345 EXP 6789"
        self.assertTrue(self.detector.detect_portada(short_text))

    def test_portada_detection_long_text(self):
        long_text = "X" * 1000
        self.assertFalse(self.detector.detect_portada(long_text))

    def test_portada_detection_with_header(self):
        text = "AVISO DE REMATE\nFINCA 12345\nBase $100,000\nDemandante: Juan"
        self.assertFalse(self.detector.detect_portada(text))

    def test_detect_party_section(self):
        self.assertTrue(self.detector.detect_party_section("DEMANDANTE: Juan Perez"))
        self.assertTrue(self.detector.detect_party_section("DEMANDADO: Maria Lopez"))
        self.assertFalse(self.detector.detect_party_section("AVISO DE REMATE"))

    def test_detect_full_aviso(self):
        text = "AVISO DE REMATE\nFINCA 12345\nBase $100,000\nDemandante: Juan\nDescripcion: Casa en Panama"
        self.assertTrue(self.detector.detect_full_aviso(text))

    def test_detect_full_aviso_short(self):
        text = "AVISO DE REMATE"
        self.assertFalse(self.detector.detect_full_aviso(text))

    def test_classify_block_header(self):
        block = DetectedBlock(text="AVISO DE REMATE")
        stype, conf = self.detector.classify_block(block)
        self.assertEqual(stype, SectionType.HEADER)

    def test_classify_block_parties(self):
        block = DetectedBlock(text="DEMANDANTE: Juan\nDEMANDADO: Maria")
        stype, _ = self.detector.classify_block(block)
        self.assertEqual(stype, SectionType.PARTIES)

    def test_classify_block_unknown(self):
        block = DetectedBlock(text="Some random text without keywords")
        stype, _ = self.detector.classify_block(block)
        self.assertEqual(stype, SectionType.UNKNOWN)

    def test_detect_portada_keyword(self):
        text = "PORTADA\nFinca 12345\nDemandante: Juan"
        self.assertTrue(self.detector.detect_portada(text))

    def test_detect_portada_short_remate(self):
        text = "REMATE\nFinca 12345"
        self.assertTrue(self.detector.detect_portada(text))

    def test_portada_false_for_full_aviso(self):
        text = "AVISO DE REMATE\nJuzgado Primero\nFINCA 30269\nBase $150,000\nDemandante: Juan\nDescripcion: Casa en Panama\nFianza 10%\nMinimo 66.67%"
        self.assertFalse(self.detector.detect_portada(text))


class TestScoring(unittest.TestCase):
    def setUp(self):
        self.scorer = SegmentationScorer()

    def test_score_empty(self):
        score = self.scorer.score([], 0)
        self.assertEqual(score["overall"], 0.0)

    def test_score_columns_empty(self):
        score = self.scorer.score_columns([], 2)
        self.assertEqual(score, 0.0)

    def test_score_columns_perfect(self):
        from backend.app.v2.segmenter.models import DetectedColumn
        cols = [DetectedColumn(index=0, blocks=[DetectedBlock(text="1")]),
                DetectedColumn(index=1, blocks=[DetectedBlock(text="2")])]
        score = self.scorer.score_columns(cols, 2)
        self.assertEqual(score, 1.0)

    def test_score_columns_excess(self):
        from backend.app.v2.segmenter.models import DetectedColumn
        cols = [DetectedColumn(index=0, blocks=[DetectedBlock(text="1")])]
        score = self.scorer.score_columns(cols, 1)
        self.assertEqual(score, 1.0)

    def test_score_aviso_no_sections(self):
        from backend.app.v2.segmenter.models import DetectedAviso
        aviso = DetectedAviso()
        score = self.scorer.score_aviso(aviso)
        self.assertEqual(score, 0.3)

    def test_score_aviso_with_sections(self):
        from backend.app.v2.segmenter.models import DetectedAviso, DetectedSection
        s1 = DetectedSection(section_type=SectionType.HEADER)
        s2 = DetectedSection(section_type=SectionType.VALORES)
        aviso = DetectedAviso(sections=[s1, s2], confidence=0.9)
        score = self.scorer.score_aviso(aviso)
        self.assertGreater(score, 0.5)


class TestRelationshipDetector(unittest.TestCase):
    def setUp(self):
        self.detector = RelationshipDetector()

    def test_detect_pairs_expediente(self):
        sec = DetectedSection(text="EXPEDIENTE: 12345-2024", section_type=SectionType.HEADER)
        pairs = self.detector.detect_pairs([sec])
        self.assertTrue(any(p.field_name == "expediente" for p in pairs))

    def test_detect_pairs_demandante(self):
        sec = DetectedSection(text="DEMANDANTE: Juan Perez", section_type=SectionType.PARTIES)
        pairs = self.detector.detect_pairs([sec])
        self.assertTrue(any(p.field_name == "demandante" for p in pairs))

    def test_detect_pairs_finca(self):
        sec = DetectedSection(text="FINCA N° 30269", section_type=SectionType.HEADER)
        pairs = self.detector.detect_pairs([sec])
        self.assertTrue(any(p.field_name == "finca_matr" for p in pairs))

    def test_extract_field_value(self):
        field, value = self.detector.extract_field_value("BASE: $150,000.00")
        self.assertEqual(field, "base")

    def test_extract_field_value_not_found(self):
        field, value = self.detector.extract_field_value("No labels here")
        self.assertEqual(field, "")

    def test_find_all_labels(self):
        results = self.detector.find_all_labels("FINCA 12345 EXP 6789")
        self.assertTrue(len(results) >= 2)

    def test_deduplicate_by_field(self):
        s1 = DetectedSection(text="BASE: $100,000", confidence=0.8)
        s2 = DetectedSection(text="VALOR: $150,000", confidence=0.95)
        pairs = self.detector.detect_pairs([s1, s2])
        base_results = [p for p in pairs if p.field_name == "base"]
        self.assertLessEqual(len(base_results), 1)

    def test_empty_sections(self):
        pairs = self.detector.detect_pairs([])
        self.assertEqual(pairs, [])


if __name__ == "__main__":
    unittest.main()
