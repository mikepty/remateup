"""
Parser de PDFs tabulares de Colombia (SEJURE).
Extrae texto directamente con pypdf (gratis, sin IA) y parsea la estructura
tabular conocida: FECHA, HORA, DIRECCION, DESCRIPCION, MATRICULA, EXPEDIENTE,
AVALUO, %, BASE, JUZ, CIUDAD.
"""
import re
from pypdf import PdfReader


def _limpiar_numero(texto: str) -> float | None:
    """Convierte texto de moneda a número: '$ 409.186.500' -> 409186500.0"""
    if not texto:
        return None
    texto = texto.strip().replace("$", "").replace(" ", "")
    # Formato colombiano: puntos como separadores de miles
    texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except (ValueError, TypeError):
        return None


def _detectar_categoria(descripcion: str) -> str:
    """Detecta categoría del bien basándose en la columna DESCRIPCION."""
    desc = (descripcion or "").upper()
    if "VEHICULO" in desc or "CAMIONETA" in desc or "MOTO" in desc or "CHEVROLET" in desc or "RENAULT" in desc:
        return "VEHICULO"
    if "APARTAMENTO" in desc or "APARAMENTO" in desc:
        return "APARTAMENTO"
    if "CASA" in desc or "CAS." in desc:
        return "CASA"
    if "CUOTA PARTE" in desc or "CUOTAS PARTES" in desc:
        return "MISCELANEO"
    if "LOCAL" in desc or "GARAJE" in desc or "DEPOSITO" in desc:
        return "MISCELANEO"
    # Default para PREDIO
    return "TERRENO"


def _extraer_departamento(ciudad: str) -> str | None:
    """Intenta extraer departamento de la columna CIUDAD."""
    if not ciudad:
        return None
    ciudad = ciudad.strip().upper()
    # Mapeo de ciudades conocidas a departamentos
    mapeo = {
        "BOGOTA": "BOGOTA", "CALI": "VALLE DEL CAUCA", "MONTERIA": "CORDOBA",
        "MEDELLIN": "ANTIOQUIA", "BARRANQUILLA": "ATLANTICO", "SOACHA": "CUNDINAMARCA",
        "VILLAVICENCIO": "META", "PEREIRA": "RISARALDA", "ARMENIA": "QUINDIO",
        "PASTO": "NARINO", "RIOHACHA": "LA GUAJIRA", "TUNJA": "BOYACA",
        "NEIVA": "HUILA", "IBAGUE": "TOLIMA", "CARTAGENA": "BOLIVAR",
        "BARRANCA": "SANTANDER", "ESPINAL": "TOLIMA", "HONDA": "TOLIMA",
        "FUNZA": "CUNDINAMARCA", "FACATATIVA": "CUNDINAMARCA", "DUITAMA": "BOYACA",
        "SOGAMOSO": "BOYACA", "CARTAGO": "VALLE DEL CAUCA", "GRANADA": "META",
        "SANTA MARTA": "MAGDALENA",
    }
    for key, dept in mapeo.items():
        if key in ciudad:
            return dept
    # Si tiene departamento en el nombre (ej. "ESPINAL T." = Tolima)
    if "T." in ciudad or "TOL" in ciudad:
        return "TOLIMA"
    if "CES" in ciudad:
        return "CESAR"
    if "CUNDI" in ciudad:
        return "CUNDINAMARCA"
    if "BOYACA" in ciudad or "BOY" in ciudad:
        return "BOYACA"
    if "VALLE" in ciudad:
        return "VALLE DEL CAUCA"
    if "RISARALDA" in ciudad or "RIS" in ciudad:
        return "RISARALDA"
    if "CAQ" in ciudad:
        return "CAQUETA"
    return ciudad


def _parsear_expediente(texto: str) -> dict:
    """Extrae demandante y demandado del campo expediente.
    Formato típico: 'EJ. HP. No.001-2017-00251 00 Banco Agrario de Colombia Vs.Juan Daza Cárdenas'
    """
    resultado = {"expediente": None, "demandante": None, "demandado": None, "proceso": None}
    if not texto:
        return resultado

    texto = texto.strip()

    # Extraer número de expediente
    exp_match = re.search(r'No\.?\s*([0-9\-]+)', texto)
    if exp_match:
        resultado["expediente"] = exp_match.group(1)

    # Extraer tipo de proceso
    if "HP" in texto or "HIPOTECARIO" in texto:
        resultado["proceso"] = "EJECUTIVO HIPOTECARIO"
    elif "SING" in texto or "SINGULAR" in texto:
        resultado["proceso"] = "EJECUTIVO SINGULAR"
    elif "MIX" in texto:
        resultado["proceso"] = "EJECUTIVO MIXTO"
    elif "DIV" in texto:
        resultado["proceso"] = "DIVORCIO"
    elif "Administrativo" in texto or "Coactivo" in texto:
        resultado["proceso"] = "ADMINISTRATIVO COACTIVO"
    else:
        resultado["proceso"] = "EJECUTIVO"

    # Extraer demandante y demandado (separados por "Vs." o "Vs")
    vs_match = re.split(r'\bVs\.?\s*', texto, flags=re.IGNORECASE)
    if len(vs_match) >= 2:
        # El demandante está antes del Vs, después del número
        parte_demandante = vs_match[0]
        # Limpiar: quitar el número de expediente y datos iniciales
        dem_clean = re.sub(r'^.*?\d{2}\s+', '', parte_demandante, count=1).strip()
        if dem_clean:
            resultado["demandante"] = dem_clean
        # Demandado es después del Vs
        resultado["demandado"] = vs_match[1].strip().rstrip(" y otros").strip()

    return resultado


def extraer_desde_pdf(pdf_path: str) -> list[dict]:
    """
    Extrae avisos de remate de un PDF tabular de Colombia.
    Devuelve lista de dicts con formato {datos: {...}, confianza: {...}}
    compatible con el pipeline existente.
    """
    reader = PdfReader(pdf_path)
    avisos = []

    for page in reader.pages:
        texto = page.extract_text() or ""
        lineas = texto.split("\n")

        # Buscar filas de la tabla. Cada fila de remate tiene:
        # fecha (DD-jul o similar), hora, dirección, tipo, matrícula, expediente, avalúo, %, base, juz, ciudad
        fila_actual = []
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue

            # Detectar inicio de fila nueva: empieza con fecha (25-jul, 28-jul, 29-jul, 30-jul)
            fecha_match = re.match(r'^(\d{1,2})-?(jul|ago|sep|oct|nov|dic|ene|feb|mar|abr|may|jun)\s+(.+)', linea, re.IGNORECASE)

            if fecha_match:
                # Procesar fila anterior si existe
                if fila_actual:
                    aviso = _procesar_fila(fila_actual)
                    if aviso:
                        avisos.append(aviso)
                fila_actual = [linea]
            else:
                # Continuación de la fila actual
                if fila_actual:
                    fila_actual.append(linea)

        # Procesar última fila
        if fila_actual:
            aviso = _procesar_fila(fila_actual)
            if aviso:
                avisos.append(aviso)

    return avisos


def _procesar_fila(lineas: list[str]) -> dict | None:
    """Procesa una fila de la tabla y extrae los campos."""
    texto_completo = " ".join(lineas)

    # Extraer fecha
    fecha_match = re.match(r'^(\d{1,2})-(jul|ago|sep|oct|nov|dic|ene|feb|mar|abr|may|jun)', texto_completo, re.IGNORECASE)
    if not fecha_match:
        return None

    dia = fecha_match.group(1)
    mes_texto = fecha_match.group(2).lower()
    meses = {"ene": "01", "feb": "02", "mar": "03", "abr": "04", "may": "05", "jun": "06",
             "jul": "07", "ago": "08", "sep": "09", "oct": "10", "nov": "11", "dic": "12"}
    mes = meses.get(mes_texto, "07")
    # Año: asumimos 2025 ya que el documento dice "28 JULIO 2025"
    fecha = f"2025-{mes}-{dia.zfill(2)}"

    # Extraer hora
    hora_match = re.search(r'(\d{1,2})[.:]\s*(\d{2})\s*(A\.?M|P\.?M)', texto_completo, re.IGNORECASE)
    hora = None
    if hora_match:
        h = int(hora_match.group(1))
        m = hora_match.group(2)
        ampm = hora_match.group(3).upper().replace(".", "")
        if ampm == "PM" and h < 12:
            h += 12
        if ampm == "AM" and h == 12:
            h = 0
        hora = f"{h:02d}:{m}"

    # Extraer montos (buscar patrones de dinero: $ XXX.XXX.XXX)
    montos = re.findall(r'\$\s*[\d.,]+', texto_completo)
    avaluo = _limpiar_numero(montos[0]) if len(montos) >= 1 else None
    base = _limpiar_numero(montos[1]) if len(montos) >= 2 else None

    # Extraer porcentaje
    pct_match = re.search(r'\b(70|100|50)\b', texto_completo)
    minimo_pct = float(pct_match.group(1)) if pct_match else 70.0

    # Extraer matrícula
    matr_match = re.search(r'(\d{2,3}[A-Z]?-?\d{3,7})', texto_completo)
    matricula = matr_match.group(1) if matr_match else None

    # Extraer tipo de bien (PREDIO, APARTAMENTO, VEHICULO, CASA, etc.)
    tipo_bien = "PREDIO"
    for tipo in ["APARTAMENTO", "VEHICULO", "CASA", "CUOTA PARTE", "LOCAL", "GARAJE", "MOTO"]:
        if tipo in texto_completo.upper():
            tipo_bien = tipo
            break

    categoria = _detectar_categoria(tipo_bien)

    # Extraer expediente/partes
    exp_data = _parsear_expediente(texto_completo)

    # Extraer ciudad (suele estar al final)
    ciudad_match = re.search(r'(BOGOTA|CALI|MONTERIA|MEDELLIN|SOACHA|VILLAVICENCIO|PEREIRA|ARMENIA|PASTO|RIOHACHA|TUNJA|NEIVA|IBAGUE|BARRANCA|ESPINAL|HONDA|FUNZA|FACATATIVA|DUITAMA|SOGAMOSO|CARTAGO|GRANADA|SANTA MARTA|MARIQUITA|PLANETA RICA|PUERTO ASIS|CURILLO|CHOCONTA|SEVILLA|MOSQUERA|VILLANUEVA|GUAYABAL|PITALITO|TOCANCIPA|SAN LUIS|SAN JUAN|LA JAGUA|LA MESA|APIA)', texto_completo.upper())
    ciudad = ciudad_match.group(1) if ciudad_match else None

    # Extraer dirección (texto entre la hora y el tipo de bien)
    direccion = ""
    resto = texto_completo[fecha_match.end():].strip()
    if hora_match:
        idx_hora_fin = texto_completo.find(hora_match.group(0)) + len(hora_match.group(0))
        resto = texto_completo[idx_hora_fin:].strip()
    # La dirección suele ser lo primero antes de las palabras clave
    dir_match = re.match(r'^(.+?)(?:PREDIO|APARTAMENTO|VEHICULO|CASA|CUOTA PARTE|LOCAL|GARAJE|MOTO|PLACAS)', resto, re.IGNORECASE)
    if dir_match:
        direccion = dir_match.group(1).strip()
    else:
        direccion = resto[:80]  # primeros 80 chars como fallback

    # Construir prevista para Google Maps
    prevista = f"{direccion}, {ciudad}" if ciudad else direccion

    provincia = _extraer_departamento(ciudad)

    # Juzgado
    juz_match = re.search(r'(\d+\s*[A-Z.]+\s*(?:C\.?C|C\.?M|P\.?M|C\.?CE|C\.?ME|EC\.?M|LB|PQNC|D\.?C\.?M))', texto_completo)
    juzgado = juz_match.group(1).strip() if juz_match else None

    datos = {
        "pais": 2,
        "codigo": None,  # Se genera en business_rules
        "fecha": fecha,
        "hora": hora,
        "proceso": exp_data.get("proceso"),
        "expediente": exp_data.get("expediente"),
        "lugar": juzgado,
        "categoria": categoria,
        "demandante": exp_data.get("demandante"),
        "demandado": exp_data.get("demandado"),
        "lote_casa": None,
        "descripcion": f"{direccion}, {tipo_bien}, {ciudad or ''}".strip(", "),
        "descripcion_completa": texto_completo,
        "prevista": prevista,
        "superficie": None,
        "finca_matr": matricula,
        "codigo_ubicacion": None,
        "provincia": provincia,
        "plano": None,
        "base": base,
        "fianza_porcentaje": 40.0,  # Fijo para Colombia
        "minimo_porcentaje": minimo_pct,
        "fianza": None,
        "minimo": None,
        "codigo_fuente": None,
        "codigo_prensa": None,
        "email_observaciones": None,
    }

    # Confianza alta para datos extraídos directamente del texto
    confianza = {campo: 0.95 for campo in datos.keys()}
    # Campos que podrían no estar perfectos
    if not exp_data.get("demandante"):
        confianza["demandante"] = 0.0
    if not exp_data.get("demandado"):
        confianza["demandado"] = 0.0
    if not matricula:
        confianza["finca_matr"] = 0.0
    if not juzgado:
        confianza["lugar"] = 0.0

    return {"datos": datos, "confianza": confianza}
