import base64
from dataclasses import dataclass, field
from typing import Optional

import requests


class VisionAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Vision API error {status_code}: {message}")


class VisionClientError(Exception):
    pass


@dataclass
class VisionClientConfig:
    api_key: str = ""
    base_url: str = "https://vision.googleapis.com/v1/images:annotate"
    timeout_seconds: int = 120
    language_hints: list[str] = field(default_factory=lambda: ["es"])
    feature_type: str = "DOCUMENT_TEXT_DETECTION"
    max_results: int = 10


class VisionClient:
    def __init__(self, config: Optional[VisionClientConfig] = None):
        self._config = config or VisionClientConfig()
        self._session: Optional[requests.Session] = None

    @property
    def config(self) -> VisionClientConfig:
        return self._config

    @property
    def _http(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def annotate(
        self,
        image_bytes: bytes,
        language_hints: Optional[list[str]] = None,
        feature_type: Optional[str] = None,
    ) -> dict:
        if not self._config.api_key:
            raise VisionClientError("GOOGLE_VISION_API_KEY not configured")

        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        body = {
            "requests": [
                {
                    "image": {"content": b64},
                    "features": [
                        {
                            "type": feature_type or self._config.feature_type,
                            "maxResults": self._config.max_results,
                        }
                    ],
                    "imageContext": {
                        "languageHints": language_hints or self._config.language_hints
                    },
                }
            ]
        }
        url = f"{self._config.base_url}?key={self._config.api_key}"
        try:
            resp = self._http.post(url, json=body, timeout=self._config.timeout_seconds)
        except requests.Timeout:
            raise VisionClientError(
                f"Vision API timeout after {self._config.timeout_seconds}s"
            )
        except requests.ConnectionError as e:
            raise VisionClientError(f"Vision API connection error: {e}")

        if resp.status_code != 200:
            detail = resp.text[:500] if resp.text else "no details"
            raise VisionAPIError(resp.status_code, detail)

        data = resp.json()
        api_error = data.get("responses", [{}])[0].get("error")
        if api_error:
            raise VisionAPIError(
                api_error.get("code", 500),
                api_error.get("message", "unknown API error"),
            )
        return data

    def annotate_batch(
        self,
        images: list[bytes],
        language_hints: Optional[list[str]] = None,
        feature_type: Optional[str] = None,
    ) -> list[dict]:
        if not self._config.api_key:
            raise VisionClientError("GOOGLE_VISION_API_KEY not configured")

        requests_list = []
        for img_bytes in images:
            b64 = base64.standard_b64encode(img_bytes).decode("utf-8")
            requests_list.append(
                {
                    "image": {"content": b64},
                    "features": [
                        {
                            "type": feature_type or self._config.feature_type,
                            "maxResults": self._config.max_results,
                        }
                    ],
                    "imageContext": {
                        "languageHints": language_hints or self._config.language_hints
                    },
                }
            )

        body = {"requests": requests_list}
        url = f"{self._config.base_url}?key={self._config.api_key}"
        try:
            resp = self._http.post(url, json=body, timeout=self._config.timeout_seconds)
        except requests.Timeout:
            raise VisionClientError(
                f"Vision API timeout after {self._config.timeout_seconds}s"
            )
        except requests.ConnectionError as e:
            raise VisionClientError(f"Vision API connection error: {e}")

        if resp.status_code != 200:
            detail = resp.text[:500] if resp.text else "no details"
            raise VisionAPIError(resp.status_code, detail)

        data = resp.json()
        raw_responses = data.get("responses", [])
        for i, r in enumerate(raw_responses):
            api_error = r.get("error")
            if api_error:
                raise VisionAPIError(
                    api_error.get("code", 500),
                    f"image {i}: {api_error.get('message', 'unknown error')}",
                )
        return raw_responses

    def is_available(self) -> bool:
        return bool(self._config.api_key)

    def close(self):
        if self._session is not None:
            self._session.close()
            self._session = None
