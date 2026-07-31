import base64
import requests
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import GOOGLE_VISION_API_KEY

VISION_URL = "https://vision.googleapis.com/v1/images:annotate"

def ocr_image(ruta):
    data = open(ruta, "rb").read()
    b64 = base64.standard_b64encode(data).decode("utf-8")
    body = {
        "requests": [{
            "image": {"content": b64},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            "imageContext": {"languageHints": ["es"]},
        }]
    }
    resp = requests.post(f"{VISION_URL}?key={GOOGLE_VISION_API_KEY}", json=body, timeout=120)
    resp.raise_for_status()
    data_json = resp.json()
    r0 = data_json.get("responses", [{}])[0]
    if "error" in r0:
        raise RuntimeError(f"Vision API error: {r0['error'].get('message', 'desconocido')}")
    anotacion = r0.get("fullTextAnnotation", {})
    plano = anotacion.get("text", "") or ""
    return plano

# OCR both images
img1 = r"C:\Users\user\Pictures\rem PAperiod\IMG-20260710-WA0016.jpg"
img2 = r"C:\Users\user\Pictures\rem PAperiod\IMG-20260710-WA0012.jpg"

print("=== OCR Imagen 1 (superior) ===")
texto1 = ocr_image(img1)
print(f"Length: {len(texto1)} chars")
# Save to file
with open("ocr_img1.txt", "w", encoding="utf-8") as f:
    f.write(texto1)

print("\n=== OCR Imagen 2 (inferior) ===")
texto2 = ocr_image(img2)
print(f"Length: {len(texto2)} chars")
with open("ocr_img2.txt", "w", encoding="utf-8") as f:
    f.write(texto2)

# Print first 2000 chars of each
print("\n=== Primeros 2000 chars de img1 ===")
print(texto1[:2000])
print("\n=== Primeros 2000 chars de img2 ===")
print(texto2[:2000])
