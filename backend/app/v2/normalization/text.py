import re


class TextNormalizer:
    _OCR_ARTIFACTS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
    _MULTI_SPACE = re.compile(r"[ \t]+")
    _MULTI_NEWLINE = re.compile(r"\n{3,}")
    _BORDER_CHARS = re.compile(r"^[\s\-_=*#|\"']+|[\s\-_=*#|\"']+$")

    def normalize(self, raw: str) -> dict:
        cleaned = self.clean_ocr_artifacts(raw)
        ws_norm = self.normalize_whitespace(cleaned)
        border_norm = self._strip_border_chars(ws_norm)
        return {
            "raw": raw,
            "normalized": border_norm,
            "success": bool(border_norm),
        }

    def clean_ocr_artifacts(self, text: str) -> str:
        if not text:
            return ""
        result = self._OCR_ARTIFACTS.sub("", text)
        result = re.sub(r"\\(?![nrt])", "", result)
        result = re.sub(r"[\u2018\u2019]", "'", result)
        result = re.sub(r"[\u201c\u201d]", '"', result)
        result = re.sub(r"\b0([0-9]{3})\b", r"\1", result)
        return result

    def normalize_whitespace(self, text: str) -> str:
        if not text:
            return ""
        result = self._MULTI_SPACE.sub(" ", text)
        result = self._MULTI_NEWLINE.sub("\n\n", result)
        result = result.strip()
        return result

    def _strip_border_chars(self, text: str) -> str:
        lines = text.split("\n")
        cleaned_lines = [self._BORDER_CHARS.sub("", l) for l in lines]
        return "\n".join(cleaned_lines).strip()
