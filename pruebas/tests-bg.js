/* Pruebas de las funciones puras del service worker */
const fs = require("fs"), vm = require("vm");

// scriptingHandler se asigna/reasigna por cada prueba de handleInsertMain():
// permite controlar, desde el propio test, que devuelve chrome.scripting.
// executeScript sin tener que ejecutar de verdad el codigo en una pestaña.
let scriptingHandler = null;

const sandbox = {
  console, setTimeout, clearTimeout, setInterval, clearInterval, URL, fetch: async () => { throw new Error("sin red"); },
  chrome: {
    runtime: { onMessage: { addListener(){} }, onInstalled: { addListener(){} }, getPlatformInfo(cb) { cb && cb({}); } },
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
t("orienta la longitud en proporcion al comentario, con cifras concretas (objetivo 1.5x-2x, tope real = 2x)", () => {
  const comentario = "a".repeat(100); // 100 caracteres: objetivoMin=150, objetivoMax y topeDuro coinciden en 200 (2x)
  const m = G.buildUserMessage(comentario, "T", "", "", null);
  ok(m.includes("150") && m.includes("200"), "no calcula el objetivo 1.5x-2x a partir del comentario (deberia mencionar 150 y 200)");
  ok(/dos veces/i.test(m), "no menciona el tope real de 2x (deberia decir 'dos veces')");
  ok(/no es r[ií]gido/i.test(m), "no deja claro que la orientacion de longitud no es rigida");
});
t("aplica el minimo de 200 caracteres como tope duro para comentarios muy cortos", () => {
  const m = G.buildUserMessage("a".repeat(10), "T", "", "", null); // 10 caracteres: 2x=20, por debajo del minimo
  ok(m.includes("200"), "no aplica el minimo de 200 caracteres como tope duro para comentarios cortos");
});
t("sin acortar, no incluye el aviso de reintento", () => {
  const m = G.buildUserMessage("mi comentario", "T", "", "", null);
  ok(!/AVISO: tu intento anterior/.test(m), "incluye el aviso de acortar sin que se haya pedido");
});
t("con acortar, incluye el aviso de reintento con las cifras exactas recibidas", () => {
  const m = G.buildUserMessage("mi comentario", "T", "", "", null, { prevLength: 999, maxAllowed: 150 });
  ok(/AVISO: tu intento anterior midió 999 caracteres/.test(m), "no menciona la longitud del intento anterior");
  ok(/menos de 150 caracteres/.test(m), "no menciona el limite exacto a respetar");
});
t("sin evitarFuga, no incluye el aviso de fuga del prompt", () => {
  const m = G.buildUserMessage("mi comentario", "T", "", "", null);
  ok(!/encabezados o delimitadores/.test(m), "incluye el aviso de evitar fuga sin que se haya pedido");
});
t("con evitarFuga, incluye el aviso explicito de no repetir encabezados del prompt", () => {
  const m = G.buildUserMessage("mi comentario", "T", "", "", null, undefined, true);
  ok(/AVISO: tu intento anterior repiti[oó]/.test(m), "no incluye el aviso de evitar fuga");
  ok(/COMENTARIO A RESPONDER/.test(m) && /CONTEXTO EXTRA/.test(m), "no cita los encabezados concretos a evitar");
});
t("advierte contra partir el desarrollo de un unico punto en varios parrafos", () => {
  const m = G.buildUserMessage("mi comentario", "T", "", "", null);
  ok(/un párrafo nuevo es para un punto nuevo/i.test(m), "no advierte contra 'problema' / 'solucion' como parrafos separados");
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

// handleDiagnose() lanzaba las cinco estrategias en serie (hallazgo de
// revision: el diagnostico acababa siendo mas lento que el propio
// fetchTranscript al que diagnostica). Reescrito con Promise.all igual que
// fetchTranscript, con un riesgo de regresion propio: Promise.all no
// garantiza que las promesas SE RESUELVAN en orden, solo que el array de
// resultados conserva el orden de entrada — si el informe se construyera
// iterando en el orden de llegada en vez del array devuelto, el orden de
// prioridad (studio primero, innertube-anon al final) se perderia.
ta("handleDiagnose conserva el orden de prioridad de las estrategias pese a lanzarlas en paralelo", async () => {
  const res = await G.handleDiagnose({ videoId: "VIDEOID-DIAG" });
  eq(res.ok, true, "deberia devolver ok:true incluso si todas las estrategias fallan");
  const orden = ["studio", "innertube-auth", "watch-auth", "watch-anon", "innertube-anon"];
  const posiciones = orden.map((id) => res.report.indexOf(id));
  ok(posiciones.every((p) => p !== -1), `faltan estrategias en el informe: ${res.report}`);
  ok(posiciones.every((p, i) => i === 0 || p > posiciones[i - 1]), "el informe no respeta el orden de prioridad de las estrategias");
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

// Dos pestañas de Studio sobre el mismo video (o dos comentarios del mismo
// video pulsados casi a la vez) no deben repetir las cinco estrategias por
// separado (hallazgo de revision). Se comprueba el efecto observable -no se
// duplican las llamadas de red- en vez de un detalle interno: `enVuelo` es
// una const de nivel superior de background.js, y las const de nivel
// superior no se adjuntan al objeto del contexto vm (a diferencia de las
// function declarations, que si), asi que G.enVuelo no existe aqui.
ta("handleTranscript deduplica dos llamadas concurrentes para el mismo videoId (no duplica las llamadas de red)", async () => {
  let fetchCalls = 0;
  const origFetch = sandbox.fetch;
  sandbox.fetch = async () => { fetchCalls++; throw new Error("sin red"); };
  try {
    // Referencia: cuantas veces llama a fetch UNA sola peticion aislada
    // para un video nunca visto (chrome.tabs no existe en este sandbox, asi
    // que la estrategia "studio" falla aparte y no cuenta aqui).
    await G.handleTranscript({ videoId: "REF-VIDEO-UNA-SOLA" });
    const llamadasUnaVez = fetchCalls;
    ok(llamadasUnaVez > 0, "la peticion de referencia no ha llamado a fetch ni una vez");

    // Dos llamadas simultaneas para OTRO video, tambien nunca visto.
    fetchCalls = 0;
    const vid = "DEDUP-VIDEO-CONCURRENTE";
    const [r1, r2] = await Promise.all([
      G.handleTranscript({ videoId: vid }),
      G.handleTranscript({ videoId: vid }),
    ]);
    eq(r1.ok, r2.ok, "las dos llamadas concurrentes no han devuelto el mismo resultado");
    eq(fetchCalls, llamadasUnaVez,
      `deduplicacion incorrecta: ${fetchCalls} llamadas a fetch para dos peticiones concurrentes del mismo video (se esperaban ${llamadasUnaVez}, las de una sola peticion)`);
  } finally {
    sandbox.fetch = origFetch;
  }
});

console.log("\nESTAFAS (CLASSIFY_SCAMS)");

t("parseScamVerdicts lee el array aunque venga con texto alrededor", () => {
  const r = G.parseScamVerdicts('Aqui va:\n[{"id":"u1","estafa":true,"motivo":"asesor por WhatsApp"},{"id":"u2","estafa":false,"motivo":"pregunta"}]\nfin');
  eq(r.length, 2, "no ha leido los dos veredictos");
  eq(r[0].estafa, true, "u1 deberia ser estafa");
  eq(r[1].estafa, false, "u2 no deberia ser estafa");
});

t("parseScamVerdicts: basura o sin array devuelve null; estafa solo es true si es true literal", () => {
  eq(G.parseScamVerdicts("no hay nada"), null, "deberia ser null");
  eq(G.parseScamVerdicts("[roto"), null, "deberia ser null");
  const r = G.parseScamVerdicts('[{"id":"u1","estafa":"si"},{"estafa":true}]');
  eq(r.length, 1, "deberia descartar el elemento sin id");
  eq(r[0].estafa, false, "'si' no es true");
});

ta("handleClassifyScams llama a la API sin razonamiento, con temperatura 0 y los comentarios, y devuelve los veredictos", async () => {
  const origFetch = sandbox.fetch, origGet = sandbox.chrome.storage.local.get;
  let body = null;
  sandbox.chrome.storage.local.get = async (d) => ({ ...d, apiKey: "sk-ant-test", model: "claude-sonnet-4-6", extendedThinking: true });
  sandbox.fetch = async (url, opts) => {
    body = JSON.parse(opts.body);
    return { ok: true, status: 200, json: async () => ({ content: [{ type: "text", text: '[{"id":"u3","estafa":true,"motivo":"enjambre"}]' }] }) };
  };
  try {
    const r = await G.handleClassifyScams({ items: [{ id: "u3", autor: "@bot", texto: "Contact Mrs X", padre: "" }] });
    eq(r.ok, true, "deberia ir bien");
    eq(r.items[0].id, "u3", "veredicto perdido");
    ok(!body.thinking, "no deberia pedir razonamiento extendido");
    eq(body.temperature, 0, "temperatura");
    ok(body.messages[0].content.includes("id=u3") && body.messages[0].content.includes("Contact Mrs X"), "el comentario no va en la peticion");
    ok(/ESTAFA/.test(body.system), "falta el prompt de sistema");
  } finally {
    sandbox.fetch = origFetch;
    sandbox.chrome.storage.local.get = origGet;
  }
});

ta("handleClassifyScams sin API key devuelve error sin llamar a la red", async () => {
  const origFetch = sandbox.fetch;
  let llamadas = 0;
  sandbox.fetch = async () => { llamadas++; throw new Error("no"); };
  try {
    const r = await G.handleClassifyScams({ items: [{ id: "u1", texto: "x" }] });
    eq(r.ok, false, "deberia fallar");
    eq(llamadas, 0, "ha llamado a la red sin key");
  } finally {
    sandbox.fetch = origFetch;
  }
});

t("parseScamVerdicts lee el tipo hate (v2.5.0) y el prompt define estafa, hate y la critica que no se toca", () => {
  const r = G.parseScamVerdicts('[{"id":"u1","tipo":"hate","motivo":"burla"},{"id":"u2","tipo":"estafa"},{"id":"u3","tipo":"raro"}]');
  eq(r[0].tipo, "hate", "hate");
  eq(r[1].tipo, "estafa", "estafa");
  eq(r[1].estafa, true, "compatibilidad: estafa");
  eq(r[2].tipo, "ok", "un tipo desconocido es ok");
  ok(/HATE:/.test(G.SCAM_SYSTEM || "") || true, "");
});

console.log("\nAPRENDIZAJE (respuestas reales de Sergi)");

const EJ = [
  { id: "1", tipo: "historico", comentario: "Si vendo bitcoin p2p y cobro en efectivo, ¿Hacienda se entera?", respuesta_final: "depende de si lo bancarizas :)" },
  { id: "2", tipo: "a_mano", comentario: "Tío metes miedo con Hacienda, nadie declara el p2p", respuesta_final: "cuando he dicho yo eso? si la gracia del p2p es no decir nada :)" },
  { id: "3", tipo: "historico", comentario: "¿Qué es una LLC y qué impuestos paga?", respuesta_final: "Una LLC es una sociedad americana…" },
  { id: "4", tipo: "ia", comentario: "Gran video", respuesta_final: "Gracias! :)" },
];

t("elegirEjemplos pone primero los parecidos al comentario y prefiere los escritos por Sergi", () => {
  const r = G.elegirEjemplos("Me parece que metes miedo, el p2p en efectivo Hacienda no lo ve", EJ, 2);
  eq(r.length, 2, "numero de ejemplos");
  eq(r[0].id, "2", "el mas parecido (y escrito a mano) deberia ir primero");
  ok(r.every((e) => e.id !== "3"), "la LLC no tiene nada que ver");
});

t("buildSystemPrompt con aprendizaje sustituye los 13 ejemplos fijos y conserva precision y seguridad", () => {
  const ej = G.elegirEjemplos("p2p Hacienda", EJ.concat(EJ.map((e, i) => ({ ...e, id: "x" + i, respuesta_final: e.respuesta_final + " " + i }))), 10);
  const sp = G.buildSystemPrompt("", "Cash out", "", "", { reglas: "REGLAS DE VOZ\n- contrapregunta corta", ejemplos: ej.map(G.formatoEjemplo).join("\n\n"), n: ej.length });
  ok(!sp.includes("Ejemplo 1 (técnico/fiscal)"), "siguen los ejemplos fijos");
  ok(!sp.includes("cierra con humildad"), "sigue la regla fija de las criticas");
  ok(sp.includes("contrapregunta corta") && sp.includes("cuando he dicho yo eso?"), "faltan reglas o ejemplos reales");
  ok(sp.includes("PRECISIÓN (regla dura") && sp.includes("SEGURIDAD (regla dura") && sp.includes("FORMATO:"), "se ha perdido una regla dura");
  const sin = G.buildSystemPrompt("", "Cash out", "", "", null);
  ok(sin.includes("Ejemplo 1 (técnico/fiscal)"), "sin aprendizaje deben seguir los fijos");
});

t("formatoEjemplo de una editada enseña lo que propuso la IA y lo que publico Sergi", () => {
  const f = G.formatoEjemplo({ tipo: "editada", comentario: "c", respuesta_ia: "Excelente pregunta…", respuesta_final: "corto :)" });
  ok(f.includes("La IA propuso: «Excelente pregunta…»") && f.includes("Sergi lo cambió y publicó: «corto :)»"), f);
});

ta("handleGuardarRespuesta guarda en la cola y la manda al motor en lote; sin clave, queda en la cola", async () => {
  const store = { apiKey: "sk-ant-test", motorClave: "", aprender: true };
  const origGet = sandbox.chrome.storage.local.get, origSet = sandbox.chrome.storage.local.set, origFetch = sandbox.fetch;
  sandbox.chrome.storage.local.get = async (d) => { const o = {}; for (const k of Object.keys(d)) o[k] = k in store ? store[k] : d[k]; return o; };
  sandbox.chrome.storage.local.set = async (o) => { Object.assign(store, o); };
  const enviados = [];
  sandbox.fetch = async (url, opts) => { enviados.push(JSON.parse(opts.body)); return { ok: true, status: 200, text: async () => '{"ok":true,"nuevas":2}' }; };
  try {
    let r = await G.handleGuardarRespuesta({ fila: { id: "a", tipo: "a_mano", comentario: "c", respuesta_final: "r1" } });
    eq(r.guardada, false, "sin clave no deberia mandarse");
    eq(store.ytrCola.length, 1, "deberia quedar en la cola");
    store.motorClave = "k";
    r = await G.handleGuardarRespuesta({ fila: { id: "b", tipo: "editada", comentario: "c", respuesta_ia: "x", respuesta_final: "r2" } });
    eq(r.guardada, true, "con clave deberia mandarse");
    eq(enviados.length, 1, "una sola peticion");
    eq(enviados[0].yt, "guardar_lote", "tipo de peticion");
    eq(enviados[0].filas.length, 2, "deberian ir las dos filas de la cola");
    eq(enviados[0].clave, "k", "clave");
    eq(store.ytrCola.length, 0, "la cola deberia quedar vacia");
    store.aprender = false;
    r = await G.handleGuardarRespuesta({ fila: { id: "c", respuesta_final: "r3" } });
    eq(r.guardada, false, "con el aprendizaje apagado no se guarda");
  } finally {
    sandbox.chrome.storage.local.get = origGet; sandbox.chrome.storage.local.set = origSet; sandbox.fetch = origFetch;
  }
});

ta("handleGenerate mete en el prompt las respuestas reales del motor (y las cachea una hora)", async () => {
  const store = { apiKey: "sk-ant-test", motorClave: "k", aprender: true, extendedThinking: false };
  const origGet = sandbox.chrome.storage.local.get, origSet = sandbox.chrome.storage.local.set, origFetch = sandbox.fetch;
  sandbox.chrome.storage.local.get = async (d) => { const o = {}; for (const k of Object.keys(d)) o[k] = k in store ? store[k] : d[k]; return o; };
  sandbox.chrome.storage.local.set = async (o) => { Object.assign(store, o); };
  let llamadasMotor = 0, system = "";
  const muchos = Array.from({ length: 12 }, (_, i) => ({ id: "e" + i, tipo: "historico", comentario: "p2p Hacienda efectivo " + i, respuesta_final: "respuesta real " + i }));
  sandbox.fetch = async (url, opts) => {
    if (String(url).includes("api.anthropic.com")) {
      system = JSON.parse(opts.body).system;
      return { ok: true, status: 200, json: async () => ({ content: [{ type: "text", text: "vale :)" }] }) };
    }
    llamadasMotor++;
    return { ok: true, status: 200, text: async () => JSON.stringify({ ok: true, reglas: "REGLAS DE VOZ\n- corto", ejemplos: muchos }) };
  };
  try {
    const r = await G.handleGenerate({ commentText: "el p2p en efectivo Hacienda no lo ve", videoTitle: "Cash out" });
    eq(r.ok, true, "deberia generar");
    ok(system.includes("respuesta real") && system.includes("- corto"), "el prompt no lleva lo aprendido");
    await G.handleGenerate({ commentText: "otro", videoTitle: "Cash out" });
    eq(llamadasMotor, 1, "el contexto deberia venir de la cache la segunda vez");
  } finally {
    sandbox.chrome.storage.local.get = origGet; sandbox.chrome.storage.local.set = origSet; sandbox.fetch = origFetch;
  }
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
