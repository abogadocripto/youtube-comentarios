const { run } = require("./harness");

const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
const results = [];
const T = async (...a) => results.push(await run(...a));

(async () => {
  console.log("\nINYECCION DEL BOTON");

  await T("inyecta exactamente un boton por fila de comentario", {}, async ({ wait, $$ }) => {
    await wait(600);
    const btns = $$(".yra2-btn");
    assert(btns.length === 3, `esperaba 3 botones, hay ${btns.length}`);
    const threads = $$("ytcp-comment-thread");
    threads.forEach((t, i) => assert(t.querySelectorAll(".yra2-btn").length === 1, `fila ${i} tiene ${t.querySelectorAll(".yra2-btn").length} botones`));
  });

  await T("no duplica botones al repetirse el escaneo", {}, async ({ wait, $$, doc }) => {
    await wait(400);
    // Provocar mutaciones que disparen el observer varias veces
    for (let i = 0; i < 4; i++) { doc.body.appendChild(doc.createElement("span")); await wait(400); }
    await wait(3000);
    assert($$(".yra2-btn").length === 3, `se han duplicado: ${$$(".yra2-btn").length}`);
  });

  console.log("\nCAMINO FELIZ");

  await T("un clic publica la respuesta en la fila correcta", {}, async ({ wait, $$, doc }) => {
    await wait(600);
    const threads = $$("ytcp-comment-thread");
    const target = threads[1];
    target.querySelector(".yra2-btn").click();
    await wait(2500);
    assert(target.dataset.published, "la fila objetivo no ha publicado nada");
    assert(target.dataset.published === "Respuesta de prueba.", `texto publicado: "${target.dataset.published}"`);
    assert(!threads[0].dataset.published && !threads[2].dataset.published, "ha publicado en otra fila tambien");
  });

  await T("la ventana de escape publica al agotarse", { mock: { reply: "Con margen.", cfg: { countdown: 2 } } }, async ({ wait, $$ }) => {
    await wait(600);
    const t = $$("ytcp-comment-thread")[0];
    t.querySelector(".yra2-btn").click();
    await wait(1200);
    assert($$(".yra2-countdown").length === 1, "no ha aparecido la cuenta atras");
    assert(!t.dataset.published, "ha publicado antes de agotar la cuenta atras");
    await wait(3000);
    assert(t.dataset.published === "Con margen.", "no ha publicado al agotarse la cuenta");
  });

  await T("Cancelar en la cuenta atras impide la publicacion", { mock: { reply: "No debe salir.", cfg: { countdown: 5 } } }, async ({ wait, $$, $ }) => {
    await wait(600);
    const t = $$("ytcp-comment-thread")[0];
    t.querySelector(".yra2-btn").click();
    await wait(1200);
    $(".yra2-countdown [data-cd='cancel']").click();
    await wait(2500);
    assert(!t.dataset.published, "ha publicado pese a cancelar");
    assert($$(".yra2-panel").length === 1, "no ha dejado el panel con el texto");
  });

  console.log("\nSALVAGUARDAS");

  await T("sin transcripcion no publica sola: abre el panel", { mock: { reply: "Texto.", transcriptOk: false } }, async ({ wait, $$ }) => {
    await wait(600);
    const t = $$("ytcp-comment-thread")[0];
    t.querySelector(".yra2-btn").click();
    await wait(2500);
    assert(!t.dataset.published, "ha publicado sin transcripcion");
    assert($$(".yra2-panel").length === 1, "no ha abierto el panel de revision");
  });

  await T("con requireTranscript desactivado si publica sin transcripcion",
    { mock: { reply: "Texto.", transcriptOk: false, cfg: { requireTranscript: false } } },
    async ({ wait, $$ }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(2500);
      assert(t.dataset.published === "Texto.", "deberia haber publicado");
    });

  await T("modo revision nunca publica solo", { mock: { reply: "Texto.", cfg: { mode: "review" } } }, async ({ wait, $$ }) => {
    await wait(600);
    const t = $$("ytcp-comment-thread")[0];
    t.querySelector(".yra2-btn").click();
    await wait(2500);
    assert(!t.dataset.published, "ha publicado en modo revision");
    assert($$(".yra2-panel").length === 1, "no ha abierto el panel");
  });

  await T("si Angular NO registra el texto, aborta sin publicar",
    { studio: { angularRegistersInput: false }, mock: { reply: "Texto que no cuaja." } },
    async ({ wait, $$ }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(9000);
      assert(!t.dataset.published, "ha publicado con el boton deshabilitado");
      assert($$(".yra2-panel").length === 1, "no ha dejado el texto en el panel");
    });

  await T("respuesta vacia de la API: nunca abre la caja", { mock: { reply: "   " } }, async ({ wait, $$ }) => {
    await wait(600);
    const t = $$("ytcp-comment-thread")[0];
    t.querySelector(".yra2-btn").click();
    await wait(2000);
    assert(!t.dataset.published, "ha publicado vacio");
    assert(!t.querySelector(".reply-box"), "ha abierto la caja pese a no tener texto");
  });

  await T("fuga del prompt que el modelo nunca corrige: se rinde tras los reintentos y descarta la respuesta",
    // El mock devuelve siempre la misma fuga (no coopera con el aviso de
    // evitarFuga), asi que se agotan los 2 reintentos automaticos antes de
    // rendirse: 1 generacion inicial + 2 reintentos = 3 llamadas en total.
    { mock: { reply: "COMENTARIO A RESPONDER: hola" } },
    async ({ wait, $$, mock }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(2500);
      assert(!t.dataset.published, "ha publicado una fuga del prompt");
      const llamadas = mock.calls.filter((c) => c === "GENERATE_REPLY").length;
      assert(llamadas === 3, `deberia haber intentado 1 generacion + 2 reintentos de fuga (3 en total), hizo ${llamadas}`);
    });

  await T("fuga del prompt que el modelo SI corrige al pedirselo: se publica sin pasar por revision",
    { mock: { reply: (payload) => payload.evitarFuga
        ? "Respuesta limpia tras el aviso de evitar la fuga."
        : "COMENTARIO A RESPONDER: hola" } },
    async ({ wait, $$ }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(2500);
      assert(t.dataset.published === "Respuesta limpia tras el aviso de evitar la fuga.", `no ha publicado la version corregida: "${t.dataset.published}"`);
      assert($$(".yra2-panel").length === 0, "ha abierto el panel pese a que el reintento si corrigio la fuga");
    });

  await T("muletilla prohibida: pasa a revision en vez de publicar", { mock: { reply: "Excelente pregunta, mira..." } }, async ({ wait, $$ }) => {
    await wait(600);
    const t = $$("ytcp-comment-thread")[0];
    t.querySelector(".yra2-btn").click();
    await wait(2500);
    assert(!t.dataset.published, "ha publicado con muletilla prohibida");
    assert($$(".yra2-panel").length === 1, "no ha abierto el panel");
  });

  await T("respuesta desproporcionada que el modelo nunca corrige: se rinde tras los reintentos y pasa a revision",
    // El comentario de la fila 0 mide 84 caracteres (tope duro = 84*2 = 168).
    // Esta respuesta mide ~584: por encima del tope de proporcion pero muy
    // por debajo de los 2000 caracteres del otro chequeo de longitud
    // absoluta, para aislar el nuevo chequeo del ya existente. El mock
    // devuelve siempre lo mismo (no coopera con el aviso de acortar), asi
    // que se agotan los 2 reintentos automaticos antes de rendirse.
    { mock: { reply: () => "Esta es una frase neutra de relleno para la prueba automatizada. ".repeat(9) } },
    async ({ wait, $$, $, mock }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(3000);
      assert(!t.dataset.published, "ha publicado una respuesta desproporcionada");
      assert($$(".yra2-panel").length === 1, "no ha abierto el panel");
      // El panel se ancla a document.body, no dentro de la fila del hilo.
      const motivo = $(".yra2-why")?.textContent || "";
      assert(/desproporcionada/.test(motivo), `el motivo no menciona la desproporcion: "${motivo}"`);
      const llamadas = mock.calls.filter((c) => c === "GENERATE_REPLY").length;
      assert(llamadas === 3, `deberia haber intentado 1 generacion + 2 reintentos de acortado (3 en total), hizo ${llamadas}`);
    });

  await T("respuesta desproporcionada que el modelo SI corrige al pedirselo: se publica sin pasar por revision",
    { mock: { reply: (payload) => payload.acortar
        ? "Respuesta breve tras el aviso de acortar."
        : "Esta es una frase neutra de relleno para la prueba automatizada. ".repeat(9) } },
    async ({ wait, $$ }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(3000);
      assert(t.dataset.published === "Respuesta breve tras el aviso de acortar.", `no ha publicado la version acortada: "${t.dataset.published}"`);
      assert($$(".yra2-panel").length === 0, "ha abierto el panel pese a que el reintento si acorto la respuesta");
    });

  await T("caja vacia abierta en otra fila: la cierra y sigue", {}, async ({ wait, $$ }) => {
    await wait(600);
    const threads = $$("ytcp-comment-thread");
    threads[2].querySelector(".open-reply").click();
    await wait(600);
    threads[0].querySelector(".yra2-btn").click();
    await wait(3000);
    assert(threads[0].dataset.published === "Respuesta de prueba.", "no ha publicado en la fila correcta");
    assert(!threads[2].dataset.published, "ha publicado en la fila equivocada");
  });

  await T("caja vacia abierta en otra fila SIN boton Cancelar: solo Escape puede cerrarla, y lo hace",
    { studio: { sinBotonCancelar: true } },
    async ({ wait, $$ }) => {
      // Caso real reportado: Studio no siempre expone un boton "Cancelar"
      // reconocible. El unico cierre posible es Escape, y antes se
      // despachaba sobre `document` -que nunca llega a un listener atado al
      // campo o a un ancestro suyo, como hace este mock a proposito-. Si
      // closeOpenBoxes() siguiera despachando en document, este test fallaria
      // con el mismo "no se ha podido cerrar" que reporto el usuario.
      await wait(600);
      const threads = $$("ytcp-comment-thread");
      threads[2].querySelector(".open-reply").click();
      await wait(600);
      threads[0].querySelector(".yra2-btn").click();
      await wait(3000);
      assert(threads[0].dataset.published === "Respuesta de prueba.", "no ha publicado en la fila correcta");
      assert(!threads[2].querySelector(".reply-box"), "no ha cerrado la caja vacia sin boton Cancelar (deberia haberla cerrado con Escape)");
      assert(!threads[0].querySelector(".yra2-inline--error"), "ha avisado de conflicto pese a que la caja vacia se cerro");
    });

  await T("caja con texto a medias en otra fila: aborta y no la destruye", {}, async ({ wait, $$ }) => {
    await wait(600);
    const threads = $$("ytcp-comment-thread");
    threads[2].querySelector(".open-reply").click();
    await wait(600);
    const campo = threads[2].querySelector("#contenteditable-root");
    campo.textContent = "borrador que estaba escribiendo a mano";
    threads[0].querySelector(".yra2-btn").click();
    await wait(2500);
    assert(!threads[0].dataset.published && !threads[2].dataset.published, "ha publicado con un borrador abierto");
    assert(campo.textContent === "borrador que estaba escribiendo a mano", "ha destruido el borrador");
    assert(threads[0].querySelector(".yra2-inline--error"), "no ha avisado del conflicto");
  });

  await T("caja con texto a medias en otra fila (campo real <textarea>): aborta y no la destruye",
    { studio: { campoTextarea: true } },
    async ({ wait, $$ }) => {
      // closeOpenBoxes() (salvaguarda 1) solo se probaba en modo
      // contenteditable (test de arriba), que ya no es el campo real
      // (hallazgo de revision): fieldText() lee .value para <textarea> en
      // vez de .innerText/.textContent, es una ruta de lectura distinta.
      await wait(600);
      const threads = $$("ytcp-comment-thread");
      threads[2].querySelector(".open-reply").click();
      await wait(600);
      const campo = threads[2].querySelector("textarea");
      campo.value = "borrador que estaba escribiendo a mano";
      threads[0].querySelector(".yra2-btn").click();
      await wait(2500);
      assert(!threads[0].dataset.published && !threads[2].dataset.published, "ha publicado con un borrador abierto");
      assert(campo.value === "borrador que estaba escribiendo a mano", "ha destruido el borrador del textarea real");
      assert(threads[0].querySelector(".yra2-inline--error"), "no ha avisado del conflicto");
    });

  await T("cerrojo: dos clics simultaneos solo ejecutan un flujo", {}, async ({ wait, $$ }) => {
    await wait(600);
    const threads = $$("ytcp-comment-thread");
    threads[0].querySelector(".yra2-btn").click();
    threads[1].querySelector(".yra2-btn").click();
    await wait(3000);
    const publicadas = threads.filter((t) => t.dataset.published).length;
    // Antes solo se exigia "<= 1": un fallo donde AMBOS clics abortaran en
    // silencio (0 publicadas) pasaba esta prueba igual, sin comprobar que
    // el segundo clic avisa en vez de simplemente perderse (hallazgo de
    // revision: assert tautologico).
    assert(publicadas === 1, `deberia haberse publicado exactamente 1 respuesta, se han publicado ${publicadas}`);
    assert($$(".yra2-toast--warn").length >= 1, "el segundo clic no ha avisado 'Hay una respuesta en curso'");
  });

  console.log("\nREGRESIONES DE LA v2.1.0");

  await T("publicar desde el panel tras bloquearse por falta de transcripcion",
    { mock: { reply: "Texto revisado a mano.", transcriptOk: false } },
    async ({ wait, $$, $ }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(2500);
      assert($$(".yra2-panel").length === 1, "no ha abierto el panel");
      assert(!t.dataset.published, "ha publicado sin revisar");
      $(".yra2-panel [data-act='publish']").click();
      await wait(3000);
      assert(t.dataset.published === "Texto revisado a mano.", `no ha publicado desde el panel: ${$(".yra2-inline--error")?.textContent || "sin error visible"}`);
    });

  await T("el boton Publicar del propio panel no se confunde con el de enviar",
    { mock: { reply: "Texto.", transcriptOk: false } },
    async ({ wait, $$, $ }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(2500);
      $(".yra2-panel [data-act='publish']").click();
      await wait(3000);
      // Si hubiera pulsado su propio boton en vez del de Studio, la fila
      // no tendria nada publicado y el panel seguiria ahi.
      assert(t.dataset.published === "Texto.", "no ha llegado al boton real de Studio");
      assert($$(".yra2-panel").length === 0, "el panel sigue abierto tras publicar");
    });

  await T("caja con dos contenteditable: elige el bueno y publica",
    { studio: { campoExtra: true }, mock: { reply: "Con overlay de menciones." } },
    async ({ wait, $$ }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(3000);
      assert(t.dataset.published === "Con overlay de menciones.", "no ha publicado con dos campos presentes");
    });

  await T("boton que solo reacciona al gesto de puntero, no al click suelto",
    { studio: { soloPuntero: true }, mock: { reply: "Abierto por puntero." } },
    async ({ wait, $$ }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(3000);
      assert(t.dataset.published === "Abierto por puntero.", "no ha abierto la caja con la secuencia de puntero");
    });

  await T("si el proceso de fondo no contesta, avisa en vez de colgarse",
    { mock: { reply: "x", mudo: ["GENERATE_REPLY"] } },
    async ({ wait, $$ }) => {
      await wait(600);
      $$("ytcp-comment-thread")[0].querySelector(".yra2-btn").click();
      // El tope real es de 45 s; aqui solo comprobamos que el boton no se
      // queda bloqueado para siempre y que el cerrojo no se atasca.
      await wait(2000);
      const btn = $$(".yra2-btn")[0];
      assert(btn.disabled, "deberia seguir esperando, no haber terminado ya");
      assert($$(".yra2-panel").length === 0, "no deberia haber panel todavia");
    });

  await T("el panel no se oculta al pulsar Publicar",
    { mock: { reply: "Texto.", transcriptOk: false } },
    async ({ wait, $$, $, doc }) => {
      await wait(600);
      $$("ytcp-comment-thread")[0].querySelector(".yra2-btn").click();
      await wait(2500);
      const panel = $(".yra2-panel");
      $(".yra2-panel [data-act='publish']").click();
      await wait(400);
      // content.js nunca escribe panel.style.visibility: comprobar esa
      // propiedad no detectaria una regresion que hiciera panel.remove() o
      // display:none al pulsar Publicar (hallazgo de revision: assert
      // tautologico). Lo que de verdad hay que confirmar es que el nodo
      // sigue en el documento.
      assert(doc.body.contains(panel), "ha eliminado el panel del DOM mientras publica");
      assert($(".yra2-panel [data-act='copy']").disabled, "no ha bloqueado los botones mientras publica");
    });

  await T("un fallo de publicacion deja aviso flotante, no solo dentro del panel",
    { studio: { angularRegistersInput: false }, mock: { reply: "Texto.", transcriptOk: false } },
    async ({ wait, $$, $ }) => {
      await wait(600);
      $$("ytcp-comment-thread")[0].querySelector(".yra2-btn").click();
      await wait(2500);
      $(".yra2-panel [data-act='publish']").click();
      await wait(9000);
      assert($$(".yra2-toast--err").length === 1, "no ha sacado aviso flotante del error");
      assert(!$(".yra2-panel [data-act='publish']").disabled, "ha dejado el boton bloqueado");
    });

  console.log("\nCAMPO REAL: <textarea> (confirmado con diagnostico-dom.js el 21/09/2026)");

  await T("un clic publica la respuesta cuando el campo es un <textarea>, no un contenteditable",
    { studio: { campoTextarea: true }, mock: { reply: "Respuesta sobre textarea." } },
    async ({ wait, $$ }) => {
      await wait(600);
      const threads = $$("ytcp-comment-thread");
      const target = threads[1];
      target.querySelector(".yra2-btn").click();
      await wait(2500);
      assert(target.dataset.published, "no ha publicado con el campo real (textarea)");
      assert(target.dataset.published === "Respuesta sobre textarea.", `texto publicado: "${target.dataset.published}"`);
      assert(!threads[0].dataset.published && !threads[2].dataset.published, "ha publicado en otra fila tambien");
    });

  await T("con <textarea>, si Angular no registra el input el boton de enviar sigue deshabilitado y aborta",
    { studio: { campoTextarea: true, angularRegistersInput: false }, mock: { reply: "No deberia publicarse." } },
    async ({ wait, $$ }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(9000);
      assert(!t.dataset.published, "ha publicado sin que Angular registrara el texto");
      assert($$(".yra2-panel").length === 1, "no ha dejado el texto disponible en el panel");
    });

  await T("un hilo con una respuesta ya publicada no confunde su 'Responder' sin pulsar con el boton de enviar (hallazgo de review)",
    { studio: { campoTextarea: true, respuestaPrevia: true }, mock: { reply: "Respuesta nueva, no la existente." } },
    async ({ wait, $$ }) => {
      await wait(600);
      const threads = $$("ytcp-comment-thread");
      const target = threads[1];
      target.querySelector(".yra2-btn").click();
      await wait(2500);
      assert(target.dataset.published === "Respuesta nueva, no la existente.", `no ha publicado en el boton correcto: "${target.dataset.published}"`);
    });

  await T("falta la API key: aborta sin haber pedido nunca su valor real al content script",
    { mock: { reply: "No deberia generarse.", apiKeyMissing: true } },
    async ({ wait, $$ }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(1500);
      assert(!t.dataset.published, "ha publicado sin API key");
      assert(t.querySelector(".yra2-inline--error"), "no ha avisado de que falta la API key");
    });

  console.log("\n'ME GUSTA' TRAS PUBLICAR");

  await T("con likeOnPublish activado (por defecto), da 'me gusta' tras publicar",
    {}, async ({ wait, $$ }) => {
      const t = $$("ytcp-comment-thread")[1];
      await wait(600);
      t.querySelector(".yra2-btn").click();
      await wait(2500);
      assert(t.dataset.published === "Respuesta de prueba.", "no ha publicado");
      assert(t.dataset.liked === "1", "no ha dado 'me gusta' tras publicar con el ajuste activado");
    });

  await T("con likeOnPublish desactivado, no toca el boton de me gusta",
    { mock: { reply: "Sin like.", cfg: { likeOnPublish: false } } },
    async ({ wait, $$ }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(2500);
      assert(t.dataset.published === "Sin like.", "no ha publicado");
      assert(!t.dataset.liked, "ha dado 'me gusta' con el ajuste desactivado");
    });

  await T("el 'me gusta' tras publicar desde el panel tambien se intenta",
    { mock: { reply: "Texto.", transcriptOk: false } },
    async ({ wait, $$, $ }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(2500);
      $(".yra2-panel [data-act='publish']").click();
      await wait(3000);
      assert(t.dataset.published === "Texto.", "no ha publicado desde el panel");
      assert(t.dataset.liked === "1", "no ha dado 'me gusta' al publicar desde el panel");
    });

  await T("sin ningun boton de 'me gusta' con confianza suficiente, publica igual y no rompe nada",
    { studio: { sinBotonLike: true }, mock: { reply: "Publicada sin poder dar like." } },
    async ({ wait, $$ }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(2500);
      assert(t.dataset.published === "Publicada sin poder dar like.", "no ha publicado cuando no hay boton de me gusta");
      assert(!t.dataset.liked, "ha marcado 'me gusta' sin que exista boton alguno");
    });

  console.log("\nREGRESIONES 2.2.2 — confirmacion de envio y ruta");

  await T("un vaciado del campo sin publicar de verdad no se confunde con exito (H1)",
    { studio: { clicSinRegistro: true }, mock: { reply: "No deberia darse por publicado." } },
    async ({ wait, $$ }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(9000);
      assert(!t.dataset.published, "ha marcado como publicado sin que Studio lo confirmara realmente");
      assert($$(".yra2-panel").length === 1, "no ha dejado el texto disponible tras el falso positivo");
      // likeComment() solo debe llamarse tras publish():ok:true (hallazgo de
      // revision: sin una prueba explicita, una futura regresion que lo
      // disparara antes de esa confirmacion pasaria desapercibida).
      assert(!t.dataset.liked, "ha dado 'me gusta' pese a que la publicacion no se confirmo");
    });

  await T("un cambio de ruta mientras se publica no borra el panel/cuenta atras en pleno vuelo (H3)",
    { mock: { reply: "Con margen.", cfg: { countdown: 3 } } },
    async ({ wait, $$, window }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(1200);
      assert($$(".yra2-countdown").length === 1, "no ha aparecido la cuenta atras");
      // Cambio de ruta interno mientras el flujo esta en marcha (state.busy).
      window.history.pushState({}, "", "/channel/UCabc/analytics");
      await wait(200);
      assert($$(".yra2-countdown").length === 1, "ha borrado la cuenta atras al cambiar de ruta en pleno envio");
      await wait(3000);
      assert(t.dataset.published === "Con margen.", "no ha completado la publicacion tras el cambio de ruta");
      // Al terminar, la desactivacion aplazada debe aplicarse.
      await wait(200);
      assert($$(".yra2-btn").length === 0, "no ha aplicado la desactivacion aplazada al terminar");
    });

  console.log("\nREGRESIONES 2.2.5 — relectura final tras la cuenta atras");

  await T("si el contenido cambia durante la cuenta atras, no publica el texto mutado (hallazgo de review)",
    { studio: { campoTextarea: true }, mock: { reply: "Texto original verificado.", cfg: { countdown: 2 } } },
    async ({ wait, $$, window }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(1200);
      assert($$(".yra2-countdown").length === 1, "no ha aparecido la cuenta atras");

      // El campo real (textarea) sigue editable durante la cuenta atras: se
      // muta directamente, como haria un repintado de Angular o una edicion
      // manual, sin pulsar "Editar" ni "Cancelar".
      const field = t.querySelector("textarea");
      assert(field, "no se encuentra el campo real (textarea) para mutarlo");
      const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
      setter.call(field, "TEXTO MUTADO DURANTE LA CUENTA ATRAS");
      field.dispatchEvent(new window.Event("input", { bubbles: true }));

      await wait(3000);
      assert(t.dataset.published !== "TEXTO MUTADO DURANTE LA CUENTA ATRAS", "ha publicado el texto mutado en vez del verificado");
      assert(!t.dataset.published, "ha publicado algo cuando el contenido ya no coincidia con lo verificado");
      assert($$(".yra2-panel").length === 1, "no ha dejado el texto original disponible en el panel tras abortar");
    });

  console.log("\nVIDEO DE LA FILA (nunca el de otra fila)");

  await T("pide la transcripcion del video de SU fila (miniatura dentro del hilo)", {}, async ({ wait, $$, mock }) => {
    await wait(600);
    const t = $$("ytcp-comment-thread")[2];
    t.querySelector(".yra2-btn").click();
    await wait(2500);
    const tr = mock.payloads.find((p) => p.type === "FETCH_TRANSCRIPT");
    assert(tr, "no ha pedido la transcripcion");
    assert(tr.payload.videoId === "VID20000000", `ha pedido el video ${tr.payload.videoId}, esperaba VID20000000`);
    assert(t.dataset.published === "Respuesta de prueba.", "no ha publicado en la fila");
  });

  await T("si la miniatura de su fila aun no ha cargado, NO coge el video de la primera fila de la lista",
    { studio: { sinMiniaturaEn: [1] } },
    async ({ wait, $$, mock }) => {
      await wait(600);
      const threads = $$("ytcp-comment-thread");
      threads[1].querySelector(".yra2-btn").click();
      await wait(2500);
      const tr = mock.payloads.find((p) => p.type === "FETCH_TRANSCRIPT");
      assert(!tr, `ha pedido la transcripcion del video ${tr && tr.payload.videoId}: es el de OTRA fila (caso real del 19/10/2026)`);
      // Sin video identificado no hay transcripcion; con requireTranscript
      // (por defecto) eso pasa a revision en vez de publicarse solo.
      assert(!threads[1].dataset.published, "ha publicado sin saber de que video era el comentario");
      assert($$(".yra2-panel").length === 1, "no ha abierto el panel de revision");
      const gen = mock.payloads.find((p) => p.type === "GENERATE_REPLY");
      assert(gen && gen.payload.videoTitle === "Europa quiere PROHIBIR las wallets", "el titulo de la propia fila si debe usarse");
    });

  await T("acepta un envoltorio hermano con la miniatura (fila = envoltorio > hilo + miniatura) y se para en la lista",
    { studio: { miniaturaFuera: true } },
    async ({ wait, $$, mock }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[1];
      t.querySelector(".yra2-btn").click();
      await wait(2500);
      const tr = mock.payloads.find((p) => p.type === "FETCH_TRANSCRIPT");
      assert(tr, "no ha pedido la transcripcion aunque la miniatura esta en el envoltorio de la fila");
      assert(tr.payload.videoId === "VID10000000", `ha pedido ${tr.payload.videoId}, esperaba VID10000000`);
      assert(t.dataset.published === "Respuesta de prueba.", "no ha publicado");
    });

  await T("con envoltorio hermano Y miniatura sin cargar, tampoco coge la de otra fila",
    { studio: { miniaturaFuera: true, sinMiniaturaEn: [2] } },
    async ({ wait, $$, mock }) => {
      await wait(600);
      $$("ytcp-comment-thread")[2].querySelector(".yra2-btn").click();
      await wait(2500);
      const tr = mock.payloads.find((p) => p.type === "FETCH_TRANSCRIPT");
      assert(!tr, `ha pedido el video ${tr && tr.payload.videoId} de otra fila`);
    });

  await T("en la pagina de comentarios de UN video usa el id de la URL como respaldo",
    { studio: { sinMiniaturaEn: [0, 1, 2], url: "https://studio.youtube.com/video/PAGINA00001/comments" } },
    async ({ wait, $$, mock }) => {
      await wait(600);
      $$("ytcp-comment-thread")[1].querySelector(".yra2-btn").click();
      await wait(2500);
      const tr = mock.payloads.find((p) => p.type === "FETCH_TRANSCRIPT");
      assert(tr && tr.payload.videoId === "PAGINA00001", `esperaba PAGINA00001, ha pedido ${tr && tr.payload.videoId}`);
    });

  console.log("\nCOMENTARIOS DE REACCION (emoticono)");

  await T("un comentario de solo emoticonos se responde con el emoticono, sin modelo ni transcripcion",
    { studio: { rows: 1, comentarios: ["👏👏👏"] }, mock: { reply: "NO DEBE USARSE" } },
    async ({ wait, $$, mock }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      assert(t.querySelector(".yra2-btn"), "la fila de solo emoticonos no tiene boton");
      t.querySelector(".yra2-btn").click();
      await wait(2500);
      assert(t.dataset.published === "🤙", `ha publicado "${t.dataset.published}", esperaba 🤙`);
      assert(!mock.calls.includes("GENERATE_REPLY"), "ha llamado al modelo para un comentario de solo emoticonos");
      assert(!mock.calls.includes("FETCH_TRANSCRIPT"), "ha pedido la transcripcion para un comentario de solo emoticonos");
      assert(t.dataset.liked === "1", "no ha dado me gusta");
    });

  await T("«top!» y «Grande Sergi, crack!!» son elogios cortos: emoticono configurado",
    { studio: { rows: 2, comentarios: ["top!", "Grande Sergi, crack!!"] }, mock: { reply: "NO DEBE USARSE", cfg: { emojiReplyText: "🙌" } } },
    async ({ wait, $$, mock }) => {
      await wait(600);
      const threads = $$("ytcp-comment-thread");
      threads[0].querySelector(".yra2-btn").click();
      await wait(2500);
      assert(threads[0].dataset.published === "🙌", `fila 0: "${threads[0].dataset.published}"`);
      threads[1].querySelector(".yra2-btn").click();
      await wait(2500);
      assert(threads[1].dataset.published === "🙌", `fila 1: "${threads[1].dataset.published}"`);
      assert(!mock.calls.includes("GENERATE_REPLY"), "ha llamado al modelo");
    });

  await T("una pregunta o un comentario con palabras que no son de elogio van al modelo como siempre",
    { studio: { rows: 3, comentarios: ["Gracias, ¿y en Andorra?", "muy bueno pero no estoy de acuerdo", "👏 y el modelo 721 que"] } },
    async ({ wait, $$, mock }) => {
      await wait(600);
      const threads = $$("ytcp-comment-thread");
      for (const t of threads) {
        t.querySelector(".yra2-btn").click();
        await wait(2500);
        assert(t.dataset.published === "Respuesta de prueba.", `"${t.querySelector("[id='content-text']").textContent}" -> "${t.dataset.published}"`);
      }
      assert(mock.calls.filter((c) => c === "GENERATE_REPLY").length === 3, "no ha llamado al modelo las tres veces");
    });

  await T("con emojiReply desactivado, los emoticonos van al modelo",
    { studio: { rows: 1, comentarios: ["🔥🔥"] }, mock: { reply: "Del modelo.", cfg: { emojiReply: false } } },
    async ({ wait, $$, mock }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(2500);
      assert(t.dataset.published === "Del modelo.", `ha publicado "${t.dataset.published}"`);
      assert(mock.calls.includes("GENERATE_REPLY"), "no ha llamado al modelo");
    });

  await T("en modo revision, la reaccion abre el panel con el emoticono y no publica sola",
    { studio: { rows: 1, comentarios: ["💪💪"] }, mock: { reply: "NO", cfg: { mode: "review" } } },
    async ({ wait, $$, $ }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(1500);
      assert(!t.dataset.published, "ha publicado en modo revision");
      assert($$(".yra2-panel").length === 1, "no ha abierto el panel");
      assert($(".yra2-panel .yra2-text").value === "🤙", `el panel no lleva el emoticono: "${$(".yra2-panel .yra2-text").value}"`);
    });

  await T("la cuenta atras tambien se aplica al emoticono (se puede cancelar)",
    { studio: { rows: 1, comentarios: ["👍"] }, mock: { reply: "NO", cfg: { countdown: 5 } } },
    async ({ wait, $$, $ }) => {
      await wait(600);
      const t = $$("ytcp-comment-thread")[0];
      t.querySelector(".yra2-btn").click();
      await wait(1200);
      assert($$(".yra2-countdown").length === 1, "no ha aparecido la cuenta atras");
      $(".yra2-countdown [data-cd='cancel']").click();
      await wait(2000);
      assert(!t.dataset.published, "ha publicado pese a cancelar");
    });

  console.log("\nRUTA SPA");

  await T("al salir de /comments retira botones y paneles", {}, async ({ wait, $$, window }) => {
    await wait(600);
    assert($$(".yra2-btn").length === 3, `antes de navegar hay ${$$(".yra2-btn").length} botones, esperaba 3`);
    window.history.pushState({}, "", "/channel/UCabc/analytics");
    await wait(1200);
    assert($$(".yra2-btn").length === 0, "los botones siguen tras salir de comentarios");
  });

  await T("al volver a /comments los repone sin recargar", {}, async ({ wait, $$, window }) => {
    await wait(600);
    window.history.pushState({}, "", "/channel/UCabc/analytics");
    await wait(1000);
    assert($$(".yra2-btn").length === 0, "no se limpio al salir");
    window.history.pushState({}, "", "/channel/UCabc/comments/inbox");
    await wait(1800);
    assert($$(".yra2-btn").length === 3, `al volver hay ${$$(".yra2-btn").length} botones`);
  });

  const ok = results.filter(Boolean).length;
  console.log(`\n${ok}/${results.length} pruebas superadas\n`);
  process.exit(ok === results.length ? 0 : 1);
})();
