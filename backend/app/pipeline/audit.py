from sqlalchemy.orm import Session
from ..models import Auditoria


def registrar(db: Session, agente: str, accion: str, detalle: str,
              aviso_id: int = None, documento_id: int = None):
    entrada = Auditoria(
        agente=agente, accion=accion, detalle=detalle,
        aviso_id=aviso_id, documento_id=documento_id,
    )
    db.add(entrada)
    db.commit()
    return entrada
