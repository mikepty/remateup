# FASE 4.4 + 4.5 — Page Reconstruction + Layout Segmentation

## Estado: COMPLETADO ✓

### Resumen

Implementación de dos capacidades identificadas como necesarias durante la validación con datos reales (FASE 4.3):

| FASE | Nombre | Archivos |
|---|---|---|
| 4.4 | Newspaper Page Reconstruction | `document/stitching.py` |
| 4.5 | Newspaper Layout Segmentation | `segmenter/column_analyzer.py`, `notice_detector.py`, `newspaper_layout.py` |

---

## FASE 4.4 — Page Reconstruction

### Problema

Los periódicos de Panamá se entregan como pares de imágenes (superior + inferior de cada página). El pipeline anterior dependía de keywords en nombres de archivo (`sup`/`inf`) para detectar posición, pero en datos reales los archivos se llaman `imagen1.jpg`, `imagen2.jpg`, etc.

### Solución

**SequenceDetector** modificado: cuando country=`PA` y no hay keywords de posición en los nombres, se empareja por **orden de subida**:
- índice impar (0, 2, 4) = fragmento superior
- índice par (1, 3, 5) = fragmento inferior

### PageStitcher (`document/stitching.py`)

Une dos OCRPage (top + bottom) en un StitchedPage preservando geometría:

| Propiedad | Comportamiento |
|---|---|
| Blocks top | Sin modificar (coordenadas originales) |
| Blocks bottom | Y offset = height del fragmento superior |
| X coordinates | Sin modificar |
| Width | max(top.width, bottom.width) |
| Height | top.height + bottom.height |
| Reading order | Top blocks primero, bottom blocks después |
| `to_ocr_page()` | Convierte a OCRPage para pipeline descendente |

### Modelos nuevos

- **FragmentMapping**: mapeo top→bottom con offset Y
- **StitchedBlock**: bloque con coordenadas ajustadas + metadato `source_position` ("top"/"bottom")
- **StitchedPage**: página reconstruida con blocks, texto completo, y método `to_ocr_page()`

---

## FASE 4.5 — Layout Segmentation

### Problema

La segmentación genérica trataba cada página completa como 1 aviso con 1 columna. Para periódicos se necesita:
1. Detectar múltiples columnas (histograma de proyección vertical)
2. Detectar avisos de remate específicamente (no edictos genéricos)
3. Mantener continuidad top/bottom dentro del aviso

### ColumnAnalyzer (`segmenter/column_analyzer.py`)

Detección de columnas mediante:

1. **Perfil de proyección vertical**: histograma de densidad de texto por píxel X
2. **Detección de gaps**: espacios verticales sin texto (whitespace entre columnas)
3. **Construcción**: cada gap define un límite de columna; se asignan blocks por centro X

| Parámetro | Default | Descripción |
|---|---|---|
| `MIN_TEXT_DENSITY` | 3 | Densidad mínima para considerar "con texto" |
| `MIN_COLUMN_WIDTH_RATIO` | 0.08 | Ancho mínimo de columna (8% del page width) |
| `MAX_COLUMNS` | 4 | Límite superior de columnas detectables |

### NoticeDetector (`segmenter/notice_detector.py`)

Detección estricta de remates judiciales. Solo reconoce:

| Header | Incluido |
|---|---|
| `AVISO DE REMATE` | ✅ |
| `REMATE JUDICIAL` | ✅ |
| `SUBASTA JUDICIAL` | ✅ |
| `EDICTO EMPLAZATORIO` | ❌ Excluido |
| `AVISO` (genérico) | ❌ Excluido |
| `EDICTO` (genérico) | ❌ Excluido |

Agrupa blocks por cabecera: cada ocurrencia de un header inicia un nuevo aviso candidato.

### NewspaperLayout (`segmenter/newspaper_layout.py`)

Orquestador:
```
StitchedPage
    ↓ ColumnAnalyzer → columnas
    ↓ NoticeDetector → avisos por columna
    ↓ DetectedAviso[]
```

---

### Tests

| Archivo | Tests | Descripción |
|---|---|---|
| `tests/test_stitching.py` | 12 | Stitching: offset Y, preservación X, reading order, fragment mapping |
| `tests/test_newspaper_layout.py` | 24 | ColumnAnalyzer (8), NoticeDetector (10), NewspaperLayout (6) |
| `tests/test_assembly.py` | 27 (+1) | Nuevo: `test_panama_six_images_sequential_paired` |

### Resultados

**258 tests — 258 passed, 0 failed, 0 errors**

### Reglas respetadas

1. ✅ Sin LLM ni IA generativa — ColumnAnalyzer usa histograma, NoticeDetector usa regex
2. ✅ Sin dependencia de nombres de archivo — Panama usa orden de subida
3. ✅ Edictos excluidos — solo REMATE, REMATE JUDICIAL, SUBASTA JUDICIAL
4. ✅ Geometría preservada — stitching mantiene bounding boxes + coordenadas

### Archivos creados/modificados

| Archivo | Estado | Descripción |
|---|---|---|
| `backend/app/v2/document/stitching.py` | ✓ Nuevo | PageStitcher, StitchedPage, FragmentMapping, StitchedBlock |
| `backend/app/v2/segmenter/column_analyzer.py` | ✓ Nuevo | ColumnAnalyzer con proyección vertical |
| `backend/app/v2/segmenter/notice_detector.py` | ✓ Nuevo | NoticeDetector (solo remates judiciales) |
| `backend/app/v2/segmenter/newspaper_layout.py` | ✓ Nuevo | NewspaperLayout (orquestador) |
| `backend/app/v2/document/sequence.py` | ✓ Modificado | Panama pairing por orden cuando no hay keywords |
| `backend/app/v2/tests/test_stitching.py` | ✓ Nuevo | 12 tests |
| `backend/app/v2/tests/test_newspaper_layout.py` | ✓ Nuevo | 24 tests |
| `backend/app/v2/tests/test_assembly.py` | ✓ Modificado | +1 test sequential pairing |

### Pipeline Panama actualizado

```
imagen1.jpg (top) ──┐
                     ├── DocumentAssembly (par por orden) ──→ SourceDocument (3 páginas)
imagen2.jpg (bottom) ┘                              │
                                                    ▼
                                              OCRProcessor (6 imágenes)
                                                    │
                                                    ▼
                                              PageStitcher (3 StitchedPage)
                                                    │
                                                    ▼
                                              NewspaperLayout
                                                    │
                                              ColumnAnalyzer → NoticeDetector → DetectedAviso[]
                                                    │
                                              ContinuityEngine (si aplica)
```

### Próximo paso

FASE 5 — Parser Engine (extraer campos estructurados: finca, base, precio, propietario, etc.)
