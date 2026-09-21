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
   4. Pasa el raton por encima de la fila del comentario un momento (algunos
      iconos de me gusta / no me gusta solo aparecen al hover).
   5. F12 > Consola. Si pide permiso, teclea  allow pasting  y Enter.
   6. Pega este fichero entero y Enter.
   7. Copia toda la salida.

   Busca ademas si el campo de respuesta es un <textarea> normal en vez de un
   contenteditable, y lista los botones de reaccion (me gusta, etc.) de la
   fila del comentario.
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

  /* 1. Campos de respuesta: contenteditable Y <textarea> --------------------
     Antes solo se buscaba contenteditable. Si Studio ha cambiado a un
     <textarea> normal (el placeholder "Añade una respuesta..." es tipico de
     un textarea, no de un contenteditable), el metodo de insercion actual
     -execCommand con seleccion de Range- no sirve para el, y hay que saberlo
     aqui, no adivinarlo.                                                   */
  const SEL_CE = "div#contenteditable-root, ytcp-mentionable-textarea [contenteditable='true'], " +
              "ytcp-form-textarea [contenteditable='true'], div[contenteditable='true']";
  const todosCE = [...new Set(document.querySelectorAll(SEL_CE))];
  const visCE = todosCE.filter(visible);
  const todosTA = [...new Set(document.querySelectorAll("textarea"))];
  const visTA = todosTA.filter(visible);

  say("1. CAMPOS DE RESPUESTA");
  say(`   contenteditable: ${todosCE.length} en total, ${visCE.length} visibles`);
  visCE.forEach((f, i) => {
    const r = f.getBoundingClientRect();
    say(`   [ce${i}] ${ident(f)}  ${Math.round(r.width)}x${Math.round(r.height)}` +
        `  ariaHidden=${!!f.closest("[aria-hidden='true']")}` +
        `  texto=${JSON.stringify((f.innerText || "").slice(0, 30))}`);
    say(`        cadena: ${cadena(f)}`);
  });
  say(`   textarea: ${todosTA.length} en total, ${visTA.length} visibles`);
  visTA.forEach((f, i) => {
    const r = f.getBoundingClientRect();
    say(`   [ta${i}] ${ident(f)}  ${Math.round(r.width)}x${Math.round(r.height)}` +
        `  placeholder=${JSON.stringify(f.placeholder || "")}` +
        `  value=${JSON.stringify((f.value || "").slice(0, 30))}`);
    say(`        cadena: ${cadena(f)}`);
  });
  if (!visCE.length && !visTA.length) {
    say("   NINGUNO. Abre a mano un cuadro de respuesta antes de ejecutar esto.");
  } else if (!visCE.length && visTA.length) {
    say("   AVISO IMPORTANTE: no hay ningun contenteditable visible pero SI hay <textarea>.");
    say("   El campo de respuesta de Studio probablemente ya no es un contenteditable.");
  }
  say("");

  /* 2. Botones alrededor del campo ----------------------------------------- */
  const campo = visCE.find((f) => f.id === "contenteditable-root") || visCE[0] || visTA[0];
  const campoEsTextarea = campo && campo.tagName === "TEXTAREA";
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

  /* 6. Botones de reaccion del comentario (me gusta / no me gusta / corazon) -
     Para la funcion de "dar like al publicar". Si no salen aqui, pasa el
     raton por encima de la fila del comentario (algunos solo se muestran al
     hover) y vuelve a ejecutar el script.                                  */
  say("6. BOTONES DE REACCION DEL COMENTARIO (me gusta / no me gusta / corazon / mas)");
  if (campo) {
    const hiloReaccion = campo.closest("ytcp-comment-thread") || campo.closest("ytcp-comment") || campo.closest("ytcp-comment-info");
    if (hiloReaccion) {
      const posibles = [...hiloReaccion.querySelectorAll(
        "ytcp-icon-button, tp-yt-paper-icon-button, ytcp-button, button, tp-yt-paper-button"
      )].filter(visible);
      if (posibles.length) {
        posibles.forEach((b) => {
          const iconEl = b.hasAttribute("icon") ? b : b.querySelector("[icon]");
          say(`   ${ident(b)}`);
          say(`      texto=${JSON.stringify((b.innerText || "").trim().slice(0, 25))}` +
              `  aria=${JSON.stringify(b.getAttribute("aria-label") || "")}` +
              `  title=${JSON.stringify(b.getAttribute("title") || "")}` +
              `  icon=${JSON.stringify(iconEl ? iconEl.getAttribute("icon") : "")}`);
          say(`      ariaPressed=${b.getAttribute("aria-pressed")}` +
              `  cadena: ${cadena(b, 4)}`);
        });
      } else {
        say("   Ninguno visible. Puede que solo aparezcan al pasar el raton por encima");
        say("   del comentario (hover): pasa el cursor por la fila y repite el diagnostico.");
      }
    } else {
      say("   No se ha encontrado el contenedor del comentario.");
    }
  } else {
    say("   (sin campo de referencia, no se puede localizar la fila del comentario)");
  }
  say("");

  /* 7. Prueba de insercion --------------------------------------------------
     Se adapta al tipo de campo detectado en la seccion 1: contenteditable
     (execCommand con seleccion de Range) o textarea (setter nativo del value
     + evento input, que es lo que espera un formulario reactivo de Angular). */
  if (campo) {
    say("7. PRUEBA DE INSERCION (escribe y borra una marca de prueba)");
    const marca = "YRA_PRUEBA_" + Date.now();
    try {
      if (campoEsTextarea) {
        const antes = campo.value || "";
        const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
        campo.focus();
        setter.call(campo, antes + marca);
        campo.dispatchEvent(new Event("input", { bubbles: true }));
        const leido = campo.value || "";
        say(`   campo tratado como <textarea> (setter nativo + evento input)`);
        say(`   el campo contiene la marca: ${leido.includes(marca)}`);
        setter.call(campo, antes);
        campo.dispatchEvent(new Event("input", { bubbles: true }));
        say(`   restaurado a: ${JSON.stringify((campo.value || "").slice(0, 30))}`);
      } else {
        const antes = campo.innerText || "";
        campo.focus();
        const sel = window.getSelection();
        const r = document.createRange();
        r.selectNodeContents(campo);
        sel.removeAllRanges();
        sel.addRange(r);
        const ok = document.execCommand("insertText", false, marca);
        const leido = campo.innerText || "";
        say(`   campo tratado como contenteditable (execCommand)`);
        say(`   execCommand devolvio: ${ok}`);
        say(`   el campo contiene la marca: ${leido.includes(marca)}`);
        const r2 = document.createRange();
        r2.selectNodeContents(campo);
        sel.removeAllRanges();
        sel.addRange(r2);
        document.execCommand("insertText", false, antes);
        say(`   restaurado a: ${JSON.stringify((campo.innerText || "").slice(0, 30))}`);
      }
    } catch (e) {
      say(`   ERROR: ${e.message}`);
    }
  }

  const salida = L.join("\n");
  console.log(salida);
  try { copy(salida); console.log("\n>>> Copiado al portapapeles."); } catch (e) {}
  return "Diagnostico terminado. Revisa la salida de arriba.";
})();
