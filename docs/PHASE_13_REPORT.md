# FASE 13 — Real World Accuracy Optimization (Panamá Prioritario) — Reporte

Determinista y auditable: cada artefacto mide documentos reales (OCR de uploads,
samples del cliente, parser_validation, golden dataset). Sin arquitectura nueva,
sin cambios en V1/OCR/AIResolver/Validator/Certification, sin parsers modificados,
sin conocimiento aprobado (0 reglas creadas). 78 tests nuevos; 0 regresiones
(926 + 78 = 1004 passed).

## Resumen ejecutivo

| Métrica | Valor |
| --- | --- |
| Documentos reales analizados | 72 (PA 32, CO 40) |
| Precisión Panamá | 1.0 (52 TP / 0 FP / 6 FN) |
| Recall Panamá | 0.8966 |
| F1 Panamá | 0.9455 |
| Precisión/Recall Colombia | 0.0 (honesto: el grid `EJ ./DIV .` no tiene etiquetas) |
| Campos perdidos totales | 69 (63 CO + 6 PA) |
| Sugerencias generadas | 53 (ninguna aprobada) |
| Reglas creadas | 0 (knowledge.db real vacío; nada se aprueba automáticamente) |
| Tests | 1004 passed (926 + 78 nuevos), 0 regresiones |

## Parte 1-2 — Corpus estadístico real (Panamá First)

Artefactos: `output/country_statistics.{json,md}`

- Corpus = 72 documentos de 6 fuentes, siempre PA primero:
  - PA (32): 13 imágenes OCR real (La Prensa), 6 avisos canónicos del cliente,
    7 variantes de parser_validation, 6 records golden.
  - CO (40): 5 PDFs SEJURE/extras OCR real, 16 samples, 3 parser_validation, 16 golden.
- Formato canónico del cliente (PA) verificado: `AVISO DE REMATE / JUZGADO:
  JUZGADO MUNICIPAL DE PANAMA / EXPEDIENTE N° 112235-24 / DEMANDANTE / DEMANDADO /
  AVALÚO COMERCIAL: $5.000.00`.
- Estadísticas reales PA: 179+ ocurrencias de `JUZGADO`, 247 evidencia de juzgado,
  formatos monetarios `$5.000.00`, `B/.85,000.00`, expedientes cortos (`112235-24`)
  y largos (`1029202000030580`), fechas `12 DE MARZO DE 2026`, matrículas
  `12345-678`, porcentajes `10% / 1/4` (mínimo/fianza de postor).

## Parte 5 — Pattern Discovery Engine

Artefacto: `output/pattern_discovery.{json,md}`

- Palabras partidas por OCR: `JUDI-CIAL -> JUDICIAL` (34), `CIR-CUITO -> CIRCUITO`
  (26), `NOR-ESTE -> NORESTE` (57).
- Palabras unidas por OCR: `DIREC+CION -> DIREC CION` (499), `JUDI+CIAL` (444),
  `CIR+CUITO` (405), `JUZ+GADO` (247).
- Acentos perdidos: `PANAMA -> PANAMÁ` (353), `NUMERO -> NÚMERO` (166),
  `CENTIMETROS -> CENTÍMETROS` (390).
- Símbolos: `%` (210), `°` (177), variantes de `N°` (`N ° `, `N `, `N`).
- Colombia: grid compacto con labels reales `EJ .`, `DIV .`, `C.C. No.`,
  `No.001-`, `LOT .`, `MZ .`, `URB .`, `$181.080.000` — sin etiquetas EXPEDIENTE/
  DEMANDANTE → causa raíz de la pérdida CO.

## Parte 6 — Coverage Analyzer real

Artefacto: `output/coverage_real.{json,md}`

- 33 campos del catálogo medidos contra texto OCR real: muchos campos del
  catálogo NUNCA aparecen en documentos reales (categoria, codigo_*, plano,
  prevista, superficie, email_observaciones, etc.) — candidatos a limpieza.
- Campos exclusivos PA: `lugar`, `provincia`. Exclusivos CO: `fianza_porcentaje`,
  `minimo_porcentaje` (en el golden CO).
- **Campos con evidencia real que NO existen en el catálogo**: `juzgado`
  (247 PA / 32 CO) y `municipio` (97 CO) — el parser PA no puede devolver juzgado
  porque el catálogo no lo tiene; `avaluo` y `matricula` se mapean como evidencia
  de `precio_base` y `finca`.

## Partes 4+7 — Sugerencias y Knowledge Analytics

Artefactos: `output/knowledge_suggestions.{json,md}`, `output/knowledge_analytics.{json,md}`

- 53 sugerencias (PA primero): alias de labels (p. ej. `MATRICULA` -> `MATRÍCULA`),
  expresiones recurrentes y labels nuevos. **Todas con estado SUGERENCIA,
  `aprobado: false`** — requieren revisión humana.
- knowledge.db real: 0 reglas, 0 correcciones (verificado abriendo la DB real).
- Por qué está vacía: el pipeline no aprende (AIFeedbackTracker solo registra
  métricas), las reglas se crean solo por aprobación manual, y el flujo de
  correcciones nunca se activó en producción.
- 14 candidatos de regla con evidencia real >= 3 (útiles), 1 aprendible, 3 sin
  evidencia (ignorables) — **ninguno se crea**.

## Parte 8 — Parser Gap

Artefacto: `output/parser_gap.{json,md}`

- Fuentes: 63 avisos CO anclados (aviso_por_aviso), 24 PA canónicos cliente,
  34 PA parser_validation, 78 PA benchmark imágenes.
- 199 filas; 121 con golden; 69 pérdidas totales, TODAS en parser (`parser_pierde`):
  - CO (63): expediente 16, precio_base 16, demandante 16, demandado 15 —
    el parser CO no lee el grid.
  - PA (6): precio_base 6 — el formato cliente `AVALÚO COMERCIAL: $5.000.00`
    no está en los patrones del parser PA.
- Validator: 63 avisos CO certificados INVALID (correcto: nada extraído).
- Knowledge no aplica: 0 reglas. IA: 0 recupera / 0 no recupera (solo cubre los
  campos permitidos por policy en benchmark, sin golden para medir).

## Parte 9 — False Positive Report

Artefacto: `output/false_positive_report.{json,md}`

- 1 página descartada correctamente (edicto sin aviso de remate); 0 incorrectos.
- 27 expedientes duplicados REALES: el mismo aviso aparece en varias imágenes
  (p. ej. `32852-2026` en 3 JPG + 1 sample; `153929` en 3 PDFs CO; los 6 canónicos
  PA duplican golden vs sample — fuente sintética, no error).
- 10 falsos duplicados: prefijos de 6 dígitos (`483992026` vs `483992025`, etc.).
- 16 rechazados, 6 inválidos aceptados (resultados FASE 12, sin regresión).

## Parte 13 — Dashboard de Precisión

Artefacto: `output/production_accuracy.{json,md}`

- **Panamá: precision 1.0, recall 0.8966, F1 0.9455** (52 TP / 0 FP / 6 FN).
  Por campo: expediente/finca/demandante/demandado/fecha_remate recall 1.0;
  **precio_base recall 0.5** (6 FN por `AVALÚO COMERCIAL` no cubierto).
- **Colombia: 0.0** — el grid real no tiene etiquetas; ningún campo TP.
- Cobertura por campo: PA 1.0 en expediente vs CO 0.0 — la brecha real es el
  formato, no la cantidad de datos.
- Origen: Parser 52 campos correctos, IA 0, Knowledge 0, Perdidos 69.

## Parte 14 — Tests (78 nuevos, 0 regresiones)

`backend/app/v2/tests/test_phase13.py` — corpus (72 docs, PA-first, fuentes),
country_statistics, pattern discovery, coverage (33 campos, faltan juzgado/
municipio), sugerencias (53, nunca aprobadas), knowledge analytics (db vacía),
parser gap (69 pérdidas, 63 CO), false positives (duplicados reales),
dashboard (métricas PA/CO exactas), orquestador (artefactos, determinismo,
**no modifica knowledge.db ni parsers**).

## Hallazgos accionables (Panamá primero)

1. **Catálogo**: agregar campos `juzgado` y `municipio` (evidencia real 247/97).
2. **Parser PA**: cubrir el label cliente `AVALÚO COMERCIAL:` → +6 TP de precio
   base (recall PA 0.8966 → 1.0).
3. **Parser CO**: el grid `EJ ./DIV .` requiere un extractor propio (estructura
   columnar); la etiqueta `No.` + `$monto` + `Vs.` permite extracción por patrón.
4. **OCR normalization**: aplicar diccionario de correcciones (partidas/unidas/
   acentos) antes de parsers.
5. **Knowledge**: las 14 reglas útiles esperan aprobación humana; nada automático.

## Reproducción

```
$env:PYTHONPATH='C:\Users\user\Documents\RemateUp'
python -m backend.app.v2.evaluation.accuracy.phase13
python -m pytest backend/app/v2/tests/test_phase13.py -q
python -m pytest backend/app/v2/tests -q
```
