import unittest

from backend.app.v2.ocr.models import OCRWord, OCRBlock, OCRPage, OCRDocument


class TestOCRWord(unittest.TestCase):
    def test_create_word(self):
        w = OCRWord(text="AVISO", confidence=0.98, x0=100, y0=200, x1=200, y1=220, page=1)
        self.assertEqual(w.text, "AVISO")
        self.assertEqual(w.confidence, 0.98)
        self.assertEqual(w.center_x(), 150.0)
        self.assertEqual(w.center_y(), 210.0)
        self.assertEqual(w.height(), 20)
        self.assertEqual(w.width(), 100)

    def test_word_to_dict(self):
        w = OCRWord(text="DE", confidence=0.95, x0=210, y0=200, x1=250, y1=220, page=1)
        d = w.to_dict()
        self.assertEqual(d["text"], "DE")
        self.assertEqual(d["confidence"], 0.95)
        self.assertEqual(d["x0"], 210)


class TestOCRBlock(unittest.TestCase):
    def test_create_block(self):
        w1 = OCRWord(text="AVISO", confidence=0.98, x0=100, y0=200, x1=200, y1=220, page=1)
        w2 = OCRWord(text="DE", confidence=0.95, x0=210, y0=200, x1=250, y1=220, page=1)
        w3 = OCRWord(text="REMATE", confidence=0.97, x0=260, y0=200, x1=380, y1=220, page=1)
        block = OCRBlock(
            text="AVISO DE REMATE", confidence=0.97, block_type="text",
            x0=100, y0=200, x1=380, y1=220, page=1, words=[w1, w2, w3],
        )
        self.assertEqual(block.text, "AVISO DE REMATE")
        self.assertEqual(len(block.words), 3)
        self.assertEqual(block.to_dict()["block_type"], "text")

    def test_empty_block(self):
        block = OCRBlock(text="", confidence=0.0, block_type="text",
                         x0=0, y0=0, x1=0, y1=0, page=1)
        self.assertEqual(len(block.words), 0)


class TestOCRPage(unittest.TestCase):
    def test_create_page(self):
        page = OCRPage(page_number=1, width=2000, height=3000)
        self.assertEqual(page.page_number, 1)
        self.assertEqual(page.word_count, 0)
        self.assertEqual(page.average_confidence, 0.0)

    def test_page_with_blocks(self):
        w = OCRWord(text="test", confidence=0.95, x0=0, y0=0, x1=50, y1=20, page=1)
        block = OCRBlock(text="test", confidence=0.95, block_type="text",
                         x0=0, y0=0, x1=50, y1=20, page=1, words=[w])
        page = OCRPage(page_number=1, width=2000, height=3000, blocks=[block], text="test")
        self.assertEqual(page.word_count, 1)
        self.assertEqual(page.average_confidence, 0.95)


class TestOCRDocument(unittest.TestCase):
    def test_empty_document(self):
        doc = OCRDocument()
        self.assertEqual(doc.total_pages, 0)
        self.assertEqual(doc.total_blocks, 0)
        self.assertEqual(doc.total_words, 0)
        self.assertEqual(doc.average_confidence, 0.0)

    def test_document_with_pages(self):
        p1 = OCRPage(page_number=1, width=2000, height=3000)
        p2 = OCRPage(page_number=2, width=2000, height=3000)
        doc = OCRDocument(pages=[p1, p2])
        self.assertEqual(doc.total_pages, 2)

    def test_get_all_words(self):
        w1 = OCRWord(text="word1", confidence=0.9, x0=0, y0=0, x1=50, y1=20, page=1)
        w2 = OCRWord(text="word2", confidence=0.8, x0=60, y0=0, x1=110, y1=20, page=1)
        b = OCRBlock(text="word1 word2", confidence=0.85, block_type="text",
                     x0=0, y0=0, x1=110, y1=20, page=1, words=[w1, w2])
        p = OCRPage(page_number=1, width=2000, height=3000, blocks=[b])
        doc = OCRDocument(pages=[p])
        words = doc.get_all_words()
        self.assertEqual(len(words), 2)
        self.assertEqual(words[0].text, "word1")
        self.assertEqual(words[1].text, "word2")

    def test_get_blocks_on_page(self):
        b1 = OCRBlock(text="block1", confidence=0.9, block_type="text",
                      x0=0, y0=0, x1=100, y1=50, page=1)
        b2 = OCRBlock(text="block2", confidence=0.8, block_type="text",
                      x0=0, y0=60, x1=100, y1=110, page=1)
        p1 = OCRPage(page_number=1, width=2000, height=3000, blocks=[b1, b2])
        p2 = OCRPage(page_number=2, width=2000, height=3000)
        doc = OCRDocument(pages=[p1, p2])
        self.assertEqual(len(doc.get_blocks_on_page(1)), 2)
        self.assertEqual(doc.get_blocks_on_page(2), [])
        self.assertEqual(doc.get_blocks_on_page(99), [])

    def test_to_domain_document(self):
        w = OCRWord(text="AVISO", confidence=0.98, x0=100, y0=200, x1=200, y1=220, page=1)
        b = OCRBlock(text="AVISO", confidence=0.98, block_type="text",
                     x0=100, y0=200, x1=200, y1=220, page=1, words=[w])
        p = OCRPage(page_number=1, width=2000, height=3000, blocks=[b], text="AVISO")
        ocr_doc = OCRDocument(pages=[p], full_text="AVISO")
        domain_doc = ocr_doc.to_domain_document(pais="PA", doc_type="newspaper_page")
        self.assertEqual(domain_doc.pais, "PA")
        self.assertEqual(domain_doc.document_type.value, "newspaper_page")
        self.assertEqual(domain_doc.total_pages, 1)
        self.assertEqual(domain_doc.raw_text, "AVISO")


if __name__ == "__main__":
    unittest.main()
