# FASE 12 — Production Hardening & Real Dataset Completion — Reporte

Determinista y auditable: cada artefacto documenta su origen y sus datos reales.
Sin cambios de arquitectura, sin modificaciones a parsers/OCR/Knowledge/Validator/Certification,
sin prompts nuevos de IA. 30 tests nuevos; 0 regresiones (896 + 30 = 926 passed).

## Resumen ejecutivo

| Métrica | Valor |
| --- | --- |
| PDFs CO procesados | 3 (SEJURE 28 jul 2025: parte1/2/3) |
| Páginas reales detectadas | 57 (19 por PDF) |
| Bloques `EJ .`/`DIV .` reales | 192 (64/61/67) |
| Avisos golden anclados | 16 / 16 (100%) — todos en parte1, páginas 17-19 |
| Avisos procesados aviso-por-aviso | 16 |
| Precisión/F1 aviso-por-aviso | 0.0 (honesto: el parser CO no extrae el grid real) |
| Decisiones IA registradas (audit) | 141 (glm-4.5-flash) |
| Aceptadas / rechazadas / corregidas | 32 / 109 / 0 (22.7%) |
| Reglas Knowledge | 0 (knowledge.db real vacío — hallazgo) |
| Documentos benchmark | 16 (3 CO + 13 PA), 54 diferencias reales entre modos |
| Módulos muertos (auditoría estática) | 126 de 131 |
| Dependencias circulares | 0 |
| Tests | 926 passed (896 + 30 nuevos), 0 regresiones |

## Parte 1 — Causa raíz de "0 avisos en CO" (verificada con datos reales)

- `ocr/processor.py` construye objetos página (líneas 87-92) pero las descarta:
  `pages=[]` hardcodeado (líneas 96-100). El `full_text` sí viaja.
- `pipeline/runner.py` itera `ocr_doc.pages` (líneas 190-201) → 0 avisos para CO;
  su fallback exige un header "AVISO DE REMATE"/"REMATE JUDICIAL" (línea 194)
  que los carteles colombianos reales no tienen (formato grid `EJ .`/`DIV .`).
- Los runners de FASE 10/11 alimentaban el `full_text` completo como UN aviso,
  sobreestimando la cobertura real.

Verificación: los 16 expedientes golden aparecen por flujo de dígitos en el OCR
real de parte1 (páginas 17-19); parte2 contiene 54 tokens expediente sueltos;
parte3 página 13 contiene avisos que también anclan.

## Parte 2 — Aviso por aviso sobre el dataset real

Artefacto: `output/aviso_por_aviso.json`

- Anclaje 16/16 con página + segmento `chars:` + texto del bloque real.
- Resultado honesto: el parser CO (ColombiaRemateParser) devuelve `{}` sobre los
  bloques grid reales (sin etiquetas EXPEDIENTE/MATRÍCULA) → precisión/F1 = 0.0.
- La IA (única capa permitida) resolvió 2 campos: `municipio` en b0/b1
  ("GUAYABAL DE SIQUIMA"). El resto de consultas → NOT_FOUND/REQUIRES_REVIEW.
- Los FN documentados por campo (expediente, demandante, demandado, fianza,
  mínimo) con esperado/obtenido en `comparison.errores`.

## Parte 3 — Traza de pipeline por aviso

Artefacto: `output/pipeline_trace.json` — 16 trazas; cada una con documento,
aviso_id, expediente golden, página, bbox, segmento, parser (CO REMATE),
knowledge (aplicado: false — 0 reglas), IA (usada: true, campos, provider,
tiempo, cache, tokens), validator (decision/score/campos), certification y
comparación con el golden.

## Parte 4 — AI Feedback Loop

Artefacto: `output/ai_feedback.json`

- 141 decisiones reales (glm-4.5-flash): 32 aceptadas (22.7%), 109 rechazadas,
  0 corregidas. Confianza media 0.62.
- Por campo: municipio 3/37, fecha_remate 6/39, hora 3/37, juzgado 1/41,
  lugar 0/37, provincia 0/39.
- Cache: 8 hits / 88 misses; tiempo IA 621.5s; 35,470 tokens; costo $0.
- `aprendizaje_automatico: false`, `knowledge_modificado: false` — la IA solo
  responde; no aprende (garantizado).
- Reproducibilidad: `audit_log_baseline: 736`, `audit_log_final: 877` en
  `phase12_summary.json` (rango exacto del audit usado).

## Parte 5 — Knowledge Impact Report

Artefactos: `output/knowledge_impact.json` / `.md`

- Hallazgo real: la base de conocimiento (`knowledge.db`) tiene 0 reglas y 0
  correcciones → 0 reglas usadas, 0 nunca usadas, 0 expiradas. El impacto de
  Knowledge en producción es nulo.
- Limitaciones documentadas: el país de la regla se deriva de la corrección que
  la originó (N/A cuando no nació de una corrección); primer uso exacto no se
  almacena (se estima con created_at).

## Parte 6 — Field Quality Report

Artefactos: `output/field_quality.json` / `.md` — 32 documentos (16 avisos +
16 benchmark), 33 campos del catálogo.

| campo | FOUND | FOUND_IA | FINAL |
| --- | --- | --- | --- |
| municipio | 13 | 2 | 13 |
| fecha_remate | 15 | 0 | 15 |
| finca | 14 | 0 | 14 |
| hora | 10 | 0 | 10 |
| provincia | 13 | 0 | 13 |
| lugar | 9 | 0 | 9 |
| juzgado | 9 | 0 | 9 |
| demandado / expediente / precio_base / demandante | 3 c/u | 0 | 3 c/u |

## Parte 7 — Production Dashboard

Artefactos: `output/production_dashboard.json` / `.md`

- 32 documentos, 95 campos encontrados (promedio 2.97/doc).
- Stage dominante: `ai_resolver` (promedio 38.8s por documento) — el costo de
  tiempo de producción está en la IA, no en parser/knowledge/validator.
- Knowledge: 0 campos resueltos (0 reglas). IA: 2 campos resueltos.
- Health: registrado en el dashboard (fecha de chequeo, status).

## Parte 8 — Real Dataset Benchmark (mismo OCR, 3 modos)

Artefactos: `output/real_benchmark.json` / `.md` — 16 documentos, 54
diferencias reales entre `parser` vs `parser+knowledge` vs
`parser+knowledge+ia` (campos que cambian: fecha_remate, hora, juzgado, lugar,
municipio, provincia — todos del conjunto permitido de IA).

Hallazgo real e importante: en 7 imágenes PA (21ce358d, dfe0e387,
IMG-20260710-WA0014/18), la IA eleva campos pero la certificación cambia de
`INCOMPLETE` a `INCONSISTENT`: la IA completa cobertura introduciendo valores
que la certificación juzga en conflicto. La IA mejora recall pero degrada la
consistencia certificada en esos documentos.

## Parte 9 — Architecture Audit (estática, AST)

Artefactos: `output/architecture_audit.json` / `.md` — 131 módulos analizados.

- Módulos muertos: 126 · Código nunca ejecutado: 395 símbolos · Clases nunca
  instanciadas: 82.
- Reglas nunca utilizadas: 0 (no hay reglas) · Campos imposibles: 0 ·
  Dependencias circulares: 0 · Validaciones duplicadas: 0 · Alias redundantes: 6.
- Productores sin consumidores: 1 · Consumidores sin productores: 2.
- Metodología documentada en el artefacto.

## Correcciones hechas durante FASE 12 (sin tocar arquitectura)

- `comparison.py::_normalize`: bug real — golden flotante `181080000.0` se
  convertía a `1810800000` (10x) al limpiar el sufijo `.0`, imposibilitando
  matches de precio. Ningún test existente fijaba el quirk.
- `field_quality.py`: TypeError por defaultdict anidado en los contadores.
- `benchmark.py`: SyntaxError en el cálculo de decisiones de certificación.
- `ai_feedback.py`: lógica aceptado/corregido (FOUND sin estado final = aceptado;
  FOUND con final ≠ FOUND = corregido); cache summary ahora acumula por run.
- `knowledge_impact.py`: claves `reglas_nunca_usadas_count` / `reglas_expiradas_count`.
- Normalización de cache OCR en runner/benchmark (rutas absolutas vs relativas).

## Cómo reproducir

```
python -m pytest backend/app/v2/tests/test_phase12.py -q
python -m backend.app.v2.evaluation.production.phase12            # con IA
python -m backend.app.v2.evaluation.production.phase12 --no-ai    # sin llamadas
```

Los 9 artefactos se regeneran en `backend/app/v2/evaluation/production/output/`.
`phase12_summary.json` resume la ejecución (tiempos, audit baseline/final).
