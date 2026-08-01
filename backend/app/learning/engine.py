"""Hyper Learning / Intelligence / Prediction engines (FASE 14).

UNIFY (Parte 1) y amplía las señales que el sistema YA recolecta (V1
`correcciones`, `avisos`, `documentos`, `auditoria`) en un motor que:

  * Genera SUGERENCIAS (Parte 1 / Parte 4 / Parte 5).
  * Analiza un documento/aviso punto por punto (Parte 2).
  * Produce un diagnóstico global reproducible (Parte 10 / Parte 11).
  * Genera los reportes requeridos (Parte 12).

RESTRICCIONES FASE 14 respetadas:
  - NO crea arquitectura nueva: reusa los modelos V1 (`Aviso`, `Documento`,
    `Auditoria`, `Correccion`) y los módulos de evaluación V2 existentes.
  - NUNCA modifica Knowledge, el Parser ni el Validator automáticamente:
    solo emite sugerencias. La aplicación es explícita y auditable (ver
    `admin aplicar_sugerencia`).
  - TODO es serializable / determinista / reproducible: las funciones puras
    reciben dataclasses/dicts y devuelven dicts JSON-serializables; el
    acceso a la BD se aísla en `admin.py` para que los motores sean unit-testables.
  - Panamá es prioridad (Parte 14): las sugerencias y la inteligencia se
    priorizan sobre pais=1; Colombia no se rompe.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from ..config import (
    CAMPOS_FUNDAMENTALES,
    PORCENTAJES_FIANZA_VALIDOS_PA,
    PORCENTAJES_MINIMO_VALIDOS_PA,
    PORCENTAJES_FIANZA_VALIDOS_CO,
    PORCENTAJES_MINIMO_VALIDOS_CO,
)

# Campos que el motor de sugerencias considera "normalizables" (alias / formato).
# No se sugiere normalizar ids, montos calculados ni estado.
_CAMPOS_SUG_UI = {
    "expediente", "lugar", "proceso", "demandante", "demandado", "categoria",
    "provincia", "finca_matr", "lote_casa", "plano", "superficie", "fecha",
    "hora", "codigo", "codigo_prensa", "pagina_prensa",
    "descripcion", "descripcion_completa", "prevista",
}

# Vocabulario conocido: si un valor nuevo NO pertenece aquí, se sugiere
# revisar (etiqueta_nueva). Se extiende con normalización de provincias.
_PROVINCIAS_PA = {
    "BOCAS DEL TORO", "COCLE", "COLON", "CHIRIQUI", "DARIEN", "HERRERA",
    "LOS SANTOS", "PANAMA", "PANAMA OESTE", "VERAGUAS",
}
_DEPARTAMENTOS_CO = {
    "ANTIOQUIA", "AMAZONAS", "ARAUCA", "ATLANTICO", "BOGOTA", "BOGOTA D.C",
    "BOGOTA DC", "BOLIVAR", "BOYACA", "CALDAS", "CAQUETA", "CASANARE",
    "CAUCA", "CESAR", "CHOCO", "CORDOBA", "CUNDINAMARCA", "GUAINIA",
    "GUAVIARE", "HUILA", "LA GUAJA", "MAGDALENA", "META", "NARIÑO",
    "NORTE DE SANTANDER", "PUTUMAYO", "QUINDIO", "RISARALDA",
    "SAN ANDRES Y PROVIDENCIA", "SANTANDER", "SUCRE", "TOLIMA",
    "VALLE DEL CAUCA", "VAUPES", "VICHADA",
}
_CATEGORIAS = {"CASA", "APARTAMENTO", "TERRENO", "VEHICULO", "MISCELANEO"}


def _norm(v: Any) -> str:
    """Normalización canónica para comparar tokens: mayúsculas, sin acentos,
    sin puntuación/espacios. Sirve para detectar alias (JDO ≈ JUZGADO no)."""
    if v is None:
        return ""
    s = str(v).strip().upper()
    s = s.replace("Ñ", "N")
    s = re.sub(r"[ÁÉÍÓÚÜ]", lambda m: "AEIOU"["ÁÉÍÓÚÜ".index(m.group())], s)
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s


def _contar_por_campo(correcciones: list[dict]) -> dict[str, Counter]:
    """Agrupa correcciones por (campo) → Counter de ocurrencias de cada valor_nuevo."""
    out: dict[str, Counter] = defaultdict(Counter)
    for c in correcciones:
        campo = c.get("campo")
        if campo in _CAMPOS_SUG_UI:
            out[campo][_norm(c.get("valor_nuevo") or "")] += 1
    return out


def generar_sugerencias(correcciones: list[dict], top_n: int = 50) -> list[dict]:
    """Parte 1/4: motor de SUGERENCIAS basado en correcciones repetidas.

    Lee `correcciones` (list[dict] con: campo, valor_anterior, valor_nuevo, pais,
    contexto, codigo_prensa, era_vacio, creado_en) y genera sugerencias del tipo:

      - `correccion_repetida` : un mismo (campo, old→new) aparece >1 vez → proponer
        normalizar futuras ocurrencias iguales.
      - `alias`               : mismo token normalizado, forma escrita distinta
        (ej. "PANAMA"/"Panamá") → unificar.
      - `etiqueta_nueva`      : valor nuevo fuera del vocabulario oficial → revisar.
      - `campo_vacio_frecuente`: un campo queda vacío con mucha frecuencia → reforzar OCR.

    NUNCA aplica nada: devuelve sugerencias serializables con confianza [0,1].
    """
    if not correcciones:
        return []

    # 1) correccion_repetida: (campo, pais, old_norm, new) repetido
    pares = Counter()
    pares_meta: dict[tuple, dict] = {}
    por_campo_nuevo = defaultdict(Counter)
    vacios_por_campo = Counter()

    for c in correcciones:
        campo = c.get("campo")
        if campo not in _CAMPOS_SUG_UI:
            continue
        pais = c.get("pais")
        new = c.get("valor_nuevo") or ""
        old = c.get("valor_anterior") or ""
        new_norm = _norm(new)
        old_norm = _norm(old)
        por_campo_nuevo[campo][new_norm] += 1
        if c.get("era_vacio"):
            vacios_por_campo[campo] += 1
        clave = (campo, pais, old_norm, _norm(new))
        pares[clave] += 1
        meta = pares_meta.setdefault(clave, {
            "campo": campo, "pais": pais,
            "valor_anterior": old, "valor_nuevo": new,
            "codigo_prensa": c.get("codigo_prensa"),
            "ultima": c.get("creado_en") or "",
        })
        if (c.get("creado_en") or "") > (meta["ultima"] or ""):
            meta["ultima"] = c.get("creado_en") or ""

    sugs: list[dict] = []
    total = len(correcciones)

    for (campo, pais, old_n, new_n), n in pares.items():
        if n < 2:
            continue  # solo sugerencias con >=2 repeticiones (Historical Memory)
        meta = pares_meta[(campo, pais, old_n, new_n)]
        sugs.append({
            "tipo": "correccion_repetida",
            "campo": campo, "pais": pais,
            "valor_sugerido": meta["valor_nuevo"],
            "valor_referencia": meta["valor_anterior"],
            "count": n, "confianza": min(0.99, 0.5 + n / max(total, 1) * 5),
            "ultima": meta["ultima"], "codigo_prensa_ref": meta["codigo_prensa"],
        })

    # 2) alias: mismo token normalizado, formas distintas (ej. "PANAMA"/"Panamá")
    # Detectar pares de valor_nuevo distintos que normalizan igual (colisión).
    por_norma: dict[tuple, dict] = {}
    for c in correcciones:
        campo = c.get("campo")
        if campo not in _CAMPOS_SUG_UI:
            continue
        new = c.get("valor_nuevo") or ""
        nkey = _norm(new)
        if not nkey:
            continue
        slot = por_norma.setdefault((campo, c.get("pais"), nkey), {"formas": set(), "count": 0, "ultima": ""})
        slot["formas"].add(new.strip())
        slot["count"] += 1
        if (c.get("creado_en") or "") > (slot["ultima"] or ""):
            slot["ultima"] = c.get("creado_en") or ""
    for (campo, pais, nkey), slot in por_norma.items():
        if len(slot["formas"]) >= 2 and slot["count"] >= 2:
            formas = sorted(slot["formas"], key=len)
            sugs.append({
                "tipo": "alias",
                "campo": campo, "pais": pais,
                "valor_sugerido": formas[0],  # forma más corta/canonica
                "valor_referencia": None,
                "count": slot["count"], "confianza": min(0.95, 0.6 + slot["count"] / max(total, 1)),
                "alternativas": formas, "ultima": slot["ultima"],
            })

    # 3) etiqueta_nueva: categoría / provincia fuera del vocabulario oficial
    nuevas = set()
    for c in correcciones:
        campo = c.get("campo")
        val = (c.get("valor_nuevo") or "").strip()
        if not val:
            continue
        if campo == "categoria" and val.upper() not in _CATEGORIAS:
            nuevas.add(("categoria", c.get("pais"), val))
        if campo == "provincia":
            up = val.upper()
            if c.get("pais") == 1 and _norm(up) not in {_norm(p) for p in _PROVINCIAS_PA}:
                nuevas.add(("provincia", 1, val))
            if c.get("pais") == 2 and _norm(up) not in {_norm(d) for d in _DEPARTAMENTOS_CO}:
                nuevas.add(("provincia", 2, val))
    for campo, pais, val in sorted(nuevas, key=lambda x: x[2]):
        sugs.append({
            "tipo": "etiqueta_nueva", "campo": campo, "pais": pais,
            "valor_sugerido": val, "valor_referencia": None,
            "count": 1, "confianza": 0.5, "ultima": "",
            "detalle": "Valor fuera del vocabulario oficial del cliente; revisar antes de aplicar.",
        })

    # 4) campo_vacio_frecuente
    for campo, n in vacios_por_campo.most_common(8):
        if n >= 2:
            sugs.append({
                "tipo": "campo_vacio_frecuente", "campo": campo, "pais": None,
                "valor_sugerido": None, "count": n,
                "confianza": min(0.9, 0.4 + n / max(total, 1)),
                "ultima": "",
                "detalle": f"El {n}% de las correcciones llenaron '{campo}' desde vacío; reforzar captura OCR.",
            })

    # Prioridad PA (Parte 14): pais=1 primero, luego por confianza
    def _peso(s: dict):
        pais = s.get("pais")
        base = 0 if pais == 1 else 0.0005
        return (base, -s["confianza"])
    sugs.sort(key=_peso)
    # dedup por (tipo, campo, pais, valor_sugerido)
    vistos = {}
    res = []
    for s in sugs:
        k = (s["tipo"], s["campo"], s.get("pais"), s.get("valor_sugerido"))
        if k in vistos:
            continue
        vistos[k] = True
        res.append(s)
        if len(res) >= top_n:
            break
    return res


def inteligencia_aviso(aviso: dict, auditoria: list[dict] | None = None,
                        correcciones_aviso: list[dict] | None = None) -> dict:
    """Parte 2: análisis inteligente de UN aviso.

    `aviso` es el dict serializado del modelo (ver `_serializar_aviso_admin`).
    Devuelve un informe serializable y determinista:

      - motivo_fallo: por qué puede haber quedado en esperando_aprobacion.
      - campos_faltantes: campos fundamentales vacíos.
      - recuperacion: qué motor extrajo cada campo (IA / deterministico / desconocido).
      - sugerencias: sugerencias previamente generadas que aplican a este aviso.
      - confianza_predicha: [0,1].
    """
    auditoria = auditoria or []
    correcciones_aviso = correcciones_aviso or []

    # Campos fundamentales vacíos (None / "" / "None"). fianza/minimo vienen como
    # porcentaje cuando se leen; si quedan vacíos el motivo lo detalla.
    campos_faltantes = [c for c in CAMPOS_FUNDAMENTALES
                        if aviso.get(c) in (None, "", "None")]
    motivo = []
    if aviso.get("discrepancia_valores"):
        motivo.append("discrepancia_valores")
    if aviso.get("confianza_promedio") is not None and aviso["confianza_promedio"] < 0.70:
        motivo.append("confianza_baja")
    if not aviso.get("base"):
        motivo.append("base_faltante")
    if aviso.get("fianza") in (None, "", "None") and not aviso.get("fianza_porcentaje"):
        motivo.append("fianza_indeterminada")
    if aviso.get("minimo") in (None, "", "None") and not aviso.get("minimo_porcentaje"):
        motivo.append("minimo_indeterminado")
    if aviso.get("estado") == "esperando_aprobacion" and not motivo:
        motivo.append("pendiente_revision_cliente")
    # Discrepancia puntual sobre los porcentajes leídos
    if aviso.get("fianza_porcentaje") is not None:
        validos = (PORCENTAJES_FIANZA_VALIDOS_PA if (aviso.get("pais") == 1)
                   else PORCENTAJES_FIANZA_VALIDOS_CO)
        try:
            if min(abs(float(aviso["fianza_porcentaje"]) - v) for v in validos) > 1.0:
                motivo.append("fianza_pct_no_legal")
        except (ValueError, TypeError):
            pass

    # Recuperación: ¿qué motor produjo esto?
    fuente = aviso.get("codigo_fuente") or ""
    if fuente.startswith("det-"):
        motor = "deterministico"
    elif fuente.startswith("ai-") or fuente.startswith("claude") or fuente.startswith("gemini"):
        motor = "ia"
    else:
        motor = "desconocido"
    # eventos de auditoría que tocaron este aviso
    agentes = Counter(r.get("agente") for r in auditoria if r.get("agente"))
    recuperacion = {"motor_principal": motor, "codigo_fuente": fuente,
                    "agentes_auditados": dict(agentes)}
    if "extraction" in agentes or motor == "ia":
        recuperacion["recuperado_por"] = "ia"
    if "business_rules" in agentes:
        recuperacion["monto_computado"] = True

    # Sugerencias aplicables a este aviso (por campo vacío o valor repetido)
    sugs = []
    for c in correcciones_aviso:
        campo = c.get("campo")
        if not aviso.get(campo):
            sugs.append({"campo": campo, "valor_sugerido": c.get("valor_nuevo"),
                         "confianza": min(0.9, 0.4 + c.get("count", 1) / 5)})
    # dedup
    vistos = set(); out_s = []
    for s in sorted(sugs, key=lambda x: -x["confianza"]):
        if s["campo"] in vistos:
            continue
        vistos.add(s["campo"]); out_s.append(s)

    # confianza predicha: pondera promedio real + ausencia de discrepancia + cobertura de campos
    conf_real = aviso.get("confianza_promedio") or 0.0
    cobertura = sum(1 for c in CAMPOS_FUNDAMENTALES if aviso.get(c)) / len(CAMPOS_FUNDAMENTALES)
    conf_pred = round(0.7 * float(conf_real) + 0.3 * cobertura
                      - (0.25 if aviso.get("discrepancia_valores") else 0)
                      - (0.15 if aviso.get("estado") == "esperando_aprobacion" else 0), 3)
    conf_pred = max(0.0, min(1.0, conf_pred))

    return {
        "aviso_id": aviso.get("id"),
        "expediente": aviso.get("expediente"),
        "motivo_fallo": motivo,
        "campos_faltantes": campos_faltantes,
        "recuperacion": recuperacion,
        "sugerencias": out_s,
        "confianza_predicha": conf_pred,
    }


def predecir(correcciones: list[dict], avisos: list[dict] | None = None) -> dict:
    """Parte 5: predicción global de dónde fallará la extracción.

    - campos_mas_problematicos (top).
    - ocr_conflictos (un mismo campo corregido a valores distintos = ambigüedad OCR).
    - campos_incompletos (más correcciones con era_vacio).
    - posibles_duplicados (avisos con mismo expediente+finca).
    """
    avisos = avisos or []
    por_campo = Counter()
    vacios = Counter()
    conflictos: dict[str, set] = defaultdict(set)
    for c in correcciones:
        campo = c.get("campo")
        if campo not in _CAMPOS_SUG_UI:
            continue
        por_campo[campo] += 1
        conflictos[campo].add(_norm(c.get("valor_nuevo") or ""))
        if c.get("era_vacio"):
            vacios[campo] += 1

    ocr_conflictos = [{"campo": c, "variantes": len(v)} for c, v in conflictos.items() if len(v) > 1]
    campos_mas_problematicos = [
        {"campo": c, "veces": n, "vacios": vacios.get(c, 0)}
        for c, n in por_campo.most_common(10)
    ]

    # posibles duplicados por expediente + finca_matr
    claves: dict[str, list] = defaultdict(list)
    for a in avisos:
        k = f"{a.get('expediente') or ''}|{a.get('finca_matr') or ''}"
        if k.strip("|") and len(k.strip("|")) > 2:
            claves[k].append(a.get("id"))
    duplicados = [{"clave": k, "ids": v} for k, v in claves.items() if len(v) > 1]

    total_corr = len(correcciones)
    return {
        "total_correcciones": total_corr,
        "campos_mas_problematicos": campos_mas_problematicos,
        "ocr_conflictos": ocr_conflictos,
        "campos_incompletos": [{"campo": c, "vacios": n} for c, n in vacios.most_common(10)],
        "posibles_duplicados": duplicados[:20],
        "prediccion_resumen": (
            "Reforzar OCR en: " + ", ".join(c["campo"] for c in campos_mas_problematicos[:3])
            if campos_mas_problematicos else "Sin datos de correcciones aún."
        ),
    }
