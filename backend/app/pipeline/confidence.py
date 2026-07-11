"""
Agente de Confianza / Decisión.
Umbral configurable y explícito -- auditable, no una caja negra, apropiado
para un proceso legal donde cada decisión debe poder explicarse.
"""
from ..config import UMBRAL_CONFIANZA
from .business_rules import CAMPOS_DERIVADOS


def _a_float_seguro(valor):
    """Convierte a float de forma tolerante -- Gemini a veces devuelve la
    confianza como texto ('1.0' en vez de 1.0) o algún tipo inesperado.
    Si no se puede convertir, se ignora ese valor en vez de tronar."""
    if valor is None:
        return None
    try:
        return float(valor)
    except (ValueError, TypeError):
        return None


# Campos cuyo valor ya se sabe de antemano (porcentaje fijo por ley) o se
# deriva del negocio -- no deben bloquear la auto-aprobación aunque el OCR
# les haya dado confianza baja o haya puesto null.
CAMPOS_NO_CRITICOS = {
    "fianza_porcentaje",   # Panamá: 10/20/25 se lee del texto; Colombia: 40 fijo
    "minimo_porcentaje",   # se calcula o se lee del texto
    "fianza",              # se deriva de base * porcentaje
    "minimo",              # se deriva de base * porcentaje
    "codigo",              # se genera internamente
    "codigo_ubicacion",    # se mapea internamente
    "codigo_fuente",       # opcional
    "plano",               # secundario
    "superficie",          # secundario
    "expediente",          # a veces N/A en Panamá
}


def decidir(confianza: dict, faltantes: list[str], validacion: dict, discrepancia_valores: bool,
            fianza_asumida_por_regla: bool = False) -> dict:
    """
    'validacion' viene de validation.evaluar_duplicado_o_republicacion().

    Devuelve:
      { "decision": "auto_aprobado" | "esperando_aprobacion",
        "motivo": str, "confianza_promedio": float }

    Nota: "republicacion_legal" YA NO detiene la subida -- la nueva ocurrencia
    sigue el flujo normal de confianza (puede auto-aprobarse o no, igual que
    cualquier aviso nuevo). Lo único especial es que el orquestador marca la
    ocurrencia ANTERIOR como reemplazada, en vez de dejarla como vigente.
    """
    confianza_relevante = {
        k: _a_float_seguro(v) for k, v in confianza.items()
        if k not in CAMPOS_DERIVADOS
    }
    valores = [v for v in confianza_relevante.values() if v is not None]
    promedio = sum(valores) / len(valores) if valores else 0.0

    if validacion["tipo"] == "duplicado_sospechoso":
        return {
            "decision": "esperando_aprobacion",
            "motivo": f"Posible duplicado con inconsistencias: {validacion['detalle']}",
            "confianza_promedio": round(promedio, 3),
        }

    if discrepancia_valores:
        return {
            "decision": "esperando_aprobacion",
            "motivo": "El porcentaje o monto de fianza/mínimo no coincide con los valores legales esperados.",
            "confianza_promedio": round(promedio, 3),
        }

    # NOTA: el cliente confirmó que la fianza de Colombia es SIEMPRE 40% (no
    # varía como en Panamá), así que cuando se asume por regla ya no se
    # bloquea la auto-aprobación por eso -- pero el flag queda guardado en
    # el aviso (fianza_asumida_por_regla) para que sea auditable si el
    # cliente llegara a corregir esta regla más adelante.

    # Filtrar faltantes: solo bloquear si faltan campos CRÍTICOS (no los no-críticos)
    faltantes_criticos = [f for f in faltantes if f not in CAMPOS_NO_CRITICOS]
    if faltantes_criticos:
        return {
            "decision": "esperando_aprobacion",
            "motivo": f"Campos fundamentales faltantes: {', '.join(faltantes_criticos)}",
            "confianza_promedio": round(promedio, 3),
        }

    # Para el cálculo de umbral, ignorar campos no-críticos
    confianza_critica = {k: v for k, v in confianza_relevante.items()
                         if k not in CAMPOS_NO_CRITICOS and v is not None}
    valores_criticos = list(confianza_critica.values())
    promedio_critico = sum(valores_criticos) / len(valores_criticos) if valores_criticos else promedio

    if promedio_critico < UMBRAL_CONFIANZA:
        campos_bajos = [k for k, v in confianza_critica.items() if v < UMBRAL_CONFIANZA]
        return {
            "decision": "esperando_aprobacion",
            "motivo": f"Confianza por debajo del umbral ({promedio_critico:.2f} < {UMBRAL_CONFIANZA}) en campos críticos: {', '.join(campos_bajos)}",
            "confianza_promedio": round(promedio, 3),
        }

    return {
        "decision": "auto_aprobado",
        "motivo": f"Todos los campos críticos superan el umbral de confianza ({promedio_critico:.2f} >= {UMBRAL_CONFIANZA}).",
        "confianza_promedio": round(promedio, 3),
    }
