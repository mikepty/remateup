from typing import Any, Optional


class ParserConfidenceScorer:
    def score(self, parser_result: dict) -> float:
        if not parser_result:
            return 0.0
        fields = parser_result.get("fields", parser_result)
        if not fields or not isinstance(fields, dict):
            return 0.0
        confs = []
        for fname, fdata in fields.items():
            if isinstance(fdata, dict):
                c = fdata.get("confidence", 0)
                s = fdata.get("status", "")
                if c is not None and s == "FOUND":
                    confs.append(float(c))
            elif isinstance(fdata, (int, float)):
                confs.append(float(fdata))
        if not confs:
            return 0.0
        return round(sum(confs) / len(confs), 4)

    def per_field_confidence(self, fields: dict) -> dict[str, float]:
        result = {}
        for fname, fdata in fields.items():
            if isinstance(fdata, dict):
                c = fdata.get("confidence", 0)
                s = fdata.get("status", "")
                if s == "FOUND" and c is not None:
                    result[fname] = round(float(c), 4)
                else:
                    result[fname] = 0.0
            else:
                result[fname] = 0.0
        return result
