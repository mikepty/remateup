from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import DATABASE_URL
from app.models import Documento, Aviso

e = create_engine(DATABASE_URL)
s = sessionmaker(bind=e)()

# Find documents with IMG-20260710 in filename
docs = s.query(Documento).filter(Documento.nombre_archivo.like("%IMG-20260710%")).all()
for d in docs:
    ocr_len = len(d.texto_ocr) if d.texto_ocr else 0
    print(f"id={d.id} nombre={d.nombre_archivo} pais={d.pais} estado={d.estado} creado={d.creado_en} avisos={len(d.avisos)} ocr_len={ocr_len}")
    if d.rutas_adicionales_json:
        print(f"  rutas_adicionales: {d.rutas_adicionales_json}")

# Also find documents by the avisos we saw
avisos = s.query(Aviso).filter(Aviso.codigo.like("PA6410300%")).order_by(Aviso.id).all()
for a in avisos:
    print(f"aviso id={a.id} codigo={a.codigo} expediente={a.expediente} documento_id={a.documento_id} estado={a.estado} creado={a.creado_en}")
