import shutil
import json
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Documento
from ..pipeline.orchestrator import procesar_documento
from ..config import BASE_DIR

router = APIRouter(prefix="/documentos", tags=["documentos"])
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/subir")
async def subir_documento(
    background_tasks: BackgroundTasks,
    archivos: list[UploadFile] = File(..., description="Uno o más archivos. Si son 2+ imágenes, "
                                       "se tratan como partes verticales de la MISMA página (ej. mitad "
                                       "superior + mitad inferior de una columna larga de periódico), "
                                       "en el orden en que se suben."),
    pais: str = Form(...),
    db: Session = Depends(get_db),
):
    if pais not in ("PA", "CO"):
        raise HTTPException(400, "pais debe ser 'PA' o 'CO'")
    if not archivos:
        raise HTTPException(400, "Debes subir al menos un archivo")

    # Prefijo único por lote de subida para evitar colisiones de nombre
    lote_id = uuid.uuid4().hex[:8]

    rutas_guardadas = []
    for idx, archivo in enumerate(archivos):
        ext = Path(archivo.filename).suffix or ".jpg"
        nombre_unico = f"{lote_id}_{idx + 1}{ext}"
        ruta = UPLOAD_DIR / nombre_unico
        with open(ruta, "wb") as f:
            shutil.copyfileobj(archivo.file, f)
        rutas_guardadas.append(str(ruta))

    documento = Documento(
        nombre_archivo=archivos[0].filename,
        ruta_archivo=rutas_guardadas[0],
        rutas_adicionales_json=json.dumps(rutas_guardadas[1:]) if len(rutas_guardadas) > 1 else None,
        pais=pais,
    )
    db.add(documento)
    db.commit()
    db.refresh(documento)

    background_tasks.add_task(_procesar_en_background, documento.id)

    return {
        "documento_id": documento.id,
        "archivos_recibidos": len(rutas_guardadas),
        "estado": "recibido, procesando en segundo plano",
    }


def _procesar_en_background(documento_id: int):
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        documento = db.query(Documento).get(documento_id)
        procesar_documento(db, documento)
    finally:
        db.close()


@router.post("/subir_lote")
async def subir_lote_paginas(
    background_tasks: BackgroundTasks,
    archivos: list[UploadFile] = File(..., description="Imágenes de múltiples páginas de periódico. "
                                        "Para cada página: imagen superior primero, luego imagen inferior. "
                                        "Ejemplo: pag1_sup, pag1_inf, pag2_sup, pag2_inf, ..."),
    pais: str = Form(...),
    db: Session = Depends(get_db),
):
    """Sube múltiples páginas de periódico de una vez.
    Cada página se procesa como un documento independiente.
    Las imágenes deben ir en orden: sup1, inf1, sup2, inf2, ...
    """
    if pais not in ("PA", "CO"):
        raise HTTPException(400, "pais debe ser 'PA' o 'CO'")
    if not archivos or len(archivos) < 2:
        raise HTTPException(400, "Debes subir al menos 2 archivos (1 página con superior + inferior)")

    lote_id = uuid.uuid4().hex[:8]

    # Guardar todas las imágenes
    rutas_guardadas = []
    for idx, archivo in enumerate(archivos):
        ext = Path(archivo.filename).suffix or ".jpg"
        nombre_unico = f"{lote_id}_{idx + 1}{ext}"
        ruta = UPLOAD_DIR / nombre_unico
        with open(ruta, "wb") as f:
            shutil.copyfileobj(archivo.file, f)
        rutas_guardadas.append(str(ruta))

    # Agrupar en pares (superior, inferior) -- cada par = 1 página = 1 documento
    documentos_creados = []
    for i in range(0, len(rutas_guardadas), 2):
        superior = rutas_guardadas[i]
        inferior = rutas_guardadas[i + 1] if i + 1 < len(rutas_guardadas) else None

        num_pagina = (i // 2) + 1
        doc = Documento(
            nombre_archivo=f"pagina_{num_pagina}_{archivos[i].filename}",
            ruta_archivo=superior,
            rutas_adicionales_json=json.dumps([inferior]) if inferior else None,
            pais=pais,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        background_tasks.add_task(_procesar_en_background, doc.id)
        documentos_creados.append({
            "documento_id": doc.id,
            "pagina": num_pagina,
            "archivos": 2 if inferior else 1,
        })

    return {
        "total_paginas": len(documentos_creados),
        "documentos": documentos_creados,
        "estado": "recibido, procesando en segundo plano",
    }


@router.get("/{documento_id}")
def obtener_documento(documento_id: int, db: Session = Depends(get_db)):
    doc = db.query(Documento).get(documento_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")
    adicionales = json.loads(doc.rutas_adicionales_json) if doc.rutas_adicionales_json else []
    return {
        "id": doc.id, "nombre_archivo": doc.nombre_archivo, "pais": doc.pais,
        "estado": doc.estado, "creado_en": doc.creado_en,
        "total_archivos": 1 + len(adicionales),
        "archivos_adicionales": adicionales,
        "avisos": [{"id": a.id, "estado": a.estado, "confianza_promedio": a.confianza_promedio,
                    "expediente": a.expediente} for a in doc.avisos],
    }
