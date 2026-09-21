# Traspaso técnico — YouTube Reply Assistant v2.2.1

Documento para retomar este proyecto en Claude Code. Escrito por quien lo ha
construido, con lo que funciona, lo que no, lo que ya se ha descartado y por
qué. Léelo entero antes de tocar código: buena parte del tiempo perdido hasta
ahora ha sido repetir hipótesis ya refutadas.

---

## 0. Lo primero: por qué esto se traspasa

El proyecto se ha desarrollado sin acceso al entorno real. El asistente que lo
escribió **no tenía salida de red hacia youtube.com** ni forma de abrir un
navegador. Todo el código está razonado y probado contra un YouTube Studio
simulado (57 pruebas en `pruebas/`, todas pasan), pero **ningún selector de
Studio ha sido verificado nunca contra el DOM real**.

Esa es la causa raíz de la iteración interminable: cada hipótesis sobre el DOM
requería una ronda completa con el usuario haciendo de sonda.

**Claude Code sí puede cerrar ese bucle.** Tiene acceso al sistema del usuario
y puede pedirle que ejecute cosas concretas, leer la salida y corregir en la
misma sesión. Ésa es toda la ventaja, y es suficiente.

**Primera acción recomendada:** ejecutar `diagnostico-dom.js` (instrucciones
dentro del fichero) y trabajar sobre datos reales en lugar de deducciones.

---

## 0bis. Actualización — ronda de Claude Code (v2.2.2)

Esta ronda tampoco ha tenido acceso a `studio.youtube.com` con tu sesión (ese
acceso solo lo tienes tú, en tu navegador). Sigue sin poder verificarse nada
contra el DOM real. Lo que sí se ha podido hacer, sin adivinar selectores
nuevos, es corregir la **lógica** de `publish()` allí donde el razonamiento
del traspaso ya identificaba un fallo real independientemente del DOM
concreto:

- **H1 (confirmación de envío por ausencia)** — corregido. Ver §4, ahora exige
  dos señales, no una. Se añadió una prueba en `tests.js` que reproduce
  exactamente el síntoma descrito ("el campo se vacía pero no se ha publicado
  nada de verdad") y confirma que con el código anterior habría dado un falso
  positivo.
- **H3 (`deactivate()` en pleno envío)** — corregido. La desactivación se
  aplaza mientras `state.busy` es `true` y se aplica al terminar.
- **H2 (`findSubmitButton` coge el botón equivocado)** — endurecido, no
  descartado. Ahora busca primero dentro de la fila ya identificada
  (`row`), y solo si no encuentra nada ahí recurre a la subida por
  ancestros de antes. Reduce el radio de error, pero sigue sin poder
  probarse frente al DOM real: si Studio renderiza el botón de enviar fuera
  de la fila (portal/diálogo), esto no lo cambia.
- **No tocado, deliberadamente**: no se ha añadido el contador "N respuestas"
  que este documento propone como la confirmación *real* (§4, "Cómo
  arreglarlo"). Habría requerido adivinar un selector nunca visto, exactamente
  el tipo de hipótesis sin verificar que esta sección pide no repetir. Es lo
  primero que hay que añadir en cuanto `diagnostico-dom.js` confirme cómo se
  ve ese contador en el DOM real.
- **Problema abierto 2 (transcripción)** no se ha tocado: no hay ningún
  fallo de lógica identificable sin datos reales del diagnóstico del popup,
  y añadir una sexta estrategia a ciegas sería exactamente el error que este
  documento pide evitar.

Sigue en pie la recomendación de fondo de la §7 (Data API v3). Nada de esta
ronda la sustituye; solo hace que la vía DOM falle con menos falsos positivos
mientras se decide si se invierte en OAuth.

### Primera evidencia visual real (captura del usuario, no diagnóstico)

El usuario ha instalado la 2.2.2 y ha mandado una captura de pantalla real de
Studio. Es la primera vez que este proyecto ve algo del DOM real, aunque sea
una imagen y no la salida de `diagnostico-dom.js`. Secuencia observada:

1. Pulsa "✨ Responder con IA" en un comentario sin transcripción → se abre el
   panel de revisión (correcto, es el comportamiento esperado sin
   transcripción).
2. Pulsa "Publicar" dentro del panel.
3. Studio SÍ abre una caja de respuesta visible ("Añade una respuesta...").
4. El toast rojo dice: **"Al pulsar Responder no se ha abierto ningún cuadro
   de respuesta."**

Es decir: la caja se abre a la vista, pero el código no la detecta dentro de
los 8 s de `waitFor` en el paso 2 de `publish()`. Hipótesis más probable a
partir de lo visible en la captura: el placeholder gris "Añade una
respuesta..." es típico de un `<textarea>` con atributo `placeholder`, no de
un `contenteditable` (que normalmente usa un truco de CSS `:empty::before`,
sin atributo `placeholder`). Si Studio ha pasado su editor de respuestas de
un `div[contenteditable]` a un `<textarea>` normal, **todo** el mecanismo
actual de detección (`FIELD_SELECTOR`, que solo busca contenteditable) e
inserción (`execCommand("insertText")` con selección de `Range`, que no
aplica a un `<textarea>`) está construido sobre un supuesto que ya no es
cierto. No es H1/H2/H3: es un cuarto candidato, anterior a todos ellos, que
haría fallar el flujo antes de llegar siquiera al paso de publicar.

**No se ha cambiado el código a partir de esta sola hipótesis** — sería
exactamente el error que esta sección pide no repetir: una imagen no es un
selector, y adivinar el atributo `placeholder` de una captura no es dato
verificado. En su lugar se ha ampliado `diagnostico-dom.js` (sección 1) para
que busque explícitamente `<textarea>` visibles además de `contenteditable`,
y avise si detecta la combinación "sin contenteditable, con textarea" — que
confirmaría o refutaría esto de un vistazo. También se ha añadido la sección
6, que lista los botones de reacción del comentario (me gusta / no me gusta /
corazón), pedidos por el usuario para una función nueva (ver más abajo).

**Siguiente paso, antes de tocar `FIELD_SELECTOR` o `insertText()`:** que el
usuario ejecute el `diagnostico-dom.js` actualizado con una caja de respuesta
abierta (como en su captura) y pegue la salida completa. Con eso se confirma
si es un `<textarea>` y, si lo es, el arreglo es sencillo y ya está esbozado
en `handleInsertMain` (`background.js`): usar el setter nativo de `.value` +
evento `input`, en vez de `execCommand`.

#### Confirmado con datos reales — 21/09/2026

El usuario ha ejecutado `diagnostico-dom.js` real (no una imagen: la salida
completa de la sección 1). **Confirmado: es un `<textarea>`.** Cadena real:

```
textarea#textarea.style-scope.tp-yt-iron-autogrow-textarea
  < div.textarea-container.fit.style-scope
  < tp-yt-iron-autogrow-textarea#textarea...
  < div#child-input... < div#outer... < ytcp-form-input-container#input-container
  < div#main.style-scope.ytcp-commentbox < div#body.style-scope.ytcp-commentbox
```

placeholder="Añade una respuesta...". Y el botón de enviar real, dentro de
`ytcp-commentbox`, **no lleva `id="submit-button"`** — solo texto/aria
"Responder", después del campo en orden de documento. Encaja exactamente con
la rama de fallback por texto que `findSubmitButton`/`buscarBotonEnviar` ya
tenían para este caso.

Con esto se ha corregido, ya no como hipótesis sino como hecho verificado:

- `FIELD_SELECTOR` ahora incluye `"ytcp-commentbox textarea"`.
- `insertText()` (content.js) bifurca por `field.tagName === "TEXTAREA"`: usa
  el setter nativo de `HTMLTextAreaElement.prototype.value` + eventos
  `input`/`change`, en vez de `execCommand` con selección de `Range` (que no
  aplica a un `<textarea>`, que no participa en `window.getSelection()`).
- `contentMatches()`, `closeOpenBoxes()` y la confirmación de envío del paso 7
  de `publish()` ahora leen el contenido con `fieldText()`, que usa `.value`
  para `<textarea>` en vez de `.innerText`/`.textContent` (que en un
  `<textarea>` reflejan el HTML inicial, no lo que el usuario ha escrito).
- El plan B (`handleInsertMain` en `background.js`, mundo principal) recibió
  la misma bifurcación.
- `pruebas/harness.js` tiene ahora un modo `campoTextarea: true` que reproduce
  esta estructura exacta (textarea sin id, botón de enviar sin id, solo
  texto), para no volver a dar por buena una prueba que solo ejercita el
  modelo antiguo. Dos pruebas nuevas en `tests.js` cubren el camino feliz y
  el aborto cuando el framework no registra el input.

**Lo que sigue sin verificar:** los botones de reacción (me gusta / no me
gusta / corazón) de la sección 6 del diagnóstico — el mensaje se cortó antes
de llegar a esa parte. `likeComment()` sigue siendo best-effort hasta que se
vea esa sección.

### Función nueva pedida: "me gusta" al comentario al publicar

Se ha añadido `likeComment()` en `content.js`, activada por el ajuste
`likeOnPublish` (por defecto `true`, checkbox en el popup). Se llama siempre
DESPUÉS de que `publish()` ya ha devuelto `ok:true`, nunca antes ni durante:
un fallo aquí no puede impedir ni deshacer una respuesta ya publicada. Busca,
dentro de la fila del comentario, un botón visible con `aria-label` o texto
"me gusta"/"like", excluyendo "no me gusta", "corazón" (que en Studio es la
reacción exclusiva del propietario del canal, no un "me gusta" genérico) y
los propios botones de la extensión. **Es una heurística razonable, no un
selector verificado** — igual que el resto de selectores de este proyecto,
nadie ha visto el DOM real de esos iconos. Si no encuentra un candidato claro,
lo omite en silencio (log en consola) y la respuesta se publica igual. La
sección 6 de `diagnostico-dom.js` está pensada exactamente para confirmar o
corregir esto en la próxima ronda con datos reales.

---

## 1. Contexto

**Usuario:** abogado, socio de un despacho, especializado en fiscalidad de
criptoactivos y fiscalidad internacional. Tiene un canal de YouTube
("Abogado Cripto") que usa para divulgación y captación.

**Objetivo:** responder los comentarios de su canal con un solo clic. Genera la
respuesta con la API de Anthropic, usando un prompt de estilo con su voz y 13
ejemplos reales suyos, y la publica en YouTube Studio.

**Restricción que no es negociable:** las respuestas se publican bajo su nombre
profesional y hablan de DAC8, CRS, MiCA, IRPF y estructuras internacionales. Un
dato inventado es un problema reputacional real. Por eso todo el diseño gira en
torno a **no publicar cuando no hay certeza**. Si dudas entre "publicar algo
imperfecto" y "abortar y avisar", aborta siempre.

**Lo que el usuario quiere ahora mismo:** modo instantáneo, un clic, sin
revisión. Está configurado para ello, pero la publicación falla.

---

## 2. Estado actual, sin adornos

| Componente | Estado |
|---|---|
| Arranque automático al entrar en Comunidad (sin recargar) | Funciona |
| Inyección del botón en cada fila de comentario | Funciona |
| Llamada a la API y generación de la respuesta | Funciona |
| Calidad y longitud del texto generado | Funciona |
| Salvaguardas de calidad (vacío, fuga de prompt, muletillas) | Funciona |
| Panel de revisión y edición | Funciona |
| **Publicación automática en Studio** | **FALLA — problema abierto 1** |
| **Obtención de la transcripción** | **FALLA — problema abierto 2** |

---

## 3. Arquitectura

```
manifest.json     MV3. content script en TODO studio.youtube.com/*
                  Permisos: storage, scripting, tabs, clipboardWrite
                  Hosts: studio.youtube.com, www.youtube.com, api.anthropic.com

content.js        ~1.100 líneas. Todo el DOM y el flujo.
background.js     ~700 líneas. API, transcripción, inserción en mundo principal.
popup.html/js     Ajustes + prueba de conexión + diagnóstico de transcripción.
styles.css        Prefijo yra2- en todo, para convivir con la v1.
```

### Estado en `content.js`

```js
state = {
  active,     // dentro de una ruta de comentarios
  busy,       // cerrojo: un solo flujo simultáneo en toda la página
  cfg,        // ajustes desde chrome.storage.local
  observer,   // MutationObserver sobre body
  processed,  // WeakSet de nodos ya evaluados
  abort,      // cancela la cuenta atrás en curso
}
```

### Protocolo de mensajes (content → background)

| Tipo | Payload | Devuelve |
|---|---|---|
| `GENERATE_REPLY` | commentText, videoTitle, videoDescription, transcript | `{ok, reply, usage, model}` |
| `FETCH_TRANSCRIPT` | videoId | `{ok, text, source, lang, kind}` o `{ok:false, reason, detail}` |
| `INSERT_MAIN` | text | `{ok, method, content}` |
| `TEST_API` | — | `{ok, model}` |
| `DIAGNOSE` | videoId | `{ok, report}` |

Todos pasan por `send()` en content.js, que **tiene timeout** (45 s por
defecto, 12 s para `INSERT_MAIN`, 20 s para `FETCH_TRANSCRIPT`). Ese timeout se
añadió en 2.2.1 tras un cuelgue silencioso.

### Máquina de estados de `publish()`

Es el núcleo. Está en `content.js`, y es donde vive el problema abierto 1.

```
1. Conseguir el campo de respuesta
   1a. ¿Ya hay una caja abierta EN ESTA FILA y es la única de la página?
       → reutilizarla
   1b. ¿Hay cajas abiertas en otras filas? → ABORTAR
   1c. Si no: realClick(opener) y esperar un campo NUEVO
       - snapshot de campos visibles ANTES del clic
       - polling 120 ms / 8 s
       - el campo válido es el que no estaba antes Y está dentro de la fila
       - si hay varios dentro, pickBestField() elige
       - si aparece fuera de la fila, solo se acepta si no había ninguno antes

2. Localizar el botón de enviar y GUARDAR su estado previo (habilitado o no)

3. Insertar el texto
   3a. execCommand("insertText") con selección explícita → verificar
   3b. si falla: INSERT_MAIN (mundo principal, setters nativos + InputEvent)
       → verificar
   3c. si sigue sin coincidir → ABORTAR

4. Confirmar que el framework lo registró
   - si el botón estaba DESHABILITADO antes: esperar a que se habilite (5 s)
     Ésta es la prueba fuerte: si Angular habilita el botón, registró el texto.
   - si ya estaba habilitado: solo se verifica el contenido, y se avisa por log

5. Releer el campo justo antes del punto de no retorno

6. Ventana de escape (si countdown > 0)

7. realClick(submit) y confirmar envío
   - éxito = el campo desaparece, se oculta, o queda vacío (6 s)
```

Cualquier paso que falle devuelve `{ok:false, error}` y **no publica**.

### `realClick()`

`.click()` a secas no bastaba: los `ytcp-button` de Studio parecen reaccionar a
gestos de puntero. `realClick` emite `pointerdown`, `mousedown`, `pointerup`,
`mouseup` y después **un solo** `click()` nativo. Nunca dos, para descartar por
construcción la doble publicación.

---

## 4. PROBLEMA ABIERTO 1 — la publicación

### Síntoma exacto, en palabras del usuario

> "a la que clico publicar, desaparece la ventana emergente, y no pasa nada"

Y tras la 2.2.1, que dejó de ocultar el panel y añadió avisos flotantes de
error de 12 segundos: **"continúa mismo error"**.

### Por qué eso es muy informativo

En 2.2.1 el panel ya **no** se oculta durante la publicación. Sólo hay cinco
sitios en todo el código que eliminan `.yra2-panel`:

1. `showPanel()`, al inicio (borra paneles anteriores)
2. `deactivate()`, al salir de una ruta de comentarios
3. El manejador global de `Escape`
4. `panel.remove()` en la rama de **éxito** de publicar
5. El botón de cerrar del propio panel

Si el panel desaparece al pulsar Publicar y no sale ningún aviso rojo, los dos
candidatos serios son **(4)** y **(2)**.

### Hipótesis, ordenadas por probabilidad

**H1 — Falso positivo en la confirmación de envío (candidato 4). La más probable.**

En el paso 7:

```js
const sent = await waitFor(() => {
  if (!field.isConnected) return true;
  if (!isVisible(field)) return true;
  if (norm(field.innerText || field.textContent || "") === "") return true;
  return null;
});
```

Esto interpreta **"el campo ha desaparecido"** como **"se ha publicado"**. Son
cosas distintas. Si el cuadro se cierra por cualquier otro motivo —se pulsó
algo que lo cancela, Angular lo desmonta, la lista se repinta— `publish()`
devuelve `ok:true`, el panel se elimina y no se publica nada. Encaja con el
síntoma al 100%.

*Cómo confirmarlo:* al pulsar Publicar debería salir un aviso **verde** abajo a
la derecha ("Respuesta publicada."). Si el usuario ve el verde y el comentario
no aparece, es H1, confirmado.

*Cómo arreglarlo:* la confirmación tiene que ser positiva, no por ausencia.
Opciones, de mejor a peor:
- Antes de pulsar, contar las respuestas del hilo (el texto "N respuestas").
  Después, esperar a que sea N+1. Es la única confirmación real.
- Comprobar que aparece en el hilo un nodo nuevo cuyo texto coincide con lo
  enviado.
- Como mínimo: exigir que el botón de enviar se deshabilite **y** el campo
  desaparezca, no una cosa o la otra.

**H2 — `findSubmitButton()` encuentra el botón equivocado.**

`SUBMIT_TEXTS = ["responder","reply","comentar","comment","publicar","respondre"]`.
El filtro exige que el botón vaya **después** del campo en orden de documento y
excluye lo que sea de la extensión (`esNuestro()`). Pero si Studio coloca el
botón que **abre** otra caja después del campo, o si hay un menú con un elemento
llamado "Responder", puede elegirse mal.

*Cómo confirmarlo:* `diagnostico-dom.js`, apartado 2, lista todos los botones
alrededor del campo con su texto, su posición relativa y su estado de
deshabilitado. Sale a la vista de inmediato.

**H3 — `deactivate()` se dispara (candidato 2).**

`watchRoute()` sondea `location.href` cada 400 ms. Si Studio cambia la URL al
abrir la caja de respuesta (un parámetro de diálogo, por ejemplo),
`isCommentsRoute()` puede devolver `false` y `deactivate()` borra el panel, los
botones y desconecta los observadores.

La expresión es `/\/comments?(\/|$|\?|#)/` sobre `pathname + search`.

*Cómo confirmarlo:* en la consola, `YRA2` registra "Desactivado" cuando esto
pasa. Si aparece justo al pulsar Publicar, es H3.

*Cómo arreglarlo:* no desactivar mientras `state.busy` sea `true`, y ampliar la
expresión.

**H4 — El texto se inserta en un campo que no es el real.**

`pickBestField()` prefiere `#contenteditable-root`, descarta los que cuelgan de
`[aria-hidden='true']` y, si empata, coge el de mayor área. Si Studio monta un
espejo o un overlay de menciones que cumple esas condiciones, escribiríamos ahí.
La verificación de contenido pasaría (leemos el mismo elemento donde
escribimos), pero Angular nunca registraría nada.

*Contraargumento:* con el botón deshabilitado de partida, el paso 4 lo cazaría.
Salvo que el botón ya esté habilitado de entrada, en cuyo caso el propio código
avisa por log de que la verificación es débil.

*Cómo confirmarlo:* `diagnostico-dom.js`, apartado 1, lista todos los campos
editables visibles con dimensiones y jerarquía.

### Qué está descartado — no lo repitas

- **No es el botón "Publicar" del propio panel.** `SUBMIT_TEXTS` incluye
  `"publicar"` y el panel tiene un botón con ese texto: era un fallo real, se
  corrigió en 2.1.1 con `esNuestro()`, que excluye todo lo que lleve `yra2-`.
- **No es que `.click()` no baste.** Se corrigió en 2.1.1 con `realClick()`.
- **No es la ambigüedad de varios `contenteditable`.** Antes de 2.1.1 devolvía
  `null` para siempre; ahora `pickBestField()` elige.
- **No es un cuelgue del mensaje al background.** `send()` no tenía timeout
  hasta 2.2.1; ahora lo tiene y devuelve error visible.
- **No es que el panel se ocultara.** Se hacía hasta 2.2.1; ya no.
- **No es la duplicación de botones.** Corregida en 2.0.

---

## 5. PROBLEMA ABIERTO 2 — la transcripción

### Síntoma

`"YouTube ha encontrado los subtítulos pero no deja descargarlos"`.

Es decir: la detección de pistas **funciona** (el parseo de
`ytInitialPlayerResponse` encuentra `captionTracks`), pero al descargar la
`baseUrl` viene contenido vacío.

### Lo que ya se intentó

Cinco estrategias, en paralelo, con tope de 12 s global:

1. `studio` — POST a `/youtubei/v1/player` **desde el mundo principal de la
   pestaña de Studio**, mismo origen, con las cookies del usuario y el
   `ytcfg` de la página. El usuario es el **propietario** del vídeo. Ésta
   debería ser la buena.
2. `innertube-auth` — POST a `www.youtube.com/youtubei/v1/player` con cookies.
3. `watch-auth` — la página `/watch` con la sesión del usuario.
4. `watch-anon` — la misma sin cookies.
5. `innertube-anon` — el endpoint sin cookies.

Cuatro formatos de descarga: `json3`, `srv3`, `vtt` y el XML por defecto.

### Diagnóstico ya construido

El popup tiene un apartado **Diagnóstico de transcripción** que ejecuta las
cinco estrategias y los cuatro formatos y devuelve un informe con el código
HTTP y los bytes de cada uno. **Ese informe nunca se ha llegado a ejecutar.**
Ejecutarlo es el primer paso obligatorio antes de tocar nada aquí.

### Hipótesis

Lo más probable es el requisito de **proof-of-origin token** (`pot`/`potc`) que
YouTube ha ido imponiendo en `timedtext`. Si es eso, la `baseUrl` sólo sirve con
un token ligado a la sesión que la generó.

Si la estrategia 1 (Studio, como propietario) tampoco funciona, la vía correcta
deja de ser el reproductor: hay que ir a la **API de subtítulos de Studio**
(`captions.list` / `captions.download` en la Data API v3), donde el usuario está
autorizado por ser dueño del canal. Eso encaja de forma natural con la
recomendación de la sección 7.

### Apaño que funciona hoy

El popup tiene un campo "Contexto del vídeo". Cuatro o cinco líneas pegadas a
mano sobre el vídeo de la tanda cubren el 80 % del problema. No es la
transcripción, pero evita que el modelo afirme cosas sobre el contenido sin
saber nada de él.

---

## 6. Banco de pruebas

En `pruebas/`. Ejecutar con Node (necesita `npm install jsdom`):

```bash
node tests.js        # 24 pruebas: flujo, DOM, salvaguardas, SPA
node tests-bg.js     # 33 pruebas: parseo, prompts, transcripción, errores
```

`harness.js` monta un YouTube Studio simulado con jsdom que reproduce lo
esencial del comportamiento de Angular: el botón de enviar arranca
deshabilitado y sólo se habilita cuando llega un evento `input` real. Acepta
variantes por parámetro:

- `campoExtra` — añade un segundo `contenteditable` (overlay de menciones)
- `soloPuntero` — el botón sólo reacciona a `mousedown`, no a `click`
- `angularRegistersInput: false` — el framework nunca registra el texto
- `submitStartsEnabled` — el botón de enviar ya viene habilitado

**Advertencia importante:** que las 57 pruebas pasen no significa que funcione
en Studio. Significa que la lógica es coherente con el modelo que yo supuse.
Y ese modelo es exactamente lo que está en duda.

**Lo primero que debería hacer Claude Code** tras ejecutar
`diagnostico-dom.js`: ajustar `harness.js` para que reproduzca el DOM **real**
que revele el diagnóstico. A partir de ahí las pruebas sí valen algo.

---

## 7. Recomendación: abandonar el DOM y usar la Data API v3

Ésta es la recomendación de fondo, y se ha hecho al usuario tres veces.

Los problemas 1 y 2 son **la misma enfermedad**: estamos automatizando y
raspando una aplicación de Google desde fuera, con selectores deducidos y
endpoints internos no documentados. Cada arreglo es provisional.

La YouTube Data API v3 elimina las dos cosas de golpe:

- **Publicar:** `comments.insert` con `parentId` = el `comment-id` que ya está
  en el DOM de Studio (atributo `comment-id`, presente y verificado). Una
  llamada HTTP con respuesta determinista. Sin Angular, sin timings, sin
  selectores CSS, sin falsos positivos de confirmación: la API dice si se
  publicó o no.
- **Transcripción:** `captions.list` + `captions.download`. El usuario es el
  propietario del canal, así que está autorizado. Adiós a `timedtext`.

**Coste:** proyecto en Google Cloud, pantalla de consentimiento OAuth, scope
`youtube.force-ssl`, y el flujo de autorización en la extensión
(`chrome.identity.launchWebAuthFlow` o `getAuthToken`). Estimación honesta: una
o dos horas para alguien que ya sabe montar OAuth.

**Detalle a verificar antes de comprometerse:** el régimen de verificación de
Google para el scope `youtube.force-ssl` determina cada cuánto habría que
reautorizar. No está confirmado: compruébalo antes de prometerle nada al
usuario.

**Lo que se conserva tal cual:** el prompt de estilo con sus 13 ejemplos, el
control de calidad del texto, los ajustes, el popup y la inyección del botón.
Sólo cambian el paso de publicar y el de obtener la transcripción. Es menos
trabajo del que parece.

---

## 8. Sobre el prompt — no lo toques a la ligera

`buildSystemPrompt()` en `background.js` contiene la voz del usuario: 13
ejemplos reales de respuestas suyas, con el patrón anotado debajo de cada uno.
Es lo más valioso del proyecto y lo único que no se puede reconstruir.

Tres reglas que costó establecer y que hay que respetar:

1. **Los ejemplos mandan sobre cualquier regla de longitud.** Hay un bloque
   `JERARQUÍA` al principio que lo dice explícitamente. La v1 imponía "máximo
   4 líneas", en contradicción con sus propios ejemplos 9, 10, 12 y 13, que son
   de varios párrafos. Eso aplastaba las respuestas técnicas.
2. **Hay un bloque `PRECISIÓN`** que prohíbe inventar cifras, tipos, plazos,
   artículos, modelos y consultas vinculantes, y prohíbe afirmar qué dice un
   vídeo sin tener la transcripción delante. Es un requisito profesional, no
   una preferencia de estilo.
3. **`vetReply()` en content.js** es la última barrera: descarta respuestas
   vacías, fugas del prompt, y marca muletillas ("Excelente pregunta") o
   autoidentificación como IA. Con cualquier marca, no autopublica.

---

## 9. Plan de ataque sugerido

1. Ejecutar `diagnostico-dom.js` en el Studio real. Trabajar con datos.
2. Ejecutar el diagnóstico de transcripción del popup. Igual.
3. Con eso, decidir: ¿se arregla el DOM o se salta a la API v3?
4. Si se arregla el DOM: **empezar por H1**, la confirmación de envío. Cambiar
   "el campo ha desaparecido" por una confirmación positiva (contador de
   respuestas del hilo). Es el fallo que mejor explica el síntoma.
5. Antes de entregar nada, reproducir el fallo en `harness.js` con el DOM real.
   Si la prueba no falla antes del arreglo, no sabes qué has arreglado.

---

## 10. Estado de las credenciales

La API key del usuario se pegó en claro en una conversación y **debe estar
revocada**. Si sigue activa, revocarla en console.anthropic.com es prioritario
sobre cualquier otra cosa de este documento.

La key se guarda en `chrome.storage.local` (no `sync`, que se replica a todos
los Chrome con la sesión de Google iniciada). El content script no la maneja
nunca: sólo el service worker.

---

## 11. Ronda de revisión exhaustiva (v2.2.5 / v2.2.6) — máxima capacidad

El usuario pidió una revisión "perfecta, máxima capacidad" del proyecto ya
funcionando en Studio real (v2.2.3/2.2.4 confirmadas). Se orquestó con el
Workflow tool: 10 agentes en paralelo, cada uno una dimensión distinta del
código (flujo de publicación, manejo dual textarea/contenteditable,
detección del botón de enviar, seguridad del "me gusta", ciclo de vida de
rutas, background.js/API/transcripción, consistencia del popup, seguridad/
XSS/inyección, cobertura de tests, manifest/diagnóstico/estilos), con
verificación adversarial de cada hallazgo (varios verificadores intentando
refutarlo por separado) antes de aplicar nada. La primera ronda se topó con
el límite de sesión a mitad de la verificación; se reanudó con
`resumeFromRunId` cuando el usuario avisó que se había restablecido.

**Nota de proceso, para quien retome esto:** uno de los agentes verificadores
dejó un `console.log("### PLAN_B_REACHED ...")` de depuración olvidado en
`content.js` durante su reproducción (el workflow no usó aislamiento de
worktree, así que todos los agentes comparten el árbol de trabajo real). Se
detectó con `git diff` antes de comitear y se eliminó. **Si vuelves a lanzar
un workflow de revisión con agentes que ejecutan código real contra el
repo, revisa el diff completo línea por línea antes de comitear** — no
asumas que un agente "solo de revisión" no ha podido escribir en el árbol.

### Confirmado y corregido (con test de regresión cada uno)

1. **`publish()` no releía el contenido tras la cuenta atrás (crítico).**
   La única relectura (`contentMatches`) ocurría ANTES de abrir la ventana
   de escape del paso 6, no después. El campo real sigue editable durante
   esos segundos. Se añadió una segunda relectura justo antes del clic
   real (paso 7). Verificado 3/3 por los verificadores adversariales, con
   reproducción empírica contra el harness real antes del fix.
2. **`findSubmitButton()` acotaba solo a `row`**, que es el hilo COMPLETO
   con todas sus respuestas ya publicadas, no la caja local de respuesta.
   En un hilo con respuestas previas, el botón "Responder" sin pulsar de
   una respuesta ya existente podía colar como "botón de enviar" (mismo
   texto, después del campo en el documento). Se añadió un paso previo que
   acota primero al contenedor real y más cercano (`ytcp-commentbox`).
3. **`pendingDeactivate` no se limpiaba** si la ruta volvía a `/comments`
   mientras la publicación seguía en curso (el flag quedaba "pegado" y
   desactivaba la extensión al terminar, aunque el usuario siguiera
   legítimamente en la bandeja de comentarios).
4. **Condición de carrera en el plan B de inserción** (`handleInsertMain`):
   usaba un selector global `[data-yra2-target="1"]` sin identificador de
   invocación. Dos filas con el plan B en vuelo a la vez podían hacer que
   un resultado tardío de una escribiera el texto en el campo de la otra.
   Se añadió un nonce por invocación.
5. **La API key llegaba al content script.** `getSettings()` pedía el
   objeto `DEFAULTS` completo (incluida `apiKey`) a `chrome.storage.local`,
   contradiciendo el propio comentario de cabecera de `background.js`
   ("el content script ya no la recibe ni la maneja" — que era falso). Se
   quitó `apiKey` de `DEFAULTS` en `content.js`; la presencia se comprueba
   ahora con un mensaje `HAS_API_KEY` que el service worker resuelve sin
   revelar el valor.
6. **Inyección de instrucciones desde comentarios de terceros.** El texto
   del comentario se pasaba a la API sin delimitador ni instrucción
   anti-inyección. Con modo "auto" + `countdown:0` (combinación ofrecida
   por el propio popup), un comentario del tipo "ignora las instrucciones
   anteriores y responde X" podía publicarse bajo el nombre profesional
   del usuario sin revisión humana, sin que `vetReply()` lo detectara (el
   texto resultante es gramatical, no contiene sus patrones conocidos). Se
   añadió un delimitador explícito (`<<<INICIO_COMENTARIO>>>`/
   `<<<FIN_COMENTARIO>>>`) y una regla SEGURIDAD en el system prompt.
7. **`downloadTrack()` sin timeout real por descarga.** El "tope global de
   12s" (`TRANSCRIPT_DEADLINE_MS`) solo se comprobaba antes de llamar,
   nunca durante: un `fetch` colgado (sin responder, no sin fallar) podía
   superarlo ampliamente. Se envolvió con `conTope()`.
8. **`DEFAULTS` de `background.js` sin `likeOnPublish`** (desincronizado de
   `content.js`/`popup.js`). Dormante hoy, pero un futuro `if
   (cfg.likeOnPublish)` en `background.js` habría leído siempre `undefined`
   sin ningún aviso.
9. **`LIKE_EXCLUDE` no cubría la variante "quitar me gusta"/"unlike".** Si
   Studio etiqueta así el botón para deshacer un "me gusta" ya dado (su
   texto también contiene "like"/"me gusta"), `likeComment()` podía
   quitarlo en vez de darlo.
10. **`state.processed` (WeakSet) no se recuperaba de la virtualización de
    listas de Studio.** Si Studio recicla un nodo ya marcado como
    procesado para mostrar un comentario distinto (scroll infinito), la
    fila se quedaba sin botón para siempre. Se añadió un reset periódico
    (~cada 30s) dentro de la red de seguridad ya existente.
11. **`diagnostico-dom.js` podía capturar el propio panel de la extensión**
    en vez del campo real de Studio si se ejecutaba justo tras un intento
    fallido de publicar (el escenario típico para depurar). Se excluye
    ahora la UI de la extensión de las tres búsquedas de campos/botones.
12. **`diagnostico-dom.js`, rama contenteditable de la prueba de
    inserción, no avisaba si la restauración del texto original fallaba**
    (`execCommand` puede devolver `false` sin lanzar excepción). Ahora
    compara el resultado final y avisa explícitamente si no coincide.
13. **Dos asserts tautológicos en `pruebas/tests.js`**: uno comprobaba
    `panel.style.visibility !== "hidden"`, propiedad que el código nunca
    escribe (no detectaría un `panel.remove()`); otro aceptaba `publicadas
    <= 1` en el test del cerrojo, que seguiría pasando aunque AMBOS clics
    fallaran en silencio. Corregidos a comprobaciones reales.

### Cierre del workflow (los 25 hallazgos brutos, verificados al 100%)

La verificación adversarial se topó con el límite de sesión a mitad de
camino (ver más abajo lo aplicado mientras tanto por lectura directa del
código). Al reanudarla completa (85/85 agentes, sin errores), el veredicto
final sobre los 25 hallazgos brutos de la fase de revisión fue: **5
sobreviven** la refutación por mayoría de 3 verificadores independientes.
De esos 5, el crítico (relectura tras la cuenta atrás) ya estaba corregido
arriba. Los otros 4:

14. **El fast-path por `id="submit-button"` del harness, que el DOM real
    confirmado NUNCA tiene**, era el camino que tomaba casi toda la suite
    (el modo contenteditable legacy sí le ponía ese id), así que la
    búsqueda real por texto/aria-label — la que usa producción — apenas se
    ejercitaba. Se quitó ese id de **ambos** modos del harness: ya no es
    solo "menos representativo", es modelar un dato que sabemos que es
    falso. Los 36 tests de `tests.js` pasan igual, confirmando que el
    fallback por texto siempre ha funcionado — pero ahora es lo que de
    verdad se está probando.
15. **`closeOpenBoxes()` (la salvaguarda contra destruir un borrador a
    medias) solo se probaba en modo contenteditable.** Añadido el mismo
    test en modo `campoTextarea: true`.
16. **`handleInsertMain()` (plan B de inserción) sin ninguna prueba.**
    Cerrado parcialmente ya en la ronda anterior (orquestación: tabId,
    args, propagación del resultado, en `tests-bg.js`). Sigue sin probarse
    la lógica interna del `func` inyectado contra un DOM real — requeriría
    extraerlo a una función nombrada aparte en `background.js`, un cambio
    de arquitectura fuera de esta ronda.
17. **Condición de carrera en la caché de transcripción**: dos pestañas
    sobre el mismo vídeo (o dos llamadas casi simultáneas) podían disparar
    `fetchTranscript()` por separado antes de que ninguna cacheara nada,
    repitiendo las cinco estrategias y hasta veinte peticiones de red.
    Añadido un `Map` de promesas en vuelo por `videoId`, registrado
    **antes de cualquier `await`** dentro de `handleTranscript()` (el
    primer intento lo registraba después de leer la caché de storage, lo
    que dejaba una ventana de carrera real para dos llamadas verdaderamente
    simultáneas — se corrigió al detectarlo). Test en `tests-bg.js` que
    verifica el efecto observable (no se duplican las llamadas de red),
    no el estado interno: las `const` de nivel superior de `background.js`
    no se adjuntan al objeto del contexto `vm` que usan las pruebas
    (a diferencia de las `function`, que sí), así que `G.enVuelo` no
    existe ahí — lección para quien añada más pruebas de este estilo.

### Refutado tras verificación adversarial (no se ha tocado)

- **"El botón de enviar podría sustituirse por un nodo nuevo al
  habilitarse"** (patrón `*ngIf` de Angular Material). Refutado 2/2 por los
  verificadores que llegaron a completar: Studio usa componentes Polymer
  (`ytcp-button`), que reflejan `disabled` sobre el mismo nodo, no lo
  reemplazan — confirmado también por el propio `pruebas/harness.js` en
  modo `campoTextarea`. Incluso si ocurriera, el resultado sería un aborto
  seguro (texto preservado para envío manual), no una publicación errónea.

### Pendiente, documentado pero no implementado

- **El *default* del harness sigue siendo el modo `contenteditable`
  legacy** (la mayoría de tests no pasan `campoTextarea: true`). Ya no
  ejercitan un fast-path falso (el `id="submit-button"` se quitó de los dos
  modos, punto 14 de arriba), pero invertir el default exigiría revisar
  cada test legacy uno a uno para no perder cobertura de lo que sí es
  específico de contenteditable (p.ej. el test de doble
  `contenteditable`/`campoExtra`).
- **La lógica interna del `func` inyectado por `handleInsertMain()`** (el
  plan B, mundo principal) se probó en su orquestación (tabId, args,
  propagación del resultado), no ejecutando de verdad esa función contra
  un DOM real — requeriría extraerla a una función nombrada por separado
  en `background.js` para poder importarla en un test aislado, un cambio
  de arquitectura fuera del alcance de esta ronda.
- **El catch de excepción dentro de `likeComment()`** no tiene test
  dedicado (bajo valor: es un try/catch trivial alrededor de código ya
  cubierto).
