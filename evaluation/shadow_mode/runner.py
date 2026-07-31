import json
import time
from pathlib import Path
from typing import Callable

from .comparator import generate_report, compare_documents


class ShadowModeRunner:
    def __init__(self, pipeline_v1: Callable, pipeline_v2: Callable):
        self.pipeline_v1 = pipeline_v1
        self.pipeline_v2 = pipeline_v2
        self.results_v1 = {}
        self.results_v2 = {}
        self.timings_v1 = {}
        self.timings_v2 = {}

    def run_on_document(self, doc_id: int, doc_paths: list[str], pais: str):
        t0 = time.time()
        try:
            result_v1 = self.pipeline_v1(doc_paths, pais)
            self.results_v1[doc_id] = result_v1
        except Exception as e:
            result_v1 = {"error": str(e)}
            self.results_v1[doc_id] = []
        self.timings_v1[doc_id] = time.time() - t0

        t0 = time.time()
        try:
            result_v2 = self.pipeline_v2(doc_paths, pais)
            self.results_v2[doc_id] = result_v2
        except Exception as e:
            result_v2 = {"error": str(e)}
            self.results_v2[doc_id] = []
        self.timings_v2[doc_id] = time.time() - t0

        print(f"Document {doc_id}: V1={len(self.results_v1[doc_id])} avisos ({self.timings_v1[doc_id]:.1f}s), "
              f"V2={len(self.results_v2[doc_id])} avisos ({self.timings_v2[doc_id]:.1f}s)")

    def run_on_dataset(self, dataset: list[dict]):
        for item in dataset:
            self.run_on_document(
                doc_id=item["doc_id"],
                doc_paths=item["paths"],
                pais=item["pais"],
            )

    def get_report(self) -> str:
        return generate_report(self.results_v1, self.results_v2)

    def save_results(self, output_dir: str):
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        with open(out / "v1_results.json", "w", encoding="utf-8") as f:
            json.dump(self.results_v1, f, ensure_ascii=False, indent=2, default=str)
        with open(out / "v2_results.json", "w", encoding="utf-8") as f:
            json.dump(self.results_v2, f, ensure_ascii=False, indent=2, default=str)
        with open(out / "timings.json", "w", encoding="utf-8") as f:
            json.dump({"v1": self.timings_v1, "v2": self.timings_v2}, f, ensure_ascii=False, indent=2)

        report = self.get_report()
        with open(out / "comparison_report.md", "w", encoding="utf-8") as f:
            f.write(report)

        print(f"Results saved to {output_dir}")
