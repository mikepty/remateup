"""
Agente WhatsApp. No implementa el protocolo de WhatsApp directamente --
delega al servicio 'whatsapp-bridge' (Node.js + Baileys) via HTTP.
Esta separación permite reiniciar/actualizar el backend Python sin tocar
la sesión de WhatsApp, que es lo más frágil de mantener corriendo.
"""
import requests
from sqlalchemy.orm import Session
from ..config import WHATSAPP_BRIDGE_URL, WHATSAPP_APROBADOR
from ..models import Aprobacion, Aviso, Documento


def _moneda(valor) -> str:
    if valor is None:
        return "N/D"
    try:
        return f"${float(valor):,.2f}"
    except (ValueError, TypeError):
        return str(valor)


def _construir_mensaje(aviso: Aviso, motivo: str) -> str:
    bandera = "🇵🇦" if aviso.pais == 1 else "🇨🇴" if aviso.pais == 2 else ""
    categoria = f"{aviso.categoria or 'N/D'}" + (f" (código {aviso.categoria_codigo})" if aviso.categoria_codigo else "")
    ubicacion = f"{aviso.provincia or 'N/D'}" + (f" (código {aviso.codigo_ubicacion})" if aviso.codigo_ubicacion else "")

    fianza_linea = f"Fianza: {_moneda(aviso.fianza)} ({aviso.fianza_porcentaje or '?'}%)"
    if aviso.fianza_asumida_por_regla:
        fianza_linea += "  ⚠️ asumida por regla, no venía en el texto"

    return (
        f"{bandera} *RemateUp — Aviso #{aviso.id} requiere tu aprobación*\n\n"
        f"*Motivo:* {motivo}\n\n"
        f"Expediente: {aviso.expediente or 'N/D'}\n"
        f"Demandante: {aviso.demandante or 'N/D'}\n"
        f"Demandado: {aviso.demandado or 'N/D'}\n"
        f"Categoría: {categoria}\n"
        f"Ubicación: {ubicacion}\n"
        f"Fecha del remate: {aviso.fecha or 'N/D'} {aviso.hora or ''}\n"
        f"Lugar/Juzgado: {aviso.lugar or 'N/D'}\n\n"
        f"Base: {_moneda(aviso.base)}\n"
        f"{fianza_linea}\n"
        f"Mínimo: {_moneda(aviso.minimo)} ({aviso.minimo_porcentaje or '?'}%)\n\n"
        f"Confianza del sistema: {(aviso.confianza_promedio or 0)*100:.0f}%\n\n"
        f"Responde:\n"
        f"*SI {aviso.id}* para aprobar y subir\n"
        f"*NO {aviso.id}* para rechazar"
    )


def enviar_solicitud_aprobacion(db: Session, aviso: Aviso, documento: Documento, motivo: str):
    mensaje = _construir_mensaje(aviso, motivo)

    aprobacion = Aprobacion(
        aviso_id=aviso.id,
        mensaje_enviado=mensaje,
        numero_destino=WHATSAPP_APROBADOR,
    )
    db.add(aprobacion)
    db.commit()

    if not WHATSAPP_APROBADOR:
        # Sin número configurado, se registra pero no se envía (útil en desarrollo/demo)
        return aprobacion

    try:
        requests.post(f"{WHATSAPP_BRIDGE_URL}/send", json={
            "to": WHATSAPP_APROBADOR,
            "message": mensaje,
            "media_path": documento.ruta_archivo,  # adjunta el soporte original
        }, timeout=10)
    except requests.RequestException as e:
        # No se detiene el flujo si WhatsApp falla -- queda pendiente en el dashboard igual.
        print(f"[whatsapp] No se pudo enviar (¿bridge caído?): {e}")

    return aprobacion
