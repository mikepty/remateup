# FASE 5 — Parser Engine

## Estado: COMPLETADO ✓

### Resumen

Parser Engine determinista que reemplaza el monolito `extraction.py` de V1. Arquitectura modular con parsers especializados por país + interfaz `AIResolver` desacoplada para fallback futuro.

### Arquitectura

```
ParserFactory
    ↓
ParserRegistry (country + document_type → parser)
    ↓
ParserInterface ←── PanamaRemateParser (regex + reglas PA)
    ↓               └── ColombiaRemateParser (regex + reglas CO)
AIResolver (interfaz para fallback Z.ai/OpenRouter/HuggingFace)
```

### Flujo de extracción

```
ParserContext (text, sections, blocks, evidence)
    ↓
ParserInterface.parse(context)
    ↓
regex + reglas geométricas
    ↓
dict[str, ParseResult]  (cada campo con: value, status, confidence, evidence)
    ↓
Si confianza < umbral → AIResolver.resolve(field, context) → ParseResult
```

### Archivos creados

| Archivo | Descripción |
|---|---|
| `parser/__init__.py` | Módulo parser |
| `parser/context.py` | `ParserContext` — country, document_type, text, sections, blocks, evidence |
| `parser/result.py` | `ParseResult` — field_name, value, status (FOUND/NOT_FOUND/REQUIRES_REVIEW), confidence, evidence |
| `parser/base.py` | `ParserInterface` (ABC) + `AIResolver` (ABC para fallback) |
| `parser/registry.py` | `ParserRegistry` — registro por (country, document_type) |
| `parser/factory.py` | `ParserFactory` — auto-registra parsers por defecto |
| `parser/documents/__init__.py` | Submódulo documentos |
| `parser/documents/panama_remate.py` | `PanamaRemateParser` — 6 campos, regex PA |
| `parser/documents/colombia_remate.py` | `ColombiaRemateParser` — 6 campos, regex CO |

### Campos extraídos

| Campo | Panama (PA) | Colombia (CO) |
|---|---|---|
| `expediente` | `EXPEDIENTE N° \d+-\d+` | `EXPEDIENTE/RADICADO N° \d+-\d+` |
| `finca` | `FINCA \d+` | `MATRÍCULA INMOBILIARIA \d+` |
| `precio_base` | `BASE B/. \d+` | `AVALÚO COMERCIAL: $\d+` |
| `fecha_remate` | `FECHA DE REMATE: \d+ DE MES DE \d+` | `FECHA DE REMATE: \d+ DE MES DE \d+` |
| `demandante` | `DEMANDANTE: ...` | `DEMANDANTE: ...` |
| `demandado` | `DEMANDADO: ...` | `DEMANDADO: ...` |

### ParseResult — Estados

| Estado | Significado |
|---|---|
| `FOUND` | Valor encontrado con evidencia |
| `NOT_FOUND` | No se encontró el campo |
| `REQUIRES_REVIEW` | Encontrado pero con baja confianza |
| (nunca se devuelven valores sin evidencia) |

### AIResolver (interfaz)

```python
class AIResolver(ABC):
    def resolve(self, field_name: str, context: ParserContext,
                previous_result: ParseResult | None = None) -> ParseResult: ...
    def is_available(self) -> bool: ...
    def provider_name(self) -> str: ...
```

Diseñado para implementaciones con Z.ai, OpenRouter o HuggingFace. Se invoca solo cuando la confianza del parser determinista está por debajo del umbral.

### Tests

| Archivo | Tests | Temas |
|---|---|---|
| `tests/test_parser.py` | 45 | ParseResult (7), ParserContext (3), PanamaRemateParser (14), ColombiaRemateParser (6), Registry (6), Factory (5), AIResolver (3) |

### Casos cubiertos

| Test | Descripción |
|---|---|
| `test_extract_finca` | FINCA encontrada por regex |
| `test_extract_precio_base` | Precio base encontrado |
| `test_extract_expediente` | Expediente encontrado |
| `test_extract_demandante/demandado` | Partes encontradas |
| `test_field_not_found` | Campo ausente → NOT_FOUND |
| `test_evidence_added_on_found` | Evidencia correcta guardada |
| `test_low_confidence_partial_match` | Baja confianza manejada |
| `test_all_fields_extracted` | Todos los campos en un texto realista |
| `test_set_found/set_not_found/requires_review` | Transiciones de estado válidas |

### Resultados

**303 tests — 303 passed, 0 failed, 0 errors**

| Suite | Tests |
|---|---|
| FASE 2 (models) | 48 |
| FASE 3 (OCR) | 46 |
| FASE 4 (segmenter + continuity) | 74 + 24 |
| FASE 4.2 (assembly) | 27 |
| FASE 4.4 (stitching) | 12 |
| FASE 4.5 (newspaper layout) | 24 |
| FASE 5 (parser) | **45** |
| **Total** | **303** |

### Reglas respetadas

1. ✅ Sin LLM — todo determinista (regex + reglas)
2. ✅ Sin Claude, Gemini, ni IA generativa
3. ✅ `AIResolver` es interfaz abstracta — sin implementación concreta
4. ✅ Sin modificar pipeline V1
5. ✅ Sin modificar OCR, segmenter, database ni frontend
6. ✅ Cada campo tiene evidencia — nunca valores sin source

### Próximo paso

FASE 6 — Knowledge Engine (aprender de correcciones)
