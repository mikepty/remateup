"""NoticeValidator — determines whether a detected block is a valid judicial notice."""

from typing import Optional

from backend.app.v2.validator.models import (
    Decision, NoticeDecision, RuleResult,
)
from backend.app.v2.validator.production_rules import (
    check_mandatory_fields, check_field_co_occurrence,
    min_strong_fields_rule, detect_header,
    has_publicidad_only, has_edicto_only,
    STRONG_FIELDS, MEDIUM_FIELDS, WEAK_FIELDS, ALL_FIELDS,
)


class NoticeValidator:
    def validate(
        self,
        aviso_id: str,
        text: str,
        fields_found: Optional[dict] = None,
    ) -> NoticeDecision:
        parsed_fields = set(fields_found.keys()) if fields_found else set()
        field_names_lower = {f.lower() for f in parsed_fields}

        decision = NoticeDecision(aviso_id=aviso_id)
        header, header_valid = detect_header(text)

        strong_present = STRONG_FIELDS & field_names_lower
        medium_present = MEDIUM_FIELDS & field_names_lower
        weak_present = WEAK_FIELDS & field_names_lower
        all_present = strong_present | medium_present | weak_present

        applicable = []
        failed = []

        # Rule 1: valid header
        r1 = RuleResult(rule_name="valid_header", weight=0.25)
        r1.passed = header_valid
        r1.details = f"Header: {header[:80] if header else '(none)'}"
        if r1.passed:
            applicable.append(r1)
        else:
            failed.append(r1)

        # Rule 2: not publicidad
        r2 = RuleResult(rule_name="not_publicidad", weight=0.15)
        if has_publicidad_only(text):
            r2.passed = False
            r2.details = "Texto contiene únicamente publicidad"
            failed.append(r2)
        else:
            r2.passed = True
            r2.details = "No es publicidad"
            applicable.append(r2)

        # Rule 3: not edicto
        r3 = RuleResult(rule_name="not_edicto", weight=0.15)
        if has_edicto_only(text):
            r3.passed = False
            r3.details = "Texto contiene únicamente edicto"
            failed.append(r3)
        else:
            r3.passed = True
            r3.details = "No es edicto"
            applicable.append(r3)

        # Rule 4: has at least one strong field
        r4 = RuleResult(rule_name="min_one_strong_field", weight=0.15)
        r4.passed = min_strong_fields_rule(field_names_lower)
        r4.details = f"Strong: {sorted(strong_present)}, Medium: {sorted(medium_present)}"
        if r4.passed:
            applicable.append(r4)
        else:
            failed.append(r4)

        # Rule 5: structural coherence (header + fields)
        r5 = RuleResult(rule_name="structural_coherence", weight=0.15)
        if header_valid and r4.passed:
            r5.passed = True
            r5.details = "Header válido + campos fuertes presentes"
        else:
            r5.passed = False
            r5.details = "Header inválido o sin campos fuertes"
            failed.append(r5)

        # Rule 6: co-occurrence
        r6 = RuleResult(rule_name="field_co_occurrence", weight=0.10)
        warnings = check_field_co_occurrence(field_names_lower)
        r6.passed = len(warnings) == 0
        r6.details = "; ".join(warnings) if warnings else "Sin advertencias"
        if r6.passed:
            applicable.append(r6)
        else:
            failed.append(r6)

        # Rule 7: field count check
        r7 = RuleResult(rule_name="min_field_count", weight=0.05)
        r7.passed = len(all_present) >= 2
        r7.details = f"Campos encontrados: {len(all_present)}"
        if r7.passed:
            applicable.append(r7)
        else:
            failed.append(r7)

        decision.rules_applied = applicable
        decision.rules_failed = failed
        decision.header_detected = header[:80] if header else ""
        decision.header_valid = header_valid

        fields_present, critical_missing = check_mandatory_fields(field_names_lower)
        decision.fields_found = sorted(fields_present)
        decision.fields_missing = sorted(critical_missing)

        structural_ok = r1.passed and r4.passed and r5.passed
        decision.structural_valid = structural_ok

        if not r1.passed and not r4.passed:
            decision.decision = Decision.INVALID
        elif not r1.passed:
            decision.decision = Decision.INVALID
        elif len(failed) >= 4:
            decision.decision = Decision.INVALID
        elif len(all_present) == 0:
            decision.decision = Decision.INVALID
        elif r2.passed is False or r3.passed is False:
            decision.decision = Decision.INVALID
        elif structural_ok and len(all_present) >= 4:
            decision.decision = Decision.VALID
        elif structural_ok:
            decision.decision = Decision.INCOMPLETE
        else:
            decision.decision = Decision.REQUIRES_REVIEW

        return decision
