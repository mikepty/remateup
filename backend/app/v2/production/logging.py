"""FASE 10 — Structured logging.

Each processed document produces one structured JSON log line with:
document_id, country, pages, processing_time, decision, score,
errores and warnings.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class StructuredLogEntry:
    def __init__(
        self,
        document_id: str = "",
        country: str = "",
        pages: int = 0,
        processing_time: float = 0.0,
        decision: str = "",
        score: float = 0.0,
        errores: Optional[list] = None,
        warnings: Optional[list] = None,
        **extra: Any,
    ):
        self.timestamp = datetime.utcnow().isoformat()
        self.document_id = document_id
        self.country = country
        self.pages = pages
        self.processing_time = round(float(processing_time), 3)
        self.decision = decision
        self.score = round(float(score), 4)
        self.errores = list(errores or [])
        self.warnings = list(warnings or [])
        self.extra = dict(extra)

    def to_dict(self) -> dict:
        data = {
            "timestamp": self.timestamp,
            "document_id": self.document_id,
            "country": self.country,
            "pages": self.pages,
            "processing_time": self.processing_time,
            "decision": self.decision,
            "score": self.score,
            "errores": self.errores,
            "warnings": self.warnings,
        }
        data.update(self.extra)
        return data

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class StructuredLogger:
    def __init__(self, log_path: Optional[Path] = None, console: bool = False):
        self.log_path = Path(log_path) if log_path else None
        self.console = console
        self._entries: list[StructuredLogEntry] = []

    def log(self, entry: StructuredLogEntry) -> None:
        self._entries.append(entry)
        line = entry.to_json_line()
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        if self.console:
            print(line)

    def log_document(
        self,
        document_id: str,
        country: str,
        pages: int,
        processing_time: float,
        decision: str,
        score: float,
        errores: Optional[list] = None,
        warnings: Optional[list] = None,
        **extra: Any,
    ) -> StructuredLogEntry:
        entry = StructuredLogEntry(
            document_id=document_id,
            country=country,
            pages=pages,
            processing_time=processing_time,
            decision=decision,
            score=score,
            errores=errores,
            warnings=warnings,
            **extra,
        )
        self.log(entry)
        return entry

    def log_from_result(self, result: dict) -> StructuredLogEntry:
        return self.log_document(
            document_id=result.get("document_id", ""),
            country=result.get("country", ""),
            pages=result.get("stages", {}).get("assembly", {}).get("pages", 0),
            processing_time=result.get("total_time_ms", 0.0),
            decision=result.get("certification", {})
                .get("all_avisos", [{}])[0]
                .get("decision", "REQUIRES_REVIEW")
                if isinstance(result.get("certification"), dict) else "REQUIRES_REVIEW",
            score=result.get("validation", {}).get("score", 0.0),
            errores=result.get("errors", []),
            warnings=result.get("warnings", []),
        )

    def log_event(self, level: str, event: str, **fields: Any) -> StructuredLogEntry:
        entry = StructuredLogEntry(
            document_id=fields.pop("document_id", ""),
            country=fields.pop("country", ""),
            decision=fields.pop("decision", ""),
            score=fields.pop("score", 0.0),
            level=level,
            event=event,
            **fields,
        )
        self.log(entry)
        return entry

    def entries(self) -> list[StructuredLogEntry]:
        return list(self._entries)

    def to_dict(self) -> dict:
        return {
            "total_entries": len(self._entries),
            "entries": [e.to_dict() for e in self._entries],
        }


def log_document(result: dict, log_path: Optional[Path] = None) -> StructuredLogEntry:
    logger = StructuredLogger(log_path=log_path)
    return logger.log_from_result(result)
