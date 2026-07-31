import re
from typing import Optional

VALID_HEADERS = re.compile(
    r"^\s*(?:"
    r"AVISO\s+DE\s+REMATE"
    r"|REMATE\s+JUDICIAL"
    r"|PRIMERA\s+FECHA\s+DE\s+REMATE"
    r"|SEGUNDA\s+FECHA\s+DE\s+REMATE"
    r"|TERCERA\s+FECHA\s+DE\s+REMATE"
    r"|SUBASTA\s+JUDICIAL"
    r"|REMATE\s+EXTRAJUDICIAL"
    r")",
    re.IGNORECASE,
)

INVALID_HEADERS = re.compile(
    r"^\s*(?:"
    r"EDICTO"
    r"|EDICTO\s+EMPLAZATORIO"
    r"|AVISO\s+(?!DE\s+REMATE|IMPORTANTE)"
    r"|AVISO\s+IMPORTANTE"
    r"|COMUNICADO"
    r"|CIRCULAR"
    r"|PUBLICIDAD"
    r"|LICITACION"
    r"|CONVOCATORIA"
    r"|AVISO\s+AL\s+PUBLICO"
    r")",
    re.IGNORECASE,
)

STRONG_FIELDS = {"expediente", "finca", "precio_base", "base", "finca_matr"}
MEDIUM_FIELDS = {"fecha_remate", "demandante", "demandado", "fecha"}
WEAK_FIELDS = {"lugar", "proceso", "hora", "provincia", "categoria", "fianza_porcentaje", "minimo_porcentaje"}

ALL_FIELDS = STRONG_FIELDS | MEDIUM_FIELDS | WEAK_FIELDS

FIELD_CO_OCCURRENCE = [
    ({"finca", "finca_matr"}, {"expediente"}),
    ({"expediente"}, {"finca", "finca_matr"}),
    ({"precio_base", "base"}, {"fecha_remate", "fecha"}),
    ({"fecha_remate", "fecha"}, {"precio_base", "base"}),
    ({"demandante"}, {"demandado"}),
    ({"demandado"}, {"demandante"}),
    ({"fianza_porcentaje"}, {"precio_base", "base"}),
    ({"minimo_porcentaje"}, {"precio_base", "base"}),
]


def detect_header(text: str) -> tuple[str, bool]:
    first_line = text.strip().split("\n")[0] if text.strip() else ""
    if VALID_HEADERS.match(first_line):
        return first_line.strip(), True
    if INVALID_HEADERS.match(first_line):
        return first_line.strip(), False
    for line in text.strip().split("\n")[:5]:
        stripped = line.strip()
        if VALID_HEADERS.match(stripped):
            return stripped, True
    return first_line.strip(), False


def has_publicidad_only(text: str) -> bool:
    indicators = [
        r"\bpublicidad\b",
        r"\bcomunicado\b",
        r"\bcircula(?:r|res)\b",
        r"\blicitacion\b",
        r"\bconvocatoria\b",
        r"\boferta\b",
        r"\bdescuento\b",
    ]
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    if not lines:
        return False
    first_line = lines[0].upper()
    if first_line in ("PUBLICIDAD", "COMUNICADO", "CIRCULAR", "AVISO IMPORTANTE"):
        return True
    matched = sum(1 for p in indicators for l in lines if re.search(p, l, re.IGNORECASE))
    legal_indicators = sum(1 for l in lines if re.search(
        r"remate|aviso\s+de\s+remate|expediente|finca|juzgado|tribunal|juez", l, re.IGNORECASE
    ))
    return matched >= 2 and legal_indicators == 0


def has_edicto_only(text: str) -> bool:
    text_upper = text.upper()
    has_edicto = bool(re.search(r"\bEDICTO\b", text_upper))
    if not has_edicto:
        return False
    has_remate = bool(re.search(r"REMATE|SUBASTA", text_upper))
    return has_edicto and not has_remate


def check_mandatory_fields(fields_found: set) -> tuple[list[str], list[str]]:
    strong_present = STRONG_FIELDS & fields_found
    medium_present = MEDIUM_FIELDS & fields_found
    missing_strong = sorted(STRONG_FIELDS - fields_found)
    missing_medium = sorted(MEDIUM_FIELDS - fields_found)

    fields_present = strong_present | medium_present
    weak_present = WEAK_FIELDS & fields_found
    fields_present |= weak_present

    strong_names = {"expediente": "expediente", "finca": "finca", "finca_matr": "finca",
                    "precio_base": "base", "base": "base"}
    required_labels = {"expediente", "finca", "finca_matr", "precio_base", "base"}
    critical_missing = [f for f in required_labels if f not in fields_found]

    return sorted(s for s in fields_present), critical_missing


def check_field_co_occurrence(fields_found: set) -> list[str]:
    warnings = []
    for group_a, group_b in FIELD_CO_OCCURRENCE:
        if group_a & fields_found and not (group_b & fields_found):
            a_name = next(iter(group_a))
            b_name = next(iter(group_b))
            warnings.append(f"{a_name} presente pero no {b_name}")
    return warnings


def min_strong_fields_rule(fields_found: set) -> bool:
    strong_present = STRONG_FIELDS & fields_found
    medium_present = MEDIUM_FIELDS & fields_found
    return len(strong_present) >= 1 or len(medium_present) >= 2
