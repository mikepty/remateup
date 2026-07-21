"""
Agente de Reglas de Negocio (Business Rules Agent).

Basado en "INFORMACION_EXTRA_SOLICITADA.docx" del cliente (fuente oficial):

- Categorías: CASA=1, APARTAMENTO=2, TERRENO=3, VEHICULO=4, MISCELANEO=5.
- Provincias/departamentos: numeración continua Panamá (1-10) + Colombia (11-43).
- Fianza y mínimo NO son porcentajes fijos por país -- el aviso indica el
  porcentaje aplicable, dentro de un conjunto de valores legales posibles:
    Panamá:   fianza 10/20/25% -- mínimo 66.67% (2/3), 50% o 100% de la base
    Colombia: fianza 40% fijo  -- mínimo 70%, 50% o 100% de la base
  El sistema calcula el monto (fianza/mínimo) a partir de base + porcentaje,
  y valida que el porcentaje leído esté dentro del conjunto permitido.
"""
from ..config import (
    CODIGOS_PROVINCIA_PA, CODIGOS_DEPARTAMENTO_CO, CODIGOS_CATEGORIA,
    PORCENTAJES_FIANZA_VALIDOS_PA, PORCENTAJES_MINIMO_VALIDOS_PA,
    PORCENTAJES_FIANZA_VALIDOS_CO, PORCENTAJES_MINIMO_VALIDOS_CO,
    TOLERANCIA_PORCENTAJE,
)

# Campos que el sistema genera/deriva, no que se extraen tal cual del documento.
# Se excluyen del cálculo de confianza promedio en confidence.py.
CAMPOS_DERIVADOS = ["codigo", "codigo_ubicacion", "codigo_prensa"]


def _normalizar(texto) -> str:
    if not texto:
        return ""
    return str(texto).strip().upper().replace("Á", "A").replace("É", "E") \
        .replace("Í", "I").replace("Ó", "O").replace("Ú", "U")


def _generar_codigo_interno(datos: dict) -> str:
    """Genera codigo secuencial: PA64103XXX para Panama, CO64104XXX para Colombia."""
    from sqlalchemy import func
    from ..database import SessionLocal
    from ..models import Aviso

    prefijo = "PA" if datos.get("pais") == 1 else "CO"
    db = SessionLocal()

    # Contar avisos existentes de este pais para generar siguiente secuencial
    if datos.get("pais") == 1:
        # Panama: PA64103000 en adelante
        base_num = 64103000
        count = db.query(func.count(Aviso.id)).filter(Aviso.pais == 1).scalar() or 0
    else:
        # Colombia: CO64104000 en adelante
        base_num = 64104000
        count = db.query(func.count(Aviso.id)).filter(Aviso.pais == 2).scalar() or 0

    db.close()

    secuencial = base_num + count + 1
    return f"{prefijo}{secuencial}"


def _a_numero(valor) -> float | None:
    if valor is None:
        return None
    try:
        return float(str(valor).strip().replace(",", "").replace("$", "").replace("%", ""))
    except (ValueError, TypeError):
        return None


def _calcular_y_validar_valores(datos: dict) -> dict:
    """
    Calcula fianza/mínimo en dinero a partir de base + porcentaje, y valida
    que el porcentaje leído sea uno de los legalmente posibles para el país.
    """
    base = _a_numero(datos.get("base"))
    fianza_pct = _a_numero(datos.get("fianza_porcentaje"))
    minimo_pct = _a_numero(datos.get("minimo_porcentaje"))
    pais = datos.get("pais")
    discrepancias = []

    if base is None:
        return {"tiene_discrepancia": False, "detalle": [],
                "fianza_calculada": None, "minimo_calculado": None,
                "fianza_porcentaje_resuelto": fianza_pct,
                "fianza_asumida_por_regla": False}

    fianzas_validas = PORCENTAJES_FIANZA_VALIDOS_PA if pais == 1 else PORCENTAJES_FIANZA_VALIDOS_CO
    minimos_validos = PORCENTAJES_MINIMO_VALIDOS_PA if pais == 1 else PORCENTAJES_MINIMO_VALIDOS_CO

    fianza_calculada = None
    minimo_calculado = None
    fianza_asumida_por_regla = False

    # Colombia: la fianza es 40% FIJO según el docx del cliente ("colombia 40%
    # del valor base" -- a diferencia del mínimo, que sí varía según lo que
    # ordene el juez). Si el OCR no lo encontró en el texto, se aplica la
    # regla directamente en vez de forzar una aprobación innecesaria por un
    # dato que ya se sabe de antemano. Queda marcado como "asumido por regla"
    # para que sea auditable -- no se pierde de vista que no vino del documento.
    if pais == 2 and fianza_pct is None:
        fianza_pct = PORCENTAJES_FIANZA_VALIDOS_CO[0]  # 40
        fianza_asumida_por_regla = True

    if fianza_pct is not None:
        if min(abs(fianza_pct - v) for v in fianzas_validas) > TOLERANCIA_PORCENTAJE:
            discrepancias.append(
                f"fianza_porcentaje leído ({fianza_pct}%) no está entre los valores válidos {fianzas_validas} "
                f"para {'Panamá' if pais == 1 else 'Colombia'} -- posible error de lectura.")
        else:
            fianza_calculada = round(base * fianza_pct / 100, 2)
    else:
        discrepancias.append("No se pudo leer el porcentaje de fianza del aviso.")

    if minimo_pct is not None:
        if min(abs(minimo_pct - v) for v in minimos_validos) > TOLERANCIA_PORCENTAJE:
            discrepancias.append(
                f"minimo_porcentaje leído ({minimo_pct}%) no está entre los valores válidos {minimos_validos} "
                f"para {'Panamá' if pais == 1 else 'Colombia'} -- posible error de lectura.")
        else:
            minimo_calculado = round(base * minimo_pct / 100, 2)
    else:
        discrepancias.append("No se pudo leer el porcentaje mínimo del aviso.")

    fianza_impresa = _a_numero(datos.get("fianza"))
    minimo_impreso = _a_numero(datos.get("minimo"))
    if fianza_impresa and fianza_calculada and abs(fianza_impresa - fianza_calculada) / base > 0.03:
        discrepancias.append(
            f"El monto de fianza impreso ({fianza_impresa}) no coincide con el calculado ({fianza_calculada}).")
    if minimo_impreso and minimo_calculado and abs(minimo_impreso - minimo_calculado) / base > 0.03:
        discrepancias.append(
            f"El monto mínimo impreso ({minimo_impreso}) no coincide con el calculado ({minimo_calculado}).")

    return {
        "tiene_discrepancia": len(discrepancias) > 0,
        "detalle": discrepancias,
        "fianza_calculada": fianza_calculada if fianza_calculada is not None else fianza_impresa,
        "minimo_calculado": minimo_calculado if minimo_calculado is not None else minimo_impreso,
        "fianza_porcentaje_resuelto": fianza_pct,
        "fianza_asumida_por_regla": fianza_asumida_por_regla,
    }


def _generar_codigo_prensa(datos: dict) -> str | None:
    """Genera el código de prensa si tenemos suficiente información.
    Formato: SIGLA-YYYY-MM-DD-PXX
    Siglas: LP (La Prensa), ML (Metro Libre), LE (La Estrella), SEJ (Colombia).
    Si no podemos determinar la sigla, usamos la del país por defecto."""
    pais = datos.get("pais")
    codigo_fuente = datos.get("codigo_fuente")

    # Si ya hay un codigo_fuente del OCR que parece tener formato de prensa, usarlo
    if codigo_fuente and any(s in str(codigo_fuente).upper() for s in ["LP", "ML", "LE", "SEJ"]):
        return codigo_fuente

    # Para Colombia, la sigla es siempre SEJ
    if pais == 2:
        sigla = "SEJ"
    elif pais == 1:
        # Para Panamá, sin más datos asumimos LP (La Prensa) como default
        sigla = "LP"
    else:
        return None

    return None  # Si no tenemos fecha de periódico ni página, dejar null para completar manual


# La descripción de PORTADA debe ser un resumen corto; el detalle largo va en
# descripcion_completa. Si la IA devuelve una portada larga, se corrige aquí
# de forma determinista (sin volver a llamar a la IA).
LARGO_MAX_DESCRIPCION_PORTADA = 220


def _resumir_descripcion_portada(datos: dict) -> None:
    desc = str(datos.get("descripcion") or "").strip()
    if len(desc) <= LARGO_MAX_DESCRIPCION_PORTADA:
        return
    # Preservar el texto largo como descripción completa si no vino aparte
    if not str(datos.get("descripcion_completa") or "").strip():
        datos["descripcion_completa"] = desc
    # Cortar en un límite natural (antes de linderos/medidas si aparecen)
    desc_u = desc.upper()
    corte = len(desc)
    for marca in ("LINDEROS", "PARTIENDO DE", "CON UNA SUPERFICIE", "MIDE UNA DISTANCIA"):
        i = desc_u.find(marca)
        if i != -1:
            corte = min(corte, i)
    resumen = desc[:min(corte, LARGO_MAX_DESCRIPCION_PORTADA)].rstrip(" ,.;:-")
    # No cortar a media palabra
    if len(resumen) == LARGO_MAX_DESCRIPCION_PORTADA and " " in resumen:
        resumen = resumen[:resumen.rfind(" ")].rstrip(" ,.;:-")
    datos["descripcion"] = resumen


def aplicar_reglas(datos: dict) -> dict:
    """Recibe el dict de datos extraídos y le agrega/corrige campos codificados."""
    datos = dict(datos)  # copia, no mutar el original

    _resumir_descripcion_portada(datos)

    pais = datos.get("pais")
    provincia_raw = _normalizar(datos.get("provincia") or "")
    categoria_raw = _normalizar(datos.get("categoria") or "")

    if pais == 1:
        datos["codigo_ubicacion"] = CODIGOS_PROVINCIA_PA.get(provincia_raw)
    elif pais == 2:
        datos["codigo_ubicacion"] = CODIGOS_DEPARTAMENTO_CO.get(provincia_raw)

    # Si contiene "cuota parte" en la descripcion o categoria, es miscelaneo (5)
    desc_raw = _normalizar(datos.get("descripcion") or "")
    if "CUOTA PARTE" in categoria_raw or "CUOTA PARTE" in desc_raw or "CUOTAS PARTES" in desc_raw:
        datos["categoria_codigo"] = 5
        datos["categoria"] = "MISCELANEO"
    else:
        datos["categoria_codigo"] = CODIGOS_CATEGORIA.get(categoria_raw)

    # SIEMPRE generar código interno (PA64103XXX / CO64104XXX)
    # Gemini puede extraer un código del periódico (ej. "810") pero nuestro sistema
    # usa su propio secuencial. El código del periódico va en codigo_fuente si aplica.
    if datos.get("codigo") and not str(datos["codigo"]).startswith(("PA", "CO")):
        # Si Gemini extrajo un código del periódico, guardarlo en codigo_fuente
        if not datos.get("codigo_fuente"):
            datos["codigo_fuente"] = str(datos["codigo"])
    datos["codigo"] = _generar_codigo_interno(datos)

    # Generar codigo_prensa si no fue extraído directamente
    if not datos.get("codigo_prensa"):
        datos["codigo_prensa"] = _generar_codigo_prensa(datos)

    validacion = _calcular_y_validar_valores(datos)
    datos["fianza"] = validacion["fianza_calculada"]
    datos["minimo"] = validacion["minimo_calculado"]
    # Si se asumió el 40% de Colombia por regla (no vino del OCR), se refleja
    # aquí para que "campos_faltantes" no lo marque como ausente -- pero queda
    # visible en "_fianza_asumida_por_regla" para que se sepa que no vino leído.
    datos["fianza_porcentaje"] = validacion["fianza_porcentaje_resuelto"]
    datos["_fianza_asumida_por_regla"] = validacion["fianza_asumida_por_regla"]
    datos["_discrepancia_valores"] = validacion["tiene_discrepancia"]
    datos["_detalle_discrepancia_valores"] = validacion["detalle"]

    return datos
