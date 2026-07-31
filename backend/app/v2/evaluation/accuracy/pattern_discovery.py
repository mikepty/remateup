"""FASE 13 — Parte 5: Pattern Discovery Engine.

Descubre con frecuencia real (nunca modifica parsers):

- variantes OCR de labels conocidos (N° vs No. vs N ° vs N. ...)
- palabras partidas por guion/hiphen ("JU- DICIAL" -> JUDICIAL)
- palabras unidas sin espacio ("SISTEMAUTOMATIZADO")
- acentos perdidos ("PANAMA" vs "PANAMÁ")
- espacios/giones/símbolos raros
- confusiones dígito/letra 0/O, 1/I, 5/S, 8/B

Determinista: mismos documentos -> mismos resultados. Solo sugiere.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

DIGIT_LETTER_CONFUSIONS = {"0": "O", "1": "I", "5": "S", "8": "B"}

_LABEL_VARIANTS = {
    "N°": r"N\s*[°º.]",
    "N": r"N\s*[°º.]?\s*$",
}

KNOWN_LABELS = [
    "AVISO DE REMATE", "AVISO DE REMATE JUDICIAL", "EDICTO EMPLAZATORIO",
    "EXPEDIENTE", "EXPE", "JUZGADO", "FINCA", "MATRICULA", "MATRÍCULA",
    "AVALUO COMERCIAL", "AVALÚO COMERCIAL", "BASE DEL REMATE", "BASE",
    "FECHA DE REMATE", "FECHA", "DEMANDANTE", "DEMANDADO", "DEMANDA",
    "LUGAR", "MUNICIPIO", "PROVINCIA", "HORA", "FIANZA", "PORCENTAJE",
    "FOLIO REAL", "CODIGO DE UBICACION", "CÓDIGO DE UBICACIÓN", "PRECIO BASE",
    "VALOR BASE", "NEGOCIO", "ACTOR", "DEUDOR", "EJECUTADO", "EJECUTANTE",
]

_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÑáéíóúñ0-9']+", re.I)


@dataclass
class PatternDiscovery:
    pais: str
    variantes_labels: dict[str, Counter] = field(default_factory=dict)
    palabras_partidas: Counter = field(default_factory=Counter)
    palabras_unidas: Counter = field(default_factory=Counter)
    acentos_perdidos: Counter = field(default_factory=Counter)
    simbolos: Counter = field(default_factory=Counter)
    confusiones: Counter = field(default_factory=Counter)

    def to_dict(self) -> dict:
        return {
            "pais": self.pais,
            "variantes_labels": {k: dict(v.most_common(20)) for k, v in self.variantes_labels.items()},
            "palabras_partidas": dict(self.palabras_partidas.most_common(40)),
            "palabras_unidas": dict(self.palabras_unidas.most_common(40)),
            "acentos_perdidos": dict(self.acentos_perdidos.most_common(40)),
            "simbolos": dict(self.simbolos.most_common(30)),
            "confusiones_digito_letra": dict(self.confusiones.most_common(40)),
        }


def _norm_word(w: str) -> str:
    return re.sub(r"[^A-Za-zÁÉÍÓÚÑ]", "", w).upper()


def discover(texts: list[str], pais: str) -> PatternDiscovery:
    pd = PatternDiscovery(pais=pais)
    joined = "\n".join(texts)
    corpus_words: Counter = Counter()
    for w in _WORD_RE.findall(joined):
        corpus_words[_norm_word(w)] += 1
    all_words = set(corpus_words)

    # 1) variantes de labels conocidos (frecuencia de grafía exacta)
    for text in texts:
        for label in KNOWN_LABELS:
            for m in re.finditer(re.escape(label).replace(" ", r"\s+"), text, re.I):
                pd.variantes_labels.setdefault(label, Counter())[m.group(0)] += 1

    # 2) variantes del símbolo N° (N°, N., N °, N" , N )
    for text in texts:
        for m in re.finditer(r"\bN\s*[°º.\"']?\s*(?=\d)", text):
            pd.simbolos["N°-variante:" + repr(m.group(0))] += 1

    # 3) palabras partidas: "AA- BB" donde AA+BB es palabra del corpus
    split_re = re.compile(r"([A-Za-zÁÉÍÓÚÑ]{3,})\s*-\s*([A-Za-zÁÉÍÓÚÑ]{3,})", re.I)
    for text in texts:
        for m in split_re.finditer(text):
            a, b = _norm_word(m.group(1)), _norm_word(m.group(2))
            if a + b in all_words:
                pd.palabras_partidas[f"{a}-{b} -> {a + b}"] += 1

    # 4) palabras unidas: A+B sin espacio donde A y B son palabras del corpus
    for w in all_words:
        if len(w) < 6:
            continue
        for i in range(3, len(w) - 2):
            a, b = w[:i], w[i:]
            if a in all_words and b in all_words and a != b:
                pd.palabras_unidas[f"{a}+{b} -> {a} {b}"] += corpus_words[w]
                break

    # 5) acentos perdidos: sin acento vs con acento en el corpus
    def _accentless(w: str) -> str:
        return (w.replace("Á", "A").replace("É", "E").replace("Í", "I")
                 .replace("Ó", "O").replace("Ú", "U").replace("Ñ", "N"))

    accented = {w for w in all_words if re.search(r"[ÁÉÍÓÚÑ]", w)}
    accentless = {_accentless(w) for w in accented}
    for w in all_words:
        if w in accented or len(w) < 3:
            continue
        if w in accentless:
            with_acc = [x for x in accented if _accentless(x) == w]
            pd.acentos_perdidos[f"{w} (sin acento) -> {with_acc[0]}"] += corpus_words[w]

    # 6) confusiones dígito/letra: palabra con dígito que coincide con otra palabra
    for w in all_words:
        if not re.search(r"[0-9]", w) or len(w) < 3:
            continue
        for digit, letter in DIGIT_LETTER_CONFUSIONS.items():
            variant = w.replace(digit, letter)
            if variant in all_words and variant != w:
                pd.confusiones[f"{w} -> {variant}"] += corpus_words[w]

    # 7) símbolos raros / caracteres no estándar con frecuencia
    for ch in re.findall(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ0-9\s.,:;()/\"'-]", joined):
        pd.simbolos["caracter raro: " + repr(ch)] += 1

    return pd


def discovery_to_markdown(pd: PatternDiscovery) -> str:
    lines = [f"## Pattern Discovery — {pd.pais} (Panamá First)", ""]
    d = pd.to_dict()
    for header, key in (("Variantes de labels", "variantes_labels"),
                        ("Palabras partidas", "palabras_partidas"),
                        ("Palabras unidas", "palabras_unidas"),
                        ("Acentos perdidos", "acentos_perdidos"),
                        ("Símbolos/variantes N°", "simbolos"),
                        ("Confusiones dígito/letra", "confusiones_digito_letra")):
        lines += ["", f"### {header}", ""]
        lines.append("| variante | frecuencia |")
        lines.append("| --- | --- |")
        for value, freq in d.get(key, {}).items():
            lines.append(f"| {value} | {freq} |")
    return "\n".join(lines)
