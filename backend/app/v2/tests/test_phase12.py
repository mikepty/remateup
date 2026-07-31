"""FASE 12 — Tests: segmentación real de PDFs, runner aviso-por-aviso, trace,
AI feedback, knowledge impact, field quality, dashboard, benchmark, auditoría.

No existing test is removed; all previous phases must keep passing.

Requiere GOOGLE_VISION_API_KEY (backend/.env) para los tests de OCR real;
sin la clave, esos tests se saltan (pytest.mark.skipif).
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from dotenv import load_dotenv

load_dotenv("backend/.env")

from backend.app.v2.evaluation.production.avisos import (
    AvisoRunner,
    compare_aviso,
    extract_pages,
    find_expediente,
    find_aviso_region,
    split_avisos,
)
from backend.app.v2.evaluation.production.trace import build_trace, _knowledge_applied
from backend.app.v2.evaluation.production.ai_feedback import AIFeedbackTracker
from backend.app.v2.evaluation.production.knowledge_impact import generate_knowledge_impact_report
from backend.app.v2.evaluation.production.field_quality import generate_field_quality_report
from backend.app.v2.evaluation.production.dashboard import generate_production_dashboard
from backend.app.v2.evaluation.production.benchmark import _field_diffs
from backend.app.v2.evaluation.production.architecture_audit import run_architecture_audit

VISION_AVAILABLE = bool(os.environ.get("GOOGLE_VISION_API_KEY"))
requires_vision = pytest.mark.skipif(not VISION_AVAILABLE, reason="GOOGLE_VISION_API_KEY no disponible")

REAL_PAGE_17 = """FECHA
HORA
DIRECCION
30 - jul
AVALUO
%
BASE
JUZ
CIUDAD
JANETH ALEXANDRA RODRIGUEZ C.C. No. 52.496.297
CR . 12 A No.8 B - 33 9.00 MZ . L LOT . 21 URB .
A.M
VILLA DEL ROCIO DE MOSQUERA
CASA
Patiño Marin y
Omaira Patiño
Marin
DIV . No.2023- 01327 00 Rogers Edilberto Matallana Poveda Vs.Luz Marina Cardenas Hernandez EJ . HP . No.001-
$ 181.080.000
30 - jul
2.00 P.M
DEL MUNICIPIO DE
No
RE
DESCRIPCION
MATRICULA
EXPEDIENTE
RODRIC
52
97
30 - jul
10.00 A.M
CRA . 10 No. 15-24
GRANADA M.
PREDIO LA ESPERANZA
UBICADO EN LA VEREDA EL TRIGO DEL MUNICIPIO DE GUAYABAL DE
SIQUIMA .
PREDIO VILLA
PREDIO
9.00
30 - jul
A.M
YERALDIN DE ESTE MUNICIPIO
PREDIO
236-19480
156-94513
2014-00383 00 BBVA Vs. Robinson Ortiz
RODRIGUEZ
3249
SEJURE
496 297
GUAYABAL DE SIQUIMA CUNDI .
VILLANUEVA CAS .
EJ . HP . No.001- 2019-00058 Jonathan
Castañeda Gaitán Vs.Carmen
Castiblanco de Avila
EJ . HP . No.2017- 00141 00 Banco
206-70603 Agrario de
9.00
CRA . 9 A No.4-53
PREDIO
420-82864
30 - ju AM
Colombia Vs. Flor Useche
EJ . MIX . No.001- 2013-00074.00 Utrahuilca
$ 199.250,000
70
P.M
PITALITO H
$ 2.797.500
70
$ 1.958.250
1 P.M
CURILLO CAQ .
17
Préstamos Hipotecarios
DESDE 10 A 100 MILLONES , TRAMITE INMEDIATO
Plazo I a 10 años Facilidades de Pago
Teléfono 304 4 54 54 64
www.creditofacil.me
"""


def golden_avisos_sample() -> list[dict]:
    path = Path(__file__).resolve().parents[4] / "evaluation" / "golden_dataset" / "records.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for suite in data.get("test_suites", []):
        if suite.get("pais") == "CO":
            return list(suite.get("expected_avisos", []))
    return []


class TestParte1Segmentacion:
    def test_extract_pages_con_marcadores(self):
        text = "--- PÁGINA 1 ---\nhola\n\n--- PÁGINA 2 ---\nmundo"
        pages = extract_pages(text)
        assert [p.pagina for p in pages] == [1, 2]
        assert pages[0].text == "hola"
        assert pages[1].text == "mundo"

    def test_extract_pages_sin_marcadores(self):
        pages = extract_pages("solo texto")
        assert len(pages) == 1
        assert pages[0].pagina == 1

    def test_extract_pages_vacio(self):
        assert extract_pages("") == []

    def test_split_avisos_pagina_real(self):
        blocks = split_avisos(REAL_PAGE_17)
        assert len(blocks) == 4
        assert blocks[0].text.startswith("DIV . No.2023- 01327")
        assert "2023-01327" in blocks[0].text or "2023- 01327" in blocks[0].text
        assert "2019-00058" in blocks[1].text
        assert "2013-00074" in blocks[3].text

    def test_find_expediente_con_espacios(self):
        span = find_expediente("EJ . No.001-2017- 01197 00 BBVA", "2017-01197")
        assert span is not None
        start, end = span
        assert "2017- 01197" in "EJ . No.001-2017- 01197 00 BBVA"[start:end] or "2017-01197" in "EJ . No.001-2017- 01197 00 BBVA"[start:end]

    def test_find_expediente_ausente(self):
        assert find_expediente("no hay expediente", "2017-01197") is None

    def test_find_aviso_region_ancla_bloque(self):
        region = find_aviso_region(REAL_PAGE_17, "2023-01327")
        assert region is not None
        start, end = region
        block_text = REAL_PAGE_17[start:end]
        assert block_text.lstrip().startswith("DIV . No.2023- 01327")
        assert "".join(ch for ch in block_text if ch.isdigit()).find("202301327") >= 0

    def test_anclaje_golden_pagina_real(self):
        spans = {exp: find_expediente(REAL_PAGE_17, exp)
                 for exp in ["2023-01327", "2014-00383", "2019-00058", "2017-00141", "2013-00074"]}
        assert all(v is not None for v in spans.values())


class TestParte2AvisoPorAviso:
    def test_compare_aviso_exacto(self):
        predicted = {
            "expediente": {"value": "2019-00302", "status": "FOUND"},
            "demandante": {"value": "Banco", "status": "FOUND"},
            "demandado": {"value": "Deudor", "status": "FOUND"},
        }
        expected = {"expediente": "2019-00302", "demandante": "Banco", "demandado": "Deudor"}
        c = compare_aviso(predicted, expected, ["expediente", "demandante", "demandado"])
        assert c["tp"] == 3
        assert c["fp"] == 0 and c["fn"] == 0
        assert c["precision"] == 1.0 and c["recall"] == 1.0 and c["f1"] == 1.0

    def test_compare_aviso_con_errores(self):
        predicted = {
            "expediente": {"value": "X", "status": "FOUND"},
            "demandado": {"value": "Deudor", "status": "FOUND"},
        }
        expected = {"expediente": "2019-00302", "demandante": "Banco", "demandado": "Deudor"}
        c = compare_aviso(predicted, expected, ["expediente", "demandante", "demandado"])
        assert c["fp"] == 1 and c["fn"] == 1 and c["tp"] == 1
        assert len(c["errores"]) == 2
        tipos = {e["tipo"] for e in c["errores"]}
        assert tipos == {"FP", "FN"}

    def test_compare_aviso_normaliza_precio(self):
        predicted = {"precio_base": {"value": "$ 181.080.000", "status": "FOUND"}}
        expected = {"precio_base": 181080000.0}
        c = compare_aviso(predicted, expected, ["precio_base"])
        assert c["tp"] == 1

    def test_locate_golden(self, tmp_path):
        pdf = tmp_path / "fake.pdf"
        pdf.write_text("x", encoding="utf-8")
        runner = AvisoRunner(ocr_cache={"fake.pdf": "--- PÁGINA 1 ---\n" + REAL_PAGE_17})
        located, missed = runner.locate_golden("fake.pdf", "CO",
                                               [{"expediente": "2013-00074", "demandante": "Utrahuilca"}])
        assert len(located) == 1
        assert located[0]["pagina"] == 1
        assert "2013-00074" in located[0]["text"]
        assert missed == []


class TestParte3Trace:
    def test_build_trace_completo(self):
        aviso = {
            "documento": "parte1.pdf",
            "aviso_id": "p17_b0",
            "expediente": "2019-00058",
            "pagina": 17,
            "bbox": None,
            "segmento": "chars:10-50",
            "pipeline_result": {
                "country": "CO",
                "total_time_ms": 12.3,
                "fields": {
                    "expediente": {"value": "2019-00058", "status": "FOUND", "confidence": 0.9, "source": "parser"},
                    "lugar": {"value": "X", "status": "FOUND", "confidence": 0.96, "source": "ai",
                              "evidence": [{"method": "rule:regex:abc123def456:v1"}]},
                },
                "ai": {"enabled": True, "ai_fields": ["lugar"], "provider": "zai",
                       "ai_time_ms": 3.1, "cache_hits": 0, "cache_misses": 1,
                       "cost_usd": 0.0, "total_ai_tokens": 100},
                "validation": {"decision": "VALID", "score": 0.9, "fields_found": ["expediente"],
                               "fields_missing": [], "rules_applied": [], "rules_failed": [],
                               "duplicate_info": None},
                "certification": {"all_avisos": [{"decision": "VALID", "confidence": 0.8}]},
            },
            "comparison": {"precision": 1.0, "recall": 0.5, "f1": 0.66, "errores": []},
        }
        t = build_trace(aviso)
        assert t["documento"] == "parte1.pdf"
        assert t["pagina"] == 17
        assert t["bbox"] is None
        assert t["parser"]["pais"] == "CO"
        assert t["validator"]["decision"] == "VALID"
        assert t["certification"]["decision"] == "VALID"
        assert t["ia"]["usada"] is True
        assert t["tiempo_ms"] == 12.3
        assert t["resultado"]["expediente"]["valor"] == "2019-00058"

    def test_knowledge_applied_extrae_reglas(self):
        fields = {
            "finca": {"source": "knowledge", "evidence": [
                {"method": "rule:regex:abcdef123456:v2"}]},
        }
        rules = _knowledge_applied(fields)
        assert rules == [{"campo": "finca", "rule_id": "abcdef123456", "version": 2}]


class TestParte4AIFeedback:
    def test_ingest_audit_y_summary(self):
        tracker = AIFeedbackTracker()
        tracker.ingest_audit_entries([
            {"campo": "juzgado", "modelo": "glm-4.5-flash", "confidence": 1.0,
             "decision": "FOUND", "latencia_ms": 100.0, "documento": "d1", "provider": "zai"},
            {"campo": "fecha_remate", "modelo": "glm-4.5-flash", "confidence": 0.0,
             "decision": "NOT_FOUND", "latencia_ms": 50.0, "documento": "d1", "provider": "zai"},
            {"campo": "lugar", "modelo": "glm-4.5-flash", "confidence": 0.9,
             "decision": "REQUIRES_REVIEW", "latencia_ms": 60.0, "documento": "d1", "provider": "zai"},
        ])
        s = tracker.summary()
        assert s["entries"] == 3
        assert s["aceptados"] == 1
        assert s["rechazados"] == 2
        assert s["corregidos"] == 0
        assert "juzgado" in s["por_campo"]
        assert "glm-4.5-flash" in s["por_modelo"]
        assert s["aprendizaje_automatico"] is False

    def test_found_pero_descartado_es_corregido(self):
        tracker = AIFeedbackTracker()
        result = {
            "document_id": "d1",
            "fields": {"juzgado": {"status": "NOT_FOUND"}},
        }
        tracker.ingest_audit_entries([
            {"campo": "juzgado", "modelo": "m", "confidence": 1.0,
             "decision": "FOUND", "latencia_ms": 10.0, "documento": "d1", "provider": "zai"},
        ], result=result)
        s = tracker.summary()
        assert s["corregidos"] == 1
        assert s["aceptados"] == 0

    def test_summary_vacio(self):
        s = AIFeedbackTracker().summary()
        assert s == {"entries": 0}


class TestParte5KnowledgeImpact:
    def test_reporte_vacio_determinista(self, tmp_path):
        from backend.app.v2.knowledge.repository import KnowledgeRepository

        repo = KnowledgeRepository(db_path=str(tmp_path / "k.db"))
        report = generate_knowledge_impact_report(repository=repo, out_dir=str(tmp_path))
        assert report["total_reglas"] == 0
        assert report["reglas_nunca_usadas_count"] == 0
        assert (tmp_path / "knowledge_impact.json").exists()
        assert (tmp_path / "knowledge_impact.md").exists()

    def test_reporte_con_regla(self, tmp_path):
        from backend.app.v2.knowledge.repository import KnowledgeRepository
        from backend.app.v2.knowledge.models import KnowledgeRule

        repo = KnowledgeRepository(db_path=str(tmp_path / "k2.db"))
        rule = KnowledgeRule(field_name="juzgado", category="label",
                             pattern=r"JUZGADO\s*(\w+)", confidence=0.9, status="APPROVED")
        repo.save_rule(rule)
        report = generate_knowledge_impact_report(repository=repo)
        assert report["total_reglas"] == 1
        entry = report["por_regla"][0]
        assert entry["campo"] == "juzgado"
        assert entry["veces_usada"] == 0
        assert entry["primer_uso_exacto"] is False
        assert entry["pais"] == "N/A"


class TestParte6FieldQuality:
    def test_reporte_por_fuente(self):
        results = [
            {"country": "CO", "document_id": "d1",
             "fields": {
                 "expediente": {"status": "FOUND", "source": "parser"},
                 "lugar": {"status": "FOUND", "source": "ai"},
                 "finca": {"status": "NOT_FOUND", "source": "parser"},
             },
             "validation": {"fields_found": ["expediente"]}},
            {"country": "CO", "document_id": "d2",
             "fields": {"expediente": {"status": "FOUND", "source": "knowledge"}},
             "validation": {"fields_found": ["expediente"]}},
        ]
        report = generate_field_quality_report(results)
        exp = report["por_campo"]["expediente"]
        assert exp["FOUND"] == 2
        assert exp["FOUND_PARSER"] == 1
        assert exp["FOUND_KNOWLEDGE"] == 1
        assert exp["FOUND_VALIDATOR"] == 2
        assert report["por_pais"]["CO"]["lugar"]["FOUND_IA"] == 1
        assert report["por_documento"]["d1"]["expediente"]["FOUND_FINAL"] == 1


class TestParte7Dashboard:
    def test_dashboard_agrega(self):
        results = [
            {"document_id": "d1", "country": "CO", "total_time_ms": 100.0,
             "fields": {"expediente": {"status": "FOUND", "source": "parser"}},
             "ai": {"ai_fields": [], "ai_time_ms": 0.0, "cache_hits": 1, "cache_misses": 0,
                    "total_ai_tokens": 10, "cost_usd": 0.0},
             "validation": {"decision": "VALID", "score": 0.8, "fields_missing": ["finca"],
                            "duplicate_info": None},
             "certification": {"all_avisos": [{"decision": "VALID"}]},
             "stages": {"ocr": {"duration_ms": 90.0}, "parser": {"duration_ms": 10.0}},
             "errors": ["error A"], "warnings": []},
        ]
        d = generate_production_dashboard(results)
        assert d["procesados"]["documentos"] == 1
        assert d["campos"]["total_encontrados"] == 1
        assert d["validator"]["decisiones"] == {"VALID": 1}
        assert d["certification"]["decisiones"] == {"VALID": 1}
        assert d["errores"]["top"] == {"error A": 1}
        assert d["top_campos_faltantes"] == {"finca": 1}
        assert d["health"]["status"] in ("HEALTHY", "ERROR")

    def test_dashboard_escribe_archivos(self, tmp_path):
        generate_production_dashboard([], out_dir=str(tmp_path))
        assert (tmp_path / "production_dashboard.json").exists()
        assert (tmp_path / "production_dashboard.md").exists()


class TestParte8Benchmark:
    def test_field_diffs_solo_diferencias_reales(self):
        p = {"expediente": {"status": "FOUND", "value": "X"}}
        k = {"expediente": {"status": "FOUND", "value": "X"}}
        a = {"expediente": {"status": "FOUND", "value": "X"}}
        assert _field_diffs(p, k, a) == []

    def test_field_diffs_captura_cambios(self):
        p = {"expediente": {"status": "NOT_FOUND", "value": ""}}
        k = {"expediente": {"status": "FOUND", "value": "2019-00302"}}
        a = {"expediente": {"status": "FOUND", "value": "2019-00302"}}
        diffs = _field_diffs(p, k, a)
        assert len(diffs) == 1
        assert diffs[0]["campo"] == "expediente"
        assert diffs[0]["parser"]["status"] == "NOT_FOUND"
        assert diffs[0]["parser_knowledge"]["value"] == "2019-00302"

    def test_field_diffs_captura_campo_nuevo_ia(self):
        p = {}
        k = {}
        a = {"lugar": {"status": "FOUND", "value": "Bogotá"}}
        diffs = _field_diffs(p, k, a)
        assert len(diffs) == 1
        assert diffs[0]["campo"] == "lugar"


class TestParte9ArchitectureAudit:
    def test_audit_responde_todas_las_preguntas(self):
        audit = run_architecture_audit()
        for key in ("modulos_muertos", "codigo_nunca_ejecutado", "clases_nunca_instanciadas",
                    "reglas_nunca_utilizadas", "campos_imposibles", "dependencias_circulares",
                    "productores_sin_consumidores", "consumidores_sin_productores",
                    "alias_redundantes", "validaciones_duplicadas"):
            assert key in audit
        assert audit["modulos_analizados"] > 10

    def test_alias_redundantes_detecta_pares_v1_v2(self):
        audit = run_architecture_audit()
        pairs = {tuple(sorted(a["par"])) for a in audit["alias_redundantes"]}
        assert ("base", "precio_base") in pairs
        assert ("fecha", "fecha_remate") in pairs

    def test_audit_escribe_archivos(self, tmp_path):
        run_architecture_audit(out_dir=str(tmp_path))
        assert (tmp_path / "architecture_audit.json").exists()
        assert (tmp_path / "architecture_audit.md").exists()


@requires_vision
class TestParte1PDFsReales:
    def test_process_pdf_pages_vacio_pero_texto_completo(self):
        """Causa raíz auditada: process_pdf devuelve pages=[] aunque el texto
        real completo (con separadores de página) está en full_text."""
        from backend.app.v2.ocr.processor import OCRProcessor

        pdf = Path(__file__).resolve().parents[3] / "data" / "uploads" / "SEJURE_28_JULIO_2025_JANETH_RODRIGUEZ_parte1.pdf"
        if not pdf.exists():
            pytest.skip("PDF real no disponible")
        doc = OCRProcessor().process_pdf(str(pdf))
        assert len(doc.pages) == 0
        assert len(doc.full_text) > 20000
        pages = extract_pages(doc.full_text)
        assert len(pages) >= 15
        assert all(p.text.strip() for p in pages)

    def test_pdf_real_segmenta_avisos_y_ancla_golden(self):
        from backend.app.v2.ocr.processor import OCRProcessor

        pdf = Path(__file__).resolve().parents[3] / "data" / "uploads" / "SEJURE_28_JULIO_2025_JANETH_RODRIGUEZ_parte1.pdf"
        if not pdf.exists():
            pytest.skip("PDF real no disponible")
        doc = OCRProcessor().process_pdf(str(pdf))
        pages = extract_pages(doc.full_text)
        total_blocks = sum(len(split_avisos(p.text)) for p in pages)
        assert total_blocks > 30
        golden = golden_avisos_sample()
        hits = 0
        for aviso in golden:
            if find_expediente(doc.full_text, aviso.get("expediente", "")) is not None:
                hits += 1
        assert hits >= 15
