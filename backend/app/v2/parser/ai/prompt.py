"""FASE 11 — Controlled prompt builder for AIResolver.

The prompt sent to the provider is extremely restricted:

- country
- document type
- field name
- OCR text
- existing evidence

The provider MUST answer exclusively JSON:

    {"value": "...", "confidence": 0.82, "reason": "..."}

No free text is accepted. If the JSON is not valid, the caller must return
REQUIRES_REVIEW.
"""

import hashlib
import json
from typing import Any, Optional

from backend.app.v2.parser.context import ParserContext

PROMPT_VERSION = "1.0.0"

JSON_ONLY_INSTRUCTION = (
    "Respond exclusively with a single valid JSON object. No prose, no "
    "markdown fences, no code blocks. The JSON must have exactly three keys: "
    '"value" (string), "confidence" (number between 0 and 1), "reason" (string).'
)


def build_ai_prompt(
    field_name: str,
    context: ParserContext,
    previous_result: Optional[Any] = None,
) -> dict:
    country = context.country or "unknown"
    document_type = context.document_type or "REMATE"
    ocr_text = (context.text or "")[:8000]

    evidence = ""
    if previous_result is not None:
        prev = getattr(previous_result, "to_dict", lambda: previous_result)()
        if isinstance(prev, dict):
            if prev.get("value") is not None:
                evidence = json.dumps(
                    {
                        "existing_value": prev.get("value"),
                        "existing_status": prev.get("status"),
                        "existing_confidence": prev.get("confidence"),
                    },
                    ensure_ascii=False,
                )
    if context.evidence:
        evidence = json.dumps(context.evidence[:10], ensure_ascii=False, default=str)

    system = (
        "You are a field extractor for judicial auction notices "
        "(avisos de remate). "
        + JSON_ONLY_INSTRUCTION
    )

    user = (
        f"Country: {country}\n"
        f"Document type: {document_type}\n"
        f"Field to extract: {field_name}\n"
        f"Existing evidence: {evidence or 'none'}\n"
        f"OCR text:\n{ocr_text}"
    )

    return {
        "system": system,
        "user": user,
        "field_name": field_name,
        "country": country,
        "document_type": document_type,
        "prompt_version": PROMPT_VERSION,
    }


def prompt_hash(prompt: dict) -> str:
    canonical = json.dumps(prompt, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def response_hash(response: Any) -> str:
    canonical = json.dumps(response, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_ai_json(content: str) -> Optional[dict]:
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    if "value" not in data or "confidence" not in data:
        return None
    return {
        "value": data.get("value"),
        "confidence": float(data.get("confidence", 0.0)),
        "reason": str(data.get("reason", "")),
    }
