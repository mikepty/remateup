import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import get_db
from ..models import Aviso, Documento, Auditoria, Aprobacion

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/pendientes")
def avisos_pendientes(db: Session = Depends(get_db)):
    avisos = db.query(Aviso).filter(Aviso.estado == "esperando_aprobacion").all()
    return [_serializar_aviso(a) for a in avisos]


@router.get("/historial")
def historial(limit: int = 50, db: Session = Depends(get_db)):
    avisos = db.query(Aviso).order_by(Aviso.creado_en.desc()).limit(limit).all()
    return [_serializar_aviso(a) for a in avisos]


@router.get("/auditoria")
def auditoria(limit: int = 100, db: Session = Depends(get_db)):
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
    confianza_promedio = db.query(func.avg(Aviso.confianza_promedio)).scalar() or 0

    return {
        "documentos_procesados": total_docs,
        "avisos_totales": total_avisos,
        "auto_aprobados": auto_aprobados,
        "esperando_aprobacion": esperando,
        "duplicados_sospechosos": duplicados,
        "republicaciones_legales": republicaciones,
        "confianza_promedio_global": round(confianza_promedio, 3),
        "porcentaje_automatizacion": round((auto_aprobados / total_avisos * 100), 1) if total_avisos else 0,
    }


def _serializar_aviso(a: Aviso) -> dict:
    return {
        "id": a.id, "codigo": a.codigo, "estado": a.estado, "pais": a.pais,
        "expediente": a.expediente,
        "demandante": a.demandante, "demandado": a.demandado,
        "fecha": a.fecha, "hora": a.hora,
        "lugar": a.lugar, "proceso": a.proceso,
        "descripcion": a.descripcion,
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
    }
