"""
Utilidad para dividir PDFs grandes en bloques de páginas.

Necesario porque documentos largos (ej. el PDF semanal de Colombia, ~75
páginas) generan una respuesta JSON tan extensa que se puede cortar por el
límite de tokens de salida de Gemini, incluso con max_output_tokens al
máximo (confirmado en pruebas reales: 19 páginas ya se truncó en 55 avisos).
Procesar en bloques de páginas más chicos evita ese problema.
"""
import pathlib
import tempfile
from pypdf import PdfReader, PdfWriter

PAGINAS_POR_BLOQUE = 8  # ajustable -- si sigue truncándose, bajar este número


def contar_paginas(pdf_path: str) -> int:
    return len(PdfReader(pdf_path).pages)


def dividir_en_bloques(pdf_path: str, paginas_por_bloque: int = PAGINAS_POR_BLOQUE) -> list[str]:
    """
    Divide un PDF en archivos temporales de N páginas cada uno.
    Devuelve la lista de rutas de los archivos temporales creados.
    El llamador es responsable de borrarlos después de usarlos.
    """
    reader = PdfReader(pdf_path)
    total_paginas = len(reader.pages)
    bloques = []

    for inicio in range(0, total_paginas, paginas_por_bloque):
        writer = PdfWriter()
        fin = min(inicio + paginas_por_bloque, total_paginas)
        for i in range(inicio, fin):
            writer.add_page(reader.pages[i])

        temp = tempfile.NamedTemporaryFile(suffix=f"_paginas_{inicio+1}-{fin}.pdf", delete=False)
        with open(temp.name, "wb") as f:
            writer.write(f)
        bloques.append(temp.name)

    return bloques


def limpiar_bloques(rutas: list[str]):
    for ruta in rutas:
        try:
            pathlib.Path(ruta).unlink(missing_ok=True)
        except Exception:
            pass
