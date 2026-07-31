# V2 Migration Rules — RemateUp

## Core Principle
V2 architecture is **temporal coexistence**. V1 remains the production pipeline.
V2 runs in parallel until validated against the Golden Dataset.

## Immutable Rules

### 1. V1 Remains Intact Until Phase 16
- No file in `backend/app/pipeline/` is modified.
- No file in `backend/app/routers/` is modified.
- No file in `backend/app/upload/` is modified.
- No file in `backend/app/whatsapp/` is modified.
- No file in `frontend/` is modified.
- No file in `whatsapp-bridge/` is modified.

### 2. V2 Lives in Its Own Namespace
All V2 code goes into `backend/app/v2/`.
No V2 import crosses into V1 modules.
V1 never imports from V2.

### 3. Progressive Migration
```
Phase 1-11:  Build V2 modules (no deployment)
Phase 12:    Database migration (new tables only)
Phase 13:    Frontend panels (new read-only views)
Phase 14:    Shadow Mode (both pipelines run, V1 is source of truth)
Phase 15:    Testing and comparison against Golden Dataset
Phase 16:    ONLY if V2 >= V1 accuracy: flip default to V2
Phase 17:    Remove V1 code (Claude, prompts, old pipeline)
```

### 4. No Destructive Changes
- Never ALTER TABLE on V1 tables.
- Never DROP COLUMN on V1 tables.
- Never DELETE records from V1 tables.
- New V2 tables use `v2_` prefix or separate schema.

### 5. Shadow Mode Protocol
In Shadow Mode:
```
Document → V1 Pipeline → V1 Result (production)
        → V2 Pipeline → V2 Result (shadow)
                          ↓
                   Comparator → Comparison Report
```
V2 result is NEVER written to production DB.
V2 result is NEVER sent to WhatsApp or platform upload.
V2 never triggers side effects.

### 6. Database Coexistence
```
V1 tables:          documentos, avisos, aprobaciones, auditoria, correcciones
V2 tables:          v2_documents, v2_pages, v2_ocr_blocks, v2_sections,
                    v2_fields, v2_knowledge_*, v2_evidence
```
No foreign keys between V1 and V2 tables.
Documents can be processed by both pipelines independently.

### 7. Parser V2 Rules
- NEVER infer values not found in the document.
- Allowed states: FOUND, NOT_FOUND, REQUIRES_REVIEW.
- Never invent probabilistic values.
- Every extracted value must have evidence.
- Evidence format: what was found, where, with what confidence.

### 8. Learning/AI Constraints
- No Claude API calls in V2 code.
- No Gemini API calls in V2 extraction (only OCR).
- Knowledge engine learns from user corrections only.
- No single correction becomes a rule automatically.
- Rule requires: ≥3 occurrences + evidence + approval.

### 9. Rollback Strategy
If V2 produces worse results than V1 for any document:
1. Shadow Mode report flags the document.
2. Pipeline reverts to V1 for that document type.
3. V2 module gets fixed before re-enabling.

### 10. Success Criteria
V2 replaces V1 only when:
- Field accuracy >= V1 baseline per Golden Dataset.
- Processing time <= 2x V1 time (initial target).
- Zero regressions on critical fields.
- Knowledge engine demonstrably improves over time.
