from backend.app.v2.ocr.models import OCRWord, OCRBlock, OCRPage, OCRDocument


def _vertices_to_bbox(vertices: list[dict]) -> tuple[int, int, int, int]:
    xs = [v.get("x", 0) for v in vertices if v is not None and v.get("x") is not None]
    ys = [v.get("y", 0) for v in vertices if v is not None and v.get("y") is not None]
    if not xs:
        xs = [0]
    if not ys:
        ys = [0]
    return min(xs), min(ys), max(xs), max(ys)


def _get_symbol_text(symbol: dict) -> str:
    return symbol.get("text", "")


def _get_detected_break(symbol: dict) -> str:
    prop = symbol.get("property", {})
    break_info = prop.get("detectedBreak", {})
    if break_info:
        return break_info.get("type", "")
    return ""


def _extract_words_from_paragraph(paragraph: dict, page_number: int) -> list[OCRWord]:
    words = []
    for w in paragraph.get("words", []):
        symbols = w.get("symbols", [])
        text = "".join(_get_symbol_text(s) for s in symbols)
        bbox = w.get("boundingBox", {}).get("vertices", [])
        x0, y0, x1, y1 = _vertices_to_bbox(bbox)
        confidence = w.get("confidence", 0.0)
        break_type = ""
        if symbols:
            break_type = _get_detected_break(symbols[-1])
        word = OCRWord(
            text=text,
            confidence=confidence,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            page=page_number,
            break_type=break_type,
        )
        words.append(word)
    return words


def _extract_blocks_from_page(page_data: dict, page_number: int) -> list[OCRBlock]:
    blocks = []
    for b in page_data.get("blocks", []):
        bbox = b.get("boundingBox", {}).get("vertices", [])
        x0, y0, x1, y1 = _vertices_to_bbox(bbox)
        block_confidence = b.get("confidence", 0.0)
        block_type = b.get("blockType", "TEXT").lower()
        paragraphs = b.get("paragraphs", [])
        words: list[OCRWord] = []
        for p in paragraphs:
            words.extend(_extract_words_from_paragraph(p, page_number))
        block_text = _join_words_simple(words)
        block = OCRBlock(
            text=block_text,
            confidence=block_confidence,
            block_type=block_type,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            page=page_number,
            words=words,
        )
        blocks.append(block)
    return blocks


def _reconstruct_text_word_level(annotation: dict) -> str:
    pages = annotation.get("pages", [])
    if not pages:
        return ""

    lines = []
    for page_idx, page_data in enumerate(pages):
        page_number = page_idx + 1
        words: list[OCRWord] = []
        for b in page_data.get("blocks", []):
            for p in b.get("paragraphs", []):
                words.extend(_extract_words_from_paragraph(p, page_number))

        if not words:
            continue

        columns = _detect_columns(words, page_data.get("width", 0))
        if len(columns) <= 1:
            text = _join_words_simple(words)
        else:
            text = _join_words_by_column(words, columns)

        if page_number > 1:
            lines.append(f"--- PÁGINA {page_number} ---")
        lines.append(text)

    return "\n\n".join(lines)


def _detect_columns(words: list[OCRWord], page_width: int) -> list[tuple[int, int]]:
    if not words or page_width == 0:
        return []

    x_centers = [(w.x0 + w.x1) // 2 for w in words]
    if not x_centers:
        return []

    min_x = min(x_centers)
    max_x = max(x_centers)
    if max_x - min_x < page_width * 0.15:
        return []

    threshold = page_width // 3
    histogram: dict[int, int] = {}
    for cx in x_centers:
        bucket = cx // max(threshold, 1)
        histogram[bucket] = histogram.get(bucket, 0) + 1

    if not histogram:
        return []

    sorted_buckets = sorted(histogram.keys())
    gap = 1
    merged = []
    current_start = sorted_buckets[0]
    current_end = sorted_buckets[0]
    for b in sorted_buckets[1:]:
        if b - current_end <= gap:
            current_end = b
        else:
            merged.append((current_start, current_end))
            current_start = b
            current_end = b
    merged.append((current_start, current_end))

    significant = [(s, e) for s, e in merged if histogram.get(s, 0) >= 3]

    if len(significant) < 2:
        return []

    columns: list[tuple[int, int]] = []
    for s, e in significant:
        col_min = s * threshold
        col_max = (e + 1) * threshold
        columns.append((col_min, col_max))

    return columns


def _append_word_with_break(parts: list[str], word_text: str, break_type: str) -> None:
    """Agrega word_text a parts y decide qué separador va después, según el
    break_type que reportó Vision. HYPHEN significa que la palabra continúa
    en la siguiente línea por guion de fin de línea (word-wrap tipográfico):
    la reconstruimos como una sola palabra (sin '-' ni salto de línea) en vez
    de dejar el guion suelto, que es lo que después queda partido en
    descripcion_completa/descripcion. Si el glifo del guion sí quedó
    capturado como parte del texto de la palabra, se retira; si Vision no lo
    incluyó, no hay nada que retirar y la unión es igual de correcta."""
    parts.append(word_text)
    if break_type == "LINE_BREAK":
        parts.append("\n")
    elif break_type == "HYPHEN":
        if parts[-1].endswith("-"):
            parts[-1] = parts[-1][:-1]
        # Sin separador: la palabra continúa directamente en la siguiente línea.
    elif break_type in ("SPACE", "EOL_SURE_SPACE", ""):
        parts.append(" ")


def _join_words_simple(words: list[OCRWord]) -> str:
    if not words:
        return ""
    result_parts: list[str] = []
    for i, w in enumerate(words):
        if i < len(words) - 1:
            _append_word_with_break(result_parts, w.text, w.break_type)
        else:
            result_parts.append(w.text)
    return "".join(result_parts)


def _join_words_by_column(words: list[OCRWord], columns: list[tuple[int, int]]) -> str:
    col_words: dict[int, list[OCRWord]] = {}
    for w in words:
        cx = (w.x0 + w.x1) // 2
        assigned = False
        for col_idx, (col_min, col_max) in enumerate(columns):
            if col_min <= cx < col_max:
                col_words.setdefault(col_idx, []).append(w)
                assigned = True
                break
        if not assigned:
            col_words.setdefault(len(columns), []).append(w)

    sorted_cols = sorted(col_words.keys())
    col_texts: list[str] = []
    for col_idx in sorted_cols:
        col_words[col_idx].sort(key=lambda w: (w.y0, w.x0))
        col_texts.append(_join_words_simple(col_words[col_idx]))

    return "\n".join(col_texts)


def _reconstruct_text_block_level(annotation: dict) -> str:
    pages = annotation.get("pages", [])
    if not pages:
        return annotation.get("text", "")

    lines = []
    for page_idx, page_data in enumerate(pages):
        page_number = page_idx + 1
        blocks = page_data.get("blocks", [])
        if not blocks:
            continue

        page_width = page_data.get("width", 0)
        threshold = page_width * 0.15 if page_width > 0 else 100

        sorted_blocks = sorted(blocks, key=lambda b: _block_center_x(b))
        columns: list[list[dict]] = []
        for b in sorted_blocks:
            cx = _block_center_x(b)
            placed = False
            for col in columns:
                ref_cx = _block_center_x(col[0])
                if abs(cx - ref_cx) <= threshold:
                    col.append(b)
                    placed = True
                    break
            if not placed:
                columns.append([b])

        col_texts: list[str] = []
        for col in columns:
            col.sort(key=lambda b: _block_min_y(b))
            col_lines: list[str] = []
            for b in col:
                col_lines.append(_block_to_text(b))
            col_texts.append("\n".join(col_lines))

        text = "\n".join(col_texts)
        if page_number > 1:
            lines.append(f"--- PÁGINA {page_number} ---")
        lines.append(text)

    return "\n\n".join(lines)


def _block_center_x(block: dict) -> int:
    bbox = block.get("boundingBox", {}).get("vertices", [])
    xs = [v.get("x", 0) for v in bbox if v is not None and v.get("x") is not None]
    return sum(xs) // len(xs) if xs else 0


def _block_min_y(block: dict) -> int:
    bbox = block.get("boundingBox", {}).get("vertices", [])
    ys = [v.get("y", 0) for v in bbox if v is not None and v.get("y") is not None]
    return min(ys) if ys else 0


def _block_to_text(block: dict) -> str:
    parts: list[str] = []
    for p in block.get("paragraphs", []):
        for w in p.get("words", []):
            word_text = "".join(s.get("text", "") for s in w.get("symbols", []))
            symbols = w.get("symbols", [])
            break_type = ""
            if symbols:
                prop = symbols[-1].get("property", {})
                br = prop.get("detectedBreak", {})
                if br:
                    break_type = br.get("type", "")
            _append_word_with_break(parts, word_text, break_type)
    return "".join(parts).strip()


def _get_full_text(annotation: dict) -> str:
    return annotation.get("text", "")


class OCRMapper:
    def map_response(self, vision_response: dict) -> OCRDocument:
        raw_responses = vision_response.get("responses", [{}])
        pages: list[OCRPage] = []
        full_text_parts: list[str] = []

        for page_idx, resp in enumerate(raw_responses):
            annotation = resp.get("fullTextAnnotation", {})
            if not annotation:
                continue

            page_number = page_idx + 1
            page_data_list = annotation.get("pages", [])
            if page_data_list:
                page_data = page_data_list[0]
                page_width = page_data.get("width", 0)
                page_height = page_data.get("height", 0)
                blocks = _extract_blocks_from_page(page_data, page_number)
                word_level_text = _reconstruct_text_word_level(annotation)
                block_level_text = _reconstruct_text_block_level(annotation)
                plain_text = _get_full_text(annotation)
                raw_text_len = len(plain_text)
                if word_level_text and (not plain_text or len(word_level_text) >= raw_text_len * 0.85):
                    page_text = word_level_text
                elif block_level_text and raw_text_len > 0 and len(block_level_text) >= raw_text_len * 0.85:
                    page_text = block_level_text
                else:
                    page_text = plain_text
            else:
                page_width = 0
                page_height = 0
                blocks = []
                page_text = _get_full_text(annotation)

            page = OCRPage(
                page_number=page_number,
                width=page_width,
                height=page_height,
                blocks=blocks,
                text=page_text,
            )
            pages.append(page)
            full_text_parts.append(page_text)

        full_text = "\n\n".join(full_text_parts)
        return OCRDocument(
            pages=pages,
            full_text=full_text,
            raw_response=vision_response,
        )

    def map_text_annotation(self, annotation: dict) -> OCRPage:
        page_data_list = annotation.get("pages", [{}])
        page_data = page_data_list[0] if page_data_list else {}
        page_width = page_data.get("width", 0)
        page_height = page_data.get("height", 0)
        page_number = 1

        blocks = _extract_blocks_from_page(page_data, page_number)
        word_level_text = _reconstruct_text_word_level(annotation)
        block_level_text = _reconstruct_text_block_level(annotation)
        plain_text = _get_full_text(annotation)
        raw_text_len = len(plain_text)
        if word_level_text and (not plain_text or len(word_level_text) >= raw_text_len * 0.85):
            page_text = word_level_text
        elif block_level_text and raw_text_len > 0 and len(block_level_text) >= raw_text_len * 0.85:
            page_text = block_level_text
        else:
            page_text = plain_text

        return OCRPage(
            page_number=page_number,
            width=page_width,
            height=page_height,
            blocks=blocks,
            text=page_text,
        )
