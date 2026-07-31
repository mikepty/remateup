import re
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline import extraction

texto1 = open("ocr_img1.txt", encoding="utf-8").read()
texto2 = open("ocr_img2.txt", encoding="utf-8").read()
texto = texto1 + "\n\n" + texto2

# Step 1: Mark document boundaries
texto_marcado = extraction._marcar_limites_documentos(texto)
print(f"Marcadores insertados: {texto_marcado.count(extraction.MARCADOR_LIMITE)}")

# Step 2: Segment by aviso headers
posiciones = extraction._posiciones_avisos(texto_marcado)
print(f"Posiciones de avisos: {len(posiciones)}")

segmentos = extraction._segmentar_por_avisos(texto_marcado)
if segmentos:
    print(f"Segmentos: {len(segmentos)}")
    lotes = extraction._agrupar_segmentos(segmentos)
else:
    lotes = extraction._dividir_texto(texto_marcado)
    print(f"Lotes (división clásica): {len(lotes)}")

print(f"\nNumero de lotes: {len(lotes)}")
for i, lote in enumerate(lotes):
    remates = len(re.findall(r'AVISO\s+DE\s+REMATE', lote, re.IGNORECASE))
    print(f"  Lote {i+1}: {len(lote)} chars, {remates} AVISO DE REMATE")

# Step 3: Run actual extraction on each lote
print("\n=== Ejecutando extracción en cada lote ===")
todos_resultados = []
for i, lote in enumerate(lotes):
    print(f"\n--- Lote {i+1}/{len(lotes)} ({len(lote)} chars) ---")
    try:
        resultado = extraction._estructurar_texto_ocr(lote, "PA")
        print(f"  Resultado: {len(resultado)} avisos")
        for item in resultado:
            d = item.get("datos", {})
            print(f"    expediente={d.get('expediente')}, finca={d.get('finca_matr')}, "
                  f"demandado={str(d.get('demandado'))[:50] if d.get('demandado') else 'None'}, "
                  f"base={d.get('base')}")
        todos_resultados.extend(resultado)
    except Exception as e:
        print(f"  ERROR: {e}")

# Step 4: Deduplicate
print(f"\n=== Antes de deduplicar: {len(todos_resultados)} avisos ===")
deduplicados = extraction._deduplicar(todos_resultados)
print(f"=== Después de deduplicar: {len(deduplicados)} avisos ===")

# Step 5: Print summary of each aviso
print("\n=== RESUMEN DE AVISOS FINALES ===")
for i, item in enumerate(deduplicados):
    d = item.get("datos", {})
    print(f"\n[{i+1}] expediente={d.get('expediente')}, finca={d.get('finca_matr')}")
    print(f"    demandante={str(d.get('demandante'))[:60] if d.get('demandante') else 'None'}")
    print(f"    demandado={str(d.get('demandado'))[:60] if d.get('demandado') else 'None'}")
    print(f"    descripcion={str(d.get('descripcion'))[:80] if d.get('descripcion') else 'None'}")
    print(f"    descripcion_completa={str(d.get('descripcion_completa'))[:80] if d.get('descripcion_completa') else 'None'}...")
    print(f"    base={d.get('base')}, fianza_pct={d.get('fianza_porcentaje')}, minimo_pct={d.get('minimo_porcentaje')}")
    email = d.get('email_observaciones')
    print(f"    email_observaciones={'None' if not email else str(email)[:80]}")
    print(f"    codigo_prensa={d.get('codigo_prensa')}, periodico={d.get('periodico')}, fecha_prensa={d.get('fecha_prensa')}, pagina_prensa={d.get('pagina_prensa')}")
    print(f"    codigo_ubicacion_prensa={d.get('codigo_ubicacion_prensa')}")
