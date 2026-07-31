import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

texto1 = open("ocr_img1.txt", encoding="utf-8").read()
texto2 = open("ocr_img2.txt", encoding="utf-8").read()
texto = texto1 + "\n\n" + texto2

with open("ocr_combined.txt", "w", encoding="utf-8") as f:
    f.write(texto)

# Find all AVISO DE REMATE occurrences with context
headers = []
for m in re.finditer(r"AVISO\s+DE\s+REMATE", texto, re.IGNORECASE):
    start = m.start()
    prev = texto[max(0, start-40):start]
    line_start = prev.rfind('\n')
    prev_line = prev[line_start+1:] if line_start >= 0 else prev
    is_header = prev_line.strip() == "" or prev_line.strip().endswith('\n')
    headers.append((start, is_header, prev_line.strip()))

print(f"Total AVISO DE REMATE: {len(headers)}")
print(f"  Likely headers (start of line): {sum(1 for _, h, _ in headers if h)}")
print(f"  In-text (mid-sentence): {sum(1 for _, h, _ in headers if not h)}")

# Find EDICTO occurrences
edictos = []
for m in re.finditer(r"EDICTO\s+EMPLAZATORIO", texto, re.IGNORECASE):
    edictos.append(m.start())
print(f"\nEDICTO EMPLAZATORIO: {len(edictos)} occurrences")

for m in re.finditer(r"EDICTO\s+(?:No|N.|N[°º])", texto, re.IGNORECASE):
    edictos.append(m.start())
print(f"EDICTO (general): {len(edictos)} occurrences")

# Find NEGOCIO occurrences
negocios = [m.start() for m in re.finditer(r"NEGOCIO\s+(?:No|N.)", texto, re.IGNORECASE)]
print(f"NEGOCIO: {len(negocios)} occurrences")

# Find DISOLUCION occurrences
disoluciones = [m.start() for m in re.finditer(r"DISOLUCI[OÓ]N", texto, re.IGNORECASE)]
print(f"DISOLUCION: {len(disoluciones)} occurrences")

# Print context around each AVISO DE REMATE header
print("\n=== Context around each AVISO DE REMATE ===")
for i, (pos, is_header, prev_line) in enumerate(headers):
    ctx = texto[pos:pos+200].replace('\n', ' | ')
    print(f"\n[{i+1}] pos={pos} header={is_header} prev='{prev_line[:50]}'")
    print(f"    {ctx[:200]}")
