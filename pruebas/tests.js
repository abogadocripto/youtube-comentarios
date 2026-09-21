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

  await T("fuga del prompt: descarta la respuesta", { mock: { reply: "COMENTARIO A RESPONDER: hola" } }, async ({ wait, $$ }) => {
    await wait(600);
    const t = $$("ytcp-comment-thread")[0];
    t.querySelector(".yra2-btn").click();
    await wait(2000);
    assert(!t.dataset.published, "ha publicado una fuga del prompt");
  });

  await T("muletilla prohibida: pasa a revision en vez de publicar", { mock: { reply: "Excelente pregunta, mira..." } }, async ({ wait, $$ }) => {
    await wait(600);
    const t = $$("ytcp-comment-thread")[0];
    t.querySelector(".yra2-btn").click();
    await wait(2500);
    assert(!t.dataset.published, "ha publicado con muletilla prohibida");
    assert($$(".yra2-panel").length === 1, "no ha abierto el panel");
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

  await T("cerrojo: dos clics simultaneos solo ejecutan un flujo", {}, async ({ wait, $$ }) => {
    await wait(600);
    const threads = $$("ytcp-comment-thread");
    threads[0].querySelector(".yra2-btn").click();
    threads[1].querySelector(".yra2-btn").click();
    await wait(3000);
    const publicadas = threads.filter((t) => t.dataset.published).length;
    assert(publicadas <= 1, `se han publicado ${publicadas} respuestas a la vez`);
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
    async ({ wait, $$, $ }) => {
      await wait(600);
      $$("ytcp-comment-thread")[0].querySelector(".yra2-btn").click();
      await wait(2500);
      const panel = $(".yra2-panel");
      $(".yra2-panel [data-act='publish']").click();
      await wait(400);
      assert(panel.style.visibility !== "hidden", "ha ocultado el panel mientras publica");
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
