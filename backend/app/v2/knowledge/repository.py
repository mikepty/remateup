import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from backend.app.v2.knowledge.models import (
    CorrectionEvent, KnowledgeAlias, KnowledgeEvidence, KnowledgeRule,
    RuleHistory, RuleStatus, ShadowComparison,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_rules (
    rule_id TEXT PRIMARY KEY,
    rule_type TEXT NOT NULL DEFAULT 'regex',
    category TEXT NOT NULL DEFAULT '',
    field_name TEXT NOT NULL DEFAULT '',
    pattern TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'PENDING',
    version INTEGER NOT NULL DEFAULT 1,
    rollback_version INTEGER,
    created_from_correction TEXT NOT NULL DEFAULT '',
    approved_by TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    usage_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    fail_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS knowledge_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    field_name TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.0,
    is_builtin INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PENDING',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    usage_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT '',
    field_name TEXT NOT NULL DEFAULT '',
    previous_value TEXT,
    corrected_value TEXT,
    evidence_text TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.0,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 0,
    previous_status TEXT NOT NULL DEFAULT '',
    new_status TEXT NOT NULL DEFAULT '',
    accuracy_before REAL NOT NULL DEFAULT 0.0,
    accuracy_after REAL NOT NULL DEFAULT 0.0,
    reason TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shadow_comparisons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL DEFAULT '',
    field_name TEXT NOT NULL DEFAULT '',
    parser_value TEXT,
    parser_confidence REAL NOT NULL DEFAULT 0.0,
    knowledge_value TEXT,
    knowledge_confidence REAL NOT NULL DEFAULT 0.0,
    knowledge_rule_id TEXT NOT NULL DEFAULT '',
    knowledge_rule_version INTEGER NOT NULL DEFAULT 0,
    winner TEXT NOT NULL DEFAULT '',
    difference INTEGER NOT NULL DEFAULT 0,
    evidence_text TEXT NOT NULL DEFAULT '',
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rules_field ON knowledge_rules(field_name);
CREATE INDEX IF NOT EXISTS idx_rules_status ON knowledge_rules(status);
CREATE INDEX IF NOT EXISTS idx_aliases_field ON knowledge_aliases(field_name);
CREATE INDEX IF NOT EXISTS idx_corrections_field ON corrections(field_name);
CREATE INDEX IF NOT EXISTS idx_corrections_country ON corrections(country);
CREATE INDEX IF NOT EXISTS idx_history_rule ON knowledge_history(rule_id);
CREATE INDEX IF NOT EXISTS idx_shadow_field ON shadow_comparisons(field_name);
"""


class KnowledgeRepository:
    def __init__(self, db_path: str = ""):
        if not db_path:
            db_path = os.environ.get(
                "KNOWLEDGE_DB_PATH",
                os.path.join(os.path.dirname(__file__), "knowledge.db"),
            )
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript(_SCHEMA_SQL)
        conn.commit()

    def _gen_rule_id(self) -> str:
        return uuid.uuid4().hex[:12]

    # --- Corrections ---

    def save_correction(self, event: CorrectionEvent) -> CorrectionEvent:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO corrections (document_id, country, field_name,
               previous_value, corrected_value, evidence_text, confidence, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event.document_id, event.country, event.field_name,
             str(event.previous_value) if event.previous_value is not None else None,
             str(event.corrected_value) if event.corrected_value is not None else None,
             event.evidence_text, event.confidence,
             event.timestamp or _utcnow()),
        )
        conn.commit()
        return event

    def get_corrections(self, country: Optional[str] = None,
                        field_name: Optional[str] = None) -> list[CorrectionEvent]:
        conn = self._get_conn()
        parts = ["SELECT * FROM corrections WHERE 1=1"]
        params: list[Any] = []
        if country:
            parts.append("AND country = ?")
            params.append(country)
        if field_name:
            parts.append("AND field_name = ?")
            params.append(field_name)
        parts.append("ORDER BY timestamp DESC")
        rows = conn.execute(" ".join(parts), params).fetchall()
        return [self._row_to_correction(r) for r in rows]

    def count_corrections(self, country: Optional[str] = None) -> int:
        conn = self._get_conn()
        if country:
            return conn.execute("SELECT COUNT(*) FROM corrections WHERE country = ?",
                                (country,)).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]

    def _row_to_correction(self, r: sqlite3.Row) -> CorrectionEvent:
        return CorrectionEvent(
            document_id=r["document_id"],
            country=r["country"],
            field_name=r["field_name"],
            previous_value=r["previous_value"],
            corrected_value=r["corrected_value"],
            evidence_text=r["evidence_text"],
            confidence=r["confidence"],
            timestamp=r["timestamp"],
        )

    # --- Rules ---

    def save_rule(self, rule: KnowledgeRule) -> KnowledgeRule:
        conn = self._get_conn()
        if not rule.rule_id:
            rule.rule_id = self._gen_rule_id()
            rule.created_at = rule.created_at or _utcnow()
            rule.updated_at = _utcnow()
            conn.execute(
                """INSERT INTO knowledge_rules (rule_id, rule_type, category, field_name,
                   pattern, confidence, status, version, rollback_version,
                   created_from_correction, approved_by, evidence_json,
                   created_at, updated_at, usage_count, success_count, fail_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rule.rule_id, rule.rule_type, rule.category, rule.field_name,
                 rule.pattern, rule.confidence, rule.status, rule.version,
                 rule.rollback_version, rule.created_from_correction, rule.approved_by,
                 json.dumps([e.to_dict() for e in rule.evidence]),
                 rule.created_at, rule.updated_at, rule.usage_count,
                 rule.success_count, rule.fail_count),
            )
        else:
            rule.updated_at = _utcnow()
            conn.execute(
                """UPDATE knowledge_rules SET rule_type=?, category=?, field_name=?,
                   pattern=?, confidence=?, status=?, version=?, rollback_version=?,
                   created_from_correction=?, approved_by=?, evidence_json=?,
                   updated_at=?, usage_count=?, success_count=?, fail_count=?
                   WHERE rule_id=?""",
                (rule.rule_type, rule.category, rule.field_name, rule.pattern,
                 rule.confidence, rule.status, rule.version, rule.rollback_version,
                 rule.created_from_correction, rule.approved_by,
                 json.dumps([e.to_dict() for e in rule.evidence]),
                 rule.updated_at, rule.usage_count, rule.success_count,
                 rule.fail_count, rule.rule_id),
            )
        conn.commit()
        return rule

    def get_rule(self, rule_id: str) -> Optional[KnowledgeRule]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM knowledge_rules WHERE rule_id = ?",
                           (rule_id,)).fetchone()
        return self._row_to_rule(row) if row else None

    def get_rule_by_field_pattern(self, field: str, pattern: str) -> Optional[KnowledgeRule]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM knowledge_rules WHERE field_name = ? AND pattern = ?",
            (field, pattern),
        ).fetchone()
        return self._row_to_rule(row) if row else None

    def get_rules(self, field: Optional[str] = None,
                  status: Optional[str] = None,
                  category: Optional[str] = None) -> list[KnowledgeRule]:
        conn = self._get_conn()
        parts = ["SELECT * FROM knowledge_rules WHERE 1=1"]
        params: list[Any] = []
        if field:
            parts.append("AND field_name = ?")
            params.append(field)
        if status:
            parts.append("AND status = ?")
            params.append(status)
        if category:
            parts.append("AND category = ?")
            params.append(category)
        parts.append("ORDER BY created_at DESC")
        rows = conn.execute(" ".join(parts), params).fetchall()
        return [self._row_to_rule(r) for r in rows]

    def get_approved_rules(self, field: Optional[str] = None) -> list[KnowledgeRule]:
        return self.get_rules(field=field, status=RuleStatus.APPROVED.value)

    def count_rules(self, status: Optional[str] = None) -> int:
        conn = self._get_conn()
        if status:
            return conn.execute("SELECT COUNT(*) FROM knowledge_rules WHERE status = ?",
                                (status,)).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM knowledge_rules").fetchone()[0]

    def get_rules_by_country(self, country: str) -> list[KnowledgeRule]:
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT DISTINCT r.* FROM knowledge_rules r
               JOIN corrections c ON r.field_name = c.field_name
               WHERE c.country = ?""",
            (country,),
        ).fetchall()
        return [self._row_to_rule(r) for r in rows]

    def _row_to_rule(self, r: sqlite3.Row) -> KnowledgeRule:
        evidence_list: list[KnowledgeEvidence] = []
        try:
            raw = json.loads(r["evidence_json"]) if r["evidence_json"] else []
            evidence_list = [KnowledgeEvidence(**e) for e in raw]
        except (json.JSONDecodeError, TypeError):
            pass
        return KnowledgeRule(
            rule_id=r["rule_id"],
            rule_type=r["rule_type"],
            category=r["category"],
            field_name=r["field_name"],
            pattern=r["pattern"],
            confidence=r["confidence"],
            status=r["status"],
            version=r["version"],
            rollback_version=r["rollback_version"],
            created_from_correction=r["created_from_correction"],
            approved_by=r["approved_by"],
            evidence=evidence_list,
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            usage_count=r["usage_count"],
            success_count=r["success_count"],
            fail_count=r["fail_count"],
        )

    # --- Aliases ---

    def save_alias(self, alias: KnowledgeAlias) -> KnowledgeAlias:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO knowledge_aliases (source, target, field_name, confidence,
               is_builtin, status, evidence_json, created_at, usage_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (alias.source, alias.target, alias.field_name, alias.confidence,
             1 if alias.is_builtin else 0, alias.status,
             json.dumps([e.to_dict() for e in alias.evidence]),
             alias.created_at or _utcnow(), alias.usage_count),
        )
        conn.commit()
        return alias

    def get_aliases(self, field: Optional[str] = None,
                    source: Optional[str] = None,
                    status: Optional[str] = None) -> list[KnowledgeAlias]:
        conn = self._get_conn()
        parts = ["SELECT * FROM knowledge_aliases WHERE 1=1"]
        params: list[Any] = []
        if field:
            parts.append("AND field_name = ?")
            params.append(field)
        if source:
            parts.append("AND source = ?")
            params.append(source)
        if status:
            parts.append("AND status = ?")
            params.append(status)
        parts.append("ORDER BY is_builtin DESC, confidence DESC")
        rows = conn.execute(" ".join(parts), params).fetchall()
        return [self._row_to_alias(r) for r in rows]

    def get_learned_aliases(self, field: Optional[str] = None) -> list[KnowledgeAlias]:
        conn = self._get_conn()
        parts = ["SELECT * FROM knowledge_aliases WHERE is_builtin = 0"]
        params: list[Any] = []
        if field:
            parts.append("AND field_name = ?")
            params.append(field)
        parts.append("ORDER BY confidence DESC")
        rows = conn.execute(" ".join(parts), params).fetchall()
        return [self._row_to_alias(r) for r in rows]

    def count_aliases(self) -> int:
        conn = self._get_conn()
        return conn.execute("SELECT COUNT(*) FROM knowledge_aliases").fetchone()[0]

    def _row_to_alias(self, r: sqlite3.Row) -> KnowledgeAlias:
        evidence_list: list[KnowledgeEvidence] = []
        try:
            raw = json.loads(r["evidence_json"]) if r["evidence_json"] else []
            evidence_list = [KnowledgeEvidence(**e) for e in raw]
        except (json.JSONDecodeError, TypeError):
            pass
        return KnowledgeAlias(
            source=r["source"],
            target=r["target"],
            field_name=r["field_name"],
            confidence=r["confidence"],
            is_builtin=bool(r["is_builtin"]),
            status=r["status"],
            evidence=evidence_list,
            created_at=r["created_at"],
            usage_count=r["usage_count"],
        )

    # --- History ---

    def save_history(self, entry: RuleHistory) -> RuleHistory:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO knowledge_history (rule_id, version, previous_status,
               new_status, accuracy_before, accuracy_after, reason, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (entry.rule_id, entry.version, entry.previous_status, entry.new_status,
             entry.accuracy_before, entry.accuracy_after, entry.reason,
             entry.timestamp or _utcnow()),
        )
        conn.commit()
        entry.history_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return entry

    def get_history(self, rule_id: Optional[str] = None) -> list[RuleHistory]:
        conn = self._get_conn()
        if rule_id:
            rows = conn.execute(
                "SELECT * FROM knowledge_history WHERE rule_id = ? ORDER BY timestamp DESC",
                (rule_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM knowledge_history ORDER BY timestamp DESC"
            ).fetchall()
        return [self._row_to_history(r) for r in rows]

    def _row_to_history(self, r: sqlite3.Row) -> RuleHistory:
        return RuleHistory(
            history_id=r["id"],
            rule_id=r["rule_id"],
            version=r["version"],
            previous_status=r["previous_status"],
            new_status=r["new_status"],
            accuracy_before=r["accuracy_before"],
            accuracy_after=r["accuracy_after"],
            reason=r["reason"],
            timestamp=r["timestamp"],
        )

    # --- Shadow Comparisons ---

    def save_shadow(self, comp: ShadowComparison) -> ShadowComparison:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO shadow_comparisons (document_id, field_name,
               parser_value, parser_confidence, knowledge_value,
               knowledge_confidence, knowledge_rule_id, knowledge_rule_version,
               winner, difference, evidence_text, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (comp.document_id, comp.field_name,
             str(comp.parser_value) if comp.parser_value is not None else None,
             comp.parser_confidence,
             str(comp.knowledge_value) if comp.knowledge_value is not None else None,
             comp.knowledge_confidence, comp.knowledge_rule_id,
             comp.knowledge_rule_version, comp.winner,
             1 if comp.difference else 0, comp.evidence_text,
             comp.timestamp or _utcnow()),
        )
        conn.commit()
        comp.comparison_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return comp

    def get_shadow_comparisons(self, field_name: Optional[str] = None,
                               limit: int = 100) -> list[ShadowComparison]:
        conn = self._get_conn()
        if field_name:
            rows = conn.execute(
                "SELECT * FROM shadow_comparisons WHERE field_name = ? ORDER BY timestamp DESC LIMIT ?",
                (field_name, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM shadow_comparisons ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_shadow(r) for r in rows]

    def _row_to_shadow(self, r: sqlite3.Row) -> ShadowComparison:
        return ShadowComparison(
            comparison_id=r["id"],
            document_id=r["document_id"],
            field_name=r["field_name"],
            parser_value=r["parser_value"],
            parser_confidence=r["parser_confidence"],
            knowledge_value=r["knowledge_value"],
            knowledge_confidence=r["knowledge_confidence"],
            knowledge_rule_id=r["knowledge_rule_id"],
            knowledge_rule_version=r["knowledge_rule_version"],
            winner=r["winner"],
            difference=bool(r["difference"]),
            evidence_text=r["evidence_text"],
            timestamp=r["timestamp"],
        )

    # --- Maintenance ---

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self):
        self.close()
