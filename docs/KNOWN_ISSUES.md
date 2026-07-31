# Known Issues — RemateUp V1 → V2 Migration

## Critical Issues

### 1. Correcciones Table Not Created
- **Status:** BUG
- **Severity:** HIGH
- **Found:** 2026-07-30
- **Description:** The `correcciones` table defined in `backend/app/models.py` (line 114-133) is never created in the SQLite database. The `Base.metadata.create_all()` in `main.py` should create it, but the database only has 4 tables: `documentos`, `auditoria`, `avisos`, `aprobaciones`.
- **Impact:** Learning system cannot persist corrections. The V1 "aprendizaje" feature (loading corrections into Claude prompts) is non-functional.
- **Root cause:** Likely the `_migrar_columnas()` function in `main.py` adds columns but doesn't ensure the `correcciones` table exists. The `create_all` may be creating the table but the schema check in the audit didn't find it — further investigation needed.
- **Workaround:** V2 knowledge engine uses in-memory storage (`MemoryKnowledgeRepository`) until Phase 12 migration.

### 2. Duplicated Avisos in Dataset
- **Status:** DATA_QUALITY
- **Severity:** MEDIUM
- **Found:** 2026-07-30
- **Details:** Document #2 (Panama newspaper) contains 20 avisos, of which:
  - 4 avisos share `expediente=1029202000030580` with identical data (IDs 17-20)
  - 15 avisos share `expediente=2724202000000300` with identical data (IDs 22-36)
  - These are either the same aviso published on different dates (republicaciones legales) or OCR extraction duplicates
- **Impact:** Inflated aviso count. Pipeline counted 20 avisos from doc#2 when there are at most 3 unique cases.
- **Fix needed:** V2 deduplication logic must detect and merge these.

### 3. Validation Simplified to No-op
- **Status:** TECH_DEBT
- **Severity:** HIGH
- **Found:** 2026-07-30
- **File:** `backend/app/pipeline/validation.py` line 49
- **Description:** `evaluar_duplicado_o_republicacion()` always returns `{"tipo": "nuevo"}` — no actual duplicate detection or republication logic runs.
- **Code:**
  ```python
  def evaluar_duplicado_o_republicacion(db, datos: dict) -> dict:
      """Simplificado - siempre retorna nuevo para evitar problemas con la BD."""
      return {"tipo": "nuevo"}
  ```
- **Impact:** Duplicate avisos are not detected. The republication legal window logic is disabled.
- **Fix needed:** V2 validation engine must implement real duplicate detection.

### 4. Missing Tests
- **Status:** TECH_DEBT
- **Severity:** HIGH
- **Description:** Zero test files exist in the entire repository (before Phase 1).
- **Impact:** Any change risks regression. No way to verify V2 matches V1 accuracy.

### 5. Pipeline Extraction Monolith (890 lines)
- **Status:** TECH_DEBT
- **Severity:** MEDIUM
- **File:** `backend/app/pipeline/extraction.py`
- **Description:** Single file handles: prompt construction, Claude API calls, Gemini API calls, JSON parsing, deduplication, fusion, text segmentation, document boundary marking, learning injection.
- **Impact:** Hard to maintain, test, or modify specific extraction behavior.
- **Fix:** V2 separates this into: segmenter → parser → normalization → evidence.

### 6. Mixed OCR and Extraction Responsibilities
- **Status:** ARCHITECTURE
- **Severity:** LOW
- **File:** `backend/app/pipeline/extraction.py` lines 771-890
- **Description:** The `extraer()` function decides whether to call Vision OCR or Claude directly, mixing OCR responsibility with extraction logic.
- **Fix:** V2 separates OCR client, OCR processor, and OCR mapper into distinct modules.

### 7. No Shadow Mode in Production
- **Status:** MISSING_FEATURE
- **Severity:** MEDIUM
- **Description:** V1 pipeline runs without shadow comparison. No way to compare V2 results against V1 for the same document without manual effort.
- **Fix:** V2 pipeline orchestrator includes shadow mode coordinator.

## Non-Critical Issues

### 8. Image Tiler Specific to Claude
- **File:** `backend/app/pipeline/image_tiler.py`
- **Description:** Only needed for Claude's image resolution limits. Will be deprecated when Claude is removed.

### 9. WhatsApp Bridge Reliability
- **File:** `whatsapp-bridge/index.js`
- **Description:** Baileys (non-official WhatsApp library) can disconnect. No persistent session recovery beyond auto-reconnect.

### 10. Platform Uploader in Simulation Mode
- **File:** `backend/app/upload/platform_uploader.py`
- **Description:** `SIMULACION_ACTIVA = True` — no actual platform upload occurs.
