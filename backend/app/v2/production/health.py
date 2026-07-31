"""FASE 10 — Health Check.

Validates the operational state of every critical component:

Parser, Knowledge, Schema, Validator, Registry, SQLite,
Configuration and overall status (HEALTHY / WARNING / ERROR).
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from backend.app.v2.parser.factory import ParserFactory
from backend.app.v2.knowledge.repository import KnowledgeRepository
from backend.app.v2.schema.field_registry import REGISTRY
from backend.app.v2.validator.orchestrator import ValidationOrchestrator
from backend.app.v2.production.config import ProductionConfig, get_default

_CRITICAL = {"parser", "knowledge", "schema", "validator", "registry", "sqlite", "config"}


class HealthChecker:
    def __init__(self, config: Optional[ProductionConfig] = None):
        self.config = config or get_default()
        self.checks: dict[str, dict] = {}

    def check_parser(self) -> dict:
        try:
            parser_factory = ParserFactory()
            for country in ("PA", "CO"):
                parser_factory.get_parser(country, "REMATE")
            return self._ok("parser", "ParserFactory loaded for PA and CO")
        except Exception as e:  # pragma: no cover
            return self._fail("parser", f"Parser not loaded: {e}")

    def check_knowledge(self) -> dict:
        try:
            repo = KnowledgeRepository()
            rules = repo.get_rules()
            detail = f"KnowledgeRepository loaded ({len(rules)} rules)"
            return self._ok("knowledge", detail)
        except Exception as e:
            return self._fail("knowledge", f"Knowledge not loaded: {e}")

    def check_schema(self) -> dict:
        try:
            from backend.app.v2.schema.definitions import FIELD_CATALOG
            total = len(FIELD_CATALOG)
            if total <= 0:
                return self._fail("schema", "Schema empty")
            return self._ok("schema", f"Schema loaded ({total} fields)")
        except Exception as e:
            return self._fail("schema", f"Schema not loaded: {e}")

    def check_validator(self) -> dict:
        try:
            orchestrator = ValidationOrchestrator()
            return self._ok("validator", "ValidationOrchestrator loaded")
        except Exception as e:
            return self._fail("validator", f"Validator not loaded: {e}")

    def check_registry(self) -> dict:
        try:
            names = REGISTRY.field_names()
            if not names:
                return self._fail("registry", "Registry is empty")
            duplicates = len(names) != len(set(names))
            if duplicates:
                return self._fail("registry", "Registry contains duplicate field names")
            return self._ok("registry", f"Registry valid ({len(names)} fields)")
        except Exception as e:
            return self._fail("registry", f"Registry invalid: {e}")

    def check_sqlite(self) -> dict:
        issues = []
        checked = 0
        knowledge_db = Path(__file__).resolve().parents[1] / "knowledge" / "knowledge.db"
        for label, path in (("knowledge", knowledge_db),):
            if not path.exists():
                issues.append(f"{label} DB not found: {path}")
                continue
            try:
                conn = sqlite3.connect(str(path), timeout=2.0)
                conn.execute("SELECT 1")
                conn.close()
                checked += 1
            except Exception as e:
                issues.append(f"{label} DB not accessible: {e}")
        if checked > 0 and not issues:
            return self._ok("sqlite", f"SQLite accessible ({checked} database(s))")
        if issues:
            return self._warn("sqlite", "; ".join(issues))
        return self._warn("sqlite", "No SQLite database available")

    def check_config(self) -> dict:
        errors = self.config.validate()
        if errors:
            return self._fail("config", "; ".join(errors))
        return self._ok("config", "Configuration valid")

    def _ok(self, name: str, detail: str) -> dict:
        return {"check": name, "status": "OK", "ok": True, "detail": detail}

    def _warn(self, name: str, detail: str) -> dict:
        return {"check": name, "status": "WARNING", "ok": False, "detail": detail}

    def _fail(self, name: str, detail: str) -> dict:
        return {"check": name, "status": "ERROR", "ok": False, "detail": detail}

    def run(self) -> dict:
        self.checks = {
            "parser": self.check_parser(),
            "knowledge": self.check_knowledge(),
            "schema": self.check_schema(),
            "validator": self.check_validator(),
            "registry": self.check_registry(),
            "sqlite": self.check_sqlite(),
            "config": self.check_config(),
        }
        statuses = {c["status"] for c in self.checks.values()}
        if "ERROR" in statuses:
            overall = "ERROR"
        elif any(c["status"] == "WARNING" for c in self.checks.values()):
            overall = "WARNING"
        else:
            overall = "HEALTHY"

        critical_failed = [
            name for name, c in self.checks.items()
            if name in _CRITICAL and c["status"] == "ERROR"
        ]

        return {
            "status": overall,
            "critical_failed": critical_failed,
            "checks": self.checks,
            "checked_at": datetime.utcnow().isoformat(),
            "summary": {
                "total_checks": len(self.checks),
                "ok": sum(1 for c in self.checks.values() if c["status"] == "OK"),
                "warnings": sum(1 for c in self.checks.values() if c["status"] == "WARNING"),
                "errors": sum(1 for c in self.checks.values() if c["status"] == "ERROR"),
            },
        }


def run_health_check(config: Optional[ProductionConfig] = None) -> dict:
    return HealthChecker(config).run()
