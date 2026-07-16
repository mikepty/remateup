"""
OCR con Google Cloud Vision (DOCUMENT_TEXT_DETECTION).

Transcribe TODO el texto de imágenes/PDFs de periódicos de remate.
A diferencia de los modelos multimodales (Claude/Gemini), Vision transcribe
píxel por píxel y NO inventa datos. Está diseñado para documentos densos.

Usa la API REST con API key (no requiere archivos de credenciales).
"""
import base64
import pathlib
import requests
from ..config import GOOGLE_VISION_API_KEY

VISION_URL = "https://vision.googleapis.com/v1/images:annotate"


def _ocr_imagen_bytes(data: bytes) -> str:
    """Envía una imagen (bytes) a Vision y devuelve el texto detectado."""
    if not GOOGLE_VISION_API_KEY:
        raise RuntimeError("GOOGLE_VISION_API_KEY no configurada")

    b64 = base64.standard_b64encode(data).decode("utf-8")
    body = {
        "requests": [{
            "image": {"content": b64},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            "imageContext": {"languageHints": ["es"]},
        }]
    }
    resp = requests.post(
        f"{VISION_URL}?key={GOOGLE_VISION_API_KEY}",
        json=body,
        timeout=120,
    )
    resp.raise_for_status()
    data_json = resp.json()
    respuestas = data_json.get("responses", [{}])
    if not respuestas:
        return ""
    r0 = respuestas[0]
    if "error" in r0:
        raise RuntimeError(f"Vision API error: {r0['error'].get('message', 'desconocido')}")
    anotacion = r0.get("fullTextAnnotation", {})
    return anotacion.get("text", "")


def ocr_imagen(ruta: str) -> str:
    """OCR de un archivo de imagen."""
    data = pathlib.Path(ruta).read_bytes()
    return _ocr_imagen_bytes(data)


def ocr_multiples_imagenes(rutas: list[str]) -> str:
    """OCR de varias imágenes (ej. superior + inferior de una página).
    Devuelve el texto concatenado en orden."""
    partes = []
    for i, ruta in enumerate(rutas):
        texto = ocr_imagen(ruta)
        partes.append(texto)
        print(f"[ocr_vision] Imagen {i+1}: {len(texto)} caracteres extraídos")
    return "\n\n".join(partes)


def ocr_pdf(ruta_pdf: str) -> str:
    """OCR de un PDF escaneado: renderiza cada página a imagen con PyMuPDF
    y las procesa con Vision. Devuelve el texto completo."""
    import fitz  # PyMuPDF

    doc = fitz.open(ruta_pdf)
    partes = []
    for num, pagina in enumerate(doc, 1):
        # Renderizar a imagen de alta resolución (zoom 2x = ~144 DPI)
        matriz = fitz.Matrix(2.0, 2.0)
        pix = pagina.get_pixmap(matrix=matriz)
        img_bytes = pix.tobytes("png")
        try:
            texto = _ocr_imagen_bytes(img_bytes)
            partes.append(f"--- PÁGINA {num} ---\n{texto}")
            print(f"[ocr_vision] PDF página {num}: {len(texto)} caracteres")
        except Exception as e:
            print(f"[ocr_vision] ERROR página {num}: {e}")
    doc.close()
    return "\n\n".join(partes)
