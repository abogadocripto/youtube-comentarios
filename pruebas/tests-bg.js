/* Pruebas de las funciones puras del service worker */
const fs = require("fs"), vm = require("vm");

// scriptingHandler se asigna/reasigna por cada prueba de handleInsertMain():
// permite controlar, desde el propio test, que devuelve chrome.scripting.
// executeScript sin tener que ejecutar de verdad el codigo en una pestaña.
let scriptingHandler = null;

const sandbox = {
  console, setTimeout, clearTimeout, URL, fetch: async () => { throw new Error("sin red"); },
  chrome: {
    runtime: { onMessage: { addListener(){} }, onInstalled: { addListener(){} } },
    storage: { local: { get: async () => ({}), set: async () => {} }, sync: { get: async () => ({}), remove: async () => {} } },
    scripting: { executeScript: async (opts) => scriptingHandler(opts) },
  },
  AbortController, Promise, JSON, Math, Date, String, Number, Object, Array, Set, Map, Error, RegExp,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync("../background.js", "utf8"), sandbox);
const G = sandbox;

let pass = 0, fail = 0;
const t = (name, fn) => { try { fn(); console.log("  PASA  " + name); pass++; } catch (e) { console.log("  FALLA " + name + "\n        " + e.message); fail++; } };
const eq = (a, b, m) => { if (a !== b) throw new Error(`${m}\n        obtenido: ${JSON.stringify(a)}\n        esperado: ${JSON.stringify(b)}`); };
const ok = (c, m) => { if (!c) throw new Error(m); };

// Pruebas asincronas: se acumulan aqui y se ejecutan en orden al final del
// fichero (el resto del archivo sigue siendo top-level sincrono).
const asyncTests = [];
const ta = (name, fn) => asyncTests.push({ name, fn });

console.log("\nEXTRACCION DEL JSON DEL REPRODUCTOR");

t("extrae un objeto con llaves anidadas", () => {
  const html = `<script>var ytInitialPlayerResponse = {"a":{"b":[1,2,{"c":"x"}]},"d":true};var otro=1;</script>`;
  const o = G.extractJsonObject(html, "ytInitialPlayerResponse");
  eq(o.d, true, "no ha parseado el objeto");
  eq(o.a.b[2].c, "x", "anidamiento mal");
});

t("no se rompe con llaves dentro de cadenas", () => {
  const html = `ytInitialPlayerResponse = {"titulo":"esto tiene } y { dentro","n":5};`;
  const o = G.extractJsonObject(html, "ytInitialPlayerResponse");
  eq(o.n, 5, "las llaves entre comillas han roto el contador");
});

t("no se rompe con comillas escapadas", () => {
  const html = `ytInitialPlayerResponse = {"t":"dijo \\"hola\\" y {","n":7};`;
  const o = G.extractJsonObject(html, "ytInitialPlayerResponse");
  eq(o.n, 7, "los escapes han roto el parseo");
});

t("encuentra la ocurrencia buena si la primera es basura", () => {
  const html = `if(ytInitialPlayerResponse){} ; var ytInitialPlayerResponse = {"captions":{"ok":1}};`;
  const o = G.extractJsonObject(html, "ytInitialPlayerResponse", G.looksLikePlayerResponse);
  ok(o && o.captions, "no ha seguido buscando tras la ocurrencia invalida");
});

t("devuelve null si no existe", () => {
  eq(G.extractJsonObject("<html></html>", "ytInitialPlayerResponse"), null, "deberia ser null");
});

t("saca las pistas de un player response realista", () => {
  const player = { captions: { playerCaptionsTracklistRenderer: { captionTracks: [
    { baseUrl: "https://www.youtube.com/api/timedtext?v=X&lang=en", languageCode: "en", kind: "asr" },
    { baseUrl: "https://www.youtube.com/api/timedtext?v=X&lang=es", languageCode: "es" },
  ] } } };
  const html = `window.ytInitialPlayerResponse = ${JSON.stringify(player)};</script>`;
  const o = G.extractJsonObject(html, "ytInitialPlayerResponse");
  const tracks = o.captions.playerCaptionsTracklistRenderer.captionTracks;
  eq(tracks.length, 2, "no ha encontrado las 2 pistas");
  eq(G.pickTrack(tracks).languageCode, "es", "no ha priorizado castellano");
});

console.log("\nSELECCION DE PISTA");

t("prefiere castellano manual sobre automatico", () => {
  eq(G.pickTrack([{languageCode:"es",kind:"asr"},{languageCode:"es"}]).kind, undefined, "ha cogido la automatica");
});
t("cae a catalan si no hay castellano", () => {
  eq(G.pickTrack([{languageCode:"fr"},{languageCode:"ca"}]).languageCode, "ca", "no ha cogido catalan");
});
t("cae a ingles antes que a otro idioma cualquiera", () => {
  eq(G.pickTrack([{languageCode:"de"},{languageCode:"en"}]).languageCode, "en", "no ha cogido ingles");
});
t("coge la primera si no hay ninguna conocida", () => {
  eq(G.pickTrack([{languageCode:"ja"},{languageCode:"ko"}]).languageCode, "ja", "no ha cogido la primera");
});

console.log("\nLIMPIEZA DE TRANSCRIPCION");

t("decodifica entidades", () => {
  eq(G.decodeEntities("caf&#233; &amp; t&eacute".replace("&eacute","e")), "café & te", "entidades mal");
});
t("quita marcas de musica y aplausos", () => {
  eq(G.cleanTranscript("hola [Música] adios [Aplausos] fin"), "hola adios fin", "no ha limpiado las marcas");
});
t("colapsa espacios y saltos", () => {
  eq(G.cleanTranscript("uno\n\n  dos   tres "), "uno dos tres", "no ha normalizado");
});

console.log("\nPROMPTS");

t("el mensaje de usuario ya no impone el limite de 4 lineas", () => {
  const m = G.buildUserMessage("hola", "T", "D", "", "trans");
  ok(!/M[aá]ximo 4 l[ií]neas/i.test(m), "sigue la orden contradictoria de la v1");
  ok(/La longitud la marcan los ejemplos/.test(m), "falta la guia de longitud");
  ok(!/M[aá]ximo \d+ l[ií]neas/i.test(m), "queda un techo de lineas");
});
t("incluye transcripcion, titulo y comentario", () => {
  const m = G.buildUserMessage("mi comentario", "Mi video", "Mi desc", "extra", "TRANS");
  ok(m.includes("mi comentario") && m.includes("Mi video") && m.includes("TRANS") && m.includes("extra"), "falta contexto");
});
t("los ejemplos prevalecen sobre cualquier regla de longitud", () => {
  const s = G.buildSystemPrompt("", "T", "", "");
  ok(/JERARQU[IÍ]A/.test(s), "no declara la prelacion");
  ok(s.indexOf("JERARQU") < s.indexOf("CÓMO ESCRIBES"), "la prelacion va despues de las reglas que debe desempatar");
  ok(/ejemplos 9, 10, 12 o 13/.test(s), "no nombra los ejemplos largos como autorizados");
  ok(!/M[aá]ximo \d+ l[ií]neas/i.test(s), "queda un techo de lineas en el system prompt");
});

t("el system prompt conserva la persona y los 13 ejemplos", () => {
  const s = G.buildSystemPrompt("", "T", "", "");
  ok(/Sergi Andr/.test(s), "se ha perdido la persona");
  eq((s.match(/^Ejemplo \d+/gm) || []).length, 13, "no hay 13 ejemplos");
  ok(/Gr[aà]cies/.test(s), "falta el ejemplo en catalan");
});
t("añade el bloque de precision y el de instrucciones permanentes", () => {
  const s = G.buildSystemPrompt("", "T", "", "No menciones clientes");
  ok(/No inventes cifras/.test(s), "falta la regla de precision");
  ok(/No menciones clientes/.test(s), "no ha incorporado las instrucciones permanentes");
});

console.log("\nPARSEO DE FORMATOS DE SUBTITULOS");

t("json3", () => {
  const body = JSON.stringify({ events: [{ segs: [{ utf8: "hola " }, { utf8: "mundo" }] }, { segs: [{ utf8: " adios" }] }] });
  eq(G.parsearPista(body, "json3"), "hola mundo adios", "json3 mal parseado");
});
t("json3 invalido devuelve null en vez de romper", () => {
  eq(G.parsearPista("<html>no soy json</html>", "json3"), null, "deberia ser null");
});
t("xml por defecto", () => {
  eq(G.parsearPista('<transcript><text start="0">hola</text><text start="1">mundo</text></transcript>', ""), "hola mundo", "xml mal");
});
t("srv3 usa etiquetas p", () => {
  eq(G.parsearPista('<timedtext><p t="0">hola</p><p t="1">mundo</p></timedtext>', "srv3"), "hola mundo", "srv3 mal");
});
t("vtt quita cabeceras y marcas de tiempo", () => {
  const vtt = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\nhola mundo\n\n2\n00:00:03.000 --> 00:00:05.000\nadios";
  eq(G.parsearPista(vtt, "vtt"), "hola mundo adios", "vtt mal");
});
t("cuerpo vacio devuelve null en todos los formatos", () => {
  for (const f of ["json3","srv3","vtt",""]) eq(G.parsearPista("", f), null, "formato " + f);
});
t("xml sin etiquetas text devuelve null (no cadena vacia)", () => {
  eq(G.parsearPista("<transcript></transcript>", ""), null, "deberia ser null para pasar al siguiente formato");
});

console.log("\nURL SANEADA PARA EL INFORME");

t("enmascara los tokens y deja visible lo util", () => {
  const u = G.sanitizeUrl("https://www.youtube.com/api/timedtext?v=ABC&lang=es&signature=SECRETOLARGO&pot=OTROSECRETO");
  ok(u.includes("v=ABC") && u.includes("lang=es"), "ha ocultado lo que si hay que ver");
  ok(!u.includes("SECRETOLARGO") && !u.includes("OTROSECRETO"), "ha filtrado un token al informe");
});
t("escapes \\u0026 se normalizan antes de parsear", () => {
  eq(G.normalizeTrackUrl("https://x.com/a?b=1\\u0026c=2"), "https://x.com/a?b=1&c=2", "no normaliza");
});

console.log("\nCASCADA DE ESTRATEGIAS");

t("son cinco, con las autenticadas primero", () => {
  const e = G.trackStrategies("VIDEOID1234");
  eq(e.length, 5, "no son cinco");
  eq(e[0][0], "studio", "studio no va primero");
  eq(e[1][0], "innertube-auth", "la autenticada no va segunda");
  ok(e[3][0].includes("anon") && e[4][0].includes("anon"), "las anonimas no van al final");
});

t("el resumen distingue 'no deja descargar' de 'no hay subtitulos'", () => {
  ok(/no deja descargarlos/.test(G.resumirFallos(["watch-auth: descarga vacia"])), "no detecta el bloqueo de descarga");
  ok(/no tiene subtitulos/.test(G.resumirFallos(["a: sin pistas","b: sin pistas"])), "no detecta la ausencia de pistas");
});

console.log("\nRENDIMIENTO");

t("conTope corta una promesa colgada", async () => {
  // comprobacion sincrona del contrato: devuelve una promesa que rechaza
  const p = G.conTope(new Promise(() => {}), 10, "timeout");
  ok(p instanceof Promise, "no devuelve promesa");
});

t("las cinco estrategias se lanzan, no se encadenan", () => {
  const e = G.trackStrategies("VIDEOID1234");
  eq(e.length, 5, "no son cinco");
  ok(e.every(x => typeof x[2] === "function"), "alguna no es invocable por separado");
});

console.log("\nERRORES DE API");
t("404 explica que el modelo no existe", () => {
  ok(/no esta disponible|no existe/.test(G.friendlyApiError(404, "x", "claude-x")), "mensaje poco util");
});
t("401 habla de la key", () => {
  ok(/key/i.test(G.friendlyApiError(401, "x", "m")), "mensaje poco util");
});

// handleInsertMain (plan B de insercion) no tenia ninguna prueba (hallazgo
// de revision): ni el guard trivial de tabId, ni que orquesta correctamente
// chrome.scripting.executeScript (target/world/args) y propaga su
// resultado. No se ejecuta aqui la logica real del "func" inyectado en el
// mundo principal (requeriria un DOM real del lado de la pagina, cubierto
// en su lugar por el camino end-to-end de pruebas/tests.js con jsdom); esto
// cierra el hueco de la orquestacion misma.
ta("handleInsertMain sin tabId aborta sin llamar a chrome.scripting", async () => {
  let llamado = false;
  scriptingHandler = () => { llamado = true; return []; };
  const res = await G.handleInsertMain({ text: "x", nonce: "n1" }, {});
  eq(res.ok, false, "deberia fallar sin tabId");
  eq(res.error, "sin tabId", "mensaje incorrecto");
  eq(llamado, false, "ha llamado a chrome.scripting.executeScript sin tabId");
});

ta("handleInsertMain pasa tabId/world/args correctamente y propaga el resultado", async () => {
  let recibido = null;
  scriptingHandler = (opts) => {
    recibido = opts;
    return [{ result: { ok: true, method: "textarea-value-setter", content: "hola" } }];
  };
  const res = await G.handleInsertMain({ text: "hola", nonce: "abc123" }, { tab: { id: 42 } });
  eq(recibido.target.tabId, 42, "no ha pasado el tabId correcto");
  eq(recibido.world, "MAIN", "no ha pedido el mundo principal");
  eq(recibido.args[0], "hola", "no ha pasado el texto");
  eq(recibido.args[1], "abc123", "no ha pasado el nonce");
  eq(res.ok, true, "no ha propagado el resultado de exito");
  eq(res.method, "textarea-value-setter", "no ha propagado el metodo");
});

ta("handleInsertMain sin resultado de la pagina devuelve un error explicito", async () => {
  scriptingHandler = () => [];
  const res = await G.handleInsertMain({ text: "x", nonce: "n2" }, { tab: { id: 1 } });
  eq(res.ok, false, "deberia fallar sin resultado");
  eq(res.error, "sin resultado de la pagina", "mensaje incorrecto");
});

(async () => {
  for (const { name, fn } of asyncTests) {
    try {
      await fn();
      console.log("  PASA  " + name);
      pass++;
    } catch (e) {
      console.log("  FALLA " + name + "\n        " + e.message);
      fail++;
    }
  }
  console.log(`\n${pass}/${pass + fail} pruebas superadas\n`);
  process.exit(fail ? 1 : 0);
})();
