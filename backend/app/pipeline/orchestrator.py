"""
Orchestrator: coordina el flujo completo, paso a paso, de forma lineal y explícita.
"""
import json
from sqlalchemy.orm import Session
from ..models import Documento, Aviso
from . import extraction, business_rules, validation, confidence, audit
from ..whatsapp.notifier import enviar_solicitud_aprobacion
from ..upload.platform_uploader import subir_a_plataforma


def procesar_documento(db: Session, documento: Documento) -> list[Aviso]:
    audit.registrar(db, "orchestrator", "inicio_procesamiento",
                     f"Procesando {documento.nombre_archivo}", documento_id=documento.id)

    documento.estado = "procesando"
    db.commit()

    try:
        rutas = [documento.ruta_archivo]
        if documento.rutas_adicionales_json:
            rutas.extend(json.loads(documento.rutas_adicionales_json))
        salida_ocr = {}
        resultados = extraction.extraer(rutas, documento.pais, salida_ocr=salida_ocr)
        # Guardar el texto OCR en el documento (fuente para verificar/aprender)
        if salida_ocr.get("texto"):
            try:
                documento.texto_ocr = salida_ocr["texto"][:300000]
                db.commit()
            except Exception:
                db.rollback()
        audit.registrar(db, "extraction", "extraccion_completa",
                         f"{len(resultados)} aviso(s) extraído(s)", documento_id=documento.id)
    except Exception as e:
        documento.estado = "error"
        db.commit()
        audit.registrar(db, "extraction", "error", str(e), documento_id=documento.id)
        raise

    avisos_creados = []

    for idx, item in enumerate(resultados):
        try:
            datos = business_rules.aplicar_reglas(item["datos"])
            confianza_campos = item["confianza"]
            audit.registrar(db, "business_rules", "reglas_aplicadas",
                             json.dumps(datos, ensure_ascii=False, default=str), documento_id=documento.id)

            faltantes = validation.campos_faltantes(datos)
            resultado_validacion = validation.evaluar_duplicado_o_republicacion(db, datos)
            discrepancia = datos.get("_discrepancia_valores", False)

            fianza_asumida = datos.get("_fianza_asumida_por_regla", False)
            decision = confidence.decidir(confianza_campos, faltantes, resultado_validacion, discrepancia, fianza_asumida)
            audit.registrar(db, "confidence", decision["decision"], decision["motivo"], documento_id=documento.id)

            aviso_reemplazado_id = resultado_validacion.get("aviso_a_reemplazar_id")
            if aviso_reemplazado_id:
                anterior = db.query(Aviso).get(aviso_reemplazado_id)
                if anterior:
                    anterior.estado = "reemplazado_por_republicacion"
                    db.commit()

            # Filtrar solo campos que existen en el modelo
            campos_aviso = {}
            for k, v in datos.items():
                if not k.startswith("_") and hasattr(Aviso, k):
                    campos_aviso[k] = v

            aviso = Aviso(
                documento_id=documento.id,
                **campos_aviso,
                confianza_promedio=decision["confianza_promedio"],
                campos_confianza_json=json.dumps(confianza_campos),
                campos_faltantes_json=json.dumps(faltantes),
                discrepancia_valores=discrepancia,
                detalle_discrepancia_json=json.dumps(datos.get("_detalle_discrepancia_valores", [])),
                fianza_asumida_por_regla=datos.get("_fianza_asumida_por_regla", False),
                tipo_validacion=resultado_validacion["tipo"],
                aviso_original_id=aviso_reemplazado_id,
                estado=decision["decision"],
            )
            db.add(aviso)
            db.commit()
            db.refresh(aviso)

            if decision["decision"] == "auto_aprobado":
                try:
                    subir_a_plataforma(aviso)
                    aviso.estado = "subido"
                    db.commit()
                except Exception as e:
                    aviso.estado = "error"
                    db.commit()

            avisos_creados.append(aviso)
        except Exception as e:
            # Log the error to audit so we can see it
            audit.registrar(db, "orchestrator", "error_aviso", f"Item {idx}: {str(e)[:500]}", documento_id=documento.id)
            db.commit()
            continue

    documento.estado = "completado"
    db.commit()
    audit.registrar(db, "orchestrator", "fin_procesamiento",
                     f"{len(avisos_creados)} aviso(s) procesado(s)", documento_id=documento.id)

    return avisos_creados
