from pathlib import Path
from typing import Optional
import os

from backend.app.v2.ocr.client import VisionClient, VisionClientConfig, VisionClientError
from backend.app.v2.ocr.mapper import OCRMapper
from backend.app.v2.ocr.models import OCRDocument


class OCRProcessorError(Exception):
    pass


class OCRProcessor:
    def __init__(
        self,
        client: Optional[VisionClient] = None,
        mapper: Optional[OCRMapper] = None,
    ):
        if client is None:
            api_key = os.environ.get("GOOGLE_VISION_API_KEY", "")
            config = VisionClientConfig(api_key=api_key)
            client = VisionClient(config=config)
        self._client = client
        self._mapper = mapper or OCRMapper()

    @property
    def client(self) -> VisionClient:
        return self._client

    @property
    def mapper(self) -> OCRMapper:
        return self._mapper

    def process_image(self, image_path: str) -> OCRDocument:
        path = Path(image_path)
        if not path.exists():
            raise OCRProcessorError(f"Image not found: {image_path}")
        if not path.is_file():
            raise OCRProcessorError(f"Path is not a file: {image_path}")

        image_bytes = path.read_bytes()
        return self._process_image_bytes(image_bytes)

    def _process_image_bytes(self, image_bytes: bytes) -> OCRDocument:
        try:
            response = self._client.annotate(image_bytes)
        except VisionClientError as e:
            raise OCRProcessorError(f"Vision API call failed: {e}")

        return self._mapper.map_response(response)

    def process_pdf(self, pdf_path: str, dpi: int = 144) -> OCRDocument:
        path = Path(pdf_path)
        if not path.exists():
            raise OCRProcessorError(f"PDF not found: {pdf_path}")
        if not path.is_file():
            raise OCRProcessorError(f"Path is not a file: {pdf_path}")

        try:
            import fitz
        except ImportError:
            raise OCRProcessorError(
                "PyMuPDF (fitz) is required for PDF processing. "
                "Install with: pip install PyMuPDF"
            )

        pdf_doc = fitz.open(str(path))
        pages: list[dict] = []
        full_text_parts: list[str] = []
        total_width = 0
        total_height = 0

        for num in range(len(pdf_doc)):
            pagina = pdf_doc[num]
            matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
            pix = pagina.get_pixmap(matrix=matrix)
            img_bytes = pix.tobytes("png")

            try:
                response = self._client.annotate(img_bytes)
            except VisionClientError as e:
                full_text_parts.append(f"--- PÁGINA {num + 1} ---\n[OCR Error: {e}]")
                continue

            ocr_doc = self._mapper.map_response(response)
            if ocr_doc.pages:
                page = ocr_doc.pages[0]
                page.page_number = num + 1
                total_width = max(total_width, page.width)
                total_height = max(total_height, page.height)
                full_text_parts.append(f"--- PÁGINA {num + 1} ---\n{page.text}")

        pdf_doc.close()

        return OCRDocument(
            pages=[],
            full_text="\n\n".join(full_text_parts),
            raw_response={},
        )

    def process_multiple(self, paths: list[str]) -> OCRDocument:
        if not paths:
            return OCRDocument()

        all_pages: list = []
        full_text_parts: list[str] = []

        for path_str in paths:
            p = Path(path_str)
            suffix = p.suffix.lower()

            if suffix == ".pdf":
                result = self.process_pdf(path_str)
            elif suffix in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"):
                result = self.process_image(path_str)
            else:
                full_text_parts.append(f"[Unsupported file type: {suffix}]")
                continue

            if result.pages:
                all_pages.extend(result.pages)
            if result.full_text:
                full_text_parts.append(result.full_text)

        return OCRDocument(
            pages=all_pages,
            full_text="\n\n".join(full_text_parts),
            raw_response={},
        )

    def is_available(self) -> bool:
        return self._client.is_available()
