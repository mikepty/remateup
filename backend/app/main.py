from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import Base, engine
from .routers import documents, dashboard, approvals, exports

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="RemateUp API",
    description="Agente autónomo de captura, validación y carga de avisos de remate.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ajustar a la URL real del frontend en producción
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
