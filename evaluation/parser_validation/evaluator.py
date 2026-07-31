"""
FASE 5.5 — Parser Engine Real Data Validation

Measures accuracy, precision, recall per field for both parsers.
"""

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.v2.parser.factory import ParserFactory
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.result import ParseResult


SAMPLES_DIR = Path(__file__).parent / "samples"
EXPECTED_DIR = Path(__file__).parent / "expected"
REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_expected(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_value(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip().lower().replace(" ", "").replace(",", "").replace(".", "").replace("-", "").replace("/", "")


def fields_match(expected_val: Any, actual_val: Any) -> bool:
    if expected_val is None and actual_val is None:
        return True
    if expected_val is None or actual_val is None:
        return False
    return normalize_value(expected_val) == normalize_value(actual_val)


def evaluate():
    factory = ParserFactory()
    country_samples = {
        "PA": list(SAMPLES_DIR.glob("pa_*.txt")),
        "CO": list(SAMPLES_DIR.glob("co_*.txt")),
    }

    # country → field → stats
    all_stats: dict[str, dict] = {}
    detailed: list[dict] = []

    for country, sample_files in country_samples.items():
        parser = factory.get_parser(country, "REMATE")
        fields = parser.supported_fields if parser else []
        stats = {f: {"tp": 0, "fp": 0, "fn": 0, "total": 0} for f in fields}

        for sample_path in sorted(sample_files):
            stem = sample_path.stem
            expected_path = EXPECTED_DIR / f"{stem}.json"
            if not expected_path.exists():
                print(f"  SKIP: no expected file for {stem}")
                continue

            text = sample_path.read_text(encoding="utf-8")
            expected = load_expected(expected_path)
            ctx = ParserContext(country=country, document_type="REMATE", text=text)

            if parser:
                results = parser.parse(ctx)
            else:
                results = {}

            sample_detail = {"sample": stem, "country": country, "fields": {}}

            for field in fields:
                actual: ParseResult = results.get(field, ParseResult(field_name=field))
                exp = expected.get(field, {})
                exp_status = exp.get("status", "NOT_FOUND")
                exp_value = exp.get("value")

                actual_status = actual.status
                actual_value = actual.value
                is_found = actual_status == "FOUND"
                should_find = exp_status == "FOUND"

                if should_find and is_found and fields_match(exp_value, actual_value):
                    stats[field]["tp"] += 1
                elif should_find and not is_found:
                    stats[field]["fn"] += 1
                elif not should_find and is_found:
                    stats[field]["fp"] += 1
                elif not should_find and not is_found:
                    pass  # true negative
                stats[field]["total"] += 1

                sample_detail["fields"][field] = {
                    "expected": exp_status,
                    "actual": actual_status,
                    "expected_value": exp_value,
                    "actual_value": actual_value,
                    "match": (should_find == is_found and fields_match(exp_value, actual_value)),
                }

            detailed.append(sample_detail)

        all_stats[country] = stats

    # Compute metrics
    metrics = {}
    for country, stats in all_stats.items():
        metrics[country] = {}
        for field, s in stats.items():
            tp = s["tp"]
            fp = s["fp"]
            fn = s["fn"]
            precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 1.0
            recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
            accuracy = round(tp / max(tp + fn + fp, 1), 4)
            f1 = round(2 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 0.0
            metrics[country][field] = {
                "tp": tp, "fp": fp, "fn": fn,
                "precision": precision,
                "recall": recall,
                "accuracy": accuracy,
                "f1": f1,
            }

    # Print report
    print()
    print("=" * 70)
    print("  PARSER ENGINE — REAL DATA VALIDATION REPORT")
    print("=" * 70)

    for country, country_metrics in metrics.items():
        print(f"\n  Country: {'PANAMA' if country == 'PA' else 'COLOMBIA'}")
        print(f"  {'=' * 50}")
        print(f"  {'Field':<20} {'TP':<5} {'FP':<5} {'FN':<5} {'Prec':<8} {'Recall':<8} {'Acc':<8} {'F1':<8}")
        print(f"  {'-' * 60}")
        for field, m in country_metrics.items():
            print(f"  {field:<20} {m['tp']:<5} {m['fp']:<5} {m['fn']:<5} {m['precision']:<8} {m['recall']:<8} {m['accuracy']:<8} {m['f1']:<8}")
        avg_prec = sum(m["precision"] for m in country_metrics.values()) / len(country_metrics)
        avg_rec = sum(m["recall"] for m in country_metrics.values()) / len(country_metrics)
        avg_acc = sum(m["accuracy"] for m in country_metrics.values()) / len(country_metrics)
        avg_f1 = sum(m["f1"] for m in country_metrics.values()) / len(country_metrics)
        print(f"  {'-' * 60}")
        print(f"  {'AVERAGE':<20} {'':<5} {'':<5} {'':<5} {avg_prec:<8} {avg_rec:<8} {avg_acc:<8} {avg_f1:<8}")

    # Detailed mismatches
    print(f"\n  {'=' * 70}")
    print("  FIELD-LEVEL MISMATCHES")
    print(f"  {'=' * 70}")
    mismatch_count = 0
    for d in detailed:
        for field, info in d["fields"].items():
            if not info["match"]:
                mismatch_count += 1
                print(f"\n  [{d['sample']}] {field}:")
                print(f"    Expected: {info['expected']} = {info['expected_value']}")
                print(f"    Actual:   {info['actual']} = {info['actual_value']}")
    if mismatch_count == 0:
        print("  (none — all fields matched perfectly)")

    # Save report
    report = {
        "metrics": metrics,
        "detailed": detailed,
        "summary": {
            "total_samples": len(detailed),
            "total_mismatches": mismatch_count,
        }
    }
    report_path = REPORTS_DIR / "validation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n  Full report saved: {report_path}")
    print()

    return report


if __name__ == "__main__":
    evaluate()
