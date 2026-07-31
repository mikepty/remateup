import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

texto1 = open("ocr_img1.txt", encoding="utf-8").read()
texto2 = open("ocr_img2.txt", encoding="utf-8").read()
texto = texto1 + "\n\n" + texto2

from app.pipeline.extraction import (
    _marcar_limites_documentos, _posiciones_avisos, _segmentar_por_avisos,
    _dividir_texto, _estructurar_texto_ocr, _estructurar_texto_largo,
    _RE_ENCABEZADO_REMATE, _RE_LIMITES_DOCUMENTO, MARCADOR_LIMITE,
    LIMITE_CHARS_POR_LLAMADA, OVERLAP_CHARS, _deduplicar
)

# Step 1: Marcar limites
texto_marcado = _marcar_limites_documentos(texto)
marcadores = texto_marcado.count(MARCADOR_LIMITE)
print(f"=== Step 1: Marcar limites ===")
print(f"Marcadores insertados: {marcadores}")
print(f"Texto original: {len(texto)} chars")
print(f"Texto marcado: {len(texto_marcado)} chars")

# Step 2: Find aviso positions
posiciones = _posiciones_avisos(texto_marcado)
print(f"\n=== Step 2: Posiciones de avisos ===")
print(f"Posiciones encontradas: {len(posiciones)}")
for i, pos in enumerate(posiciones):
    ctx = texto_marcado[max(0,pos-30):pos+100].replace('\n', ' | ')
    print(f"  [{i+1}] pos={pos}: {ctx[:150]}")

# Step 3: Segmentar
segmentos = _segmentar_por_avisos(texto_marcado)
print(f"\n=== Step 3: Segmentar ===")
if segmentos:
    print(f"Segmentos: {len(segmentos)}")
    for i, seg in enumerate(segmentos):
        print(f"  Segmento {i+1}: {len(seg)} chars, empieza con: {seg[:80].replace(chr(10), ' | ')}")
else:
    print("No se pudieron segmentar (menos de 2 encabezados)")

# Step 4: Dividir en lotes
if segmentos:
    from app.pipeline.extraction import _agrupar_segmentos
    lotes = _agrupar_segmentos(segmentos)
    print(f"\n=== Step 4: Lotes ===")
    print(f"Numero de lotes: {len(lotes)}")
    for i, lote in enumerate(lotes):
        print(f"  Lote {i+1}: {len(lote)} chars")
else:
    lotes = _dividir_texto(texto_marcado)
    print(f"\n=== Step 4: Lotes (división clásica) ===")
    print(f"Numero de lotes: {len(lotes)}")
    for i, lote in enumerate(lotes):
        print(f"  Lote {i+1}: {len(lote)} chars")

# Step 5: Now run the actual extraction (this will call Claude)
print(f"\n=== Step 5: Estructurando texto largo ===")
print(f"Largo del texto: {len(texto)} chars")
print(f"LIMITE_CHARS_POR_LLAMADA: {LIMITE_CHARS_POR_LLAMADA}")
print(f"OVERLAP_CHARS: {OVERLAP_CHARS}")
if len(texto) > LIMITE_CHARS_POR_LLAMADA:
    print("Texto EXCEDE el limite - se dividirá en lotes")
else:
    print("Texto cabe en un solo lote")

# Count remates in each lote
for i, lote in enumerate(lotes):
    remates_en_lote = len(re.findall(r'AVISO\s+DE\s+REMATE', lote, re.IGNORECASE))
    print(f"  Lote {i+1}: {remates_en_lote} AVISO DE REMATE")
