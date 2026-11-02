/* ============================================================================
   YouTube Reply Assistant — botón «💡 Guardar idea» en youtube.com (v2.9.0)
   ----------------------------------------------------------------------------
   Sergi (02/11/2026): guardar outliers e ideas sin salir de YouTube y que
   aparezcan a la izquierda de su pizarra (calendario de vídeos del motor).

   - En la PÁGINA DE UN VÍDEO (/watch y /shorts): botón flotante abajo a la
     derecha. Pide un comentario opcional (Cancelar = no se guarda).
   - En CADA VÍDEO de la portada, la búsqueda, los sugeridos y la página de un
     canal: botón pequeño sobre la miniatura (se ve al pasar el ratón). Guarda
     al momento, sin abrir el vídeo.
   - Si vidIQ ha pintado en la tarjeta el multiplicador («>100x», «1.6x») y el
     VPH («36.3K VPH»), se mandan también; si no, se guarda igual.
   - YouTube recicla las tarjetas al hacer scroll: el enlace se lee en el
     momento del clic, nunca el que había al poner el botón.
   El background lo manda al motor ({yt:'idea'}) → pestaña IDEAS (sin duplicar).
   ========================================================================== */

(() => {
  "use strict";
  if (window.__YRA2_IDEAS__) return;
  window.__YRA2_IDEAS__ = true;

  const TARJETAS = [
    "ytd-rich-item-renderer", "ytd-video-renderer", "ytd-compact-video-renderer", "ytd-grid-video-renderer",
    "ytd-reel-item-renderer", "ytm-shorts-lockup-view-model", "yt-lockup-view-model",
  ].join(",");
  const MARCA = "data-yra2-idea";

  const css = document.createElement("style");
  css.textContent = `
    .yra2-idea-btn{position:absolute;top:6px;left:6px;z-index:50;font:600 12px/1 Roboto,Arial,sans-serif;
      padding:6px 8px;border-radius:8px;border:0;background:rgba(15,15,15,.82);color:#fff;cursor:pointer;
      opacity:.88;transition:opacity .15s,transform .15s}
    ${TARJETAS.split(",").map(t => t + ":hover .yra2-idea-btn").join(",")}{opacity:1;transform:scale(1.05)}
    .yra2-idea-btn.ok,.yra2-idea-btn.trabajando{opacity:1}
    .yra2-idea-btn.ok{background:#1b7f4b}
    .yra2-idea-btn.error{opacity:1;background:#c62828}
    .yra2-idea-flot{position:fixed;right:22px;bottom:22px;z-index:9999;font:600 14px/1 Roboto,Arial,sans-serif;
      padding:12px 16px;border-radius:999px;border:0;background:#F5A524;color:#162040;cursor:pointer;
      box-shadow:0 4px 14px rgba(0,0,0,.3)}
    .yra2-idea-flot.ok{background:#1b7f4b;color:#fff}
    .yra2-idea-flot.error{background:#c62828;color:#fff}`;
  document.documentElement.appendChild(css);

  function enlaceDe(tarjeta) {
    const a = tarjeta.querySelector('a#thumbnail[href], a[href*="/watch?v="], a[href*="/shorts/"]');
    if (!a) return "";
    try { return new URL(a.getAttribute("href"), location.origin).href; } catch { return ""; }
  }

  // Etiquetas de vidIQ en la tarjeta (si están): «>100x», «1.6x» y «36.3K VPH».
  function vidiqDe(tarjeta) {
    const t = (tarjeta.innerText || "").replace(/ /g, " ");
    const vph = (t.match(/(\d[\d.,]*\s*[KkMm]?)\s*VPH/) || [])[1] || "";
    const mult = (t.match(/(?:^|\s)(>?\s?\d+(?:[.,]\d+)?x)(?=\s|$)/m) || [])[1] || "";
    return { vph: vph.replace(/\s+/g, ""), multiplicador: mult.replace(/\s+/g, "") };
  }

  function guardar(datos) {
    return new Promise(resolve => {
      try {
        chrome.runtime.sendMessage({ type: "GUARDAR_IDEA", payload: datos }, r => {
          if (chrome.runtime.lastError) resolve({ ok: false, error: chrome.runtime.lastError.message });
          else resolve(r || { ok: false, error: "sin respuesta" });
        });
      } catch (e) { resolve({ ok: false, error: e.message }); }
    });
  }

  async function pulsar(btn, datos, textoBase) {
    if (btn.classList.contains("trabajando")) return;
    btn.classList.remove("ok", "error");
    btn.classList.add("trabajando");
    btn.textContent = "Guardando…";
    const r = await guardar(datos);
    btn.classList.remove("trabajando");
    if (r.ok) {
      btn.classList.add("ok");
      btn.textContent = r.duplicada ? "✓ Ya estaba" : "✓ Guardado";
      btn.title = r.titulo || "";
    } else {
      btn.classList.add("error");
      btn.textContent = "⚠️ No guardado";
      btn.title = r.error || "";
      setTimeout(() => { btn.classList.remove("error"); btn.textContent = textoBase; }, 5000);
    }
  }

  // Botón en cada tarjeta de vídeo
  function ponerBotones() {
    document.querySelectorAll(TARJETAS).forEach(tarjeta => {
      const url = enlaceDe(tarjeta);
      let btn = tarjeta.querySelector(":scope .yra2-idea-btn");
      if (!url) { if (btn) btn.remove(); return; }
      if (btn) {
        if (btn.getAttribute(MARCA) !== url) {                 // tarjeta reciclada: botón limpio para el vídeo nuevo
          btn.setAttribute(MARCA, url);
          btn.classList.remove("ok", "error", "trabajando");
          btn.textContent = "💡 Guardar idea";
        }
        return;
      }
      const host = tarjeta.querySelector("#thumbnail, a#thumbnail, yt-thumbnail-view-model, .shortsLockupViewModelHostThumbnailContainer") || tarjeta;
      if (getComputedStyle(host).position === "static") host.style.position = "relative";
      btn = document.createElement("button");
      btn.className = "yra2-idea-btn";
      btn.type = "button";
      btn.textContent = "💡 Guardar idea";
      btn.setAttribute(MARCA, url);
      btn.addEventListener("click", ev => {
        ev.preventDefault(); ev.stopPropagation();
        const ahora = enlaceDe(tarjeta);                       // el enlace de AHORA, no el de cuando se puso el botón
        if (!ahora) return;
        const titulo = (tarjeta.querySelector("#video-title, h3, a#video-title-link") || {}).textContent || "";
        pulsar(btn, { url: ahora, titulo: titulo.trim(), ...vidiqDe(tarjeta) }, "💡 Guardar idea");
      }, true);
      host.appendChild(btn);
    });
  }

  // Botón flotante en la página de un vídeo
  function botonFlotante() {
    const enVideo = /^\/(watch|shorts\/)/.test(location.pathname);
    let f = document.querySelector(".yra2-idea-flot");
    if (!enVideo) { if (f) f.remove(); return; }
    if (!f) {
      f = document.createElement("button");
      f.className = "yra2-idea-flot";
      f.type = "button";
      f.addEventListener("click", () => {
        const comentario = window.prompt("💡 Guardar este vídeo como idea.\nComentario (opcional): por qué es buena idea, ángulo…", "");
        if (comentario === null) return;
        const titulo = (document.querySelector("h1.ytd-watch-metadata, ytd-watch-metadata h1, h2.title") || {}).textContent || document.title;
        pulsar(f, { url: location.href, titulo: titulo.trim(), comentario }, "💡 Guardar idea");
      });
      document.body.appendChild(f);
    }
    if (f.getAttribute(MARCA) !== location.href) {               // vídeo nuevo (YouTube no recarga la página)
      f.setAttribute(MARCA, location.href);
      f.classList.remove("ok", "error", "trabajando");
      f.textContent = "💡 Guardar idea";
    }
  }

  let pendiente = false;
  function repasar() {
    if (pendiente) return;
    pendiente = true;
    setTimeout(() => { pendiente = false; ponerBotones(); botonFlotante(); }, 400);
  }
  new MutationObserver(repasar).observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("yt-navigate-finish", repasar);
  repasar();
  // Versión nueva copiada en la carpeta de la extensión: también se recarga desde youtube.com (no solo desde Studio).
  try { chrome.runtime.sendMessage({ type: "COMPROBAR_VERSION" }, () => void chrome.runtime.lastError); } catch { /* nada */ }
})();
