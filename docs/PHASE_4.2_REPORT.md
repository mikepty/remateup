# FASE 4.2 — Document Assembly Layer

## Estado: COMPLETADO ✓

### Contexto

Los documentos llegan en dos formatos distintos según el país:
- **Panamá (PA)**: Páginas de periódico en pares de imágenes (superior + inferior), ej. `p1_sup.jpg`, `p1_inf.jpg`
- **Colombia (CO)**: Documentos PDF, que pueden tener capa de texto (`pdf_text`) o ser escaneados (`pdf_scanned`)

La capa de ensamblaje transforma archivos crudos en un `SourceDocument` estructurado con páginas y fragmentos.

### Arquitectura

```
Archivos crudos (file_paths)
       │
       ▼
 SequenceDetector ── detecta país y estructura ──► SourceDocument
       │                                                    │
       ├─ PA: agrupa top/bottom por posición                │
       │   (sup/inf → top/bottom,                            │
       │    full → página individual)                        │
       │                                                    │
       └─ CO: analiza PDF via PDFAnalyzer                   │
           (PyMuPDF para text vs scanned)                   │
                                                            ▼
                                                  DocumentPages c/u con
                                                  ImageFragment(s)
```

### Archivos creados/modificados

| Archivo | Estado | Descripción |
|---|---|---|
| `backend/app/v2/document/assembly.py` | ✓ Nuevo | `DocumentAssembly` + `PDFAnalyzer` (text vs scanned) |
| `backend/app/v2/document/sequence.py` | ✓ Nuevo | `SequenceDetector` — agrupación top/bottom, auto-detection |
| `backend/app/v2/document/models.py` | ✓ Extendido | `SourceDocument`, `SourceType`, `DocumentPage`, `ImageFragment` |
| `backend/app/v2/document/__init__.py` | ✓ Actualizado | Exporta nuevas clases |
| `backend/app/v2/tests/test_assembly.py` | ✓ Nuevo | 26 tests de ensamblaje |

### Detalle de implementación

#### SourceType (enum)

| Valor | Propósito |
|---|---|
| `PANAMA_NEWSPAPER` | Periódico Panamá (pares de imágenes) |
| `COLOMBIA_PDF_TEXT` | PDF Colombia con capa de texto |
| `COLOMBIA_PDF_SCANNED` | PDF Colombia escaneado |
| `PDF_MIXED` | PDF con páginas mixtas text/scanned |
| `IMAGE` | Imagen suelta |
| `UNKNOWN` | No identificado |

#### SequenceDetector — Lógica de detección

1. **PA explícito** (`country="PA"` o `"PANAMA"`): agrupa por posición
2. **CO explícito** (`country="CO"` o `"COLOMBIA"`): analiza PDF(s)
3. **Auto-detect**: si hay exactamente 1 PDF y 0 imágenes → Colombia; si hay imágenes → Panamá

#### Position keywords (token-based)

Se dividen los stems por `[^a-z0-9]` y se compara cada token contra keywords:

| Posición | Keywords |
|---|---|
| `top` | superior, upper, top, sup, arriba |
| `bottom` | inferior, lower, bottom, inf, abajo |

#### PDFAnalyzer

- PyMuPDF opcional (fallback a `"unknown"` si no está instalado)
- Lee hasta 5 páginas, si alguna contiene ≥100 chars de texto → `pdf_text`
- Si ninguna página tiene texto → `pdf_scanned`
- Si error de apertura → `unknown`

#### DocumentPage e ImageFragment

- `ImageFragment`: path, page_position ("top"/"bottom"/"full"), page_number
- `DocumentPage`: page_number, fragments[], page_type
- `SourceDocument`: source_type, file_paths[], pages[], metadata

### Issues resueltos

1. ✅ **Dependencia PyMuPDF (fitz)**: `PDFAnalyzer` maneja `ImportError` y retorna `"unknown"` — no es requisito obligatorio
2. ✅ **Keywords cortas como "p1"/"p2"**: removidas por ambigüedad (ej. "p1_inf" matcheaba "p1" como top). Se usa matching por token exacto, no substring

### Tests específicos

| Test | Descripción |
|---|---|
| `test_create_fragment` | Creación de ImageFragment |
| `test_to_dict` | Serialización de modelos |
| `test_panama_two_images` | 2 imágenes → 1 página top+bottom |
| `test_panama_six_images_three_pages` | 6 imágenes → 3 páginas |
| `test_panama_auto_detection` | Auto PA por presencia de imágenes |
| `test_position_detection_top/bottom/full` | Keywords por token |
| `test_analyze_nonexistent` | PDF inexistente → unknown |
| `test_analyze_unreadable_returns_unknown` | Sin PyMuPDF → unknown |
| `test_validate_paths_*` | Validación de soporte de formatos |

### Resultados de tests

**222 tests — 222 passed, 0 failed, 0 errors**

### Reglas respetadas

1. ✅ Sin LLM ni IA generativa — solo reglas deterministas
2. ✅ PyMuPDF es opcional — graceful degradation
3. ✅ No modifica V1 — todo en `backend/app/v2/`
4. ✅ No asume estructura de nombres de archivo específica — usa detección por tokens

### Próximo paso

FASE 5 — Parser Engine (extraer campos estructurados del texto segmentado: finca, base, precio, propietario, etc.)
