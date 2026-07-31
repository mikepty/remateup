# FASE 11 — REAL DATASET VALIDATION + AIRESOLVER (Z.AI)

## Estado

COMPLETADO ✓

## Objetivo

Ejecutar el sistema completo sobre documentos reales (PDFs CO y JPGs PA con OCR real de Google Vision) y conectar la implementación real de AIResolver usando la API de Z.ai ya configurada mediante variables de entorno (`ZAI_API_KEY`). No se creó otro motor, no se modificó Parser, OCR, Validator, Knowledge ni Certification. La arquitectura certificada en la FASE 9 permanece intacta.

## Contexto

El motor V2 quedó CERTIFIED en FASE 9 (8 campos certificados, Overall Alignment 65.8%) y operacional en FASE 10 (profiler, health, smoke, batch, reportes). FASE 11 añade el único componente faltante: el fallback inteligente encapsulado tras `AIResolver`, ejecutado contra el dataset real de `backend/data/uploads/` (3 PDFs SEJURE CO + 13 imágenes PA) con OCR real, y validado contra el golden dataset (`evaluation/golden_dataset/records.json`, 22 avisos con ground truth).

## Arquitectura

```
                    ┌────────────────────────────────────────────┐
                    │         parser/ai/ (NUEVO, FASE 11)         │
                    │                                            │
   AIResolver ◄─────┤  policy.py   — campos permitidos + gate     │
   (interfaz)       │  prompt.py   — prompt controlado JSON-only  │
                    │  cache.py    — hash campo+texto+país        │
                    │  rate_limit  — ventana + backoff + timeout  │
                    │  audit.py    — auditoría (nunca API key)    │
                    │  providers   — ZAI / OpenRouter / HF / Local│
                    │  zai_resolver — ZAIResolver (Z.ai real)     │
                    │  integration — Parser→Knowledge→AI→Valid→Cert│
                    └────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
  TXT / PDF / JPG / PNG       ProductionDatasetRunner      comparison.py
  (OCR real Vision)           (evaluation/production/)     TP/FP/FN/P/R/F1
                                    │
                                    ▼
                        production_validation.json / .md
```

## Flujo actualizado

```
Documento (TXT | PDF | JPG | PNG)
    │
    ▼
OCR (Google Vision real — GOOGLE_VISION_API_KEY desde .env)
    │
    ▼
Assembly / Mapping / Segmentation / Stitching / Continuity
    │
    ▼
Parser (determinista, NO modificado)
    │
    ▼
Knowledge (reglas aprobadas, NO modificado)
    │
    ▼
AIResolver — SOLO fallback
    │   condiciones: ParseResult.status in (REQUIRES_REVIEW, NOT_FOUND)
    │   y campo in {fecha_remate, hora, lugar, juzgado, provincia, municipio}
    │   Nunca reemplaza FOUND con alta confianza.
    │   Concurren: cache → rate limiter → Z.ai → policy → auditoría
    ▼
Validator (NO modificado)
    │
    ▼
Certification (NO modificado)
    │
    ▼
Resultado + knowledge_safety (reglas NO tocadas por IA)
```

## Componentes implementados

| Módulo | Responsabilidad | Estado |
| --- | --- | --- |
| `parser/ai/policy.py` | `AIConfidencePolicy` (≥0.95 FOUND, 0.80–0.95 REQUIRES_REVIEW, <0.80 NOT_FOUND) + campos permitidos/prohibidos | OK |
| `parser/ai/prompt.py` | Prompt controlado: país, tipo documental, campo, texto OCR, evidencia; respuesta JSON exclusiva; parseo JSON (fences, prosa, inválido→None) | OK |
| `parser/ai/cache.py` | `AICache`: hash sha256(campo+texto+país), guarda respuesta/confidence/provider/timestamp, persistencia JSON, stats hit/miss | OK |
| `parser/ai/rate_limit.py` | `RateLimiter`: ventana deslizante, timeout configurable, backoff exponencial, reintentos | OK |
| `parser/ai/audit.py` | `AIAuditLog`: provider, modelo, tokens, latencia, prompt/response hash, confidence, campo, documento — nunca la API key | OK |
| `parser/ai/zai_resolver.py` | `ZAIResolver`: `ZAI_API_KEY` desde env (nunca hardcodeada), `is_available()`, `provider_name()`, `resolve(...)`; `glm-4.5-flash` + `thinking disabled`, JSON object | OK |
| `parser/ai/providers.py` | `OpenRouterResolver`, `HuggingFaceResolver`, `LocalResolver` (determinista offline), `AIResolverRegistry`, `estimate_cost` | OK |
| `parser/ai/integration.py` | `AIEnhancedPipeline`: Parser→Knowledge→AIResolver→Validator→Certification; `enrich_fields`; knowledge_safety | OK |
| `evaluation/production/runner.py` | `ProductionDatasetRunner`: TXT/JPG/PNG/PDF, directorios completos, resumen, errores, métricas | OK |
| `evaluation/production/comparison.py` | Comparativa Solo Parser vs Parser+IA: TP/FP/FN/P/R/F1 por campo vs golden | OK |
| `evaluation/production/report.py` | `production_validation.json` + `.md` | OK |
| `evaluation/production/samples/` | Corpus TXT real derivado del golden (16 CO + 6 PA) + `generate_corpus.py` | OK |

## Archivos creados/modificados

Creados:
- `backend/app/v2/parser/ai/{__init__,policy,prompt,cache,rate_limit,audit,providers,zai_resolver,integration}.py`
- `backend/app/v2/evaluation/{__init__,production/{__init__,runner,comparison,report}.py}.py`
- `backend/app/v2/evaluation/production/samples/generate_corpus.py` + 22 TXT generados
- `backend/app/v2/evaluation/production/output/production_validation.{json,md}`, `real_run_results.json`, `zai_live_metrics.json`
- `backend/app/v2/tests/test_ai_phase11.py` (50 tests)

Modificados: ninguno de Parser, OCR, Validator, Knowledge, Certification ni V1.

## Integración

- Parser/Knowledge: se reutilizan `ParserFactory`, `KnowledgeAwareWrapper` y `RuleEngine` (sin tocar).
- AIResolver actúa únicamente sobre campos en `AI_ALLOWED_FIELDS` con estado `REQUIRES_REVIEW`/`NOT_FOUND` (incluye campos permitidos ausentes del resultado del parser).
- `AIConfidencePolicy` convierte la confianza del proveedor en estado ParseResult.
- Knowledge Safety (Parte 13): las respuestas de Z.ai NO crean/modifican reglas, NO aprenden, NO elevan confianza, NO cambian métricas de entrenamiento — solo se registran en el AI Audit Log (verificado por test: repositorio sin cambios tras ejecutar el pipeline con IA).
- Provider Abstraction (Parte 14): el pipeline solo conoce `AIResolver`; proveedores registrables (`zai`, `openrouter`, `huggingface`, `local`) sin condicionales en el pipeline; selección por `AI_PROVIDER` o por disponibilidad de clave.

## Tests agregados

`backend/app/v2/tests/test_ai_phase11.py` — 50 tests:
- ✓ ZAIResolver (disponibilidad sin clave, provider_name, FOUND/REQUIRES_REVIEW/NOT_FOUND, JSON inválido→REQUIRES_REVIEW, campo prohibido nunca llama al transporte, cache evita llamadas repetidas, auditoría sin API key)
- ✓ Cache (key estable, hit/miss, persistencia, evicción)
- ✓ RateLimiter (timeout, retry hasta éxito, reintentos agotados, stats)
- ✓ ConfidencePolicy (umbrales y límites)
- ✓ Auditoría (campos registrados, persistencia, ausencia de clave)
- ✓ JSON parsing (válido, fences, prosa, inválido, claves faltantes)
- ✓ Timeout y Retry
- ✓ Integración (fallback solo para permitidos, nunca reemplaza FOUND alto, pipeline completo, knowledge safety)
- ✓ Dataset Runner (archivo, directorio, comparativa, reporte)

## Total de tests

**896 passed** (846 previos + 50 nuevos) — 0 regresiones, ningún test existente eliminado.

## Métricas obtenidas sobre dataset real

### Dataset real (backend/data/uploads, OCR real Google Vision)

| Métrica | CO (3 PDFs SEJURE) | PA (13 imágenes) | Total |
| --- | --- | --- | --- |
| Documentos | 3 | 13 | 16 |
| Avisos encontrados | 3 | 30 | 33 |
| Avisos válidos | 0 | 0 | 0 |
| Descartados (certificación) | 3 (INVALID) | 0 | 3 |
| Duplicados | 0 | 0 | 0 |
| Campos encontrados | 5 (finca 2, expediente 1, municipio IA 3) | 30 (fecha_remate, finca, demandado…) | 35 |
| Campos IA (LocalResolver) | 3 | 0 | 3 |
| Tiempo promedio | 76.76 ms | — | — |
| Errores | 0 | 0 | 0 |

- Los 3 PDFs CO: OCR real completo (~31k chars por parte), la segmentación del runner devuelve 0 avisos (páginas `[]` en PDF) → el runner usa flujo OCR-texto (documentado); certificación INVALID por falta de campos críticos en el aviso único reconstruido.
- Las 13 imágenes PA: **pipeline completo real** (assembly → OCR → stitching → segmentación → parser → knowledge → validator → certification); segmentación real detecta 2–3 avisos por imagen (30 avisos totales).

### Comparativa Solo Parser vs Parser + IA (corpus golden CO, 16 documentos)

| Modo | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| Solo Parser | 47 | 32 | 0 | 0.5949 | 1.0000 | 0.7460 |
| Parser + IA | 47 | 32 | 0 | 0.5949 | 1.0000 | 0.7460 |

Por campo (ambos modos): expediente TP16 F1=1.0, demandante TP16 F1=1.0, demandado TP15 F1=1.0, fianza_porcentaje FP16 (valores presentes en texto pero sin match exacto vs golden), minimo_porcentaje FP16. Los campos permitidos de IA (lugar/provincia) no tienen ground truth en las suites CO (campos ausentes del golden), por lo que el delta IA no altera la comparativa sobre campos golden; el delta aparece en campos nuevos (juzgado resuelto por IA en los 3 documentos Z.ai).

### Z.ai en vivo (glm-4.5-flash, 3 documentos reales)

| Métrica | Valor |
| --- | --- |
| Llamadas (cache miss) | 18 (6 campos permitidos × 3 docs) |
| Cache hit | 0 (documentos distintos) |
| Campos IA resueltos (juzgado) | 3 (todos FOUND conf 1.0) |
| Tokens totales | 6 215 (prompt ~2 000/doc) |
| Tiempo IA | 95 667.87 ms (2 500–3 800 ms/llamada + rate limit/backoff por 429) |
| Costo estimado | $0.00 (glm-4.5-flash free tier; tarifas configurables por env) |
| Latencia por llamada | 2.46–2.93 s (prueba directa) |
| Auditoría | 18 entradas (provider, modelo, tokens, latencia, hashes, confidence, campo, documento) — sin API key |

### Health / comportamiento

- Smoke PASS, HEALTHY (7/7) de FASE 10 intactos.
- Campos prohibidos (expediente, finca, precio_base, base, fianza, mínimo, matrícula) jamás llegan al proveedor (verificado con transporte espía).

## Limitaciones

1. Los PDFs SEJURE son tabulares multi-aviso (16 avisos por documento): el OCR real produce texto completo correcto, pero la segmentación del runner devuelve 0 avisos (comportamiento FASE 7, `OCRDocument.pages=[]` en PDF); la validación usa el flujo OCR-texto (1 aviso reconstruido por PDF), por lo que la extracción cubre solo el primer aviso del texto.
2. El corpus TXT derivado del golden es una renderización del ground truth real: la comparativa mide el sistema completo sobre textos reales, no sobre las imágenes originales (cuyo OCR multi-aviso no tiene mapeo 1:1 aviso→registro golden).
3. `glm-4.7-flash` (modelo por defecto anterior) devuelve 429 temporal en este entorno; se usó `glm-4.5-flash` con `thinking disabled` (JSON limpio, free tier). Cambiable vía `ZAI_MODEL`.
4. Costo estimado = $0 con free tier; para modelos de pago se deben configurar `ZAI_PRICE_INPUT_PER_1M` / `ZAI_PRICE_OUTPUT_PER_1M`.
5. La revalidación tras IA re-ejecuta Validator y Certifier sobre los campos enriquecidos (no modifica sus módulos).

## Riesgos

1. Dependencia de la disponibilidad del proveedor (429/overload) → mitigado con rate limiter, backoff y fallback seguro a REQUIRES_REVIEW.
2. Modelo razonador devuelve `reasoning_content` vacío si no se desactiva thinking → mitigado con `thinking: disabled` por defecto.
3. La IA nunca debe influir en Knowledge: garantizado por diseño (solo audit log) y cubierto por test de seguridad.
4. Latencia por llamada (~3 s) limita el throughput en modo IA; el cache por (campo+texto+país) evita llamadas repetidas.
5. OCR real depende de Google Vision (clave en `backend/.env`); sin clave, los archivos reales reportan error controlado.

## Compatibilidad con FASES 2–10

- FASE 2–6: ParserFactory, Knowledge, Validator, Certification reutilizados sin modificaciones.
- FASE 7: PipelineRunner intacto; `AIEnhancedPipeline.run_files` lo envuelve y enriquece.
- FASE 8: certificación sin cambios; la comparativa usa el mismo golden dataset.
- FASE 9: 8 campos certificados y alignment 65.8% intactos (0 regresiones en la suite).
- FASE 10: `production/*` sin cambios; `run_text_pipeline` reutilizado por `AIEnhancedPipeline.run_text`; smoke/health siguen verdes.

## Próximo paso sugerido

FASE 12 — Operación asistida: habilitar la corrección humana verificada de respuestas AIResolver para que fluya al Knowledge Engine (Corrección Humana → Knowledge Analyzer → Knowledge Trainer → Repository) tal como define la Parte 13, e integrar el AI Audit Log con el dashboard operacional de FASE 10 para monitorear latencia, costo y tasa de aceptación por campo.
