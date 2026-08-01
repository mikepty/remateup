"""
Agente de Subida a Plataforma.

MAPEO REAL DE CAMPOS (confirmado con capturas de la app RemateHoy, Play Store):

  Nuestro campo interno    -> Campo en la plataforma           -> Formato
  ------------------------    ----------------------------        -------
  base                     -> "Base del remate" (PA)            -> monto $
                            -> "Avalúo del remate" (CO)          -> monto $
  fianza                   -> "Mínimo para participar"           -> PA: monto $
                                                                     CO: PORCENTAJE ("40%", texto, no monto)
  minimo                   -> "Mínimo para ganarte el remate"    -> monto $ (ambos países)
  finca_matr                -> "Folio (Finca)" (PA)               -> igual
                            -> "Matrícula inmobiliaria" (CO)      -> igual
  lote_casa                -> "Lote o número de casa"            -> igual
  codigo                   -> "#PA64103320" / "#CO64103994"      -> la plataforma asigna el #

  codigo_ubicacion_prensa -> "Código de Ubicación" (ej. "8706", "4506")
                             -> código impreso en el aviso original (número de
                                dígitos VARIABLE, normalmente 1-6). El cliente lo
                                usa como referencia para ubicarse cerca al abrir
                                Maps. Respaldo: codigo_ubicacion (provincia 1-43).

RemateHoy es una app Android (Play Store), no un sitio web -- Playwright no
aplica directo. Ver notas de integración más abajo (API REST vs Appium).
"""
import requests
from ..models import Aviso

SIMULACION_ACTIVA = True  # cambiar a False cuando haya integración real


def _moneda(valor) -> str:
    """Convierte un valor numérico a formato monetario para la plataforma."""
    if valor is None:
        return "0.00"
    try:
        return f"{float(valor):.2f}"
    except (ValueError, TypeError):
        return "0.00"


def _formato_codigo(aviso: Aviso) -> str:
    """Genera el código en formato #PA64103320 / #CO64103994."""
    prefijo = "PA" if aviso.pais == 1 else "CO"
    # Usar el código del aviso si ya tiene el formato correcto
    if aviso.codigo and aviso.codigo.startswith("#"):
        return aviso.codigo
    if aviso.codigo:
        return f"#{aviso.codigo}"
    return f"#{prefijo}00000000"


def _construir_payload(aviso: Aviso) -> dict:
    """Construye el payload exacto que espera la API de RemateHoy,
    según las capturas de la app (appPA01-03 para Panamá, app23-25 para Colombia)."""
    es_colombia = aviso.pais == 2

    payload = {
        # Identificación
        "codigo": _formato_codigo(aviso),

        # Fechas
        "fecha_remate": aviso.fecha or "",
        "hora_remate": aviso.hora or "",

        # Ubicación
        "provincia_o_departamento": aviso.provincia or "",
        # "Código de Ubicación": el código impreso en el aviso (número de
        # dígitos variable), con respaldo al de provincia.
        "codigo_ubicacion": str(aviso.codigo_ubicacion_prensa or aviso.codigo_ubicacion or ""),

        # Proceso judicial
        "juzgado": aviso.lugar or "",
        "tipo_proceso": aviso.proceso or "",
        "expediente": aviso.expediente or "",

        # Partes
        "demandante": aviso.demandante or "",
        "demandado": aviso.demandado or "",

        # Descripción del bien
        "descripcion": aviso.descripcion or "",

        # Valores económicos
        # PA: "Base del remate" / CO: "Avalúo del remate"
        "base_remate": _moneda(aviso.base),

        # "Mínimo para participar"
        # PA: monto en dólares / CO: porcentaje ("40%")
        "minimo_participar": f"{aviso.fianza_porcentaje}%" if es_colombia else _moneda(aviso.fianza),

        # "Mínimo para ganarte el bien" -- monto en ambos países
        "minimo_ganar": _moneda(aviso.minimo),

        # Categoría
        "categoria": aviso.categoria or "",

        # Datos del bien
        "lote_o_casa": aviso.lote_casa or "",
        "folio_o_matricula": aviso.finca_matr or "",
        "plano": aviso.plano or "",
        "superficie": aviso.superficie or "",
    }

    return payload


def subir_a_plataforma(aviso: Aviso) -> dict:
    """Sube un aviso a la plataforma RemateHoy."""
    payload = _construir_payload(aviso)

    if SIMULACION_ACTIVA:
        print(f"[SIMULADO] Se subiría el aviso #{aviso.id} (expediente {aviso.expediente})")
        print(f"  Payload: {payload}")
        return {"status": "simulado", "aviso_id": aviso.id, "payload": payload}

    # --- CAMINO A (preferido): API REST detrás de la app ---
    # Encontrar la API real con mitmproxy/HTTP Toolkit mientras se crea un
    # registro manualmente en la app.
    #
    # import os
    # api_url = os.environ.get("REMATEHOY_API_URL", "https://api.remate-hoy.com")
    # api_token = os.environ.get("REMATEHOY_API_TOKEN", "")
    # respuesta = requests.post(
    #     f"{api_url}/registros",
    #     headers={"Authorization": f"Bearer {api_token}"},
    #     json=payload,
    #     timeout=30,
    # )
    # respuesta.raise_for_status()
    # return {"status": "subido", "aviso_id": aviso.id, "respuesta": respuesta.json()}

    # --- CAMINO B (respaldo): Appium sobre un emulador Android ---
    # Solo si de verdad no hay API accesible.

    raise NotImplementedError("Integración real con la plataforma aún no configurada.")
