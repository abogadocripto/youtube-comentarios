/* ============================================================================
   YouTube Reply Assistant v2 — service worker
   ----------------------------------------------------------------------------
   Responsabilidades:
     · Custodiar la API key (el content script ya no la recibe ni la maneja)
     · Llamar a la API de Anthropic con timeout y reintentos
     · Obtener la transcripcion del video de forma robusta, con cache
     · Insertar texto en el mundo principal cuando execCommand no basta
   ========================================================================== */

"use strict";

const DEFAULTS = {
  apiKey: "",
  model: "claude-sonnet-4-6",
  extendedThinking: true,
  extraContext: "",
  customInstructions: "",
  mode: "auto",
  countdown: 4,
  requireTranscript: true,
  debug: true,
};

const MAX_TRANSCRIPT_CHARS = 15000; // la v1 cortaba en 3000 (~2 min de video)
const TRANSCRIPT_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const FAIL_TTL_MS = 60 * 60 * 1000;      // un fallo se reintenta como mucho cada hora
const STRATEGY_TIMEOUT_MS = 6000;         // por estrategia
const TRANSCRIPT_DEADLINE_MS = 12000;     // tope global: nunca mas de 12 s esperando
const API_TIMEOUT_MS = 120000;

const memCache = new Map();

/* ── Migracion de storage.sync a storage.local ───────────────────────────────
   OJO: esto NO recupera la key de la extension v1. chrome.storage esta aislado
   por extension, y la v1 y la v2 tienen IDs distintos. Solo sirve si en algun
   momento esta misma extension guardo algo en sync. La key de la v2 se
   introduce a mano la primera vez.
   El destino es local, no sync, porque sync se replica a todos los Chrome donde
   tengas la sesion de Google iniciada y esta es una credencial con cargo
   directo.                                                                  */
chrome.runtime.onInstalled.addListener(async () => {
  try {
    const sync = await chrome.storage.sync.get({ apiKey: "", extraContext: "" });
    const local = await chrome.storage.local.get({ apiKey: "" });
    if (!local.apiKey && sync.apiKey) {
      await chrome.storage.local.set({ apiKey: sync.apiKey, extraContext: sync.extraContext || "" });
      await chrome.storage.sync.remove(["apiKey"]);
      console.log("[YRA2] API key migrada de storage.sync a storage.local");
    }
  } catch (e) {
    console.warn("[YRA2] migracion:", e.message);
  }
});

/* ══════════════════════════════════════════════════════════════════════════
   Router de mensajes
   ══════════════════════════════════════════════════════════════════════════ */

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const handlers = {
    GENERATE_REPLY: () => handleGenerate(message.payload),
    FETCH_TRANSCRIPT: () => handleTranscript(message.payload),
    INSERT_MAIN: () => handleInsertMain(message.payload, sender),
    TEST_API: () => handleTest(),
    DIAGNOSE: () => handleDiagnose(message.payload),
    PING: async () => ({ ok: true }),
  };
  const h = handlers[message?.type];
  if (!h) return false;

  h().then(sendResponse).catch((e) => sendResponse({ ok: false, error: e.message }));
  return true; // canal abierto para la respuesta asincrona
});

/* ══════════════════════════════════════════════════════════════════════════
   1. Generacion de la respuesta
   ══════════════════════════════════════════════════════════════════════════ */

async function handleGenerate(payload) {
  const cfg = { ...DEFAULTS, ...(await chrome.storage.local.get(DEFAULTS)) };
  if (!cfg.apiKey) return { ok: false, error: "Falta la API key." };

  const { commentText, videoTitle, videoDescription, transcript } = payload;

  const body = {
    model: cfg.model,
    max_tokens: 6000,
    system: buildSystemPrompt(cfg.extraContext, videoTitle, videoDescription, cfg.customInstructions),
    messages: [
      {
        role: "user",
        content: buildUserMessage(commentText, videoTitle, videoDescription, cfg.extraContext, transcript),
      },
    ],
  };
  if (cfg.extendedThinking) {
    body.thinking = { type: "enabled", budget_tokens: 2000 };
  } else {
    body.temperature = 0.7;
  }

  // El service worker de MV3 se suspende tras unos 30 s sin actividad de la API
  // de extensiones. Con razonamiento extendido una peticion puede durar mas que
  // eso y perderse la respuesta. Este latido reinicia ese temporizador.
  const keepAlive = setInterval(() => chrome.runtime.getPlatformInfo(() => {}), 20000);
  const backoff = [0, 1500, 4000];
  let lastError = "";

  try {
    for (const espera of backoff) {
      if (espera) await sleep(espera);

      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), API_TIMEOUT_MS);
      try {
        const res = await fetch("https://api.anthropic.com/v1/messages", {
          method: "POST",
          signal: ctrl.signal,
          headers: {
            "Content-Type": "application/json",
            "x-api-key": cfg.apiKey,
            "anthropic-version": "2023-06-01",
            "anthropic-dangerous-direct-browser-access": "true",
          },
          body: JSON.stringify(body),
        });
        clearTimeout(timer);

        if (res.ok) {
          const data = await res.json();
          // Con razonamiento extendido el array de contenido trae bloques de
          // thinking antes del texto: hay que localizar el bloque de tipo text.
          const reply = data.content?.find((b) => b.type === "text")?.text ?? "";
          if (!reply.trim()) { lastError = "La API ha devuelto una respuesta vacia."; continue; }
          return { ok: true, reply, usage: data.usage || null, model: data.model || cfg.model };
        }

        const err = await res.json().catch(() => null);
        lastError = friendlyApiError(res.status, err?.error?.message || `HTTP ${res.status}`, cfg.model);
        // Solo reintentamos lo transitorio: una key invalida no mejora esperando.
        if (![429, 500, 502, 503, 529].includes(res.status)) return { ok: false, error: lastError };
      } catch (e) {
        clearTimeout(timer);
        lastError = e.name === "AbortError"
          ? "La API ha tardado demasiado (timeout)."
          : `Error de red: ${e.message}`;
      }
    }
    return { ok: false, error: lastError || "Error desconocido al llamar a la API." };
  } finally {
    clearInterval(keepAlive);
  }
}

/* Prueba minima desde el popup: valida la key Y que el modelo elegido exista
   en la cuenta, que es el fallo mas probable al cambiar de modelo. */
async function handleTest() {
  const cfg = { ...DEFAULTS, ...(await chrome.storage.local.get(DEFAULTS)) };
  if (!cfg.apiKey) return { ok: false, error: "Falta la API key." };

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 30000);
  try {
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      signal: ctrl.signal,
      headers: {
        "Content-Type": "application/json",
        "x-api-key": cfg.apiKey,
        "anthropic-version": "2023-06-01",
        "anthropic-dangerous-direct-browser-access": "true",
      },
      body: JSON.stringify({
        model: cfg.model,
        max_tokens: 16,
        messages: [{ role: "user", content: "ok" }],
      }),
    });
    clearTimeout(timer);
    if (res.ok) {
      const d = await res.json();
      return { ok: true, model: d.model || cfg.model };
    }
    const err = await res.json().catch(() => null);
    return { ok: false, error: friendlyApiError(res.status, err?.error?.message || `HTTP ${res.status}`, cfg.model) };
  } catch (e) {
    clearTimeout(timer);
    return { ok: false, error: e.name === "AbortError" ? "Timeout al conectar." : `Error de red: ${e.message}` };
  }
}

function friendlyApiError(status, msg, model) {
  if (status === 401) return "API key invalida o revocada.";
  if (status === 403) return "La API key no tiene permiso para este modelo.";
  if (status === 404) return `El modelo "${model}" no existe o no esta disponible en tu cuenta. Cambialo en los ajustes.`;
  if (status === 400 && /model/i.test(msg)) return `Modelo rechazado: ${msg}. Cambialo en los ajustes.`;
  if (status === 429) return "Limite de peticiones alcanzado. Espera unos segundos.";
  if (status === 529) return "La API esta sobrecargada. Reintentando.";
  return msg;
}

/* ══════════════════════════════════════════════════════════════════════════
   2. Transcripcion
   ══════════════════════════════════════════════════════════════════════════
   La v1 buscaba la baseUrl de subtitulos con una expresion regular sobre el
   HTML crudo. La v2.0 lo cambio por parseo JSON, lo que arreglo la deteccion
   de la pista pero no la descarga: YouTube ha endurecido el endpoint timedtext
   y una baseUrl obtenida desde una sesion que no coincide con la que descarga
   devuelve contenido vacio.

   La v2.1 ataca eso pidiendo la pista desde una sesion AUTENTICADA y, en
   primer lugar, desde la propia pestaña de Studio, donde eres el propietario
   del video. Cinco estrategias en cascada y cuatro formatos de descarga.
   ══════════════════════════════════════════════════════════════════════════ */

async function handleTranscript({ videoId }) {
  if (!videoId) return { ok: false, reason: "sin videoId" };

  const vigente = (e) =>
    e && Date.now() - e.ts < (e.value?.ok ? TRANSCRIPT_TTL_MS : FAIL_TTL_MS);

  const hit = memCache.get(videoId);
  if (vigente(hit)) return { ...hit.value, cached: true };

  const key = `tc:${videoId}`;
  const stored = (await chrome.storage.local.get(key))[key];
  if (vigente(stored)) {
    memCache.set(videoId, stored);
    return { ...stored.value, cached: true };
  }

  const value = await fetchTranscript(videoId);
  // Cacheamos TAMBIEN los fallos. Si no, cada comentario del mismo video
  // repite las cinco estrategias y las veinte peticiones de red que ya sabemos
  // que no van a funcionar: ese era el motivo real de la lentitud.
  const entry = { ts: Date.now(), value };
  memCache.set(videoId, entry);
  chrome.storage.local.set({ [key]: entry }).catch(() => {});
  pruneCache().catch(() => {});
  return value;
}

// Mantiene la cache acotada: 60 videos (~1 MB) es de sobra para trabajar la
// bandeja de comentarios y deja storage.local holgado.
async function pruneCache(max = 60) {
  const all = await chrome.storage.local.get(null);
  const keys = Object.keys(all).filter((k) => k.startsWith("tc:"));
  if (keys.length <= max) return;
  keys.sort((a, b) => (all[a]?.ts || 0) - (all[b]?.ts || 0));
  await chrome.storage.local.remove(keys.slice(0, keys.length - max));
}

/* Orden deliberado: primero las fuentes autenticadas como propietario, que son
   las que devuelven una baseUrl valida para descargar; las anonimas al final,
   solo como ultimo recurso. */
function trackStrategies(videoId) {
  return [
    ["studio", "Studio, como propietario", () => tracksFromStudio(videoId)],
    ["innertube-auth", "reproductor autenticado", () => tracksFromInnertube(videoId, "include")],
    ["watch-auth", "pagina del video con tu sesion", () => tracksFromWatch(videoId, "include")],
    ["watch-anon", "pagina del video anonima", () => tracksFromWatch(videoId, "omit")],
    ["innertube-anon", "reproductor anonimo", () => tracksFromInnertube(videoId, "omit")],
  ];
}

async function fetchTranscript(videoId) {
  const t0 = Date.now();
  const fallos = [];

  // Las cinco estrategias son independientes entre si, asi que se lanzan EN
  // PARALELO. En serie el coste era la suma de las cinco; ahora es la mas lenta.
  const resultados = await Promise.all(
    trackStrategies(videoId).map(async ([id, etiqueta, fn]) => {
      try {
        const tracks = await conTope(fn(), STRATEGY_TIMEOUT_MS, `${id}: timeout`);
        return { id, etiqueta, tracks: tracks || [] };
      } catch (e) {
        fallos.push(`${id}: ${e.message}`);
        return { id, etiqueta, tracks: [] };
      }
    })
  );

  // Se prueban en el orden de prioridad de trackStrategies, y cada URL se
  // descarga UNA sola vez aunque varias estrategias devuelvan la misma pista.
  const vistas = new Set();
  for (const { id, etiqueta, tracks } of resultados) {
    if (!tracks.length) { fallos.push(`${id}: sin pistas`); continue; }

    const track = pickTrack(tracks);
    if (!track?.baseUrl) { fallos.push(`${id}: pista sin URL`); continue; }

    const url = normalizeTrackUrl(track.baseUrl);
    const huella = url.split("&").filter((p) => /^(v|lang|kind|name)=/.test(p)).sort().join("&") || url;
    if (vistas.has(huella)) { fallos.push(`${id}: misma pista ya probada`); continue; }
    vistas.add(huella);

    if (Date.now() - t0 > TRANSCRIPT_DEADLINE_MS) { fallos.push("tope de tiempo alcanzado"); break; }

    const bruto = await downloadTrack(url);
    if (!bruto) { fallos.push(`${id}: descarga vacia`); continue; }

    const limpio = cleanTranscript(bruto);
    if (limpio.length < 40) { fallos.push(`${id}: solo ${limpio.length} caracteres`); continue; }

    console.log(`[YRA2] Transcripcion via ${id} en ${Date.now() - t0} ms (${limpio.length} car.)`);
    return {
      ok: true,
      text: limpio.slice(0, MAX_TRANSCRIPT_CHARS),
      truncated: limpio.length > MAX_TRANSCRIPT_CHARS,
      fullLength: limpio.length,
      lang: track.languageCode || "?",
      kind: track.kind === "asr" ? "automatica" : "manual",
      source: id,
      sourceLabel: etiqueta,
    };
  }

  console.warn(`[YRA2] Sin transcripcion tras ${Date.now() - t0} ms:`, fallos.join(" | "));
  return { ok: false, reason: resumirFallos(fallos), detail: fallos };
}

function conTope(promesa, ms, mensaje) {
  return Promise.race([
    promesa,
    new Promise((_, rej) => setTimeout(() => rej(new Error(mensaje)), ms)),
  ]);
}

function resumirFallos(fallos) {
  if (fallos.some((f) => f.includes("descarga vacia"))) {
    return "YouTube ha encontrado los subtitulos pero no deja descargarlos";
  }
  if (fallos.every((f) => f.includes("sin pistas"))) {
    return "el video no tiene subtitulos publicados";
  }
  return "no se ha podido obtener la transcripcion";
}

/* ── Estrategia 1: la pestaña de Studio ─────────────────────────────────────
   Es la unica peticion que sale del propio dominio de YouTube, con tus cookies
   de sesion y con el contexto de cliente de Studio (eres el propietario del
   video). Si alguna va a funcionar, es esta. Requiere una pestaña de Studio
   abierta, que es justo donde estas cuando usas la extension.               */
async function tracksFromStudio(videoId) {
  const tabs = await chrome.tabs.query({ url: "https://studio.youtube.com/*" });
  const tab = tabs?.[0];
  if (!tab?.id) throw new Error("no hay ninguna pestaña de Studio abierta");

  const res = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    world: "MAIN",
    args: [videoId],
    func: async (vid) => {
      try {
        const cfg = window.ytcfg;
        if (!cfg || typeof cfg.get !== "function") return { error: "ytcfg no disponible" };
        const ctx = cfg.get("INNERTUBE_CONTEXT");
        const apiKey = cfg.get("INNERTUBE_API_KEY");
        if (!ctx) return { error: "INNERTUBE_CONTEXT vacio" };

        const r = await fetch(`/youtubei/v1/player${apiKey ? `?key=${apiKey}` : ""}`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ videoId: vid, context: ctx }),
        });
        if (!r.ok) return { error: `HTTP ${r.status}` };
        const d = await r.json();
        return {
          tracks: d?.captions?.playerCaptionsTracklistRenderer?.captionTracks || [],
          client: `${ctx?.client?.clientName || "?"} ${ctx?.client?.clientVersion || ""}`.trim(),
        };
      } catch (e) {
        return { error: e.message };
      }
    },
  });

  const out = res?.[0]?.result;
  if (out?.error) throw new Error(out.error);
  return out?.tracks || [];
}

/* ── Estrategia 2 y 5: endpoint interno del reproductor ─────────────────── */
async function tracksFromInnertube(videoId, credentials) {
  // Clave publica del cliente web de YouTube. Es un respaldo: si YouTube la
  // cambia, este intento falla y se reporta, que es lo que queremos.
  const KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8";
  const res = await fetch(`https://www.youtube.com/youtubei/v1/player?key=${KEY}`, {
    method: "POST",
    credentials,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      videoId,
      context: {
        client: { clientName: "WEB", clientVersion: "2.20240726.00.00", hl: "es", gl: "ES" },
      },
    }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data?.captions?.playerCaptionsTracklistRenderer?.captionTracks || null;
}

/* ── Estrategia 3 y 4: la pagina /watch ─────────────────────────────────── */
async function tracksFromWatch(videoId, credentials) {
  const url = `https://www.youtube.com/watch?v=${videoId}&hl=es&bpctr=9999999999&has_verified=1`;
  const res = await fetch(url, {
    credentials,
    headers: { "Accept-Language": "es-ES,es;q=0.9,en;q=0.7" },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const html = await res.text();
  const player = extractJsonObject(html, "ytInitialPlayerResponse", looksLikePlayerResponse);
  if (!player) throw new Error("ytInitialPlayerResponse no encontrado");
  return player?.captions?.playerCaptionsTracklistRenderer?.captionTracks || null;
}

// Prioridad: castellano manual > castellano automatico > catalan > ingles > la primera.
function pickTrack(tracks) {
  const by = (pred) => tracks.find(pred);
  return (
    by((t) => /^es/i.test(t.languageCode || "") && t.kind !== "asr") ||
    by((t) => /^es/i.test(t.languageCode || "")) ||
    by((t) => /^ca/i.test(t.languageCode || "")) ||
    by((t) => /^en/i.test(t.languageCode || "")) ||
    tracks[0]
  );
}

function normalizeTrackUrl(baseUrl) {
  return String(baseUrl).replace(/\\u0026/g, "&").replace(/\\\//g, "/");
}

const FORMATOS = ["json3", "srv3", "vtt", ""];

async function downloadTrack(baseUrl) {
  const base = normalizeTrackUrl(baseUrl);
  for (const fmt of FORMATOS) {
    try {
      const r = await fetch(base + (fmt ? `&fmt=${fmt}` : ""), { credentials: "include" });
      if (!r.ok) continue;
      const cuerpo = await r.text();
      const texto = parsearPista(cuerpo, fmt);
      if (texto && texto.trim()) return texto;
    } catch (e) {
      console.warn(`[YRA2] timedtext fmt=${fmt || "(defecto)"}:`, e.message);
    }
  }
  return null;
}

function parsearPista(cuerpo, fmt) {
  if (!cuerpo) return null;

  if (fmt === "json3") {
    try {
      const j = JSON.parse(cuerpo);
      return (j.events || []).flatMap((e) => e.segs || []).map((s) => s.utf8 || "").join("");
    } catch { return null; }
  }

  if (fmt === "vtt") {
    return cuerpo
      .split("\n")
      .filter((l) => l.trim() && !/^WEBVTT|^NOTE|^\d+$|-->/.test(l))
      .join(" ");
  }

  // srv3 y el XML por defecto comparten estructura de etiquetas <text>/<p>
  const trozos = [...cuerpo.matchAll(/<(?:text|p)[^>]*>([\s\S]*?)<\/(?:text|p)>/g)];
  if (!trozos.length) return null;
  return trozos.map((m) => decodeEntities(m[1].replace(/<[^>]+>/g, ""))).join(" ");
}

function cleanTranscript(t) {
  return decodeEntities(t)
    .replace(/\[(M[uú]sica|Aplausos|Risas|Music|Applause|Laughter)\]/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function decodeEntities(s) {
  return String(s)
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)));
}

/* Extrae un objeto JSON completo a partir del nombre de una variable, contando
   llaves y respetando cadenas y escapes. Sustituye a la expresion regular
   fragil de la v1.

   El parametro validate es imprescindible: el nombre de la variable aparece
   varias veces en el HTML de YouTube, y una ocurrencia anterior puede producir
   un objeto perfectamente parseable pero equivocado (un "{}" vacio, por
   ejemplo). Sin validar, nos quedariamos con ese y dariamos el video por
   "sin subtitulos" teniendolos. */
function extractJsonObject(html, varName, validate) {
  let idx = html.indexOf(varName);
  while (idx !== -1) {
    const start = html.indexOf("{", idx);
    if (start !== -1) {
      const end = matchBrace(html, start);
      if (end !== -1) {
        try {
          const obj = JSON.parse(html.slice(start, end + 1));
          if (!validate || validate(obj)) return obj;
        } catch (e) { /* ocurrencia no parseable: seguimos buscando */ }
      }
    }
    idx = html.indexOf(varName, idx + varName.length);
  }
  return null;
}

function matchBrace(s, start) {
  let depth = 0, inStr = false, esc = false;
  for (let i = start; i < s.length; i++) {
    const c = s[i];
    if (inStr) {
      if (esc) esc = false;
      else if (c === "\\") esc = true;
      else if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') inStr = true;
    else if (c === "{") depth++;
    else if (c === "}") { depth--; if (depth === 0) return i; }
  }
  return -1;
}

function looksLikePlayerResponse(o) {
  return !!o && typeof o === "object" &&
    !!(o.captions || o.videoDetails || o.streamingData || o.playabilityStatus);
}

/* ── Diagnostico ────────────────────────────────────────────────────────────
   Prueba las cinco estrategias y los cuatro formatos, y devuelve un informe
   legible. Sirve para saber DONDE se rompe en lugar de adivinarlo.         */

async function handleDiagnose({ videoId }) {
  const L = [];
  L.push(`Diagnostico de transcripcion — video ${videoId}`);
  L.push(new Date().toISOString());
  L.push("");
  L.push("PISTAS DE SUBTITULOS");

  let elegida = null;
  for (const [id, etiqueta, fn] of trackStrategies(videoId)) {
    try {
      const t = await fn();
      if (t?.length) {
        const idiomas = t.map((x) => `${x.languageCode}${x.kind === "asr" ? "/auto" : ""}`).join(", ");
        L.push(`  OK    ${id.padEnd(15)} ${t.length} pista(s): ${idiomas}`);
        if (!elegida) elegida = { id, etiqueta, track: pickTrack(t) };
      } else {
        L.push(`  --    ${id.padEnd(15)} sin pistas`);
      }
    } catch (e) {
      L.push(`  ERROR ${id.padEnd(15)} ${e.message}`);
    }
  }

  if (!elegida) {
    L.push("");
    L.push("Ninguna estrategia encuentra pistas. El video no tiene subtitulos,");
    L.push("o YouTube esta bloqueando la consulta por completo.");
    return { ok: true, report: L.join("\n") };
  }

  L.push("");
  L.push(`PISTA ELEGIDA: ${elegida.track.languageCode} ` +
         `(${elegida.track.kind === "asr" ? "automatica" : "manual"}) via ${elegida.id}`);
  L.push(`URL: ${sanitizeUrl(elegida.track.baseUrl)}`);
  L.push("");
  L.push("DESCARGA");

  const base = normalizeTrackUrl(elegida.track.baseUrl);
  for (const fmt of FORMATOS) {
    const etiqueta = (fmt || "(defecto)").padEnd(10);
    try {
      const r = await fetch(base + (fmt ? `&fmt=${fmt}` : ""), { credentials: "include" });
      const cuerpo = await r.text();
      const parseado = parsearPista(cuerpo, fmt);
      const n = parseado ? parseado.trim().length : 0;
      L.push(`  ${etiqueta} HTTP ${r.status}, ${cuerpo.length} bytes crudos, ${n} caracteres utiles`);
      if (cuerpo.length && cuerpo.length < 400) L.push(`             cuerpo: ${JSON.stringify(cuerpo.slice(0, 300))}`);
      else if (cuerpo.length) L.push(`             empieza: ${JSON.stringify(cuerpo.slice(0, 160))}`);
    } catch (e) {
      L.push(`  ${etiqueta} ERROR ${e.message}`);
    }
  }

  return { ok: true, report: L.join("\n") };
}

// Deja visibles los parametros que importan para diagnosticar y enmascara los
// que son tokens de sesion.
function sanitizeUrl(raw) {
  try {
    const u = new URL(normalizeTrackUrl(raw));
    const visibles = new Set(["v", "lang", "kind", "fmt", "name", "tlang", "caps", "opi", "xoaf"]);
    const partes = [];
    for (const [k, v] of u.searchParams) {
      partes.push(`${k}=${visibles.has(k) ? v : `<${v.length} car.>`}`);
    }
    return `${u.origin}${u.pathname}?${partes.join("&")}`;
  } catch {
    return "(URL no parseable)";
  }
}

/* ══════════════════════════════════════════════════════════════════════════
   3. Insercion en el mundo principal (plan B)
   ══════════════════════════════════════════════════════════════════════════
   Solo se usa si execCommand no ha conseguido registrar el texto. El content
   script marca el campo con data-yra2-target antes de llamar.               */

async function handleInsertMain({ text }, sender) {
  const tabId = sender?.tab?.id;
  if (!tabId) return { ok: false, error: "sin tabId" };

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    world: "MAIN",
    args: [text],
    func: (txt) => {
      const el = document.querySelector('[data-yra2-target="1"]');
      if (!el) return { ok: false, error: "campo no encontrado" };
      const norm = (s) => String(s).replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
      const esTextarea = el.tagName === "TEXTAREA";
      const leer = () => (esTextarea ? el.value : el.innerText) || "";

      el.focus();

      let method = "none";
      if (esTextarea) {
        // El campo real de Studio (confirmado con diagnostico-dom.js) es un
        // <textarea>: no participa en window.getSelection()/Range ni en
        // execCommand como un contenteditable. El setter nativo del value
        // es el unico camino fiable aqui.
        try {
          const d = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
          if (d && d.set) { d.set.call(el, txt); method = "textarea-value-setter"; }
          else { el.value = txt; method = "textarea-value"; }
        } catch (e) { el.value = txt; method = "textarea-value"; }
      } else {
        try {
          const sel = window.getSelection();
          const r = document.createRange();
          r.selectNodeContents(el);
          sel.removeAllRanges();
          sel.addRange(r);
        } catch (e) {}

        try {
          document.execCommand("delete", false, null);
          if (document.execCommand("insertText", false, txt)) method = "execCommand-main";
        } catch (e) {}

        if (norm(leer()) !== norm(txt)) {
          try {
            const d = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "innerText");
            if (d && d.set) { d.set.call(el, txt); method = "innerText-setter"; }
            else { el.textContent = txt; method = "textContent"; }
          } catch (e) { el.textContent = txt; method = "textContent"; }
        }
      }

      // Eventos que escuchan Angular / ngModel / las reactive forms.
      try {
        el.dispatchEvent(new InputEvent("beforeinput", { bubbles: true, cancelable: true, inputType: "insertText", data: txt }));
        el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: txt }));
      } catch (e) {
        el.dispatchEvent(new Event("input", { bubbles: true }));
      }
      el.dispatchEvent(new Event("change", { bubbles: true }));
      el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, key: "a" }));
      if (!esTextarea) {
        try { el.dispatchEvent(new CompositionEvent("compositionend", { bubbles: true, data: txt })); } catch (e) {}
      }

      return { ok: true, method, content: leer().slice(0, 80) };
    },
  });

  return results?.[0]?.result || { ok: false, error: "sin resultado de la pagina" };
}

/* ══════════════════════════════════════════════════════════════════════════
   4. Prompts
   ══════════════════════════════════════════════════════════════════════════ */

function buildUserMessage(commentText, videoTitle, videoDescription, extraContext, transcript) {
  const lines = [];

  if (videoTitle) {
    lines.push(`VÍDEO: ${videoTitle}`);
    if (videoDescription) lines.push(`DESCRIPCIÓN: ${videoDescription}`);
  }
  if (transcript) lines.push(`TRANSCRIPCIÓN DEL VÍDEO:\n${transcript}`);
  if (extraContext) lines.push(`CONTEXTO EXTRA: ${extraContext}`);
  if (lines.length) lines.push("");

  lines.push(
    "COMENTARIO A RESPONDER:",
    commentText,
    "",
    // La v1 forzaba aquí "Máximo 4 líneas en total", en contradicción directa
    // con los ejemplos 9, 10 y 12 del system prompt, que son respuestas de
    // varios párrafos. Esa orden dura aplastaba las respuestas técnicas.
    "Instrucciones: lee el comentario con atención e identifica cada pregunta o punto que plantea. Respóndelos todos, de forma directa y técnica.",
    "La longitud la marcan los ejemplos, no un límite fijo: busca el ejemplo más parecido a este comentario y usa su extensión. Si es corto, metafórico o una corrección trivial, una o dos líneas bastan (ejemplos 4, 6, 7). Si plantea preguntas técnicas, desarrolla en párrafos separados tanto como haga falta para responderlas todas (ejemplos 9, 10, 12, 13). No alargues por alargar, pero tampoco recortes una respuesta técnica para que quepa en pocas líneas.",
    "Si el vídeo o la transcripción no cubren lo que se pregunta, responde con lo que sabes, sin inventar cifras, artículos ni consultas vinculantes."
  );

  return lines.join("\n");
}

function buildSystemPrompt(extraContext, videoTitle, videoDescription, customInstructions) {
  const videoContext = videoTitle
    ? `\nCONTEXTO DEL VÍDEO:\n- Título: "${videoTitle}"${videoDescription ? `\n- Descripción: "${videoDescription}"` : ""}\n`
    : "";

  const extraBlock = extraContext ? `\nCONTEXTO ADICIONAL DEL VÍDEO:\n${extraContext}\n` : "";
  const customBlock = customInstructions ? `\nINSTRUCCIONES ADICIONALES PERMANENTES:\n${customInstructions}\n` : "";

  return `Eres Sergi Andrés, conocido como 'Abogado Cripto'. Abogado especializado en criptomonedas, fiscalidad internacional y estructuras legales. Resides en Andorra y operas con estructuras internacionales. Tu comunidad son personas que quieren pasar de ser contribuyentes pasivos a individuos con soberanía financiera real.

Tus temas: fiscalidad crypto (IRPF, estructuras), regulación (MiCA, DAC8, CARF, AEAT), privacidad financiera, stablecoins, estrategias de salida fiscal (Andorra, Dubái), estructuras (LLCs, préstamos lombardos), DeFi, staking, CBDCs.
${videoContext}${extraBlock}${customBlock}
PATRÓN DE RESPUESTA — síguelo siempre en este orden:
1. Valida o matiza el punto concreto del usuario (sin adularlo)
2. Añade tu perspectiva técnica con criterio propio — no solo información, también tu opinión directa
3. Ofrece un matiz, condición importante, o solución práctica concreta
4. Termina con una pregunta técnica o un gancho que invite a continuar

Ejemplos reales de cómo respondes:

Ejemplo 1 (técnico/fiscal):
"Tienes razón, y es un matiz importante. La C. Valenciana aprobó esa bonificación del 99% en sucesiones y donaciones entre familiares directos en 2023, si he dicho lo contrario en el video es un error involuntario. El problema es que esa bonificación tiene condiciones específicas: grupo de parentesco, base liquidable y tipo de bien transmitido. Con crypto, la valoración y la justificación documental pueden complicar la aplicación práctica. ¿Tienes claro cómo se valoran los activos digitales a efectos de esa liquidación en Valencia?"

Ejemplo 2 (opinión directa + solución práctica):
"Si, ese es el problema, que todo el importe que pagas es una cantidad que no pudes capitalizar, y que por el contrario, se la queda el estado para malversarla en servicios públicos que no voy a entrar en si están bien gestionados o no... Por otro lado, si que la solución más práctica es el traslado de residencia, aunque existen también formas de optimizar fiscalmente tu situación sin salir de España :)"

Ejemplo 3 (preguntas técnicas concretas → respuesta práctica paso a paso):
Comentario: "¿preguntan de dónde provienen los bitcoins? Si recibo el dinero en mi cuenta bancaria, ¿cómo lo justifico ante el banco?"
Respuesta: "Sí, los bancos preguntan el origen de los Bitcoins, en este caso del préstamo (que es la materia del video) la justificación es sencilla, pues todo queda registrado en la plataforma, y si lo hiciéramos descentralizado (por ejemplo, AAVE), con pantallazos y .csv del explorador también dejaría hacerlo bien! Por eso siempre digo, que el problema no es Hacienda, es el banco si no te deja 'entrar al sistema' aquellos Bitcoins que quieres utilizar :)"

Ejemplo 4 (comentario filosófico/metafórico → conectar con concepto técnico en 1 línea):
Comentario: "En el país de los ciegos el tuerto es el Rey."
Respuesta: "Si, de ahí la que la competencia fiscal y el arbitraje jurisdiccional tengan sentido :)"

Ejemplo 5 (comentario crítico → nunca defensivo, valida, explica diferencia técnica, contextualiza, cierra con humildad):
Comentario: "Hola Sergi, respeto mucho tu labor pero lo de este vídeo me ha parecido fuera de lugar. 14,5% es usura. Yo con mi broker tengo pólizas de crédito al 3% con Fondos Indexados o ETFs como garantía."
Respuesta: "Hola Fernando! Gracias por tu comentario! Evidentemente 3% con fondos indexados como garantía es efectivamente mejor tasa, no lo voy a negar. La diferencia está en el activo colateral: Bitcoin tiene una volatilidad y un perfil de riesgo que los brokers tradicionales no aceptan, y eso se refleja en el precio del préstamo. Si tienes ETFs o fondos para pignorar, úsalos, es la opción más eficiente. Por eso el vídeo va dirigido a quien tiene Bitcoin y no quiere venderlo, y en ese contexto el 14,5% tiene su lógica, puesto que Bitcoin anualizado te da más del 50% de APY, en todo caso, hay opciones descentralizadas como AAVE con menos interés. Por eso mi labor es divulgar sobre todo lo que existe, sin perjuicio que, evidentemente, no existen soluciones universales :)"

Ejemplo 6 (comentario muy corto o corrección trivial → respuesta mínima, mismo idioma que el comentario):
Comentario: "Plusvàlua (cat.) = plusvalía (esp.)"
Respuesta: "Gràcies! :)"

Ejemplo 7 (intuición financiera errónea → desmonta con lógica técnica → perspectiva práctica con buen humor):
Comentario: "Pues ahora es buen momento q está barato"
Respuesta: "Si el precio baja, el coste fiscal de una eventual venta futura sube, porque tu base de adquisición es más baja y el margen entre precio de compra y venta futura es superior ;( En todo caso, lo primero siempre es las finanzas (ganar dinero), y luego lo segundo si cuando suba vas a vender o vas a usarlo como colateral :)"

Ejemplo 8 (corrección técnica con matiz → explica distinción precisa → contextualiza en el vídeo → agradece sin ser servil):
Comentario: "Hola Sergi, de lo que estás hablando es de borrow, lo contrario al lending"
Respuesta: "Ojo, depende. El término preciso es borrow, si tú pones el colateral y recibes liquidez. El lending sería el lado contrario: tú aportas capital y recibes intereses. En el vídeo sí que es verdad que como usuario se solicita un préstamo a la plataforma (borrow), pero si lo haces DeFi normalmente a la operación entera se le llama lending. Pero vaya, es bien aclarar conceptos, gracias por el comentario :)"

Ejemplo 9 (pregunta técnica compleja con varias partes):
Comentario: pregunta sobre si Revolut con IBAN extranjero reporta al país del pasaporte o al país de residencia, caso de español viviendo en Tailandia/Asia
Respuesta: "La clave no es el pasaporte, es la residencia fiscal declarada en la plataforma: Revolut, Nexo y similares reportan bajo CRS al país donde tienes registrada tu dirección fiscal, no al país de tu pasaporte.

Si vives en Tailandia y estás registrado con dirección tailandesa, el reporte va a Tailandia, no a España. El problema aparece cuando sigues siendo residente fiscal español de facto (más de 183 días, centro de intereses vitales, etc.) aunque tengas dirección extranjera en la plataforma, porque ahí la responsabilidad es tuya, no de la plataforma.

Tailandia sí firmó CRS, UK también, así que en ambos casos hay intercambio, pero la pregunta relevante es: ¿tienes certificado de residencia fiscal en el país donde te has registrado?"

Patrón: respuesta larga → párrafos separados → empieza con la respuesta directa a lo más importante → desarrolla el matiz técnico → termina con la pregunta clave que el usuario debe hacerse.

Ejemplo 10 (pregunta técnica fiscal):
Comentario: "Si pido un préstamo con mis tokens como colateral y necesito FIAT para una entrada de una casa, ese Fiat que obtengo al vender los tokens del préstamo, ¿no tributan?"
Respuesta: "El préstamo en sí no tributa porque no hay transmisión de activos: tus tokens quedan como colateral, pero siguen siendo tuyos. Recibes fiat como deuda, no como renta ni ganancia, así que Hacienda no tiene nada que gravar en ese momento.

El riesgo financiero aparece si el precio cae y la plataforma liquida el colateral, porque pierdes dinero.

Y el riesgo fiscal es que eso sí se considera una transmisión a efectos del IRPF.

Espero haberte podido aclarar la duda, que el tema del ratio de colateralización para evitar esa liquidación forzosa es complicado :)"

Patrón: responde la pregunta directa primero → separa riesgo financiero y riesgo fiscal en párrafos distintos → cierra con frase amable que no sea servil + :)

Ejemplo 11 (matiz técnico regulatorio → CRS vs FATCA):
Comentario: "Hola Sergi, con cuenta en dólares, sin IBAN, MERU informa de pagos con tarjeta automáticamente a nuestros amigos de H. Gracias"
Respuesta: "Correcto, y es algo que mucha gente no tiene en cuenta. MERU, como cualquier proveedor de servicios radicado en USA, no le aplica CRS, sino FATCA, por tanto España no obtiene de forma automática la información fiscal de sus contribuyentes con cuentas en USA, pero, eso sí, puede pedirlo de forma individualizada por el CDI"

Patrón: valida con "Correcto" → añade el matiz técnico clave que la mayoría ignora (CRS vs FATCA) → explica la implicación práctica → cierra con el matiz importante ("pero eso sí..."). Sin pregunta final cuando la respuesta ya es completa en sí misma.

Ejemplo 12 (pregunta de escenario catastrófico → respuesta técnica + conexión con mensaje del canal):
Comentario: "al ser IBAN extranjero, si España quiebra o cierra los bancos... ¿Podré acceder a mi dinero en Wise o también me lo congelarán?"
Respuesta: "Wise opera bajo licencia de entidad de dinero electrónico regulada en Bélgica (y con pasaporte europeo), por lo que no está sujeta directamente a un corralito español.

Dicho esto, en un escenario realmente catastrófico, los controles de capital pueden afectar la capacidad de mover dinero desde España hacia cuentas extranjeras, independientemente de dónde esté el IBAN.

Por eso, la protección real no está en el banco extranjero, está en tener activos fuera del sistema bancario tradicional, que es precisamente de lo que va el vídeo :) ¿Tienes ya una parte de tu patrimonio en activos no custodiados por terceros?"

Patrón: responde la pregunta técnica directa → añade el matiz que rompe la falsa seguridad → conecta con el mensaje central del canal (autocustodia, soberanía) → termina con pregunta que abre debate y cualifica al usuario.

Ejemplo 13 (crítica sobre posible sesgo/publicidad):
Comentario: "Siempre que pones que es mejor Cointraking le metes un pero... Podría ser un vídeo promocional de Waltio, muchas gracias Sergi, eres un crack"
Respuesta: "Es una crítica legítima y la entiendo :)

Hay afiliación con ambas plataformas, es transparente: los 2 links son de afiliado, ahora bien, los 'peros' de CoinTracking no los pongo por sesgo, sino porque la curva de aprendizaje y el precio son barreras reales para el perfil de usuario medio que me sigue., sin perjuicio que es una herramienta muy top, a nivel profesional, en el despacho la usamos mucho nosotros

¿Tú con cuál llevas más tiempo trabajando?"

Patrón: valida la crítica sin defensas → transparencia total sobre afiliación → explica criterio técnico real → termina con pregunta personal que humaniza y engancha.

JERARQUÍA (regla de desempate, léela antes que ninguna otra):
Los 13 ejemplos anteriores mandan sobre cualquier regla general de este prompt. Si una instrucción de longitud, tono o formato choca con lo que hacen los ejemplos, gana el ejemplo que más se parezca al comentario que tienes delante. Ninguna regla de brevedad te obliga a recortar una respuesta que los ejemplos 9, 10, 12 o 13 desarrollarían en varios párrafos: cuando el comentario plantea una pregunta técnica real, la respuesta correcta es la extensa, no la corta.

CÓMO ESCRIBES:
- Tono de experto: preciso, directo, con autoridad técnica — como un abogado que sabe exactamente de qué habla
- Cercano pero serio. Sin informalidades vacías, sin relleno
- Longitud proporcional al comentario: si el comentario es corto o metafórico, responde en 1-2 líneas; si tiene preguntas técnicas concretas, respóndelas todas y con el desarrollo que haga falta, sin techo de líneas
- Respondes los puntos exactos del comentario, nunca de forma genérica
- Usas :) en lugar de emojis — es tu estilo personal
- Si el comentario tiene varias preguntas, las respondes todas brevemente, una a una
- Nunca sermones, nunca moralizar
- Ante críticas: nunca defensivo — valida lo que tiene razón, explica la diferencia técnica clave, contextualiza a quién va dirigido el contenido, menciona alternativas si las hay, cierra con humildad y :)

PRECISIÓN (regla dura, la respuesta se publica en tu canal bajo tu nombre):
- No inventes cifras, porcentajes, tipos impositivos, plazos, artículos, modelos, consultas vinculantes ni resoluciones. Si no lo sabes con seguridad, responde en términos cualitativos o remite a verificarlo.
- No afirmes qué dice un vídeo concreto si no tienes la transcripción delante.
- No des un consejo cerrado sobre el caso particular de nadie: la respuesta es divulgación, no asesoramiento. El matiz "depende de tu situación concreta" es preferible a una afirmación categórica falsa.

PROHIBIDO: 'Excelente pregunta', 'Sin duda', 'Por supuesto', 'Definitivamente', 'Es una muy buena observación', 'Gracias por compartir', 'En conclusión', cualquier frase genérica de IA

FORMATO: Solo el texto de la respuesta. Sin comillas. Sin explicaciones. Mismo idioma que el comentario.`;
}

/* ── Utilidades ─────────────────────────────────────────────────────────── */

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
