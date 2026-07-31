"""
FASE 4.3 — Real Data Validation Pipeline

Validates the full pipeline (Assembly → OCR → Mapping → Segmentation → Continuity)
against real Panama images and Colombia PDF data.
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# ── Load env ────────────────────────────────────────────────────────────────
ENV_PATH = Path("backend/.env")
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# ── Imports ─────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / "backend" / ".env")

from backend.app.v2.document.assembly import DocumentAssembly
from backend.app.v2.document.models import SourceType
from backend.app.v2.document.sequence import SequenceDetector
from backend.app.v2.ocr.client import VisionClient, VisionClientConfig
from backend.app.v2.ocr.processor import OCRProcessor
from backend.app.v2.ocr.mapper import OCRMapper
from backend.app.v2.ocr.models import OCRDocument
from backend.app.v2.segmenter.engine import SegmentationEngine
from backend.app.v2.segmenter.continuity import ContinuityEngine
from backend.app.v2.segmenter.models import (
    AvisoFragment, DetectedAviso, BoundingBox,
)

# ── Paths ────────────────────────────────────────────────────────────────────
PRUEBAS_DIR = Path("C:/Users/user/Documents/pruebas")
COLOMBIA_PDF = Path("C:/Users/user/Documents/SEJURE_28_JULIO_2025_JANETH_RODRIGUEZ_parte1.pdf")
OUTPUT_DIR = Path(__file__).parent

PANAMA_FILES = sorted(str(p) for p in PRUEBAS_DIR.glob("*.jpg"))
PANAMA_IMAGE_BYTES = {p: Path(p).read_bytes() for p in PANAMA_FILES}

# ── Helpers ──────────────────────────────────────────────────────────────────


def write_json(data: dict, name: str):
    path = OUTPUT_DIR / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  -> saved {path.name}")


def print_sep(title: str):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


# ── 1. DocumentAssembly ─────────────────────────────────────────────────────


def validate_assembly():
    print_sep("1. DocumentAssembly — Panama")
    da = DocumentAssembly()
    source = da.assemble(PANAMA_FILES, country="PA")
    print(f"  Source type : {source.source_type.value}")
    print(f"  Total files : {source.total_files}")
    print(f"  Total pages : {source.total_pages}")
    for p in source.pages:
        positions = [f.page_position for f in p.fragments]
        print(f"    Page {p.page_number}: {p.page_type} - fragments: {positions}")

    issues = []
    if source.total_pages == 6:
        issues.append("MAX_ISSUE: 6 pages detected for 6 images (all 'full'). "
                       "Expected 3 pages (top+bottom pairs). Files lack 'sup'/'inf' keywords.")
    if all(f.page_position == "full" for p in source.pages for f in p.fragments):
        issues.append("POSITION_ISSUE: All fragments classified as 'full'. No top/bottom detection.")

    write_json(source.to_dict(), "panama_assembly.json")

    print_sep("1. DocumentAssembly — Colombia")
    co_source = da.assemble([str(COLOMBIA_PDF)], country="CO")
    print(f"  Source type : {co_source.source_type.value}")
    print(f"  Total pages : {co_source.total_pages}")
    write_json(co_source.to_dict(), "colombia_assembly.json")
    if co_source.source_type in (SourceType.COLOMBIA_PDF_TEXT, SourceType.COLOMBIA_PDF_SCANNED):
        pass  # will be detected below

    return source, co_source, issues


# ── 2. OCR ───────────────────────────────────────────────────────────────────


def validate_ocr(panama_source):
    print_sep("2. OCR — Google Vision API")

    api_key = os.environ.get("GOOGLE_VISION_API_KEY", "")
    if not api_key:
        print("  SKIP: GOOGLE_VISION_API_KEY not set")
        return None, None, ["SKIP: No API key for OCR"]

    config = VisionClientConfig(api_key=api_key)
    client = VisionClient(config=config)
    processor = OCRProcessor(client=client)

    print(f"  Vision API available: {processor.is_available()}")
    issues = []

    # Process Panama images
    print(f"\n  Processing {len(PANAMA_FILES)} Panama images...")
    ocr_docs = []
    for fp in PANAMA_FILES:
        fname = Path(fp).name
        print(f"    OCR: {fname} ... ", end="", flush=True)
        try:
            t0 = time.time()
            doc = processor.process_image(fp)
            elapsed = time.time() - t0
            text_len = len(doc.full_text or "")
            pages = len(doc.pages)
            print(f"OK  ({elapsed:.1f}s, {pages} pages, {text_len} chars)")
            ocr_docs.append(doc)
        except Exception as e:
            print(f"ERROR: {e}")
            issues.append(f"OCR_FAILED:{fname}: {e}")
            ocr_docs.append(None)

    # Merge into single OCRDocument
    all_pages = []
    all_text = []
    for i, doc in enumerate(ocr_docs):
        if doc:
            all_pages.extend(doc.pages)
            if doc.full_text:
                all_text.append(f"--- {Path(PANAMA_FILES[i]).name} ---\n{doc.full_text}")
    ocr_document = OCRDocument(pages=all_pages, full_text="\n\n".join(all_text))

    # Save
    ocr_summary = {
        "total_pages": len(all_pages),
        "total_chars": len(all_pages[0].text) if all_pages else 0,
        "page_sizes": [(p.width, p.height) for p in all_pages],
    }
    write_json(ocr_summary, "panama_ocr_summary.json")
    if all_pages:
        sample = {"page_1_text": all_pages[0].text[:1000]}
        write_json(sample, "panama_ocr_sample.json")

    return processor, ocr_document, issues


# ── 3. Segmentation ──────────────────────────────────────────────────────────


def validate_segmentation(ocr_document: OCRDocument):
    print_sep("3. Segmentation")

    if ocr_document is None:
        return None, ["SKIP: No OCR document for segmentation"]

    engine = SegmentationEngine()
    try:
        t0 = time.time()
        segmented = engine.segment(ocr_document)
        elapsed = time.time() - t0
    except Exception as e:
        print(f"  ERROR: {e}")
        return None, [f"SEGMENTATION_FAILED: {e}"]

    print(f"  Pages      : {segmented.total_pages}")
    print(f"  Avisos     : {segmented.total_avisos}")
    print(f"  Avg conf   : {segmented.average_confidence}")

    issues = []
    for page in segmented.pages:
        cols = len(page.columns)
        avisos = len(page.avisos)
        print(f"    Page {page.page_number}: {cols} columns, {avisos} avisos")
        if cols == 0:
            issues.append(f"NO_COLUMNS: Page {page.page_number} has 0 columns")
        for aviso in page.avisos:
            text_preview = aviso.full_text[:150].replace("\n", " ")
            print(f"      Aviso ({aviso.confidence:.2f}): {text_preview}...")

    write_json(segmented.to_dict(), "panama_segmented.json")
    return segmented, issues


# ── 4. Continuity ────────────────────────────────────────────────────────────


def validate_continuity(source, segmented):
    print_sep("4. Continuity Engine")

    if segmented is None:
        return None, ["SKIP: No segmented data for continuity"]

    # Build AvisoFragments from segmented pages + assembly page positions
    fragments: list[AvisoFragment] = []
    page_map = {p.page_number: p for p in source.pages}

    issues = []
    for sp in segmented.pages:
        doc_page = page_map.get(sp.page_number)
        if not doc_page:
            issues.append(f"NO_SOURCE_PAGE: Page {sp.page_number} has no assembly info")
            continue
        for aviso in sp.avisos:
            pos = doc_page.fragments[0].page_position if doc_page.fragments else "full"
            frag = AvisoFragment(
                source_image=doc_page.fragments[0].path if doc_page.fragments else "",
                page_number=sp.page_number,
                position=pos,
                bbox=aviso.bbox,
                confidence=aviso.confidence,
                has_header=bool(aviso.header_text),
                trailing_text=aviso.full_text[-100:] if aviso.full_text else "",
                leading_text=aviso.full_text[:100] if aviso.full_text else "",
                ends_with_hyphen=aviso.full_text.rstrip().endswith("-") if aviso.full_text else False,
            )
            fragments.append(frag)

    print(f"  Fragments : {len(fragments)}")
    print(f"  Positions : {[f.position for f in fragments]}")

    engine = ContinuityEngine()
    completed = engine.detect_continuity(fragments)
    print(f"  Complete  : {len(completed)}")
    for c in completed:
        print(f"    {'[RECONSTRUCTED]' if c.is_reconstructed else '[SINGLE]'} "
              f"type={c.aviso_type} conf={c.confidence:.2f} "
              f"frags={c.fragment_count} signals={c.continuity_signals}")
        print(f"      text: {c.text[:200].replace(chr(10), ' ')}")

    if all(f.position == "full" for f in fragments):
        issues.append("CONTINUITY_SKIPPED: All fragments are 'full', no top/bottom matching possible")

    write_json([c.to_dict() for c in completed], "panama_continuity.json")
    return completed, issues


# ── 5. Colombia pipeline ────────────────────────────────────────────────────


def validate_colombia():
    print_sep("5. Colombia — PDF Analysis")

    if not COLOMBIA_PDF.exists():
        print(f"  SKIP: File not found: {COLOMBIA_PDF}")
        return None, ["SKIP: Colombia PDF not found"]

    from backend.app.v2.document.assembly import PDFAnalyzer
    analyzer = PDFAnalyzer()
    try:
        pdf_type = analyzer.analyze(str(COLOMBIA_PDF))
    except Exception as e:
        print(f"  ERROR: {e}")
        return None, [f"PDF_ANALYSIS_FAILED: {e}"]

    print(f"  PDF type  : {pdf_type}")
    print(f"  Size      : {COLOMBIA_PDF.stat().st_size / 1024:.0f} KB")

    issues = []
    if pdf_type == "pdf_text":
        print("  -> Has text layer. No OCR needed. Ready for direct text extraction.")
    elif pdf_type == "pdf_scanned":
        print("  -> Scanned PDF. OCR required before segmentation.")
        # Check if PyMuPDF available for page rendering
        try:
            import fitz
            print("  -> PyMuPDF available for PDF-to-image conversion")
        except ImportError:
            issues.append("NO_PYMUPDF: Cannot render scanned PDF pages for OCR")
    elif pdf_type == "unknown":
        issues.append("PDF_UNKNOWN: PDFAnalyzer returned 'unknown' (PyMuPDF may be missing)")

    metadata = {
        "path": str(COLOMBIA_PDF),
        "size_bytes": COLOMBIA_PDF.stat().st_size,
        "pdf_type": pdf_type,
    }
    write_json(metadata, "colombia_pdf_analysis.json")
    return pdf_type, issues


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    print()
    print("#" * 60)
    print("  FASE 4.3 — Real Data Pipeline Validation")
    print("#" * 60)
    print(f"  Panama  : {len(PANAMA_FILES)} images in {PRUEBAS_DIR}")
    print(f"  Colombia: {COLOMBIA_PDF}")

    all_issues: list[str] = []

    # 1. Assembly
    panama_source, colombia_source, assembly_issues = validate_assembly()
    all_issues.extend(assembly_issues)

    # 2. OCR
    processor, ocr_document, ocr_issues = validate_ocr(panama_source)
    all_issues.extend(ocr_issues)

    # 3. Segmentation
    segmented, seg_issues = validate_segmentation(ocr_document)
    all_issues.extend(seg_issues)

    # 4. Continuity
    completed, cont_issues = validate_continuity(panama_source, segmented)
    all_issues.extend(cont_issues)

    # 5. Colombia
    colombia_result, colombia_issues = validate_colombia()
    all_issues.extend(colombia_issues)

    # ── Summary metrics ─────────────────────────────────────────────────────
    print_sep("SUMMARY — Metrics & Issues")

    metrics = {
        "panama": {
            "assembly": {
                "source_type": panama_source.source_type.value if panama_source else "N/A",
                "total_pages": panama_source.total_pages if panama_source else 0,
                "total_files": panama_source.total_files if panama_source else 0,
                "pages_detected": len(panama_source.pages) if panama_source else 0,
            },
            "ocr": {
                "pages_processed": len(ocr_document.pages) if ocr_document else 0,
                "total_chars": len(ocr_document.full_text or "") if ocr_document else 0,
            },
            "segmentation": {
                "total_pages": segmented.total_pages if segmented else 0,
                "total_avisos": segmented.total_avisos if segmented else 0,
                "avg_confidence": segmented.average_confidence if segmented else 0.0,
                "columns_per_page": [
                    len(p.columns) for p in segmented.pages
                ] if segmented else [],
                "avisos_per_page": [
                    p.total_avisos for p in segmented.pages
                ] if segmented else [],
            },
            "continuity": {
                "complete_avisos": len(completed) if completed else 0,
                "reconstructed": sum(1 for c in (completed or []) if c.is_reconstructed),
            },
        },
        "colombia": {
            "pdf_type": colombia_result if colombia_result else "N/A",
            "needs_ocr": colombia_result == "pdf_scanned" if colombia_result else "unknown",
        },
        "issues": all_issues,
        "issue_count": len(all_issues),
    }

    write_json(metrics, "validation_metrics.json")

    print(f"\n  Metrics saved: {len(all_issues)} issues found")
    for i, issue in enumerate(all_issues, 1):
        print(f"    [{i}] {issue}")

    print()
    print("  Done.")

    return metrics


if __name__ == "__main__":
    main()
