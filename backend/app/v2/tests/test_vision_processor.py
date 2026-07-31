import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

from backend.app.v2.ocr.processor import OCRProcessor, OCRProcessorError
from backend.app.v2.ocr.mapper import OCRMapper
from backend.app.v2.ocr.client import VisionClient, VisionClientConfig, VisionClientError
from backend.app.v2.ocr.models import OCRDocument, OCRPage


SAMPLE_VISION_RESPONSE = {
    "responses": [
        {
            "fullTextAnnotation": {
                "pages": [
                    {
                        "width": 2000,
                        "height": 3000,
                        "blocks": [],
                    }
                ],
                "text": "Test OCR output",
            }
        }
    ]
}

SAMPLE_IMAGE_CONTENT = b"fake-png-image-bytes"


class TestOCRProcessor(unittest.TestCase):
    def setUp(self):
        cfg = VisionClientConfig(api_key="test-key")
        self.mock_client = MagicMock(spec=VisionClient)
        self.mock_client.config = cfg
        self.mock_client.is_available.return_value = True
        self.mock_client.annotate.return_value = SAMPLE_VISION_RESPONSE
        self.mapper = OCRMapper()
        self.processor = OCRProcessor(client=self.mock_client, mapper=self.mapper)

    def test_processor_exposes_client(self):
        self.assertIs(self.processor.client, self.mock_client)

    def test_processor_exposes_mapper(self):
        self.assertIs(self.processor.mapper, self.mapper)

    def test_is_available_delegates_to_client(self):
        self.assertTrue(self.processor.is_available())
        self.mock_client.is_available.assert_called_once()

    def test_process_image_not_found(self):
        with self.assertRaises(OCRProcessorError) as ctx:
            self.processor.process_image(r"C:\nonexistent\file.png")
        self.assertIn("not found", str(ctx.exception).lower())

    @patch("backend.app.v2.ocr.processor.Path.read_bytes")
    def test_process_image_reads_file(self, mock_read_bytes):
        mock_read_bytes.return_value = SAMPLE_IMAGE_CONTENT
        with patch("backend.app.v2.ocr.processor.Path.exists") as mock_exists:
            with patch("backend.app.v2.ocr.processor.Path.is_file") as mock_isfile:
                mock_exists.return_value = True
                mock_isfile.return_value = True
                doc = self.processor.process_image(r"C:\fake\test.png")
        self.assertIsInstance(doc, OCRDocument)
        self.mock_client.annotate.assert_called_once_with(SAMPLE_IMAGE_CONTENT)

    @patch("backend.app.v2.ocr.processor.Path.read_bytes")
    def test_process_image_returns_ocr_document(self, mock_read_bytes):
        mock_read_bytes.return_value = SAMPLE_IMAGE_CONTENT
        with patch("backend.app.v2.ocr.processor.Path.exists") as mock_exists:
            with patch("backend.app.v2.ocr.processor.Path.is_file") as mock_isfile:
                mock_exists.return_value = True
                mock_isfile.return_value = True
                doc = self.processor.process_image(r"C:\fake\test.png")
        self.assertIn("Test OCR output", doc.full_text)

    def test_process_image_path_is_directory(self):
        with patch("backend.app.v2.ocr.processor.Path.exists") as mock_exists:
            with patch("backend.app.v2.ocr.processor.Path.is_file") as mock_isfile:
                mock_exists.return_value = True
                mock_isfile.return_value = False
                with self.assertRaises(OCRProcessorError) as ctx:
                    self.processor.process_image(r"C:\fake\dir")
        self.assertIn("not a file", str(ctx.exception).lower())

    def test_process_image_client_error_propagates(self):
        self.mock_client.annotate.side_effect = VisionClientError("API failure")
        with patch("backend.app.v2.ocr.processor.Path.read_bytes") as mock_read:
            with patch("backend.app.v2.ocr.processor.Path.exists") as mock_exists:
                with patch("backend.app.v2.ocr.processor.Path.is_file") as mock_isfile:
                    mock_read.return_value = SAMPLE_IMAGE_CONTENT
                    mock_exists.return_value = True
                    mock_isfile.return_value = True
                    with self.assertRaises(OCRProcessorError) as ctx:
                        self.processor.process_image(r"C:\fake\test.png")
        self.assertIn("API failure", str(ctx.exception))

    @patch("backend.app.v2.ocr.processor.Path.read_bytes")
    def test_process_image_empty_file(self, mock_read_bytes):
        mock_read_bytes.return_value = b""
        with patch("backend.app.v2.ocr.processor.Path.exists") as mock_exists:
            with patch("backend.app.v2.ocr.processor.Path.is_file") as mock_isfile:
                mock_exists.return_value = True
                mock_isfile.return_value = True
                doc = self.processor.process_image(r"C:\fake\empty.png")
        self.assertIsInstance(doc, OCRDocument)

    def test_process_multiple_empty_list(self):
        doc = self.processor.process_multiple([])
        self.assertIsInstance(doc, OCRDocument)
        self.assertEqual(doc.full_text, "")

    def test_process_multiple_unsupported_format(self):
        doc = self.processor.process_multiple([r"C:\fake\file.txt"])
        self.assertIn("unsupported", doc.full_text.lower())

    @patch("backend.app.v2.ocr.processor.Path.read_bytes")
    @patch("backend.app.v2.ocr.processor.Path.exists")
    @patch("backend.app.v2.ocr.processor.Path.is_file")
    def test_process_multiple_images(self, mock_isfile, mock_exists, mock_read_bytes):
        mock_exists.return_value = True
        mock_isfile.return_value = True
        mock_read_bytes.return_value = SAMPLE_IMAGE_CONTENT
        doc = self.processor.process_multiple([
            r"C:\fake\img1.png",
            r"C:\fake\img2.jpg",
        ])
        self.assertEqual(self.mock_client.annotate.call_count, 2)

    def test_process_pdf_not_found(self):
        with self.assertRaises(OCRProcessorError) as ctx:
            self.processor.process_pdf(r"C:\nonexistent\file.pdf")
        self.assertIn("not found", str(ctx.exception).lower())

    def test_process_pdf_requires_pymupdf(self):
        import sys
        backup = sys.modules.get("fitz", None)
        sys.modules["fitz"] = None

        with patch("backend.app.v2.ocr.processor.Path.exists") as mock_exists:
            with patch("backend.app.v2.ocr.processor.Path.is_file") as mock_isfile:
                mock_exists.return_value = True
                mock_isfile.return_value = True
                try:
                    with self.assertRaises(OCRProcessorError) as ctx:
                        self.processor.process_pdf(r"C:\fake\test.pdf")
                    self.assertIn("PyMuPDF", str(ctx.exception))
                finally:
                    if backup is not None:
                        sys.modules["fitz"] = backup
                    else:
                        del sys.modules["fitz"]


if __name__ == "__main__":
    unittest.main()
