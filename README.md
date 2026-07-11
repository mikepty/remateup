# RemateUp — Agente Autónomo de Automatización de Avisos de Remate

Sistema que recibe documentos (imágenes, PDF), extrae información con IA,
la valida contra reglas de negocio, decide autónomamente si tiene confianza
suficiente para subirla sola o si necesita aprobación del cliente por
WhatsApp, y registra auditoría completa de cada paso.

## Arquitectura (dimensionada a 4 cargas/semana, no a millones de documentos)

```
Documento (imagen/PDF)
        ↓
  [Extracción]      Gemini 2.5 Flash lee el documento y devuelve
                     datos + confianza por campo
        ↓
[Reglas de negocio]  Codifica provincia→código interno, genera código
                     interno, calcula campos derivados
        ↓
   [Validación]      Detecta duplicados y campos requeridos faltantes
        ↓
   [Confianza]       ¿Promedio >= umbral Y sin duplicados Y sin faltantes?
        ↓                              ↓
   SÍ → Sube solo               NO → Manda WhatsApp pidiendo aprobación
        ↓                              ↓
                    [Auditoría]  Cada paso queda registrado
```

Cada "agente" de la propuesta original (OCR, extracción, clasificación,
validación, reglas, confianza) existe como módulo de Python separado en
`backend/app/pipeline/` — modular y desacoplado, pero sin la sobrecarga de
un framework de orquestación multi-agente que no aporta nada a este volumen.

## Qué está REAL y probado vs. qué falta conectar

✅ **Probado con datos reales de tu imagen de periódico:**
- Modelo de datos, base de datos, migraciones automáticas
- Reglas de negocio (generación de código interno, mapeo de provincia)
- Detección de duplicados (probado: el mismo expediente no se sube dos veces)
- Decisión de confianza (probado: alta confianza sube sola, baja confianza pide aprobación)
- Auditoría completa de cada paso
- Todos los endpoints de la API (dashboard, métricas, historial)

⏳ **Construido pero pendiente de probar con conexión real (hazlo tú esta noche/mañana):**
- Llamada real a Gemini (el código está listo, solo hay que correrlo con
  internet normal — mi entorno de pruebas bloquea ese dominio por seguridad)
- Envío real de WhatsApp (Baileys) — requiere escanear un QR la primera vez

❌ **Explícitamente NO conectado todavía (esperando al cliente):**
- Subida real a "la plataforma" — no tienes credenciales ni saben si tiene API
- Catálogos de códigos de provincia/departamento — puse un placeholder,
  hay que reemplazarlo con la tabla real (ver `backend/app/config.py`)

## Instalación y prueba local (esta noche)

### 1. Backend

```bash
cd backend
pip install -r requirements.txt --break-system-packages
export GEMINI_API_KEY="tu_api_key_nueva"   # regenera la que compartiste en el chat
uvicorn app.main:app --reload
```

Abre http://localhost:8000/docs — ahí puedes probar cada endpoint manualmente,
incluyendo subir un documento real con `/documentos/subir`.

### 2. WhatsApp bridge (opcional para probar esta noche, necesario para producción)

```bash
cd whatsapp-bridge
npm install
node index.js
```

Va a mostrar un código QR en la terminal — escanéalo con el WhatsApp del
número que va a recibir las aprobaciones (no necesita ser un número de
WhatsApp Business, puede ser un número normal).

### 3. Frontend (dashboard)

Solo abre `frontend/public/index.html` en el navegador, o despliégalo:

```bash
cd frontend
npm install -g firebase-tools
firebase login
firebase init hosting   # public directory: public, single-page app: No
firebase deploy
```

### 4. Todo junto con Docker (cuando quieras correrlo de forma persistente)

```bash
cp .env.example .env    # y pon tu API key real ahí
docker compose up --build
```

## Cosas que tienes que rellenar tú (marcadas como TODO en el código)

1. **`backend/app/config.py`** — reemplaza `CODIGOS_PROVINCIA_PA` y
   `CODIGOS_DEPARTAMENTO_CO` con el catálogo real que use la plataforma del cliente.
2. **`backend/app/pipeline/business_rules.py`** — la fórmula de porcentaje
   (`_porcentaje_minimo_sobre_base`) es un ejemplo; ajústala a la regla real.
3. **`backend/app/upload/platform_uploader.py`** — está en modo simulado.
   Cuando tengas acceso a la plataforma, actívalo (instrucciones en el archivo).
4. **`backend/app/models.py` → criterio de duplicado** — actualmente es
   "mismo expediente + fecha + país". Ajusta si el cliente usa otro criterio.

## Sobre dónde correr esto "gratis en la nube"

Sé realista con el cliente sobre esto: no existe una combinación 100% gratis,
100% siempre-activa y 100% confiable para mantener una sesión de WhatsApp
corriendo indefinidamente. Las opciones reales son:

- **Tu laptop encendida** (gratis, pero depende de tu conexión y de que no
  la apagues) — razonable para el arranque del proyecto.
- **Un VPS barato** (~$4-6/mes en Contabo, Hetzner, DigitalOcean) — la opción
  más estable, y a este precio es razonable pasárselo al cliente como costo
  de infraestructura si el proyecto crece.
- El backend (FastAPI) sí puede vivir gratis en Render/Railway (se "duerme"
  con inactividad, pero como aquí no hay tráfico constante, se despierta
  solo cuando llega un documento — la única parte que NO tolera dormirse es
  el bridge de WhatsApp).

## Próximos pasos reales

1. Corre la extracción real con Gemini esta noche/mañana, con 3-5 fotos de
   periódico reales (no solo la de la demo) para confirmar que el prompt
   funciona consistentemente.
2. Pide al cliente: acceso a la plataforma, catálogo real de códigos,
   número de WhatsApp de aprobación.
3. Recién ahí conecta WhatsApp real y la subida real a la plataforma.
