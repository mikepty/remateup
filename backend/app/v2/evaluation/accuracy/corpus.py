"""FASE 13 — Corpus Estadístico Real (Partes 1 y 2).

Reúne TODOS los documentos reales existentes (uploads, ocr cache, samples,
parser_validation, golden dataset) y calcula frecuencias estadísticas por país:

  headers, etiquetas, palabras, expresiones, formatos monetarios, fechas,
  expedientes, matrículas, fincas, juzgados, municipios, provincias, porcentajes.

PA siempre primero (Panamá First). Nunca inventa patrones: solo mide los
textos reales. Determinista y auditable.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parents[4]
UPLOADS_DIR = REPO_ROOT / "backend" / "data" / "uploads"
OCR_CACHE = MODULE_DIR.parent / "production" / "output" / "real_ocr_texts.json"
SAMPLES_DIR = MODULE_DIR.parent / "production" / "samples"
PARSER_VALIDATION = REPO_ROOT / "evaluation" / "parser_validation"
GOLDEN_PATH = REPO_ROOT / "evaluation" / "golden_dataset" / "records.json"
AVISO_POR_AVISO = MODULE_DIR.parent / "production" / "output" / "aviso_por_aviso.json"
REAL_BENCHMARK = MODULE_DIR.parent / "production" / "output" / "real_benchmark.json"

PA_IMAGES = [
    "21ce358d_1.jpg", "21ce358d_2.jpg", "5b48a468_1.jpg", "9a1ef910_1.jpg",
    "9a1ef910_2.jpg", "c84594ff_1.jpg", "c84594ff_2.jpg", "dfe0e387_1.jpg",
    "dfe0e387_2.jpg", "IMG-20260710-WA0014.jpg", "IMG-20260710-WA0018.jpg",
    "imagen1.jpg", "imagen2.jpg", "afk.png",
]
CO_PDFS = [
    "SEJURE_28_JULIO_2025_JANETH_RODRIGUEZ_parte1.pdf",
    "SEJURE_28_JULIO_2025_JANETH_RODRIGUEZ_parte2.pdf",
    "SEJURE_28_JULIO_2025_JANETH_RODRIGUEZ_parte3.pdf",
    "19e7c816_1.pdf",
    "848e75e1_1.pdf",
]

_HEADER_PATTERNS = [
    re.compile(r"AVISO\s+DE\s+REMATE\s+JUDICIAL", re.I),
    re.compile(r"AVISO\s+DE\s+REMATE", re.I),
    re.compile(r"EDICTO\s+EMPLAZATORIO", re.I),
    re.compile(r"AVISO\s+P[ÚU]BLICO", re.I),
    re.compile(r"REMATE\s+JUDICIAL", re.I),
]

_LABEL_PATTERNS = [
    re.compile(r"EXPEDIENTE|EXPE\.?", re.I),
    re.compile(r"DEMANDANTE|ACTOR|EJECUTANTE", re.I),
    re.compile(r"DEMANDADO|DEUDOR|EJECUTADO", re.I),
    re.compile(r"JUZGADO", re.I),
    re.compile(r"FINCA", re.I),
    re.compile(r"MATR[ÍI]CULA", re.I),
    re.compile(r"AVAL[ÚU]O", re.I),
    re.compile(r"BASE\s+(?:DEL\s+)?REMATE|PRECIO\s+BASE|VALOR\s+BASE|BASE\s*:", re.I),
    re.compile(r"FECHA\s+DE\s+REMATE", re.I),
    re.compile(r"HORA", re.I),
    re.compile(r"LUGAR", re.I),
    re.compile(r"MUNICIPIO", re.I),
    re.compile(r"PROVINCIA", re.I),
    re.compile(r"FIANZA", re.I),
    re.compile(r"PORCENTAJE", re.I),
    re.compile(r"FOLIO\s+REAL", re.I),
    re.compile(r"C[ÓO]DIGO\s+DE\s+UBICACI[ÓO]N", re.I),
    re.compile(r"AVAL[ÚU]O\s+COMERCIAL", re.I),
]

_MONEY_RE = re.compile(r"(?:\$\s*|\$|B\s*/\s*\.?\s*|\$?\s*B/?\s*)([\d]{1,3}(?:[.,][\d]{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2}))")
_DATE_RE = re.compile(
    r"\b\d{1,2}\s+DE\s+[A-ZÁÉÍÓÚÑ]{3,}\s+DE\s+\d{4}\b|"
    r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|"
    r"\b\d{1,2}\s*/\s*[A-Za-z]{3,}\s*/\s*\d{4}\b|"
    r"\b\d{1,2}\s*-\s*[A-Za-z]{3,}\s*-\s*\d{4}\b",
    re.I,
)
_EXPEDIENTE_RE = re.compile(
    r"(?:EXPEDIENTE|EXPE\.?|EXP\.?|NEGOCIO|E\.J\.?E\.?|E\s*-?)\s*(?:N[°º.]?\s*)?"
    r"([0-9]{3,}[0-9\-\s/]{2,})",
    re.I,
)
_MATRICULA_RE = re.compile(r"MATR[ÍI]CULA[^A-Za-zÁÉÍÓÚÑ]*([0-9]{2,3}\s*-\s*[0-9]{3,})", re.I)
_FINCA_RE = re.compile(
    r"(?:FINCA\s+(?:N[°º.]?\s*|N[UÚ]MERO\s*)?|FOLIO\s+REAL\s+N[°º.]?\s*)"
    r"([0-9]{3,}[0-9,\s\-\/]*)",
    re.I,
)
_JUZGADO_RE = re.compile(
    r"JUZGADO\s+[A-ZÁÉÍÓÚÑ'°0-9.\"]+\s+(?:DE\s+)?(?:CIRCUITO|MUNICIPAL|PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[ÉE]PTIMO|OCTAVO|NOVENO|D[ÉE]CIMO|UNDECIMO|D[ÉE]CIMO\s+OCTAVO)[A-ZÁÉÍÓÚÑ\s,.\"']*",
    re.I,
)
_PCT_RE = re.compile(r"\b\d{1,3}\s*(?:%|por\s+ciento|porciento)\b", re.I)
_PCT_FRACTION_RE = re.compile(r"\b(\d+)\s*/\s*(\d+)\b")

_MONTHS = {"ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
           "AGOSTO", "SEPTIEMBRE", "SETIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"}


@dataclass
class CorpusDocument:
    document_id: str
    country: str
    source: str
    text: str
    avisos: list[str] = field(default_factory=list)
    ground_truth: Optional[dict] = None

    @property
    def chars(self) -> int:
        return len(self.text)


def _load_ocr_cache() -> dict:
    if OCR_CACHE.exists():
        try:
            return json.loads(OCR_CACHE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _page_markers(text: str) -> list[str]:
    parts = re.split(r"--- PÁGINA \d+ ---", text)
    return [p.strip() for p in parts if p.strip()]


def _split_avisos(text: str) -> list[str]:
    """Divide texto en avisos usando los marcadores reales EJ ./DIV . (CO) o
    bloques separados por headers (PA)."""
    blocks = re.split(r"^\s*(?:EJ|DIV)\s*\.", text, flags=re.M)
    if len(blocks) > 1:
        return [b.strip() for b in blocks if b.strip()]
    headers = [m for m in re.finditer(r"^\s*(?:AVISO\s+DE\s+REMATE|EDICTO\s+EMPLAZATORIO|AVISO\s+P[ÚU]BLICO)", text, re.M | re.I)]
    if headers:
        out = []
        for i, m in enumerate(headers):
            end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
            block = text[m.start():end].strip()
            if block:
                out.append(block)
        return out
    return [text.strip()] if text.strip() else []


def build_corpus() -> list[CorpusDocument]:
    """Reúne todos los documentos reales conocidos, PA primero."""
    docs: list[CorpusDocument] = []
    cache = _load_ocr_cache()

    # PA: imágenes de periódicos (OCR real cacheado o lectura directa).
    for name in PA_IMAGES:
        path = UPLOADS_DIR / name
        if not path.exists():
            continue
        key = "backend/data/uploads/" + name
        entry = cache.get(key) or {}
        text = entry.get("full_text", "") if isinstance(entry, dict) else str(entry)
        if not text:
            continue
        docs.append(CorpusDocument(
            document_id=name, country="PA", source="upload_ocr",
            text=text, avisos=_split_avisos(text),
        ))

    # PA: avisos canónicos validados por el cliente (samples generados del golden).
    for txt in sorted((SAMPLES_DIR / "pa").glob("*.txt")):
        text = txt.read_text(encoding="utf-8")
        docs.append(CorpusDocument(
            document_id="pa_sample_" + txt.stem, country="PA", source="sample",
            text=text, avisos=_split_avisos(text),
        ))

    # PA: samples de parser_validation (variantes de periódico).
    for txt in sorted((PARSER_VALIDATION / "samples").glob("pa_aviso_*.txt")):
        text = txt.read_text(encoding="utf-8")
        docs.append(CorpusDocument(
            document_id="pv_" + txt.stem, country="PA", source="parser_validation",
            text=text, avisos=_split_avisos(text),
        ))

    # PA: golden records.
    for aviso in _golden_avisos("PA"):
        docs.append(CorpusDocument(
            document_id="golden_pa_" + str(aviso.get("expediente", "")).replace("/", "-"),
            country="PA", source="golden",
            text="\n".join(f"{k}: {v}" for k, v in aviso.items()),
            ground_truth=aviso,
        ))

    # CO: PDFs reales (OCR cache).
    for name in CO_PDFS:
        key = "backend/data/uploads/" + name
        entry = cache.get(key) or {}
        text = entry.get("full_text", "") if isinstance(entry, dict) else str(entry)
        if not text:
            continue
        docs.append(CorpusDocument(
            document_id=name, country="CO", source="upload_ocr",
            text=text, avisos=_split_avisos(text),
        ))

    # CO: samples (16 avisos del golden renderizados).
    for txt in sorted((SAMPLES_DIR / "co").glob("*.txt")):
        text = txt.read_text(encoding="utf-8")
        docs.append(CorpusDocument(
            document_id="co_sample_" + txt.stem, country="CO", source="sample",
            text=text, avisos=_split_avisos(text),
        ))

    # CO: parser_validation samples.
    for txt in sorted((PARSER_VALIDATION / "samples").glob("co_aviso_*.txt")):
        text = txt.read_text(encoding="utf-8")
        docs.append(CorpusDocument(
            document_id="pv_" + txt.stem, country="CO", source="parser_validation",
            text=text, avisos=_split_avisos(text),
        ))

    # CO: golden records.
    for aviso in _golden_avisos("CO"):
        docs.append(CorpusDocument(
            document_id="golden_co_" + str(aviso.get("expediente", "")).replace("/", "-"),
            country="CO", source="golden",
            text="\n".join(f"{k}: {v}" for k, v in aviso.items()),
            ground_truth=aviso,
        ))

    # PA primero (Panamá First).
    return sorted(docs, key=lambda d: (0 if d.country == "PA" else 1, d.document_id))


def _golden_avisos(country: str) -> list[dict]:
    if not GOLDEN_PATH.exists():
        return []
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    out = []
    for suite in data.get("test_suites", []):
        if suite.get("pais") == country:
            out.extend(suite.get("expected_avisos", []))
    return out


def _clean_token(word: str) -> str:
    return re.sub(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ0-9]", "", word)


def _frecuencia(texts: list[str]) -> Counter:
    counter: Counter = Counter()
    for text in texts:
        for word in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", text, re.I):
            counter[_clean_token(word).upper()] += 1
    return counter


def country_statistics(country: str, docs: list[CorpusDocument]) -> dict:
    texts = [d.text for d in docs if d.country == country]
    joined = "\n".join(texts)

    headers: Counter = Counter()
    labels: Counter = Counter()
    words: Counter = _frecuencia(texts)
    expressions: Counter = Counter()
    money_formats: Counter = Counter()
    dates: Counter = Counter()
    expedientes: Counter = Counter()
    matriculas: Counter = Counter()
    fincas: Counter = Counter()
    juzgados: Counter = Counter()
    municipios: Counter = Counter()
    provincias: Counter = Counter()
    porcentajes: Counter = Counter()

    for text in texts:
        for pat in _HEADER_PATTERNS:
            for m in pat.finditer(text):
                headers[m.group(0).upper()] += 1
        for pat in _LABEL_PATTERNS:
            for m in pat.finditer(text):
                labels[pat.pattern] += 1
        for m in _MONEY_RE.finditer(text):
            money_formats[m.group(0).strip()] += 1
        for m in _DATE_RE.finditer(text):
            dates[m.group(0).strip()] += 1
        for m in _EXPEDIENTE_RE.finditer(text):
            expedientes[m.group(1).strip()] += 1
        for m in _MATRICULA_RE.finditer(text):
            matriculas[m.group(1).strip()] += 1
        for m in _FINCA_RE.finditer(text):
            fincas[m.group(1).strip()] += 1
        for m in _JUZGADO_RE.finditer(text):
            juzgados[m.group(0).strip()] += 1
        for m in _PCT_RE.finditer(text):
            porcentajes[m.group(0).strip()] += 1
        for m in _PCT_FRACTION_RE.finditer(text):
            try:
                n, d = int(m.group(1)), int(m.group(2))
                if d in (3, 4, 5, 10, 100) and n <= d:
                    porcentajes[f"{n}/{d}"] += 1
            except ValueError:
                pass
        for word, count in _municipios_provincias(text).items():
            municipios[word] += count

    for word, count in _municipios_provincias(joined).items():
        provincias[word] += count

    return {
        "pais": country,
        "documentos": len([d for d in docs if d.country == country]),
        "avisos": sum(len(d.avisos) for d in docs if d.country == country),
        "caracteres_total": sum(d.chars for d in docs if d.country == country),
        "headers": dict(headers.most_common()),
        "etiquetas": dict(labels.most_common()),
        "palabras_top": dict(words.most_common(100)),
        "expresiones": dict(expressions.most_common()),
        "formatos_monetarios": dict(money_formats.most_common(50)),
        "fechas": dict(dates.most_common(30)),
        "expedientes": dict(expedientes.most_common(60)),
        "matriculas": dict(matriculas.most_common(40)),
        "fincas": dict(fincas.most_common(40)),
        "juzgados": dict(juzgados.most_common(40)),
        "municipios": dict(municipios.most_common(40)),
        "provincias": dict(provincias.most_common(40)),
        "porcentajes": dict(porcentajes.most_common(40)),
    }


_PROVINCIAS_PA = {
    "PANAMA", "PANAMÁ", "HERRERA", "CHIRIQUI", "CHIRIQUÍ", "COCLE", "COLON", "COLÓN",
    "VERAGUAS", "LOS SANTOS", "BOCAS DEL TORO", "DARIEN", "DARÍEN", "COMARCA",
}
_PROVINCIAS_CO = {"CUNDINAMARCA", "TOLIMA", "ANTIOQUIA", "VALLE", "BOYACA", "BOYACÁ"}


def _municipios_provincias(text: str) -> dict[str, int]:
    """Detección determinista de municipios/provincias reales presentes."""
    found: Counter = Counter()
    up = text.upper()
    for prov in _PROVINCIAS_PA | _PROVINCIAS_CO:
        n = len(re.findall(re.escape(prov), up))
        if n:
            found[prov] += n
    for m in re.finditer(r"(?:DEL?\s+MUNICIPIO\s+DE|MUNICIPIO\s+DE|EN\s+EL\s+MUNICIPIO\s+DE)\s+([A-ZÁÉÍÓÚÑ'0-9.\s]{3,40})", up):
        token = m.group(1).strip().strip(" .")
        if token:
            found[token] += 1
    for m in re.finditer(r"\(?\s*([A-ZÁÉÍÓÚÑ]{3,})\s*\)", up):
        pass
    return dict(found)


def statistics_to_markdown(stats: dict) -> str:
    title = stats["pais"]
    lines = [f"## Estadísticas país: {title} (Panamá First)", ""]
    lines.append(f"- Documentos: {stats['documentos']} | Avisos: {stats['avisos']} | Caracteres: {stats['caracteres_total']}")
    for key, header in (("headers", "Headers"), ("etiquetas", "Etiquetas"),
                        ("formatos_monetarios", "Formatos monetarios"),
                        ("fechas", "Fechas"), ("expedientes", "Expedientes"),
                        ("matriculas", "Matrículas"), ("fincas", "Fincas"),
                        ("juzgados", "Juzgados"), ("municipios", "Municipios"),
                        ("provincias", "Provincias"), ("porcentajes", "Porcentajes"),
                        ("palabras_top", "Palabras (top)")):
        lines += ["", f"### {header}", ""]
        items = stats.get(key, {})
        if isinstance(items, dict):
            lines.append("| valor | frecuencia |")
            lines.append("| --- | --- |")
            for value, freq in list(items.items())[:60]:
                lines.append(f"| {value} | {freq} |")
    return "\n".join(lines)
