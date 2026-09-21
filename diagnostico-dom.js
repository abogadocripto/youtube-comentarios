/* ============================================================================
   DIAGNOSTICO DEL DOM DE YOUTUBE STUDIO
   ----------------------------------------------------------------------------
   Para que sirve: la extension automatiza el DOM de Studio a ciegas, con
   selectores deducidos. Este script revela la estructura REAL. Es de solo
   lectura: no pulsa nada, no publica nada, no envia nada a ningun sitio.

   COMO USARLO
   1. Ve a YouTube Studio > Comunidad > Comentarios.
   2. Abre a mano el cuadro de respuesta de un comentario (boton Responder).
   3. Escribe dos o tres letras dentro, a mano, para que el boton de enviar
      se habilite.
   4. F12 > Consola. Si pide permiso, teclea  allow pasting  y Enter.
   5. Pega este fichero entero y Enter.
   6. Copia toda la salida.
   ========================================================================== */

(() => {
  const L = [];
  const say = (...a) => L.push(a.join(" "));
  const ident = (el) => {
    if (!el) return "null";
    const id = el.id ? `#${el.id}` : "";
    const cls = (el.className && typeof el.className === "string")
      ? "." + el.className.trim().split(/\s+/).slice(0, 3).join(".")
      : "";
    return `${el.tagName.toLowerCase()}${id}${cls}`;
  };
  const visible = (el) => {
    if (!el?.isConnected) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== "hidden" && cs.display !== "none" && cs.opacity !== "0";
  };
  const cadena = (el, n = 8) => {
    const out = [];
    let x = el;
    for (let i = 0; i < n && x && x !== document.body; i++) { out.push(ident(x)); x = x.parentElement; }
    return out.join("  <  ");
  };

  say("=== DIAGNOSTICO YRA — " + new Date().toISOString() + " ===");
  say("URL: " + location.pathname + location.search);
  say("");

  /* 1. Campos editables ---------------------------------------------------- */
  const SEL = "div#contenteditable-root, ytcp-mentionable-textarea [contenteditable='true'], " +
              "ytcp-form-textarea [contenteditable='true'], div[contenteditable='true']";
  const todos = [...new Set(document.querySelectorAll(SEL))];
  const vis = todos.filter(visible);

  say(`1. CAMPOS EDITABLES: ${todos.length} en total, ${vis.length} visibles`);
  vis.forEach((f, i) => {
    const r = f.getBoundingClientRect();
    say(`   [${i}] ${ident(f)}  ${Math.round(r.width)}x${Math.round(r.height)}` +
        `  ariaHidden=${!!f.closest("[aria-hidden='true']")}` +
        `  texto=${JSON.stringify((f.innerText || "").slice(0, 30))}`);
    say(`        cadena: ${cadena(f)}`);
  });
  if (!vis.length) say("   NINGUNO. Abre a mano un cuadro de respuesta antes de ejecutar esto.");
  say("");

  /* 2. Botones alrededor del campo ----------------------------------------- */
  const campo = vis.find((f) => f.id === "contenteditable-root") || vis[0];
  if (campo) {
    say("2. BOTONES ALREDEDOR DEL CAMPO (subiendo desde el)");
    let n = campo.parentElement;
    for (let nivel = 0; nivel < 8 && n && n !== document.body; nivel++) {
      const bs = [...n.querySelectorAll("ytcp-button, button, tp-yt-paper-button")].filter(visible);
      if (bs.length) {
        say(`   nivel ${nivel} (${ident(n)}): ${bs.length} boton(es)`);
        bs.forEach((b) => {
          const despues = !!(campo.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
          const inner = b.querySelector("button");
          say(`      ${ident(b)}`);
          say(`         texto=${JSON.stringify((b.innerText || "").trim().slice(0, 25))}` +
              `  aria=${JSON.stringify(b.getAttribute("aria-label") || "")}`);
          say(`         disabled=${b.hasAttribute("disabled")}` +
              `  ariaDisabled=${b.getAttribute("aria-disabled")}` +
              `  propDisabled=${b.disabled}` +
              `  innerDisabled=${inner ? inner.disabled : "sin-inner"}`);
          say(`         despuesDelCampo=${despues}`);
        });
      }
      n = n.parentElement;
    }
  }
  say("");

  /* 3. Contenedor de hilo -------------------------------------------------- */
  say("3. CONTENEDORES DE HILO PRESENTES EN LA PAGINA");
  ["ytcp-comment-thread", "ytcp-comment", "ytcp-comment-item", "ytcp-comment-info",
   "ytcp-comment-snippet", "ytcp-mentionable-textarea", "ytcp-commentbox",
   "ytcp-comment-dialog"].forEach((t) => {
    const n = document.querySelectorAll(t).length;
    if (n) say(`   ${t}: ${n}`);
  });
  if (campo) {
    const hilo = campo.closest("ytcp-comment-thread") || campo.closest("ytcp-comment");
    say(`   El campo abierto ${hilo ? "SI" : "NO"} esta dentro de un contenedor de hilo` +
        (hilo ? ` (${ident(hilo)})` : ""));
  }
  say("");

  /* 4. Comment-id ---------------------------------------------------------- */
  const conId = document.querySelectorAll("[comment-id]");
  say(`4. ATRIBUTO comment-id: ${conId.length} elementos`);
  if (conId.length) say(`   ejemplo: ${ident(conId[0])} → ${conId[0].getAttribute("comment-id")}`);
  say("");

  /* 5. Que ve la extension ------------------------------------------------- */
  say("5. ELEMENTOS DE LA EXTENSION EN LA PAGINA");
  ["yra2-btn", "yra2-panel", "yra2-toast", "yra2-countdown"].forEach((c) => {
    say(`   .${c}: ${document.querySelectorAll("." + c).length}`);
  });
  say("");

  /* 6. Prueba de insercion ------------------------------------------------- */
  if (campo) {
    say("6. PRUEBA DE INSERCION (escribe y borra una marca de prueba)");
    const antes = campo.innerText || "";
    const marca = "YRA_PRUEBA_" + Date.now();
    try {
      campo.focus();
      const sel = window.getSelection();
      const r = document.createRange();
      r.selectNodeContents(campo);
      sel.removeAllRanges();
      sel.addRange(r);
      const ok = document.execCommand("insertText", false, marca);
      const leido = campo.innerText || "";
      say(`   execCommand devolvio: ${ok}`);
      say(`   el campo contiene la marca: ${leido.includes(marca)}`);
      // restaurar
      const r2 = document.createRange();
      r2.selectNodeContents(campo);
      sel.removeAllRanges();
      sel.addRange(r2);
      document.execCommand("insertText", false, antes);
      say(`   restaurado a: ${JSON.stringify((campo.innerText || "").slice(0, 30))}`);
    } catch (e) {
      say(`   ERROR: ${e.message}`);
    }
  }

  const salida = L.join("\n");
  console.log(salida);
  try { copy(salida); console.log("\n>>> Copiado al portapapeles."); } catch (e) {}
  return "Diagnostico terminado. Revisa la salida de arriba.";
})();
