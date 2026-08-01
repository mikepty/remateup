from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class Documento(Base):
    """Un archivo recibido (imagen, PDF o Excel). Puede tener más de un
    archivo asociado si una página larga de periódico se fotografía en
    partes (ej. mitad superior + mitad inferior de la misma columna)."""
    __tablename__ = "documentos"

    id = Column(Integer, primary_key=True)
    nombre_archivo = Column(String, nullable=False)
    ruta_archivo = Column(String, nullable=False)  # archivo principal (o único)
    rutas_adicionales_json = Column(Text, nullable=True)  # JSON list de rutas extra (ej. mitad inferior)
    pais = Column(String(2), nullable=False)  # PA o CO
    estado = Column(String, default="recibido")  # recibido, procesando, completado, error
    texto_ocr = Column(Text, nullable=True)  # texto crudo extraído por OCR (fuente para verificar/aprender)
    creado_en = Column(DateTime, default=datetime.utcnow)

    avisos = relationship("Aviso", back_populates="documento")


class Aviso(Base):
    """Un aviso de remate extraído de un documento (puede haber varios por documento)."""
    __tablename__ = "avisos"

    id = Column(Integer, primary_key=True)
    documento_id = Column(Integer, ForeignKey("documentos.id"))

    # Campos de negocio (según Excel del cliente)
    pais = Column(Integer)  # 1=PA, 2=CO
    codigo = Column(String)
    fecha = Column(String)
    hora = Column(String)
    proceso = Column(String)
    expediente = Column(String)
    lugar = Column(String)
    categoria = Column(String)
    categoria_codigo = Column(Integer, nullable=True)  # 1=Casa,2=Apto,3=Terreno,4=Vehiculo,5=Misceláneo
    demandante = Column(String)
    demandado = Column(String)
    lote_casa = Column(String)
    descripcion = Column(Text)  # descripcion del bien
    superficie = Column(String)
    finca_matr = Column(String)
    codigo_ubicacion = Column(String)
    provincia = Column(String)
    plano = Column(String)
    base = Column(String)
    fianza_porcentaje = Column(Float, nullable=True)  # % indicado en el aviso (ej. 10, 20, 25, 40)
    minimo_porcentaje = Column(Float, nullable=True)  # % indicado en el aviso (ej. 66.67, 50, 70, 100)
    fianza = Column(String)   # monto calculado = base * fianza_porcentaje/100
    minimo = Column(String)   # monto calculado = base * minimo_porcentaje/100
    fianza_asumida_por_regla = Column(Boolean, default=False)  # True = Colombia 40% aplicado por regla, no leído del OCR
    codigo_fuente = Column(String, nullable=True)  # periódico/fecha/página de donde salió (ej. "PA10ABRP23")
    codigo_prensa = Column(String, nullable=True)  # LP/ML/LE/SEJ + fecha periódico + página (ej. "LP-2025-07-28-P23")
    email_observaciones = Column(String, nullable=True)  # correo electrónico extraído de observaciones
    descripcion_completa = Column(Text, nullable=True)  # descripción completa del bien (detalle largo)
    prevista = Column(Text, nullable=True)  # texto limpio de ubicación para Google Maps (ej. "332 m2, PH Princesa y Condesa del Mar, Corr: Bella Vista, Dist: Panamá")
    codigo_ubicacion_prensa = Column(String, nullable=True)  # código de ubicación REAL impreso en el periódico, junto a la finca/folio (NO es el código de provincia; número de dígitos variable, ej. "4506")
    periodico = Column(String, nullable=True)  # nombre del periódico TAL CUAL aparece impreso en la página (ej. "La Prensa", "La Estrella", "Metro Libre")
    fecha_prensa = Column(String, nullable=True)  # fecha de la EDICIÓN del periódico (no la del remate), formato YYYY-MM-DD, leída del encabezado/pie de página
    pagina_prensa = Column(String, nullable=True)  # página impresa donde salió el aviso, tal cual aparece (ej. "7B", "1C")

    # Metadatos del proceso
    confianza_promedio = Column(Float, default=0.0)
    campos_confianza_json = Column(Text)  # JSON con confianza por campo
    campos_faltantes_json = Column(Text)  # JSON con lista de campos faltantes
    discrepancia_valores = Column(Boolean, default=False)  # fianza/mínimo no cuadran con la fórmula legal
    detalle_discrepancia_json = Column(Text, nullable=True)

    tipo_validacion = Column(String, default="nuevo")
    # nuevo, republicacion_legal_pendiente, republicacion_legal_final, duplicado_sospechoso
    aviso_original_id = Column(Integer, nullable=True)  # apunta a la publicación anterior de la misma cadena

    estado = Column(String, default="pendiente_procesar")
    # pendiente_procesar, auto_aprobado, esperando_aprobacion, aprobado, rechazado,
    # subido, reemplazado_por_republicacion, error

    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    documento = relationship("Documento", back_populates="avisos")


class Aprobacion(Base):
    """Solicitud de aprobación enviada al cliente por WhatsApp."""
    __tablename__ = "aprobaciones"

    id = Column(Integer, primary_key=True)
    aviso_id = Column(Integer, ForeignKey("avisos.id"))
    mensaje_enviado = Column(Text)
    numero_destino = Column(String)
    respuesta = Column(String, nullable=True)  # aprobado / rechazado / null (pendiente)
    respondido_en = Column(DateTime, nullable=True)
    creado_en = Column(DateTime, default=datetime.utcnow)


class Auditoria(Base):
    """Registro inmutable de cada acción/decisión del sistema."""
    __tablename__ = "auditoria"

    id = Column(Integer, primary_key=True)
    aviso_id = Column(Integer, nullable=True)
    documento_id = Column(Integer, nullable=True)
    agente = Column(String)  # ej: "extraction", "business_rules", "confidence", "whatsapp", "upload"
    accion = Column(String)
    detalle = Column(Text)
    creado_en = Column(DateTime, default=datetime.utcnow)


class Correccion(Base):
    """Corrección hecha por el cliente al editar un aviso. Es la fuente del
    APRENDIZAJE: cada vez que el cliente llena un campo vacío o corrige un
    valor, se guarda aquí. Estas correcciones se retroalimentan a la IA en
    futuras extracciones para que capte mejor lo que suele omitir o equivocar.

    Como la información que el cliente edita es la misma que aparece en la
    página del periódico, cada corrección es "verdad de terreno" (ground truth)."""
    __tablename__ = "correcciones"

    id = Column(Integer, primary_key=True)
    aviso_id = Column(Integer, nullable=True)
    campo = Column(String)              # nombre del campo corregido (ej. "expediente", "plano")
    valor_anterior = Column(Text)       # lo que la IA extrajo (puede ser vacío)
    valor_nuevo = Column(Text)          # lo correcto según el periódico (lo que puso el cliente)
    pais = Column(Integer)              # 1=PA, 2=CO
    contexto = Column(Text, nullable=True)      # descripción/texto del aviso para aprender patrones
    codigo_prensa = Column(String, nullable=True)  # fuente del aviso (LP/ML/LE/SEJ)
    era_vacio = Column(Boolean, default=False)  # True si el campo estaba vacío y el cliente lo llenó
    creado_en = Column(DateTime, default=datetime.utcnow)
