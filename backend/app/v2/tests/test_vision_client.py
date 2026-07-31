import unittest
from unittest.mock import MagicMock, patch

from backend.app.v2.ocr.client import (
    VisionClient, VisionClientConfig, VisionClientError, VisionAPIError,
)


SAMPLE_VISION_RESPONSE = {
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
                                                        {"x": 200, "y": 200},
                                                        {"x": 200, "y": 220},
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
                                        ],
                                    }
                                ],
                            },
                        ],
                    }
                ],
                "text": "AVISO",
            }
        }
    ]
}


class TestVisionClientConfig(unittest.TestCase):
    def test_default_config(self):
        cfg = VisionClientConfig()
        self.assertEqual(cfg.api_key, "")
        self.assertEqual(cfg.base_url, "https://vision.googleapis.com/v1/images:annotate")
        self.assertEqual(cfg.language_hints, ["es"])
        self.assertEqual(cfg.feature_type, "DOCUMENT_TEXT_DETECTION")
        self.assertEqual(cfg.timeout_seconds, 120)

    def test_custom_config(self):
        cfg = VisionClientConfig(api_key="test-key", timeout_seconds=60)
        self.assertEqual(cfg.api_key, "test-key")
        self.assertEqual(cfg.timeout_seconds, 60)


class TestVisionClient(unittest.TestCase):
    def test_raises_when_no_key(self):
        client = VisionClient()
        with self.assertRaises(VisionClientError):
            client.annotate(b"fake-image-bytes")

    def test_is_available_false_without_key(self):
        client = VisionClient()
        self.assertFalse(client.is_available())

    def test_is_available_true_with_key(self):
        cfg = VisionClientConfig(api_key="test-key")
        client = VisionClient(config=cfg)
        self.assertTrue(client.is_available())

    @patch("backend.app.v2.ocr.client.requests.Session")
    def test_annotate_success(self, mock_session_class):
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_VISION_RESPONSE
        mock_session.post.return_value = mock_response

        cfg = VisionClientConfig(api_key="test-key")
        client = VisionClient(config=cfg)
        result = client.annotate(b"fake-image-bytes")

        self.assertIn("responses", result)
        mock_session.post.assert_called_once()

    @patch("backend.app.v2.ocr.client.requests.Session")
    def test_annotate_http_error(self, mock_session_class):
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_session.post.return_value = mock_response

        cfg = VisionClientConfig(api_key="test-key")
        client = VisionClient(config=cfg)
        with self.assertRaises(VisionAPIError) as ctx:
            client.annotate(b"fake-image-bytes")
        self.assertEqual(ctx.exception.status_code, 400)

    @patch("backend.app.v2.ocr.client.requests.Session")
    def test_annotate_api_error_in_response(self, mock_session_class):
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "responses": [{"error": {"code": 500, "message": "internal error"}}]
        }
        mock_session.post.return_value = mock_response

        cfg = VisionClientConfig(api_key="test-key")
        client = VisionClient(config=cfg)
        with self.assertRaises(VisionAPIError) as ctx:
            client.annotate(b"fake-image-bytes")
        self.assertEqual(ctx.exception.status_code, 500)

    @patch("backend.app.v2.ocr.client.requests.Session")
    def test_annotate_timeout(self, mock_session_class):
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        from requests.exceptions import Timeout
        mock_session.post.side_effect = Timeout("timed out")

        cfg = VisionClientConfig(api_key="test-key")
        client = VisionClient(config=cfg)
        with self.assertRaises(VisionClientError) as ctx:
            client.annotate(b"fake-image-bytes")
        self.assertIn("timeout", str(ctx.exception).lower())

    @patch("backend.app.v2.ocr.client.requests.Session")
    def test_annotate_connection_error(self, mock_session_class):
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        from requests.exceptions import ConnectionError
        mock_session.post.side_effect = ConnectionError("connection failed")

        cfg = VisionClientConfig(api_key="test-key")
        client = VisionClient(config=cfg)
        with self.assertRaises(VisionClientError) as ctx:
            client.annotate(b"fake-image-bytes")
        self.assertIn("connection", str(ctx.exception).lower())

    @patch("backend.app.v2.ocr.client.requests.Session")
    def test_annotate_batch_success(self, mock_session_class):
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "responses": [
                {"fullTextAnnotation": {"text": "Page 1"}},
                {"fullTextAnnotation": {"text": "Page 2"}},
            ]
        }
        mock_session.post.return_value = mock_response

        cfg = VisionClientConfig(api_key="test-key")
        client = VisionClient(config=cfg)
        results = client.annotate_batch([b"img1", b"img2"])

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["fullTextAnnotation"]["text"], "Page 1")

    @patch("backend.app.v2.ocr.client.requests.Session")
    def test_annotate_batch_api_error(self, mock_session_class):
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "responses": [
                {"error": {"code": 500, "message": "image 0 failed"}},
            ]
        }
        mock_session.post.return_value = mock_response

        cfg = VisionClientConfig(api_key="test-key")
        client = VisionClient(config=cfg)
        with self.assertRaises(VisionAPIError) as ctx:
            client.annotate_batch([b"img1"])
        self.assertIn("image 0", str(ctx.exception.message))

    def test_close_idempotent(self):
        client = VisionClient()
        client.close()
        client.close()

    def test_close_without_session(self):
        cfg = VisionClientConfig(api_key="test-key")
        client = VisionClient(config=cfg)
        client.close()


if __name__ == "__main__":
    unittest.main()
