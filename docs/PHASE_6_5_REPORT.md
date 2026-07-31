# FASE 6.5 — Knowledge Validation & Learning Pipeline

## Estado: COMPLETADO ✓

### Resumen

Validación completa del Knowledge Engine sobre datos reales: persistencia SQLite, shadow learning, protección contra regresiones, versionado, expiración, categorización por tipo de conocimiento, explicabilidad, dashboard de métricas, y benchmark de rendimiento.

### Arquitectura

```
┌─────────────────────────────────────────────────────┐
│                    FASE 6.5 NEW                      │
├─────────────────────────────────────────────────────┤
│ SQLiteRepository (reemplaza memoria)                 │
│   ├── knowledge_rules (con categorías + versiones)  │
│   ├── knowledge_aliases (con prioridad + builtin)   │
│   ├── corrections (persistente)                     │
│   ├── knowledge_history (versionado + rollback)     │
│   └── shadow_comparisons (parser vs knowledge)      │
├─────────────────────────────────────────────────────┤
│ ShadowLearner — compara parser vs parser+knowledge   │
│ RegressionGuard — test vs Golden Dataset            │
│ KnowledgeBenchmark — overhead <10%                 │
│ KnowledgeCategory — LABEL/MONEY/DATE/PERSON/...     │
│ RuleExpiration — accuracy <70% → INACTIVE          │
│ MetricsDashboard — JSON exportable                 │
└─────────────────────────────────────────────────────┘
```

### Archivos nuevos/modificados

| Archivo | Cambio |
|---|---|
| `knowledge/models.py` | +RuleStatus.INACTIVE, +KnowledgeCategory, +version, +rule_id, +fail_count, +RuleHistory, +ShadowComparison, +KnowledgeAlias priority fields |
| `knowledge/repository.py` | **REESCRITO** — SQLite con 5 tablas, índices, persistencia real |
| `knowledge/patterns.py` | +Category-aware patterns (LABEL, MONEY, DATE, PERSON, PROPERTY, CASE_NUMBER) |
| `knowledge/aliases.py` | +Priority: builtin > approved learned > pending learned |
| `knowledge/analyzer.py` | +Batch learning con categorías, +detect_variants |
| `knowledge/rules.py` | +Expiration (accuracy<70%→INACTIVE), +explain_rule, +rollback_rule, +fail_count tracking |
| `knowledge/trainer.py` | +History tracking, +INACTIVE support, +approved_by |
| `knowledge/services.py` | +batch_learn con regression guard, +rollback, +explain |
| `knowledge/metrics.py` | +Dashboard completo (by field, by country, top failed, categories) |
| `knowledge/integration.py` | Explicabilidad en evidence (rule_id, version) |
| `knowledge/shadow.py` | **NUEVO** — ShadowLearner: parser vs parser+knowledge |
| `knowledge/regression.py` | **NUEVO** — RegressionGuard: Golden Dataset validation |
| `knowledge/benchmark.py` | **NUEVO** — KnowledgeBenchmark: overhead test |
| `tests/test_knowledge.py` | Adaptado a SQLite |
| `tests/test_knowledge_v2.py` | **NUEVO** — 81 tests de FASE 6.5 |

### Componentes detallados

#### 1. SQLite Persistence

5 tablas con índices:

| Tabla | Propósito |
|---|---|
| `knowledge_rules` | Reglas con versión, categoría, status, evidencia JSON |
| `knowledge_aliases` | Alias con prioridad (builtin/learned) y status |
| `corrections` | Historial de correcciones humanas |
| `knowledge_history` | Audit trail de cambios de estado en reglas |
| `shadow_comparisons` | Resultados de comparación parser vs knowledge |

- Sobrevive reinicios
- Ruta configurable via `KNOWLEDGE_DB_PATH` env var
- Default: `knowledge/knowledge.db`

#### 2. Rule Categorization

6 categorías de conocimiento (no solo regex):

| Categoría | Ejemplo | Pattern generado |
|---|---|---|
| `LABEL` | "VALOR BASE", "PRECIO BASE" | `(variants)` |
| `MONEY` | "B/.100,000.00", "$50000" | `([\$B/\.\s]*[\d\.,]+...)` |
| `DATE` | "15 DE SEPTIEMBRE DE 2026" | `(\d{1,2}\s+DE\s+[A-ZÁÉÍÓÚÑ]+\s+DE\s*\d{2,4})` |
| `PERSON` | "JUAN PEREZ" | `([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s\.]+...)` |
| `PROPERTY` | "90123" | `([\d]+)` |
| `CASE_NUMBER` | "12345-2026" | `([\d\-]+)` |

#### 3. Shadow Learning

```python
learner = ShadowLearner(repository=repo)
comparisons = learner.compare(parser, context, document_id="D1")
# Cada comparison tiene: parser_value, knowledge_value, winner, difference
```

- Ejecuta parser solo y parser+knowledge side by side
- Guarda ganador, diferencias, evidencia, confianza
- Summary con parser_wins / knowledge_wins / ties

#### 4. Regression Protection

```python
guard = RegressionGuard(repository=repo)
success, evaluation = guard.approve_with_guard(rule)
# Si regression=True → auto-reject + history
```

- Evalúa contra Golden Dataset completo
- Compara precisión antes/después de aplicar regla
- Rechaza automáticamente si hay regresión

#### 5. Rule Versioning + History

```python
rule.rule_id    # uuid único
rule.version    # entero, incremental
rule.created_from_correction  # DOC-001
rule.approved_by              # "auto", "trainer", "regression_guard"

engine.rollback_rule(rule_id)  # → PENDING + history entry
engine.explain_rule(rule_id)   # → rule details + full history
```

#### 6. Rule Expiration

```python
# Automático: accuracy < 70% + ≥5 ejecuciones → INACTIVE
engine = RuleEngine(repository=repo)
engine.apply_rules(field, text, previous_result)  # checks expiration
```

- Reglas INACTIVE no se aplican
- Nunca se borran automáticamente
- Quedan en history para auditoría

#### 7. Explainability

Cada evidencia de regla incluye:
```
"method": "rule:regex:R1A2B3C4D5E6:v1"
"source": "knowledge"
"snippet": "FINCA 12345"
"confidence": 0.9
```

Además vía `explain_rule(rule_id)`:
- Rule ID, versión, pattern
- Categoría, campo, status
- Accuracy, usage, success/fail
- Corrección origen
- Historial completo de cambios

#### 8. Metrics Dashboard

```python
metrics = MetricsTracker(repository=repo)
dashboard = metrics.get_dashboard()
```

Retorna JSON con:
- Summary (corrections, rules por status)
- Overall accuracy
- Accuracy por campo
- Accuracy por país (PA/CO)
- Top 10 reglas más usadas
- Top 10 reglas más fallidas
- Distribución por categoría

#### 9. Performance Benchmark

```python
benchmark = KnowledgeBenchmark(repository=repo)
benchmark.setup_test_data()
result = benchmark.benchmark_parser(iterations=100)
# result.overhead_pct debe ser < 10%
```

### Tests

| Archivo | Tests | Temas |
|---|---|---|
| `tests/test_knowledge.py` | 42 | Tests originales adaptados a SQLite |
| `tests/test_knowledge_v2.py` | 81 | FASE 6.5: persistence (18), versioning (6), categories (11), alias priority (4), batch learning (4), expiration (5), shadow (4), explainability (4), dashboard (5), regression (2), benchmark (2), rollback (3), service (5), trainer (3), models (5) |
| **Total knowledge** | **123** | |
| **Total sistema** | **448** | |

### Resultados

| Suite | Tests |
|---|---|
| FASE 2 (models) | 48 |
| FASE 3 (OCR) | 46 |
| FASE 4 (segmenter + continuity) | 74 + 24 |
| FASE 4.2 (assembly) | 27 |
| FASE 4.4 (stitching) | 12 |
| FASE 4.5 (newspaper layout) | 24 |
| FASE 5 (parser) | 45 |
| FASE 5.5 (real patterns) | 22 |
| FASE 6 (knowledge engine) | 42 |
| FASE 6.5 (knowledge v2) | **81** |
| **Total** | **448** |

**448 tests — 448 passed, 0 failed, 0 errors**

### Reglas respetadas

1. ✅ Sin LLM — todo determinista
2. ✅ Sin Claude, Gemini, ni IA generativa
3. ✅ AIResolver sin modificar
4. ✅ Sin modificar pipeline V1
5. ✅ Sin modificar OCR, segmenter, database ni frontend
6. ✅ Sin modificar frontend
7. ✅ KnowledgeAwareWrapper no modifica parsers

### Próximo paso

FASE 7 — Normalization, Confidence Scoring, integración end-to-end, o según instrucciones del usuario.
