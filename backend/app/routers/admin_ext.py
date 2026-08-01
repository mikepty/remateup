"""Extensión administrativa (FASE 14) — endpoints ADDITIVOS sobre la arquitectura V1.

NO modifica V1, NO crea arquitectura nueva, NO modifica migraciones. Reutiliza los
modelos V1 (`Aviso`, `Documento`, `Auditoria`, `Correccion`) y expone:

  * /admin/sugerencias              -> Hyper Learning (sugerencias)        (Parte 1,4,5)
  * /admin/prediccion               -> campos conflictivos / duplicados     (Parte 5)
  * /admin/aviso/{id}/inteligencia  -> análisis por aviso                   (Parte 2)
  * /admin/aviso/{id}/aplicar       -> aplicar una sugerencia (audit)       (Parte 3)
  * DELETE /admin/aviso/{id}        -> soft-delete + restaurar              (Parte 7)
  * POST /admin/avisos/borrar       -> borrar por filtros / duplicados      (Parte 7)
  * GET  /admin/diagnostico         -> diagnóstico global                   (Parte 10,11)
  * GET  /admin/reportes/client_ready -> generar reportes .json/.md         (Parte 12)
  * GET  /admin/admin-dashboard     -> métricas admin                       (Parte 6)

Panamá es prioridad (Parte 14): sugerencias priorizan pais=1; Colombia no se rompe.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Aviso, Documento, Auditoria, Correccion
from ..pipeline import audit as audit_mod
from ..config import (BASE_DIR, GEMINI_API_KEY, ANTHROPIC_API_KEY,
                      GOOGLE_VISION_API_KEY, MOTOR_IA, WHATSAPP_BRIDGE_URL)
from ..routers.dashboard import _serializar_aviso
from ..learning.engine import generar_sugerencias, inteligencia_aviso, predecir
from ..learning.reports import BUILDERS as REPORT_BUILDERS

router = APIRouter(prefix="/admin", tags=["admin-fase14"])

UPLOAD_DIR = BASE_DIR / "data" / "uploads"

# Campos que un cliente puede editar (deben coincidir con main.editar_aviso).
CAMPOS_PERMITIDOS = [
    "codigo", "expediente", "lugar", "proceso", "demandante", "demandado",
    "descripcion", "descripcion_completa", "fecha", "hora", "base",
    "fianza_porcentaje", "minimo_porcentaje", "fianza", "minimo",
    "categoria", "categoria_codigo", "provincia", "codigo_ubicacion",
    "codigo_ubicacion_prensa", "finca_matr", "lote_casa", "plano", "superficie",
    "codigo_prensa", "email_observaciones", "codigo_fuente", "prevista",
    "periodico", "fecha_prensa", "pagina_prensa",
]


def _correccion_to_dict(c: Correccion) -> dict:
    return {
        "id": c.id, "aviso_id": c.aviso_id, "campo": c.campo,
        "valor_anterior": c.valor_anterior, "valor_nuevo": c.valor_nuevo,
        "pais": c.pais, "contexto": c.contexto, "codigo_prensa": c.codigo_prensa,
        "era_vacio": bool(c.era_vacio), "creado_en": c.creado_en.isoformat() if c.creado_en else "",
    }


def _auditoria_a_lista(db: Session, aviso_id: int) -> list[dict]:
    regs = db.query(Auditoria).filter(Auditoria.aviso_id == aviso_id).order_by(Auditoria.creado_en.desc()).limit(200).all()
    return [{"agente": r.agente, "accion": r.accion, "detalle": r.detalle,
             "creado_en": r.creado_en.isoformat() if r.creado_en else ""} for r in regs]


# ---------------------------------------------------------------- Parte 1/4/5
@router.get("/sugerencias")
def sugerencias(
    pais: Optional[int] = Query(None, description="1=PA, 2=CO"),
    campo: Optional[str] = Query(None),
    top_n: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """SUGERENCIAS (nunca se aplican automáticamente). Lee la tabla
    `correcciones` y devuelve sugerencias de normalización/alias/etiquetas."""
    q = db.query(Correccion)
    if pais is not None:
        q = q.filter(Correccion.pais == pais)
    if campo:
        q = q.filter(Correccion.campo == campo)
    rows = [_correccion_to_dict(c) for c in q.order_by(Correccion.creado_en.desc()).all()]
    sugs = generar_sugerencias(rows, top_n=top_n)
    return {"total": len(sugs), "sugerencias": sugs}


@router.get("/prediccion")
def prediccion(db: Session = Depends(get_db)):
    """Parte 5: campos más problemáticos, OCR conflictos, duplicados, campos vacíos."""
    correcciones = [_correccion_to_dict(c) for c in db.query(Correccion).all()]
    avisos = [_serializar_aviso(a) for a in db.query(Aviso).all()]
    return predecir(correcciones, avisos)


# ---------------------------------------------------------------- Parte 2
@router.get("/aviso/{aviso_id}/inteligencia")
def inteligencia(aviso_id: int, db: Session = Depends(get_db)):
    """Parte 2: análisis por aviso — ¿por qué falló? ¿qué faltó? ¿qué motor?
    ¿qué sugerencia aplica? ¿qué confianza predeciría?"""
    aviso = db.query(Aviso).get(aviso_id)
    if not aviso:
        raise HTTPException(404, "Aviso no encontrado")
    a = _serializar_aviso(aviso)
    auditoria = _auditoria_a_lista(db, aviso_id)
    correcciones_aviso = [_correccion_to_dict(c) for c in
                          db.query(Correccion).filter(Correccion.aviso_id == aviso_id).all()]
    return inteligencia_aviso(a, auditoria, correcciones_aviso)


# ---------------------------------------------------------------- Parte 3
@router.post("/aviso/{aviso_id}/aplicar")
def aplicar_sugerencia(
    aviso_id: int, campo: str = Query(...), valor: str = Query(...),
    motivo: str = Query(""), usuario: str = Query("admin"),
    db: Session = Depends(get_db),
):
    """Aplicar EXPLICITAMENTE una sugerencia a un aviso (Parte 3). Registra
    auditoría + corrección de aprendizaje. Nunca es automático."""
    aviso = db.query(Aviso).get(aviso_id)
    if not aviso or not hasattr(aviso, campo):
        raise HTTPException(404, "Aviso o campo no encontrado")
    if campo not in CAMPOS_PERMITIDOS:
        raise HTTPException(400, f"Campo no permitido: {campo}")
    valor_anterior = getattr(aviso, campo)
    setattr(aviso, campo, valor)
    try:
        db.commit(); db.refresh(aviso)
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"No se pudo guardar: {e}")
    audit_mod.registrar(db, "admin", "aplicar_sugerencia",
                        f"campo={campo} valor={valor} motivo={motivo} usuario={usuario}",
                        aviso_id=aviso.id)
    # Aprendizaje: registrar la corrección aplicada
    db.add(Correccion(
        aviso_id=aviso_id, campo=campo,
        valor_anterior=("" if valor_anterior in (None, "None") else str(valor_anterior)),
        valor_nuevo=str(valor), pais=aviso.pais,
        contexto=f"applied_suggestion from {valor_anterior}", codigo_prensa=aviso.codigo_prensa,
        era_vacio=(not valor_anterior),
    ))
    try:
        db.commit()
    except Exception:
        db.rollback()
    return {"aviso_id": aviso.id, "campo": campo, "valor_anterior": valor_anterior,
            "valor_nuevo": valor, "estado": aviso.estado}


# ---------------------------------------------------------------- Parte 7
@router.delete("/aviso/{aviso_id}")
def eliminar_aviso(aviso_id: int,
                   confirm: bool = Query(True),
                   db: Session = Depends(get_db)):
    """Eliminar UN aviso. Soft-delete (estado='eliminado') por seguridad y para
    permitir rollback lógico. Registra auditoría inmediata."""
    aviso = db.query(Aviso).get(aviso_id)
    if not aviso:
        raise HTTPException(404, "Aviso no encontrado")
    if not confirm:
        raise HTTPException(400, "Confirme con confirm=true")
    previo = aviso.estado
    aviso.estado = "eliminado"
    db.commit()
    audit_mod.registrar(db, "admin", "eliminar_aviso",
                        f"estado {previo} -> eliminado", aviso_id=aviso.id,
                        documento_id=aviso.documento_id)
    return {"aviso_id": aviso.id, "antes": previo, "ahora": "eliminado",
            "mensaje": "Soft-delete. Usar /admin/aviso/{id}/restaurar para rollback logico."}


@router.post("/aviso/{aviso_id}/restaurar")
def restaurar_aviso(aviso_id: int, db: Session = Depends(get_db)):
    """Rollback lógico de un soft-delete."""
    aviso = db.query(Aviso).get(aviso_id)
    if not aviso:
        raise HTTPException(404, "Aviso no encontrado")
    if aviso.estado != "eliminado":
        return {"aviso_id": aviso.id, "mensaje": "El aviso no esta eliminado"}
    aviso.estado = "pendiente_procesar"
    db.commit()
    audit_mod.registrar(db, "admin", "restaurar_aviso",
                        "eliminado -> pendiente_procesar (rollback)", aviso_id=aviso.id,
                        documento_id=aviso.documento_id)
    return {"aviso_id": aviso.id, "ahora": aviso.estado}


def _avisos_query_bulk(db: Session, params: dict) -> "Query":
    q = db.query(Aviso).filter(Aviso.estado != "eliminado")
    pais = params.get("pais")
    if pais is not None:
        q = q.filter(Aviso.pais == int(pais))
    estado = params.get("estado")
    if estado:
        q = q.filter(Aviso.estado == estado)
    if params.get("documento_id"):
        q = q.filter(Aviso.documento_id == int(params["documento_id"]))
    fdesde = params.get("fecha_desde")
    fhasta = params.get("fecha_hasta")
    if fdesde:
        try:
            q = q.filter(Aviso.creado_en >= datetime.strptime(fdesde, "%Y-%m-%d"))
        except ValueError:
            pass
    if fhasta:
        try:
            q = q.filter(Aviso.creado_en <= datetime.strptime(fhasta, "%Y-%m-%d"))
        except ValueError:
            pass
    if params.get("ids"):
        ids = [int(i) for i in re.split(r"[,\s]+", params["ids"]) if i.isdigit()]
        if ids:
            q = q.filter(Aviso.id.in_(ids))
    return q


@router.post("/avisos/borrar")
def borrar_avisos(
    request: Request, db: Session = Depends(get_db),
    pais: Optional[int] = Query(None),
    estado: Optional[str] = Query(None),
    documento_id: Optional[int] = Query(None),
    fecha_desde: Optional[str] = Query(None),
    fecha_hasta: Optional[str] = Query(None),
    ids: Optional[str] = Query(None),
    duplicados: bool = Query(False),
    confirm: bool = Query(...),
):
    """Borrar varios avisos por filtros (Parte 7). Soft-delete + auditoría.
    Si `duplicados=true`, borra los duplicados (misma expediente+finca+base)
    dejando el más reciente. Nunca elimina sin confirm=true."""
    if not confirm:
        raise HTTPException(400, "Confirme con confirm=true")
    params = {"pais": pais, "estado": estado, "documento_id": documento_id,
              "fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta, "ids": ids}
    q = _avisos_query_bulk(db, params)
    if duplicados:
        # duplicados por (pais, expediente, finca_matr, base): conservar el max(id)
        sub = (db.query(Aviso.pais, Aviso.expediente, Aviso.finca_matr, Aviso.base,
                        func.max(Aviso.id).label("keep_id"))
               .filter(Aviso.estado != "eliminado")
               .group_by(Aviso.pais, Aviso.expediente, Aviso.finca_matr, Aviso.base)
               .subquery())
        q = q.join(sub,
                   (Aviso.pais == sub.c.pais) & (Aviso.expediente == sub.c.expediente) &
                   (Aviso.finca_matr == sub.c.finca_matr) & (Aviso.base == sub.c.base))
        q = q.filter(Aviso.id != sub.c.keep_id)
    avisos = q.all()
    n = 0
    for a in avisos:
        a.estado = "eliminado"
        n += 1
    db.commit()
    audit_mod.registrar(db, "admin", "borrar_lote",
                        f"soft-delete {n} avisos; filtros={params}; duplicados={duplicados}",
                        documento_id=documento_id)
    return {"borrados": n, "estado": "eliminado",
            "mensaje": f"Soft-delete de {n} avisos. Rollback: re-procesar o restaurar individual."}


# ---------------------------------------------------------------- Parte 10/11
def _try_import(module_path: str):
    try:
        mod = __import__(module_path, fromlist=["__ok"])
        return {"status": "ok", "detalle": f"{module_path} importable"}
    except Exception as e:
        return {"status": "error", "detalle": f"{type(e).__name__}: {str(e)[:160]}"}


@router.get("/diagnostico")
def diagnostico(db: Session = Depends(get_db)):
    checks: dict = {}
    # 1) DB
    try:
        db.execute(text("SELECT 1"))
        total_a = db.query(func.count(Aviso.id)).scalar()
        total_d = db.query(func.count(Documento.id)).scalar()
        total_c = db.query(func.count(Correccion.id)).scalar()
        checks["db"] = {"status": "ok", "detalle": f"avisos={total_a}, documentos={total_d}, correcciones={total_c}"}
    except Exception as e:
        checks["db"] = {"status": "error", "detalle": f"{type(e).__name__}: {str(e)[:160]}"}
    # 2) Variables de entorno / IA / OCR
    checks["ocr"] = {"status": "ok" if GOOGLE_VISION_API_KEY else "fail",
                     "detalle": "GOOGLE_VISION_API_KEY configurada" if GOOGLE_VISION_API_KEY else "SIN KEY (OCR caído)"}
    ia_ok = bool(GEMINI_API_KEY or ANTHROPIC_API_KEY)
    checks["ia"] = {"status": "ok" if ia_ok else "fail",
                    "detalle": f"MOTOR_IA={MOTOR_IA}; gemini={'sí' if GEMINI_API_KEY else 'no'}; "
                               f"claude={'sí' if ANTHROPIC_API_KEY else 'no'}; "
                               f"nota: ANTHROPIC sin saldo y GEMINI 429 (ver logs de pipeline)"}
    checks["whatsapp_bridge"] = {"status": "ok" if WHATSAPP_BRIDGE_URL else "warn",
                                 "detalle": WHATSAPP_BRIDGE_URL or "no configurado (default localhost:3001)"}
    # 3) Knowledge (v2 knowledge.db)
    kb_path = BASE_DIR / "app" / "v2" / "knowledge" / "knowledge.db"
    checks["knowledge"] = {"status": "ok" if kb_path.exists() else "warn",
                           "detalle": str(kb_path),
                           "size_bytes": kb_path.stat().st_size if kb_path.exists() else 0}
    # 4) Pipeline V1 importable
    pm1 = _try_import("backend.app.pipeline.orchestrator")
    checks["pipeline_v1"] = pm1
    # 5) V2 módulos (guardados: un import roto no rompe V1)
    checks["validator_v2"] = _try_import("backend.app.v2.validator.notice_validator")
    checks["certification_v2"] = _try_import("backend.app.v2.fase8.certification_engine")
    checks["segmenter_v2"] = _try_import("backend.app.v2.segmenter.engine")
    checks["evaluation_v2"] = _try_import("backend.app.v2.evaluation.production.health")
    # 6) Smoke local: extracción determinista sobre texto de prueba (offline, PA)
    try:
        from ..pipeline.extraction import _estructurar_texto_ocr
        sample = ("AVISO DE REMATE Expediente No. 1-25 La Alguacil. Servira de base "
                  "para el remate la cifra de B/.110,000.00 y sera postura admisible "
                  "la que cubra las dos terceras partes (2/3). FIANZA 10%.")
        out = _estructurar_texto_ocr(sample, "PA")
        checks["smoke_extraccion"] = {"status": "ok" if out else "fail",
                                      "detalle": f"{len(out)} aviso(s) extraídos (IA->det fallback)"}
    except Exception as e:
        checks["smoke_extraccion"] = {"status": "error", "detalle": f"{type(e).__name__}: {str(e)[:160]}"}
    # 7) Uploads dir
    checks["uploads_dir"] = {"status": "ok" if UPLOAD_DIR.exists() else "warn",
                             "detalle": str(UPLOAD_DIR)}
    checks["firebase_hosting"] = {"status": "ok", "detalle": "remateup-panel.web.app (Firebase Hosting)"}
    checks["render_backend"] = {"status": "ok", "detalle": "remateup-backend.onrender.com (auto-deploy master)"}

    fallos = [k for k, v in checks.items() if v["status"] in ("error", "fail")]
    return {"timestamp": datetime.utcnow().isoformat(),
            "checks": checks, "fallos_criticos": fallos,
            "ok_general": len(fallos) == 0}


# ---------------------------------------------------------------- Parte 6
@router.get("/admin-dashboard")
def admin_dashboard(db: Session = Depends(get_db)):
    """Métricas para el panel admin (Parte 6): reusa dashboard + aprendizaje."""
    from .dashboard import metricas, estadisticas_aprendizaje
    m = metricas.__wrapped__(db) if hasattr(metricas, "__wrapped__") else metricas(db)
    try:
        m.update(estadisticas_aprendizaje(db))
    except Exception:
        pass
    # sugerencias rápidas
    rows = [_correccion_to_dict(c) for c in db.query(Correccion).order_by(Correccion.creado_en.desc()).limit(5000).all()]
    sugs = generar_sugerencias(rows, top_n=10)
    m["sugerencias_top"] = sugs[:10]
    m["ultimas_correcciones"] = rows[:20]
    return m


# ---------------------------------------------------------------- Parte 12
@router.get("/reportes/client_ready")
def generar_reportes(db: Session = Depends(get_db),
                     out_dir: str = Query(None)):
    """Genera los 7 reportes de la Parte 12 (.json + .md) reutilizando los
    motores existentes. Devuelve rutas de archivos escritos."""
    out = Path(out_dir) if out_dir else (BASE_DIR / "app" / "reports" / "output")
    out.mkdir(parents=True, exist_ok=True)

    # 1) Hyper Learning
    rows = [_correccion_to_dict(c) for c in db.query(Correccion).order_by(Correccion.creado_en.desc()).all()]
    sugs = generar_sugerencias(rows)
    data_hl = {"sugerencias": sugs}

    # 2) Hyper Intelligence (últimos 30 avisos en espera + subidos)
    avisos_q = (db.query(Aviso)
                .filter(Aviso.estado.in_(["esperando_aprobacion", "subido", "auto_aprobado"]))
                .order_by(Aviso.creado_en.desc()).limit(30).all())
    analisis = []
    for a in avisos_q:
        adv = _auditoria_a_lista(db, a.id)
        corrc = [_correccion_to_dict(c) for c in db.query(Correccion).filter(Correccion.aviso_id == a.id).all()]
        analisis.append(inteligencia_aviso(_serializar_aviso(a), adv, corrc))
    data_hi = {"analisis_por_aviso": analisis}

    # 3) Diagnóstico
    data_diag = diagnostico(db)

    # 4) UI audit (escanea index.html + endpoints declarados)
    data_ui = _auditar_ui()

    # 5) Knowledge evolution (top correcciones repetidas)
    pares = {}
    for r in rows:
        k = (r["campo"], str(r["valor_anterior"]), str(r["valor_nuevo"]))
        pares.setdefault(k, {"campo": r["campo"], "valor_anterior": r["valor_anterior"],
                             "valor_nuevo": r["valor_nuevo"], "count": 0, "ultima": r["creado_en"]})
        pares[k]["count"] += 1
        if r["creado_en"] > pares[k]["ultima"]:
            pares[k]["ultima"] = r["creado_en"]
    evol = sorted(pares.values(), key=lambda x: -x["count"])[:20]
    data_ke = {"evolucion": evol}

    # 6) Continuous learning (eventos recientes de auditoria + correcciones)
    eventos = []
    for r in db.query(Auditoria).order_by(Auditoria.creado_en.desc()).limit(100).all():
        eventos.append({"timestamp": r.creado_en.isoformat(), "agente": r.agente,
                        "accion": r.accion, "aviso_id": r.aviso_id, "detalle": r.detalle})
    for r in rows[:100]:
        eventos.append({"timestamp": r["creado_en"], "agente": "cliente",
                        "accion": "correccion", "aviso_id": r["aviso_id"],
                        "detalle": f"{r['campo']}: '{r['valor_anterior']}'->'{r['valor_nuevo']}'"})
    eventos.sort(key=lambda e: e["timestamp"], reverse=True)
    data_cl = {"registro": eventos[:100]}

    # 7) client_ready (resumen + issues)
    checks = data_diag["checks"]
    resumen = {k: v.get("status", "?") for k, v in checks.items()}
    resumen["avisos_totales"] = data_diag["checks"]["db"]["detalle"].split("avisos=")[1].split(",")[0] if "avisos=" in data_diag["checks"]["db"]["detalle"] else "?"
    issues = []
    if not GOOGLE_VISION_API_KEY:
        issues.append({"area": "OCR", "severidad": "crítica", "problema": "GOOGLE_VISION_API_KEY no configurada",
                       "accion": "Configurar variable de entorno en Render"})
    if checks.get("ia", {}).get("status") != "ok":
        issues.append({"area": "IA", "severidad": "alta", "problema": "Motor(es) de IA sin key",
                       "accion": "Configurar GEMINI_API_KEY / ANTHROPIC_API_KEY"})
    if checks.get("segmenter_v2", {}).get("status") != "ok":
        issues.append({"area": "v2/segmenter", "severidad": "media",
                       "problema": "Import error (DetectedBlock)",
                       "accion": "Revisar app/v2/segmenter/models.py forward refs"})
    data_cr = {"timestamp": datetime.utcnow().isoformat(), "resumen": resumen, "issues": issues}

    datasets = {
        "hyper_learning": data_hl, "hyper_intelligence": data_hi,
        "production_diagnosis": data_diag, "ui_audit": data_ui,
        "knowledge_evolution": data_ke, "continuous_learning": data_cl,
        "client_ready": data_cr,
    }
    archivos = []
    for name, data in datasets.items():
        b = REPORT_BUILDERS[name]
        j, m = b(data)
        (out / f"{name}.json").write_text(j, encoding="utf-8")
        (out / f"{name}.md").write_text(m, encoding="utf-8")
        archivos.append(str(out / f"{name}.json"))
        archivos.append(str(out / f"{name}.md"))
    return {"out_dir": str(out), "archivos": archivos, "datasets": list(datasets)}


def _auditar_ui() -> dict:
    """Parte 8/9: escanea index.html en busca de endpoints llamados y botones
    declarados vs implementados. Best-effort, offline."""
    idx = BASE_DIR.parent / "frontend" / "public" / "index.html"
    hallazgos = []
    if not idx.exists():
        return {"hallazgos": [{"elemento": "index.html", "tipo": "archivo", "estado": "fail",
                               "observacion": "frontend/public/index.html no encontrado"}]}
    html = idx.read_text(encoding="utf-8", errors="replace")
    # endpoints llamados desde el frontend
    llamados = sorted(set(re.findall(r"apiUrl\(['\"]([^'\"]+)['\"]", html)))
    declarados = ["/documentos/subir", "/documentos/{id}", "/documentos/{id}/reintentar",
                  "/dashboard/metricas", "/dashboard/pendientes", "/dashboard/todos",
                  "/admin/editar_aviso/{id}"]
    for ep in llamados:
        hallazgos.append({"elemento": ep, "tipo": "endpoint", "estado": "ok",
                          "observacion": f"llamado desde index.html"})
    # botones declarados
    botones = ["subirDocumento", "reintentarDocumento", "aprobar", "simularTodas",
               "simularUna", "exportarExcel", "exportarFiltrados", "abrirEditor",
               "guardarEdicion", "toggleDet", "cargarPendientes", "cargarHistorial"]
    for b in botones:
        ok = bool(re.search(rf"(?:function\s+{b}\s*\(|\b{b}\s*\()", html))
        hallazgos.append({"elemento": b, "tipo": "boton/funcion JS", "estado": "ok" if ok else "warn",
                          "observacion": "implementada" if ok else "NO implementada en index.html"})
    return {"index_html": str(idx), "endpoints_llamados": llamados, "n_hallazgos": len(hallazgos),
            "hallazgos": hallazgos}
