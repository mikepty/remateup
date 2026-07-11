"""
Agente de Validación (Validation Agent).

Rediseño basado en el docx del cliente ("Publicaciones repetidas" y
"Multiples bienes en un solo remate"):

1. Un mismo expediente puede tener VARIOS bienes -- se identifican por
   expediente + (lote/casa, finca/matrícula o descripción), NO solo por
   expediente, para no confundir varios bienes del mismo demandado.

2. Por ley, un mismo aviso se publica repetido hasta 3 días seguidos. El
   cliente pidió EXPLÍCITAMENTE: quedarse con la ÚLTIMA de las publicaciones
   repetidas como la versión válida a subir -- no la primera. Esto es porque
   la última suele ser la más confiable/actualizada, y porque el flujo del
   periódico a veces corrige pequeños detalles entre ediciones.

   Implementación: cuando llega una nueva ocurrencia del mismo bien dentro de
   la ventana legal de 3 días, la ocurrencia ANTERIOR se marca como
   "reemplazado_por_republicacion" (se retira de subida si ya se había
   subido automáticamente) y la NUEVA ocurrencia sigue el flujo normal de
   confianza -- se convierte en la candidata vigente a subir.

3. Un "duplicado sospechoso" real es cuando el mismo bien aparece con datos
   que NO deberían diferir entre republicaciones (ej. valor base distinto),
   lo cual sí amerita revisión humana en vez de reemplazo automático.
"""
from ..models import Aviso
from ..config import CAMPOS_REQUERIDOS, VENTANA_REPUBLICACION_DIAS


def _normalizar(texto) -> str:
    if not texto:
        return ""
    return str(texto).strip().upper()


def _identificador_bien(datos: dict) -> str:
    """Identifica el BIEN específico dentro de un expediente, no el caso completo."""
    expediente = _normalizar(datos.get("expediente"))
    identificador_especifico = (
        _normalizar(datos.get("lote_casa"))
        or _normalizar(datos.get("finca_matr"))
        or _normalizar(datos.get("descripcion"))[:60]
    )
    return f"{expediente}::{identificador_especifico}"


def evaluar_duplicado_o_republicacion(db, datos: dict) -> dict:
    """
    Devuelve uno de:
      {"tipo": "nuevo"}
      {"tipo": "republicacion_legal", "aviso_a_reemplazar_id": int}
          -> hay una ocurrencia anterior del mismo bien, dentro de la ventana
             legal, con los mismos valores -- esta nueva ocurrencia la
             reemplaza como versión vigente (el cliente pidió quedarse con
             la última).
      {"tipo": "duplicado_sospechoso", "detalle": str}
          -> mismo bien pero datos inconsistentes entre publicaciones
             (ej. valor base distinto) -- requiere revisión humana.
    """
    if not datos.get("expediente"):
        return {"tipo": "nuevo"}

    identificador = _identificador_bien(datos)
    candidatos = db.query(Aviso).filter(Aviso.expediente == datos.get("expediente")).all()

    for existente in candidatos:
        if existente.estado == "reemplazado_por_republicacion":
            continue  # ya fue superado por una republicación más nueva, ignorar

        id_existente = _identificador_bien({
            "expediente": existente.expediente,
            "lote_casa": existente.lote_casa,
            "finca_matr": existente.finca_matr,
            "descripcion": existente.descripcion,
        })
        if id_existente != identificador:
            continue  # bien distinto del mismo expediente -> no es duplicado

        mismo_valor_base = _normalizar(existente.base) == _normalizar(datos.get("base"))

        if mismo_valor_base:
            # Republicación legal esperada -- esta nueva ocurrencia reemplaza a la anterior.
            return {"tipo": "republicacion_legal", "aviso_a_reemplazar_id": existente.id}

        return {
            "tipo": "duplicado_sospechoso",
            "detalle": f"El bien ya existe (aviso #{existente.id}) pero con un valor base distinto "
                       f"({existente.base} vs {datos.get('base')}). Podría ser un error de lectura "
                       f"o un cambio real -- requiere confirmación.",
        }

    return {"tipo": "nuevo"}


def campos_faltantes(datos: dict) -> list[str]:
    """Solo marca como faltantes los campos FUNDAMENTALES que realmente
    son críticos para subir a la plataforma. Secundarios no bloquean."""
    faltantes = []
    for c in CAMPOS_REQUERIDOS:
        val = datos.get(c)
        if val is None or (isinstance(val, str) and val.strip() == ""):
            faltantes.append(c)
    return faltantes
