from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from ..database import get_db
from ..models import Aviso, Aprobacion
from ..pipeline import audit
from ..upload.platform_uploader import subir_a_plataforma

router = APIRouter(prefix="/aprobaciones", tags=["aprobaciones"])


@router.post("/webhook")
def webhook_whatsapp(payload: dict, db: Session = Depends(get_db)):
    """
    El bridge de WhatsApp (Baileys) llama aquí cuando el cliente responde
    un mensaje. Se espera: {"mensaje": "SI 14"} o {"mensaje": "NO 14"}
    """
    texto = payload.get("mensaje", "").strip().upper()
    partes = texto.split()
    if len(partes) != 2 or partes[0] not in ("SI", "NO"):
        return {"status": "ignorado", "razon": "formato no reconocido, se esperaba 'SI <id>' o 'NO <id>'"}

    accion, aviso_id_str = partes
    try:
        aviso_id = int(aviso_id_str)
    except ValueError:
        return {"status": "ignorado", "razon": "id de aviso inválido"}

    return _resolver_aprobacion(db, aviso_id, aprobado=(accion == "SI"), origen="whatsapp")


@router.post("/{aviso_id}/manual")
def aprobar_manual(aviso_id: int, aprobado: bool, db: Session = Depends(get_db)):
    """Aprobación manual desde el dashboard, por si el cliente prefiere no usar WhatsApp."""
    return _resolver_aprobacion(db, aviso_id, aprobado, origen="dashboard_manual")


@router.post("/simular_todas")
def simular_aprobaciones(db: Session = Depends(get_db)):
    """Aprueba y sube automáticamente TODOS los avisos pendientes.
    Útil para testing y demostración -- simula lo que el cliente haría
    respondiendo 'SI' a cada aviso por WhatsApp."""
    avisos_pendientes = db.query(Aviso).filter(
        Aviso.estado.in_(["esperando_aprobacion", "auto_aprobado"])
    ).all()

    resultados = []
    for aviso in avisos_pendientes:
        resultado = _resolver_aprobacion(db, aviso.id, aprobado=True, origen="simulacion_masiva")
        resultados.append(resultado)

    return {
        "total": len(resultados),
        "aprobados": len([r for r in resultados if r["estado"] == "subido"]),
        "errores": len([r for r in resultados if r["estado"] == "error"]),
        "detalles": resultados,
    }


@router.post("/simular_una/{aviso_id}")
def simular_una_aprobacion(aviso_id: int, db: Session = Depends(get_db)):
    """Aprueba y sube UN aviso específico (simulación)."""
    return _resolver_aprobacion(db, aviso_id, aprobado=True, origen="simulacion_individual")


def _resolver_aprobacion(db: Session, aviso_id: int, aprobado: bool, origen: str):
    aviso = db.query(Aviso).get(aviso_id)
    if not aviso:
        raise HTTPException(404, "Aviso no encontrado")

    aprobacion = db.query(Aprobacion).filter(Aprobacion.aviso_id == aviso_id).order_by(
        Aprobacion.creado_en.desc()).first()
    if aprobacion:
        aprobacion.respuesta = "aprobado" if aprobado else "rechazado"
        aprobacion.respondido_en = datetime.utcnow()

    if aprobado:
        aviso.estado = "aprobado"
        db.commit()
        try:
            subir_a_plataforma(aviso)
            aviso.estado = "subido"
            db.commit()
            audit.registrar(db, "platform_upload", "subida_tras_aprobacion",
                             f"Aprobado vía {origen}", aviso_id=aviso.id)
        except Exception as e:
            aviso.estado = "error"
            db.commit()
            audit.registrar(db, "platform_upload", "error", str(e), aviso_id=aviso.id)
    else:
        aviso.estado = "rechazado"
        db.commit()
        audit.registrar(db, "whatsapp", "rechazado", f"Rechazado vía {origen}", aviso_id=aviso.id)

    return {"aviso_id": aviso.id, "estado": aviso.estado}
