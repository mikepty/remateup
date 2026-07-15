from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
from .database import Base, engine, get_db
from .routers import documents, dashboard, approvals, exports
from .models import Aviso, Documento, Auditoria, Aprobacion

Base.metadata.create_all(bind=engine)

# --- Migracion ligera: agregar columnas nuevas si no existen ---
def _migrar_columnas():
    """Agrega columnas nuevas al schema existente sin perder datos."""
    nuevas_columnas = {
        "avisos": [
            ("codigo_prensa", "VARCHAR"),
            ("email_observaciones", "VARCHAR"),
            ("descripcion_completa", "TEXT"),
            ("prevista", "TEXT"),
        ]
    }
    insp = inspect(engine)
    with engine.connect() as conn:
        for tabla, columnas in nuevas_columnas.items():
            existentes = {c["name"] for c in insp.get_columns(tabla)}
            for col_name, col_type in columnas:
                if col_name not in existentes:
                    conn.execute(text(f'ALTER TABLE {tabla} ADD COLUMN {col_name} {col_type}'))
                    conn.commit()

try:
    _migrar_columnas()
except Exception as e:
    print(f"[migration] Advertencia al migrar columnas: {e}")

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


@app.put("/admin/editar_aviso/{aviso_id}")
def editar_aviso(aviso_id: int, campos: dict, db: Session = Depends(get_db)):
    """Edita campos especificos de un aviso y guarda correcciones para aprendizaje."""
    aviso = db.query(Aviso).get(aviso_id)
    if not aviso:
        return {"error": "Aviso no encontrado"}

    campos_permitidos = [
        "codigo", "expediente", "lugar", "proceso", "demandante", "demandado",
        "descripcion", "descripcion_completa", "fecha", "hora", "base",
        "fianza_porcentaje", "minimo_porcentaje",
        "fianza", "minimo", "categoria", "categoria_codigo", "provincia",
        "codigo_ubicacion", "finca_matr", "lote_casa", "plano", "superficie", "estado",
        "codigo_prensa", "email_observaciones", "codigo_fuente", "prevista"
    ]

    for campo, valor in campos.items():
        if campo in campos_permitidos and hasattr(aviso, campo):
            valor_anterior = getattr(aviso, campo)
            if str(valor_anterior) != str(valor):
                # Guardar correccion para aprendizaje
                correccion = Correccion(
                    aviso_id=aviso_id,
                    campo=campo,
                    valor_anterior=str(valor_anterior),
                    valor_nuevo=str(valor),
                    pais=aviso.pais,
                )
                db.add(correccion)
            setattr(aviso, campo, valor)

    db.commit()
    db.refresh(aviso)
    return {"message": "Aviso actualizado", "aviso_id": aviso.id}
