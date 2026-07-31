import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline import extraction

texto1 = open("ocr_img1.txt", encoding="utf-8").read()
texto2 = open("ocr_img2.txt", encoding="utf-8").read()
texto = texto1 + "\n\n" + texto2

# Mark document boundaries
texto_marcado = extraction._marcar_limites_documentos(texto)

# Segment
posiciones = extraction._posiciones_avisos(texto_marcado)
segmentos = extraction._segmentar_por_avisos(texto_marcado)

# Show what's in each segment
print("=== ESTRUCTURA DE SEGMENTOS ===")
for i, seg in enumerate(segmentos):
    # Count document types in this segment
    remates = len(re.findall(r'AVISO\s+DE\s+REMATE', seg, re.IGNORECASE))
    edictos = len(re.findall(r'EDICTO\s+EMPLAZATORIO', seg, re.IGNORECASE))
    negocios = len(re.findall(r'NEGOCIO\s+(?:No|N[°º])', seg, re.IGNORECASE))
    disoluciones = len(re.findall(r'DISOLUCI[OÓ]N', seg, re.IGNORECASE))
    
    # Get the expediente
    exp_match = re.search(r'(?:Expediente|Exp\.|E-)\s*(?:No\.?|N[°º]\.?\s*)\s*([0-9\-]+)', seg, re.IGNORECASE)
    exp = exp_match.group(1) if exp_match else "N/A"
    
    # Get first 100 chars
    inicio = seg[:100].replace('\n', ' | ')
    
    print(f"\nSegmento {i+1}: {len(seg)} chars")
    print(f"  Remates: {remates}, Edictos: {edictos}, Negocios: {negocios}, Disoluciones: {disoluciones}")
    print(f"  Expediente: {exp}")
    print(f"  Inicio: {inicio}")

# Now let's see what's in lote 1 (the one that returned 0)
lotes = extraction._agrupar_segmentos(segmentos)
print(f"\n\n=== LOTE 1 (que devolvió 0 avisos) ===")
print(f"Length: {len(lotes[0])} chars")
# Show the markers
marcadores = [(m.start(), texto_marcado[:m.start()].count(extraction.MARCADOR_LIMITE)) 
              for m in re.finditer(extraction.MARCADOR_LIMITE, lotes[0])]
print(f"Marcadores en lote 1: {len(marcadores)}")

# Show what document types are in lote 1
remates_l1 = len(re.findall(r'AVISO\s+DE\s+REMATE', lotes[0], re.IGNORECASE))
edictos_l1 = len(re.findall(r'EDICTO\s+EMPLAZATORIO', lotes[0], re.IGNORECASE))
print(f"AVISO DE REMATE en lote 1: {remates_l1}")
print(f"EDICTO EMPLAZATORIO en lote 1: {edictos_l1}")

# Show the prompt that would be sent
print(f"\n=== LONGITUD DEL PROMPT PARA LOTE 1 ===")
prompt = extraction._construir_prompt_texto("PA")
texto_completo = f"{prompt}\n\n=== TEXTO OCR ===\n{lotes[0]}"
print(f"Prompt: {len(prompt)} chars")
print(f"Texto OCR lote: {len(lotes[0])} chars")
print(f"Total input: {len(texto_completo)} chars")

# Check if lote 1 exceeds Claude's context
print(f"\nClaude max_tokens: 16384 (output)")
print(f"Claude context window: ~200K tokens")
print(f"Input chars: {len(texto_completo)}")
print(f"Input tokens (est): {len(texto_completo) // 4}")

# Show the first 500 chars of lote 1
print(f"\n=== PRIMEROS 500 CHARS DE LOTE 1 ===")
print(lotes[0][:500])
print(f"\n=== ÚLTIMOS 500 CHARS DE LOTE 1 ===")
print(lotes[0][-500:])
