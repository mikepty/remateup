"""Explore validation results."""
import json

seg = json.loads(open("evaluation/real_data/panama_segmented.json", encoding="utf-8").read())
for p in seg["pages"]:
    print(f"--- Page {p['page_number']} ---")
    print(f"  Columns: {len(p['columns'])}")
    print(f"  Avisos: {p['total_avisos']}")
    for a in p["avisos"]:
        h = a["header_text"][:100] if a["header_text"] else "(no header)"
        print(f"    Aviso conf={a['confidence']}: {h}")
        for s in a["sections"]:
            txt = s["text_preview"][:80]
            print(f"      Section type={s['section_type']}: {txt}")
    print()

# Also check continuity
cont = json.loads(open("evaluation/real_data/panama_continuity.json", encoding="utf-8").read())
print("--- Continuity ---")
for c in cont:
    print(f"  type={c['aviso_type']} frags={c['fragment_count']} rec={c['is_reconstructed']} signals={c['continuity_signals']}")
    print(f"    text: {c['text_preview'][:200]}")
    print()

# Assembly
asm = json.loads(open("evaluation/real_data/panama_assembly.json", encoding="utf-8").read())
print("--- Assembly ---")
print(json.dumps(asm, indent=2))
