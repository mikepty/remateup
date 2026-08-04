import unittest

from backend.app.v2.ocr.models import OCRPage, OCRBlock, OCRWord
from backend.app.v2.document.stitching import PageStitcher, StitchedBlock, StitchedPage
from backend.app.v2.segmenter.models import BoundingBox, DetectedBlock, DetectedColumn
from backend.app.v2.segmenter.column_analyzer import ColumnAnalyzer
from backend.app.v2.segmenter.notice_detector import NoticeDetector
from backend.app.v2.segmenter.newspaper_layout import NewspaperLayout


class TestColumnAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = ColumnAnalyzer()

    def test_empty_blocks(self):
        cols = self.analyzer.analyze([], 1000, 2000)
        self.assertEqual(len(cols), 1)
        self.assertEqual(cols[0].index, 0)

    def test_single_column(self):
        blocks = [DetectedBlock(text="text", bbox=BoundingBox(x0=100, y0=0, x1=500, y1=100))]
        cols = self.analyzer.analyze(blocks, 1000, 2000)
        self.assertEqual(len(cols), 1)

    def test_two_columns_with_gap(self):
        blocks = [
            DetectedBlock(text="left col text", bbox=BoundingBox(x0=50, y0=0, x1=400, y1=500)),
            DetectedBlock(text="right col text", bbox=BoundingBox(x0=600, y0=0, x1=950, y1=500)),
        ]
        cols = self.analyzer.analyze(blocks, 1000, 2000)
        self.assertEqual(len(cols), 2)
        self.assertEqual(cols[0].index, 0)
        self.assertEqual(cols[1].index, 1)

    def test_three_columns(self):
        blocks = [
            DetectedBlock(text="col1", bbox=BoundingBox(x0=30, y0=0, x1=300, y1=500)),
            DetectedBlock(text="col2", bbox=BoundingBox(x0=350, y0=0, x1=650, y1=500)),
            DetectedBlock(text="col3", bbox=BoundingBox(x0=700, y0=0, x1=970, y1=500)),
        ]
        cols = self.analyzer.analyze(blocks, 1000, 2000)
        self.assertGreaterEqual(len(cols), 2)

    def test_column_block_assignment(self):
        blocks = [
            DetectedBlock(text="left", bbox=BoundingBox(x0=50, y0=0, x1=400, y1=100)),
            DetectedBlock(text="right", bbox=BoundingBox(x0=600, y0=0, x1=950, y1=100)),
        ]
        cols = self.analyzer.analyze(blocks, 1000, 2000)
        self.assertEqual(len(cols), 2)
        self.assertIn(blocks[0], cols[0].blocks)
        self.assertIn(blocks[1], cols[1].blocks)

    def test_blocks_narrow_page(self):
        blocks = [
            DetectedBlock(text="only", bbox=BoundingBox(x0=10, y0=0, x1=100, y1=100)),
        ]
        cols = self.analyzer.analyze(blocks, 200, 500)
        self.assertEqual(len(cols), 1)

    def test_stitched_block_input(self):
        blocks = [
            StitchedBlock(text="col1", x0=50, y0=0, x1=400, y1=500),
            StitchedBlock(text="col2", x0=600, y0=0, x1=950, y1=500),
        ]
        cols = self.analyzer.analyze(blocks, 1000, 2000)
        self.assertEqual(len(cols), 2)


class TestNoticeDetector(unittest.TestCase):
    def setUp(self):
        self.detector = NoticeDetector()

    def test_aviso_de_remate_detected(self):
        blocks = [
            DetectedBlock(text="AVISO DE REMATE", bbox=BoundingBox(x0=100, y0=0, x1=500, y1=50)),
            DetectedBlock(text="FINCA 12345", bbox=BoundingBox(x0=100, y0=60, x1=500, y1=100)),
        ]
        avisos = self.detector.detect_avisos(blocks)
        self.assertEqual(len(avisos), 1)
        self.assertIn("AVISO DE REMATE", avisos[0].header_text)

    def test_remate_judicial_detected(self):
        blocks = [
            DetectedBlock(text="REMATE JUDICIAL", bbox=BoundingBox(x0=100, y0=0, x1=500, y1=50)),
        ]
        avisos = self.detector.detect_avisos(blocks)
        self.assertEqual(len(avisos), 1)

    def test_subasta_judicial_detected(self):
        blocks = [
            DetectedBlock(text="SUBASTA JUDICIAL", bbox=BoundingBox(x0=100, y0=0, x1=500, y1=50)),
        ]
        avisos = self.detector.detect_avisos(blocks)
        self.assertEqual(len(avisos), 1)

    def test_edicto_emplazatorio_not_detected(self):
        blocks = [
            DetectedBlock(text="EDICTO EMPLAZATORIO", bbox=BoundingBox(x0=100, y0=0, x1=500, y1=50)),
        ]
        avisos = self.detector.detect_avisos(blocks)
        self.assertEqual(len(avisos), 0)

    def test_generic_aviso_not_detected(self):
        blocks = [
            DetectedBlock(text="AVISO IMPORTANTE", bbox=BoundingBox(x0=100, y0=0, x1=500, y1=50)),
        ]
        avisos = self.detector.detect_avisos(blocks)
        self.assertEqual(len(avisos), 0)

    def test_generic_edicto_not_detected(self):
        blocks = [
            DetectedBlock(text="EDICTO", bbox=BoundingBox(x0=100, y0=0, x1=500, y1=50)),
        ]
        avisos = self.detector.detect_avisos(blocks)
        self.assertEqual(len(avisos), 0)

    def test_multiple_avisos_in_column(self):
        blocks = [
            DetectedBlock(text="AVISO DE REMATE", bbox=BoundingBox(x0=100, y0=0, x1=500, y1=50)),
            DetectedBlock(text="FINCA UNO", bbox=BoundingBox(x0=100, y0=60, x1=500, y1=100)),
            DetectedBlock(text="AVISO DE REMATE", bbox=BoundingBox(x0=100, y0=200, x1=500, y1=250)),
            DetectedBlock(text="FINCA DOS", bbox=BoundingBox(x0=100, y0=260, x1=500, y1=300)),
        ]
        avisos = self.detector.detect_avisos(blocks)
        self.assertEqual(len(avisos), 2)

    def test_confidence_propagated(self):
        blocks = [
            DetectedBlock(text="AVISO DE REMATE", confidence=0.95,
                          bbox=BoundingBox(x0=100, y0=0, x1=500, y1=50)),
            DetectedBlock(text="detalle", confidence=0.90,
                          bbox=BoundingBox(x0=100, y0=60, x1=500, y1=100)),
        ]
        avisos = self.detector.detect_avisos(blocks)
        self.assertAlmostEqual(avisos[0].confidence, 0.925)

    def test_bbox_union(self):
        blocks = [
            DetectedBlock(text="AVISO DE REMATE", bbox=BoundingBox(x0=100, y0=0, x1=500, y1=50)),
            DetectedBlock(text="continuacion", bbox=BoundingBox(x0=100, y0=60, x1=500, y1=200)),
        ]
        avisos = self.detector.detect_avisos(blocks)
        self.assertEqual(avisos[0].bbox.y0, 0)
        self.assertEqual(avisos[0].bbox.y1, 200)

    def test_no_remate_headers_returns_empty(self):
        blocks = [
            DetectedBlock(text="La Prensa", bbox=BoundingBox(x0=100, y0=0, x1=500, y1=50)),
        ]
        avisos = self.detector.detect_avisos(blocks)
        self.assertEqual(len(avisos), 0)

    def test_banner_publicitario_no_es_cabecera_de_aviso(self):
        # El banner "AVISO DE REMATE IC Publica tus judiciales..." contiene
        # "AVISO DE REMATE" pero es publicidad del periódico: no debe crear
        # un aviso por sí mismo ni agrupar el resto de la columna.
        blocks = [
            DetectedBlock(text="AVISO DE REMATE IC Publica tus judiciales llamando al 204-0000 204-0045",
                          bbox=BoundingBox(x0=100, y0=0, x1=500, y1=50)),
        ]
        avisos = self.detector.detect_avisos(blocks)
        self.assertEqual(len(avisos), 0)

    def test_edicto_emplazatorio_remate_separa_dos_avisos(self):
        # En Panamá los remates se publican como "EDICTO EMPLAZATORIO Nº":
        # cada uno debe ser un aviso separado, y un edicto que no es remate
        # (tutela/divorcio) no debe detectarse.
        blocks = [
            DetectedBlock(text="EDICTO EMPLAZATORIO No. 853-26 N74459-26 RITA ... BASE DEL REMATE sirve de base ... posturas ... Certificado de Deposito",
                          bbox=BoundingBox(x0=100, y0=0, x1=500, y1=200)),
            DetectedBlock(text="EDICTO EMPLAZATORIO N994 Exp. 74468-26 KLEVER ... BASE DEL REMATE sirve de base ... posturas ... Certificado de Deposito",
                          bbox=BoundingBox(x0=100, y0=300, x1=500, y1=500)),
            DetectedBlock(text="EDICTO EMPLAZATORIO No. 751/686902026 Proceso de TUTELA ADULTO MAYOR",
                          bbox=BoundingBox(x0=100, y0=600, x1=500, y1=700)),
        ]
        avisos = self.detector.detect_avisos(blocks)
        self.assertEqual(len(avisos), 2)
        textos = [a.sections[0].text for a in avisos if a.sections]
        self.assertTrue(any("N74459-26" in t for t in textos))
        self.assertTrue(any("74468-26" in t for t in textos))
        self.assertTrue(all("TUTELA" not in t for t in textos))

    def test_banner_no_contamina_texto_del_aviso(self):
        blocks = [
            DetectedBlock(text="AVISO DE REMATE IC Publica tus judiciales llamando al 204-0000 204-0045",
                          bbox=BoundingBox(x0=100, y0=0, x1=500, y1=50)),
            DetectedBlock(text="EDICTO EMPLAZATORIO No. 853-26 N74459-26 RITA ... BASE DEL REMATE sirve de base ... posturas ... Certificado de Deposito",
                          bbox=BoundingBox(x0=100, y0=100, x1=500, y1=300)),
        ]
        avisos = self.detector.detect_avisos(blocks)
        self.assertEqual(len(avisos), 1)
        texto = avisos[0].sections[0].text if avisos[0].sections else ""
        self.assertNotIn("Publica tus judiciales", texto)
        self.assertIn("N74459-26", texto)


class TestNewspaperLayout(unittest.TestCase):
    def setUp(self):
        self.layout = NewspaperLayout()

    def test_empty_page(self):
        page = StitchedPage(page_number=1, width=2000, height=3000)
        avisos = self.layout.segment(page)
        self.assertEqual(len(avisos), 0)

    def test_single_column_one_aviso(self):
        blocks = [
            StitchedBlock(text="AVISO DE REMATE", x0=100, y0=100, x1=500, y1=140, confidence=0.95),
            StitchedBlock(text="FINCA 9999", x0=100, y0=150, x1=500, y1=190, confidence=0.90),
        ]
        page = StitchedPage(page_number=1, width=2000, height=3000, blocks=blocks)
        avisos = self.layout.segment(page)
        self.assertEqual(len(avisos), 1)
        self.assertIn("AVISO DE REMATE", avisos[0].header_text)

    def test_edicto_excluded(self):
        blocks = [
            StitchedBlock(text="EDICTO EMPLAZATORIO", x0=100, y0=100, x1=500, y1=140),
        ]
        page = StitchedPage(page_number=1, width=2000, height=3000, blocks=blocks)
        avisos = self.layout.segment(page)
        self.assertEqual(len(avisos), 0)

    def test_multiple_avisos_across_columns(self):
        blocks = [
            StitchedBlock(text="AVISO DE REMATE", x0=50, y0=100, x1=400, y1=140, confidence=0.95),
            StitchedBlock(text="Contenido aviso 1", x0=50, y0=150, x1=400, y1=300, confidence=0.90),
            StitchedBlock(text="AVISO DE REMATE", x0=600, y0=100, x1=950, y1=140, confidence=0.94),
            StitchedBlock(text="Contenido aviso 2", x0=600, y0=150, x1=950, y1=300, confidence=0.88),
        ]
        page = StitchedPage(page_number=1, width=1000, height=3000, blocks=blocks)
        avisos = self.layout.segment(page)
        # May detect 2 columns with 1 aviso each, or 1 column with 2 avisos
        self.assertGreaterEqual(len(avisos), 1)
        self.assertEqual(avisos[0].header_text, "AVISO DE REMATE")

    def test_continuity_preserved_across_stitch(self):
        blocks = [
            StitchedBlock(text="AVISO DE REMATE", x0=100, y0=100, x1=500, y1=140,
                          source_position="top", confidence=0.95),
            StitchedBlock(text="FINCA 1234", x0=100, y0=200, x1=500, y1=240,
                          source_position="top", confidence=0.90),
            StitchedBlock(text="BASE: 50000", x0=100, y0=3100, x1=500, y1=3140,
                          source_position="bottom", confidence=0.92),
            StitchedBlock(text="DEMANDANTE: JUAN", x0=100, y0=3200, x1=500, y1=3240,
                          source_position="bottom", confidence=0.88),
        ]
        page = StitchedPage(page_number=1, width=2000, height=6000, blocks=blocks)
        avisos = self.layout.segment(page)
        self.assertEqual(len(avisos), 1)
        self.assertIn("AVISO DE REMATE", avisos[0].header_text)

    def test_full_pipeline_integration(self):
        stitcher = PageStitcher()
        top = OCRPage(page_number=1, width=2000, height=3000,
                       text="col1 text\ncol2 text",
                       blocks=[
            OCRBlock(text="AVISO DE REMATE FINCA UNO\nBASE DEL REMATE: 100000\nDEMANDANTE: PEDRO",
                     confidence=0.95, block_type="text",
                     x0=50, y0=100, x1=450, y1=340, page=1),
            OCRBlock(text="PUBLICIDAD", confidence=0.80, block_type="text",
                     x0=600, y0=100, x1=950, y1=140, page=1),
        ])
        bottom = OCRPage(page_number=2, width=2000, height=3000,
                          text="",
                          blocks=[])
        stitched = stitcher.stitch(top, bottom)
        avisos = self.layout.segment(stitched)
        self.assertGreaterEqual(len(avisos), 1)
        self.assertTrue(any("REMATE" in a.header_text.upper() for a in avisos))
        self.assertGreater(stitched.height, 5000)

    def test_two_avisos_same_column_detected(self):
        """2 avisos en la misma columna vertical (uno arriba, otro abajo)
        deben detectarse como 2 avisos separados."""
        stitcher = PageStitcher()
        top = OCRPage(page_number=1, width=2000, height=3000,
                       text="",
                       blocks=[
            OCRBlock(text="AVISO DE REMATE FINCA 11111\nBASE DEL REMATE: 50000\nPOSTURA MINIMA",
                     confidence=0.95, block_type="text",
                     x0=50, y0=100, x1=450, y1=300, page=1),
        ])
        bottom = OCRPage(page_number=2, width=2000, height=3000,
                          text="",
                          blocks=[
            OCRBlock(text="AVISO DE REMATE FINCA 22222\nBASE DEL REMATE: 80000\nPOSTURA MINIMA",
                     confidence=0.95, block_type="text",
                     x0=50, y0=100, x1=450, y1=300, page=2),
        ])
        stitched = stitcher.stitch(top, bottom)
        avisos = self.layout.segment(stitched)
        self.assertGreaterEqual(len(avisos), 2, "Debe detectar 2 avisos en la misma columna")
        headers = [a.header_text.upper() for a in avisos]
        self.assertTrue(any("REMATE" in h for h in headers))

    def test_two_avisos_different_columns_detected(self):
        """2 avisos en columnas diferentes (izq y der) deben detectarse."""
        stitcher = PageStitcher()
        top = OCRPage(page_number=1, width=2000, height=3000,
                       text="",
                       blocks=[
            OCRBlock(text="AVISO DE REMATE FINCA 11111\nBASE DEL REMATE: 50000\nPOSTURA MINIMA",
                     confidence=0.95, block_type="text",
                     x0=50, y0=100, x1=450, y1=300, page=1),
            OCRBlock(text="AVISO DE REMATE FINCA 22222\nBASE DEL REMATE: 80000\nPOSTURA MINIMA",
                     confidence=0.95, block_type="text",
                     x0=1000, y0=100, x1=1950, y1=300, page=1),
        ])
        bottom = OCRPage(page_number=2, width=2000, height=3000,
                          text="",
                          blocks=[])
        stitched = stitcher.stitch(top, bottom)
        avisos = self.layout.segment(stitched)
        self.assertGreaterEqual(len(avisos), 2, "Debe detectar 2 avisos en columnas diferentes")


if __name__ == "__main__":
    unittest.main()
