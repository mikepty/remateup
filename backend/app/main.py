from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
from .database import Base, engine, get_db
from .routers import documents, dashboard, approvals, exports
from .models import Aviso, Documento, Auditoria, Aprobacion, Correccion

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
            ("codigo_ubicacion_prensa", "VARCHAR"),
        ],
        "documentos": [
            ("texto_ocr", "TEXT"),
        ],
        "correcciones": [
            ("contexto", "TEXT"),
            ("codigo_prensa", "VARCHAR"),
            ("era_vacio", "BOOLEAN"),
        ],
    }
    insp = inspect(engine)
    with engine.connect() as conn:
        for tabla, columnas in nuevas_columnas.items():
            try:
                existentes = {c["name"] for c in insp.get_columns(tabla)}
            except Exception:
                # La tabla aún no existe (create_all debería haberla creado)
                continue
            for col_name, col_type in columnas:
                if col_name not in existentes:
                    try:
                        conn.execute(text(f'ALTER TABLE {tabla} ADD COLUMN {col_name} {col_type}'))
                        conn.commit()
                        print(f"[migration] Columna agregada: {tabla}.{col_name}")
                    except Exception as e:
                        print(f"[migration] No se pudo agregar {tabla}.{col_name}: {e}")

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


@app.post("/admin/limpiar_aprendizaje")
def limpiar_aprendizaje(db: Session = Depends(get_db)):
    """Borra TODAS las correcciones aprendidas (resetea el aprendizaje)."""
    n = db.query(Correccion).delete()
    db.commit()
    return {"message": f"{n} correccion(es) eliminadas", "status": "ok"}


@app.post("/admin/limpiar_pais/{pais}")
def limpiar_por_pais(pais: str, db: Session = Depends(get_db)):
    """Borra avisos y documentos de un pais específico (PA o CO)."""
    pais_num = 1 if pais == "PA" else 2 if pais == "CO" else None
    if pais_num is None:
        return {"error": "pais debe ser PA o CO"}
    # Borrar avisos del país
    avisos_ids = [a.id for a in db.query(Aviso).filter(Aviso.pais == pais_num).all()]
    if avisos_ids:
        db.query(Aprobacion).filter(Aprobacion.aviso_id.in_(avisos_ids)).delete(synchronize_session=False)
        db.query(Auditoria).filter(Auditoria.aviso_id.in_(avisos_ids)).delete(synchronize_session=False)
    db.query(Aviso).filter(Aviso.pais == pais_num).delete(synchronize_session=False)
    db.query(Documento).filter(Documento.pais == pais).delete(synchronize_session=False)
    db.commit()
    return {"message": f"Datos de {pais} eliminados", "status": "ok"}


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
        "codigo_ubicacion", "codigo_ubicacion_prensa", "finca_matr", "lote_casa",
        "plano", "superficie", "estado",
        "codigo_prensa", "email_observaciones", "codigo_fuente", "prevista"
    ]

    # Campos que NO son datos del periódico (no sirven para aprendizaje de OCR)
    campos_no_aprendibles = {"estado", "codigo", "categoria_codigo", "codigo_ubicacion",
                              "fianza", "minimo"}

    # === PASO 1 (CRÍTICO): aplicar cambios al aviso y guardar ===
    # Recolectamos los cambios aprendibles para procesarlos después, pero lo
    # más importante es que la edición se guarde SIEMPRE.
    cambios_aprendibles = []
    pais_aviso = aviso.pais
    codigo_prensa = aviso.codigo_prensa
    documento_id = aviso.documento_id

    for campo, valor in campos.items():
        if campo in campos_permitidos and hasattr(aviso, campo):
            valor_anterior = getattr(aviso, campo)
            ant_str = "" if valor_anterior in (None, "None") else str(valor_anterior)
            nuevo_str = "" if valor in (None, "None") else str(valor)
            if ant_str.strip() != nuevo_str.strip():
                if campo not in campos_no_aprendibles and nuevo_str.strip():
                    cambios_aprendibles.append((campo, ant_str, nuevo_str))
            setattr(aviso, campo, valor)

    try:
        db.commit()
        db.refresh(aviso)
    except Exception as e:
        db.rollback()
        return {"error": f"No se pudo guardar el aviso: {e}"}

    # === PASO 2 (SECUNDARIO): guardar correcciones para aprendizaje ===
    # La edición YA se guardó. Todo aquí es best-effort y nunca rompe la edición.

    # 2a: obtener contexto de la fuente (OCR) de forma aislada
    contexto = ""
    try:
        if documento_id:
            doc = db.query(Documento).get(documento_id)
            if doc and getattr(doc, "texto_ocr", None):
                contexto = (doc.texto_ocr or "")[:4000]
    except Exception:
        db.rollback()
        contexto = ""

    # 2b: guardar las correcciones
    correcciones_guardadas = 0
    try:
        for campo, ant_str, nuevo_str in cambios_aprendibles:
            db.add(Correccion(
                aviso_id=aviso_id, campo=campo,
                valor_anterior=ant_str, valor_nuevo=nuevo_str,
                pais=pais_aviso, contexto=contexto, codigo_prensa=codigo_prensa,
                era_vacio=(ant_str.strip() == ""),
            ))
            correcciones_guardadas += 1
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[editar_aviso] Aviso guardado, pero falló el aprendizaje: {e}")
        correcciones_guardadas = 0

    return {"message": "Aviso actualizado", "aviso_id": aviso.id,
            "correcciones_aprendidas": correcciones_guardadas}


@app.get("/admin/debug_doc/{documento_id}")
def debug_documento(documento_id: int, db: Session = Depends(get_db)):
    """Debug: devuelve el texto OCR guardado de un documento y un scan de keywords,
    para diagnosticar por que se extrajeron pocos/ningun aviso."""
    doc = db.query(Documento).get(documento_id)
    if not doc:
        return {"error": "documento no encontrado"}
    texto = getattr(doc, "texto_ocr", None) or ""
    t = texto.upper()
    kws = ["REMATE", "SUBASTA", "BASE DEL REMATE", "AVALUO", "AVALÚO", "POSTURA",
           "FIANZA", "CONSIGNAR", "DEMANDANTE", "DEMANDADO", "JUZGADO", "EDICTO",
           "EMPLAZA", "SUCESION", "FINCA", "FOLIO REAL"]
    conteo = {k: t.count(k) for k in kws}
    return {
        "id": doc.id,
        "nombre": doc.nombre_archivo,
        "pais": doc.pais,
        "estado": doc.estado,
        "texto_ocr_len": len(texto),
        "keywords": conteo,
        "texto_ocr": texto,
    }


@app.post("/admin/debug_reestructurar/{documento_id}")
def debug_reestructurar(documento_id: int, db: Session = Depends(get_db)):
    """Debug: re-ejecuta SOLO la estructuracion de Claude sobre el texto OCR ya
    guardado (no vuelve a hacer OCR, no guarda nada). Sirve para probar cambios
    de prompt contra el texto real sin re-subir imagenes."""
    doc = db.query(Documento).get(documento_id)
    if not doc:
        return {"error": "documento no encontrado"}
    texto = getattr(doc, "texto_ocr", None) or ""
    if len(texto.strip()) < 20:
        return {"error": "el documento no tiene texto_ocr guardado", "texto_ocr_len": len(texto)}
    from .pipeline.extraction import _estructurar_texto_ocr, _deduplicar
    try:
        resultado = _deduplicar(_estructurar_texto_ocr(texto, doc.pais))
    except Exception as e:
        return {"error": f"fallo al estructurar: {e}"}
    resumen = [{
        "expediente": (r.get("datos") or {}).get("expediente"),
        "demandante": (r.get("datos") or {}).get("demandante"),
        "demandado": (r.get("datos") or {}).get("demandado"),
        "base": (r.get("datos") or {}).get("base"),
        "finca_matr": (r.get("datos") or {}).get("finca_matr"),
    } for r in resultado]
    return {"documento_id": doc.id, "avisos_encontrados": len(resultado), "resumen": resumen}
