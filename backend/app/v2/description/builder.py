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
    """descripcion (corta, para portada): resumen extractivo determinista
    (problemas #3 y #8 -- sin IA generativa).

    Contrato:
    - Regla principal del cliente: máximo 30 palabras.
    - Red de seguridad adicional: tope de caracteres (max_chars).
    - Nunca corta una oración a la mitad cuando el texto corto cabe en
      presupuesto (preferir texto largo pero completo).
    - Se acumulan oraciones completas hasta el presupuesto; si la primera
      oración ya lo supera se devuelve tal cual (mejor larga que incompleta).
    - Los encabezados/etiquetas (AVISO DE REMATE, EXPEDIENTE Nº, etc.) se
      saltan para tomar la primera oración con contenido comercial real.
    - Si el texto supera 30 palabras, se recorta a 30 palabras como regla
      principal, sin cortar palabras."""
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
