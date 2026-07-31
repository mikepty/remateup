# FASE 4 — Segmentation Engine

## Estado: COMPLETADO ✓

### Pipeline de segmentación

```
OCRDocument (OCRPage, OCRBlock, OCRWord con bounding boxes)
        ↓
  LineDetector — Agrupa palabras en líneas por proximidad Y
        ↓
  BlockDetector — Agrupa líneas en bloques por gap vertical
        ↓
  ColumnDetector — Detecta columnas mediante histograma de proyección
        ↓
  SectionDetector — Clasifica bloques en secciones semánticas (HEADER, PARTIES, VALORES, PORTADA, etc.)
        ↓
  SegmentationEngine — Detecta avisos individuales, arma SegmentedDocument
        ↓
  SegmentationScorer — Calcula confianza de segmentación
```

### Archivos creados/modificados

| Archivo | Estado | Descripción |
|---|---|---|
| `backend/app/v2/segmenter/models.py` | ✓ Nuevo | `SegmentedDocument`, `SegmentedPage`, `DetectedAviso`, `DetectedSection`, `DetectedBlock`, `DetectedLine`, `DetectedColumn`, `BoundingBox` |
| `backend/app/v2/segmenter/engine.py` | ✓ Implementado | Orquestador: OCRDocument → SegmentedDocument |
| `backend/app/v2/segmenter/block_detector.py` | ✓ Implementado | Agrupa líneas en bloques por gap vertical (ratio 1.5x) |
| `backend/app/v2/segmenter/column_detector.py` | ✓ Implementado | Detecta columnas por histograma de centros X (bucket page_width/4) |
| `backend/app/v2/segmenter/line_detector.py` | ✓ Implementado | Agrupa palabras en líneas por proximidad Y; merge de split-words |
| `backend/app/v2/segmenter/section_detector.py` | ✓ Implementado | Clasifica secciones: HEADER, PARTIES, VALORES, UBICACION, DESCRIPCION, PORTADA vs FULL |
| `backend/app/v2/segmenter/relationship_detector.py` | ✓ Implementado | Detecta pares label-valor (EXPEDIENTE, FINCA, BASE, DEMANDANTE, etc.) |
| `backend/app/v2/segmenter/scoring.py` | ✓ Implementado | Scoring de segmentación por cobertura, columnas, avisos |
| `backend/app/v2/segmenter/__init__.py` | ✓ Actualizado | Exporta todas las clases |
| `backend/app/v2/tests/test_segmenter_models.py` | ✓ Nuevo | 24 tests para modelos |
| `backend/app/v2/tests/test_segmenter_detectors.py` | ✓ Nuevo | 39 tests para detectores |
| `backend/app/v2/tests/test_segmenter_engine.py` | ✓ Nuevo | 11 tests para engine |

### Resultados de tests

**175 tests — 175 passed, 0 failed, 0 errors**

| Suite | Tests |
|---|---|
| FASE 2 (document + OCR + evidence) | 48 |
| FASE 3 (VisionClient + Mapper + Processor) | 46 |
| FASE 4 — Models | 24 |
| FASE 4 — Detectors | 39 |
| FASE 4 — Engine | 11 |
| **Total (test runner)** | **175** |
| + test_vision_client + test_vision_mapper + test_vision_processor | 7 extra |

### PORTADA vs AVISO JUDICIAL COMPLETO

El `SectionDetector` implementa detección de PORTADA basada en:
- **Texto corto** (< 300 chars) sin header "AVISO DE REMATE" pero con keywords (finca, expediente)
- **Palabra clave** "PORTADA", "RESUMEN", "CONTENIDO", "SUMARIO" en el texto
- **Texto muy corto** (< 3 líneas) con keyword "REMATE" pero sin header completo
- Textos largos (> 800 chars) o con header "AVISO DE REMATE" NO se clasifican como portada

### Geometría utilizada

El segmenter trabaja exclusivamente con geometría (bounding boxes):
1. **LineDetector**: proximidad Y entre palabras (tolerance = avg_word_height * 0.008, min 3px)
2. **BlockDetector**: gap vertical entre líneas (threshold = avg_line_height * 1.5, min 10px)
3. **ColumnDetector**: histograma de centros X de bloques (bucket = page_width/4, min 3 palabras por columna)
4. **SectionDetector**: posición relativa y contenido textual
5. **Engine**: headers "AVISO DE REMATE" como separadores de avisos

### Reglas respetadas

1. ✅ El mapper NO mueve lógica de segmentación — solo produce words/paragraphs/blocks/coordinates
2. ✅ El segmenter trabaja con geometría (bounding boxes, columnas, separación vertical)
3. ✅ Diferencia PORTADA/RESUMEN de AVISO JUDICIAL COMPLETO
4. ✅ No extrae campos (finca, precio, propietario) — eso pertenece al Parser Engine
5. ✅ Resultado intermedio: `SegmentedDocument` con páginas, secciones, avisos, bloques, confidence

### Ejemplos visuales de segmentación

**Documento de 1 página sin bloques:**
```
SegmentedDocument → pages[0]: SegmentedPage(page=1, avisos=0, confidence=0.0)
```

**Documento con texto "AVISO DE REMATE FINCA 30269 BASE $150,000":**
```
SegmentedDocument
  └── pages[0]
        ├── columns[0] (single column)
        │     └── blocks[0]: DetectedBlock("AVISO DE REMATE FINCA 30269 BASE $150,000")
        └── avisos[0]
              ├── header_text: "AVISO DE REMATE"
              ├── is_portada_resumen: false
              ├── sections[0]: DetectedSection(HEADER, "AVISO DE REMATE")
              └── confidence: 0.95
```

**Texto corto sin header "FINCA 12345 EXP 6789" (PORTADA):**
```
avisos[0]
  ├── header_text: ""
  ├── is_portada_resumen: true
  └── confidence: > 0
```

### Próximo paso

FASE 5 — Parser Engine (extraer campos como finca, precio, propietario del texto segmentado)
