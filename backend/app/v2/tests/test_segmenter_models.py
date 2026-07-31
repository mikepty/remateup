import unittest

from backend.app.v2.segmenter.models import (
    BoundingBox, DetectedLine, DetectedBlock, DetectedColumn,
    DetectedSection, DetectedAviso, SegmentedPage, SegmentedDocument,
)
from backend.app.v2.document.models import SectionType
from backend.app.v2.ocr.models import OCRWord


class TestBoundingBox(unittest.TestCase):
    def test_area(self):
        b = BoundingBox(0, 0, 200, 100)
        self.assertEqual(b.area(), 20000)

    def test_width_height(self):
        b = BoundingBox(10, 20, 110, 70)
        self.assertEqual(b.width(), 100)
        self.assertEqual(b.height(), 50)

    def test_center(self):
        b = BoundingBox(100, 200, 300, 400)
        self.assertEqual(b.center_x(), 200.0)
        self.assertEqual(b.center_y(), 300.0)

    def test_intersects(self):
        a = BoundingBox(0, 0, 100, 100)
        b = BoundingBox(50, 50, 150, 150)
        self.assertTrue(a.intersects(b))
        self.assertTrue(b.intersects(a))

    def test_not_intersects(self):
        a = BoundingBox(0, 0, 50, 50)
        b = BoundingBox(100, 100, 150, 150)
        self.assertFalse(a.intersects(b))

    def test_intersects_with_tolerance(self):
        a = BoundingBox(0, 0, 50, 50)
        b = BoundingBox(60, 60, 100, 100)
        self.assertFalse(a.intersects(b))
        self.assertTrue(a.intersects(b, tolerance=15))

    def test_to_dict(self):
        b = BoundingBox(10, 20, 100, 200)
        self.assertEqual(b.to_dict(), {"x0": 10, "y0": 20, "x1": 100, "y1": 200})


class TestDetectedLine(unittest.TestCase):
    def test_create_line(self):
        w = OCRWord(text="AVISO", confidence=0.98, x0=100, y0=200, x1=200, y1=220, page=1)
        line = DetectedLine(words=[w], text="AVISO", bbox=BoundingBox(100, 200, 200, 220), confidence=0.98)
        self.assertEqual(line.text, "AVISO")
        self.assertEqual(len(line.words), 1)

    def test_to_dict(self):
        line = DetectedLine(text="test", bbox=BoundingBox(0, 0, 50, 20), confidence=0.95)
        d = line.to_dict()
        self.assertEqual(d["text"], "test")
        self.assertEqual(d["confidence"], 0.95)


class TestDetectedBlock(unittest.TestCase):
    def test_create_block(self):
        block = DetectedBlock(text="AVISO DE REMATE", block_type="text",
                              bbox=BoundingBox(0, 0, 500, 50), confidence=0.95)
        self.assertEqual(block.text, "AVISO DE REMATE")
        self.assertEqual(block.block_type, "text")


class TestDetectedColumn(unittest.TestCase):
    def test_column_text(self):
        b1 = DetectedBlock(text="Block 1 text", block_type="text")
        b2 = DetectedBlock(text="Block 2 text", block_type="text")
        col = DetectedColumn(index=0, blocks=[b1, b2])
        self.assertIn("Block 1", col.text)
        self.assertIn("Block 2", col.text)

    def test_column_to_dict(self):
        col = DetectedColumn(index=0, bbox=BoundingBox(0, 0, 500, 1000))
        d = col.to_dict()
        self.assertEqual(d["index"], 0)
        self.assertEqual(d["block_count"], 0)


class TestDetectedSection(unittest.TestCase):
    def test_section_creation(self):
        sec = DetectedSection(section_type=SectionType.HEADER, text="AVISO DE REMATE",
                               bbox=BoundingBox(0, 0, 500, 30), confidence=0.98)
        self.assertEqual(sec.section_type, SectionType.HEADER)
        self.assertEqual(sec.text, "AVISO DE REMATE")

    def test_to_dict(self):
        sec = DetectedSection(section_type=SectionType.VALORES, text="$100,000")
        d = sec.to_dict()
        self.assertEqual(d["section_type"], "valores")

    def test_section_unknown_default(self):
        sec = DetectedSection(text="unclassified text")
        self.assertEqual(sec.section_type, SectionType.UNKNOWN)


class TestDetectedAviso(unittest.TestCase):
    def test_create_aviso(self):
        sec = DetectedSection(section_type=SectionType.HEADER, text="AVISO DE REMATE")
        aviso = DetectedAviso(header_text="AVISO DE REMATE", sections=[sec],
                               bbox=BoundingBox(0, 0, 500, 500), confidence=0.95)
        self.assertEqual(aviso.header_text, "AVISO DE REMATE")
        self.assertEqual(len(aviso.sections), 1)
        self.assertFalse(aviso.is_portada_resumen)

    def test_full_text(self):
        s1 = DetectedSection(section_type=SectionType.HEADER, text="AVISO DE REMATE")
        s2 = DetectedSection(section_type=SectionType.PARTIES, text="Demandante: Juan")
        aviso = DetectedAviso(header_text="AVISO DE REMATE", sections=[s1, s2])
        self.assertIn("AVISO DE REMATE", aviso.full_text)
        self.assertIn("Demandante: Juan", aviso.full_text)

    def test_to_dict(self):
        aviso = DetectedAviso(header_text="AVISO", confidence=0.9, is_portada_resumen=True)
        d = aviso.to_dict()
        self.assertTrue(d["is_portada_resumen"])
        self.assertEqual(d["confidence"], 0.9)


class TestSegmentedPage(unittest.TestCase):
    def test_create_page(self):
        page = SegmentedPage(page_number=1, width=2000, height=3000)
        self.assertEqual(page.page_number, 1)
        self.assertEqual(page.total_avisos, 0)

    def test_with_avisos(self):
        aviso = DetectedAviso(header_text="AVISO DE REMATE")
        page = SegmentedPage(page_number=1, width=2000, height=3000, avisos=[aviso])
        self.assertEqual(page.total_avisos, 1)

    def test_to_dict(self):
        page = SegmentedPage(page_number=2, avisos=[DetectedAviso()])
        d = page.to_dict()
        self.assertEqual(d["page_number"], 2)
        self.assertEqual(d["total_avisos"], 1)


class TestSegmentedDocument(unittest.TestCase):
    def test_empty_document(self):
        doc = SegmentedDocument()
        self.assertEqual(doc.total_avisos, 0)
        self.assertEqual(doc.total_pages, 0)
        self.assertEqual(doc.average_confidence, 0.0)
        self.assertEqual(doc.full_text, "")

    def test_with_pages(self):
        p1 = SegmentedPage(page_number=1, avisos=[DetectedAviso(header_text="Av1")])
        p2 = SegmentedPage(page_number=2, avisos=[DetectedAviso(header_text="Av2")])
        doc = SegmentedDocument(pages=[p1, p2])
        self.assertEqual(doc.total_pages, 2)
        self.assertEqual(doc.total_avisos, 2)

    def test_average_confidence(self):
        p1 = SegmentedPage(page_number=1, confidence=0.95)
        p2 = SegmentedPage(page_number=2, confidence=0.85)
        doc = SegmentedDocument(pages=[p1, p2])
        self.assertAlmostEqual(doc.average_confidence, 0.9)

    def test_get_avisos_by_page(self):
        a1 = DetectedAviso(header_text="Aviso 1")
        p1 = SegmentedPage(page_number=1, avisos=[a1])
        p2 = SegmentedPage(page_number=2)
        doc = SegmentedDocument(pages=[p1, p2])
        self.assertEqual(len(doc.get_avisos_by_page(1)), 1)
        self.assertEqual(len(doc.get_avisos_by_page(2)), 0)
        self.assertEqual(len(doc.get_avisos_by_page(99)), 0)

    def test_full_text(self):
        a1 = DetectedAviso(header_text="Aviso 1")
        a2 = DetectedAviso(header_text="Aviso 2")
        p1 = SegmentedPage(page_number=1, avisos=[a1, a2])
        doc = SegmentedDocument(pages=[p1])
        self.assertIn("Aviso 1", doc.full_text)
        self.assertIn("Aviso 2", doc.full_text)

    def test_to_dict(self):
        doc = SegmentedDocument(pages=[SegmentedPage(page_number=1)])
        d = doc.to_dict()
        self.assertEqual(d["total_pages"], 1)
        self.assertIn("pages", d)


if __name__ == "__main__":
    unittest.main()
