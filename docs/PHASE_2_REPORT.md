# FASE 2 — Modelos de Documento Internos

## Estado: COMPLETADO ✓

### Entregables

| Entregable | Archivo | Estado |
|---|---|---|
| Modelos de dominio (Document, Page, Section, Field) | `backend/app/v2/document/models.py` | ✓ |
| Modelos OCR (OCRWord, OCRBlock, OCRPage, OCRDocument) | `backend/app/v2/ocr/models.py` | ✓ |
| Modelos de evidencia (Evidence, ExtractedField) | `backend/app/v2/evidence/models.py` | ✓ |
| Servicio de evidencia (EvidenceService) | `backend/app/v2/evidence/service.py` | ✓ |
| Tests de modelos de documento | `backend/app/v2/tests/test_document_models.py` | 20 tests ✓ |
| Tests de modelos OCR | `backend/app/v2/tests/test_ocr_models.py` | 10 tests ✓ |
| Tests de servicio de evidencia | `backend/app/v2/tests/test_evidence_service.py` | 18 tests ✓ |

### Resultados de tests

**48 tests — 48 passed, 0 failed, 0 errors**

### Principios implementados

1. **Parser nunca infiere valores** — los únicos estados posibles son `found`, `not_found`, `requires_review` (definidos en `PARSER_ALLOWED_STATES`)
2. **Evidence System** — cada decisión de extracción registra fuente, confianza y transformaciones mediante un builder pattern
3. **OCR → Domain conversion** — `OCRDocument.to_domain_document()` convierte modelos OCR a modelos de dominio con mapeo de tipos seguro
4. **Sin dependencia de Claude/Vision** — los modelos son puramente Python, sin SQLAlchemy ni dependencias externas
5. **Inmutabilidad de reglas** — las reglas de migración (V2_MIGRATION_RULES.md) no se modificaron

### Fix aplicado

- `to_domain_document()` en `ocr/models.py` ahora convierte `doc_type` string a `DocumentType` enum con fallback a `UNKNOWN`

### Próximo paso

FASE 3 — Módulo OCR (integración con Tesseract / procesamiento de imágenes)
