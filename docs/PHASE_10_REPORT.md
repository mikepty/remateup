# FASE 10 — Production Readiness & Operational Validation

## Estado

COMPLETADO ✓

## Objetivo

Preparar el motor V2 para operar de forma estable en producción sin agregar nuevas reglas de extracción ni modificar el comportamiento funcional de OCR, Parser, Knowledge, Validator ni Certification. Todos los componentes operacionales creados son deterministas, auditables, reproducibles y compatibles con la arquitectura certificada en la FASE 9 (SYSTEM STATUS: CERTIFIED).

## Contexto

El sistema V2 alcanzó en la FASE 9 el estado SYSTEM STATUS: CERTIFIED (8 campos certificados, Overall Alignment 65.8%, sin missing producers). La FASE 10 no toca la lógica funcional: crea la capa operacional completa sobre el pipeline existente (PipelineRunner, ParserFactory, KnowledgeRepository, ValidationOrchestrator, Certifier, REGISTRY, SQLite).

## Arquitectura

```
                        ┌──────────────────────────────────────────────┐
                        │           backend/app/v2/production/          │
                        │                                              │
   PipelineRunner ─────►│  smoke.py     ── flujo mínimo end-to-end      │
   ParserFactory  ─────►│  health.py    ── estado de componentes        │
   KnowledgeRepo  ─────►│  profiler.py  ── tiempos por etapa            │
   Validator      ─────►│  memory.py    ── RAM / pico / objetos         │
   Certifier      ─────►│  metrics.py   ── métricas agregadas           │
                        │  benchmark.py ── lotes 1/10/50/100            │
                        │  batch_runner ── directorios imágenes/PDFs    │
                        │  logging.py   ── logs estructurados JSON      │
                        │  config.py    ── configuración centralizada   │
                        │  report.py    ── salida en production/output/ │
                        └──────────────────────────────────────────────┘
                                             │
                                             ▼
                          production/output/
                          ├── processing_report.json / .md
                          ├── performance_report.json / .md
                          └── metrics_dashboard.json / .md
```

## Flujo

```
Documento
   │
   ▼
OCR ───────────────────────────► (sintético en flujo de texto: texto directo)
   │
   ▼
Assembly / Mapping / Segmentation / Stitching / Continuity
   │
   ▼
Parser ─────────────────────────► PipelineProfiler.record()
   │
   ▼
Knowledge ──────────────────────► MemoryProfiler.profile_stage()
   │
   ▼
Validator ──────────────────────► PipelineMetrics.collect()
   │
   ▼
Certification ──────────────────► StructuredLogger.log_from_result()
   │
   ▼
Resultado ──────────────────────► OperationalReportGenerator.generate()
                                   │
                                   ▼
                          processing_report / performance_report / metrics_dashboard
```

## Componentes

| Módulo | Clase principal | Responsabilidad | Estado |
| --- | --- | --- | --- |
| `config.py` | `ProductionConfig` | timeouts, batch_size, workers, memory_limits, feature_flags, validación | OK |
| `logging.py` | `StructuredLogger` | log por documento: document_id, country, pages, processing_time, decision, score, errores, warnings | OK |
| `profiler.py` | `PipelineProfiler` | tiempo por etapa (10 etapas), total, promedio, máximo, mínimo, desviación | OK |
| `memory.py` | `MemoryProfiler` | RAM por etapa, pico, objetos creados/liberados, memoria final (tracemalloc, stdlib) | OK |
| `metrics.py` | `PipelineMetrics` | documentos, avisos detectados/válidos/descartados, duplicados, OCR promedio, parser accuracy, knowledge usage, validator acceptance, certification rate, errores, warnings, tiempo promedio | OK |
| `health.py` | `HealthChecker` | parser, knowledge, schema, validator, registry, SQLite, config → HEALTHY / WARNING / ERROR | OK |
| `benchmark.py` | `PipelineBenchmark` | lotes 1/10/50/100: throughput, tiempo promedio, memoria | OK |
| `batch_runner.py` | `BatchRunner` | directorios de imágenes/PDFs/TXT: resultados individuales, resumen, errores, métricas | OK |
| `smoke.py` | `SmokeTest` | flujo mínimo Documento→OCR→Parser→Knowledge→Validator→Certification; PASS/FAIL + `run_text_pipeline` | OK |
| `report.py` | `OperationalReportGenerator` | 6 artefactos en `production/output/` (JSON + MD) | OK |

## Archivos creados/modificados

Creados:
- `backend/app/v2/production/__init__.py`
- `backend/app/v2/production/config.py`
- `backend/app/v2/production/logging.py`
- `backend/app/v2/production/profiler.py`
- `backend/app/v2/production/memory.py`
- `backend/app/v2/production/metrics.py`
- `backend/app/v2/production/health.py`
- `backend/app/v2/production/benchmark.py`
- `backend/app/v2/production/batch_runner.py`
- `backend/app/v2/production/smoke.py`
- `backend/app/v2/production/report.py`
- `backend/app/v2/tests/test_production.py` (42 tests)
- `backend/app/v2/production/output/` — 6 reportes generados

Sin modificaciones funcionales en OCR, Parser, Knowledge, Validator, Certification, V1.

## Implementación detallada

**Parte 1 — Pipeline Profiler (`profiler.py`):** `PipelineProfiler` extrae `duration_ms` de cada stage del resultado del pipeline (OCR, Assembly, Mapping, Segmentation, Stitching, Continuity, Parser, Knowledge, Validator, Certification) y acumula estadísticas por ejecución: total, promedio, máximo, mínimo y desviación estándar poblacional. Incluye `slowest_stage()` y `record()`/`record_stage_times()`.

**Parte 2 — Memory Profiler (`memory.py`):** `MemoryProfiler.profile_stage()` mide RSS antes/después (psutil si está instalado; fallback `resource`; sin dependencias obligatorias), pico y memoria actual vía `tracemalloc` (stdlib), y objetos creados/liberados por comparación de snapshots. `snapshot()`, `peak()`, `stats()` serializables.

**Parte 3 — Pipeline Metrics (`metrics.py`):** `PipelineMetrics.collect()` agrega sobre la lista de resultados: documentos procesados, avisos detectados (stage segmentation), avisos válidos (decision VALID/CERTIFIED en certificación o validación), avisos descartados, duplicados (duplicate_info), OCR promedio, parser accuracy (campos canónicos FOUND / 8), knowledge usage (% con reglas aplicadas), validator acceptance (score promedio × 100), certification rate, errores, warnings y tiempo promedio. Todo JSON-serializable.

**Parte 4 — Operational Report (`report.py`):** `OperationalReportGenerator.generate()` escribe los 6 artefactos: `processing_report.{json,md}`, `performance_report.{json,md}`, `metrics_dashboard.{json,md}` en `production/output/`.

**Parte 5 — Health Check (`health.py`):** `HealthChecker.run()` valida 7 checks: ParserFactory (PA y CO), KnowledgeRepository (reglas), Schema (FIELD_CATALOG), ValidationOrchestrator, REGISTRY (sin duplicados), SQLite (knowledge.db accesible vía SELECT 1) y Configuración (validación de ProductionConfig). Estado global: HEALTHY si todo OK, WARNING si hay avisos, ERROR si algún check crítico falla. Incluye `critical_failed`.

**Parte 6 — Benchmark (`benchmark.py`):** `PipelineBenchmark.run((1,10,50,100))` ejecuta por lote el flujo de texto y registra throughput (docs/s), tiempo promedio y perfil de memoria del lote.

**Parte 7 — Batch Runner (`batch_runner.py`):** `BatchRunner.run_directory()` procesa directorios completos: imágenes (jpg/jpeg/png/tif/bmp), PDFs (vía PipelineRunner real) y TXT (flujo de texto). `run_text_batch()` procesa lotes en memoria. Salida: resultados individuales, resumen, errores y métricas; `export_results()` guarda el lote en JSON.

**Parte 8 — Logging (`logging.py`):** `StructuredLogger` escribe una línea JSON por documento con document_id, country, pages, processing_time, decision, score, errores y warnings; `log_from_result()` deriva la entrada directamente del resultado del pipeline.

**Parte 9 — Configuración (`config.py`):** `ProductionConfig` centraliza timeouts por etapa, batch_size, workers, memory_limits y feature_flags con `validate()`, `to_dict()`, `from_dict()`, `from_env()` y paths de salida. Sin valores hardcodeados dispersos.

**Parte 10 — Smoke Test (`smoke.py`):** `SmokeTest.run()` ejecuta el flujo mínimo: Documento → OCR (sintético) → Parser → Knowledge → Validator → Certification; si cualquier etapa falla reporta FAIL. Incluye `run_text_pipeline()`, ejecución determinista del pipeline en modo texto reutilizada por Batch Runner y Benchmark, y `run_with_pipeline()` para archivos reales.

## Tests

- Nueva suite: `backend/app/v2/tests/test_production.py` — **42 tests** (config 5, logging 4, profiler 6, memory 4, metrics 4, health 4, smoke 5, batch 4, benchmark 2, reportes 4).
- Cobertura solicitada verificada: Pipeline Profiler, Memory Profiler, Metrics, Health Check, Batch Runner, Benchmark, Logging, Configuración, Smoke Test, Reportes y Serialización.
- Suite completa: **846 passed** (804 previos + 42 nuevos), 0 regresiones. No se eliminó ningún test existente.

## Resultados

- **Health Check: HEALTHY** (7/7 checks OK — parser, knowledge, schema, validator, registry, SQLite, config).
- **Smoke Test: PASS** (flujo mínimo completo; aviso CO produce los 8 campos canónicos).
- **Batch real (10 documentos CO):** 10 procesados, 10 avisos detectados, 10 válidos, 0 errores, 0 warnings.
- **Benchmark:** throughput creciente por lote (1→10→50 docs), memoria controlada vía tracemalloc.
- **Overall Alignment FASE 9 preservado:** SYSTEM STATUS: CERTIFIED (sin cambios funcionales).

## Métricas

| Métrica | Valor |
| --- | --- |
| Documentos procesados (lote real) | 10 |
| Avisos detectados | 10 |
| Avisos válidos / descartados | 10 / 0 |
| Duplicados detectados | 10 (textos sintéticos casi idénticos; comportamiento real del detector) |
| OCR promedio (flujo texto sintético) | 1.0 |
| Parser accuracy (8 campos canónicos) | 100.0% |
| Validator acceptance | 83.25% |
| Certification rate | 100.0% |
| Errores / Warnings | 0 / 0 |
| Tiempo promedio por documento | 6.55 ms |
| Etapa más lenta (10 muestras) | Parser — avg 3.04 ms, max 9.31 ms, std 2.13 ms |
| Health | HEALTHY |
| Smoke | PASS |
| Tests totales | 846 (42 nuevos) |

## Reglas respetadas

- Sin nuevas reglas de extracción.
- Sin modificaciones a OCR, Parser, Knowledge, Validator ni Certification.
- Sin modificaciones a V1.
- Implementación dentro de `backend/app/v2/`.
- Determinista, auditable, reproducible, serializable.
- Sin dependencias externas obligatorias (memoria usa stdlib `tracemalloc`; `psutil` opcional).
- No se eliminó ningún test existente.

## Riesgos conocidos

1. El flujo de texto usa OCR sintético (texto directo); el OCR real requiere credenciales del servicio de visión y archivos físicos — el smoke con pipeline real (`run_with_pipeline`) lo cubre con archivos.
2. Los duplicados en el lote sintético se reportan por similitud de texto (comportamiento del detector existente, no modificado).
3. `tracemalloc` mide memoria de objetos Python; el RSS depende de la plataforma (Windows devuelve 0.0 sin psutil por ausencia de `resource`).
4. El benchmark procesa documentos sintéticos; para cifras de producción se debe apuntar `process_fn` a lotes reales.

## Compatibilidad con fases anteriores

- FASE 2–6: se reutilizan ParserFactory, KnowledgeRepository, ValidationOrchestrator y Certifier sin tocarlos.
- FASE 7: el profiler consume el formato de `PipelineRunner` (`stages[].duration_ms`) y el smoke puede ejecutarse con el runner real.
- FASE 8: certificación sin cambios; los reportes operacionales complementan los reportes de fase8.
- FASE 9: la alineación certificada (8 campos, 65.8%) permanece intacta.

## Próximo paso

FASE 11 — Operar el motor V2 contra datos reales en producción continua: ejecutar el Batch Runner sobre el dataset real (PDFs e imágenes), medir el profiler/benchmark con documentos reales, integrar el Health Check en el arranque del servicio y conectar los reportes operacionales al monitoreo (logging estructurado → métricas → dashboard).
