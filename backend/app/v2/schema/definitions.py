"""FASE 8.10.1 — Canonical field catalog.

Every field definition lives here and ONLY here. The catalog was built by
auditing the actual field lists used by each module:

- Parser (_PATTERNS in panama_remate.py / colombia_remate.py): 6 fields
- Normalizer (FIELD_NORMALIZERS in normalizer.py): 33 fields
- Validator (production_rules.py: STRONG/MEDIUM/WEAK_FIELDS): 15 fields
- Golden Dataset (records.json suites + golden_dataset.py get_field_coverage): 13 fields
- Regression (regression.py COMPARISON_FIELDS + V1_TO_V2_FIELD_MAP): 12 fields
- Knowledge: dynamic (any field_name) — supported for every field
- Confidence: field-agnostic — supported for every field
"""

from backend.app.v2.schema.models import FieldDefinition


def _f(name, display, desc, data_type, countries, doc_types=("pdf_tabular", "newspaper_images", "individual_images"),
       required=True, priority="medium", parser=False, validator=False, normalizer=False,
       golden=False, certification=False, regression=False, aliases=(), examples=()):
    return FieldDefinition(
        field_name=name,
        display_name=display,
        description=desc,
        data_type=data_type,
        country=set(countries),
        document_type=set(doc_types),
        required=required,
        priority=priority,
        parser_supported=parser,
        knowledge_supported=True,
        validator_supported=validator,
        normalizer_supported=normalizer,
        confidence_supported=True,
        golden_dataset_supported=golden,
        certification_supported=certification,
        regression_supported=regression,
        aliases=list(aliases),
        examples=list(examples),
    )


FIELD_CATALOG: list[FieldDefinition] = [
    # --- Core fields produced by the parser (PA + CO) ---
    _f("expediente", "Expediente", "Case docket number of the remate",
       "text", ("PA", "CO"), required=True, priority="critical",
       parser=True, validator=True, normalizer=True, golden=True, certification=True, regression=True,
       aliases=["numero_expediente", "n_expediente"],
       examples=["2019-00302", "1029202000030580", "112235-24"]),
    _f("finca", "Finca", "Property identifier (V2 canonical)",
       "number", ("PA", "CO"), required=False, priority="high",
       parser=True, validator=True, normalizer=True, golden=False, certification=True, regression=True,
       aliases=["finca_matr"],
       examples=["123456", "987654"]),
    _f("precio_base", "Precio Base", "Base auction price (V2 canonical)",
       "currency", ("PA", "CO"), required=True, priority="critical",
       parser=True, validator=True, normalizer=True, golden=False, certification=True, regression=True,
       aliases=["base", "base_remate"],
       examples=["181080000", "100000"]),
    _f("fecha_remate", "Fecha de Remate", "Auction date (V2 canonical)",
       "date", ("PA", "CO"), required=False, priority="high",
       parser=True, validator=True, normalizer=True, golden=False, certification=True, regression=True,
       aliases=["fecha", "fecha_aviso"],
       examples=["2025-08-12", "2026-07-30"]),
    _f("demandante", "Demandante", "Plaintiff / creditor name",
       "name", ("PA", "CO"), required=True, priority="critical",
       parser=True, validator=True, normalizer=True, golden=True, certification=True, regression=True,
       aliases=["actor", "ejecutante"],
       examples=["Banco Davivienda", "BANCO GENERAL S.A."]),
    _f("demandado", "Demandado", "Defendant / debtor name",
       "name", ("PA", "CO"), required=True, priority="critical",
       parser=True, validator=True, normalizer=True, golden=True, certification=True, regression=True,
       aliases=["deudor", "ejecutado"],
       examples=["Flor Useche", "LUIS EDUARDO GONZALEZ ACEVEDO"]),

    # --- Colombia-only remate fields ---
    _f("fianza_porcentaje", "Fianza %", "Deposit percentage over base price (CO)",
       "number", ("CO",), doc_types=("pdf_tabular",), required=True, priority="high",
       parser=True, validator=True, normalizer=True, golden=True, certification=True, regression=True,
       examples=["40"]),
    _f("minimo_porcentaje", "Mínimo %", "Minimum bid percentage over base price (CO)",
       "number", ("CO",), doc_types=("pdf_tabular",), required=True, priority="high",
       parser=True, validator=True, normalizer=True, golden=True, certification=True, regression=True,
       examples=["70"]),
    _f("lugar", "Lugar", "Court / auction location (CO)",
       "location", ("CO",), doc_types=("pdf_tabular",), required=False, priority="medium",
       validator=True, normalizer=True, regression=True),
    _f("proceso", "Proceso", "Legal process identifier (CO)",
       "text", ("CO",), doc_types=("pdf_tabular",), required=False, priority="medium",
       validator=True, normalizer=True, regression=True),
    _f("categoria", "Categoría", "Auction category (CO)",
       "text", ("CO",), doc_types=("pdf_tabular",), required=False, priority="medium",
       validator=True, normalizer=True, regression=True),
    _f("hora", "Hora", "Auction time (CO)",
       "text", ("CO",), doc_types=("pdf_tabular",), required=False, priority="low",
       validator=True, normalizer=True),
    _f("descripcion", "Descripción", "Property description",
       "text", ("PA", "CO"), required=False, priority="medium",
       normalizer=True, golden=True),
    _f("fianza", "Fianza", "Deposit amount (absolute)",
       "currency", ("PA", "CO"), required=False, priority="low",
       normalizer=True),
    _f("minimo", "Mínimo", "Minimum bid amount (absolute)",
       "currency", ("PA", "CO"), required=False, priority="low",
       normalizer=True),

    # --- Panama newspaper / individual aviso fields ---
    _f("provincia", "Provincia", "Panama province",
       "location", ("PA",), doc_types=("newspaper_images", "individual_images"), required=False, priority="medium",
       validator=True, normalizer=True, regression=True),
    _f("descripcion_completa", "Descripción Completa", "Full aviso text description (PA)",
       "text", ("PA",), doc_types=("newspaper_images", "individual_images"), required=False, priority="medium",
       normalizer=True),
    _f("codigo_ubicacion", "Código de Ubicación", "Property location code (PA)",
       "text", ("PA",), doc_types=("newspaper_images", "individual_images"), required=False, priority="medium",
       normalizer=True),
    _f("codigo_ubicacion_prensa", "Código Ubicación Prensa", "Newspaper location code (PA)",
       "text", ("PA",), doc_types=("newspaper_images",), required=False, priority="medium",
       normalizer=True),
    _f("codigo_fuente", "Código Fuente", "Source code (PA)",
       "text", ("PA",), doc_types=("newspaper_images", "individual_images"), required=False, priority="low",
       normalizer=True),
    _f("codigo_prensa", "Código Prensa", "Newspaper publication code (PA)",
       "text", ("PA",), doc_types=("newspaper_images",), required=False, priority="low",
       normalizer=True),
    _f("fecha_prensa", "Fecha Prensa", "Newspaper publication date (PA)",
       "date", ("PA",), doc_types=("newspaper_images",), required=False, priority="low",
       normalizer=True),
    _f("pagina_prensa", "Página Prensa", "Newspaper page number (PA)",
       "number", ("PA",), doc_types=("newspaper_images",), required=False, priority="low",
       normalizer=True),
    _f("periodico", "Periódico", "Newspaper name (PA)",
       "text", ("PA",), doc_types=("newspaper_images",), required=False, priority="low",
       normalizer=True),
    _f("email_observaciones", "Email Observaciones", "Observations contact email (PA)",
       "text", ("PA",), doc_types=("newspaper_images", "individual_images"), required=False, priority="low",
       normalizer=True),
    _f("lote_casa", "Lote / Casa", "Lot or house identifier (PA)",
       "text", ("PA",), doc_types=("newspaper_images", "individual_images"), required=False, priority="medium",
       normalizer=True),
    _f("plano", "Plano", "Survey plan number (PA)",
       "text", ("PA",), doc_types=("newspaper_images", "individual_images"), required=False, priority="medium",
       normalizer=True),
    _f("superficie", "Superficie", "Property surface (PA)",
       "number", ("PA",), doc_types=("newspaper_images", "individual_images"), required=False, priority="medium",
       normalizer=True),
    _f("prevista", "Prevista", "Auction foreseen date (PA)",
       "text", ("PA",), doc_types=("newspaper_images", "individual_images"), required=False, priority="low",
       normalizer=True),
    _f("codigo", "Código", "Generic code (PA)",
       "text", ("PA",), doc_types=("newspaper_images", "individual_images"), required=False, priority="low",
       normalizer=True),

    # --- V1 / golden dataset field names (aliases of V2 canonical names) ---
    _f("base", "Base (V1)", "V1 / golden name for precio_base",
       "currency", ("PA", "CO"), required=True, priority="critical",
       validator=True, normalizer=True, golden=True, certification=True, regression=True,
       aliases=["precio_base"]),
    _f("finca_matr", "Finca Matrícula (V1)", "V1 / golden name for finca",
       "text", ("PA", "CO"), required=False, priority="high",
       validator=True, normalizer=True, golden=True, certification=True, regression=True,
       aliases=["finca"]),
    _f("fecha", "Fecha (V1)", "V1 / golden name for fecha_remate",
       "date", ("PA", "CO"), required=False, priority="high",
       validator=True, normalizer=True, golden=True, certification=True, regression=True,
       aliases=["fecha_remate"]),
]


def get_definitions() -> list[FieldDefinition]:
    return list(FIELD_CATALOG)


def get_definition(field_name: str) -> FieldDefinition:
    for d in FIELD_CATALOG:
        if d.field_name == field_name:
            return d
    raise KeyError(f"Field '{field_name}' not defined in the schema registry")


def is_defined(field_name: str) -> bool:
    return any(d.field_name == field_name for d in FIELD_CATALOG)
