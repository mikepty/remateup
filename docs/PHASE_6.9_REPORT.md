# FASE 6.9 — Production Validation Rules

## Objetivo
Convertir el pipeline V2 en un motor de validación determinista de avisos de remate reales. NO es extracción ni IA — es reducción de falsos positivos mediante reglas obtenidas de ejemplos reales del cliente.

---

## Arquitectura

```
backend/app/v2/validator/
    __init__.py              → exports públicos
    models.py                → Decision, NoticeDecision, ValidationResult, etc.
    production_rules.py      → headers válidos/inválidos, reglas de co-ocurrencia
    notice_validator.py      → valida si un bloque es un aviso de remate real
    consistency.py           → detecta inconsistencias entre campos
    duplicate_detector.py    → detecta duplicados intra/inter-documento
    scoring.py               → score independiente 0.00–1.00
    orchestrator.py          → coordina todos los componentes
```

## Flujo de Integración

```
Assembly → OCR → Mapper → Segmentation → Continuity → Parser → Knowledge → **Validator** → NoticeDecision
                                                                         ↑
                                                            FASE 6.9 — nuevo módulo
```

El Validator se inserta después del Knowledge Wrapper en `certification_runner.py`. Recibe el texto del aviso + los campos extraídos y produce un `NoticeDecision` con decisión, score, reglas aplicadas/fallidas, inconsistencias, duplicados.

---

## Componentes

### 1. `models.py` — Decisiones y Data Classes

| Clase | Propósito |
|---|---|
| `Decision` enum | VALID, INVALID, DUPLICATED, LIKELY_DUPLICATED, INCOMPLETE, INCONSISTENT, REQUIRES_REVIEW |
| `DuplicateLevel` enum | UNIQUE, DUPLICATED, LIKELY_DUPLICATED |
| `RuleResult` | nombre de regla, pasó/falló, detalle, peso |
| `Inconsistency` | field_1, field_2, descripción, severidad (low/medium/high) |
| `DuplicateInfo` | nivel, campos de coincidencia, ID del duplicado, similitud |
| `NoticeDecision` | decisión completa + score + reglas + campos + inconsistencias + duplicados |
| `ValidationResult` | resumen batch: total, valid/invalid/duplicated/incomplete/inconsistent/review counts |

### 2. `production_rules.py` — 7 Reglas Deterministas

| # | Regla | Peso | Descripción |
|---|---|---|---|
| 1 | **valid_header** | 0.25 | Acepta: AVISO DE REMATE, REMATE JUDICIAL, PRIMERA/SEGUNDA/TERCERA FECHA DE REMATE, SUBASTA JUDICIAL, REMATE EXTRAJUDICIAL. Rechaza: EDICTO, EDICTO EMPLAZATORIO, AVISO (solo), COMUNICADO, CIRCULAR, PUBLICIDAD, LICITACION, CONVOCATORIA, AVISO AL PÚBLICO |
| 2 | **not_publicidad** | 0.15 | Detecta contenido publicitario (publicidad, comunicado, oferta, descuento, circular) sin indicadores legales |
| 3 | **not_edicto** | 0.15 | Rechaza edictos que no contengan términos de remate |
| 4 | **min_one_strong_field** | 0.15 | Requiere ≥1 campo fuerte (expediente, finca, base) o ≥2 campos medios |
| 5 | **structural_coherence** | 0.15 | Header válido + al menos un campo fuerte |
| 6 | **field_co_occurrence** | 0.10 | 8 pares de co-ocurrencia: finca↔expediente, base↔fecha, demandante↔demandado, fianza↔base, minimo↔base |
| 7 | **min_field_count** | 0.05 | Al menos 2 campos presentes |

**Campos clasificados:**
- **Fuertes**: expediente, finca, precio_base, base, finca_matr
- **Medios**: fecha_remate, demandante, demandado, fecha
- **Débiles**: lugar, proceso, hora, provincia, categoria, fianza_porcentaje, minimo_porcentaje

### 3. `notice_validator.py` — Lógica de Decisión

```
¿Header inválido Y sin campos fuertes? → INVALID
¿Header inválido? → INVALID
¿4+ reglas fallidas? → INVALID
¿0 campos presentes? → INVALID
¿Publicidad o edicto? → INVALID
¿Header válido + ≥4 campos fuertes/medios? → VALID
¿Header válido + algunos campos? → INCOMPLETE
¿Sin header claro ni campos? → REQUIRES_REVIEW
```

### 4. `consistency.py` — 5 Verificaciones de Consistencia

| Verificación | Severidad | Descripción |
|---|---|---|
| Base vs precio_base | high | Mismos valores requeridos si ambos presentes |
| Finca vs finca_matr | high | Mismos valores requeridos |
| Múltiples fechas | medium | Fechas distintas en el mismo texto |
| Demandante = Demandado | high | No pueden ser la misma persona |
| Fecha imposible | medium | Año fuera de 1900-2100, mes > 12, día > 31 |

### 5. `duplicate_detector.py` — Detección de Duplicados

| Nivel | Criterio |
|---|---|
| UNIQUE | Sin coincidencias con avisos previos |
| LIKELY_DUPLICATED | 1 campo coincidente (expediente, finca, base, o bbox) |
| DUPLICATED | ≥2 campos coincidentes O similitud de texto > 90% |

### 6. `scoring.py` — Score Independiente (0.00–1.00)

| Componente | Peso |
|---|---|
| Header válido | 0.20 |
| Campos fuertes (ratio) | 0.20 |
| Campos medios (ratio) | 0.15 |
| Cantidad total de campos (ratio) | 0.10 |
| Co-ocurrencia sin advertencias | 0.10 |
| Sin inconsistencias | 0.10 |
| No es publicidad | 0.05 |
| No es edicto | 0.05 |
| Estructuralmente válido | 0.05 |

---

## Tests

**50 tests nuevos** en `backend/app/v2/tests/test_validator.py`:

| Grupo | Tests | Cubre |
|---|---|---|
| `TestValidHeaders` | 8 | AVISO DE REMATE, REMATE JUDICIAL, PRIMERA/SEGUNDA/TERCERA FECHA, SUBASTA, EXTRAJUDICIAL, vacío |
| `TestInvalidHeaders` | 8 | EDICTO, EDICTO EMPLAZATORIO, AVISO, COMUNICADO, CIRCULAR, LICITACION, CONVOCATORIA, PUBLICIDAD |
| `TestContentType` | 5 | publicidad_only, not_publicidad, edicto_only, not_edicto, edicto+remate |
| `TestMandatoryFields` | 5 | strong present, no fields, weak only, min_strong pass/fail |
| `TestCoOccurrence` | 4 | expediente↔finca, demandante↔demandado, sin advertencias |
| `TestNoticeValidator` | 5 | válido, header inválido, edicto, incompleto, requires_review |
| `TestConsistency` | 5 | sin inconsistencias, base mismatch, finca mismatch, same party, fecha imposible |
| `TestDuplicateDetector` | 4 | unique, duplicated, likely, reset |
| `TestScoring` | 2 | score alto, score bajo |
| `TestOrchestrator` | 4 | válido, inválido, duplicado, batch |
| **Total** | **50** | |

**498 tests total** (448 existentes + 50 nuevos) — todos pasan.

---

## Métricas

| Concepto | Valor |
|---|---|
| Pipeline errors | 0 |
| Avisos detectados vs descartados | dependiente del documento |
| Headers válidos aceptados | 7 patrones |
| Headers inválidos rechazados | 9 patrones |
| Reglas de co-ocurrencia | 8 pares |
| Verificaciones de consistencia | 5 tipos |
| Score granularidad | 9 componentes, 0.00–1.00 |
| Tests nuevos | 50 |
| Tests totales | 498 |

---

## Limitaciones

1. **Dependiente de la calidad del OCR** — si el OCR no detecta el header, el validador no puede validarlo
2. **Sin retroalimentación** — las decisiones del validador no se re-ingesan en el knowledge engine (futura fase)
3. **Sin historial** — el DuplicateDetector es intra-documento (no persiste entre ejecuciones)
4. **CO PDF tabular** — el validador asume texto plano; formato tabular requiere pre-procesamiento
5. **Reglas de co-ocurrencia fijas** — no se aprenden automáticamente de los datos

---

## Ejemplo de Decisión

```python
NoticeDecision(
    aviso_id="doc_001",
    decision=VALID,
    score=0.85,
    rules_applied=[
        RuleResult(rule_name="valid_header", passed=True, details="AVISO DE REMATE"),
        RuleResult(rule_name="min_one_strong_field", passed=True, details="expediente, finca"),
        RuleResult(rule_name="structural_coherence", passed=True),
        RuleResult(rule_name="field_co_occurrence", passed=True),
    ],
    rules_failed=[],
    fields_found=["expediente", "finca", "precio_base", "demandante", "demandado", "fecha_remate"],
    fields_missing=[],
    inconsistencies=[],
    header_detected="AVISO DE REMATE",
    header_valid=True,
    structural_valid=True,
)
```

---

## Integración

El `ValidationOrchestrator` se instancia en `CertificationRunner.__init__()` y se ejecuta como stage 9 después de Knowledge:

```python
# certification_runner.py — stage 9
v_result = self._validator.validate_notice(
    aviso_id=document_id,
    text=aviso_text,
    fields_found=normalized_fields,
)
```

El resultado incluye `result["validation"]` con la decisión completa serializada y `result["stages"]["validation"]` con resumen legible para el reporte final de certificación.
