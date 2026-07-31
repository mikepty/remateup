import sys
import unittest

sys.path.insert(0, r"C:\Users\user\Documents\RemateUp")

loader = unittest.TestLoader()
suite = unittest.TestSuite()

suite.addTests(loader.loadTestsFromName("backend.app.v2.tests.test_document_models"))
suite.addTests(loader.loadTestsFromName("backend.app.v2.tests.test_ocr_models"))
suite.addTests(loader.loadTestsFromName("backend.app.v2.tests.test_evidence_service"))
suite.addTests(loader.loadTestsFromName("backend.app.v2.tests.test_vision_client"))
suite.addTests(loader.loadTestsFromName("backend.app.v2.tests.test_vision_mapper"))
suite.addTests(loader.loadTestsFromName("backend.app.v2.tests.test_vision_processor"))
suite.addTests(loader.loadTestsFromName("backend.app.v2.tests.test_segmenter_models"))
suite.addTests(loader.loadTestsFromName("backend.app.v2.tests.test_segmenter_detectors"))
suite.addTests(loader.loadTestsFromName("backend.app.v2.tests.test_segmenter_engine"))
suite.addTests(loader.loadTestsFromName("backend.app.v2.tests.test_continuity"))
suite.addTests(loader.loadTestsFromName("backend.app.v2.tests.test_assembly"))

runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)

sys.exit(0 if result.wasSuccessful() else 1)
