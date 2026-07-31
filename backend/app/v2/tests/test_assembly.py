import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.app.v2.document.models import (
    SourceDocument, SourceType, DocumentPage, ImageFragment,
)
from backend.app.v2.document.sequence import SequenceDetector
from backend.app.v2.document.assembly import DocumentAssembly, PDFAnalyzer


class TestImageFragment(unittest.TestCase):
    def test_create_fragment(self):
        f = ImageFragment(path="top.jpg", page_position="top", page_number=1)
        self.assertEqual(f.path, "top.jpg")
        self.assertEqual(f.page_position, "top")

    def test_to_dict(self):
        f = ImageFragment(path="img.png", page_position="bottom", page_number=2)
        d = f.to_dict()
        self.assertEqual(d["page_position"], "bottom")


class TestDocumentPage(unittest.TestCase):
    def test_empty_page(self):
        p = DocumentPage(page_number=1)
        self.assertFalse(p.is_complete)
        self.assertEqual(p.fragment_count, 0)

    def test_with_fragments(self):
        f1 = ImageFragment(path="top.jpg", page_position="top")
        f2 = ImageFragment(path="bottom.jpg", page_position="bottom")
        p = DocumentPage(page_number=1, fragments=[f1, f2])
        self.assertTrue(p.is_complete)
        self.assertEqual(p.fragment_count, 2)

    def test_to_dict(self):
        p = DocumentPage(page_number=3, fragments=[ImageFragment(path="a.jpg")], page_type="newspaper")
        d = p.to_dict()
        self.assertEqual(d["page_number"], 3)
        self.assertEqual(d["page_type"], "newspaper")


class TestSourceDocument(unittest.TestCase):
    def test_empty(self):
        s = SourceDocument()
        self.assertEqual(s.total_pages, 0)
        self.assertEqual(s.total_files, 0)

    def test_with_files(self):
        s = SourceDocument(source_type=SourceType.PANAMA_NEWSPAPER,
                           file_paths=["a.jpg", "b.jpg"])
        self.assertEqual(s.total_files, 2)

    def test_with_pages(self):
        p1 = DocumentPage(page_number=1)
        s = SourceDocument(pages=[p1, p1])
        self.assertEqual(s.total_pages, 2)

    def test_to_dict(self):
        s = SourceDocument(source_type=SourceType.COLOMBIA_PDF_TEXT)
        d = s.to_dict()
        self.assertEqual(d["source_type"], "colombia_pdf_text")


class TestSequenceDetector(unittest.TestCase):
    def setUp(self):
        self.detector = SequenceDetector()

    def test_empty(self):
        result = self.detector.detect([])
        self.assertIsNone(result)

    def test_panama_two_images(self):
        paths = ["sup.jpg", "inf.jpg"]
        with patch("backend.app.v2.document.assembly.PDFAnalyzer.analyze") as mock_pdf:
            mock_pdf.return_value = "pdf_text"
            result = self.detector.detect(paths, "PA")
        self.assertIsNotNone(result)
        self.assertEqual(result.source_type, SourceType.PANAMA_NEWSPAPER)
        self.assertEqual(result.total_pages, 1)

    def test_panama_six_images_three_pages(self):
        paths = [
            "p1_sup.jpg", "p1_inf.jpg",
            "p2_sup.jpg", "p2_inf.jpg",
            "p3_sup.jpg", "p3_inf.jpg",
        ]
        with patch("backend.app.v2.document.assembly.PDFAnalyzer.analyze") as mock_pdf:
            mock_pdf.return_value = "pdf_text"
            result = self.detector.detect(paths, "PA")
        self.assertEqual(result.total_pages, 3)
        self.assertEqual(result.total_files, 6)

    def test_panama_six_images_sequential_paired(self):
        paths = ["imagen1.jpg", "imagen2.jpg", "imagen3.jpg", "imagen4.jpg", "imagen5.jpg", "imagen6.jpg"]
        result = self.detector.detect(paths, "PA")
        self.assertEqual(result.total_pages, 3)
        self.assertEqual(result.total_files, 6)
        for i, p in enumerate(result.pages):
            self.assertEqual(len(p.fragments), 2, f"Page {i+1} should have 2 fragments")
            self.assertEqual(p.fragments[0].page_position, "top", f"Page {i+1} fragment 0 should be top")
            self.assertEqual(p.fragments[1].page_position, "bottom", f"Page {i+1} fragment 1 should be bottom")

    def test_panama_auto_detection(self):
        paths = ["arriba.jpg", "abajo.jpg"]
        result = self.detector.detect(paths, "")
        self.assertIsNotNone(result)

    def test_panama_implicit_via_auto(self):
        paths = ["img1_top.png", "img1_bottom.png"]
        result = self.detector.detect(paths, "")
        self.assertIsNotNone(result)
        self.assertEqual(result.source_type, SourceType.PANAMA_NEWSPAPER)

    def test_colombia_single_pdf(self):
        paths = ["documento.pdf"]
        with patch("backend.app.v2.document.assembly.PDFAnalyzer.analyze") as mock_pdf:
            mock_pdf.return_value = "pdf_text"
            result = self.detector.detect(paths, "CO")
        self.assertEqual(result.source_type, SourceType.COLOMBIA_PDF_TEXT)
        self.assertEqual(result.total_pages, 1)

    def test_position_detection_top(self):
        self.assertEqual(self.detector._detect_position("top"), "top")
        self.assertEqual(self.detector._detect_position("superior"), "top")

    def test_position_detection_bottom(self):
        self.assertEqual(self.detector._detect_position("bottom"), "bottom")
        self.assertEqual(self.detector._detect_position("inferior"), "bottom")

    def test_position_detection_full(self):
        self.assertEqual(self.detector._detect_position("image_only"), "full")


class TestPDFAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = PDFAnalyzer()

    def test_analyze_nonexistent(self):
        result = self.analyzer.analyze(r"C:\nonexistent.pdf")
        self.assertEqual(result, "unknown")

    def test_analyze_unreadable_returns_unknown(self):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.__import__", side_effect=ImportError("no fitz")):
                result = self.analyzer.analyze("fake.pdf")
                self.assertEqual(result, "unknown")


class TestDocumentAssembly(unittest.TestCase):
    def setUp(self):
        self.assembly = DocumentAssembly()

    def test_empty_paths(self):
        result = self.assembly.assemble([], "")
        self.assertEqual(result.source_type, SourceType.UNKNOWN)

    def test_validate_paths_not_found(self):
        with self.assertRaises(FileNotFoundError):
            self.assembly._validate_paths([r"C:\nonexistent.jpg"])

    def test_validate_paths_unsupported(self):
        with patch("pathlib.Path.exists", return_value=True):
            with self.assertRaises(ValueError):
                self.assembly._validate_paths(["file.txt"])

    def test_validate_paths_supported(self):
        with patch("pathlib.Path.exists", return_value=True):
            try:
                self.assembly._validate_paths(["test.jpg", "test.pdf"])
            except ValueError:
                self.fail("Should not raise for valid extensions")

    def test_is_panama_newspaper(self):
        s = SourceDocument(source_type=SourceType.PANAMA_NEWSPAPER)
        self.assertTrue(self.assembly.is_panama_newspaper(s))

    def test_is_colombia_pdf(self):
        s = SourceDocument(source_type=SourceType.COLOMBIA_PDF_TEXT)
        self.assertTrue(self.assembly.is_colombia_pdf(s))
        s2 = SourceDocument(source_type=SourceType.PANAMA_NEWSPAPER)
        self.assertFalse(self.assembly.is_colombia_pdf(s2))


if __name__ == "__main__":
    unittest.main()
