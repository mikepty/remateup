# FASE 6 — Knowledge Engine

## Estado: COMPLETADO ✓

### Resumen

Knowledge Engine que aprende de correcciones humanas. Cuando un usuario corrige un valor extraído, el sistema analiza el patrón, genera reglas candidatas, y las aplica automáticamente en futuras extracciones — todo determinista, sin LLM.

### Arquitectura

```
CorrectionEvent (usuario corrige un campo)
    ↓
KnowledgeAnalyzer (analiza patrón + contexto + evidencia)
    ↓
KnowledgeRule candidates (status = PENDING)
    ↓
KnowledgeTrainer (aprueba/rechaza según confianza)
    ↓
RuleEngine (aplica reglas APPROVED cuando parser retorna NOT_FOUND)
    ↓
KnowledgeAwareWrapper (wraps parser — aplica reglas sin modificar el parser)
```

### Flujo de aprendizaje

```
1. Usuario corrige "FINCA 12345" → CorrectionEvent(field_name="finca", corrected_value="12345")
2. Analyzer genera regla candidata → KnowledgeRule(pattern="FINCA (\d+)", field_name="finca")
3. Si confianza ≥ umbral (mismas correcciones previas) → auto-approve
4. Si no → queda PENDING para revisión manual
5. RuleEngine.apply(field_name, text) → si hay regla APPROVED y parser falló, aplica regex
6. MetricsTracker registra uso + aciertos/fallos
```

### Componentes

| Archivo | Descripción |
|---|---|
| `knowledge/models.py` | `CorrectionEvent`, `KnowledgeRule` (PENDING/APPROVED/REJECTED), `KnowledgeAlias`, `KnowledgeEvidence` |
| `knowledge/repository.py` | `KnowledgeRepository` — almacenamiento en memoria con CRUD + filtros |
| `knowledge/analyzer.py` | `KnowledgeAnalyzer` — detecta patrones, genera candidatos, alias |
| `knowledge/trainer.py` | `KnowledgeTrainer` — approve, reject, auto-approve (confianza ≥ 0.8) |
| `knowledge/rules.py` | `RuleEngine` — aplica reglas APPROVED como fallback |
| `knowledge/services.py` | `CorrectionService` — orquesta: recibe corrección → analiza → entrena |
| `knowledge/patterns.py` | `PatternGenerator` — crea regex flexibles desde ejemplos |
| `knowledge/aliases.py` | `AliasManager` — sinónimos builtin + aprendidos (e.g. NRO → NÚMERO) |
| `knowledge/metrics.py` | `MetricsTracker` — uso de reglas, accuracy por campo, cobertura |
| `knowledge/integration.py` | `KnowledgeAwareWrapper` — wrapper que inyecta conocimiento sin modificar parsers |

### KnowledgeRule

```python
class KnowledgeRule:
    field_name: str          # campo al que aplica
    pattern: str             # regex de captura
    confidence: float        # 0.0 - 1.0
    status: RuleStatus       # PENDING → APPROVED | REJECTED
    usage_count: int         # veces aplicada
    success_count: int       # veces que acertó
    accuracy: float          # success_count / usage_count (0 si sin uso)
```

### KnowledgeAwareWrapper

```python
class KnowledgeAwareWrapper(ParserInterface):
    def __init__(self, parser: ParserInterface, rule_engine: RuleEngine): ...

    def parse(self, context: ParserContext) -> dict[str, ParseResult]:
        results = self._parser.parse(context)        # parser original
        for field_name, result in results.items():
            if result.status == "NOT_FOUND":
                rule_result = self._rule_engine.apply(field_name, context.text)
                if rule_result: ...                   # reemplaza con valor de regla
        return results
```

### Tests

| Archivo | Tests | Temas |
|---|---|---|
| `tests/test_knowledge.py` | 43 | Models (7), Repository (7), Patterns (4), Aliases (4), Analyzer (4), Trainer (5), RuleEngine (4), CorrectionService (2), MetricsTracker (3), KnowledgeAwareWrapper (3) |

### Casos cubiertos

| Test | Descripción |
|---|---|
| `test_create_event` / `test_to_dict` | Creación y serialización de CorrectionEvent |
| `test_default_state` / `test_approve` / `test_reject` | Ciclo de vida de KnowledgeRule |
| `test_record_usage` / `test_no_usage_accuracy_zero` | Tracking de uso y precisión |
| `test_save_rule` / `test_save_alias` / `test_save_correction` | Persistencia en repositorio |
| `test_get_approved_rules` / `test_get_corrections_by_country` | Filtros del repositorio |
| `test_generate_for_value_numeric` / `test_generate_for_value_short` | PatternGenerator: valores numéricos → regex flexible |
| `test_generate_from_two_examples` / `test_insufficient_examples` | PatternGenerator: desde 2 ejemplos, mínimo 1 |
| `test_resolve_builtin` / `test_resolve_unknown` | AliasManager: sinónimos builtin |
| `test_learn_alias` / `test_learn_identical_returns_none` | AliasManager: aprendizaje dinámico |
| `test_normalize_with_aliases` | Normalización de texto con alias |
| `test_analyze_correction_generates_candidate` | Analyzer: genera regla desde corrección |
| `test_analyze_correction_no_evidence` | Analyzer: sin evidencia → sin candidato |
| `test_analyze_batch_requires_min_corrections` / `test_analyze_batch_with_enough` | Batch analysis: mínimo 3 correcciones |
| `test_approve_rule` / `test_reject_rule` | Trainer: approve/reject manual |
| `test_auto_approve_high_confidence` / `test_auto_approve_low_confidence` | Auto-approve según umbral |
| `test_get_pending_rules` | Trainer: listar pendientes |
| `test_apply_approved_rule` / `test_pending_rule_not_applied` | RuleEngine: solo reglas APPROVED |
| `test_no_approved_rules` / `test_rule_usage_tracked` | RuleEngine: edge cases |
| `test_record_correction` / `test_statistics` | CorrectionService: orquestación completa |
| `test_get_summary` / `test_overall_accuracy_no_rules` / `test_overall_accuracy_with_usage` | MetricsTracker: resumen + precisión global |
| `test_wrapper_calls_underlying_parser` / `test_wrapper_fallback_with_knowledge` / `test_wrapper_preserves_parser_identity` | KnowledgeAwareWrapper: integración con parser |

### Reglas respetadas

1. ✅ Sin LLM — todo determinista (regex + umbrales)
2. ✅ Sin Claude, Gemini, ni IA generativa
3. ✅ `AIResolver` sin modificar — sigue siendo interfaz abstracta
4. ✅ Sin modificar pipeline V1
5. ✅ Sin modificar OCR, segmenter, database ni frontend
6. ✅ `KnowledgeAwareWrapper` no modifica parsers — los envuelve
7. ✅ Parser nunca infiere valores — solo FOUND/NOT_FOUND/REQUIRES_REVIEW
8. ✅ Evidencia respetada — KnowledgeRule también registra evidencia

### Resultados

**368 tests — 368 passed, 0 failed, 0 errors**

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
| FASE 6 (knowledge engine) | **43** |
| **Total** | **368** |

### Próximo paso

FASE 7 — Normalization, Confidence Scoring, y/o integración completa del pipeline end-to-end.
