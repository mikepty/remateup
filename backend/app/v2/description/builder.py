# Description Builder — construcción determinista de descripcion_completa
# y descripcion (portada) a partir del texto ya reconstruido de un aviso.
#
# No sustituye a detector.py/normalizer.py/extractor.py (siguen siendo la
# API especulativa de "Phase 5", sin implementar): esto es la pieza que sí
# se necesitaba conectar al pipeline para los problemas #2 y #3, construida
# de forma general (sin listas de páginas/avisos concretos) sobre el texto
# que ya entregan OCR + Continuity Engine (con guiones de fin de línea ya
# reconstruidos, ver ocr/mapper.py y segmenter/line_detector.py).
#
# Sin IA generativa: reglas de texto deterministas únicamente (problema #8).

import re

REMAKE_HEADER_RE = re.compile(r"AVISO\s+DE\s+REMATE|REMATE\s+JUDICIAL|SUBASTA\s+JUDICIAL", re.IGNORECASE)
# Keywords que indican que un bloque pertenece a la descripción comercial de
# un inmueble (la "portada" que interesa al cliente para la galería).
DESCRIPCION_KW = re.compile(
    r"CASA|CON CEATA|CON\s+CEDULA|REMATE|BASE\s+DEL\s+REMATE|VALOR\s+BASE|"
    r"FINCA|LOTE|TERRENO|MÉTODO|MEDIANA|UN\s+TERRENO|DE\s+APROXIMADAMENTE",
    re.IGNORECASE,
)

# Palabra/sigla de 1-2 letras, o inicial(es) separadas por puntos (S.A.,
# E.U., N.), antes de un punto: no se considera fin de oración. Evita
# cortar "Financiera Familiar, S.A." en dos por el punto de "S." o de "A.".
_ABBREV_TAIL = re.compile(r"^[A-ZÁÉÍÓÚÑ](\.[A-ZÁÉÍÓÚÑ])*$")

# ---- Limpieza de texto OCR de la página de Judiciales (Panamá) ----
# La página de La Estrella de Panamá incluye, junto a los avisos de remate,
# elementos que NO pertenecen a ningún aviso y que el OCR mezcla con el
# texto real:
#   - Cabecera de columna "EDICTO 810" (fondo negro, tipografía grande):
#     es la etiqueta de la sección de edictos del periódico, no un aviso de
#     remate. Debe ignorarse (instrucción del cliente).
#   - Banner publicitario "AVISO DE REMATE IC Publica tus judiciales
#     llamando al 204-0000 204-0045 correo: judiciales@laestrella.com.pa
#     10 estrellaonline laestrellaonline": además de ensuciar, su "AVISO DE
#     REMATE" hace que el NoticeDetector lo tome como cabecera de aviso y
#     se trague toda la columna en un solo aviso.
#   - Teléfonos y correos promocionales sueltos ("204-0000 204-0045",
#     "judiciales@laestrella.com.pa", "estrellaonline").
_EDICTO_CABECERA_RE = re.compile(r"^EDICTO\s+\d+\s*$", re.IGNORECASE)
_EDICTO_CABECERA_INLINE_RE = re.compile(r"\bEDICTO\s+\d+\b", re.IGNORECASE)
# El banner completo del periódico (una sola línea en el OCR) se consume en
# UNA pasada: "AVISO DE REMATE IC Publica tus judiciales llamando al
# 204-0000 204-0045 correo : judiciales@laestrella.com.pa 10 estrellaonline
# laestrellaonline". El tramo entre el teléfono y el cierre "la ... online"
# se acota con {0,200}? para no comerse el texto del aviso que sigue.
_BANNER_AVISO_IC_RE = re.compile(
    r"AVISO\s+DE\s+REMATE\s+(?:IC|1C)\s+Publica\s+tus\s+judiciales\s+"
    r"llamando\s+al\s+204-0000\s+204-0045.{0,200}?la\s*estrella\s*online",
    re.IGNORECASE | re.DOTALL)
_BANNER_PUBLICA_RE = re.compile(
    r"Publica\s+tus\s+judiciales\s+llamando\s+al\s+204-0000\s+204-0045.{0,200}?",
    re.IGNORECASE | re.DOTALL)
_CORREO_JUDICIALES_RE = re.compile(r"judiciales@laestrella\.com\.pa", re.IGNORECASE)
_LAESTRELLA_COM_RE = re.compile(r"laestrella\.com\.pa", re.IGNORECASE)
_TEL_PROMO_RE = re.compile(r"\b204-0000\s+204-0045\b")
_ESTRELLAONLINE_RE = re.compile(r"\b(?:10\s+)?la?\s*estrella\s*online\b", re.IGNORECASE)


def limpiar_texto_aviso(texto: str) -> str:
    """Quita del texto OCR de un aviso todo lo que no pertenece al aviso:
    cabeceras de columna "EDICTO NNN" (fondo negro) y el banner publicitario
    del periódico ("AVISO DE REMATE IC Publica tus judiciales...", teléfonos
    y correo promocionales). Se aplica ANTES de construir descripciones o
    de enviar el texto a la IA, para que ni el detector los tome como aviso
    ni contaminen descripcion_completa/descripcion."""
    if not texto:
        return ""
    lineas = texto.split("\n")
    limpias = []
    for ln in lineas:
        if _EDICTO_CABECERA_RE.match(ln.strip()):
            continue
        limpias.append(ln)
    t = "\n".join(limpias)
    t = _BANNER_AVISO_IC_RE.sub("", t)
    t = _BANNER_PUBLICA_RE.sub("", t)
    t = _CORREO_JUDICIALES_RE.sub("", t)
    t = _TEL_PROMO_RE.sub("", t)
    t = _ESTRELLAONLINE_RE.sub("", t)
    t = _EDICTO_CABECERA_INLINE_RE.sub("", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def _looks_like_abbreviation(word: str) -> bool:
    if not word:
        return False
    if len(word) <= 2:
        return True
    return bool(_ABBREV_TAIL.match(word))


def _split_sentences(text: str) -> list[str]:
    """Separa texto en oraciones completas sin cortar abreviaturas comunes
    (S.A., B/., iniciales sueltas). Regla general por longitud/forma de la
    palabra anterior al punto, no por lista de abreviaturas específicas."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    cut_points: list[int] = []
    for m in re.finditer(r"[.!?]+(?:\s+|$)", text):
        end_of_punct = m.start()
        prev_word_match = re.search(r"(\S+)$", text[:end_of_punct])
        prev_word = prev_word_match.group(1) if prev_word_match else ""
        if _looks_like_abbreviation(prev_word):
            continue
        cut_points.append(m.end())
    sentences = []
    start = 0
    for cp in cut_points:
        piece = text[start:cp].strip()
        if piece:
            sentences.append(piece)
        start = cp
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def build_descripcion_completa(aviso_text: str) -> str:
    """descripcion_completa: reconstrucción limpia de TODAS las líneas del
    aviso (problema #2). No decide qué es "descripción de propiedad" y qué
    no -- eso requeriría clasificar líneas por contenido y no hay muestras
    reales con texto de propiedad en este entorno para calibrar eso sin
    arriesgar perder información real (ver informe: is_description()/
    detect() de description/detector.py se dejan deliberadamente sin
    implementar por lo mismo). Lo que sí es general y seguro:
    - no perder texto (solo se recorta espacio en blanco redundante)
    - no repetir párrafos idénticos
    - no cortar palabras (ya resuelto río arriba en ocr/mapper.py y
      segmenter/line_detector.py; aquí no se vuelve a tocar texto interno
      de una palabra)
    """
    if not aviso_text:
        return ""
    raw_lines = [ln.strip() for ln in aviso_text.split("\n")]
    lines = [ln for ln in raw_lines if ln]
    seen: set[str] = set()
    deduped: list[str] = []
    for ln in lines:
        key = re.sub(r"\s+", " ", ln).upper()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ln)
    return "\n".join(deduped)


MAX_WORDS_DESCRIPCION_PORTADA = 30
MAX_CHARS_DESCRIPCION_PORTADA = 350
WINDOW_SIZE = 35


def _extraer_descripcion_panama(texto: str) -> str:
    """Extrae la descripción de portada en formato Panamá:
    SIZE + PROPERTY_NAME, CORR: + CORREGIMIENTO, DIST: + DISTRITO, PROVINCIA.
    Ejemplo: '271.61 M2, LAGO EMPERADOR, CORR: JUAN DEMOSTENES AROSEMENA, DIST: ARRAIJAN.'
    Si no puede extraer todos los campos, devuelve None para que el caller use el fallback."""
    if not texto:
        return ""
    t = re.sub(r"\s+", " ", texto).strip()

    # 1. Extraer superficie
    superficie = ""
    m_sup = re.search(r"([\d,\.]+)\s*(?:M2|M²|METROS?\s*(?:CUADRADOS?)?|HEC(?:TAREAS?)?)", t, re.IGNORECASE)
    if m_sup:
        superficie = m_sup.group(0).strip()
        superficie = re.sub(r"\s+", " ", superficie)
    else:
        m_sup2 = re.search(r"SUPERFICIE\s*[:\s]*([\d,\.]+)\s*(?:M2|M²)?", t, re.IGNORECASE)
        if m_sup2:
            superficie = m_sup2.group(1).strip() + " M2"

    # 2. Extraer corregimiento / distrito / provincia
    corr = ""
    dist = ""
    prov = ""
    # Patrón: "CORR: XXX, DIST: XXX"
    m_corr = re.search(r"CORR(?:EGIMIENTO)?\s*[:\s]+([A-ZÁÉÍÓÚÑ\s]+?)(?:,|\s+DIST)", t, re.IGNORECASE)
    m_dist = re.search(r"DIST(?:RITO)?\s*[:\s]+([A-ZÁÉÍÓÚÑ\s]+?)(?:,|\s+PROV|$)", t, re.IGNORECASE)
    if m_corr:
        corr = m_corr.group(1).strip(" ,.:;-")
    if m_dist:
        dist = m_dist.group(1).strip(" ,.:;-")

    # Patrón: "UBICACION: Residencial X, lote Y, Corr: Z, Dist: W, Prov: V"
    if not corr:
        m_ubic = re.search(r"UBICA\s*CI[ÓO]?N?\s*[:\-]\s*(.+?)(?:\n|$)", t, re.IGNORECASE | re.DOTALL)
        if m_ubic:
            ubic_text = m_ubic.group(1).strip()
            m_c2 = re.search(r"CORR(?:EGIMIENTO)?\s*[:\s]+([A-ZÁÉÍÓÚÑ\s]+?)(?:,|\s+DIST)", ubic_text, re.IGNORECASE)
            m_d2 = re.search(r"DIST(?:RITO)?\s*[:\s]+([A-ZÁÉÍÓÚÑ\s]+?)(?:,|\s+PROV|$)", ubic_text, re.IGNORECASE)
            if m_c2:
                corr = m_c2.group(1).strip(" ,.:;-")
            if m_d2:
                dist = m_d2.group(1).strip(" ,.:;-")

    # Provincia
    m_prov = re.search(r"PROVINCIA\s+DE\s+([A-ZÁÉÍÓÚÑ\s]+?)(?:,|\.|\n|$)", t, re.IGNORECASE)
    if m_prov:
        prov = m_prov.group(1).strip(" ,.:;-")
    else:
        prov_match = re.search(r"(CHIRIQUI|PANAMA|COLON|VERAGUAS|HERRERA|LOS\s+SANTOS|COCLE|BOCAS\s+DEL\s+TORO|PANAMA\s+OESTE)", t, re.IGNORECASE)
        if prov_match:
            prov = prov_match.group(1).strip()

    # 3. Extraer nombre de propiedad (después de superficie, antes de CORR/UBIC)
    nombre = ""
    if superficie:
        # Buscar después de la superficie
        after_sup = t[t.find(superficie) + len(superficie):]
        m_nombre = re.search(r",?\s*([A-ZÁÉÍÓÚÑ\s\.\-]+?)(?:,|\s+CORR|\s+UBICA|\s+DISTRITO|\s+PROVINCIA)", after_sup, re.IGNORECASE)
        if m_nombre:
            nombre = m_nombre.group(1).strip(" ,.:;-")
            # Filtrar si es texto basura
            if len(nombre) < 3 or nombre.upper() in ("DE", "DEL", "LA", "EL", "EN", "CON", "POR", "PARA"):
                nombre = ""

    # 4. Armar descripción en formato CORR/DIST
    partes = []
    if superficie:
        partes.append(superficie)
    if nombre:
        partes.append(nombre)
    if corr and dist:
        partes.append(f"CORR: {corr}, DIST: {dist}")
    elif corr:
        partes.append(f"CORR: {corr}")
    elif dist:
        partes.append(f"DIST: {dist}")
    if prov:
        partes.append(prov)

    if len(partes) >= 2:
        result = ", ".join(partes)
        if result and result[-1] not in ".!?":
            result += "."
        return result
    return ""


def _palabras_bloque(cadena: str) -> list[str]:
    return [w for w in cadena.replace("\n", " ").split() if w]


def _describir_bloque_score(texto: str, require_header: bool) -> float:
    """Score de un bloque: densidad de keywords de descripción comercial, con
    bonus si el bloque contiene el header del remate (AVISO DE REMATE)."""
    palabras = _palabras_bloque(texto)
    if not palabras:
        return 0.0
    matches = len(DESCRIPCION_KW.findall(texto))
    score = matches / len(palabras)
    if require_header and REMAKE_HEADER_RE.search(texto):
        score += 2.0
    elif REMAKE_HEADER_RE.search(texto):
        score += 0.5
    return score


def _find_descripcion_bloque(texto_limpio: str) -> tuple[int, int, list[str]]:
    """Ventana deslizante de WINDOW_SIZE palabras; devuelve el slice con
    mejor puntuación. Prioriza cualquier bloque que contenga el header del
    remate (AVISO DE REMATE) con keywords de descripción, con bonus por
    cuanto más keyword denso; si ningún bloque tiene header, toma el de
    mayor densidad de keywords."""
    palabras = _palabras_bloque(texto_limpio)
    n = len(palabras)
    if n == 0:
        return 0, 0, []
    best_header: tuple[int, int, float] = (-1, -1, -1.0)
    best_kw: tuple[int, int, float] = (0, min(WINDOW_SIZE, n), 0.0)
    for i in range(0, n, max(1, WINDOW_SIZE // 2)):
        end = min(i + WINDOW_SIZE, n)
        bloque = " ".join(palabras[i:end])
        score = _describir_bloque_score(bloque, require_header=True)
        has_header = bool(REMAKE_HEADER_RE.search(bloque))
        kw_only = _describir_bloque_score(bloque, require_header=False)
        if has_header and (best_header[2] < 0 or score > best_header[2]):
            best_header = (i, end, score)
        if kw_only > best_kw[2]:
            best_kw = (i, end, kw_only)
    if best_header[0] >= 0:
        return best_header[0], best_header[1], palabras[best_header[0]:best_header[1]]
    return best_kw[0], best_kw[1], palabras[best_kw[0]:best_kw[1]]


def build_descripcion_portada(aviso_text: str, max_chars: int = MAX_CHARS_DESCRIPCION_PORTADA) -> str:
    """descripcion (corta, para portada): resumen extractivo determinista.

    Para Panamá intenta primero el formato CORR/DIST:
    'SIZE + NOMBRE, CORR: + CORREGIMIENTO, DIST: + DISTRITO, PROVINCIA.'
    Si no puede extraer todos los campos, usa el fallback extractivo original."""
    if not aviso_text:
        return ""

    # Intentar formato Panamá CORR/DIST primero
    desc_pa = _extraer_descripcion_panama(aviso_text)
    if desc_pa and len(desc_pa.split()) <= MAX_WORDS_DESCRIPCION_PORTADA:
        return desc_pa

    # Fallback: lógica original extractiva
    clean = build_descripcion_completa(aviso_text)
    if not clean:
        return ""
    # Contrato #1: si el texto completo cabe en 30 palabras y en max_chars,
    # devolverlo entero (mejor largo pero completo).
    palabras = clean.replace("\n", " ").split()
    if len(palabras) <= MAX_WORDS_DESCRIPCION_PORTADA and len(clean) <= max_chars:
        result = clean.strip()
        if result and result[-1] not in ".!?":
            result += "."
        return result

    sentences = _split_sentences(clean)
    header_label_re = re.compile(r"^(AVISO\s+DE\s+REMATE|EXPEDIENTE|EDICTO|JUEZ|SECCIONAL|CIR)$", re.IGNORECASE)
    chosen: list[str] = []
    total = 0
    for s in sentences:
        if header_label_re.match(s.strip()) and len(chosen) == 0:
            continue
        extra = len(s) + (1 if chosen else 0)
        if chosen and total + extra > max_chars:
            break
        chosen.append(s)
        total += extra
    if not chosen:
        non_headers = [s for s in sentences if not header_label_re.match(s.strip())]
        chosen = non_headers[:1] if non_headers else sentences[:1]
    result = " ".join(chosen).strip()
    # Si el resultado supera 30 palabras o max_chars, usar sliding window para
    # reencontrar el detalle comercial del remate en textos con headers rotos.
    palabras_finales = result.split()
    if len(palabras_finales) > MAX_WORDS_DESCRIPCION_PORTADA or len(result) > max_chars:
        _start, _end, bloque_palabras = _find_descripcion_bloque(clean)
        result = " ".join(bloque_palabras).strip()
    # Regla principal del cliente: tope de 30 palabras (sin cortar palabras)
    palabras_finales = result.split()
    if len(palabras_finales) > MAX_WORDS_DESCRIPCION_PORTADA:
        recorte = " ".join(palabras_finales[:MAX_WORDS_DESCRIPCION_PORTADA])
        if len(recorte) > max_chars:
            palabras_finales = palabras_finales[:MAX_WORDS_DESCRIPCION_PORTADA]
            while palabras_finales and len(" ".join(palabras_finales)) > max_chars:
                palabras_finales.pop()
            result = " ".join(palabras_finales) if palabras_finales else recorte
        else:
            result = recorte
    result = result.rstrip(" ,.;:-")
    if result and result[-1] not in ".!?":
        result += "."
    return result
