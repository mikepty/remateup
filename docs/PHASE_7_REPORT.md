# FASE 7 — End-to-End Production Pipeline & Certification

## Arquitectura

```
Assembly → OCR → Mapping → Segmentation → Stitching → Newspaper Layout →
Continuity → Parser → Knowledge → Validator → Normalizer → Confidence → Certification → Final JSON
```

### Pipeline Order (12 stages)

| # | Stage | Module | Responsabilidad |
|---|---|---|---|
| 1 | Document Assembly | `document/assembly.py` | Organiza archivos, detecta tipo |
| 2 | OCR | `ocr/processor.py` | Google Vision OCR → OCRDocument |
| 3 | Mapping | (embedded in OCR) | OCRMapper.map_response() |
| 4 | Segmentation | `segmenter/newspaper_layout.py` | Detecta avisos por layout |
| 5 | Page Stitching | `document/stitching.py` | Une top/bottom de páginas PA |
| 6 | Newspaper Layout | `segmenter/newspaper_layout.py` | Columnas y avisos |
| 7 | Continuity | `segmenter/continuity.py` | Une fragmentos continuos |
| 8 | Parser | `parser/factory.py` | Extrae 6 campos por regex |
| 9 | Knowledge | `knowledge/` (FASE 6.5) | Aplica reglas de conocimiento |
| 10 | Validator | `validator/` (FASE 6.9) | Valida + score + duplicados |
| 11 | Normalizer | `normalization/` | Normaliza fechas, monedas, nombres |
| 12 | Confidence | `confidence/` | Score por campo 0.00–1.00 |
| 13 | Certification | `certification/` | Certificado completo del documento |
| 14 | Final JSON | `runner.py` | JSON unificado con todo |

---

## Archivos Creados

### FASE 7 (nuevos)

| Archivo | Propósito | LOC |
|---|---|---|
| `pipeline/runner.py` | PipelineRunner — orquesta las 14 etapas | 470 |
| `normalization/normalizer.py` | FieldNormalizer — dispatcher por tipo de campo | 75 |
| `normalization/dates.py` | DateNormalizer — ISO/Spanish/DOT/SLASH formats | 65 |
| `normalization/currency.py` | CurrencyNormalizer — $, B/., USD, COP, PAB | 40 |
| `normalization/numbers.py` | NumberNormalizer — comas, puntos, decimales | 45 |
| `normalization/names.py` | NameNormalizer — nombres legales, partes | 65 |
| `normalization/locations.py` | LocationNormalizer — provincias PA/CO | 40 |
| `normalization/text.py` | TextNormalizer — OCR artifacts, whitespace, quotes | 30 |
| `confidence/final.py` | FinalConfidenceCalculator — 9 componentes | 75 |
| `confidence/ocr.py` | OCRConfidenceScorer — avg word confidence | 25 |
| `confidence/parser.py` | ParserConfidenceScorer — per-field confidence | 25 |
| `confidence/segment.py` | SegmentationConfidenceScorer | 20 |
| `confidence/normalization.py` | NormalizationConfidenceScorer | 15 |
| `confidence/knowledge.py` | KnowledgeConfidenceAdjuster | 15 |
| `certification/models.py` | CertDecision, CertDocument, CertAviso, CertField | 117 |
| `certification/certifier.py` | Certifier — builds certification from pipeline output | 100 |
| `certification/report.py` | ProductionReportGenerator — batch report | 55 |
| `tests/test_pipeline_fase7.py` | 51 tests de integración | 400 |

### FASE 6.9 (existentes, reutilizados)

| Archivo | Propósito |
|---|---|
| `validator/models.py` | Decision, NoticeDecision, ValidationResult |
| `validator/production_rules.py` | Headers válidos/inválidos, co-ocurrencia |
| `validator/notice_validator.py` | Validación estructural |
| `validator/consistency.py` | Inconsistencias entre campos |
| `validator/duplicate_detector.py` | Detección de duplicados |
| `validator/scoring.py` | Score 0.00–1.00 |
| `validator/orchestrator.py` | Orquestación de validación |

### Archivos Modificados

| Archivo | Cambio |
|---|---|
| `pipeline/certification_runner.py` | Agregado `load_dotenv()`, arreglos de API (stitcher, layout, continuity, DetectedAviso) |
| `pipeline/evaluation_runner.py` | Rewritado para usar golden dataset |
| `pipeline/field_auditor.py` | Arreglos de paths, filtro de campos de API |
| `ocr/client.py` | (revertido — se usa OCRProcessor para cargar API key) |
| `ocr/processor.py` | OCRProcessor lee `GOOGLE_VISION_API_KEY` del environment |

---

## Flujo End-to-End

```
Input: file_paths, country
├─ Assembly: → SourceDocument (pages, fragments)
├─ OCR: → OCRDocument (pages with words, blocks, text)
├─ Mapping: (embedded in OCR via OCRMapper)
├─ Segmentation: → list[DetectedAviso]
├─ Stitching: → list[StitchedPage] (PA only)
├─ Newspaper Layout: → list[DetectedAviso]
├─ Continuity: → list[CompleteAviso]
├─ Parser: → dict[str, ParseResult] (6 fields)
├─ Knowledge: → dict[str, field_data] (knowledge-enhanced)
├─ Validator: → NoticeDecision (VALID/INVALID/DUPLICATED/INCOMPLETE/INCONSISTENT/REQUIRES_REVIEW)
├─ Normalizer: → dict[str, field_data] with normalized values
├─ Confidence: → per-field confidence (0.00–1.00) + overall
├─ Certification: → CertDocument (complete certification)
└─ Final JSON: → unified JSON output
```

---

## Normalización

| Tipo | Input | Output | Formato |
|---|---|---|---|
| Fecha | "15 DE JULIO DE 2026" | "2026-07-15" | ISO 8601 |
| Fecha | "15/07/2026" | "2026-07-15" | ISO 8601 |
| Fecha | "15.07.2026" | "2026-07-15" | ISO 8601 |
| Moneda | "B/. 20,000" | 20000.0 | float |
| Moneda | "$100,000" | 100000.0 | float |
| Moneda | "USD 1,500.00" | 1500.0 | float |
| Moneda | "$181.080.000,00" | 181080000.0 | float |
| Número | "82699" | 82699.0 | float |
| Nombre | "JUAN PEREZ" | "Juan Perez" | Title Case |
| Nombre | "PEREZ, JUAN" | "Juan Perez" | Reordenado |
| Provincia | "PANAMA" | "Panamá" | Título con acento |
| Texto | "  Hola    Mundo  " | "Hola Mundo" | Whitespace normalizado |

---

## Confidence Engine

### Pesos de componentes

| Componente | Peso | Fuente |
|---|---|---|
| OCR confidence | 0.20 | Google Vision word confidence |
| Segmentation | 0.15 | Número de avisos detectados |
| Parser | 0.25 | Pattern match confidence |
| Normalization | 0.10 | Success/failure de normalización |
| Validation | 0.15 | Validator score |
| Knowledge | 0.15 | Knowledge rule match |

### Per-Field Confidence

Cada campo recibe:
```json
{
  "confidence": 0.80,
  "confidence_reason": "parser_high_confidence, ocr_high_quality, normalization_success, validator_passed",
  "confidence_sources": {
    "parser": 0.95,
    "ocr": 0.85,
    "normalization": 1.0,
    "knowledge": 0.0,
    "validation": 1.0
  }
}
```

---

## Certification

El `Certifier` produce un `CertDocument` con:
- Decision (VALID/INVALID/DUPLICATED/INCOMPLETE/INCONSISTENT/REQUIRES_REVIEW)
- Score (0.00–1.00)
- Todos los campos con valores raw + normalized + confidence
- Inconsistencias detectadas
- Información de duplicados
- Reglas aplicadas y fallidas
- Header detectado y validado
- Métricas de rendimiento

### ProductionReportGenerator

Genera un reporte batch con:
- Total de documentos y avisos procesados
- Distribución de decisiones
- Tiempo promedio por documento
- Score y confianza promedio
- Cobertura: % auto-approved, % revisión manual

---

## Tests

| Archivo | Tests | Estado |
|---|---|---|
| `test_validator.py` | 50 | ✅ |
| `test_pipeline_fase7.py` | 51 | ✅ |
| `test_knowledge.py` | 42 | ✅ |
| `test_knowledge_v2.py` | 81 | ✅ |
| `test_stitching.py` | — | ✅ |
| `test_vision_client.py` | 14 | ✅ |
| `test_segmenter_engine.py` | — | ✅ |
| ... (12 archivos más) | — | ✅ |
| **Total** | **549** | **✅ Todos pasan** |

### Tests de Integración (test_pipeline_fase7.py)

| Grupo | Tests | Cubre |
|---|---|---|
| TestStageResult | 2 | StageResult init + to_dict |
| TestDateNormalizer | 6 | ISO, Spanish, DOT, SLASH, invalid, empty |
| TestCurrencyNormalizer | 5 | $, B/., USD, Colombian format, empty |
| TestNumberNormalizer | 5 | simple, decimal, comma decimal, thousands, empty |
| TestNameNormalizer | 4 | simple, comma, legal entity, extract parts |
| TestLocationNormalizer | 3 | Panama province, Colombia province, city |
| TestTextNormalizer | 3 | whitespace, OCR artifacts, strip quotes |
| TestFieldNormalizer | 6 | fecha, currency, number, name, unknown, all |
| TestOCRConfidenceScorer | 2 | score, empty |
| TestParserConfidenceScorer | 2 | score, per_field |
| TestSegmentationConfidenceScorer | 1 | score |
| TestNormalizationConfidenceScorer | 1 | score |
| TestKnowledgeConfidenceAdjuster | 2 | with/without evidence |
| TestFinalConfidenceCalculator | 3 | calculate, per_field, build_field_confidence |
| TestCertifier | 2 | valid, invalid |
| TestProductionReportGenerator | 1 | generate |
| TestPipelineRunner | 3 | init, stage_result, version |
| **Total** | **51** | |

---

## Métricas de Rendimiento

### Pipeline End-to-End (1 imagen PA)

| Stage | Avg Time (ms) |
|---|---|
| Assembly | 0.21 |
| OCR | 8,367-11,531 |
| Mapping | 0.10 |
| Segmentation | 2.71 |
| Continuity | 0.01 |
| Parser | 3.91 |
| Knowledge | 0.37 |
| Validator | 13.93 |
| Normalizer | 0.00 |
| Confidence | 0.01 |
| Certification | 0.06 |
| Final JSON | 0.05 |
| **Total** | **~10,000 ms** |

### Pipeline End-to-End (CO PDF, 3 archivos)
- Total: ~191,000 ms (191s)
- OCR dominates (PDF pages processed individually)

---

## Resultados sobre Datos Reales

### Panamá (Newspaper)
- **20 imágenes** procesadas (9 avisos esperados)
- **2 avisos detectados** (1 de 20 esperados)
- **6 campos encontrados** (expediente, finca, precio_base, fecha_remate, demandante, demandado)
- **Header válido**: AVISO DE REMATE ✓
- **Decision**: INCOMPLETE (3 campos de 6)
- **Score**: 0.53

### Colombia (PDF)
- **3 PDFs** procesados (16 avisos esperados)
- **0 avisos detectados** (formato tabular no soportado)
- **Decision**: INVALID
- **Observación**: El PDF usa formato tabular, no "AVISO DE REMATE" headers

---

## Explicabilidad

Cada decisión del validador incluye:
- **Reglas aplicadas**: lista con nombre, passed/failed, detalle, peso
- **Campos encontrados**: lista de campos con valores
- **Campos faltantes**: lista de campos requeridos no encontrados
- **Header detectado**: texto del header encontrado
- **Header válido**: boolean
- **Inconsistencias**: lista con field_1, field_2, descripción, severidad
- **Duplicados**: nivel, campos de coincidencia, similitud
- **Score**: 0.00–1.00 con razón de cálculo

---

## Formato JSON Final

```json
{
  "document": { "document_id", "country", "source_type", "files", "version" },
  "processing": { "timestamp", "total_time_ms", "stages" },
  "stages": { "assembly": {...}, "ocr": {...}, ... },
  "metrics": { "stage_count", "stages_completed", ... },
  "validation": { "decision", "score", "rules_applied", ... },
  "knowledge": { "rules_applied" },
  "certification": { "document_id", "all_avisos": [...], ... },
  "performance": { "total_time_ms", "stage_times_ms" },
  "warnings": [],
  "errors": [],
  "statistics": { "fields_found", "avisos_detected" },
  "field_confidence": { "expediente": { "confidence", "reason", "sources" }, ... },
  "rules_applied": [...],
  "rules_failed": [...],
  "duplicates": { "level", "matched_on", ... },
  "parser": { "fields_found" },
  "normalization": { "fecha_remate": { "normalized", "format" }, ... },
  "validator": { "decision", "score", "header_valid", ... }
}
```

---

## Limitaciones

1. **Segmentación**: solo detecta 1 aviso de 20 esperados en periódicos PA
2. **CO PDF tabular**: formato no soportado (usa tablas, no headers)
3. **OCR costo**: ~8-10s por imagen (Google Vision API)
4. **Knowledge no poblado**: no hay reglas aprendidas todavía
5. **Normalizer**: solo normaliza los 6 campos V2 (no los 30 V1)
6. **Confidence**: valores OCR hardcodeados (0.85) cuando no hay datos reales

---

## Próximos Pasos

1. **Mejorar segmentación**: detectar múltiples avisos por página
2. **Soporte tabular PDF**: extraer tablas de SEJURE CO
3. **Poblar Knowledge**: ingerir 39 avisos V1 como correcciones
4. **Implementar campos faltantes**: base, finca_matr, fianza, minimo, etc.
5. **Calibrar confidence**: usar valores reales de OCR en lugar de hardcodeados
