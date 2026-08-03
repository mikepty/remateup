import unittest

from backend.app.v2.ocr.mapper import OCRMapper
from backend.app.v2.ocr.models import OCRDocument, OCRPage, OCRBlock, OCRWord


SINGLE_PAGE_RESPONSE = {
    "responses": [
        {
            "fullTextAnnotation": {
                "pages": [
                    {
                        "width": 2000,
                        "height": 3000,
                        "blocks": [
                            {
                                "blockType": "TEXT",
                                "confidence": 0.98,
                                "boundingBox": {
                                    "vertices": [
                                        {"x": 100, "y": 200},
                                        {"x": 500, "y": 200},
                                        {"x": 500, "y": 250},
                                        {"x": 100, "y": 250},
                                    ]
                                },
                                "paragraphs": [
                                    {
                                        "words": [
                                            {
                                                "boundingBox": {
                                                    "vertices": [
                                                        {"x": 100, "y": 200},
                                                        {"x": 150, "y": 200},
                                                        {"x": 150, "y": 220},
                                                        {"x": 100, "y": 220},
                                                    ]
                                                },
                                                "confidence": 0.99,
                                                "symbols": [
                                                    {"text": "A", "confidence": 0.99},
                                                    {"text": "V", "confidence": 0.99},
                                                    {"text": "I", "confidence": 0.99},
                                                    {"text": "S", "confidence": 0.99},
                                                    {"text": "O", "confidence": 0.99},
                                                ],
                                            },
                                            {
                                                "boundingBox": {
                                                    "vertices": [
                                                        {"x": 160, "y": 200},
                                                        {"x": 190, "y": 200},
                                                        {"x": 190, "y": 220},
                                                        {"x": 160, "y": 220},
                                                    ]
                                                },
                                                "confidence": 0.97,
                                                "symbols": [
                                                    {"text": "D", "confidence": 0.97},
                                                    {"text": "E", "confidence": 0.97},
                                                ],
                                            },
                                            {
                                                "boundingBox": {
                                                    "vertices": [
                                                        {"x": 200, "y": 200},
                                                        {"x": 320, "y": 200},
                                                        {"x": 320, "y": 220},
                                                        {"x": 200, "y": 220},
                                                    ]
                                                },
                                                "confidence": 0.98,
                                                "symbols": [
                                                    {"text": "R", "confidence": 0.98},
                                                    {"text": "E", "confidence": 0.98},
                                                    {"text": "M", "confidence": 0.98},
                                                    {"text": "A", "confidence": 0.98},
                                                    {"text": "T", "confidence": 0.98},
                                                    {"text": "E", "confidence": 0.98},
                                                ],
                                            },
                                        ],
                                    }
                                ],
                            },
                        ],
                    }
                ],
                "text": "AVISO DE REMATE",
            }
        }
    ]
}


MULTI_PAGE_RESPONSE = {
    "responses": [
        {
            "fullTextAnnotation": {
                "pages": [
                    {
                        "width": 2000,
                        "height": 3000,
                        "blocks": [
                            {
                                "blockType": "TEXT",
                                "confidence": 0.98,
                                "boundingBox": {
                                    "vertices": [
                                        {"x": 100, "y": 200},
                                        {"x": 300, "y": 200},
                                        {"x": 300, "y": 220},
                                        {"x": 100, "y": 220},
                                    ]
                                },
                                "paragraphs": [
                                    {
                                        "words": [
                                            {
                                                "boundingBox": {
                                                    "vertices": [
                                                        {"x": 100, "y": 200},
                                                        {"x": 200, "y": 200},
                                                        {"x": 200, "y": 220},
                                                        {"x": 100, "y": 220},
                                                    ]
                                                },
                                                "confidence": 0.99,
                                                "symbols": [
                                                    {"text": "P", "confidence": 0.99},
                                                    {"text": "a", "confidence": 0.99},
                                                    {"text": "g", "confidence": 0.99},
                                                    {"text": "e", "confidence": 0.99},
                                                    {"text": "1", "confidence": 0.99},
                                                ],
                                            },
                                        ],
                                    }
                                ],
                            },
                        ],
                    }
                ],
                "text": "Page1",
            }
        },
        {
            "fullTextAnnotation": {
                "pages": [
                    {
                        "width": 2000,
                        "height": 3000,
                        "blocks": [
                            {
                                "blockType": "TEXT",
                                "confidence": 0.97,
                                "boundingBox": {
                                    "vertices": [
                                        {"x": 100, "y": 200},
                                        {"x": 300, "y": 200},
                                        {"x": 300, "y": 220},
                                        {"x": 100, "y": 220},
                                    ]
                                },
                                "paragraphs": [
                                    {
                                        "words": [
                                            {
                                                "boundingBox": {
                                                    "vertices": [
                                                        {"x": 100, "y": 200},
                                                        {"x": 200, "y": 200},
                                                        {"x": 200, "y": 220},
                                                        {"x": 100, "y": 220},
                                                    ]
                                                },
                                                "confidence": 0.99,
                                                "symbols": [
                                                    {"text": "P", "confidence": 0.99},
                                                    {"text": "a", "confidence": 0.99},
                                                    {"text": "g", "confidence": 0.99},
                                                    {"text": "e", "confidence": 0.99},
                                                    {"text": "2", "confidence": 0.99},
                                                ],
                                            },
                                        ],
                                    }
                                ],
                            },
                        ],
                    }
                ],
                "text": "Page2",
            }
        },
    ]
}


EMPTY_RESPONSE = {"responses": [{}]}


NO_ANNOTATION_RESPONSE = {}


class TestOCRMapper(unittest.TestCase):
    def setUp(self):
        self.mapper = OCRMapper()

    def test_map_single_page(self):
        doc = self.mapper.map_response(SINGLE_PAGE_RESPONSE)
        self.assertIsInstance(doc, OCRDocument)
        self.assertEqual(len(doc.pages), 1)
        page = doc.pages[0]
        self.assertEqual(page.page_number, 1)
        self.assertEqual(page.width, 2000)
        self.assertEqual(page.height, 3000)

    def test_map_extracts_blocks(self):
        doc = self.mapper.map_response(SINGLE_PAGE_RESPONSE)
        page = doc.pages[0]
        self.assertEqual(len(page.blocks), 1)
        block = page.blocks[0]
        self.assertEqual(block.block_type, "text")
        self.assertEqual(block.confidence, 0.98)

    def test_map_extracts_words(self):
        doc = self.mapper.map_response(SINGLE_PAGE_RESPONSE)
        block = doc.pages[0].blocks[0]
        self.assertEqual(len(block.words), 3)
        self.assertEqual(block.words[0].text, "AVISO")
        self.assertEqual(block.words[1].text, "DE")
        self.assertEqual(block.words[2].text, "REMATE")

    def test_map_word_confidence(self):
        doc = self.mapper.map_response(SINGLE_PAGE_RESPONSE)
        word = doc.pages[0].blocks[0].words[0]
        self.assertEqual(word.confidence, 0.99)

    def test_map_word_bounding_box(self):
        doc = self.mapper.map_response(SINGLE_PAGE_RESPONSE)
        word = doc.pages[0].blocks[0].words[0]
        self.assertEqual(word.x0, 100)
        self.assertEqual(word.y0, 200)
        self.assertEqual(word.x1, 150)
        self.assertEqual(word.y1, 220)

    def test_map_full_text(self):
        doc = self.mapper.map_response(SINGLE_PAGE_RESPONSE)
        self.assertIn("AVISO", doc.full_text)
        self.assertIn("REMATE", doc.full_text)

    def test_map_multi_page(self):
        doc = self.mapper.map_response(MULTI_PAGE_RESPONSE)
        self.assertEqual(len(doc.pages), 2)
        self.assertEqual(doc.pages[0].page_number, 1)
        self.assertEqual(doc.pages[1].page_number, 2)

    def test_multi_page_full_text(self):
        doc = self.mapper.map_response(MULTI_PAGE_RESPONSE)
        self.assertIn("Page1", doc.full_text)
        self.assertIn("Page2", doc.full_text)

    def test_map_empty_response(self):
        doc = self.mapper.map_response(EMPTY_RESPONSE)
        self.assertEqual(len(doc.pages), 0)
        self.assertEqual(doc.full_text, "")

    def test_map_no_annotation(self):
        doc = self.mapper.map_response(NO_ANNOTATION_RESPONSE)
        self.assertEqual(len(doc.pages), 0)

    def test_raw_response_preserved(self):
        doc = self.mapper.map_response(SINGLE_PAGE_RESPONSE)
        self.assertEqual(doc.raw_response, SINGLE_PAGE_RESPONSE)

    def test_page_word_count(self):
        doc = self.mapper.map_response(SINGLE_PAGE_RESPONSE)
        page = doc.pages[0]
        self.assertEqual(page.word_count, 3)

    def test_page_average_confidence(self):
        doc = self.mapper.map_response(SINGLE_PAGE_RESPONSE)
        page = doc.pages[0]
        self.assertAlmostEqual(page.average_confidence, 0.98, places=2)

    def test_text_annotation_only(self):
        annotation = SINGLE_PAGE_RESPONSE["responses"][0]["fullTextAnnotation"]
        page = self.mapper.map_text_annotation(annotation)
        self.assertIsInstance(page, OCRPage)
        self.assertEqual(page.page_number, 1)
        self.assertEqual(page.width, 2000)

    def test_text_annotation_empty(self):
        page = self.mapper.map_text_annotation({})
        self.assertEqual(page.width, 0)
        self.assertEqual(page.height, 0)


HYPHENATED_WORD_RESPONSE = {
    "responses": [
        {
            "fullTextAnnotation": {
                "pages": [
                    {
                        "width": 2000,
                        "height": 3000,
                        "blocks": [
                            {
                                "blockType": "TEXT",
                                "confidence": 0.97,
                                "boundingBox": {"vertices": [
                                    {"x": 100, "y": 200}, {"x": 500, "y": 200},
                                    {"x": 500, "y": 260}, {"x": 100, "y": 260},
                                ]},
                                "paragraphs": [{
                                    "words": [
                                        {
                                            "boundingBox": {"vertices": [
                                                {"x": 100, "y": 200}, {"x": 160, "y": 200},
                                                {"x": 160, "y": 220}, {"x": 100, "y": 220},
                                            ]},
                                            "confidence": 0.96,
                                            "symbols": [
                                                {"text": "J", "confidence": 0.96},
                                                {"text": "U", "confidence": 0.96},
                                                {"text": "D", "confidence": 0.96},
                                                {"text": "I", "confidence": 0.96},
                                                {"text": "-", "confidence": 0.9,
                                                 "property": {"detectedBreak": {"type": "HYPHEN"}}},
                                            ],
                                        },
                                        {
                                            "boundingBox": {"vertices": [
                                                {"x": 100, "y": 240}, {"x": 150, "y": 240},
                                                {"x": 150, "y": 260}, {"x": 100, "y": 260},
                                            ]},
                                            "confidence": 0.96,
                                            "symbols": [
                                                {"text": "C", "confidence": 0.96},
                                                {"text": "I", "confidence": 0.96},
                                                {"text": "A", "confidence": 0.96},
                                                {"text": "L", "confidence": 0.96},
                                            ],
                                        },
                                    ],
                                }],
                            },
                        ],
                    },
                ],
            },
        },
    ],
}


class TestOCRMapperHyphenation(unittest.TestCase):
    def setUp(self):
        self.mapper = OCRMapper()

    def test_hyphenated_word_joined_without_hyphen_or_newline(self):
        doc = self.mapper.map_response(HYPHENATED_WORD_RESPONSE)
        page_text = doc.pages[0].text
        self.assertIn("JUDICIAL", page_text)
        self.assertNotIn("JUDI-", page_text)
        self.assertNotIn("-\n", page_text)

    def test_hyphenated_word_block_text_also_joined(self):
        doc = self.mapper.map_response(HYPHENATED_WORD_RESPONSE)
        block = doc.pages[0].blocks[0]
        self.assertIn("JUDICIAL", block.text)


class TestOCRMapperColumnDetection(unittest.TestCase):
    def setUp(self):
        self.mapper = OCRMapper()

    def test_single_column_no_reordering(self):
        doc = self.mapper.map_response(SINGLE_PAGE_RESPONSE)
        self.assertIn("AVISO", doc.full_text)

    def test_block_confidence_propagation(self):
        doc = self.mapper.map_response(SINGLE_PAGE_RESPONSE)
        block = doc.pages[0].blocks[0]
        self.assertEqual(block.confidence, 0.98)

    def test_word_page_assignment(self):
        doc = self.mapper.map_response(SINGLE_PAGE_RESPONSE)
        for block in doc.pages[0].blocks:
            for word in block.words:
                self.assertEqual(word.page, 1)


if __name__ == "__main__":
    unittest.main()
