/* Banco de pruebas: reproduce el comportamiento observable de YouTube Studio
   (Angular habilita el boton de enviar solo cuando registra el input) y ejecuta
   el content.js real contra el. */

const { JSDOM } = require("jsdom");
const fs = require("fs");

function buildStudio({ rows = 3, angularRegistersInput = true, openDelay = 300, submitStartsEnabled = false, campoExtra = false, soloPuntero = false, clicSinRegistro = false, campoTextarea = false, respuestaPrevia = false, sinBotonLike = false } = {}) {
  const dom = new JSDOM(
    `<!DOCTYPE html><html><body><div id="app"></div></body></html>`,
    { url: "https://studio.youtube.com/channel/UCabc/comments/inbox", pretendToBeVisual: true, runScripts: "outside-only" }
  );
  const { window } = dom;
  const doc = window.document;

  // jsdom no hace layout: todo mediria 0x0 y isVisible() lo descartaria.
  window.Element.prototype.getBoundingClientRect = function () {
    if (this.hasAttribute("data-invisible")) return { width: 0, height: 0, top: 0, left: 0, bottom: 0, right: 0 };
    return { width: 200, height: 40, top: 10, left: 10, bottom: 50, right: 210 };
  };
  Object.defineProperty(window.HTMLElement.prototype, "offsetHeight", { get() { return this.hasAttribute("data-invisible") ? 0 : 60; }, configurable: true });

  // execCommand no existe en jsdom. Reproducimos lo esencial: opera sobre el
  // elemento con foco y emite un evento input, que es lo que dispara Angular.
  doc.execCommand = (cmd, ui, value) => {
    const el = doc.activeElement;
    if (!el || el.getAttribute("contenteditable") !== "true") return false;
    if (cmd === "delete") { el.textContent = ""; }
    else if (cmd === "insertText") { el.textContent = (el.textContent || "") + value; }
    else if (cmd === "selectAll") { /* no-op */ }
    else return false;
    if (angularRegistersInput) el.dispatchEvent(new window.Event("input", { bubbles: true }));
    return true;
  };

  const app = doc.getElementById("app");
  const comments = [
    "Muy buenos directos, muchas gracias por compartir tu conocimiento y ayudarnos tanto!",
    "Si pido un prestamo con mis tokens como colateral, ese fiat, no tributa?",
    "Se escucha con un poco de eco. Pero muy bien",
  ];

  for (let i = 0; i < rows; i++) {
    const thread = doc.createElement("ytcp-comment-thread");
    thread.dataset.row = String(i);
    thread.setAttribute("comment-id", `Ugx-comment-${i}`);
    thread.innerHTML = `
      <ytcp-comment-info>
        <div id="content-text">${comments[i % comments.length]}</div>
      </ytcp-comment-info>
      <div class="comment-actions">
        <ytcp-button class="open-reply"><button>Responder</button></ytcp-button>
        <span class="video-title">Europa quiere PROHIBIR las wallets</span>
        ${sinBotonLike ? "" : '<ytcp-icon-button class="like-btn" aria-label="Me gusta"><button></button></ytcp-icon-button>'}
      </div>
      ${respuestaPrevia ? `
      <div class="existing-reply">
        <div id="content-text">Una respuesta que ya publique hace tiempo, gracias por preguntar!</div>
        <div class="comment-actions">
          <ytcp-button class="open-reply-existing"><button>Responder</button></ytcp-button>
        </div>
      </div>` : ""}
      <a href="https://studio.youtube.com/video/VID${i}0000000/comments">ver</a>
      <img src="https://i.ytimg.com/vi/VID${i}0000000/hq.jpg" />
    `;
    app.appendChild(thread);

    thread.querySelector(".like-btn button")?.addEventListener("click", () => {
      thread.dataset.liked = "1";
    });

    // Al pulsar Responder, Studio monta la caja: campo + Cancelar + Responder
    // (este ultimo deshabilitado hasta que el modelo registra texto).
    const abrir = () => {
      if (thread.querySelector(".reply-box")) return;
      setTimeout(() => {
        const box = doc.createElement("div");
        box.className = "reply-box";
        // campoTextarea reproduce el DOM real confirmado con diagnostico-dom.js:
        // un <textarea> dentro de ytcp-commentbox, no un contenteditable. El
        // boton de enviar real NO lleva id="submit-button" (solo texto
        // "Responder"), asi que aqui tampoco se le pone: hay que ejercitar
        // la misma ruta de busqueda por texto que usara la extension real.
        box.innerHTML = campoTextarea ? `
          <ytcp-commentbox>
            <textarea id="textarea" placeholder="Añade una respuesta..."></textarea>
          </ytcp-commentbox>
          <ytcp-button class="cancel"><button>Cancelar</button></ytcp-button>
          <ytcp-button class="submit-real" ${submitStartsEnabled ? "" : "disabled"}><button>Responder</button></ytcp-button>
        ` : `
          <ytcp-mentionable-textarea>
            ${campoExtra ? '<div class="mention-overlay" contenteditable="true"></div>' : ""}
            <div id="contenteditable-root" contenteditable="true"></div>
          </ytcp-mentionable-textarea>
          <ytcp-button class="cancel"><button>Cancelar</button></ytcp-button>
          <ytcp-button id="submit-button" ${submitStartsEnabled ? "" : "disabled"}><button>Responder</button></ytcp-button>
        `;
        // La caja de respuesta se inserta pegada al comentario principal
        // (justo despues de su barra de acciones), no al final del hilo:
        // asi es como se ve en Studio real. Con respuestaPrevia:true, esto
        // deja el boton "Responder" sin pulsar de la respuesta YA publicada
        // despues del campo nuevo en el orden del documento -exactamente el
        // escenario del hallazgo de revision sobre findSubmitButton().
        const anclaje = thread.querySelector(".comment-actions");
        anclaje.after(box);
        const field = campoTextarea ? box.querySelector("textarea") : box.querySelector("#contenteditable-root");
        const submit = campoTextarea ? box.querySelector(".submit-real") : box.querySelector("#submit-button");
        const valorCampo = () => (campoTextarea ? field.value : field.textContent) || "";

        field.addEventListener("input", () => {
          // En modo contenteditable, angularRegistersInput ya se aplica en el
          // mock de execCommand (el evento ni se dispara). En modo textarea
          // nuestro propio codigo SI dispara el evento 'input' siempre, asi
          // que aqui se reproduce "el framework no lo registra" ignorandolo.
          if (!angularRegistersInput) return;
          if (valorCampo().trim()) submit.removeAttribute("disabled");
          else submit.setAttribute("disabled", "");
        });
        submit.querySelector("button").addEventListener("click", () => {
          if (submit.hasAttribute("disabled")) return;
          if (clicSinRegistro) {
            // Simula un fallo silencioso de Studio: el clic vacia el campo
            // (por ejemplo, un repintado de Angular) pero no publica nada de
            // verdad. La caja sigue ahi, y el boton de enviar sigue
            // conectado, visible y habilitado: nada lo deshabilita, porque
            // no hay ninguna publicacion real en curso.
            if (campoTextarea) field.value = ""; else field.textContent = "";
            return;
          }
          thread.dataset.published = valorCampo();
          box.remove();
        });
        box.querySelector(".cancel button").addEventListener("click", () => box.remove());
      }, openDelay);
    };
    // soloPuntero reproduce los componentes de Studio que reaccionan al gesto
    // (mousedown) y no al click suelto.
    thread.querySelector(".open-reply").addEventListener(soloPuntero ? "mousedown" : "click", abrir);
  }

  return { dom, window, doc };
}

function installChromeMock(window, { reply, transcriptOk = true, cfg = {}, mudo = null, apiKeyMissing = false }) {
  const settings = {
    apiKey: apiKeyMissing ? "" : "sk-ant-test", model: "claude-sonnet-4-6", extendedThinking: true,
    extraContext: "", customInstructions: "", mode: "auto", countdown: 0,
    requireTranscript: true, debug: false, ...cfg,
  };
  const calls = [];
  window.chrome = {
    runtime: {
      lastError: null,
      sendMessage: (msg, cb) => {
        calls.push(msg.type);
        if (mudo && mudo.includes(msg.type)) return; // nunca contesta: simula el SW dormido
        setTimeout(() => {
          if (msg.type === "GENERATE_REPLY") cb({ ok: true, reply });
          else if (msg.type === "FETCH_TRANSCRIPT")
            cb(transcriptOk ? { ok: true, text: "transcripcion simulada ".repeat(40), source: "watch" }
                            : { ok: false, reason: "el video no expone pistas de subtitulos" });
          else if (msg.type === "INSERT_MAIN") cb({ ok: false, error: "no disponible en el banco" });
          // El content script real ya no pide la key en si (ver DEFAULTS de
          // content.js): solo comprueba su presencia con este mensaje.
          else if (msg.type === "HAS_API_KEY") cb({ ok: true, has: !!settings.apiKey });
          else cb({ ok: true });
        }, 10);
      },
    },
    storage: {
      local: { get: (d, cb) => cb({ ...d, ...settings }) },
      onChanged: { addListener: () => {} },
    },
  };
  window.navigator.clipboard = { writeText: async () => {} };
  return { calls, settings };
}

async function run(name, opts, assertions) {
  const { window, doc } = buildStudio(opts.studio || {});
  const mock = installChromeMock(window, opts.mock || { reply: "Respuesta de prueba." });
  const code = fs.readFileSync("../content.js", "utf8");
  window.eval(code);

  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const ctx = { window, doc, wait, mock, $: (s) => doc.querySelector(s), $$: (s) => [...doc.querySelectorAll(s)] };

  try {
    await assertions(ctx);
    console.log(`  PASA  ${name}`);
    return true;
  } catch (e) {
    console.log(`  FALLA ${name}\n        ${e.message}`);
    return false;
  } finally {
    window.close();
  }
}

module.exports = { run, buildStudio, installChromeMock };
