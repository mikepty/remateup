"""
Orchestrator: coordina el flujo completo, paso a paso, de forma lineal y explícita.
"""
import json
import re
from sqlalchemy.orm import Session
from ..models import Documento, Aviso
from . import extraction, business_rules, validation, confidence, audit, extractor_deterministico
from ..whatsapp.notifier import enviar_solicitud_aprobacion
from ..upload.platform_uploader import subir_a_plataforma


def _sigla_periodico_de_archivo(nombre_archivo: str) -> str | None:
    """Detecta la sigla del periódico (LP/ML/LE) a partir del nombre de archivo
    que el cliente sube (ej. "LE 1c 8 julio 26 header.jpg" -> "LE")."""
    if not nombre_archivo:
        return None
    m = re.match(r"\s*(LP|ML|LE)\b", nombre_archivo.upper())
    return m.group(1) if m else None


# Cabecera del periódico impresa en la hoja. La Estrella imprime:
#   "La Estrella, Panamá, miércoles 8 de julio de 2026"   (nombre primero)
# o bien:
#   "MIÉRCOLES 8 DE JULIO DE 2026 LA ESTRELLA DE PANAMA"  (fecha primero,
#    nombre al final). El modelo a veces no la lee como tal (quedó a mitad del
#    texto OCR): aquí se detecta de forma determinista para completar
#    periodico/fecha_prensa y poder generar el codigo_prensa (regla del
#    cliente: INICIAL+DDMESAAAA+PÁGINA).
_RE_CABECERA_PERIODICO = re.compile(
    r"(?:"
    r"(?P<p1>La Prensa|La Estrella|Metro Libre)\s*,?\s*Panam[áa]?\s*,?\s*"
    r"(?:lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo)\s+"
    r"(?P<d1>\d{1,2})\s+de\s+(?P<m1>enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre)\s+de\s+(?P<a1>\d{4})"
    r"|"
    r"(?:lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo)\s+"
    r"(?P<d2>\d{1,2})\s+de\s+(?P<m2>enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre)\s+de\s+(?P<a2>\d{4})\s*"
    r"(?P<p2>La Prensa|La Estrella|Metro Libre)"
    r")",
    re.IGNORECASE,
)
_MESES_A_NUMERO = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11,
    "diciembre": 12,
}


def _cabecera_periodico_desde_ocr(texto_ocr: str) -> tuple[str, str] | None:
    """Devuelve (periodico, fecha_prensa YYYY-MM-DD) si la cabecera del diario
    está impresa en el texto OCR (nombre primero O fecha primero)."""
    if not texto_ocr:
        return None
    m = _RE_CABECERA_PERIODICO.search(texto_ocr)
    if not m:
        return None
    if m.group("p1"):
        periodico, dia, mes, anio = m.group("p1"), m.group("d1"), m.group("m1"), m.group("a1")
    else:
        periodico, dia, mes, anio = m.group("p2"), m.group("d2"), m.group("m2"), m.group("a2")
    return periodico, f"{anio}-{_MESES_A_NUMERO[mes.lower()]:02d}-{int(dia):02d}"


def _pagina_prensa_desde_ocr(texto_ocr: str) -> str | None:
    """Código de página impreso en la esquina superior de la hoja (ej. "6B").
    Suele aparecer en las primeras líneas del texto OCR de la foto superior.
    El OCR a veces lee "1C" como "IC": se normaliza la I inicial a 1."""
    if not texto_ocr:
        return None
    inicio = texto_ocr[:2000]
    m = re.search(r"(?m)^\s*([0-9I][A-Za-z]{1,2})\s*$", inicio)
    if not m:
        return None
    pag = m.group(1).upper()
    if pag.startswith("I") and pag[1:].isalpha():
        pag = "1" + pag[1:]
    return pag


def _ventana_aviso_ocr(texto_ocr: str, pos: int, antes: int = 2000, despues: int = 4000) -> str:
    """Recorta el texto alrededor de un expediente hasta el encabezado del
    SIGUIENTE aviso de remate, para que los patrones de monto no capten datos
    del aviso vecino cuando varios avisos quedan pegados en el mismo texto."""
    fin = min(len(texto_ocr), pos + despues)
    prox = texto_ocr.find("AVISO DE REMATE", pos + 1)
    if prox != -1:
        fin = min(fin, prox)
    return texto_ocr[max(0, pos - antes):fin]


def _buscar_fianza_minimo_en_ocr(datos: dict, texto_ocr: str, pais: int) -> dict:
    """Red de seguridad: si la IA no asoció fianza/minimo porcentaje, busca
    determinísticamente en el texto OCR usando patrones judiciales reales.
    
    Patrones comunes en Panamá:
    - "diez por ciento ( 10 % ) de la base del remate"
    - "el 10 % de la base del remate"
    - "consignar el diez ( 10 % ) de la base"
    - "VEINTICINCO POR CIENTO ( 25 % ) de la base"
    
    Para mínimo:
    - "las dos terceras ( 2/3 )" -> 66.67%
    - "la mitad" / "50%" -> 50%
    - "TOTALIDAD" / "100%" -> 100%
    """
    if not texto_ocr or not datos.get("expediente"):
        return {}
    
    expediente = str(datos.get("expediente") or "").strip()
    pos = texto_ocr.find(expediente)
    if pos == -1:
        solo_digitos = re.sub(r"\D", "", expediente)
        if len(solo_digitos) >= 5:
            pos = texto_ocr.find(solo_digitos)
        if pos == -1:
            return {}
    
    # The fianza/minimo info can appear BEFORE or AFTER the expediente in the
    # OCR text. Search a wide window covering both directions (up to 50k chars
    # total, bounded to the text).
    antes = 10000
    despues = 30000
    inicio = max(0, pos - antes)
    fin = min(len(texto_ocr), pos + despues)
    # Avoid crossing into another aviso
    prox = texto_ocr.find("AVISO DE REMATE", pos + 1)
    if prox != -1 and prox < fin:
        fin = prox
    # Also look for the previous AVISO DE REMATE to bound backwards
    prev = texto_ocr.rfind("AVISO DE REMATE", inicio)
    if prev != -1 and prev > inicio:
        inicio = prev + len("AVISO DE REMATE")
    
    ventana = texto_ocr[inicio:fin]
    
    resultados = {}
    
    # Fianza: buscar porcentajes legales válidos según país
    fianza_pct = None
    if pais == 2:
        porcentajes_fianza = {40}
    else:
        porcentajes_fianza = {10, 20, 25}
    
    # 1) "diez por ciento ( 10 % )" o "diez ( 10 % )" - formato judicial
    for m in re.finditer(
        r"\b(diez|veinte|veinticinco|cuarenta)?\s*(?:\(\s*)?(\d{1,2})\s*%\s*(?:\))?\s*de\s+(?:la\s+)?base\s+del\s+remate",
        ventana, re.IGNORECASE):
        v = int(m.group(2))
        if v in porcentajes_fianza:
            fianza_pct = float(v)
            break
    
    # 2) "el X % de la base" sin palabra
    if fianza_pct is None:
        for m in re.finditer(r"el\s+(\d{1,2})\s*%\s*de\s+la\s+base\s+del\s+remate", ventana, re.IGNORECASE):
            v = int(m.group(1))
            if v in porcentajes_fianza:
                fianza_pct = float(v)
                break
    
    # 3) Pattern general: cualquier X% que sea un valor legal de fianza
    if fianza_pct is None:
        for m in re.finditer(r"(\d{1,2})\s*%", ventana):
            v = int(m.group(1))
            if v in porcentajes_fianza:
                # Avoid false positive from interest rates like "1.75%"
                previo = ventana[max(0, m.start()-30):m.start()].upper()
                # Skip if preceded by interest/tasa context
                if any(k in previo for k in ("INTERÉS", "INTERES", "TASA", "EFECTIVA")):
                    continue
                fianza_pct = float(v)
                break
    
    if fianza_pct:
        resultados["fianza_porcentaje"] = fianza_pct
    
    # Mínimo: buscar patrones
    minimo_pct = None
    if "2/3" in ventana or "DOS TERCERAS" in ventana.upper():
        minimo_pct = 66.67
    elif "LA MITAD" in ventana.upper() or re.search(r"50\s*%", ventana):
        minimo_pct = 50.0
    elif "TOTALIDAD" in ventana.upper() or re.search(r"100\s*%", ventana):
        minimo_pct = 100.0
    else:
        m = re.search(r"(?:POSTURA\s+MINIMA|MINIMO|MINIMA)[^\d]{0,60}?(\d{1,3}(?:\.\d{1,2})?)\s*%",
                     ventana, re.IGNORECASE)
        if m:
            minimo_pct = float(m.group(1))
    
    if minimo_pct:
        resultados["minimo_porcentaje"] = minimo_pct
    
    return resultados


def _buscar_base_en_ocr(datos: dict, texto_ocr: str) -> float | None:
    """Red de seguridad: si la IA no asoció el monto (base) del aviso, se busca
    determinísticamente en el texto OCR DESPUÉS del expediente (el monto de un
    aviso siempre está en el cuerpo, después de su encabezado).

    Solo patrones específicos de la base del remate son confiables:
    - "la base del remate, es decir la suma de B/.X"
    - "servirá de base para el remate la cifra de B/.X"
    - "CUANTÍA DEL EMBARGO: ... (B/.X)"
    El patrón genérico B/.X es peligroso: el folio real dentro del aviso trae
    OTROS montos (valor del traspaso, hipoteca). Solo se usa si hay una palabra
    clave de base/cuantía dentro de los 80 chars anteriores Y no hay otro aviso
    entre el expediente y el monto."""
    base = datos.get("base")
    if base not in (None, "", "null"):
        return None
    expediente = str(datos.get("expediente") or "").strip()
    if not expediente or not texto_ocr:
        return None

    pos = texto_ocr.find(expediente)
    if pos == -1:
        # Probar solo con dígitos (el OCR intercala guiones/espacios)
        solo_digitos = re.sub(r"\D", "", expediente)
        if len(solo_digitos) >= 5:
            pos = texto_ocr.find(solo_digitos)
        if pos == -1:
            return None
    # La base suele estar lejos del encabezado (el folio va en medio); el corte
    # real lo da el siguiente "AVISO DE REMATE" dentro de _ventana_aviso_ocr.
    ventana = _ventana_aviso_ocr(texto_ocr, pos, antes=0, despues=15000)

    def _monto(grupo: str) -> float | None:
        """Convierte el grupo capturado a float, tolerando el punto final de
        frase que el patrón [\\d.,]+ suele capturar de más (\"5,800.00.\")."""
        s = grupo.replace(",", "").rstrip(".")
        try:
            return float(s)
        except ValueError:
            return None

    for patron in (
        r"la base del remate\s*,?\s*es decir\s+la\s+suma\s+de\s+"
        r"[B8]\s*/\s*\.\s*([\d.,]+)",
        r"base para el remate\s+la\s+cifra\s+de\s+"
        r"[B8]\s*/\s*\.\s*([\d.,]+)",
        r"base para el remate\s*,?\s*la\s+suma\s+de"
        r"[^)]{0,200}?\(?\s*[B8]?\s*/\s*\.\s*([\d.,]+)",
        r"CUANT[IÍ]A\s+DEL\s+EMBARGO\s*:.*?\(\s*[B8]\s*/\s*\.\s*([\d.,]+)\s*\)",
    ):
        m = re.search(patron, ventana, re.IGNORECASE)
        if m:
            return _monto(m.group(1))
    # Patrón genérico: solo con palabra clave de base cerca y sin otro aviso
    # entre el expediente y el monto (el folio trae "valor del traspaso",
    # hipotecas y otros B/. que NO son la base del remate).
    resto = texto_ocr[pos:pos + 4000]
    if "AVISO DE REMATE" in resto.upper().replace("AVISO DE REMATE", "", 1):
        return None
    m = re.search(r"[B8]\s*/\s*\.\s*([\d.,]{5,})", ventana)
    if m:
        previo = ventana[max(0, m.start() - 80):m.start()].upper()
        if not any(k in previo for k in ("BASE", "AVALU", "AVALÚ", "CIFRA",
                                         "SUMA", "CUANT", "EMBARGO", "REMATE")):
            return None
        valor = _monto(m.group(1))
        return valor if valor and 500.0 < valor < 1_000_000_000 else None
    return None


_MAPEO_CAMPOS_V2_A_BD = {
    "expediente": "expediente",
    "finca": "finca_matr",
    "precio_base": "base",
    "fecha_remate": "fecha",
    "demandante": "demandante",
    "demandado": "demandado",
    "descripcion": "descripcion",
    "descripcion_completa": "descripcion_completa",
    "hora": "hora",
    "lugar": "lugar",
    "proceso": "proceso",
    "categoria": "categoria",
    "provincia": "provincia",
    "plano": "plano",
    "superficie": "superficie",
    "prevista": "prevista",
    "lote_casa": "lote_casa",
    "email_observaciones": "email_observaciones",
}

_CAMPOS_V2_DESCARTABLES = {None, "", "null", ".", "..", "NOT_FOUND"}


def _base_valida(base) -> bool:
    """La base del remate debe ser un número de monto válido (>0 y <1e9).
    Rechaza valores basura que el OCR/parser puede colar ('.', '0', '1931'
    sin contexto, etc.)."""
    num = _normalizar_monto_pa(base)
    if num is None:
        return False
    # Una base de remate real en Panamá nunca es < 100 B/. (rechaza '10'
    # capturado del pie de página, etc.).
    return 100 <= num < 1_000_000_000


def _normalizar_monto_pa(valor) -> float | None:
    """Interpreta un monto panameño del OCR. La Estrella imprime B/.47,927.27
    pero el OCR suele colar puntos en vez de comas: 'B / 47.92727',
    '104.355.34', '1.200.00'. Reglas:
      - si hay coma y un único punto -> coma es miles, punto es decimal.
      - si hay más de un punto -> el último es decimal, los demás miles.
      - si hay un único punto con 3 dígitos decimales y entero de 1-3 dígitos
        (p.ej. '47.92727', '1.200') se trata como miles+decimales pegados.
      - el punto final de frase se tolera.
    """
    if valor in (None, "", "null", "."):
        return None
    s = str(valor).strip().replace(" ", "").replace("$", "").replace("B/", "").replace("B/.", "")
    s = s.rstrip(".")
    if not s:
        return None
    # Quitar la moneda B/. si quedó pegada al número
    import re as _re
    s = _re.sub(r"^[B8]/?\.?", "", s)
    if not _re.match(r"^[\d.,]+$", s):
        return None
    try:
        if "," in s and "." in s:
            # '47,927.27' -> 47927.27 ; '1,200.00' -> 1200.0
            if s.rindex(".") > s.rindex(","):
                entero = s.replace(",", "")
                return float(entero)
            entero = s.replace(".", "").replace(",", ".")
            return float(entero)
        if s.count(".") > 1:
            # '104.355.34' -> 104355.34 (último punto es decimal)
            partes = s.split(".")
            entero = "".join(partes[:-1])
            dec = partes[-1]
            return float(entero + "." + dec)
        if "," in s:
            return float(s.replace(",", ""))
        if "." in s:
            entero, dec = s.split(".")
            if len(dec) <= 2:
                # decimal real: '1529.03' -> 1529.03, '10.0' -> 10.0
                return float(s)
            if len(entero) <= 2 and len(dec) > 2:
                # OCR pegó miles+centavos: '47.92727' -> 47927.27
                digitos = s.replace(".", "")
                if len(digitos) >= 6:
                    glued = float(digitos[:-2] + "." + digitos[-2:])
                    if glued >= 100:
                        return glued
            # miles sin decimales: '1.200' -> 1200.0
            return float(s.replace(".", ""))
        return float(s)
    except ValueError:
        return None


def _buscar_base_v2_en_texto(texto: str) -> float | None:
    """Rescate determinista de la base del remate desde el texto OCR de un
    aviso (pipeline V2). Busca la mención 'base del remate' o 'servirá de
    base' seguida del monto, que suele venir entre paréntesis:
        '... servirá de base la suma de ... ( B/.47,927.27 )'
        '... SIRVE DE BASE DEL REMATE ... la suma de CUARENTA Y SIETE MIL
         NOVECIENTOS VEINTISIETE BALBOAS ... ( B / 47.92727 )'
    Devuelve el monto ya normalizado, o None si no encuentra ninguno válido.
    """
    if not texto:
        return None
    patrones = [
        # mención de base seguida (hasta ~500 car.) de un monto entre paréntesis
        r"(?:SIRVE\s+DE\s+BASE|BASE\s+DEL\s+REMATE|servir[aá]?\s+de\s+base)[^()]{0,500}?\(\s*[B8]?\s*/\s*\.?\s*([\d][\d.,]*)\s*\)",
        # mención de base + 'la suma de' + monto con moneda
        r"(?:SIRVE\s+DE\s+BASE|BASE\s+DEL\s+REMATE|servir[aá]?\s+de\s+base)[^()]{0,500}?la\s+suma\s+de\s+[^()]{0,200}?([B8]?\s*/\s*\.?\s*[\d][\d.,]*)",
    ]
    for patron in patrones:
        m = re.search(patron, texto, re.IGNORECASE | re.DOTALL)
        if m:
            monto = _normalizar_monto_pa(m.group(1))
            if monto is not None:
                return monto
    # Fallback: el aviso mezcla columnas y el monto queda lejos de la mención
    # 'base'. Buscar cualquier monto con moneda B/. (p.ej. '( B / . 104.355.34 )')
    # y quedarnos con el mayor (la base de remate es el valor más alto).
    mejores = []
    for m in re.finditer(
        r"\(\s*[B8]?\s*/\s*[^)\d]{0,60}?([\d][\d.,]*)\s*\)",
        texto, re.IGNORECASE | re.DOTALL):
        monto = _normalizar_monto_pa(m.group(1))
        if monto is not None and monto >= 100:
            mejores.append(monto)
    if mejores:
        return max(mejores)
    return None


def _normalizar_fecha_remate(v) -> str | None:
    """Convierte fecha textual de Panamá ('25 de mayo de 2026') a YYYY-MM-DD."""
    if not v:
        return None
    s = str(v).strip()
    m = re.match(r"^(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})$", s, re.IGNORECASE)
    if m:
        dia, mes, anio = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        num_mes = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
            "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10,
            "noviembre": 11, "diciembre": 12,
        }.get(mes)
        if num_mes:
            return f"{anio:04d}-{num_mes:02d}-{dia:02d}"
    return None


def _v2_result_to_datos(aviso_out: dict, pais: int) -> tuple[dict, dict]:
    """Convierte el output del PipelineRunner V2 (por aviso) al formato de
    datos/confianza del pipeline de producción (modelo Aviso)."""
    fields = aviso_out.get("fields") or {}
    datos: dict = {}
    confianza: dict = {}
    for campo_v2, campo_bd in _MAPEO_CAMPOS_V2_A_BD.items():
        entry = fields.get(campo_v2)
        if not entry:
            continue
        valor = entry.get("value") if isinstance(entry, dict) else entry
        if valor in _CAMPOS_V2_DESCARTABLES:
            continue
        conf = entry.get("confidence", 0.0) if isinstance(entry, dict) else 0.0
        if campo_bd == "fecha":
            norm = _normalizar_fecha_remate(valor)
            if norm:
                datos[campo_bd] = norm
                confianza[campo_bd] = conf
        elif campo_bd == "base":
            num = _normalizar_monto_pa(valor)
            if num is not None:
                datos[campo_bd] = str(num)
                confianza[campo_bd] = conf
        else:
            datos[campo_bd] = str(valor)
            confianza[campo_bd] = conf
    datos["pais"] = 1 if pais == "PA" else 2
    return datos, confianza


def procesar_documento_v2(db: Session, documento: Documento) -> list[Aviso]:
    """Procesa un documento de Panamá con el pipeline V2 (Vision OCR +
    segmentación de columnas + parser determinista), el que detecta los
    avisos reales que el pipeline de IA (Claude) pierde. Reutiliza las
    reglas de negocio/validación/confianza del pipeline de producción para
    generar los Aviso en BD con el mismo formato."""
    # El pipeline V2 usa imports absolutos (backend.app.v2.*). En Render la
    # app arranca con `cd backend && uvicorn app.main:app`, así que el paquete
    # `backend` no está en sys.path: lo agregamos para que el import funcione.
    import sys as _sys
    import pathlib as _pathlib
    _raiz = _pathlib.Path(__file__).resolve().parents[3]
    if str(_raiz) not in _sys.path:
        _sys.path.insert(0, str(_raiz))

    from ..v2.pipeline.runner import PipelineRunner

    audit.registrar(db, "orchestrator", "inicio_procesamiento_v2",
                     f"Procesando {documento.nombre_archivo} con pipeline V2",
                     documento_id=documento.id)

    documento.estado = "procesando"
    db.commit()

    rutas = [documento.ruta_archivo]
    if documento.rutas_adicionales_json:
        rutas.extend(json.loads(documento.rutas_adicionales_json))

    try:
        runner = PipelineRunner()
        resultado = runner.process(
            file_paths=rutas,
            country="PA",
            document_id=str(documento.id),
            source_type="upload",
        )
    except Exception as e:
        documento.estado = "error"
        db.commit()
        audit.registrar(db, "orchestrator", "error_v2", str(e)[:500],
                        documento_id=documento.id)
        raise

    # Guardar el texto OCR crudo (fuente para verificar/aprender) desde la
    # salida del pipeline V2. El runner expone el OCR concatenado en
    # resultado["ocr_text"].
    try:
        ocr_pages = (resultado.get("stages") or {}).get("ocr", {}).get("output")
        if ocr_pages:
            textos = []
            for ocr_doc in ocr_pages.values():
                for page in getattr(ocr_doc, "pages", []):
                    txt = getattr(page, "full_text", None) or getattr(page, "text", "")
                    if txt:
                        textos.append(str(txt))
            if textos:
                documento.texto_ocr = "\n".join(textos)[:300000]
                db.commit()
        ocr_text = (resultado.get("ocr_text") or "").strip()
        if ocr_text and not documento.texto_ocr:
            documento.texto_ocr = ocr_text[:300000]
            db.commit()
    except Exception:
        db.rollback()

    avisos_out = (resultado.get("final_json") or {}).get("avisos") or []
    if not avisos_out:
        # Fallback al pipeline de IA (comportamiento anterior) si el V2 no
        # detectó nada.
        audit.registrar(db, "orchestrator", "v2_sin_avisos",
                        "Pipeline V2 no detectó avisos; usando pipeline de IA",
                        documento_id=documento.id)
        return procesar_documento_ia(db, documento, rutas)

    audit.registrar(db, "orchestrator", "extraccion_completa_v2",
                     f"{len(avisos_out)} aviso(s) extraído(s) con pipeline V2",
                     documento_id=documento.id)

    avisos_creados = []
    sigla_periodico = _sigla_periodico_de_archivo(documento.nombre_archivo)
    texto_ocr = documento.texto_ocr or ""
    for idx, aviso_out in enumerate(avisos_out):
        try:
            datos, confianza_campos = _v2_result_to_datos(aviso_out, documento.pais)
            datos["_sigla_periodico"] = sigla_periodico

            # Completar campos vacíos desde la descripción completa (igual que
            # el pipeline de IA): lote_casa, superficie, provincia, plano,
            # codigo_ubicacion, etc. están en el texto largo del aviso.
            try:
                campos_recuperados = extractor_deterministico.completar_campos_vacios_desde_descripcion(
                    datos, confianza_campos)
                if campos_recuperados:
                    audit.registrar(
                        db, "orchestrator", "campos_recuperados_v2",
                        f"Item {idx}: {', '.join(campos_recuperados)}",
                        documento_id=documento.id)
            except Exception as e:
                print(f"[orchestrator] completar campos v2 falló: {e}")

            # === APRENDIZAJE: aplicar correcciones anteriores del cliente ===
            try:
                from ..v2.learning.feedback_store import aplicar_aprendizaje
                texto_aviso_aprend = aviso_out.get("text") or ""
                pais_num = 1 if documento.pais == "PA" else 2
                campos_corregidos = aplicar_aprendizaje(
                    db, texto_aviso_aprend, pais_num, datos)
                if campos_corregidos:
                    for campo, valor in campos_corregidos.items():
                        datos[campo] = valor
                        confianza_campos[campo] = 0.85
                    audit.registrar(
                        db, "orchestrator", "aprendizaje_aplicado",
                        f"Item {idx}: {', '.join(campos_corregidos.keys())} "
                        f"rellenados por aprendizaje del cliente",
                        documento_id=documento.id)
            except Exception as e:
                print(f"[orchestrator] aprendizaje v2 falló: {e}")

            # Cabecera del periódico (periodico/fecha_prensa/pagina_prensa):
            # el V2 no la extrae, y sin ella aplicar_reglas no puede generar
            # el codigo_prensa (INICIAL+DDMESAAAA+PÁGINA).
            if texto_ocr:
                if not datos.get("periodico") and not datos.get("fecha_prensa"):
                    cabecera = _cabecera_periodico_desde_ocr(texto_ocr)
                    if cabecera:
                        datos["periodico"], datos["fecha_prensa"] = cabecera
                if not datos.get("pagina_prensa"):
                    pagina = _pagina_prensa_desde_ocr(texto_ocr)
                    if pagina:
                        datos["pagina_prensa"] = pagina

            # Fianza/mínimo desde el texto OCR (el parser V2 no los extrae)
            if texto_ocr:
                fm_ocr = _buscar_fianza_minimo_en_ocr(datos, texto_ocr, documento.pais)
                if fm_ocr.get("fianza_porcentaje") and not datos.get("fianza_porcentaje"):
                    datos["fianza_porcentaje"] = fm_ocr["fianza_porcentaje"]
                    confianza_campos["fianza_porcentaje"] = 0.9
                if fm_ocr.get("minimo_porcentaje") and not datos.get("minimo_porcentaje"):
                    datos["minimo_porcentaje"] = fm_ocr["minimo_porcentaje"]
                    confianza_campos["minimo_porcentaje"] = 0.9

            # Rescate determinista de la base desde el TEXTO del propio aviso:
            # el parser regex a veces no la asocia (el OCR la imprime como
            # "( B / 47.92727 )" con puntos en vez de comas), pero el texto
            # completo del aviso SÍ la trae junto a "base del remate".
            if not _base_valida(datos.get("base")):
                texto_aviso = aviso_out.get("text") or ""
                if texto_aviso:
                    base_rescatada = _buscar_base_v2_en_texto(texto_aviso)
                    if base_rescatada:
                        datos["base"] = str(base_rescatada)
                        confianza_campos["base"] = 0.8
                        audit.registrar(
                            db, "orchestrator", "base_rescatada_v2",
                            f"Item {idx}: base {base_rescatada} recuperada del texto del aviso",
                            documento_id=documento.id)

            # Descripción resumida + ubicación Maps + texto completo
            # reconstruido con IA (estilo Colombia); si la IA no está
            # disponible o falla, se conservan los respaldos deterministas
            # (descripcion del builder V2, descripcion_completa del texto ya
            # limpiado, prevista de reglas).
            texto_aviso = aviso_out.get("text") or ""
            enriquecido = extraction.enriquecer_aviso_con_ia(texto_aviso, documento.pais)
            if enriquecido.get("descripcion_completa"):
                datos["descripcion_completa"] = enriquecido["descripcion_completa"]
                confianza_campos["descripcion_completa"] = 0.85
                audit.registrar(
                    db, "orchestrator", "texto_aviso_ia",
                    f"Item {idx}: texto del aviso reconstruido con IA "
                    "(columnas desenredadas)",
                    documento_id=documento.id)
            if enriquecido.get("descripcion"):
                datos["descripcion"] = enriquecido["descripcion"]
                confianza_campos["descripcion"] = 0.9
                audit.registrar(
                    db, "orchestrator", "descripcion_portada_ia",
                    f"Item {idx}: descripción resumida generada con IA",
                    documento_id=documento.id)
            if enriquecido.get("prevista"):
                datos["prevista"] = enriquecido["prevista"]
                confianza_campos["prevista"] = 0.9
                audit.registrar(
                    db, "orchestrator", "prevista_ia",
                    f"Item {idx}: ubicación para Maps generada con IA",
                    documento_id=documento.id)

            datos = business_rules.aplicar_reglas(datos)

            # Filtro de falsos positivos: sin base no es aviso de remate real.
            if not _base_valida(datos.get("base")):
                audit.registrar(
                    db, "orchestrator", "descartado_sin_base",
                    f"Item {idx}: exp={datos.get('expediente')!r} sin base -> "
                    f"descartado (posible falso positivo o aviso cortado)",
                    documento_id=documento.id)
                db.commit()
                continue

            faltantes = validation.campos_faltantes(datos)
            resultado_validacion = validation.evaluar_duplicado_o_republicacion(db, datos)
            discrepancia = datos.get("_discrepancia_valores", False)
            fianza_asumida = datos.get("_fianza_asumida_por_regla", False)
            decision = confidence.decidir(
                confianza_campos, faltantes, resultado_validacion,
                discrepancia, fianza_asumida)
            audit.registrar(db, "confidence", decision["decision"],
                            decision["motivo"], documento_id=documento.id)

            aviso_reemplazado_id = resultado_validacion.get("aviso_a_reemplazar_id")
            if aviso_reemplazado_id:
                anterior = db.query(Aviso).get(aviso_reemplazado_id)
                if anterior:
                    anterior.estado = "reemplazado_por_republicacion"
                    db.commit()

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
            try:
                db.rollback()
            except Exception:
                pass
            try:
                audit.registrar(db, "orchestrator", "error_aviso_v2",
                                f"Item {idx}: {str(e)[:500]}", documento_id=documento.id)
            except Exception:
                db.rollback()
            continue

    documento.estado = "completado"
    db.commit()
    audit.registrar(db, "orchestrator", "fin_procesamiento",
                     f"{len(avisos_creados)} aviso(s) procesado(s) (V2)",
                     documento_id=documento.id)

    return avisos_creados


def procesar_documento_ia(db: Session, documento: Documento, rutas: list[str]) -> list[Aviso]:
    """El pipeline de IA original (Vision OCR -> Claude estructura). Se usa
    como fallback si el pipeline V2 no detecta avisos, o para Colombia."""
    audit.registrar(db, "orchestrator", "inicio_procesamiento",
                     f"Procesando {documento.nombre_archivo}", documento_id=documento.id)

    documento.estado = "procesando"
    db.commit()

    try:
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
    sigla_periodico = _sigla_periodico_de_archivo(documento.nombre_archivo)
    texto_ocr = salida_ocr.get("texto") or ""

    for idx, item in enumerate(resultados):
        try:
            item["datos"]["_sigla_periodico"] = sigla_periodico

            campos_recuperados = extractor_deterministico.completar_campos_vacios_desde_descripcion(
                item["datos"], item["confianza"])
            if campos_recuperados:
                audit.registrar(
                    db, "extraction", "campos_recuperados_descripcion_completa",
                    f"Item {idx}: {', '.join(campos_recuperados)}",
                    documento_id=documento.id)

            # Respaldos deterministas desde el texto OCR
            if texto_ocr:
                if not item["datos"].get("periodico") and not item["datos"].get("fecha_prensa"):
                    cabecera = _cabecera_periodico_desde_ocr(texto_ocr)
                    if cabecera:
                        item["datos"]["periodico"], item["datos"]["fecha_prensa"] = cabecera
                if not item["datos"].get("pagina_prensa"):
                    pagina = _pagina_prensa_desde_ocr(texto_ocr)
                    if pagina:
                        item["datos"]["pagina_prensa"] = pagina
                fm_ocr = _buscar_fianza_minimo_en_ocr(item["datos"], texto_ocr, documento.pais)
                if fm_ocr.get("fianza_porcentaje") and not item["datos"].get("fianza_porcentaje"):
                    item["datos"]["fianza_porcentaje"] = fm_ocr["fianza_porcentaje"]
                    item["confianza"]["fianza_porcentaje"] = 0.9
                if fm_ocr.get("minimo_porcentaje") and not item["datos"].get("minimo_porcentaje"):
                    item["datos"]["minimo_porcentaje"] = fm_ocr["minimo_porcentaje"]
                    item["confianza"]["minimo_porcentaje"] = 0.9
                base_ocr = _buscar_base_en_ocr(item["datos"], texto_ocr)
                if base_ocr:
                    item["datos"]["base"] = str(base_ocr)

            datos = business_rules.aplicar_reglas(item["datos"])
            confianza_campos = item["confianza"]

            # Filtro de falsos positivos
            base_aviso = datos.get("base")
            if base_aviso in (None, "", "null"):
                audit.registrar(
                    db, "orchestrator", "descartado_sin_base",
                    f"Item {idx}: exp={datos.get('expediente')!r} sin base -> "
                    f"descartado (posible falso positivo o aviso cortado)",
                    documento_id=documento.id)
                db.commit()
                continue
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


def procesar_documento(db: Session, documento: Documento) -> list[Aviso]:
    """Punto de entrada. Para Panamá usa el pipeline V2 (que detecta los
    avisos reales de la página); para Colombia usa el pipeline de IA."""
    if documento.pais == "PA":
        return procesar_documento_v2(db, documento)

    rutas = [documento.ruta_archivo]
    if documento.rutas_adicionales_json:
        rutas.extend(json.loads(documento.rutas_adicionales_json))
    return procesar_documento_ia(db, documento, rutas)
