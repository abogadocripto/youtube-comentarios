/* Banco de pruebas: reproduce el comportamiento observable de YouTube Studio
   (Angular habilita el boton de enviar solo cuando registra el input) y ejecuta
   el content.js real contra el. */

const { JSDOM } = require("jsdom");
const fs = require("fs");

function buildStudio({ rows = 3, angularRegistersInput = true, openDelay = 300, submitStartsEnabled = false, campoExtra = false, soloPuntero = false, clicSinRegistro = false, campoTextarea = false, respuestaPrevia = false, sinBotonLike = false, sinBotonCancelar = false, comentarios = null, sinMiniaturaEn = [], miniaturaFuera = false, url = "https://studio.youtube.com/channel/UCabc/comments/inbox" } = {}) {
  const dom = new JSDOM(
    `<!DOCTYPE html><html><body><div id="app"></div></body></html>`,
    { url, pretendToBeVisual: true, runScripts: "outside-only" }
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
  // `comentarios` permite fijar los textos de las filas (p.ej. para probar
  // comentarios de solo emoticonos o elogios cortos).
  const comments = comentarios || [
    "Muy buenos directos, muchas gracias por compartir tu conocimiento y ayudarnos tanto!",
    "Si pido un prestamo con mis tokens como colateral, ese fiat, no tributa?",
    "Se escucha con un poco de eco. Pero muy bien",
  ];

  // sinMiniaturaEn: filas cuya miniatura aun no tiene src (carga diferida de
  // Studio) y cuyo enlace al video no se ha renderizado. Es el caso real en
  // que la extension se quedaba con el video de OTRA fila.
  const miniatura = (i) => sinMiniaturaEn.includes(i)
    ? `<img data-lazy="1" />`
    : `<a href="https://studio.youtube.com/video/VID${i}0000000/comments">ver</a>
      <img src="https://i.ytimg.com/vi/VID${i}0000000/hq.jpg" />`;

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
      ${miniaturaFuera ? "" : miniatura(i)}
    `;
    // miniaturaFuera reproduce un DOM en el que la miniatura y el enlace del
    // video NO cuelgan del hilo sino de un envoltorio hermano (fila =
    // envoltorio > [hilo, miniatura]). La extension debe aceptar ese
    // envoltorio (no contiene otras filas) y pararse en la lista.
    if (miniaturaFuera) {
      const fila = doc.createElement("div");
      fila.className = "fila-envoltorio";
      fila.appendChild(thread);
      const caja = doc.createElement("div");
      caja.className = "miniatura";
      caja.innerHTML = miniatura(i);
      fila.appendChild(caja);
      app.appendChild(fila);
    } else {
      app.appendChild(thread);
    }

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
        // sinBotonCancelar reproduce un caso real: Studio a veces no expone
        // ningun boton reconocible como "Cancelar" (texto/aria-label distinto,
        // o ausente). El unico cierre posible entonces es la tecla Escape,
        // manejada por Angular en el propio campo o un ancestro suyo -nunca
        // en `document`-, que es justo lo que este modo ejercita.
        const botonCancelar = sinBotonCancelar ? "" : '<ytcp-button class="cancel"><button>Cancelar</button></ytcp-button>';
        box.innerHTML = campoTextarea ? `
          <ytcp-commentbox>
            <textarea id="textarea" placeholder="Añade una respuesta..."></textarea>
          </ytcp-commentbox>
          ${botonCancelar}
          <ytcp-button class="submit-real" ${submitStartsEnabled ? "" : "disabled"}><button>Responder</button></ytcp-button>
        ` : `
          <ytcp-mentionable-textarea>
            ${campoExtra ? '<div class="mention-overlay" contenteditable="true"></div>' : ""}
            <div id="contenteditable-root" contenteditable="true"></div>
          </ytcp-mentionable-textarea>
          ${botonCancelar}
          <ytcp-button class="submit-real" ${submitStartsEnabled ? "" : "disabled"}><button>Responder</button></ytcp-button>
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
        // Ningun modo pone ya id="submit-button": el DOM real confirmado con
        // diagnostico-dom.js nunca lo tiene (hallazgo de revision: el
        // harness en modo contenteditable si lo ponia, asi que la mayoria de
        // pruebas ejercitaban el fast-path por id de buscarBotonEnviar() en
        // vez de la busqueda real por texto/aria-label que usa produccion).
        const submit = box.querySelector(".submit-real");
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
        if (sinBotonCancelar) {
          // Simula el listener real de Angular: atado al CAMPO (o a un
          // ancestro suyo), nunca a `document`. Solo responde a Escape
          // despachado sobre el propio campo (o que burbujee desde el),
          // exactamente como lo haria un usuario real pulsando la tecla.
          field.addEventListener("keydown", (e) => { if (e.key === "Escape") box.remove(); });
        } else {
          box.querySelector(".cancel button").addEventListener("click", () => box.remove());
        }
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
  const payloads = []; // { type, payload } de cada mensaje, para inspeccionar p.ej. el videoId pedido
  window.chrome = {
    runtime: {
      lastError: null,
      sendMessage: (msg, cb) => {
        calls.push(msg.type);
        payloads.push({ type: msg.type, payload: msg.payload });
        if (mudo && mudo.includes(msg.type)) return; // nunca contesta: simula el SW dormido
        setTimeout(() => {
          // `reply` puede ser un string fijo o una funcion (payload) => string,
          // para simular que el modelo responde distinto segun el payload
          // (p.ej. mas breve cuando recibe payload.acortar).
          if (msg.type === "GENERATE_REPLY") {
            const texto = typeof reply === "function" ? reply(msg.payload) : reply;
            cb({ ok: true, reply: texto });
          }
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
  return { calls, payloads, settings };
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
