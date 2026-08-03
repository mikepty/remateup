import unittest

from backend.app.v2.ocr.models import OCRPage, OCRBlock, OCRWord
from backend.app.v2.document.stitching import PageStitcher, StitchedPage


class TestStitching(unittest.TestCase):
    def setUp(self):
        self.stitcher = PageStitcher()
        self.top = OCRPage(
            page_number=1, width=2000, height=3000,
            blocks=[
                OCRBlock(text="AVISO DE REMATE", confidence=0.95, block_type="text",
                         x0=100, y0=200, x1=800, y1=250, page=1,
                         words=[OCRWord(text="AVISO", confidence=0.95, x0=100, y0=200, x1=250, y1=250, page=1),
                                OCRWord(text="DE", confidence=0.95, x0=260, y0=200, x1=320, y1=250, page=1),
                                OCRWord(text="REMATE", confidence=0.95, x0=330, y0=200, x1=800, y1=250, page=1)]),
                OCRBlock(text="FINCA 1234", confidence=0.92, block_type="text",
                         x0=100, y0=600, x1=600, y1=640, page=1,
                         words=[]),
            ],
            text="AVISO DE REMATE\nFINCA 1234",
        )
        self.bottom = OCRPage(
            page_number=2, width=2000, height=2900,
            blocks=[
                OCRBlock(text="BASE: 50000", confidence=0.90, block_type="text",
                         x0=100, y0=100, x1=600, y1=140, page=2,
                         words=[]),
                OCRBlock(text="DEMANDANTE: JUAN", confidence=0.88, block_type="text",
                         x0=100, y0=300, x1=700, y1=340, page=2,
                         words=[]),
            ],
            text="BASE: 50000\nDEMANDANTE: JUAN",
        )

    def test_stitch_basic(self):
        result = self.stitcher.stitch(self.top, self.bottom)
        self.assertIsInstance(result, StitchedPage)
        self.assertEqual(result.page_number, 1)
        self.assertEqual(result.width, 2000)
        self.assertEqual(result.height, 3000 + 2900)
        self.assertEqual(result.total_blocks, 4)

    def test_stitch_preserves_top_blocks(self):
        result = self.stitcher.stitch(self.top, self.bottom)
        top_blocks = result.top_blocks
        self.assertEqual(len(top_blocks), 2)
        self.assertEqual(top_blocks[0].text, "AVISO DE REMATE")
        self.assertEqual(top_blocks[0].y0, 200)
        self.assertEqual(top_blocks[1].text, "FINCA 1234")
        self.assertEqual(top_blocks[1].y0, 600)

    def test_stitch_adjusts_bottom_y(self):
        result = self.stitcher.stitch(self.top, self.bottom)
        bottom_blocks = result.bottom_blocks
        self.assertEqual(len(bottom_blocks), 2)
        # Top height = 3000, so bottom y is offset by 3000
        self.assertEqual(bottom_blocks[0].y0, 100 + 3000)
        self.assertEqual(bottom_blocks[1].y0, 300 + 3000)

    def test_stitch_adjusts_bottom_word_y(self):
        self.bottom.blocks[0].words = [
            OCRWord(text="BASE", confidence=0.9, x0=100, y0=100,
                    x1=180, y1=140, page=2)
        ]
        result = self.stitcher.stitch(self.top, self.bottom)
        self.assertEqual(result.bottom_blocks[0].words[0].y0, 3100)
        self.assertEqual(result.bottom_blocks[0].words[0].y1, 3140)

    def test_dense_full_width_block_reconstructed_as_columns(self):
        words = []
        for col in range(4):
            for row in range(60):
                words.append(OCRWord(
                    text="AVISO" if row == 0 else f"W{row}",
                    confidence=0.9,
                    x0=50 + col * 450,
                    y0=100 + row * 20,
                    x1=130 + col * 450,
                    y1=115 + row * 20,
                    page=1,
                ))
        dense_top = OCRPage(
            page_number=1, width=2000, height=1500,
            blocks=[OCRBlock(
                text="mixed", confidence=0.9, block_type="text",
                x0=20, y0=100, x1=1980, y1=1400, page=1, words=words,
            )],
        )
        result = self.stitcher.stitch(
            dense_top, OCRPage(page_number=2, width=2000, height=1500)
        )
        self.assertEqual(len(result.blocks), 4)
        self.assertEqual([block.column_index for block in result.blocks], [0, 1, 2, 3])

    def test_stitch_preserves_x(self):
        result = self.stitcher.stitch(self.top, self.bottom)
        bottom_blocks = result.bottom_blocks
        self.assertEqual(bottom_blocks[0].x0, 100)
        self.assertEqual(bottom_blocks[0].x1, 600)

    def test_stitch_reading_order(self):
        result = self.stitcher.stitch(self.top, self.bottom)
        self.assertEqual(len(result.blocks), 4)
        self.assertEqual(result.blocks[0].source_position, "top")
        self.assertEqual(result.blocks[1].source_position, "top")
        self.assertEqual(result.blocks[2].source_position, "bottom")
        self.assertEqual(result.blocks[3].source_position, "bottom")

    def test_stitch_fragment_mapping(self):
        result = self.stitcher.stitch(self.top, self.bottom)
        mapping = result.fragment_mapping
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.top_page_index, 1)
        self.assertEqual(mapping.bottom_page_index, 2)
        self.assertEqual(mapping.top_height, 3000)
        self.assertEqual(mapping.bottom_height, 2900)
        self.assertEqual(mapping.y_offset, 3000)

    def test_stitch_full_text(self):
        result = self.stitcher.stitch(self.top, self.bottom)
        self.assertIn("AVISO DE REMATE", result.full_text)
        self.assertIn("FINCA 1234", result.full_text)
        self.assertIn("BASE: 50000", result.full_text)
        self.assertIn("DEMANDANTE: JUAN", result.full_text)

    def test_stitch_preserves_words(self):
        result = self.stitcher.stitch(self.top, self.bottom)
        top_block = result.top_blocks[0]
        self.assertEqual(len(top_block.words), 3)
        self.assertEqual(top_block.words[0].text, "AVISO")

    def test_stitch_to_ocr_page(self):
        result = self.stitcher.stitch(self.top, self.bottom)
        ocr_page = result.to_ocr_page()
        self.assertEqual(ocr_page.page_number, 1)
        self.assertEqual(len(ocr_page.blocks), 4)
        self.assertEqual(ocr_page.width, 2000)
        self.assertEqual(ocr_page.height, 5900)

    def test_stitch_ocr_pages(self):
        pages = [self.top, self.bottom, self.top, self.bottom, self.top, self.bottom]
        stitched = self.stitcher.stitch_ocr_pages(pages, 3)
        self.assertEqual(len(stitched), 3)
        for i, sp in enumerate(stitched):
            self.assertEqual(sp.page_number, i + 1)
            self.assertEqual(sp.total_blocks, 4)

    def test_stitch_ocr_pages_odd_count(self):
        pages = [self.top, self.bottom, self.top]
        stitched = self.stitcher.stitch_ocr_pages(pages, 2)
        self.assertEqual(len(stitched), 2)
        self.assertEqual(stitched[0].total_blocks, 4)
        self.assertEqual(stitched[1].total_blocks, 2)
        # Problema #7: a la segunda página le falta la mitad inferior
        # (imagen impar sin pareja) -- debe quedar marcada como parcial.
        self.assertFalse(stitched[0].is_partial)
        self.assertTrue(stitched[1].is_partial)
        self.assertEqual(stitched[1].missing_side, "bottom")

    def test_stitch_complete_page_not_partial(self):
        result = self.stitcher.stitch(self.top, self.bottom)
        self.assertFalse(result.is_partial)
        self.assertEqual(result.missing_side, "")

    def test_stitch_missing_top_detected(self):
        from backend.app.v2.ocr.models import OCRPage
        empty_top = OCRPage(page_number=0, width=0, height=0)
        result = self.stitcher.stitch(empty_top, self.bottom)
        self.assertTrue(result.is_partial)
        self.assertEqual(result.missing_side, "top")

    def test_stitch_height_calculation(self):
        result = self.stitcher.stitch(self.top, self.bottom)
        expected = self.top.height + self.bottom.height
        self.assertEqual(result.height, expected)
        self.assertGreater(result.height, self.top.height)
        self.assertGreater(result.height, self.bottom.height)


if __name__ == "__main__":
    unittest.main()
