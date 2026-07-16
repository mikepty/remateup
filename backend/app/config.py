import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")  # carga variables desde backend/.env si existe

# --- IA ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-3-5-haiku-20241022"

# --- Base de datos ---
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR}/data/remateup.db")

# --- Umbral de confianza ---
# 0.70 es más razonable: permite auto-aprobación cuando la extracción es
# decente. El 0.85 original causaba que TODO quedara pendiente.
UMBRAL_CONFIANZA = float(os.environ.get("UMBRAL_CONFIANZA", "0.70"))

# --- WhatsApp bridge ---
WHATSAPP_BRIDGE_URL = os.environ.get("WHATSAPP_BRIDGE_URL", "http://localhost:3001")
WHATSAPP_APROBADOR = os.environ.get("WHATSAPP_APROBADOR", "")

# --- Campos requeridos, según "INFORMACION_EXTRA_SOLICITADA.docx" del cliente ---
# El cliente distingue explícitamente entre información FUNDAMENTAL (bloquea
# si falta) y SECUNDARIA (no bloquea, aunque falte se puede subir igual).
CAMPOS_FUNDAMENTALES = [
    "fecha", "hora", "proceso", "lugar", "categoria", "demandante", "demandado",
    "descripcion", "finca_matr", "provincia", "base", "fianza_porcentaje", "minimo_porcentaje",
]
CAMPOS_SECUNDARIOS = ["expediente", "lote_casa", "superficie", "plano"]
CAMPOS_REQUERIDOS = CAMPOS_FUNDAMENTALES  # alias usado por validation.py

# --- Códigos internos OFICIALES (tabla entregada por el cliente el 2026-07-XX) ---
# Numeración CONTINUA entre los dos países -- Panamá usa 1-10, Colombia sigue en 11-43.
CODIGOS_PROVINCIA_PA = {
    "BOCAS DEL TORO": 1, "COCLE": 2, "COLON": 3, "CHIRIQUI": 4, "DARIEN": 5,
    "HERRERA": 6, "LOS SANTOS": 7, "PANAMA": 8, "PANAMA OESTE": 9, "VERAGUAS": 10,
}
CODIGOS_DEPARTAMENTO_CO = {
    "ANTIOQUIA": 11, "AMAZONAS": 12, "ARAUCA": 13, "ATLANTICO": 14,
    "BOGOTA": 15, "BOGOTA D.C": 15, "BOGOTA DC": 15,
    "BOLIVAR": 16, "BOYACA": 17, "CALDAS": 18, "CAQUETA": 19, "CASANARE": 20,
    "CAUCA": 21, "CESAR": 22, "CHOCO": 23, "CORDOBA": 24, "CUNDINAMARCA": 25,
    "GUAINIA": 26, "GUAVIARE": 27, "HUILA": 28, "LA GUAJIRA": 29, "MAGDALENA": 30,
    "META": 31, "NARINO": 32, "NORTE DE SANTANDER": 33, "PUTUMAYO": 34,
    "QUINDIO": 35, "RISARALDA": 36, "SAN ANDRES Y PROVIDENCIA": 37,
    "SANTANDER": 38, "SUCRE": 39, "TOLIMA": 40, "VALLE DEL CAUCA": 41,
    "VAUPES": 42, "VICHADA": 43,
}

# Categorías oficiales (docx del cliente) -- ya NO son texto libre, son estas 5 exactas.
CODIGOS_CATEGORIA = {
    "CASA": 1, "APARTAMENTO": 2, "TERRENO": 3, "VEHICULO": 4, "MISCELANEO": 5,
}

# --- Porcentajes válidos de fianza/mínimo, según el docx del cliente ---
# El aviso indica el porcentaje aplicable; el sistema valida que lo leído
# esté dentro de este conjunto permitido (si no, es probable error de OCR).
PORCENTAJES_FIANZA_VALIDOS_PA = [10, 20, 25]
PORCENTAJES_MINIMO_VALIDOS_PA = [66.67, 50, 100]  # 2/3, mitad, totalidad
PORCENTAJES_FIANZA_VALIDOS_CO = [40]
PORCENTAJES_MINIMO_VALIDOS_CO = [70, 50, 100]
TOLERANCIA_PORCENTAJE = 1.0  # margen en puntos porcentuales antes de marcar discrepancia

# --- Ventana legal de republicación (mismo aviso publicado varios días seguidos) ---
VENTANA_REPUBLICACION_DIAS = 3
# El cliente pidió explícitamente: de las publicaciones repetidas, quedarse
# con la ÚLTIMA como la versión válida a subir (ver pipeline/validation.py).

