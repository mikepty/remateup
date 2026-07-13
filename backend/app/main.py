from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .routers import documents, dashboard, approvals, exports
from .models import Aviso, Documento, Auditoria, Aprobacion

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="RemateUp API",
    description="Agente autónomo de captura, validación y carga de avisos de remate.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(dashboard.router)
app.include_router(approvals.router)
app.include_router(exports.router)


@app.get("/")
def salud():
    return {"status": "ok", "servicio": "RemateUp API"}


@app.post("/admin/limpiar_bd")
def limpiar_base_datos(db: Session = Depends(get_db)):
    """Borra TODOS los avisos y documentos. Usar con cuidado."""
    db.query(Aprobacion).delete()
    db.query(Auditoria).delete()
    db.query(Aviso).delete()
    db.query(Documento).delete()
    db.commit()
    return {"message": "Base de datos limpiada correctamente", "status": "ok"}
