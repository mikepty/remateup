# Golden Dataset — RemateUp V2 Evaluation

## Purpose
Reference benchmark for measuring V2 pipeline accuracy against V1.
Every document has known ground truth extracted from the existing system.

## Dataset Composition

### Type A — Colombia PDF (SEJURE Bulletin)
- **File:** `SEJURE_28_JULIO_2025_JANETH_RODRIGUEZ_parte1..3.pdf`
- **Documents:** doc#1
- **Avisos:** 16 (IDs 1-16)
- **Country:** Colombia (CO)
- **Format:** Tabular PDF with selectable text
- **Parser:** pdf_colombia_parser.py (local, no AI)

### Type B — Panama Newspaper Images (Financiera Familiar)
- **Files:** `21ce358d_1.jpg`, `21ce358d_2.jpg`, `5b48a468_1.jpg`, `9a1ef910_*.jpg`, etc.
- **Documents:** doc#2
- **Avisos:** 20 (IDs 17-36)
- **Country:** Panama (PA)
- **Format:** Newspaper page photos (superior + inferior)
- **Pipeline:** Google Vision OCR → Claude extraction

### Type C — Panama Individual Avisos
- **Files:** `c84594ff_*.jpg`, `dfe0e387_*.jpg`, `IMG-20260710-WA*.jpg`
- **Documents:** doc#3
- **Avisos:** 3 (IDs 37-39)
- **Country:** Panama (PA)
- **Format:** Individual aviso photos

## Ground Truth Records

### Colombia Avisos (doc#1)
| ID | Expediente | Demandante | Demandado | Base | Fianza% | Minimo% |
|----|-----------|-----------|----------|------|---------|---------|
| 1 | 2023-01327 | Rogers Edilberto Matallana Pov | Luz Marina Cardenas Hernandez | 181080000.0 | 40 | 70 |
| 2 | 2014-00383 | BBVA | Robinson Ortiz | 337153300.0 | 40 | 70 |
| 3 | 2019-00058 | Jonathan Castañeda Gaitán | Carmen Castiblanco de Avila | 44826656.0 | 40 | 70 |
| 4 | 2017-00141 | Banco Agrario de Colombia | Flor Useche | 199250000.0 | 40 | 70 |
| 5 | 2013-00074 | Utrahuilca | null | 2797500.0 | 40 | 70 |
| 6 | 2017-01197 | BBVA | Alex Jimenez | 124720000.0 | 40 | 70 |
| 7 | 2019-00872 | Banco Davivienda | Alba Yesenia Pinilla y otros | 186661000.0 | 40 | 70 |
| 8 | 2021-00025 | Manuel Francisco Peña | Inversiones Mas Megocios SAS | 512606992.0 | 40 | 70 |
| 9 | 2024-00055 | Juan Bernardo Idarraga | Jairo Alberto Echeverry | 169764000.0 | 40 | 70 |
| 10 | 2016-00311 | Cielo Yasmin Cabrera | Lucia del Carmen Insandara | 2127300000.0 | 40 | 70 |
| 11 | 2018-00180 | Mauricio Alfonso Baron | Yudy Parra | 384955500.0 | 40 | 70 |
| 12 | 2019-00302 | Banco Davivienda | Denisse Lizcano Jimenez | 268450000.0 | 40 | 70 |
| 13 | 2016-00712 | Silvia Restrepo | Centro de Formacion Artistico | 189975000.0 | 40 | 70 |
| 14 | 2017-00455 | Bancolombia | Mauricio Ramirez | 1211881500.0 | 40 | 70 |
| 15 | 2012-00536 | Conjunto Residencial Los Lagar | Jairo Ignacio Gomez y otros | 545698500.0 | 40 | 70 |
| 16 | 2022-00933 | Banco Davivienda | Milena Carolina Ramirez | 158187000.0 | 40 | 70 |

### Panama Avisos — Financiera Familiar (doc#2, batch 1)
| ID | Expediente | Demandante | Demandado | Base | Fianza% | Minimo% |
|----|-----------|-----------|----------|------|---------|---------|
| 17-20 | 1029202000030580 | Financiera Familiar, S.A. | Ismael Bonilla Atencio | 100000.0 | 10 | 66.67 |
| 21 | 2724202000000490 | J.D.H., S.A. | Ismary del Carmen Puga | 175000.0 | 10 | 66.67 |
| 22-36 | 2724202000000300 | Financiera Familiar, S.A. | Elpidio Oses Guerra | 137000.0 | 10 | 66.67 |

### Panama Avisos — Individual (doc#3)
| ID | Expediente | Demandante | Demandado | Base | Fianza% | Minimo% |
|----|-----------|-----------|----------|------|---------|---------|
| 37 | 112235-24 | BANCO GENERAL S.A. | LUIS EDUARDO GONZALEZ ACEVEDO | 5000.0 | 10 | 66.67 |
| 38 | 76478-2025 | THE BANK OF NOVA SCOTIA | DENIS ROBERTO BORTOTO DA SILVA | 68871.8 | 10 | 66.67 |
| 39 | 8633-2025 | EL BANCO NACIONAL DE PANAMA | LESLIE KATHERINE VERGARA ENGLE | 60800.0 | 10 | 66.67 |

## Baseline Metrics (V1 System)

### Extraction Accuracy
- **Colombia PDF parser:** ~95% (deterministic, regex-based)
- **Panama newspaper (Vision → Claude):** ~90% (depends on image quality)
- **Fields with highest error rate:** `finca_matr`, `codigo_ubicacion_prensa`, `email_observaciones`

### Confidence Distribution
- **Average confidence:** ~0.85
- **Auto-approved rate:** ~60%
- **Pending approval rate:** ~40%

### Performance
- **Average processing time per document:** ~60-120s (depends on image count)
- **OCR cost per page (Vision):** ~$0.0015
- **Claude cost per extraction:** ~$0.01-0.03 per page
- **Gemini cost:** free tier available

## Critical Fields for Comparison
| Field | Priority | Notes |
|-------|----------|-------|
| expediente | HIGH | Primary ID |
| demandante | HIGH | Key entity |
| demandado | HIGH | Key entity |
| base | HIGH | Monetary value |
| finca_matr | HIGH | Property ID |
| fecha | HIGH | Remate date |
| fianza_porcentaje | MEDIUM | Legal percentage |
| minimo_porcentaje | MEDIUM | Legal percentage |
| descripcion | MEDIUM | Property description |
| provincia | MEDIUM | Location |
