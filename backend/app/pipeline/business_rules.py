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
CAMPOS_DERIVADOS = ["codigo", "codigo_ubicacion", "codigo_prensa", "prevista"]


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


_MESES_ES = {
    1: "ENE", 2: "FEB", 3: "MAR", 4: "ABR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AGO", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DIC",
}

# Siglas oficiales por periódico (regla del cliente). Colombia usa siempre
# SEJ porque solo tiene una fuente semanal (el boletín SEJURE).
_SIGLAS_PERIODICO = {
    "LA PRENSA": "LP",
    "METRO LIBRE": "ML",
    "LA ESTRELLA": "LE",
}


def _sigla_desde_periodico(periodico, pais) -> str | None:
    if pais == 2:
        return "SEJ"
    if not periodico:
        return None
    p = _normalizar(periodico)
    if p in ("LP", "ML", "LE"):
        return p
    for nombre, sigla in _SIGLAS_PERIODICO.items():
        if nombre in p:
            return sigla
    return None


def _formatear_fecha_prensa(fecha_prensa) -> str | None:
    """fecha_prensa viene en formato YYYY-MM-DD (así lo pide el prompt).
    Devuelve DDMESAAAA en español, mayúsculas y sin acentos (ej. "08JUL2026"),
    que es el formato que usa el cliente en el código de prensa."""
    if not fecha_prensa:
        return None
    import re as _re
    m = _re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", str(fecha_prensa).strip())
    if not m:
        return None
    anio, mes, dia = int(m.group(1)), int(m.group(2)), int(m.group(3))
    mes_txt = _MESES_ES.get(mes)
    if not mes_txt:
        return None
    return f"{dia:02d}{mes_txt}{anio}"


def _generar_codigo_prensa(datos: dict) -> str | None:
    """Genera el código de prensa con el formato REAL pedido por el cliente:
    INICIAL + DD + MES(3 letras) + AAAA + PÁGINA (tal cual impresa), sin
    separadores. Ej: La Estrella, 8 de julio de 2026, página 1C -> "LE08JUL20261C".

    Se construye a partir de periodico + fecha_prensa + pagina_prensa, que el
    modelo lee directamente del encabezado/pie de la página (NO del cuerpo del
    aviso). Si falta alguno de los tres, se deja en null para completarlo a
    mano en el panel -- no se inventa ni se asume un periódico por defecto."""
    pais = datos.get("pais")
    sigla = _sigla_desde_periodico(datos.get("periodico"), pais) or datos.get("_sigla_periodico")
    fecha_fmt = _formatear_fecha_prensa(datos.get("fecha_prensa"))
    pagina = str(datos.get("pagina_prensa") or "").strip().upper()

    if sigla and fecha_fmt and pagina:
        return f"{sigla}{fecha_fmt}{pagina}"

    # Fallback legado: avisos de antes de este cambio pudieron traer un
    # codigo_fuente con pinta de código de prensa; se respeta si existe.
    codigo_fuente = datos.get("codigo_fuente")
    if codigo_fuente and any(s in str(codigo_fuente).upper() for s in ["LP", "ML", "LE", "SEJ"]):
        return codigo_fuente

    return None  # Datos insuficientes: mejor null que un código inventado


# La descripción de PORTADA debe ser un resumen legible (regla del cliente: máx
# 30 palabras); el detalle largo va en descripcion_completa. Si la IA devuelve
# una portada larga, se corrige aquí de forma determinista (sin volver a
# llamar a la IA), aplicando el tope de PALABRAS como regla principal y el de
# caracteres como red de seguridad adicional.
LARGO_MAX_DESCRIPCION_PORTADA = 350
MAX_PALABRAS_DESCRIPCION_PORTADA = 30


def _resumir_descripcion_portada(datos: dict) -> None:
    desc = str(datos.get("descripcion") or "").strip()
    if not desc:
        return
    excede_palabras = len(desc.split()) > MAX_PALABRAS_DESCRIPCION_PORTADA
    excede_chars = len(desc) > LARGO_MAX_DESCRIPCION_PORTADA
    if not excede_palabras and not excede_chars:
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
    recortado = desc[:corte].rstrip(" ,.;:-")
    # Regla principal del cliente: máximo 30 palabras
    palabras = recortado.split()
    if len(palabras) > MAX_PALABRAS_DESCRIPCION_PORTADA:
        recortado = " ".join(palabras[:MAX_PALABRAS_DESCRIPCION_PORTADA])
    # Red de seguridad adicional: tope de caracteres solo si aún excede después del corte de palabras
    if len(recortado) > LARGO_MAX_DESCRIPCION_PORTADA:
        palabras_finales = recortado.split()
        # Reducir palabra por palabra hasta que quepa
        while palabras_finales and len(" ".join(palabras_finales)) > LARGO_MAX_DESCRIPCION_PORTADA:
            palabras_finales.pop()
        recortado = " ".join(palabras_finales) if palabras_finales else recortado[:LARGO_MAX_DESCRIPCION_PORTADA].rsplit(" ", 1)[0]
    datos["descripcion"] = recortado.rstrip(" ,.;:-")


def _generar_prevista(datos: dict) -> str | None:
    """Ubicación limpia para Google Maps del inmueble (aproximada si el aviso
    solo da la zona). Si el modelo ya la extrajo, se respeta. Si no, se arma a
    partir de la descripción completa primero (tiene más contexto), luego
    descripción corta + provincia."""
    prevista = str(datos.get("prevista") or "").strip()
    if prevista and len(prevista) > 10:
        return prevista

    # Estrategia mejorada: buscar ubicación en descripcion_completa primero
    desc_completa = str(datos.get("descripcion_completa") or "").strip()
    if desc_completa:
        # Buscar patrones de ubicación común en Panamá
        import re
        # Patrón: Corr: XXX, Dist: XXX, Prov: XXX
        match_ubicacion = re.search(
            r'(?:Corr(?:egimiento)?|Distrito|Dist)[:\s]+([A-Za-zÁÉÍÓÚáéíóúÑñ\s]+?)(?:,|\.|\s+Dist|\s+Prov)',
            desc_completa, re.IGNORECASE
        )
        if match_ubicacion:
            ubicacion = match_ubicacion.group(1).strip()
            provincia = str(datos.get("provincia") or "").strip()
            if provincia:
                return f"{ubicacion}, {provincia}"
            return ubicacion
        
        # Patrón: lote/finca con ubicación (ej: "LOTE 212, Arraiján")
        match_lote = re.search(
            r'(?:LOTE|FINCA|APARTAMENTO|CASA)[^,\.]+,\s*([A-Za-zÁÉÍÓÚáéíóúÑñ\s]+?)(?:,|\.|\s+PANAM)',
            desc_completa, re.IGNORECASE
        )
        if match_lote:
            ubicacion = match_lote.group(1).strip()
            if len(ubicacion) > 3 and len(ubicacion) < 40:
                provincia = str(datos.get("provincia") or "").strip()
                if provincia:
                    return f"{ubicacion}, {provincia}"
                return ubicacion

    # Fallback: descripción corta + provincia
    partes = []
    desc = str(datos.get("descripcion") or "").strip()
    if desc and len(desc) <= 150:
        partes.append(desc)
    provincia = str(datos.get("provincia") or "").strip()
    if provincia:
        partes.append(provincia)
    if not partes:
        lugar = str(datos.get("lugar") or "").strip()
        if lugar:
            # 'lugar' casi siempre es el JUZGADO, no la ubicación del bien:
            # solo se usa como último recurso y solo si menciona una zona.
            if any(z in lugar.upper() for z in ("ARRAIJAN", "PANAMA", "COLON", "CHIRIQUI",
                                                 "VERAGUAS", "HERRERA", "LOS SANTOS", "COCLE",
                                                 "BOCAS", "DAVID", "LA CHORRERA")):
                partes.append(lugar)
    return ", ".join(partes) if partes else None


def aplicar_reglas(datos: dict) -> dict:
    """Recibe el dict de datos extraídos y le agrega/corrige campos codificados."""
    datos = dict(datos)  # copia, no mutar el original

    # Limpiar marcadores de límite de documento en descripciones
    for campo in ("descripcion", "descripcion_completa"):
        texto = str(datos.get(campo) or "").strip()
        if "LIMITE_DOCUMENTO" in texto:
            # Remover todo desde >>> hasta <<< inclusive
            import re
            texto = re.sub(r'>>>.*?LIMITE_DOCUMENTO.*?<<<', '', texto, flags=re.DOTALL)
            # Limpiar espacios múltiples resultantes
            texto = re.sub(r'\s+', ' ', texto).strip()
            datos[campo] = texto

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
    desc_completa_raw = _normalizar(datos.get("descripcion_completa") or "")
    proceso_raw = _normalizar(datos.get("proceso") or "")
    if ("CUOTA PARTE" in categoria_raw or "CUOTA PARTE" in desc_raw
            or "CUOTAS PARTES" in desc_raw or "CUOTAS PARTES" in desc_completa_raw
            or "CUOTAS PARTES" in proceso_raw):
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

    # Ubicación para Google Maps: respaldo determinista si el modelo no la dio
    prevista = _generar_prevista(datos)
    if prevista:
        datos["prevista"] = prevista

    validacion = _calcular_y_validar_valores(datos)
    datos["fianza"] = validacion["fianza_calculada"]
    datos["minimo"] = validacion["minimo_calculado"]
    # Si el validador resolvió un porcentaje (ej. 40% fijo Colombia), propagarlo
    if validacion.get("fianza_porcentaje_resuelto") is not None:
        if datos.get("fianza_porcentaje") in (None, "", "null"):
            datos["fianza_porcentaje"] = validacion["fianza_porcentaje_resuelto"]
    datos["_fianza_asumida_por_regla"] = validacion["fianza_asumida_por_regla"]
    datos["_discrepancia_valores"] = validacion["tiene_discrepancia"]
    datos["_detalle_discrepancia_valores"] = validacion["detalle"]
    fianza_asumida_fallback = False
    minimo_asumido_fallback = False

    # Forzar cálculo con valores por defecto si falta pero hay base (backup agresivo)
    base_num = _a_numero(datos.get("base"))
    if base_num and base_num > 500:  # Base válida detectada
        # Minimo: si falta, usar porcentaje si existe, sino asumir 66.67% (2/3 es el más común PA)
        if not datos.get("minimo"):
            minimo_pct = _a_numero(datos.get("minimo_porcentaje"))
            if not minimo_pct and pais == 1:
                minimo_pct = 66.67  # Panamá: 2/3 es el más común
                datos["minimo_porcentaje"] = minimo_pct
                minimo_asumido_fallback = True
            elif not minimo_pct and pais == 2:
                minimo_pct = 70.0  # Colombia: 70% es el más común
                datos["minimo_porcentaje"] = minimo_pct
                minimo_asumido_fallback = True
            if minimo_pct:
                datos["minimo"] = round(base_num * minimo_pct / 100, 2)
        
        # Fianza: si falta, usar porcentaje si existe, sino asumir 10% (el más común PA) o 40% (CO fijo)
        if not datos.get("fianza"):
            fianza_pct = _a_numero(datos.get("fianza_porcentaje"))
            if not fianza_pct and pais == 1:
                fianza_pct = 10.0  # Panamá: 10% es el más común
                datos["fianza_porcentaje"] = fianza_pct
                fianza_asumida_fallback = True
            elif not fianza_pct and pais == 2:
                fianza_pct = 40.0  # Colombia: 40% fijo
                datos["fianza_porcentaje"] = fianza_pct
                datos["_fianza_asumida_por_regla"] = True
            if fianza_pct:
                datos["fianza"] = round(base_num * fianza_pct / 100, 2)

    # Si se asumió porcentaje por regla (40% CO o fallback PA), limpiar la
    # discrepancia relacionada: el campo no viene del OCR, pero el cálculo
    # es correcto y auditado. Mantener la discrepancia solo si el porcentaje
    # leído viene de OCR y no es válido.
    if fianza_asumida_fallback or minimo_asumido_fallback:
        detalle_filtrado = [
            d for d in datos.get("_detalle_discrepancia_valores", [])
            if "No se pudo leer el porcentaje" not in d
        ]
        datos["_detalle_discrepancia_valores"] = detalle_filtrado
        if not detalle_filtrado:
            datos["_discrepancia_valores"] = False

    return datos
