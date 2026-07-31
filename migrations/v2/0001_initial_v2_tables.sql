-- V2 Migration: New tables for V2 document processing pipeline
-- This migration DOES NOT modify existing V1 tables.
-- All new tables coexist with V1 schema.
-- Migration will be applied via Alembic or manual SQL in Phase 12.

-- Core Document Model (independent representation, NOT tied to Vision)
CREATE TABLE v2_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id INTEGER,                 -- references V1 documentos.id when applicable
    document_type TEXT NOT NULL DEFAULT 'unknown',  -- newspaper_page, pdf_tabular, pdf_scanned, individual_image
    pais TEXT NOT NULL CHECK(pais IN ('PA', 'CO')),
    raw_text TEXT,                       -- full OCR text
    source_paths TEXT,                   -- JSON array of file paths
    status TEXT DEFAULT 'pending',       -- pending, processing, completed, error
    confidence REAL DEFAULT 0.0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Document Pages (domain level, references OCR blocks separately)
CREATE TABLE v2_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES v2_documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    width INTEGER,
    height INTEGER,
    text TEXT,
    UNIQUE(document_id, page_number)
);

-- OCR Blocks (from Vision or other OCR engines)
CREATE TABLE v2_ocr_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL REFERENCES v2_pages(id) ON DELETE CASCADE,
    block_type TEXT DEFAULT 'text',      -- text, table, picture, etc.
    text TEXT,
    confidence REAL DEFAULT 0.0,
    x0 INTEGER, y0 INTEGER, x1 INTEGER, y1 INTEGER,
    words_json TEXT                      -- JSON array of OCRWord: [{text, confidence, x0, y0, x1, y1, break_type}]
);

-- Document Sections (semantic structure)
CREATE TABLE v2_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES v2_documents(id) ON DELETE CASCADE,
    section_type TEXT NOT NULL,           -- header, property, location, values, description, parties, footer
    text TEXT,
    page INTEGER,
    confidence REAL DEFAULT 0.0,
    bounding_box TEXT,                   -- JSON
    parent_section_id INTEGER REFERENCES v2_sections(id)
);

-- Extracted Fields (results of parsing)
CREATE TABLE v2_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES v2_documents(id) ON DELETE CASCADE,
    aviso_id INTEGER,                    -- references V1 avisos.id when applicable
    field_name TEXT NOT NULL,
    value TEXT,
    raw_value TEXT,
    state TEXT DEFAULT 'not_found',      -- found, not_found, requires_review
    confidence REAL DEFAULT 0.0,
    normalized_value TEXT,
    section_id INTEGER REFERENCES v2_sections(id),
    page INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Extraction Evidence (tracing every decision)
CREATE TABLE v2_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id INTEGER REFERENCES v2_fields(id) ON DELETE CASCADE,
    field_name TEXT NOT NULL,
    value TEXT,
    raw_value TEXT,
    state TEXT DEFAULT 'not_found',
    evidence_type TEXT NOT NULL,          -- ocr_text, ocr_position, segment_context, label_value_relation, parser_pattern, normalization, knowledge_rule, manual_correction
    confidence REAL DEFAULT 0.0,
    source TEXT,
    transformation_log TEXT,             -- JSON array of transformations applied
    document_id INTEGER,
    page INTEGER DEFAULT 0,
    block_id INTEGER,
    bounding_box TEXT,                   -- JSON
    created_at TEXT DEFAULT (datetime('now'))
);

-- Knowledge Base
CREATE TABLE v2_knowledge_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    rule_type TEXT NOT NULL,              -- correction, transformation, validation, inference, layout
    status TEXT DEFAULT 'candidate',      -- candidate, approved, active, disabled, expired
    field_name TEXT,
    condition TEXT,
    action TEXT,
    source TEXT DEFAULT 'system',
    confidence REAL DEFAULT 0.5,
    frequency INTEGER DEFAULT 1,
    min_frequency INTEGER DEFAULT 3,
    evidence_ids TEXT,                   -- JSON array
    country TEXT,
    created_by TEXT DEFAULT 'system',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE v2_knowledge_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_name TEXT NOT NULL,
    alias TEXT NOT NULL,
    canonical TEXT NOT NULL,
    language TEXT DEFAULT 'es',
    confidence REAL DEFAULT 1.0,
    is_active INTEGER DEFAULT 1,
    frequency INTEGER DEFAULT 0,
    UNIQUE(field_name, alias)
);

CREATE TABLE v2_knowledge_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_name TEXT NOT NULL,
    pattern TEXT NOT NULL,
    description TEXT,
    confidence REAL DEFAULT 1.0,
    is_active INTEGER DEFAULT 1,
    frequency INTEGER DEFAULT 0,
    country TEXT
);

CREATE TABLE v2_knowledge_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    correction_id INTEGER,
    aviso_id INTEGER,
    field_name TEXT NOT NULL,
    original_value TEXT,
    corrected_value TEXT,
    context TEXT,
    pattern_detected TEXT,
    pais INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE v2_knowledge_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    total_corrections INTEGER DEFAULT 0,
    rules_created INTEGER DEFAULT 0,
    rules_activated INTEGER DEFAULT 0,
    rules_rejected INTEGER DEFAULT 0,
    fields_improving TEXT,               -- JSON
    recorded_at TEXT DEFAULT (datetime('now'))
);

-- Indexes for performance
CREATE INDEX idx_v2_pages_document ON v2_pages(document_id);
CREATE INDEX idx_v2_fields_document ON v2_fields(document_id);
CREATE INDEX idx_v2_fields_aviso ON v2_fields(aviso_id);
CREATE INDEX idx_v2_evidence_field ON v2_evidence(field_id);
CREATE INDEX idx_v2_sections_document ON v2_sections(document_id);
CREATE INDEX idx_v2_knowledge_rules_status ON v2_knowledge_rules(status);
CREATE INDEX idx_v2_knowledge_aliases_field ON v2_knowledge_aliases(field_name);
