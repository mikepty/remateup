# Auditoría de Causa Raíz — Avisos Duplicados y Mezclados en Producción (Panamá)

**Fecha:** 2026-08-02
**Alcance:** Caso real `doc103` vs `doc104` (misma página de periódico, dos documentos)
**Método:** Análisis de datos reales de producción (OCR + avisos extraídos), sin modificar código.

---

## 1. Resumen ejecutivo

**La misma página de periódico fue subida dos veces como dos documentos distintos,**
generando 22 avisos duplicados y 5 avisos incompletos/mezclados en la plataforma:

- **doc104** = subida correcta: superior (WA0016) + inferior (WA0012) como un solo
  documento → OCR de **177,921** caracteres = página COMPLETA → **22 avisos correctos**.
- **doc103** = subida de la imagen **inferior (WA0012) SOLA** como documento separado
  → OCR de **50,000** caracteres = solo la mitad inferior → **27 avisos, 22 duplicados
  y 5 rotos** (sin expediente, o con datos cruzados entre avisos vecinos).

No existe detección de duplicados entre documentos. La función diseñada para eso,
`evaluar_duplicado_o_republicacion()`, está **desactivada** (no-op).

---

## 2. Evidencia dura

### 2.1 Los dos documentos son la MISMA página

| Métrica | doc103 | doc104 |
|---|---|---|
| Imagen(es) | WA0012 (inferior sola) | WA0016 + WA0012 (superior + inferior) |
| Longitud OCR | 50,000 chars | 177,921 chars |
| Inicio del texto | `hasta su culminación... articulo 1646` (mitad de frase) | `6B` (encabezado de página) |
| Fin del texto | — | `a.v./1251947` (pie de página) |
| Avisos extraídos | 27 | 22 |

**Prueba de subconjunto:** de todas las palabras del OCR de doc103, **0** palabras
no aparecen en doc104. El 100% del contenido de doc103 está dentro de doc104.
Son la misma página física.

### 2.2 Avisos duplicados (mismo expediente + finca)

Los **22 avisos** de doc104 aparecen también en doc103 (100% de solapamiento por
expediente+finca). Ejemplos:

| expediente | finca | base doc104 | base doc103 |
|---|---|---|---|
| 86633-2025 | 433710 | 68,871.80 | **None** |
| 112235-24 | 30190614 | 45,700.00 | **None** |
| 43182-2024 | 478729 | 232,000.00 | **205,000.00** (¡valor distinto!) |
| 14605-24 | 49678 | 45,700.00 | **None** |
| 161722025 | 30356571 | 110,000.00 | 110,000.00 |
| 37468-23 | 364725 | 82,500.00 | 82,500.00 |

### 2.3 Avisos rotos en doc103 (solo en doc103, 5 sin expediente)

| finca | base | problema |
|---|---|---|
| 478729 | 232,000.00 | sin expediente |
| None | None | sin identidad |
| None | 45,700.00 | sin identidad |
| 30292475 | 50,000.00 | sin expediente |
| 1184 | 200,000.00 | sin expediente |

### 2.4 Avisos con datos MEZCLADOS (lo más grave)

En doc103 existe el aviso `exp=161722025 finca=433710 base=67000.0`, que **mezcla
datos de dos avisos distintos** de la página:

- `exp=161722025` real → `finca=30356571, base=110000.0` (aviso del mismo documento)
- `finca=433710` real → `exp=86633-2025, base=68871.8` (otro aviso de la misma página)

Es decir: el extractor tomó la finca de un aviso y el expediente/base de otro aviso
vecino. **Esto corrompe silenciosamente el dato** — el aviso es "creíble" pero falso.

---

## 3. Causa raíz

### 3.1 Cómo se llegó a 2 documentos

El endpoint `POST /documentos/subir` (`backend/app/routers/documents.py:17`) crea un
`Documento` por cada subida. Las imágenes en el mismo lote se tratan como mitades de
una página, pero **no hay correlación entre subidas distintas**:

1. El cliente subió [WA0016 + WA0012] → un documento (doc104), página completa, OK.
2. El cliente subió [WA0012] de nuevo → otro documento (doc103), solo mitad inferior.

Sin la mitad superior, cada aviso pierde su encabezado (expediente, finca, base),
que vive en la parte superior del texto → datos rotos y mezclados.

### 3.2 La deduplicación entre documentos está desactivada

`backend/app/pipeline/validation.py:48`:

```python
def evaluar_duplicado_o_republicacion(db, datos: dict) -> dict:
    """Simplificado - siempre retorna nuevo para evitar problemas con la BD."""
    return {"tipo": "nuevo"}
```

La deduplicación existente en `extraction.py` (`_es_mismo_aviso`, línea 539) solo
opera **dentro** de un documento (para fusionar las 2 lecturas del solape físico
superior/inferior). **No consulta la BD** para ver si el aviso ya fue creado por
otro documento. Por eso el mismo aviso (exp+finca) termina dos veces en el sistema.

### 3.3 Consecuencia

- 22 avisos duplicados (infla el conteo del panel).
- 5 avisos sin expediente (el filtro `descartado_sin_base` de `orchestrator.py:328`
  no los descarta porque sí tienen base; quedan con identidad incompleta).
- 1+ avisos con datos cruzados de avisos vecinos (el más grave, difícil de detectar).

---

## 4. Defectos adyacentes observados (no abordados aquí)

- `docs/KNOWN_ISSUES.md` ya documentaba que `evaluar_duplicado_o_republicacion`
  es no-op (issue #3, TECH_DEBT HIGH).
- En `ocr_vision.py`, el lienzo vertical detecta columnas sobre el conjunto completo
  de palabras (línea 276); si la detección falla en página de ancho completo, se
  puede entremezclar texto de columnas vecinas. No se observó corrupción en doc104
  (correcto), pero es el mecanismo por el cual un OCR parcial mezcla avisos.
- doc111 (LE 2c 8 julio 26) mostró OCR severamente intercalado entre columnas —
  candidato a otro root cause distinto, requiere análisis aparte.

---

## 5. Recomendación (para la fase de implementación)

1. **Reactivar** `evaluar_duplicado_o_republicacion` con lógica real: al extraer un
   aviso, buscar en `Aviso` existente por expediente+finca (misma semántica de
   `_es_mismo_aviso`); si existe con datos compatibles → `{"tipo": "duplicado"}` y no
   crear; si difiere en valores críticos → marcar para revisión humana (no reemplazo).
2. **Guardar referencia de origen** para comparación: al procesar un documento,
   verificar si su OCR es subconjunto de otro documento ya procesado (páginas de
   periódico repetidas) y marcarlo como duplicado de página.
3. **No tocar** la lógica dentro de `extraction.py` (funciona correctamente).
4. Esto es un cambio general y determinista, sin parches puntuales ni hardcode.

---

## 6. Anexo: datos verificados

- `doc104_debug.json` — texto_ocr 177,921 chars (22 avisos).
- `doc104_avisos.json` — 22 avisos con bases correctas.
- `doc103_debug.json` — texto_ocr 50,000 chars (27 avisos).
- `doc103_avisos_backup.json` — 27 avisos (22 duplicados, 5 rotos, 1+ mezclado).
- Imágenes fuente: `C:\Users\user\Pictures\rem PAperiod\IMG-20260710-WA0016.jpg` (sup)
  e `IMG-20260710-WA0012.jpg` (inf).
