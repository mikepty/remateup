import unittest
from unittest.mock import MagicMock

from backend.app.v2.ocr.models import OCRWord, OCRBlock, OCRPage, OCRDocument
from backend.app.v2.segmenter.models import (
    SegmentedDocument, DetectedBlock, DetectedSection, DetectedAviso,
)
from backend.app.v2.segmenter.engine import SegmentationEngine
from backend.app.v2.segmenter.block_detector import BlockDetector
from backend.app.v2.segmenter.line_detector import LineDetector
from backend.app.v2.segmenter.column_detector import ColumnDetector
from backend.app.v2.segmenter.section_detector import SectionDetector
from backend.app.v2.segmenter.scoring import SegmentationScorer


class TestSegmentationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = SegmentationEngine()

    def test_segment_empty_document(self):
        doc = OCRDocument()
        result = self.engine.segment(doc)
        self.assertIsInstance(result, SegmentedDocument)
        self.assertEqual(result.total_pages, 0)

    def test_segment_single_page_no_blocks(self):
        page = OCRPage(page_number=1, width=2000, height=3000)
        doc = OCRDocument(pages=[page])
        result = self.engine.segment(doc)
        self.assertEqual(result.total_pages, 1)
        self.assertEqual(result.total_avisos, 0)

    def test_segment_page_with_words(self):
        w = OCRWord(text="text", confidence=0.9, x0=0, y0=0, x1=50, y1=20, page=1)
        b = OCRBlock(text="text", confidence=0.9, block_type="text",
                     x0=0, y0=0, x1=50, y1=20, page=1, words=[w])
        page = OCRPage(page_number=1, width=2000, height=3000, blocks=[b])
        doc = OCRDocument(pages=[page])
        result = self.engine.segment(doc)
        self.assertEqual(result.total_pages, 1)

    def test_segment_multiple_pages(self):
        p1 = OCRPage(page_number=1, width=2000, height=3000)
        p2 = OCRPage(page_number=2, width=2000, height=3000)
        doc = OCRDocument(pages=[p1, p2])
        result = self.engine.segment(doc)
        self.assertEqual(result.total_pages, 2)

    def test_aviso_detection_with_header(self):
        w1 = OCRWord(text="AVISO", confidence=0.98, x0=100, y0=200, x1=200, y1=220, page=1)
        w2 = OCRWord(text="DE", confidence=0.97, x0=210, y0=200, x1=250, y1=220, page=1)
        w3 = OCRWord(text="REMATE", confidence=0.98, x0=260, y0=200, x1=380, y1=220, page=1)
        words = [w1, w2, w3]
        block = OCRBlock(text="AVISO DE REMATE", confidence=0.98, block_type="text",
                         x0=100, y0=200, x1=380, y1=220, page=1, words=words)
        page = OCRPage(page_number=1, width=2000, height=3000, blocks=[block])
        doc = OCRDocument(pages=[page])
        result = self.engine.segment(doc)
        self.assertEqual(result.total_avisos, 1)
        self.assertIn("AVISO DE REMATE", result.pages[0].avisos[0].header_text)

    def test_aviso_no_header_grouped_as_single(self):
        w = OCRWord(text="content", confidence=0.9, x0=0, y0=0, x1=50, y1=20, page=1)
        b = OCRBlock(text="content", confidence=0.9, block_type="text",
                     x0=0, y0=0, x1=50, y1=20, page=1, words=[w])
        page = OCRPage(page_number=1, width=2000, height=3000, blocks=[b])
        doc = OCRDocument(pages=[page])
        result = self.engine.segment(doc)
        self.assertEqual(result.total_avisos, 1)

    def test_get_sections_after_segment(self):
        w = OCRWord(text="text", confidence=0.9, x0=0, y0=0, x1=50, y1=20, page=1)
        b = OCRBlock(text="text", confidence=0.9, block_type="text",
                     x0=0, y0=0, x1=50, y1=20, page=1, words=[w])
        page = OCRPage(page_number=1, width=2000, height=3000, blocks=[b])
        doc = OCRDocument(pages=[page])
        self.engine.segment(doc)
        sections = self.engine.get_sections()
        self.assertIsInstance(sections, list)

    def test_segment_with_mock_detectors(self):
        mock_block = MagicMock(spec=BlockDetector)
        mock_block.detect.return_value = [
            DetectedBlock(text="AVISO DE REMATE"),
        ]
        engine = SegmentationEngine(block_detector=mock_block)

        page = OCRPage(page_number=1, width=2000, height=3000)
        doc = OCRDocument(pages=[page])
        result = engine.segment(doc)
        self.assertIsInstance(result, SegmentedDocument)

    def test_full_pipeline_integration(self):
        words = [
            OCRWord(text="AVISO", confidence=0.98, x0=100, y0=200, x1=200, y1=220, page=1),
            OCRWord(text="DE", confidence=0.97, x0=210, y0=200, x1=250, y1=220, page=1),
            OCRWord(text="REMATE", confidence=0.98, x0=260, y0=200, x1=380, y1=220, page=1),
            OCRWord(text="FINCA", confidence=0.95, x0=100, y0=240, x1=160, y1=260, page=1),
            OCRWord(text="30269", confidence=0.95, x0=170, y0=240, x1=250, y1=260, page=1),
            OCRWord(text="BASE", confidence=0.93, x0=100, y0=280, x1=160, y1=300, page=1),
            OCRWord(text="$150,000", confidence=0.93, x0=170, y0=280, x1=320, y1=300, page=1),
        ]
        block = OCRBlock(text="AVISO DE REMATE FINCA 30269 BASE $150,000",
                         confidence=0.95, block_type="text",
                         x0=100, y0=200, x1=380, y1=300, page=1, words=words)
        page = OCRPage(page_number=1, width=2000, height=3000, blocks=[block])
        doc = OCRDocument(pages=[page])
        result = self.engine.segment(doc)
        self.assertGreaterEqual(result.total_avisos, 1)
        self.assertGreater(result.average_confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
