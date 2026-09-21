/* ============================================================================
   YouTube Reply Assistant v2 — content script
   ----------------------------------------------------------------------------
   Diferencias clave frente a la v1:

   1. ARRANQUE AUTOMATICO. El manifest inyecta este script en TODO
      studio.youtube.com. La activacion/desactivacion se decide aqui dentro
      vigilando location.href con un sondeo de 400 ms. No depende de parchear
      history.pushState (que en la v1 nunca funcionaba: el parche vivia en el
      mundo aislado del content script y la pagina llama al pushState del
      mundo principal).

   2. UN SOLO CLIC. generar -> abrir caja -> insertar -> VERIFICAR -> enviar.

   3. NUNCA PUBLICA A CIEGAS. Cada paso se verifica antes de pasar al
      siguiente. Si cualquier verificacion falla, el flujo ABORTA y deja el
      texto disponible (panel + portapapeles). Nunca publica vacio, nunca
      publica en la fila equivocada, nunca publica a medias.
   ========================================================================== */

(() => {
  "use strict";

  if (window.__YRA2_LOADED__) return;
  window.__YRA2_LOADED__ = true;

  /* ── Constantes ─────────────────────────────────────────────────────────── */

  const BTN_CLASS = "yra2-btn";
  const MARK = "data-yra2";
  const LABEL_IDLE = "✨ Responder con IA";

  const DEFAULTS = {
    apiKey: "",
    model: "claude-sonnet-4-6",
    extendedThinking: true,
    extraContext: "",
    customInstructions: "",
    mode: "auto", // "auto" = publica sola | "review" = siempre revisar
    countdown: 4, // segundos de ventana de escape; 0 = publica al instante
    requireTranscript: true, // sin transcripcion -> no publica sola
    likeOnPublish: true, // dar "me gusta" al comentario tras publicar la respuesta
    debug: true,
  };

  const log = (...a) => {
    if (state.cfg?.debug !== false) console.log("%c[YRA2]", "color:#1a5fd8;font-weight:700", ...a);
  };
  const warn = (...a) => console.warn("[YRA2]", ...a);

  /* ── Estado global ──────────────────────────────────────────────────────── */

  const state = {
    active: false,
    busy: false, // cerrojo: un solo flujo simultaneo
    cfg: { ...DEFAULTS },
    observer: null,
    scanTimer: null,
    routeTimer: null,
    processed: new WeakSet(),
    abort: null, // funcion para cancelar la cuenta atras en curso
  };

  /* ── Selectores de YouTube Studio ───────────────────────────────────────── */

  // Contenedores de hilo, de mas a menos especifico. Se usan para acotar la
  // busqueda del campo de respuesta y del boton de enviar a la fila correcta.
  const THREAD_TAGS = [
    "ytcp-comment-thread",
    "ytcp-comment",
    "ytcp-comment-item",
    "ytcp-comment-info",
    "ytcp-comment-snippet",
  ];

  const COMMENT_SELECTORS = [
    "ytcp-comment-thread",
    "ytcp-comment-info",
    "ytcp-comment-snippet",
    "ytcp-comment-item",
    ".ytcp-comment-item",
    "[class*='comment-item']",
    ".comment-card",
  ];

  const TEXT_SELECTORS = [
    "#content-text",
    "[id='content-text']",
    "yt-attributed-string#content-text",
    "yt-attributed-string",
    ".comment-text",
    "#comment-text",
    "[id='comment-text']",
    "yt-formatted-string.comment-text",
    "[class*='content-text']",
    "[class*='comment-text']",
    ".snippet-text",
    "ytcp-mention-text",
  ];

  const ACTION_SELECTORS = [
    ".comment-actions",
    ".action-buttons",
    "[class*='comment-actions']",
    "[class*='action-buttons']",
    ".reply-button-container",
    ".comment-item-footer",
  ];

  const ROW_VIDEO_TITLE_SELECTORS = [
    ".video-title",
    "[class*='video-title']",
    "ytcp-video-info .title",
    ".comment-video-title",
    "[class*='video-snippet'] .title",
    "a[href*='/video/'] span",
  ];

  const PAGE_DESCRIPTION_SELECTORS = [
    "ytcp-video-info .description",
    "#description",
    ".video-description",
  ];

  // El campo de respuesta real de Studio (confirmado con diagnostico-dom.js
  // contra el DOM real, no deducido) es un <textarea> normal dentro de
  // ytcp-commentbox, NO un contenteditable. Se mantienen los selectores de
  // contenteditable por si Studio varia el editor segun el tipo de dialogo,
  // pero el caso real y verificado es el ultimo de la lista.
  const FIELD_SELECTOR = [
    "div#contenteditable-root",
    "ytcp-mentionable-textarea [contenteditable='true']",
    "ytcp-form-textarea [contenteditable='true']",
    "div[contenteditable='true']",
    "ytcp-commentbox textarea",
  ].join(", ");

  const OPEN_TEXTS = ["responder", "reply", "respondre"];
  const SUBMIT_TEXTS = ["responder", "reply", "comentar", "comment", "publicar", "respondre"];
  const CANCEL_TEXTS = ["cancelar", "cancel", "cancel·lar"];

  /* ==========================================================================
     1. VIGILANCIA DE RUTA  —  el arranque automatico
     ========================================================================== */

  function isCommentsRoute() {
    return /\/comments?(\/|$|\?|#)/.test(location.pathname + location.search);
  }

  function watchRoute() {
    let last = "";
    const check = () => {
      const href = location.href;
      if (href === last) return;
      last = href;
      const should = isCommentsRoute();
      if (should && !state.active) {
        activate();
      } else if (!should && state.active) {
        if (state.busy) {
          // Publicando ahora mismo: si esto es un cambio de ruta interno de
          // Studio (por ejemplo al abrir un dialogo) y no un abandono real
          // de la pagina, desactivar aqui borraria el panel o la cuenta
          // atras en pleno vuelo (hipotesis H3 del traspaso). Se aplaza.
          state.pendingDeactivate = true;
          warn("Cambio de ruta durante una publicacion; se aplaza la desactivacion.");
        } else {
          deactivate();
        }
      }
    };
    check();
    state.routeTimer = setInterval(check, 400);
    // Señales complementarias (no imprescindibles, pero aceleran la reaccion)
    window.addEventListener("popstate", check);
    window.addEventListener("hashchange", check);
    window.addEventListener("yt-navigate-finish", check);
  }

  async function activate() {
    state.active = true;
    state.cfg = await getSettings();
    log("Activado en", location.pathname);

    state.observer = new MutationObserver(() => {
      clearTimeout(state.scanTimer);
      state.scanTimer = setTimeout(scan, 300);
    });
    state.observer.observe(document.body, { childList: true, subtree: true });

    scan();
    // Red de seguridad mientras Studio carga en diferido. A diferencia de la
    // v1 no se apaga a los 2 minutos: el scroll infinito de comentarios sigue
    // trayendo filas nuevas mucho despues.
    state.scanTimer2 = setInterval(() => { if (state.active) scan(); }, 2500);
  }

  function releaseBusy() {
    state.busy = false;
    if (state.pendingDeactivate) {
      state.pendingDeactivate = false;
      deactivate();
    }
  }

  function deactivate() {
    state.active = false;
    log("Desactivado");
    // Si habia una cuenta atras en marcha, su promesa nunca resolveria y el
    // cerrojo state.busy quedaria bloqueado hasta recargar la pestaña.
    state.abort?.();
    state.observer?.disconnect();
    state.observer = null;
    clearTimeout(state.scanTimer);
    clearInterval(state.scanTimer2);
    document.querySelectorAll(`.${BTN_CLASS}, .yra2-panel, .yra2-toast, .yra2-countdown`).forEach((e) => e.remove());
    state.processed = new WeakSet();
  }

  /* ==========================================================================
     2. ESCANEO E INYECCION DEL BOTON
     ========================================================================== */

  function scan() {
    if (!state.active) return;

    // Campos de respuesta abiertos ahora mismo. Una fila que tenga uno abierto
    // se salta: su boton "Responder" visible es el de ENVIAR, no el de abrir,
    // y colgarle nuestro boton al lado seria un error.
    const openFields = visibleFields();

    // Via principal: anclar en el boton nativo "Responder" de cada fila. Es el
    // ancla mas estable porque siempre existe y siempre esta en la barra de
    // acciones correcta.
    document.querySelectorAll("ytcp-button, button, tp-yt-paper-button").forEach((b) => {
      if (state.processed.has(b)) return;
      if (b.classList.contains(BTN_CLASS)) return;
      if (b.id === "submit-button") return;
      const t = txt(b).toLowerCase();
      const al = (b.getAttribute("aria-label") || "").trim().toLowerCase();
      if (!OPEN_TEXTS.includes(t) && !OPEN_TEXTS.includes(al)) return;
      if (!isVisible(b)) return;
      if (b.closest("div[contenteditable='true']")) return;

      const row = findThreadRoot(b);
      if (!row) return;
      if (openFields.some((f) => row.contains(f))) return; // caja abierta: reintentar luego
      if (row.querySelector(`.${BTN_CLASS}`)) { state.processed.add(b); return; }

      // Solo damos el nodo por resuelto cuando hemos podido decidir de verdad.
      // Marcarlo antes hacia que una fila aun cargando se quedara sin boton
      // para siempre.
      const text = extractCommentText(row);
      if (!text) return;

      const bar = b.parentElement;
      if (!bar) return;
      state.processed.add(b);
      injectButton(bar, row, b);
    });

    // Via secundaria: contenedores conocidos que aun no tengan boton.
    // La deduplicacion se hace SIEMPRE contra el hilo completo, nunca contra
    // el nodo: ytcp-comment-info y ytcp-comment-thread son el mismo comentario,
    // y la barra de acciones donde va el boton cuelga de la segunda, asi que
    // mirar solo dentro de la primera producia un boton duplicado por fila.
    for (const sel of COMMENT_SELECTORS) {
      document.querySelectorAll(sel).forEach((node) => {
        if (state.processed.has(node)) return;
        if (node.closest("div[contenteditable='true']")) return;

        const row = findThreadRoot(node);
        if (!row) return;
        if (openFields.some((f) => row.contains(f))) return;
        if (row.querySelector(`.${BTN_CLASS}`)) { state.processed.add(node); return; }
        if (!extractCommentText(row)) return;

        const opener = findOpenReplyButton(row);
        const bar = (opener && opener.parentElement) || findActionContainer(row);
        if (!bar) return;
        state.processed.add(node);
        node.setAttribute(MARK, "1");
        injectButton(bar, row, opener);
      });
    }
  }

  function injectButton(container, rowRoot, opener) {
    const btn = document.createElement("button");
    btn.className = BTN_CLASS;
    btn.type = "button";
    btn.textContent = LABEL_IDLE;
    btn.title = "Genera la respuesta y la publica tras verificarla";
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      runFlow(btn, rowRoot, opener);
    });
    container.appendChild(btn);
  }

  /* ==========================================================================
     3. LECTURA DE LA FILA
     ========================================================================== */

  // Sube hasta el contenedor de hilo. Rechaza candidatos demasiado grandes
  // para no acabar seleccionando la lista entera de comentarios: ese era el
  // camino por el que la v1 podia escribir en la fila equivocada.
  function findThreadRoot(el) {
    for (const tag of THREAD_TAGS) {
      const m = el.closest(tag);
      if (m) return m;
    }
    let n = el.parentElement;
    for (let i = 0; i < 12 && n; i++) {
      if (n === document.body) break;
      const h = n.offsetHeight || 0;
      if (h > 1600) break;
      const openers = [...n.querySelectorAll("ytcp-button, button")].filter((b) => {
        const t = txt(b).toLowerCase();
        return OPEN_TEXTS.includes(t) && !b.classList.contains(BTN_CLASS);
      });
      if (openers.length > 4) break;
      if (extractCommentText(n) && openers.length >= 1) return n;
      n = n.parentElement;
    }
    return el.parentElement || el;
  }

  function extractCommentText(node) {
    if (!node) return null;
    for (const sel of TEXT_SELECTORS) {
      const el = node.querySelector(sel);
      if (el) {
        const t = txt(el);
        if (t.length > 4) return t;
      }
    }
    let best = "";
    node.querySelectorAll("*").forEach((el) => {
      if (el.children.length === 0) {
        const t = txt(el);
        if (t.length > best.length && t.length > 10 && t.length < 4000) best = t;
      }
    });
    return best || null;
  }

  function findActionContainer(node) {
    for (const sel of ACTION_SELECTORS) {
      const el = node.querySelector(sel);
      if (el) return el;
    }
    return null;
  }

  function getVideoContext(rowRoot) {
    let title = null;
    const scopes = [rowRoot];
    let a = rowRoot?.parentElement;
    for (let i = 0; i < 6 && a; i++) { scopes.push(a); a = a.parentElement; }

    outer: for (const scope of scopes) {
      if (!scope) continue;
      for (const sel of ROW_VIDEO_TITLE_SELECTORS) {
        const el = scope.querySelector(sel);
        if (el) {
          const t = txt(el);
          if (t.length > 2 && t.length < 300) { title = t; break outer; }
        }
      }
    }
    if (!title) title = extractPageTitle();

    let description = null;
    for (const sel of PAGE_DESCRIPTION_SELECTORS) {
      const el = document.querySelector(sel);
      if (el) {
        const t = txt(el);
        if (t.length > 10 && t.length < 1500) { description = t; break; }
      }
    }
    return { title, description };
  }

  function extractPageTitle() {
    for (const sel of ["h1.ytcp-video-info", "ytcp-video-info h1", "#video-title", "h1[class*='title']", "h1"]) {
      const el = document.querySelector(sel);
      if (el) {
        const t = txt(el);
        if (t.length > 2 && t.length < 300) return t;
      }
    }
    return document.title.replace(/[-–|]?\s*YouTube Studio.*$/i, "").trim() || null;
  }

  // Extraccion del videoId. Frente a la v1 se añade la miniatura de i.ytimg.com,
  // que es la fuente mas fiable en la bandeja de comentarios porque siempre
  // esta presente en cada fila.
  function getVideoId(rowRoot) {
    const scopes = [rowRoot];
    let a = rowRoot?.parentElement;
    for (let i = 0; i < 6 && a; i++) { scopes.push(a); a = a.parentElement; }

    for (const scope of scopes) {
      if (!scope) continue;
      for (const img of scope.querySelectorAll("img[src]")) {
        const m = img.src.match(/\/vi\/([A-Za-z0-9_-]{11})\//);
        if (m) return m[1];
      }
      for (const el of scope.querySelectorAll("a[href]")) {
        const h = el.href || "";
        const m =
          h.match(/[?&]v=([A-Za-z0-9_-]{11})/) ||
          h.match(/\/video\/([A-Za-z0-9_-]{11})/) ||
          h.match(/\/shorts\/([A-Za-z0-9_-]{11})/) ||
          h.match(/\/live\/([A-Za-z0-9_-]{11})/) ||
          h.match(/youtu\.be\/([A-Za-z0-9_-]{11})/);
        if (m) return m[1];
      }
    }
    const u = location.href.match(/[?&]video_id=([A-Za-z0-9_-]{11})/) ||
              location.href.match(/\/video\/([A-Za-z0-9_-]{11})/);
    return u ? u[1] : null;
  }

  function getCommentId(rowRoot) {
    const el = rowRoot.querySelector("[comment-id]") || (rowRoot.hasAttribute?.("comment-id") ? rowRoot : null);
    return el?.getAttribute("comment-id") || null;
  }

  /* ==========================================================================
     4. FLUJO PRINCIPAL  —  un clic
     ========================================================================== */

  async function runFlow(btn, rowRootAtInject, openerAtInject) {
    if (state.busy) {
      toast("Hay una respuesta en curso. Espera a que termine.", "warn");
      return;
    }
    state.busy = true;
    const setLabel = (s) => { btn.textContent = s; };
    const done = () => { releaseBusy(); btn.disabled = false; setLabel(LABEL_IDLE); };

    let row = rowRootAtInject;

    try {
      btn.disabled = true;
      setLabel("Leyendo…");

      row = liveRow(btn, rowRootAtInject);
      const commentId = getCommentId(row);
      const commentText = extractCommentText(row);
      if (!commentText) return abortFlow(row, "No se ha podido leer el texto del comentario.");

      state.cfg = await getSettings();
      if (!state.cfg.apiKey) {
        return abortFlow(row, "Falta la API key. Abre el icono de la extension y guardala.");
      }

      /* ---- Salvaguarda 1: ninguna otra caja de respuesta abierta ----------
         Es la condicion que hace identificable, sin ambiguedad, cual es el
         campo que se abre despues. Sin esto no hay forma segura de garantizar
         que escribimos en la fila correcta.                                */
      if (visibleFields().length) {
        setLabel("Cerrando…");
        const { conTexto } = await closeOpenBoxes();
        if (visibleFields().length) {
          return abortFlow(
            row,
            conTexto
              ? "Hay un cuadro de respuesta abierto con texto escrito. Enviala o descartala y vuelve a pulsar."
              : "Hay un cuadro de respuesta abierto que no se ha podido cerrar. Cierralo y vuelve a pulsar."
          );
        }
      }

      /* ---- Contexto del video ------------------------------------------- */
      const { title: videoTitle, description: videoDescription } = getVideoContext(row);
      const videoId = getVideoId(row);

      setLabel("Transcripcion…");
      const tr = videoId
        ? await send({ type: "FETCH_TRANSCRIPT", payload: { videoId } }, 20000)
        : { ok: false, reason: "no se ha podido identificar el video" };

      log("Contexto", { videoId, commentId, videoTitle, transcript: tr.ok ? `${tr.text.length} car. (${tr.source})` : `NO — ${tr.reason}` });

      /* ---- Generacion ---------------------------------------------------- */
      setLabel("Generando…");
      const gen = await send({
        type: "GENERATE_REPLY",
        payload: {
          commentText,
          videoTitle,
          videoDescription,
          transcript: tr.ok ? tr.text : null,
        },
      });

      row = liveRow(btn, row, commentId);

      if (!gen || !gen.ok) {
        return abortFlow(row, gen?.error || "Error de conexion con la API.");
      }

      /* ---- Salvaguarda 2: control de calidad del texto generado ---------- */
      const vet = vetReply(gen.reply);
      if (vet.fatal) return abortFlow(row, `Respuesta descartada: ${vet.issues.join("; ")}.`);

      const reasons = [];
      if (state.cfg.mode !== "auto") reasons.push("modo revision activado");
      if (vet.issues.length) reasons.push(vet.issues.join("; "));
      if (state.cfg.requireTranscript && !tr.ok) reasons.push(`sin transcripcion (${tr.reason})`);

      if (reasons.length) {
        log("No se autopublica:", reasons);
        showPanel(row, btn, vet.text, { videoTitle, transcript: tr, reasons, commentId });
        return;
      }

      /* ---- Automatizacion verificada ------------------------------------- */
      const res = await publish(btn, row, openerAtInject, vet.text, setLabel);
      if (!res.ok) {
        showPanel(row, btn, vet.text, { videoTitle, transcript: tr, reasons: [res.error], commentId });
        return;
      }
      toast("Respuesta publicada.", "ok");
      if (state.cfg.likeOnPublish) likeComment(liveRow(btn, row, commentId));
    } catch (err) {
      warn(err);
      abortFlow(row, `Error inesperado: ${err.message}`);
    } finally {
      done();
    }
  }

  function abortFlow(row, message) {
    warn("ABORTADO —", message);
    inlineMessage(row, message, "error");
    toast(message, "err");
    return { ok: false, error: message };
  }

  /* ==========================================================================
     5. PUBLICACION VERIFICADA
     ========================================================================== */

  async function publish(btn, row, openerAtInject, text, setLabel) {
    if (!row || !row.isConnected) {
      return { ok: false, error: "YouTube ha recargado la lista de comentarios. Vuelve a pulsar el boton de la fila." };
    }
    log("Publicando en fila", row.tagName, "· texto de", text.length, "caracteres");

    /* ---- Paso 1: conseguir el campo de respuesta de ESTA fila ------------ */
    let field = null;
    let opener = null;
    const abiertos = visibleFields();
    const abiertosEnFila = abiertos.filter((f) => row.contains(f));

    if (abiertos.length === 1 && abiertosEnFila.length === 1) {
      // Reintento desde el panel: la caja de esta fila ya esta abierta.
      field = abiertosEnFila[0];
      log("Reutilizando la caja ya abierta de esta fila");
    } else if (abiertos.length) {
      return { ok: false, error: "Hay cuadros de respuesta abiertos en la pagina. Cierralos y vuelve a intentarlo." };
    } else {
      setLabel("Abriendo…");
      opener = (openerAtInject && openerAtInject.isConnected && isVisible(openerAtInject))
        ? openerAtInject
        : findOpenReplyButton(row);

      if (!opener) return { ok: false, error: "No se encuentra el boton Responder de esta fila." };

      const before = new Set(visibleFields());
      realClick(opener);

      /* ---- Paso 2: esperar a que aparezca un campo NUEVO -----------------
         No usamos un sleep fijo (la v1 esperaba 1200 ms a ciegas) ni cogemos
         "el ultimo contenteditable visible". Identificamos el campo por
         diferencia: el que no existia antes del clic.                      */
      setLabel("Esperando caja…");
      let ultimo = { nuevos: 0, dentro: 0 };
      field = await waitFor(() => {
        const nuevos = visibleFields().filter((f) => !before.has(f));
        const dentro = nuevos.filter((f) => row.contains(f));
        ultimo = { nuevos: nuevos.length, dentro: dentro.length };
        if (!nuevos.length) return null;
        // Varios contenteditable dentro de la caja es normal en Studio (el de
        // texto y el de menciones). La v2.1.0 devolvia null en ese caso y se
        // quedaba esperando para siempre; ahora elegimos el bueno.
        if (dentro.length) return pickBestField(dentro);
        // Si el campo se renderiza fuera del hilo, solo lo aceptamos cuando no
        // habia ninguno abierto antes: asi no podemos escribir en otra fila.
        if (before.size === 0) return pickBestField(nuevos);
        return null;
      }, { timeout: 8000, interval: 120 });

      if (!field) {
        warn("No se ha identificado el campo.", {
          filaConectada: row.isConnected,
          camposNuevos: ultimo.nuevos,
          dentroDeLaFila: ultimo.dentro,
          habiaAntes: before.size,
          opener: opener.tagName + (opener.id ? "#" + opener.id : ""),
        });
        return {
          ok: false,
          error: ultimo.nuevos
            ? "La caja se ha abierto pero fuera de esta fila. No se escribe nada por seguridad."
            : "Al pulsar Responder no se ha abierto ningun cuadro de respuesta.",
        };
      }
    }
    log("Campo identificado", field);

    /* ---- Paso 3: localizar el boton de enviar y su estado PREVIO ---------
       Guardar si ya estaba habilitado antes de escribir es lo que permite
       usar "se ha habilitado" como prueba de que Angular ha registrado el
       texto. Si ya estaba habilitado, esa prueba no sirve y lo decimos.   */
    let submit = findSubmitButton(field, opener, row);
    const submitWasEnabled = submit ? !isDisabled(submit) : null;

    /* ---- Paso 4: insertar y VERIFICAR el contenido ------------------------ */
    setLabel("Escribiendo…");
    const method = await insertText(field, text);
    if (!method) {
      return { ok: false, error: "El texto no se ha podido escribir en el cuadro. Lo tienes en el portapapeles." };
    }
    log("Texto insertado via", method);

    /* ---- Paso 5: confirmar que el framework lo ha registrado ------------- */
    if (!submit) submit = findSubmitButton(field, opener, row);
    if (!submit) {
      return { ok: false, error: "No se encuentra el boton de enviar. El texto ya esta escrito: pulsalo tu." };
    }

    if (submitWasEnabled === false) {
      setLabel("Verificando…");
      const enabled = await waitFor(() => !isDisabled(submit), { timeout: 5000, interval: 100 });
      if (!enabled) {
        return { ok: false, error: "El boton de enviar sigue deshabilitado: YouTube no ha registrado el texto. Revisalo y envia tu." };
      }
      log("Boton de enviar habilitado — texto registrado por Angular");
    } else {
      log("El boton de enviar ya estaba habilitado; la verificacion se apoya solo en el contenido del campo");
    }

    // Ultima relectura antes del punto de no retorno.
    if (!contentMatches(field, text)) {
      return { ok: false, error: "El contenido del cuadro ha cambiado justo antes de enviar. No se ha publicado." };
    }

    /* ---- Paso 6: ventana de escape --------------------------------------- */
    const secs = Number(state.cfg.countdown) || 0;
    if (secs > 0) {
      setLabel("Publicando…");
      const verdict = await countdownOverlay(secs, text);
      if (verdict === "cancel") {
        return { ok: false, error: "Cancelado por ti. El texto sigue en el cuadro." };
      }
      if (verdict === "edit") {
        field.focus();
        return { ok: false, error: "En edicion. Revisa el texto y pulsa Responder tu." };
      }
    }

    /* ---- Paso 7: enviar y confirmar -------------------------------------- */
    // Si la pagina ha cambiado durante la cuenta atras (navegacion real, no
    // el aplazamiento de deactivate() de mas arriba), campo y fila ya no
    // estan conectados: publicar ahora seria un clic a ciegas sobre un nodo
    // fantasma, y el chequeo de "desaparecido" de abajo lo daria por bueno
    // sin haberse enviado nada.
    if (!row.isConnected || !field.isConnected) {
      return { ok: false, error: "La pagina ha cambiado justo antes de enviar. No se ha publicado." };
    }
    if (isDisabled(submit)) {
      return { ok: false, error: "El boton de enviar se ha deshabilitado antes de pulsarlo. No se ha publicado." };
    }
    realClick(submit);

    /* La confirmacion exige DOS señales, no una (hipotesis H1 del traspaso:
       era la causa mas probable de "desaparece la ventana y no pasa nada").
       Con una sola señal -solo el campo, como en 2.2.1- un cierre del cuadro
       por cualquier motivo ajeno al envio (cancelacion, repintado de
       Angular) se confundia con una publicacion real y el panel se cerraba
       sin haber publicado nada. Exigir tambien que el boton de enviar se
       haya deshabilitado, desconectado u ocultado descarta ese falso
       positivo salvo que ambas señales cambien exactamente a la vez.      */
    const sent = await waitFor(() => {
      const fieldGone = !field.isConnected || !isVisible(field) || norm(fieldText(field)) === "";
      const submitGone = !submit.isConnected || !isVisible(submit) || isDisabled(submit);
      return fieldGone && submitGone ? true : null;
    }, { timeout: 6000, interval: 150 });

    if (!sent) {
      return { ok: false, error: "Se ha pulsado enviar pero el cuadro sigue abierto. Comprueba si se ha publicado." };
    }
    return { ok: true };
  }

  /* ==========================================================================
     5bis. "ME GUSTA" AL COMENTARIO TRAS PUBLICAR
     ----------------------------------------------------------------------------
     A diferencia de publish(), esto es "best effort": no hay selector real
     verificado (nadie ha tenido acceso al DOM de Studio con el diagnostico
     ampliado todavia — ver diagnostico-dom.js, seccion 6). Si no se encuentra
     un boton con el que se tenga confianza razonable, se omite en silencio.
     Nunca debe poder hacer fallar ni deshacer una publicacion ya confirmada:
     se llama siempre DESPUES de que publish() ha devuelto ok:true, envuelto
     en try/catch, y su resultado no se propaga como error.               */
  const LIKE_WORDS = ["me gusta", "like"];
  const LIKE_EXCLUDE = [
    "no me gusta", "dislike", "corazon", "corazón", "heart",
    "responder", "reply", "respondre", "cancelar", "cancel",
    "mas opciones", "more options", "publicar", "comentar", "comment",
  ];

  async function likeComment(row) {
    if (!row?.isConnected) return false;
    try {
      const cands = [...row.querySelectorAll(
        "ytcp-icon-button, tp-yt-paper-icon-button, ytcp-button, button, tp-yt-paper-button"
      )].filter((b) => isVisible(b) && !esNuestro(b));

      const btn = cands.find((b) => {
        const label = ((b.getAttribute("aria-label") || "").trim() || txt(b)).toLowerCase();
        if (!label) return false;
        if (LIKE_EXCLUDE.some((w) => label.includes(w))) return false;
        if (b.getAttribute("aria-pressed") === "true") return false; // ya estaba marcado
        return LIKE_WORDS.some((w) => label.includes(w));
      });

      if (!btn) {
        log("Dar 'me gusta': no se ha identificado el boton con confianza suficiente. Se omite.");
        return false;
      }
      realClick(btn);
      log("Dar 'me gusta' al comentario: clic emitido.");
      return true;
    } catch (e) {
      warn("Dar 'me gusta' ha fallado (no afecta a la respuesta ya publicada):", e.message);
      return false;
    }
  }

  /* ==========================================================================
     6. PRIMITIVAS DE DOM
     ========================================================================== */

  function visibleFields(root = document) {
    const out = new Set();
    root.querySelectorAll(FIELD_SELECTOR).forEach((f) => {
      if (isVisible(f) && !esNuestro(f)) out.add(f);
    });
    return [...out];
  }

  // Cualquier elemento de la propia extension queda fuera de las busquedas.
  function esNuestro(el) {
    return !!el.closest?.(".yra2-panel, .yra2-countdown, .yra2-toast") || el.classList?.contains(BTN_CLASS);
  }

  // El campo real de Studio (confirmado con diagnostico-dom.js) es un
  // <textarea>: su contenido vive en .value, no en .innerText/.textContent
  // (que en un <textarea> reflejan el HTML inicial, no lo que el usuario ha
  // escrito). Si en algun otro dialogo Studio usa contenteditable, se sigue
  // leyendo por innerText como hasta ahora.
  function fieldText(field) {
    if (!field) return "";
    if (field.tagName === "TEXTAREA") return field.value || "";
    return field.innerText || field.textContent || "";
  }

  /* Clic completo. YouTube Studio usa componentes tipo ytcp-button que en
     muchos casos reaccionan a eventos de puntero (gestos), no al click suelto.
     Un .click() a pelo puede no abrir nada. Emitimos la secuencia de puntero y
     raton y despues UN solo click nativo: nunca dos, para que no exista riesgo
     de doble publicacion. */
  function realClick(el) {
    const target = el.querySelector?.("button:not([disabled])") || el;
    const r = target.getBoundingClientRect();
    const o = {
      bubbles: true, cancelable: true, composed: true, view: window,
      clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
      button: 0, buttons: 1, pointerId: 1, isPrimary: true, pointerType: "mouse",
    };
    try { target.dispatchEvent(new PointerEvent("pointerdown", o)); } catch (e) {}
    try { target.dispatchEvent(new MouseEvent("mousedown", o)); } catch (e) {}
    try { target.focus(); } catch (e) {}
    try { target.dispatchEvent(new PointerEvent("pointerup", { ...o, buttons: 0 })); } catch (e) {}
    try { target.dispatchEvent(new MouseEvent("mouseup", { ...o, buttons: 0 })); } catch (e) {}
    target.click();
  }

  // De varios campos candidatos, el que de verdad es la caja de texto.
  function pickBestField(cands) {
    const vivos = cands.filter((f) => !f.closest("[aria-hidden='true']"));
    const pool = vivos.length ? vivos : cands;
    const root = pool.find((f) => f.id === "contenteditable-root");
    if (root) return root;
    const area = (e) => { const r = e.getBoundingClientRect(); return r.width * r.height; };
    return [...pool].sort((a, b) => area(b) - area(a))[0];
  }

  function findOpenReplyButton(scope) {
    const search = (r) => {
      const cands = [...r.querySelectorAll("ytcp-button, button, tp-yt-paper-button")].filter((b) => {
        if (esNuestro(b)) return false;
        if (!isVisible(b)) return false;
        if (isDisabled(b)) return false;
        const t = txt(b).toLowerCase();
        const al = (b.getAttribute("aria-label") || "").trim().toLowerCase();
        return OPEN_TEXTS.includes(t) || OPEN_TEXTS.includes(al);
      });
      return cands[0] || null;
    };
    const inside = search(scope);
    if (inside) return inside;
    let a = scope.parentElement;
    for (let i = 0; i < 5 && a; i++) {
      const f = search(a);
      if (f) return f;
      a = a.parentElement;
    }
    return null;
  }

  // Busca el boton de enviar dentro de un contenedor concreto. OPEN_TEXTS y
  // SUBMIT_TEXTS se solapan a proposito ("Responder" es a la vez el boton que
  // abre la caja y, en algunas variantes de Studio, el que envia), asi que la
  // unica forma fiable de no coger el boton equivocado (hipotesis H2 del
  // traspaso: un "Responder" de otra fila o de un menu) es acotar la busqueda
  // al contenedor correcto, no solo filtrar por texto y orden de documento.
  function buscarBotonEnviar(scope, field, opener) {
    const byId = scope.querySelector("ytcp-button#submit-button, #submit-button");
    if (byId && isVisible(byId) && byId !== opener && !esNuestro(byId)) return byId;

    const cands = [...scope.querySelectorAll("ytcp-button, button, tp-yt-paper-button")].filter((b) => {
      if (b === opener) return false;
      if (esNuestro(b)) return false;
      if (!isVisible(b)) return false;
      const t = txt(b).toLowerCase();
      const al = (b.getAttribute("aria-label") || "").trim().toLowerCase();
      if (!SUBMIT_TEXTS.includes(t) && !SUBMIT_TEXTS.includes(al)) return false;
      // Debe ir DESPUES del campo en orden de documento: el boton que abre
      // la caja siempre esta antes.
      return !!(field.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    });
    return cands[0] || null;
  }

  function findSubmitButton(field, opener, row) {
    // Paso 1: acotado a la fila que ya hemos identificado como la correcta.
    // Es la busqueda mas segura porque no puede alcanzar el boton de otra
    // fila, sea cual sea su texto.
    if (row && row.contains(field)) {
      const found = buscarBotonEnviar(row, field, opener);
      if (found) return found;
    }

    // Paso 2 (respaldo): subir por los ancestros del campo, como antes de
    // acotar por fila. Se detiene si el contenedor ya es demasiado grande
    // para ser la caja de este comentario (mismo umbral que findThreadRoot),
    // por si el boton se renderiza fuera de la fila (portal/dialogo).
    let n = field.parentElement;
    for (let i = 0; i < 10 && n; i++) {
      if ((n.offsetHeight || 0) > 1600) break;
      const found = buscarBotonEnviar(n, field, opener);
      if (found) return found;
      n = n.parentElement;
    }
    return null;
  }

  // Cierra las cajas de respuesta que esten VACIAS. Una caja con texto dentro
  // es trabajo tuyo a medio escribir: no se toca, se aborta y se avisa.
  async function closeOpenBoxes() {
    let conTexto = false;
    for (const f of visibleFields()) {
      if (norm(fieldText(f))) { conTexto = true; continue; }
      let n = f.parentElement;
      for (let i = 0; i < 8 && n; i++) {
        const cancel = [...n.querySelectorAll("ytcp-button, button")].find((b) => {
          if (esNuestro(b)) return false;
          const t = txt(b).toLowerCase();
          const al = (b.getAttribute("aria-label") || "").trim().toLowerCase();
          return (CANCEL_TEXTS.includes(t) || CANCEL_TEXTS.includes(al)) && isVisible(b);
        });
        if (cancel) { realClick(cancel); break; }
        n = n.parentElement;
      }
    }
    await sleep(350);
    if (!conTexto && visibleFields().length) {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      await sleep(350);
    }
    return { conTexto };
  }

  /* Insercion de texto.
     Metodo 1 — execCommand con seleccion explicita. Genera eventos de
     entrada de confianza, indistinguibles de escribir a mano, que es lo que
     Angular espera. Requiere foco Y seleccion: la v1 no fijaba la seleccion,
     que es la causa mas probable de que te cayera al fallback de pegar.
     Metodo 2 — mundo principal via background (setters nativos + InputEvent).
     Tras cada metodo se RELEE el campo para comprobar que el texto esta. */
  async function insertText(field, text) {
    try { await navigator.clipboard.writeText(text); } catch { /* sin permiso: da igual */ }

    field.focus();
    field.click();

    if (field.tagName === "TEXTAREA") {
      // El campo real de Studio (confirmado con diagnostico-dom.js contra el
      // DOM real) es un <textarea>: no participa en window.getSelection() ni
      // en Range como un contenteditable, asi que execCommand no le afecta.
      // El setter nativo del value + los eventos que escucha un formulario
      // reactivo (input, change) es el metodo correcto aqui.
      try {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
        setter.call(field, text);
        field.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
        field.dispatchEvent(new Event("change", { bubbles: true }));
      } catch (e) { warn("insercion en textarea:", e.message); }

      await sleep(150);
      if (contentMatches(field, text)) return "textarea-setter";
      log("el setter de textarea no ha registrado el texto; probando mundo principal");
    } else {
      try {
        const sel = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(field);
        sel.removeAllRanges();
        sel.addRange(range);
      } catch (e) { warn("seleccion:", e.message); }

      try {
        document.execCommand("delete", false, null);
        document.execCommand("insertText", false, text);
      } catch (e) { warn("execCommand:", e.message); }

      await sleep(220);
      if (contentMatches(field, text)) {
        if (/\n\s*\n/.test(text) && !/\n/.test(field.innerText || "")) {
          warn("YouTube ha aplanado los saltos de parrafo de la respuesta.");
        }
        return "execCommand";
      }
      log("execCommand no ha registrado el texto; probando mundo principal");
    }

    field.setAttribute("data-yra2-target", "1");
    const r = await send({ type: "INSERT_MAIN", payload: { text } }, 12000);
    field.removeAttribute("data-yra2-target");
    await sleep(320);
    if (contentMatches(field, text)) return `main:${r?.method || "?"}`;

    return null;
  }

  function contentMatches(field, text) {
    const got = norm(fieldText(field));
    const want = norm(text);
    if (!got) return false;
    if (got === want) return true;
    const head = want.slice(0, Math.min(40, want.length));
    return got.startsWith(head) && got.length >= want.length * 0.9;
  }

  function isDisabled(el) {
    if (!el) return true;
    if (el.disabled === true) return true;
    if (el.hasAttribute("disabled")) return true;
    if (el.getAttribute("aria-disabled") === "true") return true;
    const inner = el.querySelector?.("button");
    if (inner && (inner.disabled || inner.hasAttribute("disabled"))) return true;
    return false;
  }

  function clickEl(el) {
    const target = el.querySelector?.("button:not([disabled])") || el;
    target.click();
  }

  function isVisible(el) {
    if (!el || !el.isConnected) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none" || cs.opacity === "0") return false;
    return true;
  }

  function liveRow(btn, fallback, commentId) {
    if (btn?.isConnected) {
      for (const tag of THREAD_TAGS) {
        const m = btn.closest(tag);
        if (m) return m;
      }
    }
    // Angular reemplaza nodos enteros al repintar. El comment-id es el unico
    // ancla que sobrevive a eso, asi que reanclamos por el.
    if (commentId) {
      const el = document.querySelector(`[comment-id="${CSS.escape(commentId)}"]`);
      if (el) return findThreadRoot(el);
    }
    if (fallback?.isConnected) return fallback;
    return btn?.parentElement || fallback;
  }

  /* ==========================================================================
     7. CONTROL DE CALIDAD DEL TEXTO GENERADO
     ========================================================================== */

  function vetReply(raw) {
    let t = String(raw || "").trim();
    t = t.replace(/^```[a-z]*\s*/i, "").replace(/\s*```$/, "").trim();
    if ((t.startsWith('"') && t.endsWith('"')) || (t.startsWith("«") && t.endsWith("»"))) {
      t = t.slice(1, -1).trim();
    }
    const issues = [];
    let fatal = false;

    if (!t || t.length < 2) { issues.push("respuesta vacia"); fatal = true; }
    if (t.length > 2000) issues.push(`respuesta muy larga (${t.length} caracteres)`);

    const leak = /COMENTARIO A RESPONDER|TRANSCRIPCI[OÓ]N DEL V[IÍ]DEO|CONTEXTO EXTRA|SYSTEM PROMPT/i;
    if (leak.test(t)) { issues.push("fuga del prompt"); fatal = true; }

    const flags = [
      [/excelente pregunta/i, "muletilla prohibida"],
      [/\bcomo (una )?(ia|inteligencia artificial)\b/i, "se identifica como IA"],
      [/\bas an ai\b/i, "se identifica como IA"],
      [/modelo de lenguaje/i, "se identifica como IA"],
      [/no (puedo|tengo la capacidad de) (ayudarte|responder|acceder)/i, "respuesta evasiva"],
      [/\[(insertar|completar|tu nombre|nombre del)/i, "marcador sin rellenar"],
    ];
    for (const [re, label] of flags) if (re.test(t)) issues.push(label);

    return { text: t, issues, fatal };
  }

  /* ==========================================================================
     8. INTERFAZ
     ========================================================================== */

  // Panel: se ancla al body en coordenadas de documento. Asi escapa de
  // cualquier ancestro con overflow:hidden (el motivo por el que la v1 lo
  // clavaba arriba tapando el primer comentario) y a la vez acompaña al
  // scroll de la pagina.
  function showPanel(row, btn, text, meta) {
    document.querySelectorAll(".yra2-panel").forEach((p) => p.remove());

    const panel = document.createElement("div");
    panel.className = "yra2-panel";

    const trBadge = meta.transcript?.ok
      ? `<span class="yra2-tag yra2-tag--ok">transcripcion ${Math.round(meta.transcript.text.length / 1000)}k</span>`
      : `<span class="yra2-tag yra2-tag--warn">sin transcripcion</span>`;

    panel.innerHTML = `
      <div class="yra2-panel-head">
        <div class="yra2-panel-title">Revisa antes de publicar</div>
        <div class="yra2-tags">${trBadge}</div>
        <button class="yra2-x" type="button" aria-label="Cerrar">✕</button>
      </div>
      ${meta.reasons?.length ? `<div class="yra2-why">No se ha publicado sola: ${escapeHtml(meta.reasons.join(" · "))}</div>` : ""}
      <textarea class="yra2-text" spellcheck="true"></textarea>
      <div class="yra2-panel-foot">
        <button class="yra2-act yra2-act--primary" data-act="publish" type="button">Publicar</button>
        <button class="yra2-act" data-act="copy" type="button">Copiar</button>
        <button class="yra2-act" data-act="regen" type="button">Regenerar</button>
        <span class="yra2-count"></span>
      </div>
    `;

    document.body.appendChild(panel);
    placePanel(panel, row);

    const ta = panel.querySelector(".yra2-text");
    ta.value = text;
    const counter = panel.querySelector(".yra2-count");
    const updateCount = () => { counter.textContent = `${ta.value.length} caracteres`; };
    ta.addEventListener("input", updateCount);
    updateCount();

    panel.querySelector(".yra2-x").addEventListener("click", () => panel.remove());

    panel.addEventListener("click", async (e) => {
      const act = e.target?.dataset?.act;
      if (!act) return;

      if (act === "copy") {
        try { await navigator.clipboard.writeText(ta.value); e.target.textContent = "Copiado"; }
        catch { e.target.textContent = "No se ha podido copiar"; }
        setTimeout(() => { e.target.textContent = "Copiar"; }, 1800);
        return;
      }

      if (act === "publish") {
        if (state.busy) { toast("Hay una respuesta en curso.", "warn"); return; }
        state.busy = true;
        e.target.disabled = true;
        e.target.textContent = "Publicando…";
        const live = liveRow(btn, row, meta.commentId);
        const prev = Number(state.cfg.countdown);
        state.cfg.countdown = 0; // ya lo ha revisado el humano
        panel.querySelectorAll(".yra2-act").forEach((b) => { b.disabled = true; });
        let res;
        try {
          res = await publish(btn, live, null, ta.value, () => {});
        } catch (err) {
          res = { ok: false, error: `Error inesperado: ${err.message}` };
        } finally {
          state.cfg.countdown = prev;
          releaseBusy();
        }
        panel.querySelectorAll(".yra2-act").forEach((b) => { b.disabled = false; });
        e.target.textContent = "Publicar";
        if (res.ok) {
          panel.remove();
          toast("Respuesta publicada.", "ok");
          if (state.cfg.likeOnPublish) likeComment(liveRow(btn, live, meta.commentId));
        } else {
          inlineMessage(panel, res.error, "error");
          toast(res.error, "err"); // tambien fuera del panel, por si se cierra
        }
        return;
      }

      if (act === "regen") {
        if (state.busy) return;
        e.target.disabled = true;
        e.target.textContent = "Regenerando…";
        const live = liveRow(btn, row, meta.commentId);
        const gen = await send({
          type: "GENERATE_REPLY",
          payload: {
            commentText: extractCommentText(live),
            videoTitle: meta.videoTitle,
            videoDescription: null,
            transcript: meta.transcript?.ok ? meta.transcript.text : null,
            nonce: Date.now(),
          },
        });
        e.target.disabled = false;
        e.target.textContent = "Regenerar";
        if (gen?.ok) { ta.value = vetReply(gen.reply).text; updateCount(); }
        else inlineMessage(panel, gen?.error || "Error al regenerar.", "error");
      }
    });

    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);
  }

  function placePanel(panel, row) {
    const r = row.getBoundingClientRect();
    const width = Math.min(760, window.innerWidth - 48);
    let left = r.left + window.scrollX;
    if (left + width > window.scrollX + window.innerWidth - 24) {
      left = window.scrollX + window.innerWidth - width - 24;
    }
    panel.style.width = `${width}px`;
    panel.style.left = `${Math.max(window.scrollX + 16, left)}px`;
    panel.style.top = `${r.bottom + window.scrollY + 8}px`;
  }

  // Cuenta atras antes de publicar. Resuelve "go", "edit" o "cancel".
  function countdownOverlay(seconds, text) {
    return new Promise((resolve) => {
      document.querySelectorAll(".yra2-countdown").forEach((e) => e.remove());

      const box = document.createElement("div");
      box.className = "yra2-countdown";
      box.innerHTML = `
        <div class="yra2-cd-ring"><span class="yra2-cd-num">${seconds}</span></div>
        <div class="yra2-cd-body">
          <div class="yra2-cd-title">Publicando la respuesta</div>
          <div class="yra2-cd-preview"></div>
        </div>
        <div class="yra2-cd-acts">
          <button class="yra2-act" data-cd="edit" type="button">Editar</button>
          <button class="yra2-act yra2-act--danger" data-cd="cancel" type="button">Cancelar</button>
        </div>
      `;
      box.querySelector(".yra2-cd-preview").textContent =
        text.length > 130 ? text.slice(0, 130) + "…" : text;
      document.body.appendChild(box);

      let left = seconds;
      const num = box.querySelector(".yra2-cd-num");
      const finish = (verdict) => {
        clearInterval(timer);
        document.removeEventListener("keydown", onKey, true);
        state.abort = null;
        box.remove();
        resolve(verdict);
      };
      const timer = setInterval(() => {
        left -= 1;
        num.textContent = String(Math.max(0, left));
        if (left <= 0) finish("go");
      }, 1000);

      const onKey = (e) => {
        if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); finish("cancel"); }
      };
      document.addEventListener("keydown", onKey, true);

      box.addEventListener("click", (e) => {
        const v = e.target?.dataset?.cd;
        if (v) finish(v);
      });

      state.abort = () => finish("cancel");
    });
  }

  function toast(message, kind = "ok") {
    const t = document.createElement("div");
    t.className = `yra2-toast yra2-toast--${kind}`;
    t.textContent = message;
    document.body.appendChild(t);
    t.addEventListener("click", () => t.remove());
    setTimeout(() => t.remove(), kind === "err" ? 12000 : 4500);
  }

  function inlineMessage(container, message, kind) {
    if (!container || !container.isConnected) { toast(message, kind === "error" ? "err" : "ok"); return; }
    container.querySelector(":scope > .yra2-inline")?.remove();
    const el = document.createElement("div");
    el.className = `yra2-inline yra2-inline--${kind}`;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => el.remove(), 9000);
  }

  /* ==========================================================================
     9. UTILIDADES
     ========================================================================== */

  function txt(el) {
    return (el?.innerText || el?.textContent || "").trim();
  }

  function norm(s) {
    return String(s).replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function waitFor(fn, { timeout = 5000, interval = 100 } = {}) {
    return new Promise((resolve) => {
      const t0 = Date.now();
      (function tick() {
        let v = null;
        try { v = fn(); } catch { v = null; }
        if (v) return resolve(v);
        if (Date.now() - t0 >= timeout) return resolve(null);
        setTimeout(tick, interval);
      })();
    });
  }

  function send(message, timeoutMs = 45000) {
    return new Promise((resolve) => {
      let hecho = false;
      const acabar = (v) => { if (!hecho) { hecho = true; clearTimeout(t); resolve(v); } };
      // Sin este tope, si el service worker no responde el flujo se queda
      // colgado para siempre y el usuario solo ve que "no pasa nada".
      const t = setTimeout(() => acabar({
        ok: false,
        error: `El proceso de fondo no ha respondido en ${Math.round(timeoutMs / 1000)} s (${message.type}).`,
      }), timeoutMs);
      try {
        chrome.runtime.sendMessage(message, (response) => {
          if (chrome.runtime.lastError) acabar({ ok: false, error: chrome.runtime.lastError.message });
          else acabar(response || { ok: false, error: "Sin respuesta del proceso de fondo." });
        });
      } catch (e) {
        acabar({ ok: false, error: e.message });
      }
    });
  }

  function getSettings() {
    return new Promise((resolve) => {
      chrome.storage.local.get(DEFAULTS, (v) => resolve({ ...DEFAULTS, ...v }));
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* ── Escape global: cierra panel y cancela cuenta atras ─────────────────── */
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (state.abort) { state.abort(); return; }
    document.querySelectorAll(".yra2-panel").forEach((p) => p.remove());
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    getSettings().then((c) => { state.cfg = c; });
  });

  /* ── Arranque ───────────────────────────────────────────────────────────── */
  watchRoute();
  log("Cargado. Vigilando ruta.");
})();
