# FASE 4.1 — Image/Page Continuity Engine

## Estado: COMPLETADO ✓

### Contexto

Los periódicos de Panamá se procesan mediante dos imágenes por página vertical (superior + inferior). El contenido de un aviso puede continuar entre ambas imágenes. Esta extensión detecta y reconstruye esas continuidades de forma determinista.

### Arquitectura

```
Imagen Superior (top.jpg)    Imagen Inferior (bottom.jpg)
         ↓                            ↓
   AvisoFragment (top)          AvisoFragment (bottom)
         ↓                            ↓
         └──────── ContinuityEngine ──┘
                        ↓
               CompleteAviso(s)
         (con 1 fragmento o 2+ reconstruidos)
```

### Archivos creados/modificados

| Archivo | Estado | Descripción |
|---|---|---|
| `backend/app/v2/segmenter/continuity.py` | ✓ Nuevo | `ContinuityEngine` — detección determinista de continuidad |
| `backend/app/v2/segmenter/models.py` | ✓ Extendido | `AvisoFragment`, `CompleteAviso` con factory methods |
| `backend/app/v2/document/models.py` | ✓ Extendido | `SectionType` con 5 nuevos estados |
| `backend/app/v2/segmenter/__init__.py` | ✓ Actualizado | Exporta `ContinuityEngine`, `AvisoFragment`, `CompleteAviso` |
| `backend/app/v2/tests/test_continuity.py` | ✓ Nuevo | 24 tests de continuidad |

### Detalle de implementación

#### Nuevos SectionType

| Estado | Valor | Propósito |
|---|---|---|
| `PORTADA_RESUMEN` | `"portada_resumen"` | Sección de portada/resumen |
| `AVISO_COMPLETO` | `"aviso_completo"` | Aviso completo en una sola imagen |
| `CONTINUACION_AVISO` | `"continuacion_aviso"` | Continuación de aviso entre imágenes |
| `INDICE` | `"indice"` | Contenido de índice |
| `PUBLICIDAD` | `"publicidad"` | Anuncios publicitarios |

#### ContinuityEngine — Señales deterministas

| Señal | Peso | Descripción |
|---|---|---|
| `header_in_bottom` | **-1.0** (bloqueante) | Si la imagen inferior tiene "AVISO DE REMATE" → NO hay continuidad |
| `column_alignment` | +3.0 | Misma posición X del bounding box (tolerance 2%) |
| `vertical_proximity` | +2.0 | Gap vertical entre fragmentos < 200px |
| `hyphenated_word` | +2.0 | Fragmento superior termina con guion |
| `lowercase_start` | +2.0 | Fragmento inferior empieza en minúscula |
| `incomplete_ending` | +1.5 | Fragmento superior termina incompleto (coma, dos puntos, preposición) |
| `label_value_continuity` | +2.0 | Fragmento superior termina con label (FINCA, BASE, etc.) |
| `context_similarity` | +1.0 | Overlap de palabras entre trailing y leading |

Umbral de continuidad: `score > 0`. Sin IA generativa, sin LLM.

#### AvisoFragment

- `source_image`: ruta de la imagen origen
- `page_number`: número de página
- `position`: "top" o "bottom"
- `blocks`, `bbox`: datos geométricos
- `has_header`: true si contiene "AVISO DE REMATE"
- `ends_with_hyphen`: true si termina con guion
- `ends_incomplete`: true si termina de forma incompleta
- `trailing_text`: últimos 100 caracteres
- `leading_text`: primeros 100 caracteres

#### CompleteAviso

- `fragments`: lista de AvisoFragment (1 si no hay reconstrucción, 2+ si hay)
- `text`: texto reconstruido (merge con manejo de guion)
- `aviso_type`: "aviso_completo", "continuacion_aviso", "unknown"
- `continuity_signals`: señales que activaron la continuidad

### Tests específicos

| Test | Descripción |
|---|---|
| `test_continuation_with_hyphen` | Palabra dividida entre imágenes ("corta-" + "do" → "cortado") |
| `test_continuation_lowercase_start` | Texto superior termina incompleto, inferior empieza minúscula |
| `test_continuation_column_aligned` | Misma columna X entre fragmentos |
| `test_no_continuation_new_header_in_bottom` | Falso positivo: bottom tiene nuevo "AVISO DE REMATE" |
| `test_no_continuation_different_columns` | Columnas diferentes → sin continuidad |
| `test_label_value_continuity` | Label-value cruza entre fragmentos |
| `test_merge_hyphenated_text` | Merge correcto de texto con guion |
| `test_build_fragment_from_aviso` | Conversión DetectedAviso → AvisoFragment |

### Resultados de tests

**194 tests — 194 passed, 0 failed, 0 errors**

| Suite | Tests |
|---|---|
| FASE 2 + 3 (base) | 94 |
| FASE 4 (segmenter) | 74 |
| FASE 4.1 (continuity) | 24 |
| **Total** | **194** |

### Reglas respetadas

1. ✅ Sin LLM ni IA generativa — solo señales deterministas
2. ✅ Solo aplica a periódico Panamá (top/bottom images) — no afecta PDF Colombia
3. ✅ No extrae campos (finca, precio, propietario) — eso es responsabilidad del Parser
4. ✅ Usa exclusivamente geometría + señales textuales deterministas

### Próximo paso

FASE 5 — Parser Engine (extraer campos como finca, precio, propietario del texto segmentado)
