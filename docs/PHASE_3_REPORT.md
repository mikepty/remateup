# FASE 3 — Google Vision OCR Adapter

## Estado: COMPLETADO ✓

### Arquitectura implementada

```
Google Cloud Vision API (REST)
        ↓
  VisionClient (client.py)
        ↓
  OCRProcessor (processor.py)
        ↓
  OCRMapper (mapper.py)
        ↓
  OCRDocument / OCRPage / OCRBlock / OCRWord (models.py)
        ↓
  Document Domain Model (document/models.py)
```

### Archivos creados/modificados

| Archivo | Estado | Descripción |
|---|---|---|
| `backend/app/v2/ocr/client.py` | ✓ Implementado | Conexión REST con Google Vision, manejo de errores, configuración |
| `backend/app/v2/ocr/processor.py` | ✓ Implementado | Envío de imágenes/PDF, procesamiento de respuestas |
| `backend/app/v2/ocr/mapper.py` | ✓ Implementado | Conversión respuesta Vision → modelos internos con reconstrucción multi-columna |
| `backend/app/v2/ocr/__init__.py` | ✓ Actualizado | Exporta todas las clases públicas |
| `backend/app/v2/tests/test_vision_client.py` | ✓ Nuevo | 14 tests para VisionClient |
| `backend/app/v2/tests/test_vision_mapper.py` | ✓ Nuevo | 18 tests para OCRMapper |
| `backend/app/v2/tests/test_vision_processor.py` | ✓ Nuevo | 14 tests para OCRProcessor |

### Detalle de implementación

**client.py — VisionClient**
- Comunicación REST directa con `requests` (sin google-cloud-vision SDK)
- Auth via API key en query string
- `annotate(image_bytes)` para una imagen; `annotate_batch(images)` para múltiples
- Manejo de errores: `VisionAPIError` (HTTP/api errors), `VisionClientError` (timeout/connection)
- Configurable via `VisionClientConfig` (api_key, base_url, timeout, language_hints, feature_type)
- `is_available()` para verificar si hay API key configurada
- Tiempo de timeout configurable (default 120s)
- Language hints español por defecto, feature `DOCUMENT_TEXT_DETECTION`

**processor.py — OCRProcessor**
- `process_image(path)` → lee archivo, llama client.annotate(), mapea a OCRDocument
- `process_pdf(path, dpi=144)` → renderiza con PyMuPDF (fitz), envía cada página a Vision, combina resultados
- `process_multiple(paths)` → soporta mix de imágenes (png/jpg/tiff/webp) y PDFs
- Inyecta dependencias: `VisionClient` y `OCRMapper` (testeable con mocks)

**mapper.py — OCRMapper**
- `map_response(vision_response)` → convierte respuesta completa de Vision API a OCRDocument
- `map_text_annotation(annotation)` → convierte solo fullTextAnnotation a OCRPage
- Extrae páginas, bloques, párrafos, palabras con bounding boxes y confianza
- Reconstrucción de texto multi-nivel (heredado de V1):
  1. Word-level con detección de columnas (proyección de histograma)
  2. Block-level con agrupación por columnas
  3. Plain text de vision API (fallback)
- Manejo de detectedBreak (SPACE, LINE_BREAK, HYPHEN, EOL_SURE_SPACE)
- Sin dependencia de Tesseract

### Tests

**94 tests — 94 passed, 0 failed, 0 errors**

| Suite | Tests |
|---|---|
| FASE 2 (document + OCR + evidence) | 48 |
| FASE 3 — VisionClient | 14 |
| FASE 3 — OCRMapper | 18 |
| FASE 3 — OCRProcessor | 14 |
| **Total** | **94** |

### Principios respetados

1. ✅ **Sin Tesseract** — no se agregó ni importó Tesseract en ningún archivo
2. ✅ **Google Vision como único motor OCR** — la integración usa REST API de Vision
3. ✅ **Sin dependencia de Claude** — el módulo no usa ninguna IA generativa
4. ✅ **Sin dependencia de SQLAlchemy** — modelos puramente Python
5. ✅ **Testeable con mocks** — todas las dependencias son inyectables

### Próximo paso

FASE 4 — Módulo de Segmentación (detectar avisos individuales en página de periódico)
