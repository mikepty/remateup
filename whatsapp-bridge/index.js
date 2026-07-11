/**
 * WhatsApp Bridge — RemateUp
 *
 * Servicio independiente del backend Python. Mantiene la sesión de WhatsApp
 * (Baileys, no oficial) y expone dos funciones:
 *   1. POST /send -> envía un mensaje (y adjunto opcional) a un número
 *   2. Reenvía cada mensaje ENTRANTE al webhook del backend Python
 *
 * IMPORTANTE: este proceso debe quedar corriendo 24/7 para no perder la
 * sesión de WhatsApp. Si tu hosting gratuito "duerme" por inactividad,
 * la sesión se cae y hay que re-escanear el QR. Por ahora, la recomendación
 * es correr esto en tu propia laptop (con la pantalla apagada pero encendida)
 * o en un VPS barato si necesitas que sea 100% independiente de tu equipo.
 */
const express = require("express");
const fs = require("fs");
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
} = require("@whiskeysockets/baileys");
const { Boom } = require("@hapi/boom");

const PORT = process.env.PORT || 3001;
const BACKEND_WEBHOOK_URL = process.env.BACKEND_WEBHOOK_URL || "http://localhost:8000/aprobaciones/webhook";

let sock;

async function iniciarWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState("./auth_info");

  sock = makeWASocket({ auth: state, printQRInTerminal: true });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect } = update;
    if (connection === "close") {
      const shouldReconnect =
        new Boom(lastDisconnect?.error)?.output?.statusCode !== DisconnectReason.loggedOut;
      console.log("Conexión cerrada. Reintentando:", shouldReconnect);
      if (shouldReconnect) iniciarWhatsApp();
    } else if (connection === "open") {
      console.log("✅ WhatsApp conectado.");
    }
  });

  sock.ev.on("messages.upsert", async ({ messages }) => {
    const msg = messages[0];
    if (!msg.message || msg.key.fromMe) return;

    const texto =
      msg.message.conversation || msg.message.extendedTextMessage?.text || "";

    if (!texto) return;
    console.log("📩 Mensaje recibido:", texto);

    try {
      await fetch(BACKEND_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mensaje: texto, de: msg.key.remoteJid }),
      });
    } catch (e) {
      console.error("No se pudo reenviar al backend:", e.message);
    }
  });
}

// --- API HTTP para que el backend Python pida enviar mensajes ---
const app = express();
app.use(express.json());

app.post("/send", async (req, res) => {
  const { to, message, media_path } = req.body;
  if (!sock) return res.status(503).json({ error: "WhatsApp no conectado todavía" });

  try {
    const jid = to.includes("@") ? to : `${to}@s.whatsapp.net`;

    if (media_path && fs.existsSync(media_path)) {
      const ext = media_path.split(".").pop().toLowerCase();
      if (["jpg", "jpeg", "png"].includes(ext)) {
        await sock.sendMessage(jid, { image: fs.readFileSync(media_path), caption: message });
      } else {
        await sock.sendMessage(jid, {
          document: fs.readFileSync(media_path),
          fileName: media_path.split("/").pop(),
          caption: message,
        });
      }
    } else {
      await sock.sendMessage(jid, { text: message });
    }
    res.json({ status: "enviado" });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get("/", (req, res) => res.json({ status: "ok", servicio: "whatsapp-bridge" }));

app.listen(PORT, () => console.log(`WhatsApp bridge escuchando en puerto ${PORT}`));
iniciarWhatsApp();
