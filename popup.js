(() => {
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
    likeOnPublish: true,
    debug: true,
  };

  const $ = (id) => document.getElementById(id);

  const el = {
    apiKey: $("apiKey"),
    toggleKey: $("toggleKey"),
    model: $("model"),
    extendedThinking: $("extendedThinking"),
    countdown: $("countdown"),
    secsRow: $("secsRow"),
    requireTranscript: $("requireTranscript"),
    likeOnPublish: $("likeOnPublish"),
    extraContext: $("extraContext"),
    customInstructions: $("customInstructions"),
    testBtn: $("testBtn"),
    saveBtn: $("saveBtn"),
    status: $("status"),
    diagVideo: $("diagVideo"),
    diagBtn: $("diagBtn"),
    diagReport: $("diagReport"),
    diagCopy: $("diagCopy"),
  };

  const modeInputs = [...document.querySelectorAll('input[name="mode"]')];

  /* ── Carga ──────────────────────────────────────────────────────────────── */

  chrome.storage.local.get(DEFAULTS, (cfg) => {
    el.apiKey.value = cfg.apiKey || "";
    el.model.value = cfg.model || DEFAULTS.model;
    if (!el.model.value) el.model.value = DEFAULTS.model;
    el.extendedThinking.checked = !!cfg.extendedThinking;
    el.requireTranscript.checked = !!cfg.requireTranscript;
    el.likeOnPublish.checked = cfg.likeOnPublish !== false;
    el.extraContext.value = cfg.extraContext || "";
    el.customInstructions.value = cfg.customInstructions || "";
    el.countdown.value = Number(cfg.countdown) > 0 ? Number(cfg.countdown) : 4;

    const choice = cfg.mode !== "auto" ? "review" : Number(cfg.countdown) > 0 ? "window" : "instant";
    modeInputs.find((i) => i.value === choice).checked = true;
    paintModes();
  });

  /* ── Interaccion ────────────────────────────────────────────────────────── */

  el.toggleKey.addEventListener("click", () => {
    const hidden = el.apiKey.type === "password";
    el.apiKey.type = hidden ? "text" : "password";
    el.toggleKey.textContent = hidden ? "ocultar" : "ver";
  });

  modeInputs.forEach((i) => i.addEventListener("change", paintModes));

  function paintModes() {
    const chosen = modeInputs.find((i) => i.checked)?.value || "window";
    document.querySelectorAll(".mode").forEach((m) => {
      m.dataset.on = m.dataset.mode === chosen ? "1" : "0";
    });
    el.secsRow.dataset.show = chosen === "window" ? "1" : "0";
  }

  function collect() {
    const chosen = modeInputs.find((i) => i.checked)?.value || "window";
    let mode = "auto";
    let countdown = 0;
    if (chosen === "review") mode = "review";
    if (chosen === "window") countdown = clamp(Number(el.countdown.value) || 4, 2, 30);

    return {
      apiKey: el.apiKey.value.trim(),
      model: el.model.value,
      extendedThinking: el.extendedThinking.checked,
      extraContext: el.extraContext.value.trim(),
      customInstructions: el.customInstructions.value.trim(),
      mode,
      countdown,
      requireTranscript: el.requireTranscript.checked,
      likeOnPublish: el.likeOnPublish.checked,
      debug: true,
    };
  }

  el.saveBtn.addEventListener("click", () => {
    const cfg = collect();
    if (!cfg.apiKey) return say("Falta la API key.", "err");
    if (!cfg.apiKey.startsWith("sk-ant-")) return say("La API key debe empezar por sk-ant-.", "err");

    chrome.storage.local.set(cfg, () => {
      if (chrome.runtime.lastError) say(`No se ha podido guardar: ${chrome.runtime.lastError.message}`, "err");
      else {
        el.countdown.value = cfg.countdown || 4;
        say(describe(cfg), "ok");
      }
    });
  });

  el.testBtn.addEventListener("click", () => {
    const cfg = collect();
    if (!cfg.apiKey) return say("Introduce la API key antes de probar.", "err");

    el.testBtn.disabled = true;
    say("Probando…", "busy");

    // Guardamos primero para que el background use estos valores exactos.
    chrome.storage.local.set(cfg, () => {
      chrome.runtime.sendMessage({ type: "TEST_API" }, (res) => {
        el.testBtn.disabled = false;
        if (chrome.runtime.lastError) return say(chrome.runtime.lastError.message, "err");
        if (res?.ok) say(`Conexion correcta con ${res.model}.`, "ok");
        else say(res?.error || "No se ha podido conectar.", "err");
      });
    });
  });

  el.apiKey.addEventListener("keydown", (e) => {
    if (e.key === "Enter") el.saveBtn.click();
  });

  /* ── Diagnostico de transcripcion ───────────────────────────────────────── */

  // Prerrellena el ID si la pestaña activa de Studio ya lo lleva en la URL.
  chrome.tabs?.query({ active: true, currentWindow: true }, (tabs) => {
    const m = tabs?.[0]?.url?.match(/\/video\/([A-Za-z0-9_-]{11})/);
    if (m) el.diagVideo.value = m[1];
  });

  el.diagBtn.addEventListener("click", () => {
    const videoId = parseVideoId(el.diagVideo.value);
    if (!videoId) {
      return showReport("Introduce un ID de 11 caracteres o una URL de YouTube.\n\n" +
        "Lo tienes en el enlace de la miniatura de cualquier comentario:\n" +
        "  studio.youtube.com/video/AQUI_VAN_LOS_11/comments");
    }
    el.diagBtn.disabled = true;
    showReport("Ejecutando las cinco estrategias…");
    chrome.runtime.sendMessage({ type: "DIAGNOSE", payload: { videoId } }, (res) => {
      el.diagBtn.disabled = false;
      if (chrome.runtime.lastError) return showReport("Error: " + chrome.runtime.lastError.message);
      showReport(res?.report || res?.error || "Sin informe.");
    });
  });

  el.diagCopy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(el.diagReport.textContent);
      el.diagCopy.textContent = "Copiado";
    } catch {
      el.diagCopy.textContent = "No se ha podido copiar";
    }
    setTimeout(() => { el.diagCopy.textContent = "Copiar informe"; }, 2000);
  });

  function showReport(texto) {
    el.diagReport.textContent = texto;
    el.diagReport.dataset.show = "1";
    el.diagCopy.style.display = "block";
  }

  // Acepta el ID pelado o cualquier URL de YouTube o de Studio.
  function parseVideoId(raw) {
    const v = String(raw || "").trim();
    if (/^[A-Za-z0-9_-]{11}$/.test(v)) return v;
    const m = v.match(/(?:[?&]v=|\/video\/|\/shorts\/|\/live\/|youtu\.be\/|\/vi\/)([A-Za-z0-9_-]{11})/);
    return m ? m[1] : null;
  }

  /* ── Utilidades ─────────────────────────────────────────────────────────── */

  function describe(cfg) {
    if (cfg.mode === "review") return "Guardado. El boton abrira el panel para que revises antes de publicar.";
    if (cfg.countdown > 0) return `Guardado. El boton publicara solo, con ${cfg.countdown} segundos para cancelar.`;
    return "Guardado. El boton publicara al instante, sin margen para cancelar.";
  }

  function say(message, kind) {
    el.status.textContent = message;
    el.status.dataset.kind = kind;
    if (kind !== "busy") setTimeout(() => { el.status.dataset.kind = ""; }, 6000);
  }

  function clamp(n, lo, hi) {
    return Math.min(hi, Math.max(lo, n));
  }
})();
