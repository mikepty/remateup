"""DuplicateDetector — detects duplicate notices within and across documents."""

import difflib
from typing import Optional

from backend.app.v2.validator.models import DuplicateInfo, DuplicateLevel


class DuplicateDetector:
    def __init__(self):
        self._seen_notices: list[dict] = []

    def reset(self):
        self._seen_notices = []

    def export_state(self) -> list[dict]:
        """Devuelve la memoria de avisos vistos, lista para persistir (ej. en DB)
        y restaurar más tarde con load_state(). Permite deduplicación entre
        sesiones/días sin que este módulo dependa de ningún almacenamiento
        concreto: quien lo use decide dónde guardar el resultado."""
        return [dict(n) for n in self._seen_notices]

    def load_state(self, state: Optional[list[dict]]) -> None:
        """Restaura memoria de avisos vistos previamente exportada con
        export_state(), por ejemplo la de una corrida anterior. Sustituye
        (no acumula sobre) el estado actual."""
        self._seen_notices = [dict(n) for n in state] if state else []

    def check(
        self,
        aviso_id: str,
        fields_found: dict,
        text: str,
        bbox: Optional[dict] = None,
    ) -> DuplicateInfo:
        info = DuplicateInfo()

        field_names = {k.lower(): v for k, v in fields_found.items()}
        current_fv = self._field_values(field_names)

        for seen in self._seen_notices:
            matched_on = []
            seen_fv = seen["field_values"]
            seen_text = seen.get("text", "")

            # Same expediente
            if current_fv.get("expediente") and seen_fv.get("expediente"):
                if current_fv["expediente"] == seen_fv["expediente"]:
                    matched_on.append("expediente")

            # Same finca
            for f in ("finca", "finca_matr"):
                if current_fv.get(f) and seen_fv.get(f):
                    if current_fv[f] == seen_fv[f]:
                        matched_on.append("finca")

            # Same base
            for f in ("precio_base", "base"):
                if current_fv.get(f) and seen_fv.get(f):
                    if current_fv[f] == seen_fv[f]:
                        matched_on.append("base")

            # Same bbox
            if bbox and seen.get("bbox"):
                if (bbox.get("x0") == seen["bbox"].get("x0") and
                        bbox.get("y0") == seen["bbox"].get("y0")):
                    matched_on.append("bbox")

            if not matched_on:
                continue

            # Text similarity for near-identical
            text_sim = 0.0
            if seen_text and text:
                text_sim = difflib.SequenceMatcher(
                    None, text.lower(), seen_text.lower()
                ).ratio()

            if len(matched_on) >= 2 or text_sim > 0.9:
                info.level = DuplicateLevel.DUPLICATED
                info.matched_on = matched_on
                info.matched_notice_id = seen.get("id", "")
                info.similarity = round(max(text_sim, 0.5), 4)
                break
            elif len(matched_on) >= 1:
                info.level = DuplicateLevel.LIKELY_DUPLICATED
                info.matched_on = matched_on
                info.matched_notice_id = seen.get("id", "")
                info.similarity = round(text_sim, 4)

        self._seen_notices.append({
            "id": aviso_id,
            "field_values": current_fv,
            "text": text,
            "bbox": bbox,
        })

        return info

    def _field_values(self, field_names: dict) -> dict:
        result = {}
        for fname, fdata in field_names.items():
            if isinstance(fdata, dict):
                val = fdata.get("value", "")
            else:
                val = str(fdata)
            if val and str(val).strip():
                result[fname] = str(val).strip()
        return result
