import json
from datetime import datetime, date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from ..database import get_db
from ..models import Aviso, Documento, Auditoria, Aprobacion, Correccion

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/aprendizaje")
def estadisticas_aprendizaje(db: Session = Depends(get_db)):
    """Muestra lo que el robot ha aprendido de las correcciones del cliente."""
    total = db.query(func.count(Correccion.id)).scalar() or 0
    pa = db.query(func.count(Correccion.id)).filter(Correccion.pais == 1).scalar() or 0
    co = db.query(func.count(Correccion.id)).filter(Correccion.pais == 2).scalar() or 0

    # Campos más corregidos
    por_campo = (db.query(Correccion.campo, func.count(Correccion.id).label("n"))
                 .group_by(Correccion.campo)
                 .order_by(func.count(Correccion.id).desc())
                 .limit(15).all())

    return {
        "total_correcciones": total,
        "panama": pa,
        "colombia": co,
        "campos_mas_corregidos": [{"campo": c, "veces": n} for c, n in por_campo],
    }


@router.get("/pendientes")
def avisos_pendientes(
    pais: int = Query(None, description="1=PA, 2=CO"),
    db: Session = Depends(get_db)
):
    query = db.query(Aviso).filter(Aviso.estado == "esperando_aprobacion")
    if pais:
        query = query.filter(Aviso.pais == pais)
    avisos = query.order_by(Aviso.creado_en.desc()).all()
    return [_serializar_aviso(a) for a in avisos]


@router.get("/avisos")
def listar_avisos(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    pais: int = Query(None, description="1=PA, 2=CO"),
    estado: str = Query(None, description="subido, esperando_aprobacion, auto_aprobado, reemplazado_por_republicacion"),
    fecha_desde: str = Query(None, description="YYYY-MM-DD"),
    fecha_hasta: str = Query(None, description="YYYY-MM-DD"),
    q: str = Query(None, description="buscar en descripcion, expediente, demandante, demandado"),
    db: Session = Depends(get_db)
):
    """Endpoint principal con filtros independientes y paginacion."""
    query = db.query(Aviso)

    # Filtros independientes
    if pais:
        query = query.filter(Aviso.pais == pais)
    if estado:
        query = query.filter(Aviso.estado == estado)
    if fecha_desde:
        try:
            fd = datetime.strptime(fecha_desde, "%Y-%m-%d").date()
            query = query.filter(Aviso.creado_en >= fd)
        except ValueError:
            pass
    if fecha_hasta:
        try:
            fh = datetime.strptime(fecha_hasta, "%Y-%m-%d").date()
            query = query.filter(Aviso.creado_en <= fh)
        except ValueError:
            pass
    if q:
        q_pattern = f"%{q}%"
        query = query.filter(
            (Aviso.descripcion.ilike(q_pattern)) |
            (Aviso.expediente.ilike(q_pattern)) |
            (Aviso.demandante.ilike(q_pattern)) |
            (Aviso.demandado.ilike(q_pattern)) |
            (Aviso.codigo.ilike(q_pattern))
        )

    total = query.count()
    avisos = query.order_by(Aviso.creado_en.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [_serializar_aviso(a) for a in avisos],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/historial")
def historial(
    limit: int = 200,
    pais: int = Query(None, description="1=PA, 2=CO"),
    estado: str = Query(None, description="subido, auto_aprobado, etc."),
    db: Session = Depends(get_db)
):
    query = db.query(Aviso)
    if pais:
        query = query.filter(Aviso.pais == pais)
    if estado:
        query = query.filter(Aviso.estado == estado)
    avisos = query.order_by(Aviso.creado_en.desc()).limit(limit).all()
    return [_serializar_aviso(a) for a in avisos]


@router.get("/todos")
def todos_avisos(
    pais: int = Query(None, description="1=PA, 2=CO"),
    estado: str = Query(None, description="subido, auto_aprobado, etc."),
    db: Session = Depends(get_db)
):
    """Devuelve TODOS los avisos sin limite."""
    query = db.query(Aviso)
    if pais:
        query = query.filter(Aviso.pais == pais)
    if estado:
        query = query.filter(Aviso.estado == estado)
    avisos = query.order_by(Aviso.creado_en.desc()).all()
    return [_serializar_aviso(a) for a in avisos]


@router.get("/auditoria")
def auditoria(limit: int = 200, db: Session = Depends(get_db)):
    registros = db.query(Auditoria).order_by(Auditoria.creado_en.desc()).limit(limit).all()
    return [{
        "id": r.id, "agente": r.agente, "accion": r.accion, "detalle": r.detalle,
        "aviso_id": r.aviso_id, "documento_id": r.documento_id, "creado_en": r.creado_en,
    } for r in registros]


@router.get("/metricas")
def metricas(db: Session = Depends(get_db)):
    total_docs = db.query(func.count(Documento.id)).scalar()
    total_avisos = db.query(func.count(Aviso.id)).scalar()
    auto_aprobados = db.query(func.count(Aviso.id)).filter(Aviso.estado.in_(["auto_aprobado", "subido"])).scalar()
    esperando = db.query(func.count(Aviso.id)).filter(Aviso.estado == "esperando_aprobacion").scalar()
    duplicados = db.query(func.count(Aviso.id)).filter(
        Aviso.tipo_validacion == "duplicado_sospechoso").scalar()
    republicaciones = db.query(func.count(Aviso.id)).filter(
        Aviso.tipo_validacion == "republicacion_legal").scalar()
    reemplazados = db.query(func.count(Aviso.id)).filter(
        Aviso.estado == "reemplazado_por_republicacion").scalar()
    confianza_promedio = db.query(func.avg(Aviso.confianza_promedio)).scalar() or 0

    pa = db.query(func.count(Aviso.id)).filter(Aviso.pais == 1).scalar()
    co = db.query(func.count(Aviso.id)).filter(Aviso.pais == 2).scalar()

    return {
        "documentos_procesados": total_docs,
        "avisos_totales": total_avisos,
        "auto_aprobados": auto_aprobados,
        "esperando_aprobacion": esperando,
        "duplicados_sospechosos": duplicados,
        "republicaciones_legales": republicaciones,
        "reemplazados": reemplazados,
        "confianza_promedio_global": round(confianza_promedio, 3),
        "porcentaje_automatizacion": round((auto_aprobados / total_avisos * 100), 1) if total_avisos else 0,
        "panama": pa,
        "colombia": co,
    }


def _serializar_aviso(a: Aviso) -> dict:
    return {
        "id": a.id, "codigo": a.codigo, "estado": a.estado, "pais": a.pais,
        "expediente": a.expediente,
        "demandante": a.demandante, "demandado": a.demandado,
        "fecha": a.fecha, "hora": a.hora,
        "lugar": a.lugar, "proceso": a.proceso,
        "descripcion": a.descripcion,
        "descripcion_completa": a.descripcion_completa,
        "prevista": a.prevista,
        "finca_matr": a.finca_matr,
        "lote_casa": a.lote_casa, "plano": a.plano, "superficie": a.superficie,
        "categoria": a.categoria, "categoria_codigo": a.categoria_codigo,
        "provincia": a.provincia, "codigo_ubicacion": a.codigo_ubicacion,
        "base": a.base, "fianza_porcentaje": a.fianza_porcentaje, "fianza": a.fianza,
        "fianza_asumida_por_regla": a.fianza_asumida_por_regla,
        "minimo_porcentaje": a.minimo_porcentaje, "minimo": a.minimo,
        "discrepancia_valores": a.discrepancia_valores,
        "campos_faltantes": json.loads(a.campos_faltantes_json) if a.campos_faltantes_json else [],
        "confianza_promedio": a.confianza_promedio,
        "tipo_validacion": a.tipo_validacion, "creado_en": a.creado_en,
        "codigo_prensa": a.codigo_prensa,
        "email_observaciones": a.email_observaciones,
        "codigo_fuente": a.codigo_fuente,
        "codigo_ubicacion_prensa": a.codigo_ubicacion_prensa,
        "periodico": a.periodico,
        "fecha_prensa": a.fecha_prensa,
        "pagina_prensa": a.pagina_prensa,
    }
