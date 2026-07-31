# FASE 4.3 — Validación con Datos Reales

## Estado: COMPLETADO ✓

### Resumen

Pipeline completo (Assembly → OCR → Mapping → Segmentation → Continuity) validado con datos reales de Panamá y Colombia.

| Dato | Archivos | Resultado |
|---|---|---|
| Panamá (La Prensa, 9 jul 2026) | 6 imágenes (`imagen1.jpg` – `imagen6.jpg`) | ✅ Pipeline ejecutado, 6 páginas procesadas, 6 avisos candidatos |
| Colombia (SEJURE 28 jul 2025) | 1 PDF (19 páginas) | ✅ Detectado como `pdf_scanned`, requiere OCR |

### 1. Panamá — DocumentAssembly

| Métrica | Valor |
|---|---|
| Source type | `panama_newspaper` |
| Archivos | 6 |
| Páginas detectadas | **6** (esperado: 3) |
| Posiciones | 6× `full` (esperado: 3× top + 3× bottom) |

**Issue detectado**: Los archivos se llaman `imagen1.jpg` – `imagen6.jpg`. No contienen keywords de posición (`sup`/`inf`/`top`/`bottom`) en el nombre. El `SequenceDetector` clasifica todo como `full`.

**Impacto**: Cada imagen se trata como página independiente. Se esperaba que `imagen1+imagen2 = página 1`, `imagen3+imagen4 = página 2`, `imagen5+imagen6 = página 3`.

### 2. Panamá — Google Vision OCR

| Métrica | Valor |
|---|---|
| Imágenes procesadas | 6/6 (100%) |
| Tiempo total | ~59s (10s promedio por imagen) |
| Caracteres por imagen | 33K – 51K |
| Tamaño promedio imagen | 2953×3107 px |

OCR con `DOCUMENT_TEXT_DETECTION` + hint español. Reconocimiento correcto de texto periodístico (incluye acentos, caracteres especiales). Sin errores de API.

### 3. Panamá — Segmentación

| Métrica | Valor |
|---|---|
| Páginas segmentadas | 6 |
| Avisos detectados | **6** (1 por página) |
| Columnas detectadas | **1 por página** |
| Confianza promedio | **0.96** |

**Issue detectado**: Cada página (imagen individual) produce exactamente 1 aviso candidato con 1 columna. Esto ocurre porque:

- El `BlockDetector` agrupa todo el texto de la imagen en un solo bloque
- No hay cabeceras `"AVISO DE REMATE"` para dividir en múltiples avisos
- El `ColumnDetector` asigna todo a 1 columna (el contenido de página completa es una sola columna de texto)

**Análisis cualitativo**: El texto OCR corresponde a páginas completas de La Prensa con múltiples secciones (clasificados, edictos, avisos). La segmentación actual no diferencia entre secciones dentro de una misma página de periódico. Para periódico Panamá, se necesita un paso adicional de **Page Stitching** (unir las 2 imágenes que pertenecen a la misma página) y luego detectar avisos individuales dentro de la página completa.

### 4. Panamá — Continuity Engine

| Métrica | Valor |
|---|---|
| Fragmentos | 6 (todos `full`) |
| CompleteAvisos | 6 (todos single-fragment) |
| Reconstrucciones | 0 |

**Issue detectado**: Sin detección top/bottom, el `ContinuityEngine` no puede emparejar fragmentos. Todos se tratan como avisos completos independientes.

### 5. Colombia — PDF Analysis

| Métrica | Valor |
|---|---|
| PDF type | `pdf_scanned` |
| Páginas | **19** |
| Tamaño | 3,662 KB |
| Capa de texto | No detectada (0 chars en páginas 1-3) |

**Análisis**: El PDF es escaneado (imágenes de documentos). Sin capa de texto. Requiere OCR antes de segmentación. PyMuPDF está disponible para convertir PDF a imágenes.

### Issues Encontrados

| # | Issue | Severidad | Solución propuesta |
|---|---|---|---|
| 1 | Archivos Panama sin keywords `sup`/`inf` | Alta | Agregar convención de nombres o usar metadata externa |
| 2 | 6 páginas en vez de 3 (sin top/bottom pairing) | Alta | Implementar Page Stitching antes de segmentación |
| 3 | 1 columna por página en periódico multi-columna | Media | Ajustar `ColumnDetector` para layout periodístico |
| 4 | 1 aviso por página (no hay splitting por aviso individual) | Media | Implementar detección de avisos múltiples dentro de página |
| 5 | PDF Colombia escaneado requiere OCR pipeline | Media | Pipeline Colombia: PyMuPDF → Vision OCR → Segmentación |
| 6 | `SegmentedPage.to_dict()` no exporta columnas | Baja | Mejorar serialización |

### Recomendaciones

1. **Page Stitching**: Antes de segmentar periódico Panamá, unir las 2 imágenes (top+bottom) que pertenecen a la misma página. Esto requiere nombrar los archivos con el formato `{page}_{position}.jpg` (ej. `01_sup.jpg`, `01_inf.jpg`).

2. **Page Splitting**: Después del stitching, dividir la página completa en avisos individuales usando detección de cabeceras (no solo "AVISO DE REMATE" sino también "EDICTO EMPLAZATORIO", etc.) y separadores geométricos.

3. **Multi-columna**: Ajustar `ColumnDetector` para detectar el layout de 2-3 columnas típico del periódico La Prensa. Considerar usar el ancho de página y densidad de texto para inferir número de columnas.

4. **Pipeline Colombia**: Integrar PyMuPDF → Vision OCR → Segmentación para PDFs escaneados.

5. **Convención de nombres**: Para Panamá, requerir que los archivos sigan el patrón `{pagina}_{posicion}.{ext}` donde posición es `sup` o `inf`. Alternativamente, usar un archivo de metadata que mapee archivos a páginas.

### Archivos generados

| Archivo | Contenido |
|---|---|
| `evaluation/real_data/validate_pipeline.py` | Script de validación |
| `evaluation/real_data/panama_assembly.json` | SourceDocument Panama |
| `evaluation/real_data/panama_ocr_summary.json` | Resumen OCR Panama |
| `evaluation/real_data/panama_ocr_sample.json` | Muestra texto OCR página 1 |
| `evaluation/real_data/panama_segmented.json` | SegmentedDocument Panama |
| `evaluation/real_data/panama_continuity.json` | CompleteAvisos Panama |
| `evaluation/real_data/colombia_pdf_analysis.json` | Análisis PDF Colombia |
| `evaluation/real_data/validation_metrics.json` | Métricas consolidadas |

### Próximo paso

Implementar las correcciones identificadas antes de proceder a FASE 5 (Parser Engine):
1. Page Stitching para Panamá (unir top/bottom antes de segmentar)
2. Mejora de detección multi-columna
3. Splitting de avisos múltiples por página
