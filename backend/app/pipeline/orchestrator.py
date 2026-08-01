"""
Orchestrator: coordina el flujo completo, paso a paso, de forma lineal y explícita.
"""
import json
import re
from sqlalchemy.orm import Session
from ..models import Documento, Aviso
from . import extraction, business_rules, validation, confidence, audit
from ..whatsapp.notifier import enviar_solicitud_aprobacion
from ..upload.platform_uploader import subir_a_plataforma


def _sigla_periodico_de_archivo(nombre_archivo: str) -> str | None:
    """Detecta la sigla del periódico (LP/ML/LE) a partir del nombre de archivo
    que el cliente sube (ej. "LE 1c 8 julio 26 header.jpg" -> "LE")."""
    if not nombre_archivo:
        return None
    m = re.match(r"\s*(LP|ML|LE)\b", nombre_archivo.upper())
    return m.group(1) if m else None


# Cabecera del periódico impresa en la hoja, ej:
# "La Prensa Panamá, jueves 9 de julio de 2026" o "La Prensa, Panamá, 9 de julio de 2026".
# El modelo a veces no la lee como tal (quedó a mitad del texto OCR): aquí se
# detecta de forma determinista para completar periodico/fecha_prensa y poder
# generar el codigo_prensa (regla del cliente: INICIAL+DDMESAAAA+PÁGINA).
_RE_CABECERA_PERIODICO = re.compile(
    r"(La Prensa|La Estrella|Metro Libre)\s*,?\s*Panam[áa]?\s*,?\s*"
    r"(?:lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo)\s+"
    r"(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})",
    re.IGNORECASE,
)
_MESES_A_NUMERO = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11,
    "diciembre": 12,
}


def _cabecera_periodico_desde_ocr(texto_ocr: str) -> tuple[str, str] | None:
    """Devuelve (periodico, fecha_prensa YYYY-MM-DD) si la cabecera del diario
    está impresa en el texto OCR."""
    if not texto_ocr:
        return None
    m = _RE_CABECERA_PERIODICO.search(texto_ocr)
    if not m:
        return None
    dia, mes, anio = int(m.group(2)), _MESES_A_NUMERO[m.group(3).lower()], m.group(4)
    return m.group(1), f"{anio}-{mes:02d}-{dia:02d}"


def _pagina_prensa_desde_ocr(texto_ocr: str) -> str | None:
    """Código de página impreso en la esquina superior de la hoja (ej. "6B").
    Suele aparecer en las primeras líneas del texto OCR de la foto superior."""
    if not texto_ocr:
        return None
    inicio = texto_ocr[:2000]
    m = re.search(r"(?m)^\s*(\d{1,2}[A-Za-z]{1,2})\s*$", inicio)
    return m.group(1).upper() if m else None


def _ventana_aviso_ocr(texto_ocr: str, pos: int, antes: int = 2000, despues: int = 4000) -> str:
    """Recorta el texto alrededor de un expediente hasta el encabezado del
    SIGUIENTE aviso de remate, para que los patrones de monto no capten datos
    del aviso vecino cuando varios avisos quedan pegados en el mismo texto."""
    fin = min(len(texto_ocr), pos + despues)
    prox = texto_ocr.find("AVISO DE REMATE", pos + 1)
    if prox != -1:
        fin = min(fin, prox)
    return texto_ocr[max(0, pos - antes):fin]


def _buscar_base_en_ocr(datos: dict, texto_ocr: str) -> float | None:
    """Red de seguridad: si la IA no asoció el monto (base) del aviso, se busca
    determinísticamente en el texto OCR DESPUÉS del expediente (el monto de un
    aviso siempre está en el cuerpo, después de su encabezado).

    Solo patrones específicos de la base del remate son confiables:
    - "la base del remate, es decir la suma de B/.X"
    - "servirá de base para el remate la cifra de B/.X"
    - "CUANTÍA DEL EMBARGO: ... (B/.X)"
    El patrón genérico B/.X es peligroso: el folio real dentro del aviso trae
    OTROS montos (valor del traspaso, hipoteca). Solo se usa si hay una palabra
    clave de base/cuantía dentro de los 80 chars anteriores Y no hay otro aviso
    entre el expediente y el monto."""
    base = datos.get("base")
    if base not in (None, "", "null"):
        return None
    expediente = str(datos.get("expediente") or "").strip()
    if not expediente or not texto_ocr:
        return None

    pos = texto_ocr.find(expediente)
    if pos == -1:
        # Probar solo con dígitos (el OCR intercala guiones/espacios)
        solo_digitos = re.sub(r"\D", "", expediente)
        if len(solo_digitos) >= 5:
            pos = texto_ocr.find(solo_digitos)
        if pos == -1:
            return None
    # La base suele estar lejos del encabezado (el folio va en medio); el corte
    # real lo da el siguiente "AVISO DE REMATE" dentro de _ventana_aviso_ocr.
    ventana = _ventana_aviso_ocr(texto_ocr, pos, antes=0, despues=15000)

    def _monto(grupo: str) -> float | None:
        """Convierte el grupo capturado a float, tolerando el punto final de
        frase que el patrón [\\d.,]+ suele capturar de más (\"5,800.00.\")."""
        s = grupo.replace(",", "").rstrip(".")
        try:
            return float(s)
        except ValueError:
            return None

    for patron in (
        r"la base del remate\s*,?\s*es decir\s+la\s+suma\s+de\s+"
        r"[B8]\s*/\s*\.\s*([\d.,]+)",
        r"base para el remate\s+la\s+cifra\s+de\s+"
        r"[B8]\s*/\s*\.\s*([\d.,]+)",
        r"base para el remate\s*,?\s*la\s+suma\s+de"
        r"[^)]{0,200}?\(?\s*[B8]?\s*/\s*\.\s*([\d.,]+)",
        r"CUANT[IÍ]A\s+DEL\s+EMBARGO\s*:.*?\(\s*[B8]\s*/\s*\.\s*([\d.,]+)\s*\)",
    ):
        m = re.search(patron, ventana, re.IGNORECASE)
        if m:
            return _monto(m.group(1))
    # Patrón genérico: solo con palabra clave de base cerca y sin otro aviso
    # entre el expediente y el monto (el folio trae "valor del traspaso",
    # hipotecas y otros B/. que NO son la base del remate).
    resto = texto_ocr[pos:pos + 4000]
    if "AVISO DE REMATE" in resto.upper().replace("AVISO DE REMATE", "", 1):
        return None
    m = re.search(r"[B8]\s*/\s*\.\s*([\d.,]{5,})", ventana)
    if m:
        previo = ventana[max(0, m.start() - 80):m.start()].upper()
        if not any(k in previo for k in ("BASE", "AVALU", "AVALÚ", "CIFRA",
                                         "SUMA", "CUANT", "EMBARGO", "REMATE")):
            return None
        valor = _monto(m.group(1))
        return valor if valor and 500.0 < valor < 1_000_000_000 else None
    return None


def procesar_documento(db: Session, documento: Documento) -> list[Aviso]:
    audit.registrar(db, "orchestrator", "inicio_procesamiento",
                     f"Procesando {documento.nombre_archivo}", documento_id=documento.id)

    documento.estado = "procesando"
    db.commit()

    try:
        rutas = [documento.ruta_archivo]
        if documento.rutas_adicionales_json:
            rutas.extend(json.loads(documento.rutas_adicionales_json))
        salida_ocr = {}
        resultados = extraction.extraer(rutas, documento.pais, salida_ocr=salida_ocr)
        # Guardar el texto OCR en el documento (fuente para verificar/aprender)
        if salida_ocr.get("texto"):
            try:
                documento.texto_ocr = salida_ocr["texto"][:300000]
                db.commit()
            except Exception:
                db.rollback()
        audit.registrar(db, "extraction", "extraccion_completa",
                         f"{len(resultados)} aviso(s) extraído(s)", documento_id=documento.id)
    except Exception as e:
        documento.estado = "error"
        db.commit()
        audit.registrar(db, "extraction", "error", str(e), documento_id=documento.id)
        raise

    avisos_creados = []
    sigla_periodico = _sigla_periodico_de_archivo(documento.nombre_archivo)
    texto_ocr = salida_ocr.get("texto") or ""

    for idx, item in enumerate(resultados):
        try:
            item["datos"]["_sigla_periodico"] = sigla_periodico

            # Respaldos deterministas desde el texto OCR (la IA a veces no
            # asocia la cabecera del diario ni el monto si quedaron lejos):
            if texto_ocr:
                if not item["datos"].get("periodico") and not item["datos"].get("fecha_prensa"):
                    cabecera = _cabecera_periodico_desde_ocr(texto_ocr)
                    if cabecera:
                        item["datos"]["periodico"], item["datos"]["fecha_prensa"] = cabecera
                if not item["datos"].get("pagina_prensa"):
                    pagina = _pagina_prensa_desde_ocr(texto_ocr)
                    if pagina:
                        item["datos"]["pagina_prensa"] = pagina
                base_ocr = _buscar_base_en_ocr(item["datos"], texto_ocr)
                if base_ocr:
                    item["datos"]["base"] = str(base_ocr)

            datos = business_rules.aplicar_reglas(item["datos"])
            confianza_campos = item["confianza"]

            # Filtro de falsos positivos: un AVISO DE REMATE real SIEMPRE tiene
            # base/avalúo. Los avisos sin base son menciones internas del texto
            # ("DERECHO DE PROPIEDAD DE UN AVISO DE REMATE EXP. No. X"), avisos
            # de páginas vecinas que asoman cortados en la foto, o fragmentos
            # de edictos/negocios mal clasificados. No se crean (el cliente los
            # rechazaba uno a uno en el panel).
            base_aviso = datos.get("base")
            if base_aviso in (None, "", "null"):
                audit.registrar(
                    db, "orchestrator", "descartado_sin_base",
                    f"Item {idx}: exp={datos.get('expediente')!r} sin base -> "
                    f"descartado (posible falso positivo o aviso cortado)",
                    documento_id=documento.id)
                db.commit()
                continue
            audit.registrar(db, "business_rules", "reglas_aplicadas",
                             json.dumps(datos, ensure_ascii=False, default=str), documento_id=documento.id)

            faltantes = validation.campos_faltantes(datos)
            resultado_validacion = validation.evaluar_duplicado_o_republicacion(db, datos)
            discrepancia = datos.get("_discrepancia_valores", False)

            fianza_asumida = datos.get("_fianza_asumida_por_regla", False)
            decision = confidence.decidir(confianza_campos, faltantes, resultado_validacion, discrepancia, fianza_asumida)
            audit.registrar(db, "confidence", decision["decision"], decision["motivo"], documento_id=documento.id)

            aviso_reemplazado_id = resultado_validacion.get("aviso_a_reemplazar_id")
            if aviso_reemplazado_id:
                anterior = db.query(Aviso).get(aviso_reemplazado_id)
                if anterior:
                    anterior.estado = "reemplazado_por_republicacion"
                    db.commit()

            # Filtrar solo campos que existen en el modelo
            campos_aviso = {}
            for k, v in datos.items():
                if not k.startswith("_") and hasattr(Aviso, k):
                    campos_aviso[k] = v

            aviso = Aviso(
                documento_id=documento.id,
                **campos_aviso,
                confianza_promedio=decision["confianza_promedio"],
                campos_confianza_json=json.dumps(confianza_campos),
                campos_faltantes_json=json.dumps(faltantes),
                discrepancia_valores=discrepancia,
                detalle_discrepancia_json=json.dumps(datos.get("_detalle_discrepancia_valores", [])),
                fianza_asumida_por_regla=datos.get("_fianza_asumida_por_regla", False),
                tipo_validacion=resultado_validacion["tipo"],
                aviso_original_id=aviso_reemplazado_id,
                estado=decision["decision"],
            )
            db.add(aviso)
            db.commit()
            db.refresh(aviso)

            if decision["decision"] == "auto_aprobado":
                try:
                    subir_a_plataforma(aviso)
                    aviso.estado = "subido"
                    db.commit()
                except Exception as e:
                    aviso.estado = "error"
                    db.commit()

            avisos_creados.append(aviso)
        except Exception as e:
            # Log the error to audit so we can see it
            audit.registrar(db, "orchestrator", "error_aviso", f"Item {idx}: {str(e)[:500]}", documento_id=documento.id)
            db.commit()
            continue

    documento.estado = "completado"
    db.commit()
    audit.registrar(db, "orchestrator", "fin_procesamiento",
                     f"{len(avisos_creados)} aviso(s) procesado(s)", documento_id=documento.id)

    return avisos_creados
