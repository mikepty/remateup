# PROJECT HANDOFF — RemateUp V2  (para GPT-5.5)

> Este documento es el **único contexto** que GPT-5.5 recibirá. Fue generado a partir del estado REAL del repositorio en `C:\Users\user\Documents\RemateUp` (commits `2591bfb` y `f9e5d5b` incluidos). **Nada está inventado.** Donde no se pudo verificar, se dice explícitamente.

- **Repo:** `https://github.com/mikepty/remateup.git` (rama `master`), con commit local adicional `f9e5d5b`.
- **Autoridad de los hechos:** todo lo que dice "véase `file:line`" fue leído directamente del árbol. Las secciones marcadas `⚠ INFERIDO` se deducen del código pero no se ejecutaron en este entorno.
- **No se modificó ni generó código** para producir este documento (solo se generaron estos dos archivos).

---

## 1. Resumen Ejecutivo

**Qué es RemateUp.** Sistema (FastAPI + frontend estático) que recibe documentos de periódico (imágenes de página superior/inferior, o PDFs de Colombia), extrae avisos de remate judicial con IA (Gemini 2.5 Flash), los valida contra reglas de negocio del cliente, decide autónomamente si la confianza es suficiente para **subirlos solos** o si deben enviarse a **WhatsApp** para aprobación humana, y registra una auditoría completa de cada paso. (Definición tomada de `README.md:1-31`.)

**Objetivo del sistema.** Automatizar la captura, normalización y carga de avisos de remate judicial Panamá/Colombia, minimizando la intervención humana: solo los avisos de baja confianza o con campos críticos faltantes piden aprobación.

**Estado actual (resumen).**
- **V1 es la pista de producción.** `backend/app/main.py` expone la API en Render; `frontend/public/index.html` es el dashboard en Firebase Hosting. La base V1 (`backend/data/remateup.db`, sqlite local; Postgres gratuito en Render) contiene **39 avisos** (23 PA, 16 CO), **130 eventos de auditoría**, **3 documentos**, **3 aprobaciones**, todos en estado `subido`.
- **V2 es un refactor en construcción** (`backend/app/v2/`) con un pipeline de 14 etapas (`pipeline/runner.py:6-7`), Knowledge Engine, AI Resolver con *policy gate*, y Certification. V2 **no está operativo por bloqueos de entorno** (ver §4/§10/§17): PyMuPDF y psycopg2 no están instalados en `backend/venv`, y `segmenter/models.py:13` lanza `NameError`.
- **IA.** En producción (Render) solo está configurada `GEMINI_API_KEY` (`render.yaml:10-11`), **no** `GOOGLE_VISION_API_KEY`, ni `ANTHROPIC_API_KEY`, ni `CLAUDE_MODEL`. `MOTOR_IA` default `auto` = "Gemini primero, Claude de respaldo si falla". Como Claude no tiene key en prod, el respaldo cae en el *fallback* determinista/regex local (`parser/ai/providers.py:324 LocalResolver`). No hay pruebas reales de llamada a Gemini en este entorno (bloquea dominios externos).
- **Producción.** Deploy continuo: push a `master` → Render redeploya backend (`render.yaml`) y Firebase despliega hosting (`frontend/firebase.json` + `frontend/.firebaserc`). No hay CI/CD de GitHub Actions (`.github/workflows/` no existe).

**Nivel de madurez.**
- V1 (producción): **funcional y usado.** Extracción por IA probada con datos reales de periódico (`README.md:35-41`); detección de duplicados, decisión de confianza y auditoría probadas. El fix de fianza/mínimo (`2591bfb`) verificado localmente sobre `doc104` (fianza/monto 0 discrepancias, 100% campos).
- V1 (limitaciones): OCR de imágenes escaneadas requiere Google Vision (no configurado en prod) → los PDFs de Colombia se extraen vía texto (`pypdf`/`PyMuPDF`); las imágenes de Panamá dependen de Google Vision **no configurado** en prod (fallback desconocido).
- V2: **construido pero no validado end-to-end** (bloqueos de entorno, ver §4).

**Arquitectura utilizada.** V1 = pipeline lineal modular (`backend/app/pipeline/*.py`) + FastAPI (`backend/app/main.py`, routers) + sqlite/postgres (`backend/app/database.py`, SQLAlchemy 2.0). V2 = pipeline orquestado de 14 etapas (`backend/app/v2/pipeline/runner.py`) con módulos independientes (`document/`, `ocr/`, `segmenter/`, `parser/`, `knowledge/`, `normalization/`, `confidence/`, `validator/`, `certification/`). Frontend = **un solo archivo** `frontend/public/index.html` (HTML + CSS + JS inline, 1057 líneas; sin archivos JS/TS separados — `git ls-files frontend` devuelve 4 archivos: `public/index.html`, `firebase.json`, `.firebaserc`, `public/favicon.svg`).

**Tecnologías.**
| Capa | Tecnología | Archivo/ubicación |
|---|---|---|
| Backend | Python 3.12, FastAPI, uvicorn | `render.yaml:6-8`, `backend/requirements.txt` |
| ORM | SQLAlchemy 2.0 | `backend/app/database.py`, `backend/app/models.py` |
| DB prod | PostgreSQL (Render free) | `render.yaml:18-21`, var `DATABASE_URL` |
| DB dev | SQLite | `backend/app/config.py:21` (fallback `sqlite:///.../remateup.db`) |
| IA (extracción) | Gemini 2.5 Flash (prod), Claude (fallback) | `backend/app/pipeline/extraction.py`, `backend/app/v2/parser/ai/policy.py` |
| IA (OCR) | Google Vision (NO key en prod) | `backend/app/pipeline/ocr_vision.py` |
| PDF | pypdf, PyMuPDF (falta instalar) | `backend/requirements.txt:10,14` |
| Excel | openpyxl | `backend/requirements.txt:11`; export en `backend/app/routers/exports.py:86/138` |
| Frontend | HTML/CSS/JS inline + Firebase Hosting | `frontend/public/index.html` |
| Infra | Render (backend+postgres) + Firebase (hosting) | `render.yaml`, `frontend/firebase.json` |
| Mensajería | WhatsApp bridge (Baileys, node) | README:67-77; var `WHATSAPP_BRIDGE_URL`/`WHATSAPP_APROBADOR` (NO configuradas en Render) |
| Tests | pytest (sin config) | no hay `pytest.ini`/`conftest`; 31 archivos, 621 pass / 2 fail / 12 error (ver §17) |

**Estado de producción.** Deploy activo vía push a `master`. Últimos deploys: fianza-fix `2591bfb` (en producción, verificado local) y FASE-14 skeleton `f9e5d5b` (en producción). Backend en `https://remateup-backend.onrender.com` (`frontend/public/index.html:253`). Free tier → "se duerme" por inactividad y se despierta al recibir tráfico (`frontend/public/index.html:269`).

**Estado de certificación.** No hay certificación externa/tercera. "Certification" es una **etapa interna** del pipeline (`backend/app/v2/certification/`) y un estado del ciclo de vida del aviso (`subido`, `auto_aprobado`, `esperando_aprobacion`, `reemplazado_por_republicacion`, `eliminado`). No confundir con certificación de terceros.

---

## 2. Arquitectura completa

### 2.1 Frontend
- **Archivo único:** `frontend/public/index.html` (1057 líneas: `<style>` líneas 8-123, `<script>` líneas 244-1055). No hay bundles, webpack, ni archivos `.js`/`.jsx`/`.ts` (`.firebaserc` y `.firebase/hosting.*.cache` son artefactos de deploy).
- **Arquitectura:** SPA "thin client". El HTML dibuja cards/paginación/tabs; el JS consume la API REST y renderiza. Estado cliente en memoria (`todosLosAvisos`, `archivosSeleccionados`, `filtroPais`). CORS permitido (`main.py:63-68 allow_origins=["*"`).
- **API base:** `https://remateup-backend.onrender.com` (hardcodeado, `index.html:253`).
- **Deploy:** `frontend/firebase.json` hosting public=`public`, rewrites `**`→`/index.html`, header CORS `*` (`frontend/firebase.json:1-19`).

### 2.2 Backend (V1, producción)
- **Entry:** `backend/app/main.py:57` (`FastAPI`, `uvicorn app.main:app`).
- **Routers:** `backend/app/routers/` → `documents.py`, `dashboard.py`, `approvals.py`, `exports.py`, `admin_ext.py` (éste último es **adicional FASE 14**, commit `f9e5d5b`, no toca V1).
- **Pipeline V1:** `backend/app/pipeline/` (13 modules, ver §6).
- **Modelo V1:** `backend/app/models.py` (`Documento`, `Aviso`, `Aprobacion`,Auditoria`, `Correccion`). 267 archivos `.py` trackeados bajo `backend/app` (`git ls-files`).
- **DB:** `backend/app/database.py` (`engine` de `config.DATABASE_URL`, `get_db` generator, `Base`, `SessionLocal`).

### 2.3 Pipeline (V1 production vs V2 refactor)
- **V1** (`backend/app/pipeline/orchestrator.py:procesar_documento`) — la usada en prod por `/documentos/subir`.
- **V2** (`backend/app/v2/pipeline/runner.py:PipelineRunner.process`) — 14 etapas (Assembly→OCR→Mapping→Segmentation→Stitching→Newspaper Layout→Continuity→Parser→Knowledge→Validator→Normalizer→Confidence→Certification→Final JSON). **No usado por V1 en prod** aún; es el objetivo de refactura.

### 2.4 OCR
- `backend/app/pipeline/ocr_vision.py` → Google Vision (`GOOGLE_VISION_API_KEY`). **No configurada en prod** (`render.yaml` solo define `GEMINI_API_KEY`).
- `backend/app/v2/ocr/processor.py` (`OCRProcessor.process_pdf` usa PyMuPDF `fitz`; `process_image` usa Vision). **PyMuPDF no instalado** → `test_phase12` falla con `OCRProcessorError: PyMuPDF (fitz) is required` (ver §10/§17).

### 2.5 Assembly
- V2: `backend/app/v2/document/assembly.py` (`DocumentAssembly`), `sequence.py`, `models.py`, `stitching.py` (`PageStitcher`). Para Panamá, PDF/imagen superior+inferior se ensamblan como una sola página continua; pausa/reanuda remate (`continuity`).

### 2.6 Mapping
- V2: `backend/app/v2/ocr/mapper.py` (`OCRMapper`); el runner la marca como "embedded_in_ocr" (`runner.py:149-155`).

### 2.7 Segmentation
- V2: `backend/app/v2/segmenter/` → `engine.py`, `block_detector.py`, `line_detector.py`, `column_detector.py`, `section_detector.py`, `continuity.py`, `newspaper_layout.py`, `models.py` (**⚠ BUG bloqueante, ver §4/§10, `models.py:13`**).

### 2.8 Stitching
- V2: `backend/app/v2/document/stitching.py` (`PageStitcher.stitch_ocr_pages`); fallback en `runner.py:173-180`. Tests: `backend/app/v2/tests/test_stitching.py` (**bloqueado** por `segmenter`).

### 2.9 Continuity
- V2: `backend/app/v2/segmenter/continuity.py` (`ContinuityEngine.detect_continuity`). Tests: `test_continuity.py` (**bloqueado** por `segmenter`).

### 2.10 Parser
- V2: `backend/app/v2/parser/` → `base.py` (`ParserInterface`, `AIResolver`), `context.py` (`ParserContext`), `result.py` (`ParseResult`), `factory.py` (`ParserFactory.get_parser(country, "REMATE")`), `registry.py`.
- Parsers por país: `backend/app/v2/parser/documents/panama_remate.py` (country=`PA`), `colombia_remate.py` (country=`CO`).
- **AI Resolver:** `backend/app/v2/parser/ai/` → `policy.py` (qué campos la IA puede resolver), `providers.py` (registro zai/openrouter/huggingface/local; `LocalResolver` regex offline fallback), `integration.py` (`AIEnhancedPipeline`, `enrich_fields`), `cache.py`/`rate_limit.py`/`audit.py`/`prompt.py`.

### 2.11 Knowledge
- V2: `backend/app/v2/knowledge/` → `models.py`, `repository.py` (sqlite `knowledge.db` con 5 tablas, esquema `repository.py:18-99`), `rules.py` (`RuleEngine.apply_rules`), `trainer.py` (`KnowledgeTrainer`: auto-approve ≥0.7 conf & ≥1 evidencia), `analyzer.py`/`metrics.py`/`shadow.py`/`services.py`/`integration.py` (`KnowledgeAwareWrapper`).
- **Estado:** `knowledge.db` existe pero está prácticamente vacío: 0 `knowledge_rules`, 0 `corrections`, 0 `knowledge_history`, 0 `shadow_comparisons`, 27 `knowledge_aliases` (todas `PENDING`, seed dev `source='00000'→target='12345'`, `field_name='finca'`, `confidence=0.3`, `usage_count=0`). Ver §9.

### 2.12 AI Resolver
- Solo actúa como **fallback** cuando Parser/Knowledge dejan un campo en `REQUIRES_REVIEW` o `NOT_FOUND`, y **solo para campos permitidos** (`policy.py:AI_ALLOWED_FIELDS = {fecha_remate, hora, lugar, juzgado, provincia, municipio}`). Campos prohibidos: `{expediente, finca, precio_base, base, fianza, minimo, matricula}`.
- Política de confianza (`policy.py:AIConfidencePolicy.decide`): `>=0.95` FOUND, `0.80-0.95` REQUIRES_REVIEW, `<0.80` NOT_FOUND.
- Proveedor por defecto (`providers.py:default_name()`): `AI_PROVIDER` env; si no, `zai` (si `ZAI_API_KEY`); si no, **`local`** (regex determinista). En prod no hay `ZAI_API_KEY` → cae a `local`.

### 2.13 Validator
- V2: `backend/app/v2/validator/` → `orchestrator.py` (`ValidationOrchestrator.validate_notice`), `models.py`. Produce `validation.to_dict()` (rules_applied/failed, duplicate_info, score, decision). Tests: `test_validator.py` (50 funciones, en las 621 pass).

### 2.14 Certification
- V2: `backend/app/v2/certification/` → `models.py`, `certifier.py` (`Certifier.build_certification`; `CertDecision`). Etapa 13 del runner (`runner.py:396-417`). Tests: `test_phase12.py` (30 funciones; 2 fallan por PyMuPDF).

### 2.15 Exports
- V1: `backend/app/routers/exports.py` (`/exportar/excel`, `/exportar/resumen`). Genera Excel con `openpyxl` (`requirements.txt:11`). La columna `descripcion` = texto corto (máx 15 palabras / ≤220 chars) y `descripcion_completa` = detalle largo (`business_rules.py:212-254`, `_resumir_descripcion_portada`). Fix de `descripcion_completa` en export + uploader: commit `2591bfb` (`exports.py:86/138`, `platform_uploader.py:83`).

### 2.16 Dashboard
- V1: `backend/app/routers/dashboard.py` expone `/dashboard/metricas`, `/dashboard/pendientes`, `/dashboard/todos`, `/dashboard/historial`, `/dashboard/auditoria`, `/dashboard/aprendizaje`, `/dashboard/avisos` (véase §15 para la lista completa de endpoints). El frontend (`index.html`) consume todas.

### 2.17 Firebase
- Hosting estático para `frontend/public/` (`firebase.json`). Domain apuntando a `remateup-backend.onrender.com`? No: backend y frontend son dominios distintos (backend `.onrender.com`, frontend Firebase). Deploy manual/vía CLI (`README:81-89`).

### 2.18 Render
- Servicio `remateup-backend` (Python 3.12, free) + Postgres `remateup-db` (free). `buildCommand: cd backend && pip install -r requirements.txt`; `startCommand: uvicorn app.main:app`. `autoDeploy: true` (`render.yaml:1-21`). **Solo** `GEMINI_API_KEY` y `DATABASE_URL` como envVars (`render.yaml:10-15`).

### 2.19 SQLite
- Local: `backend/data/remateup.db` (V1, 39 avisos) y `backend/app/v2/knowledge/knowledge.db` (V2 knowledge, ~vacío). Ambas gitignoradas (`backend/.gitignore: *.db`, root `.gitignore: *.db`). No `conftest`/fixture crea DB — los tests que tocan V1 necesitan `DATABASE_URL=sqlite://...` porque `backend/.env` pone Postgres (ver §4).

### 2.20 Postgres
- Prod: `remateup-db` en Render, inyectado vía `DATABASE_URL` (`render.yaml:12-15`). Local: NO se usa (se usa sqlite). `psycopg2-binary` está en `requirements.txt` pero **no instalado** en `backend/venv` → importar la app con `DATABASE_URL=postgres://...` falla (`ModuleNotFoundError: psycopg2`).

### 2.21 V1
- Pipeline lineal + FastAPI monolítica + sqlite local/postgres prod. `backend/app/pipeline/*.py`, `backend/app/routers/*`, `backend/app/models.py`, `backend/app/main.py`. **Base de producción.**

### 2.22 V2
- Refactor de `backend/app/v2/` (pipeline `runner.py`, módulos por etapa, Knowledge/AI/Validator/Certification). Objetivo: reemplazar V1 de forma equivalente. **No es el default en prod aún** (prod sigue llamando al V1 `orquestador.procesar_documento` en `/documentos/subir`).

### Relaciones / dependencias (resumen)
- V1 ←→ V2 coexisten; V1 no importa V2 (ni al revés). V2 importa Knowledge/Parser/Certification/V2-Ocr/Segmenter.
- Frontend → V1 API (REST). V1 API → pipeline V1 → business_rules/validation/confidence → DB.
- V2 `AIEnhancedPipeline` (`parser/ai/integration.py:140`) **envuelve** V1/V2 pero "no modifica pipeline, parser, knowledge, validator o certification" (`integration.py:141-146`).
- `backend/app/main.py:70-74` incluye 5 routers, incluido `admin_ext` (FASE 14).

### Módulos críticos (no deben romperse)
`pipeline/runner.py` (orden de etapas), `models.py` (esquema), `business_rules.py` (fianza/mínimo/códigos), `parser/factory.py` + países, `knowledge/repository.py`, `certification/`.

### Módulos que NUNCA deben romperse
V1 (`pipeline/`, `routers/`, `models.py`), exports Excel, Knowledge (sqlite schema), Parser V2 (no V3), fianza/mínimo rules, PA/CO, API (`/documentos/*`, `/dashboard/*`, `/exportar/excel`, `/aprobaciones/*`).

---

## 3. Historial de Fases

El listado canónico está en `fases.txt` (entregado con el proyecto). A continuación el síntesis, con indicación de **qué existe en el árbol** (verificado) y el **estado concreto**. Símbolos: ✅ implementado/verificado · ⚠ parcial/sin validar · 🚫 bloqueado por entorno.

- **FASE 1 — Fix fianza/mínimo determinista.** ✅ Extrae `fianza_porcentaje` vía regex judicial y marca `confianza.descripcion=ALTA`; calcula fianza/mínimo a partir de base×% (`business_rules.py:68-138`). Archivo: `backend/app/pipeline/extractor_deterministico.py`. Fix commit `2591bfb`. Verificado local `doc104` (fianza/monto OK, 0 discrepancias). Tests: `test_extractor_deterministico.py` (23 casos, ✅ verde).
- **FASE 2 — Confidence/validator.** ✅ `backend/app/pipeline/confidence.py` + `validation.py` (umbral 0.70 `config.py:26`; duplicate detection). Estado `auto_aprobado`/`esperando_aprobacion`.
- **FASE 3 — Knowledge aplicado en extractor.** ✅ `backend/app/v2/knowledge/` (`rules.py`, `repository.py`) aplicado en `runner.py:knowledge`; V1 aplica reglas en `business_rules.py`.
- **FASE 4 — WhatsApp approval bridge.** ⚠ `WHATSAPP_BRIDGE_URL` + `WHATSAPP_APROBADOR` (`config.py:29-30`); V1 `approvals.py` (`/aprobaciones/{id}/manual`, `/aprobaciones/simular_todas`, webhook). **NO configurado en Render** (solo `GEMINI_API_KEY`+`DATABASE_URL`). README describe bridge node/Baileys (entorno de pruebas bloquea dominios).
- **FASE 5 — IA estructurar (extraction).** ✅ `backend/app/pipeline/extraction.py` (`_estructurar_texto_largo`, `_deduplicar`) usa Gemini (`config.GEMINI_MODEL`/`CLAUDE_MODEL`). V2 `parser/ai/`.
- **FASE 6 — Normalización/V2 pipeline base.** ✅ `backend/app/v2/pipeline/runner.py` (14 etapas). Tests `test_pipeline_fase7.py` (**🚫 bloqueado** por `segmenter`).
- **FASE 7 — Segmentation.** ⚠ `backend/app/v2/segmenter/` (block/line/column/section detectors). **🚫 `models.py:13` NameError** bloquea colección. No validado end-to-end.
- **FASE 8 — AI integration.** ✅ `backend/app/v2/parser/ai/integration.py` (`AIEnhancedPipeline`, `enrich_fields`). Policy `policy.py` (AI_ALLOWED/Forbidden, umbrales). Knowledge Safety (`integration.py:202-209` + `providers.py:Knowledge Safety`).
- **FASE 9 — Continuity (remates multi-página).** ✅ `segmenter/continuity.py`; editor frontend reordena/quita archivos (`index.html:318-377`). Tests `test_continuity.py` (**🚫 bloqueado** por `segmenter`).
- **FASE 10 — Diagnóstico global.** ✅ `backend/app/v2/diagnosis` (si existe) + endpoints `/admin/diagnostico`, `/admin/admin-dashboard` (FASE-14 commit `f9e5d5b`, `admin_ext.py`).
- **FASE 11 — AI confidence gate / policy.** ✅ `parser/ai/policy.py` (`AIConfidencePolicy`).
- **FASE 12 — Certification.** ✅ `backend/app/v2/certification/` (`certifier.py`, `models.py`). Tests `test_phase12.py` (30; 2 **🚫 fallan** por PyMuPDF).
- **FASE 13 — Knowledge safety / no-robar-IA.** ✅ `integration.py:19-21,202-209`: AI NUNCA crea/modifica rules, NUNCA aumenta confidence ni training metrics; solo audit log.
- **FASE 14 — Panamá prioridad + admin.** ✅ `backend/app/learning/{engine,reports}.py`, `routers/admin_ext.py`, `main.py include_router` (commit `f9e5d5b`). 10 endpoints `/admin/*` (ver §15). Tests `test_hyper_learning.py` (14, ✅ verde con sqlite).
- **No hay FASE 15+.** El proyecto está estructurado hasta FASE 14.

**Tests por fase.** Véase §17 para el censo completo (31 archivos; el más representativo es `test_extractor_deterministico.py` para V1 y `test_*_phase1[12].py` para V2).

**Riesgos por fase.** V1 riesgo bajo (prod). V2 riesgo alto: bloqueado por `segmenter`/`PyMuPDF`/`psycopg2` en el entorno local; no hay validación real de Gemini/WhatsApp.

---

## 4. Estado actual

### Qué funciona
- ✅ API V1 en producción (Render). `/health`→`/`, subida, dashboard, exportación Excel, aprobaciones, reprocesar, debug.
- ✅ V1 pipeline sobre **texto** (no imágenes): fianza/mínimo calculados, descripción portada vs completa, códigos internos/periodísticos, prevista Google Maps, detección de duplicados (`validation.py`).
- ✅ Decision de confianza (0.70) → auto-aprobado vs requiere aprobación.
- ✅ WhatsApp approval flow (código presente; no validado en prod por falta de bridge configurado).
- ✅ Exportación a Excel con `descripcion_completa` (`2591bfb`).
- ✅ Auditoría inmisible de cada paso (`Auditoria`, 130 filas en local).
- ✅ Frontend dashboard funcional (tabs últimos/pendientes/historial, filtros, editor inline, exportación).
- ✅ 621 tests pasan (entorno sqlite; ver §17).

### Qué no funciona
- 🚫 **V2 pipeline no corre** en este entorno: `backend/app/v2/segmenter/models.py:13` → `NameError: name 'DetectedBlock' is not defined` (falta `from __future__ import annotations`; `DetectedBlock` se define después, línea 117). Bloquea 12 archivos de tests.
- 🚫 **PyMuPDF no instalado** (`fitz`) → `OCRProcessor.process_pdf` lanza `OCRProcessorError`; `test_phase12` (2 tests) fallan. `pip install PyMuPDF` resolvería (está en `requirements.txt`).
- 🚫 **psycopg2 no instalado** en `backend/venv` → importar la app con `DATABASE_URL=postgres://...` falla; hay que usar `DATABASE_URL=sqlite://...` localmente.
- 🚫 **Google Vision no configurado en prod** (`render.yaml` omite `GOOGLE_VISION_API_KEY`) → OCR de imágenes escaneadas (Panamá) no activo en prod; depende de texto.
- 🚫 **Claude no configurado en prod** (sin `ANTHROPIC_API_KEY`) → el fallback `auto` cae a `local` regex, no a Claude.
- 🚫 **WhatsApp bridge no configurado en prod** (sin `WHATSAPP_BRIDGE_URL`/`WHATSAPP_APROBADOR` en Render) → aprobaciones por WhatsApp no enviadas en prod.
- 🚫 **knowledge.db prácticamente vacío** (0 rules, 0 corrections; 27 aliases dev seed) → Knowledge Engine no está entrenado/usado en prod.

### Qué está estable
- V1 API + pipeline sobre texto. 39 avisos locales todos `subido`. Auditoría 130 eventos consistentes. Tests críticos V1 verdes.

### Qué está en producción
- Backend Render (commit `f9e5d5b` + `2591bfb`). Frontend Firebase Hosting. Postgres `remateup-db` free. Única var de IA: `GEMINI_API_KEY`.

### Qué está certificado
- No hay certificación externa. "Certified" interno = avisos `subido`/`auto_aprobado` (validados por reglas + confianza).

### Qué sigue experimental
- Todo `backend/app/v2/*` (refactor). Esqueleto `/admin/*` FASE 14 (`learning/*` + `admin_ext.py`).

---

## 5. Estado por país

### PANAMÁ (pais=1)
- **Precisión:** alta sobre texto. Fianza {10,20,25}%, mínimo {66.67,50,100} (`business_rules.py`, `config.py:68-69`).
- **OCR:** imágenes (superior+inferior) → ensamblables (`stitching`); OCR de imagen necesita Google Vision (⚠ no configurado en prod).
- **Parser:** `panama_remate.py` (`backend/app/v2/parser/documents/`); V1 `pdf_colombia_parser.py` es CO (PA usa imágenes).
- **Knowledge:** vacío (0 rules).
- **IA:** Gemini extraction; fallback `local` regex; Claude no disponible.
- **Validator/Certificación:** reglas PA aplicadas; decision de confianza 0.70.
- **Problemas conocidos:** dependencia de Google Vision para imágenes de periódico (no configurado en prod) → riesgo de que PA con imágenes no se procese sin ese servicio.
- **Prioridad:** ⭐⭐⭐ (prioridad absoluta, FASE 14 prioriza sugerencias pais=1).

### COLOMBIA (pais=2)
- **Precisión:** "Construido pero pendiente de probar con conexión real" (`README:43-45`). Fianza 40% fijo (asumido por regla si el OCR no lo lee, `business_rules.py:92-100`), mínimo {70,50,100}%.
- **OCR:** PDFs via `pypdf`/`PyMuPDF` (texto). `ColombiaRemateParser` regex (`colombia_remate.py:35-56` para %; `:22-46` expediente/finca/precio_base/fecha/partes).
- **Parser:** `colombia_remate.py` (country=CO) — regex-first, `words_to_number` para % en letras (`normalization/numbers.py`).
- **Knowledge:** vacío.
- **IA:** mismo stack (Gemini → local fallback).
- **Validator/Certificación:** reglas CO aplicadas.
- **Problemas conocidos:** el "grid colombiano aún necesita mejoras" (`README:48-51`); PDFs requieren PyMuPDF (no instalado localmente); expresiones regex CO no validadas con PDFs reales aún.
- **Prioridad:** ⭐⭐ (se mantiene, no se rompe, pero PA es prioridad).

---

## 6. Pipeline completo (V1 productivo — el que usa prod)

Entrada: documento (imágenes PA / PDF CO) → salida: avisos en DB + Excel/WhatsApp.

```
[Documento recibido]                          (backend/app/routers/documents.py POST /documentos/subir)
        ↓
[Assembly / OCR]                              V1: image_tiler.py / ocr_vision.py(Google Vision) /
        ↓                                       pdf_colombia_parser.py (pypdf/PyMuPDF extracción texto)
[Extracción (IA)]                             extraction.py: Gemini 2.5 Flash → datos estructurados +
        ↓                                       confianza por campo
[Reglas de negocio]                           business_rules.py:aplicar_reglas → códigos PA/CO, fianza y
        ↓                                       mínimo = base×% (regex fianza fallback, extractor_deterministico)
[Validación]                                validation.py → duplicados (expediente+fecha+país) +
        ↓                                       campos_faltantes (CAMPOS_FUNDAMENTALES, config.py:35-38)
[Confianza]                                confidence.py → avg ≥ UMBRAL_CONFIANZA(0.70) y sin
        ↓                                    duplicado/faltante → SÍ auto-subir | NO → WhatsApp
 [Subida]  → platform_uploader.py (simulado, README:104)      [WhatsApp] → approvals.py (Baileys bridge)
        ↓
[Auditoría]                                 Auditoría (130 filas locales). Campos: extraction,
        ↓                                    business_rules, confidence, whatsapp, upload, orchestrator.
[Exportación]                               /exportar/excel (openpyxl) — descripcion(portada≤15p) +
                                             descripcion_completa (exports.py:86/138, 2591bfb)
        ↓
[Frontend]                                  frontend/public/index.html consume /dashboard/* + /exportar/excel
```
**Qué entra:** imágenes/PDF + selección país (PA/CO). **Qué sale:** avisos en Postgres/sqlite, Excel, aprobaciones WhatsApp. **Qué produce cada módulo:** OCR→texto; extraction→campos+candidatos; business_rules→fianza/minimo/códigos/prevista/descripción; validation→duplicado+requeridos; confidence→decision; auditoría→trazabilidad.

## V2 pipeline (refactor, no productivo todavía)
Ver `runner.py:4-6` y `PipelineRunner.process`. 14 etapas con `StageResult` medible (status/duration_ms/warnings/errors/metrics). Produce `final_json` (`runner.py:452-498`) con stages, field_confidence, validation, certification, statistics. Entrypoint alternativo `AIEnhancedPipeline.run_files` (`integration.py:212`) que revalida/recertifica tras enriquir con IA.

---

## 7. Estado del código

- **Módulos aproximados:** 267 archivos `.py` bajo `backend/app` (`git ls-files backend/app -- '*.py'`). Estructura: `app/{root: config,database,main,models}` + `pipeline/` (13 V1) + `routers/` (5) + `upload/` + `ocr_test.py` + `v2/` (refactor: document, ocr, segmenter, parser(+ai,documents), knowledge, normalization, confidence, validator, certification, schema, evaluation, fase8, production, learning) + `v2/tests/` (20 archivos) + `v2/fase8/`. Frontend: 1 fuente (`index.html`).
- **Carpetas importantes:** `backend/app/pipeline`, `backend/app/routers`, `backend/app/v2/*`, `backend/app/learning` (nuevo), `frontend/public`, `backend/data` (sqlite), `backend/app/v2/knowledge` (sqlite). Artefactos gitignorados: `*.db`, `venv`, `__pycache__`, `data/debug/`, `data/tmp/`, `data/out/`.
- **Arquitectura:** modular, paquetes por dominio; V1 = pipeline lineal; V2 = orquestado.
- **Convenciones:** paquetes `backend.app.*`; imports absolutos desde raíz (`from backend.app.v2...`) — requiere `PYTHONPATH=.`. Funciones puras en `learning/*.engine.py` (FASE 14).
- **Inyección de dependencias:** FastAPI `Depends(get_db)` (`database.py`); `SessionLocal`.
- **Fábricas:** `ParserFactory.get_parser(country,"REMATE")` (`parser/factory.py`); `Certifier`; `FinalConfidenceCalculator`; `AIResolverRegistry.create_default()` (`providers.py:441`).
- **Wrappers:** `KnowledgeAwareWrapper` (`knowledge/integration.py`); `AIEnhancedPipeline` (`parser/ai/integration.py`).
- **Registries:** `ParserRegistry` (`parser/registry.py`); `AIResolverRegistry` (`providers.py:394`); `KnowledgeRule` estados.
- **Repositorios:** `KnowledgeRepository` (`knowledge/repository.py`, sqlite); V1 usa SQLAlchemy `SessionLocal`/`get_db` sobre Postgres/sqlite.
- **Servicios:** `knowledge/services.py`, `approvals.py` (WhatsApp), `platform_uploader.py` (subida a "la plataforma", en modo simulado).
- **DTO:** `ParseResult` (`parser/result.py`), `ParserContext` (`context.py`), `StageResult` (`runner.py:44`). V1 usa dicts + modelo ORM directamente.
- **Modelos:** V1 `backend/app/models.py` (5 tablas: Documento, Aviso, Aprobacion, Auditoria, Correccion). V2 modelos por módulo (`v2/*/models.py`; e.g. `knowledge/models.py`, `segmenter/models.py`, `certification/models.py`).

---

## 8. Estado de IA

- **Anthropic (Claude):** `ANTHROPIC_API_KEY` en `.env.example` y `config.py:11` (default modelo `claude-sonnet-4-5-20250929`). En prod Render **NO configurada** (`render.yaml` solo GEMINI+DATABASE_URL). En modo `MOTOR_IA=auto` actúa como fallback si Gemini falla.
- **Gemini:** `GEMINI_API_KEY` configurada en prod (`render.yaml:10`); modelo `gemini-2.5-flash` (`config.py:10`). Motor principal de extracción (`extraction.py`). ✅
- **ZAI (Z.ai):** `providers.py` menciona `ZAIResolver` (lazy import `parser/ai/zai_resolver.py`), activado si `ZAI_API_KEY` (no en prod ni en `.env.example`). ⚠ no disponible en prod.
- **Google Vision:** `GOOGLE_VISION_API_KEY` (`config.py:13`) — NOT en `.env.example`, NOT en `render.yaml`. OCR de imágenes no activo en prod.
- **Fallback determinista:** `LocalResolver` (`providers.py:324`) regex para campos permitidos (fecha_remate, hora, lugar, juzgado, provincia, municipio) con confianza 0.96. Es el **único proveedor activo en prod si Gemini no tiene la clave** o como backup. Existe también `extractor_deterministico.py` (regex judicial fianza%) para V1.
- **Cuándo se usan:** V1 `extraction.py` usa Gemini directamente para estructurar; fallback a regex determinista (`extractor_deterministico`) para fianza/mínimo/porcentajes. V2: Parser→Knowledge primero; IA solo si `REQUIRES_REVIEW`/`NOT_FOUND` en campos permitidos (`integration.py:61-64`).
- **Cuándo NO:** IA NUNCA toca `{expediente, finca, precio_base, base, fianza, minimo, matricula}` (`policy.py:21-29`); NUNCA crea/modifica rules ni métricas de knowledge (`integration.py:19-21`, `providers.py:202-209`).
- **Política de confianza:** 0.95 FOUND, 0.80 REQUIRES_REVIEW, <0.80 NOT_FOUND (`policy.py:31-32,48-59`); V1 umbral global 0.70 (`config.py:26`).
- **Cache:** `parser/ai/cache.py` (`AICache`), stats en `integration.py:summary`.
- **Rate limit:** `parser/ai/rate_limit.py` (`RateLimiter`), envuelve transporte.
- **Auditoría:** `parser/ai/audit.py` (`AIAuditLog`), registra provider/modelo/tokens/latencia/decisión/campo → usado para costos (`estimate_cost`, `integration.py:98-108`) y para el "knowledge safety" proof.

---

## 9. Knowledge Engine

- **Cómo funciona:** `KnowledgeRepository` (sqlite `knowledge.db` o env `KNOWLEDGE_DB_PATH`) persiste 5 tablas (`repository.py:18-99`: `knowledge_rules`, `knowledge_aliases`, `corrections`, `knowledge_history`, `shadow_comparisons`). `RuleEngine.apply_rules` (`knowledge/rules.py`) se aplica en `runner.py:knowledge` (etapa 9). `KnowledgeAwareWrapper` envuelve el parser.
- **Cómo aprende:** `KnowledgeTrainer` (`trainer.py`) auto-aprueba rules con confidence ≥0.7 y ≥1 evidencia; registra history. Las **correcciones del cliente** son la fuente de aprendizaje V1 (`Correccion` en V1; `main.py:165-197 editar_aviso` guarda `campo/valor_anterior/valor_nuevo/era_vacio/contexto/codigo_prensa/pais`).
- **Qué NO hace:** AIResolver NUNCA crea/modifica rules ni cambia métricas (`integration.py:19-21`, `providers.py:202-209`; `knowledge_safety` en `run_text`/`run_files`).
- **Qué requiere aprobación:** rules PENDING deben aprobarse (`trainer.py`) antes de aplicarse con confianza plena; el threshold `MIN_CONFIDENCE_TO_APPROVE=0.7`.
- **Reportes:** `knowledge/evolution` (endpoint V1 `/dashboard/aprendizaje` y `/admin/diagnostico`+`/admin/sugerencias` FASE 14 `learning/reports.py`).
- **Qué está vacío actualmente:** `knowledge.db` → 0 `knowledge_rules`, 0 `corrections`, 0 `knowledge_history`, 0 `shadow_comparisons`, 27 `knowledge_aliases` (todas `PENDING`, seed dev: `source='00000'→target='12345'`, `field_name='finca'`, `confidence=0.3`, `usage_count=0`). V1 `correcciones` (tabla `Correccion`) **no existe** en el snapshot local `remateup.db` (consulta sqlite: solo `documentos/auditores/avisos/aprobaciones`) → posible brecha: `editar_aviso` escribe `Correccion` pero la tabla no está presente en este snapshot.
- **Por qué:** El Knowledge Engine V2 está construido pero **nunca se ha entrenado** (no hay corrections reales; las aliases son datos de prueba de 2026-07-30/31). En prod, V1 sigue usando `business_rules.py` (reglas fijas) y la tabla `correcciones` para "ground truth", no el módulo V2 `knowledge/`.

---

## 10. Hallazgos importantes

1. **Knowledge Engine vacío.** 0 rules/corrections/history/shadow en `knowledge.db` (ver ¶9). Las 27 aliases son seed dev. → Knowledge Engine no contribuye en prod; V1 depende solo de reglas fijas.
2. **Grid colombiano sin validar en prod.** `README:43-45` dice "construido pero pendiente de probar con conexión real". Regex CO en `colombia_remate.py` no validados con PDFs reales; expresiones de % son complejas (`_PERCENT_LABELS`, `_GAP_PERCENT`) → riesgo de fianza/minimo CO mal leída.
3. **Campos faltantes (V1).** `CAMPOS_FUNDAMENTALES` (12) `config.py:35-38`; `CAMPOS_SECUNDARIOS` (4) `:39`. Un aviso con <12 fundamentales → `esperando_aprobacion` (menos del umbral). Estado local: 39 avisos todos `subido` (presumiblemente completos en dev).
4. **Parser Gap.** V2 segmenter rompe (`models.py:13`); V1 parser sobre texto funciona. CO depende de PyMuPDF (no instalado).
5. **Coverage:** NO hay configuración de coverage (`python-coverage`/`pytest-cov` no están en `requirements.txt`; sin `conftest.py`/`pytest.ini`). → **cobertura desconocida/no medida.**
6. **Accuracy.** No hay reporte numérico de acuracy. Tests `test_ai_phase11.py`(50), `test_phase12.py`(30), `test_phase13.py`(78) existen pero gran parte está bloqueada (segmenter/PyMuPDF) o no validada contra producción.
7. **False Positives.** `discrepancia_valores` (`models.py:71`) marca cuando monto impreso ≠ calculado (>3% de base) (`business_rules.py:122-129`). 39 avisos locales todos `subido` → 0 discrepancias visibles en dev.
8. **Duplicados.** `validation.py` y runner `validator` detectan duplicados (expediente+fecha+pais V1; expediente+finca V2 `predecir`). README:38 afirma detección probada.
9. **OCR.** Google Vision NO configurado en prod; dependencia principal es **texto de PDF** (pypdf/PyMuPDF). Imágenes PA → sin OCR activo en prod si no hay texto (riesgo). PyMuPDF no instalado localmente → `test_phase12` falla.
10. **Performance/Latencia IA.** No hay benchmarks reales archivados en el repo (`evaluation/production/output` existe como carpeta pero no revisamos contenidos). IA usa `temperature=0` (`providers.py:178`), cache (`AICache`) y rate-limit (`RateLimiter`) para contener latencia/costos. `monitorear()` frontend polling 3s (`index.html:498`).

---

## 11. Problemas abiertos (por prioridad)

| # | Descripción | Impacto | Riesgo | Solución probable | Módulos involucrados |
|---|---|---|---|---|---|
| 1 | `segmenter/models.py:13` `NameError: DetectedBlock` (falta `from __future__ import annotations` o import) | Bloquea V2 pipeline + 12 tests | Alto (V2 inutilizable) | Añadir `from __future__ import annotations` línea 1 (o importar `DetectedBlock`) | `backend/app/v2/segmenter/models.py` |
| 2 | PyMuPDF (`fitz`) no instalado → `OCRProcessor.process_pdf` lanza y PDF/CO no procesa | CO y PDFs V2 no funcionan; 2 tests fallan | Alto (producto CO) | `pip install PyMuPDF` | `requirements.txt`, `backend/app/v2/ocr/processor.py` |
| 3 | `psycopg2` no instalado en venv → app no importa con `DATABASE_URL=postgres` | Tests/dev con Postgres imposible | Medio (solo dev) | `pip install psycopg2-binary` | `requirements.txt`, `backend/app/database.py` |
| 4 | Google Vision `GOOGLE_VISION_API_KEY` no configurado en prod | OCR de imágenes PA no activo en prod | Alto (PA depende de imágenes) | Agregar var a `render.yaml` + secret en Render | `render.yaml`, `backend/app/pipeline/ocr_vision.py` |
| 5 | Claude/ANTHROPIC no configurado en prod | No hay fallback IA real (cae a regex) | Medio | Agregar `ANTHROPIC_API_KEY` a Render | `config.py:11`, `render.yaml` |
| 6 | knowledge.db vacío (0 rules/corrections) | Knowledge Engine no aporta en prod | Alto (aprendizaje no funciona) | Poblar con corrections reales del cliente; aprobar rules | `knowledge/` |
| 7 | WhatsApp bridge no configurado en prod (`WHATSAPP_BRIDGE_URL`/`APROBADOR`) | Aprobaciones no llegan al cliente en prod | Alto | Configurar bridge en Render (node Baileys + QR) | `config.py:29-30`, `render.yaml`, `routers/approvals.py` |
| 8 | Tabla `correcciones` (V1 `Correccion`) ausente en snapshot local `remateup.db` | `editar_aviso` learning puede fallar en local | Medio | `Base.metadata.create_all` recrea (o migrar) | `main.py:10`, `models.py:114` |
| 9 | Grid colombiano no validado con PDFs reales | Potencial under-performance CO | Medio-Alto | Correr V2 parser con PDFs reales; ajustar regex | `parser/documents/colombia_remate.py` |
| 10 | Sin cobertura de tests medida ni CI | Riesgo de regresión | Medio | Añadir `pytest-cov` + GitHub Actions | (ausente) |
| 11 | PDF→PNG/imagen pipeline: PyMuPDF falta y Vision no configurado | No OCR de imágenes/PDFs escaneados | Alto | Ver #2 + #4 | `ocr/processor.py`, `pipeline/pdf_colombia_parser.py` |
| 12 | Frontend hardcodea `https://remateup-backend.onrender.com` (`index.html:253`) | No sirve para staging/dev local sin proxy | Bajo-Medio | Variable `API_BASE` / env | `frontend/public/index.html:253` |

---

## 12. Deuda técnica

- `frontend/public/index.html` es **un solo archivo de 1057 líneas** con CSS+JS inline → no hay separación de concerns, difícil de testear/mantener; hardcodea API base.
- `backend/app/main.py` acumula **lógica de negocio + admin + debug** en el entrypoint (`limpieza_bd`, `editar_aviso`, `debug_doc/reestructurar/reprocesar` — este último es **borrado físico** `DELETE` de avisos/aprobaciones/auditoría/`main.py:82-115`) → acoplamiento; el borrado físico contradice la política de soft-delete de FASE 14.
- `render.yaml` expone **solo `GEMINI_API_KEY`+`DATABASE_URL`**; faltan `ANTHROPIC_API_KEY`, `GOOGLE_VISION_API_KEY`, `MOTOR_IA`, WhatsApp vars, `KNOWLEDGE_DB_PATH`.
- Sin CI/CD (`.github/workflows/` no existe) → deploy solo por `autoDeploy` de Render/Firebase; sin tests en CI.
- Sin `conftest.py`/`pytest.ini` → tests dependen del `DATABASE_URL=sqlite` del shell; frágiles.
- `requirements.txt` no incluye `pytest`, `pytest-cov`, `google-cloud-vision` (aunque `ocr_vision.py` lo usa), `psycopg2-binary` está listado pero no instalado en venv → entorno local inconsistente.
- `knowledge.db` es sqlite embebido al repo-adjacent (`knowledge/repository.py:106`); no versionado ni migrado; seed de aliases dev mezclado con prod potencial.
- `frontend/.firebase/hosting.cHVibGlj.cache` aparece como modificado por LF/CRLF → ruido en diffs.
- V2 duplica responsabilidades con V1 (p.ej. validators, confidence, parsers) → superficie de mantenimiento doble hasta que V2 reemplace a V1.
- `colombia_remate.py:_GAP_PERCENT`/`_NO_WORD` regex son frágiles (posible false match).
- Hardcode de versión de knowledge/validator en `runner.py:406-407` (`"6.5.0"`/`"6.9.0"`) → no derivado del código real.

---

## 13. Cosas que GPT-5.5 NO debe romper

Absolutamente todo lo siguiente debe seguir funcionando igual (V1 es prod; V2 en construcción):

- **Pipeline V2** (`backend/app/v2/pipeline/runner.py`) — orden de 14 etapas; NO reordenar ni renombrar stages sin validación.
- **Parser V2** (`backend/app/v2/parser/`) — NO crear Parser V3; NO romper `ParserFactory.get_parser`/`ParserRegistry`/`ParserInterface`/`ParseResult`/`ParserContext`.
- **Knowledge** (`backend/app/v2/knowledge/`) — NO crear Knowledge V3; schema sqlite (`repository.py:18-99`) inmutable; `trainer.py` thresholds (0.7/1).
- **Validator** (`backend/app/v2/validator/`) — output `validation.to_dict()` shape (rules_applied/failed, duplicate_info, score, decision) consumido por `final_json` (`runner.py:492-497`).
- **Certification** (`backend/app/v2/certification/`) — `cert_doc.to_dict()` / `all_avisos[].decision`.
- **Exports** / Excel — `exports.py` + `business_rules._resumir_descripcion_portada` (portada ≤15 palabras/≤220 chars, `descripcion_completa`=detalle).
- **Dashboard** — `/dashboard/*` contrato de JSON (frontend lo consume).
- **Firebase / Render** — configs de deploy.
- **API** — todos los endpoints V1 (`§15` lista completa); el contrato JSON de `cardAviso`/editor (`index.html:799-916`).
- **Tests** — mantener verdes los 621 actualmente verdes; NO empeorar los 12 errores/2 fallos.
- **Panamá** — prioridad; regex fianza PA `{10,20,25}`/mínimo `{66.67,50,100}`.
- **Colombia** — mantener regla fianza 40% asumida por regla; mínimo `{70,50,100}`.
- **Excel** — columnas `descripcion`+`descripcion_completa`, montos `fianza`/`minimo`.
- **OCR** — NO romper `pypdf`/`PyMuPDF` path; Google Vision solo como enhancement.
- **Fianza/mínimo = base×%** (`business_rules.py:102-129`) — regla de negocio del cliente.
- **Soft-delete policy (FASE 14):** `/admin/aviso/{id}` DELETE = `estado='eliminado'` (no borrado físico). El V1 `/admin/limpiar_bd` hace borrado físico → **no cambiar** (es admin intencional) pero documentarlo; FASE 14 añade soft-delete sobre ese piso.

---

## 14. Estado del Frontend

- **Funciona:** dashboard completo (`index.html:1055` init `conectar()` + `cargarTodo()`); tabs Últimos/Pendientes/Historial con paginación; upload con reorden/arrastrar/limpiar; editor inline (`abrirEditor`→`guardarEdicion`→PUT `/admin/editar_aviso/{id}`); exportación Excel (filtrada/total/PA/CO); auditoría; métricas; aprobación/rechazo (`aprobar`), simular.
- **Botones y su estado** (implementados en `index.html`):
  - `subirDocumento` ✅ (POST `/documentos/subir`; valida PA=imágenes/CO=PDF; retry 1x por backend dormido).
  - `limpiarSeleccion`, `moverArchivo`, `quitarArchivo`, `actualizarAyudaUpload` ✅.
  - `cambiarTab` (ultimos/pendientes/historial) ✅.
  - `simularTodas`, `simularUna` ✅ (POST `/aprobaciones/simular_*`).
  - `aprobar(id,ok)` ✅ (POST `/aprobaciones/{id}/manual`).
  - `reintentarDocumento` ✅ (POST `/documentos/{id}/reintentar`).
  - `exportarExcel`, `exportarFiltrados` ✅ (GET `/exportar/excel`).
  - `abrirEditor`, `guardarEdicion`, `cerrarEditor` ✅.
  - `monitorear` ✅ (poll 3s sobre `/documentos/{id}`).
  - `cargarMetricas/cargarPendientes/cargarHistorial/cargarAuditoria/mostrarUltimosProcesados` ✅ (consume `/dashboard/*`, `/dashboard/todos`).
  - `toggleDet` ✅ (expandirDetalle).
- **Filtros:** `uploadPais` PA/CO; `filtroPais` (1/2); `filtroEstado` (subido/auto_aprobado/esperando_aprobacion/reemplazado_por_republicacion); `filtroFechaRemate`; `filtroFechaSubida`; `filtroBuscar` (sobre descripción/expediente/partes/código/código_ubicacion).
- **Rutas (tabs):** `#ultimos`, `#pendientes`, `#historial` (SPA, sin router; tab cambia `display`).
- **UX a mejorar:** (a) polling 3s fijo en `monitorear` sin backoff exponencial; (b) `fetch` sin timeout/AbortController excepto `conectar`; (c) todo CSS/JS inline = carga única y sin separación; (d) estado cliente en memoria se pierde al recargar (no persiste filtros/página).
- **Pendientes:** nada funcionalmente roto aparente vs. V1 API; la deuda es arquitectónica (inline bundle) y el hardcodeo de API base.

---

## 15. Estado del Backend

- **API:** FastAPI, raíz `GET /` (`{"status":"ok"}`), docs `/docs`+`/redoc`+`/openapi.json`.
- **Endpoints (producción, excluyendo docs/openapi):** [con `DATABASE_URL=sqlite` confirmado importando `main.py`]
  - `POST /documentos/subir`, `POST /documentos/subir_lote`, `GET /documentos/{id}`, `POST /documentos/{id}/reintentar`
  - `GET /dashboard/metricas`, `/dashboard/pendientes`, `/dashboard/todos`, `/dashboard/historial`, `/dashboard/auditoria`, `/dashboard/aprendizaje`, `/dashboard/avisos`
  - `GET /exportar/excel`, `/exportar/resumen`
  - `POST /aprobaciones/{id}/manual`, `/aprobaciones/simular_una/{id}`, `/aprobaciones/simular_todas`, `/aprobaciones/webhook`
  - Admin V1: `POST /admin/limpiar_bd`, `/admin/limpiar_aprendizaje`, `/admin/limpiar_pais/{pais}`, `PUT /admin/editar_aviso/{id}`, `GET/POST /admin/debug_doc|debug_reestructurar|reprocesar_doc/{id}`
  - Admin FASE 14 (`admin_ext.py`, commit f9e5d5b): `GET /admin/sugerencias`, `/admin/prediccion`, `/admin/aviso/{id}/inteligencia`, `POST /admin/aviso/{id}/aplicar`, `DELETE /admin/aviso/{id}`, `POST /admin/aviso/{id}/restaurar`, `POST /admin/avisos/borrar`, `GET /admin/diagnostico`, `/admin/admin-dashboard`, `GET /admin/reportes/client_ready`.
  - **Total ~33 endpoints de app** (más docs/openapi). (ver listado completo de rutas en anexo; 39 rutas FastAPI incluye HEAD de estáticos).
- **Servicios:** `platform_uploader.py` (subida "la plataforma", **modo simulado** `README:104`); `approvals.py` (WhatsApp via bridge); `ocr_vision.py` (Google Vision).
- **Workers/Background jobs:** NO hay background workers/queue (Celery/RQ) en `requirements.txt`; el procesamiento es **sincrónico** dentro del request POST `/documentos/subir` → polling frontend `monitorear()`. `platform_upload` aparece 40 veces en auditoría (subidas simuladas).
- **Health/Smoke:** `GET /` = health; `backend/app/v2/production/smoke.py` (`run_text_pipeline`) = smoke V2 (importado por `ai/integration.py:32`).
- **Benchmark:** no hay archivos de benchmark archivados que revisemos (`evaluation/production/output` & `evaluation/accuracy/output` existen como carpetas vacías/sin inspeccionar).
- **Reportes:** `/exportar/excel` (Excel), `/exportar/resumen`; FASE 14 añade reportes `.json/.md` (`learning/reports.py` BUILDERS: hyper_learning, hyper_intelligence, production_diagnosis, ui_audit, knowledge_evolution, continuous_learning, client_ready).

---

## 16. Estado de Producción

- **Render:** `remateup-backend` (python 3.12, free; `autoDeploy:true`), `remateup-db` Postgres (free). Build `pip install -r requirements.txt`; start `uvicorn app.main:app`.
- **Firebase:** hosting `public`=`frontend/public`; rewrites SPA → index.html; CORS `*`; `frontend/.firebaserc` (site). Deploy manual vía CLI.
- **Variables de entorno:** prod expone **solo** `GEMINI_API_KEY` y `DATABASE_URL` (`render.yaml:10-15`). Faltan activar: `ANTHROPIC_API_KEY`, `GOOGLE_VISION_API_KEY`, `MOTOR_IA`, WhatsApp vars, `KNOWLEDGE_DB_PATH`. (`.env.example` lista 5: `ANTHROPIC_API_KEY, GEMINI_API_KEY, MOTOR_IA, WHATSAPP_APROBADOR, UMBRAL_CONFIANZA`; `config.py` añade `GOOGLE_VISION_API_KEY`, `WHATSAPP_BRIDGE_URL`.)
- **Deploy:** push a `master` → Render redeploy (autoDeploy) + Firebase (dependiendo del flujo). Últimos commits en prod: `2591bfb` (fianza) + `f9e5d5b` (FASE 14).
- **Rollback:** Render mantiene deploys anteriores (free tier: limitado); Postgres no se describe backup automático en `render.yaml` (free tier de postgres gestionado sí incluye backups; no configurado explícitamente aquí).
- **Logs:** Render logs (stdout uvicorn); no centralización ni alertas configuradas en repo.
- **Health:** `GET /` → `{"status":"ok","servicio":"RemateUp API"}`.
- **Smoke:** `production/smoke.py`.
- **Base de datos:** Postgres `remateup-db` (prod); sqlite local `backend/data/remateup.db` (dev). 4 tablas V1: documentos(3), auditoria(130), avisos(39), aprobaciones(3). V2 knowledge sqlite (`knowledge.db`, ~vacío).
- **Backups:** Postgres Render free incluye backups gestionados (no configurado en repo). Local: sqlite no respaldado.
- **Estado actual:** prod activo, V1 operativo sobre texto; V2 no productivo; IA solo Gemini (prod).

---

## 17. Estado de Tests

- **Suite completa (entorno local con `DATABASE_URL=sqlite:///...`):** `pytest backend/app` → **`621 passed, 2 failed, 12 errors` en 224.97s** (máx timeout alcanzado).
- **Archivo/suites:** 31 archivos `test_*.py` bajo `backend/app/v2/tests/` + `backend/app/v2/fase8/stress_test.py`.
- **`def test_` definiciones:** ~1042 (cuenta de funciones; muchos archivos usan `@parametrize` → items coleccionables superiores).
- **Items coleccionables:** 623 (con 12 errores de colección).
- **Los 12 errores:** todos `NameError: DetectedBlock` en `backend/app/v2/segmenter/models.py:13` (preexistente). Bloquea: `test_continuity, test_fase8, test_fase8_schema, test_newspaper_layout, test_phase9_parser_completion, test_pipeline_fase7, test_schema_completion, test_segmenter_{detectors,engine,models}, test_stitching, test_fix_produccion`, `fase8/stress_test.py`.
- **Los 2 fallos:** `test_phase12.py::TestParte1PDFsReales::*` → `PyMuPDF (fitz) is required for PDF processing` (no instalado).
- **Suites críticos verdes:** `test_extractor_deterministico.py` (V1 fianza) ✅; `test_hyper_learning.py` (FASE 14, 14 tests) ✅; `test_knowledge.py`(42)/`test_knowledge_v2.py`(81), `test_parser.py`(45), `test_validator.py`(50), `test_ai_phase11.py`(50), `test_approval`/`test_production`/`test_phase13.py`.
- **Cobertura:** NO configurada (sin `pytest-cov`, `conftest.py`, ni `.coveragerc`). → cobertura desconocida.
- **Regresiones:** el fianza-fix `2591bfb` y FASE-14 `f9e5d5b` no introdujeron regresiones en los 621 verdes; el entorno V2 sigue bloqueado por los 12 errores/2 fallos preexistentes.
- **Áreas sin tests/coverage:** cobertura real; integración prod con Gemini/WhatsApp; V2 end-to-end (pipeline completo sobre PDFs/imágenes reales).

---

## 18. Recomendaciones para GPT-5.5

Esta es la sección más importante. Leer atentamente:

1. **NO reinventar arquitectura.** V1 y V2 ya existen y están estructuradas. Trabaja DENTRO de los módulos existentes.
2. **No crear Parser V3.** Usa `panama_remate.py`/`colombia_remate.py` + `ParserFactory`/`ParserRegistry`. Mejora regex dentro del parser existente.
3. **No crear Validator V3.** Usa `backend/app/v2/validator/orchestrator.py`; respeta el shape de `validate_notice` y `ValidationResult.to_dict()`.
4. **No crear Knowledge V3.** Usa `knowledge/repository.py` (schema fijado); `trainer.py` (thresholds 0.7/1). No cambies tablas sin migración deliberada.
5. **No crear IA nueva.** El stack IA está en `parser/ai/`: `policy.py` (qué campos/tokens), `providers.py` (registro de resolvers), `integration.py` (fallback). Agrega proveedores al registro; no toques el parser/knowledge/validator/certification directamente. El fallback `LocalResolver` garantiza que el pipeline funcione sin keys.
6. **No romper V1.** V1 es prod. `pipeline/`, `routers/`, `models.py`, `main.py`. El fianza-fix (`2591bfb`) y exports (`descripcion_completa`) deben seguir verdes.
7. **No romper V2.** `runner.py` (14 etapas) y sus stages. El orden de etapas y el `final_json` shape son consumidos por tests y futuras fases.
8. **Mantener compatibilidad.** API V1, contrato JSON del frontend, exports Excel, formatos de `codigo_prensa` (ej. `LE08JUL20261C`).
9. **Priorizar Panamá.** Las sugerencias/regex/flags favorecen PA (`config.py`, `knowledge`), pero no romper CO.
10. **Mantener Colombia.** Regla fianza 40% asumida, mínimos `{70,50,100}`.
11. **Corregir bugs antes que crear funciones.** Prioriza: segmenter `NameError`, PyMuPDF, psycopg2.
12. **Reducir deuda técnica.** Separa frontend, quita borrado físico de `limpiar_bd` (o documenta el riesgo), añade CI.
13. **Aumentar precisión.** Valida V2 parser/CO con PDFs reales; popula knowledge.db.
14. **Mantener certificación.** Etapa Certification + ciclo de vida avisos.
15. **Mantener tests verdes.** `pip install -r requirements.txt` completo + `DATABASE_URL=sqlite://...` antes de correr; NO empeorar 2 fallos/12 errores.
16. **Regla de oro de FASE 14 (y futuro):** motores puros reciben dicts/devuelven dicts (determinismo); nunca modifican V1 en caliente; todo serializable; sugerencias = auditoría + aplicación explícita.

---

## 19. Plan recomendado (3 fases)

**Fase inmediata (1-2 sprints) — "Desbloquear V2 y entorno".**
- Objetivo: V2 pipeline ejecutable local y tests verdes de nuevo.
- Fix `segmenter/models.py:13` (añadir `from __future__ import annotations` o importar `DetectedBlock`) → desbloquea 12 tests.
- `pip install -r requirements.txt` completo (instalar `PyMuPDF`, `psycopg2-binary`, `pytest`, `pytest-cov`) → arregla 2 fallos + dev Postgres.
- Agregar `conftest.py`/`pytest.ini` con `DATABASE_URL=sqlite:///test.db` fixture + coverage → tests deterministas.
- Hacer correr green mínimo: 623 coleccionables → 623 pass (resuelve los 2 PyMuPDF + 12 segmenter).
- No tocar V1 ni fianza rules.

**Fase siguiente (1 sprint) — "V2 sobre texto + Knowledge vivo".**
- Objetivo: V2 PipelineRunner procesa texto (no imágenes) PA/CO y produce `final_json` válido; knowledge.db aprende de correcciones reales.
- Correr `PipelineRunner` sobre texto OCR de los 3 documentos V1 existentes; comparar salida vs V1 (`validator/consistency`, `shadow_comparisons`).
- Poblar `knowledge_aliases`/`corrections` con datos reales; aprobar rules vía `KnowledgeTrainer`.
- Tests de integración V2 texto (sin PDF).
- No tocar IA providers ni schema.

**Fase final (1-2 sprints) — "Producción híbrida V2 + reportes de calidad".**
- Objetivo: desplegar V2 como opción en prod (feature flag), con reportes de precisión/duplicados/ocorrencias.
- Añadir `AI_PROVIDER`/`ANTHROPIC_API_KEY`/`GOOGLE_VISION_API_KEY` a `render.yaml` (según decisión cliente).
- Reportes `production_diagnosis`/`client_ready` (FASE 12/14, ya en `learning/reports.py`) poblados desde prod.
- CI: GitHub Actions `pytest` + coverage gate.
- Decisión de go-live V2 vs seguir V1.

---

## 20. Resumen final

- **¿Qué tan listo para producción?** V1 **sí es operativo** en prod (39 avisos, auditoría 130 eventos, fianza/mínimo correctos, Excel con `descripcion_completa`, deploy CI continuo). V2 **no** — está construido pero bloqueado por `segmenter/models.py:13` (NameError), `PyMuPDF` no instalado y `psycopg2` faltante; no hay CI ni coverage. IA real (Gemini) configurada en prod pero **solo esa**; Claude/Vision/WhatsApp no configurados en prod.
- **¿Confianza para que GPT-5.5 continúe?** Alta, si se respetan las restricciones de §18 (no crear V3, no tocar V1/V2 sin validar, motores puros). El código está modularizado y los fixtures de tests son simples de levantar (`pip install -r requirements.txt`; `DATABASE_URL=sqlite://...`).
- **Riesgos reales:** (a) el 12-errors/2-failos de tests son **preexistentes** y bloquean V2; (b) knowledge.db vacío → el "aprendizaje" no funciona; (c) prod depende de Gemini-único con todo lo demás en fallback regex; (d) WhatsApp/Visión no configurados en prod limitan funcionalidad anunciada.
- **Oportunidades:** activar V2 vía texto (PyMuPDF+psycopg2+segmenter fix = V2 corre), poblar Knowledge con corrections reales, añadir CI, validar grid CO con PDFs reales, reportes automáticos de precisión.

---

## Anexo A — Inventario de endpoints (API)

Ver §15 para el detalle. Raíz: `GET /` (health). Documentación: `/docs`, `/redoc`, `/openapi.json` (FastAPI).

## Anexo B — Archivos clave (para navegar rápido)
- Producción V1: `backend/app/main.py`, `backend/app/models.py`, `backend/app/pipeline/{orchestrator,business_rules,extraction,validation,confidence}.py`, `backend/app/routers/*`, `backend/app/config.py`, `backend/app/database.py`.
- Refactor V2: `backend/app/v2/pipeline/runner.py`, `backend/app/v2/{document,ocr,segmenter,parser,knowledge,normalization,confidence,validator,certification}/*`.
- IA: `backend/app/v2/parser/ai/{policy,providers,integration}.py`.
- FASE 14 (commits f9e5d5b): `backend/app/learning/{engine,reports}.py`, `backend/app/routers/admin_ext.py`, `backend/app/v2/tests/test_hyper_learning.py`.
- Fianza fix (commit 2591bfb): `backend/app/pipeline/extractor_deterministico.py`, `backend/app/routers/exports.py:86/138`, `backend/app/upload/platform_uploader.py:83`.
- Infra: `render.yaml`, `frontend/firebase.json`, `frontend/.firebaserc`, `.env.example`, `backend/requirements.txt`.
- Tests: `backend/app/v2/tests/`, `backend/app/v2/fase8/stress_test.py`.
- Frontend: `frontend/public/index.html` (único archivo fuente).

## Anexo C — Comandos para levantar entorno
```bash
cd backend
pip install -r requirements.txt        # incluye PyMuPDF, psycopg2-binary, pytest
export DATABASE_URL="sqlite:///./test.db"   # requerido: backend/.env apunta a Postgres
export GEMINI_API_KEY="..."            # opcional (IA real); si no, LocalResolver regex
uvicorn app.main:app --reload
# tests:
PYTHONPATH=. DATABASE_URL="sqlite:///./test.db" pytest backend/app -q
```
(Sin `DATABASE_URL=sqlite`, `backend/.env` activa Postgres y `psycopg2` no instalado rompe la importación.)

## Anexo D — Glosario
- **PA / CO:** Panamá (pais=1) / Colombia (pais=2).
- **Fianza/mínimo:** porcentajes legales (`config.py:68-71`) → montos = `base × %/100` (`business_rules.py:108/118`).
- **codigo_prensa:** `SIGLA+DDMESAAAA+PAG` (ej. `LE08JUL20261C`) — identifica el periódico/fecha/página.
- **codigo:** interno secuencial `PA64103XXX` / `CO64104XXX`.
- **codigo_ubicacion_prensa:** código impreso en el aviso para ubicación (NO es provincia).
- **UMBRAL_CONFIANZA:** 0.70 (`config.py:26`).
- **era_vacio (Corrección):** True si el cliente llenó un campo que la IA dejó vacío (ground truth para aprendizaje).
- **Knowledge safety:** garantía de que la IA no entrena/muta Knowledge (`integration.py:19-21`).
