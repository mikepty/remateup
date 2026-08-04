"""
Sistema de aprendizaje: almacena y aplica correcciones del cliente.

Cuando el cliente edita un aviso (corrige un campo o llena uno vacío),
se guarda una Corrección en la tabla `correcciones`. Cuando se procesa
un aviso nuevo, se busca en correcciones anteriores un "patrón" de
corrección aplicable al texto del aviso nuevo y se aplica automáticamente.

Flujo:
  1. Cliente edita aviso → guardar_correccion()
  2. Pipeline procesa aviso nuevo → aplicar_aprendizaje()
  3. Si un patrón coincide, se rellena el campo vacío/corregido automáticamente
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from sqlalchemy.orm import Session


def guardar_correccion(
    db: Session,
    aviso_id: int,
    campo: str,
    valor_anterior: str,
    valor_nuevo: str,
    pais: int,
    contexto: str = "",
    codigo_prensa: str = "",
) -> None:
    """Guarda una corrección del cliente para aprendizaje futuro.

    Llamado desde el endpoint editar_aviso() en main.py cuando el cliente
    corrige un campo o llena uno que estaba vacío."""
    from ...models import Correccion
    era_vacio = not valor_anterior or valor_anterior.strip() == ""
    db.add(Correccion(
        aviso_id=aviso_id,
        campo=campo,
        valor_anterior=valor_anterior or "",
        valor_nuevo=valor_nuevo or "",
        pais=pais,
        contexto=contexto[:4000] if contexto else "",
        codigo_prensa=codigo_prensa or "",
        era_vacio=era_vacio,
    ))
    db.commit()


def _extraer_keywords(texto: str, min_len: int = 4) -> set[str]:
    """Extrae palabras significativas de un texto para matching de patrones."""
    palabras = re.findall(r"[A-ZÁÉÍÓÚÑa-záéíóúñ]{%d,}" % min_len, texto.upper())
    return set(palabras)


def _calcular_similitud(kw_texto: set[str], keywords_contexto: set[str]) -> float:
    """Calcula similitud Jaccard entre keywords del texto y keywords de contexto."""
    if not keywords_contexto or not kw_texto:
        return 0.0
    interseccion = kw_texto & keywords_contexto
    union = kw_texto | keywords_contexto
    return len(interseccion) / len(union) if union else 0.0


def aplicar_aprendizaje(
    db: Session,
    aviso_texto: str,
    pais: int,
    campos_existentes: dict[str, str | None],
    umbral_similitud: float = 0.15,
    max_correcciones: int = 5,
) -> dict[str, str | None]:
    """Busca correcciones anteriores aplicables al aviso actual y las aplica.

    Para cada campo que esté vacío o con valor bajo confianza, busca en la
    tabla `correcciones` si hay un patrón de contexto similar. Si lo encuentra,
    aplica el valor_nuevo de la corrección más reciente y más frecuente.

    Args:
        aviso_texto: texto completo del aviso nuevo
        pais: 1=PA, 2=CO
        campos_existentes: dict campo→valor ya extraído por el parser
        umbral_similitud: similitud mínima Jaccard (0-1) para considerar match
        max_correcciones: máximo de correcciones a aplicar por aviso

    Returns:
        dict campo→valor_corregido (solo campos que cambiaron)
    """
    from ...models import Correccion

    if not aviso_texto or len(aviso_texto.strip()) < 30:
        return {}

    kw_texto = _extraer_keywords(aviso_texto[:3000])
    if not kw_texto:
        return {}

    correcciones_raw = (
        db.query(Correccion)
        .filter(Correccion.pais == pais)
        .order_by(Correccion.creado_en.desc())
        .limit(500)
        .all()
    )
    if not correcciones_raw:
        return {}

    # Agrupar correcciones por campo: solo las que eran vacías (el cliente llenó)
    campos_vacios = [c for c in campos_existentes if not campos_existentes.get(c)]

    aplicadas = {}
    for campo in campos_vacios:
        if len(aplicadas) >= max_correcciones:
            break

        candidatas = [
            c for c in correcciones_raw
            if c.campo == campo and c.valor_nuevo and c.valor_nuevo.strip()
        ]
        if not candidatas:
            continue

        # Buscar la corrección con mejor similitud de contexto
        mejor = None
        mejor_sim = 0.0
        for c in candidatas:
            if not c.contexto:
                continue
            kw_ctx = _extraer_keywords(c.contexto[:2000])
            sim = _calcular_similitud(kw_texto, kw_ctx)
            if sim > mejor_sim and sim >= umbral_similitud:
                mejor_sim = sim
                mejor = c

        if mejor:
            aplicadas[campo] = mejor.valor_nuevo
            print(f"[learning] Campo '{campo}' aplicado de corrección #{mejor.id} "
                  f"(sim={mejor_sim:.2f}): {mejor.valor_nuevo[:50]}")

    return aplicadas


def resumen_aprendizaje(db: Session, pais: Optional[int] = None) -> dict:
    """Devuelve un resumen del estado de aprendizaje del sistema."""
    from ...models import Correccion
    from sqlalchemy import func

    q = db.query(Correccion)
    if pais:
        q = q.filter(Correccion.pais == pais)

    total = q.count()
    por_campo = dict(
        q.group_by(Correccion.campo)
        .with_entities(Correccion.campo, func.count(Correccion.id))
        .all()
    )
    vacios_llenados = q.filter(Correccion.era_vacio == True).count()

    return {
        "total_correcciones": total,
        "por_campo": por_campo,
        "campos_vacios_llenados": vacios_llenados,
        "campos_mas_corregidos": sorted(por_campo.items(), key=lambda x: -x[1])[:5],
    }
