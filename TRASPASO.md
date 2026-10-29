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
4. **(v2.2.8) Tope de proporción respecto al comentario, independiente de
   la regla 1.** El usuario pidió explícitamente que ninguna respuesta sea
   "5 veces más larga" que el comentario que la origina, por mucho que los
   ejemplos justifiquen desarrollarla. Esto NO contradice la regla 1: los
   ejemplos siguen marcando el estilo/profundidad (cuántos puntos cubrir,
   qué tono), pero ahora hay además un tope duro de seguridad por
   proporción (`vetReply()`, con la misma fórmula orientativa ya en el
   prompt de `buildUserMessage()`: objetivo 2x-3x, tope real 5x con mínimo
   de 200 caracteres). Si un comentario realmente justifica una respuesta
   larga (ejemplos 9/10/12/13) pero también es largo él mismo, el tope de
   5x rara vez se alcanza en la práctica — solo actúa cuando la respuesta
   se desproporciona de verdad frente a lo que se le preguntó.

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

---

## 12. Ajuste del tope de proporción (v2.2.8 → v2.2.9): 5x era demasiado permisivo

El usuario trajo un caso real de producción: comentario de 315 caracteres,
respuesta publicada de 1514 — **4.81x**. Por debajo del tope duro de 5x que
se había puesto en v2.2.8, así que el código no lo bloqueó, pero el usuario
lo veía claramente como "excedido" a simple vista.

Diagnóstico: el modelo no estaba apuntando al objetivo real (2x-3x), sino
acercándose sistemáticamente al tope duro cuando el comentario planteaba
varios conceptos aunque fuera corto (este caso: riesgo de custodia + MEDA/
regulación + dilema liquidez-vs-custodia + Binance-vs-Bitso + elección de
red de retiro + pregunta de cierre — seis puntos distintos desarrollados
cada uno con su propio párrafo). La instrucción de v2.2.8 ("no es rígido,
nunca superes el tope") dejaba demasiado margen para tratar cada concepto
como si mereciera desarrollo propio.

Dos cambios, no uno: bajar el tope SIN reforzar el prompt habría generado
más paneles de revisión sin cambiar el comportamiento típico; reforzar el
prompt SIN bajar el tope habría dejado el mismo caso límite sin red de
seguridad real si el refuerzo no bastaba. Se hicieron los dos:

- **Tope duro: 5x → 4x** (mínimo 200 sin cambios), en `vetReply()`
  (`content.js`) y en la orientación de `buildUserMessage()`
  (`background.js`) — misma fórmula en los dos sitios, hay que mantenerlos
  sincronizados si se vuelve a tocar.
- **Prompt más directivo**: ya no solo orienta un rango y avisa del tope;
  pide explícitamente decidir los 2-3 puntos que de verdad hay que
  responder y resumir o fusionar el resto, y dice sin rodeos que "un
  comentario corto con una pregunta densa no es licencia para responder
  cada concepto por separado con el mismo detalle".

Si se repite el patrón (respuestas rondando el tope en vez del objetivo),
el siguiente paso razonable es bajar más el tope antes de seguir
reescribiendo el prompt — un prompt más largo compite por atención con las
reglas ya existentes (JERARQUÍA, PRECISIÓN, SEGURIDAD) y tiene rendimientos
decrecientes.

**Actualización inmediata (misma sesión):** el usuario pidió bajar el tope
directamente a 3x, sin esperar a ver si 4x repetía el patrón. Aplicado: el
tope real ahora coincide exactamente con el extremo superior del objetivo
(`objetivoMax === topeDuro`, ambos `largoComentario * 3`, salvo el mínimo
de 200). Ya no queda margen entre "objetivo" y "límite absoluto": si se
vuelve a pedir bajar más, la fórmula ya no tiene recorrido natural (bajar
el tope por debajo del objetivo significaría que el propio objetivo
también hay que estrecharlo, p.ej. a 1.5x-2x).

---

## 13. Reintento automático de acortado (v2.2.11)

El usuario trajo un caso real donde el tope absoluto de "respuesta muy
larga" (2000 caracteres, independiente de la proporción) interrumpió con
el panel de revisión. Su reacción: no quiere seguir viendo ese panel por
este motivo — quiere que el sistema intente resolverlo solo antes de
rendirse.

Antes, exceder cualquiera de los dos topes de longitud (absoluto de 2000,
o de proporción) iba directo al panel. Ahora, en `runFlow()`
(`content.js`), si **todas** las incidencias de `vetReply()` son de
longitud (nunca si hay fuga de prompt, muletilla u otro problema de
fondo — `esSoloLongitud()` exige unanimidad), se reintenta la generación
hasta 2 veces con un aviso reforzado de brevedad
(`GENERATE_REPLY` con `payload.acortar = {prevLength, maxAllowed}`,
consumido en `buildUserMessage()` en `background.js`, añadido al final del
mensaje con prioridad de recencia sobre la instrucción de longitud
original). Solo si tras los 2 reintentos sigue sin caber, se rinde y
muestra el panel como antes — la red de seguridad original sigue intacta,
esto solo le da al sistema una oportunidad de arreglarlo sin intervención
manual antes de pedírsela al usuario.

`maxAllowed` que se comunica al modelo es
`Math.min(Math.max(comentario*3, 200), 2000)`: el menor de los dos topes
reales que `vetReply()` aplica (proporción y absoluto), para que el
reintento apunte a lo que de verdad hace falta cumplir.

`pruebas/harness.js` gana soporte para que el mock de `GENERATE_REPLY`
sea una función `(payload) => string` además de un string fijo, para poder
simular que el modelo coopera (responde corto) o no coopera (sigue largo)
al recibir el aviso de acortar. Dos tests en `tests.js` cubren ambos casos.

---

## 14. Reintento automático también para la fuga de prompt (v2.2.12)

El usuario trajo un caso real (comentario sobre Hyperliquid, 253
caracteres) donde la respuesta se descartó con el toast rojo
"Respuesta descartada: respuesta desproporcionada (776 caracteres frente
a 253 del comentario); fuga del prompt." — y pidió que esto se arreglase,
en línea con su petición ya aplicada en la 2.2.11: no quiere ver estos
avisos, quiere que el sistema lo resuelva solo.

La causa: `vet.fatal` se comprobaba **antes** del bucle de reintento de
acortado (§13), así que cualquier fuga de prompt (`fatal = true` en
`vetReply()`) iba directa a `abortFlow()` sin pasar nunca por ningún
reintento — a diferencia de los problemas de longitud, que desde la
2.2.11 sí reintentan solos. Acortar tampoco habría arreglado una fuga de
prompt aunque hubiera llegado al bucle: son problemas de naturaleza
distinta (contenido de fondo vs. longitud), así que necesitaba su propio
reintento con su propio aviso.

Añadido en `runFlow()` (`content.js`), **antes** del chequeo
`if (vet.fatal)`: si la única fuga detectada es `"fuga del prompt"`, se
reintenta la generación hasta 2 veces con `payload.evitarFuga = true`,
consumido en `buildUserMessage()` (`background.js`) para añadir, con
prioridad de recencia máxima, un aviso explícito de no repetir
encabezados ni delimitadores del prompt. Solo si tras los 2 reintentos
sigue habiendo fuga se rinde y muestra el panel/toast como antes.

No se ha extendido el mismo reintento a `"respuesta vacia"` (el otro
motivo que marca `fatal = true` en `vetReply()`): no hay evidencia de que
ocurra en la práctica y, a diferencia de la fuga, no hay un aviso
específico y accionable que añadir al prompt para corregirlo — solo
repetir la misma petición a ciegas. Si se repite como caso real, aplicar
el mismo patrón.

`tests.js` gana un segundo escenario de fuga ("el modelo SI corrige al
pedírselo", mock por función que coopera cuando recibe
`payload.evitarFuga`) y el escenario existente ahora verifica también el
número exacto de llamadas (3: 1 inicial + 2 reintentos), igual que ya
hacía el test equivalente de acortado. `tests-bg.js` gana dos tests para
el nuevo parámetro `evitarFuga` de `buildUserMessage()`.

---

## 15. Un párrafo nuevo es para un punto nuevo, no para cada paso del mismo punto (v2.2.13)

Caso real: comentario de @macoliytb (253 caracteres) preguntando qué es
"P2P directo" y si no supone un problema futuro al volver a fiat.
Respuesta publicada: 618 caracteres, ratio 2.44x — **dentro** del objetivo
2x-3x y lejos del tope duro de 3x (759). El usuario la vio larga igual:
"le quitaría un párrafo".

Esto confirma que no todo lo que se percibe como "demasiado largo" es un
problema de proporción medible en caracteres — aquí el chequeo numérico
estaba correctamente dentro de rango. El problema era estructural: la
respuesta tenía 3 párrafos para lo que en realidad eran 2 puntos (qué es
P2P directo; el problema al volver a fiat), porque el segundo punto se
desarrolló en dos párrafos separados ("el problema es real..." / "la
solución práctica es...") en vez de uno solo.

El prompt (`buildUserMessage()`, `background.js`) ya pedía fusionar
*puntos* secundarios en una frase en vez de darles su propio párrafo,
pero no decía nada sobre partir el desarrollo de un *único* punto en
varios párrafos (explicar el problema en uno y la solución en otro es,
para el modelo, una razón tan buena como cualquier otra para abrir
párrafo nuevo). Añadida una instrucción explícita justo después: "un
párrafo nuevo es para un punto nuevo, no para cada paso de explicar el
mismo punto" — problema + solución de la misma pregunta van en un solo
párrafo, salvo que de verdad sean preguntas o temas distintos.

No se ha tocado ningún número (ni el objetivo 2x-3x ni el tope duro de
3x): el ratio de este caso ya cumplía la regla, así que bajar más los
topes no habría arreglado nada — el ajuste correcto era de redacción, no
de proporción. Si se repite el patrón tras esto, el siguiente paso
razonable es añadir un ejemplo concreto de "problema + solución fusionados
en un párrafo" a la lista de 13 ejemplos del system prompt
(`buildSystemPrompt()`), que pesan más que cualquier regla general (ver
JERARQUÍA).

`tests-bg.js` gana un test que verifica que `buildUserMessage()` incluye
esta instrucción.

---

## 16. El objetivo en sí estaba demasiado alto, no solo el tope (v2.2.15)

Dos casos reales seguidos, en la misma sesión que el §15:

- Comentario de @macoliytb (253 car.) → respuesta de 618 car., ratio 2.44x.
- Comentario de @torrizgz (253 car.) → respuesta de 704 car., ratio 2.78x.

Ambos cumplen el objetivo 2x-3x vigente entonces (y el segundo también
quedaba lejos del tope duro de 3x = 759). El usuario los marcó como
"demasiado largo" igualmente. Esta vez, antes de tocar nada, se le
preguntó directamente — dos preguntas con `AskUserQuestion`: si la
extensión instalada estaba actualizada (respuesta: no lo había mirado) y
si, independientemente de la versión, el objetivo numérico debería
bajarse (respuesta: sí, bajar el objetivo).

Esto confirma algo que las rondas anteriores (§12, 5x→4x→3x) solo
tocaban a medias: bajar el **tope** no sirve de nada si el **objetivo**
sigue siendo el mismo rango generoso, porque el modelo escribe para el
objetivo, no para el tope — el tope solo actúa como red de seguridad
cuando el modelo se pasa claramente, no cuando cumple el objetivo al pie
de la letra y aun así resulta largo para el gusto del usuario.

Cambio: el objetivo pasa de 2x-3x a **1.5x-2x**, y el tope duro baja de
3x a **2x** (mismo criterio que en el §12: tope real = extremo superior
del objetivo, sin margen entre ambos). Tocado en tres sitios, que deben
mantenerse sincronizados:

- `vetReply()` en `content.js` (el chequeo que de verdad bloquea).
- El reintento automático de acortado en `content.js` (`topeLongitud`).
- `buildUserMessage()` en `background.js` (orientación al modelo,
  incluida la mención literal "dos veces el comentario").

Si se repite el patrón otra vez tras esto, ya no queda recorrido en la
fórmula sin estrechar también el mínimo del objetivo (1.5x): el siguiente
paso razonable sería 1x-1.5x, aceptando que el estilo por defecto sea
mucho más breve y reservando el desarrollo largo solo para los ejemplos
9/10/12/13 del system prompt cuando el comentario de verdad lo exige.

`tests-bg.js` y `tests.js` actualizados con los números nuevos (150/200
en vez de 200/300 para el mismo comentario de prueba; tope de fila 0
recalculado a 84×2=168).

---

## 17. Escape para cerrar una caja vacía se despachaba en `document`, nunca llegaba (v2.2.14)

Caso real: el usuario reportó "Hay un cuadro de respuesta abierto que no
se ha podido cerrar. Ciérralo y vuelve a pulsar." en una caja **confirmada
vacía** (si tuviera texto, el mensaje habría sido el otro: "con texto
escrito"). Pidió explícitamente que, en ese caso, el sistema la cerrase
solo y publicase, en vez de darse por vencido.

Causa raíz, no cosmética: `closeOpenBoxes()` intenta primero un botón
"Cancelar" reconocible (`CANCEL_TEXTS`); si no lo encuentra, su único
plan B era `document.dispatchEvent(new KeyboardEvent("keydown", {key:
"Escape", bubbles: true}))`. Un evento despachado directamente sobre
`document` **solo invoca listeners atados al propio `document`** (o a
`window` en fase de captura) — los eventos burbujean hacia ARRIBA desde
su origen real hacia sus ancestros, nunca hacia abajo hacia los
descendientes. Si Studio escucha Escape en el campo o en un componente
Angular/CDK ancestro suyo (lo habitual: overlays y cajas de edición
suelen manejar su propio cierre por teclado en el propio elemento, no en
`document`), ese despacho **no llegaba nunca**, por vacía que estuviera
la caja. No era un problema de reintentos ni de timing: el mecanismo en
sí no podía funcionar salvo que Studio tuviera un listener global en
`document`, que evidentemente no tiene.

Arreglado en `closeOpenBoxes()` (`content.js`): ahora, para cada campo
vacío que sigue visible, se le da el foco (como haría un usuario real) y
se despacha el Escape **sobre el propio campo** (`keydown` + `keyup`),
que sí burbujea por sus ancestros reales. Con reintento (hasta 2 veces,
350ms entre intentos) por si una caja recién montada tarda un ciclo en
registrar su listener.

No se ha forzado "publicar igualmente si no se cierra": sigue siendo
necesario que la caja realmente se cierre antes de continuar (abortar
con el mensaje de siempre si, tras esto, aún no se ha cerrado). La razón
no cambia: `publish()` usa `before.size === 0` para aceptar un campo que
se renderiza fuera de la fila (ver comentario en el Paso 2 de `publish()`)
precisamente para no confundirlo con una caja ajena que siga abierta —
publicar a ciegas con una caja fantasma presente reintroduciría el riesgo
de escribir en la fila equivocada que el propio diseño existe para
evitar. El arreglo correcto no es saltarse la salvaguarda: es hacer que
el cierre funcione de verdad, que es lo que hacía falta.

`pruebas/harness.js` gana la opción `sinBotonCancelar`: omite el botón
"Cancelar" y simula el listener real de Angular atado al propio campo
(nunca a `document`), para poder probar el camino de Escape de forma
realista — con el código viejo (despacho en `document`), este test
habría fallado exactamente con el mismo "no se ha podido cerrar" que
reportó el usuario. Nuevo test en `tests.js`.

---

## 18. Revisión integral del proyecto (v2.2.16)

Petición explícita del usuario: revisar todo el proyecto (no solo el
último diff), encontrar errores reales y consolidar el código. Se usó el
skill `code-review` a esfuerzo máximo con corrección automática
(`--fix`), con doble verificación posterior manual (lectura del diff
línea a línea + las dos suites de pruebas re-ejecutadas de forma
independiente, no solo el autoinforme del propio review).

**Corregido:**

- **Timeout de `GENERATE_REPLY` demasiado corto (`content.js`).** `send()`
  usaba su timeout genérico de 45 s para un mensaje que en `background.js`
  puede legítimamente tardar mucho más: hasta 3 reintentos con backoff
  (0/1.5/4 s) y 120 s de timeout de API **cada uno**. Con razonamiento
  extendido activado (por defecto) y la API bajo carga, una sola llamada
  podía superar 45 s sin que hubiera ningún fallo real — el content script
  se rendía con "no ha respondido" mientras el service worker seguía
  trabajando, y el resultado, al llegar tarde, se descartaba en silencio.
  Añadida `GEN_REPLY_TIMEOUT_MS = 150000` (150 s) para los 4 puntos donde
  se envía `GENERATE_REPLY` (generación inicial, reintento de fuga,
  reintento de acortado, y "Regenerar" del panel). No cubre el peor caso
  teórico absoluto (~366 s si los 3 reintentos agotan su propio timeout de
  120 s cada uno) — subir a ese nivel haría que un fallo real tardase más
  de 6 minutos en reportarse, un coste peor que el beneficio para un caso
  límite raro (fallos repetidos de la API tipo 529/503). 150 s es una
  cobertura pragmática del caso real reportado (razonamiento extendido
  lento, sin reintentos), no una garantía matemática del peor caso.

- **`extractCommentText()` descartaba comentarios reales de 1-4
  caracteres (`content.js`).** El umbral `t.length > 4` se aplicaba
  también cuando el texto venía de un selector YA conocido y de confianza
  (`TEXT_SELECTORS`), no solo del recorrido ciego genérico donde ese
  umbral tiene sentido (evitar confundir una etiqueta de interfaz como
  "Me gusta" con el comentario real). Un comentario como ":)", "+1" u
  "Ok" se perdía para siempre, sin aviso, dejando la fila sin botón.
  Corregido: el selector conocido acepta cualquier texto no vacío
  (`t.length > 0`); el umbral de `>10` del recorrido genérico de
  respaldo no se toca, sigue cumpliendo su función original.

- **"Regenerar" del panel no usaba el cerrojo `state.busy` (`content.js`).**
  Solo deshabilitaba su propio botón mientras esperaba la API, así que
  "Publicar" seguía activo en el mismo panel: un clic ahí durante una
  regeneración en vuelo podía arrancar `publish()` en paralelo —
  exactamente el escenario que el cerrojo de `runFlow()` existe para
  evitar en el resto de la extensión, pero que este botón en concreto se
  había quedado sin él. Ahora usa el mismo patrón que "Publicar" ya tenía
  (`state.busy` + deshabilita todos los `.yra2-act` del panel + libera en
  `finally`). De paso, se quita un campo `nonce` que este botón enviaba a
  `background.js` sin que nadie lo leyera ahí (resto de limpieza).

- **Toast y cuenta atrás se superponían en la misma esquina
  (`content.js`).** `.yra2-countdown` y `.yra2-toast` comparten
  exactamente `right:24px; bottom:24px` en `styles.css`, y el countdown
  tiene mayor z-index. Si una cuenta atrás estaba visible en una fila
  cuando se mostraba el aviso "Hay una respuesta en curso" (clic en otra
  fila), el toast quedaba completamente tapado — invisible justo en el
  caso en que más falta hace verlo. Ahora el toast se apila por encima
  (`bottom: 110px`) cuando detecta un `.yra2-countdown` visible. Nota
  honesta: esto es un ajuste visual en CSS/posicionamiento; la suite de
  pruebas corre en jsdom, que no hace layout real, así que esta parte no
  queda verificada por los tests — solo por lectura de código.

- **`handleDiagnose()` lanzaba las cinco estrategias en serie
  (`background.js`).** Irónicamente, la herramienta de diagnóstico de
  transcripción acababa siendo más lenta que `fetchTranscript()`, el
  propio camino que diagnostica (que ya las lanza en paralelo) — y
  penalizaba más el caso de fallo, justo cuando más urge un diagnóstico
  rápido. Reescrito con `Promise.all()`, igual que `fetchTranscript()`.
  Riesgo de regresión propio de este cambio: `Promise.all()` no garantiza
  que las promesas se *resuelvan* en orden, solo que el array de
  resultados conserva el orden de *entrada* — si el informe se hubiera
  construido iterando por orden de llegada en vez de por el array
  devuelto, se habría perdido el orden de prioridad de las estrategias.
  Nuevo test en `tests-bg.js` que verifica explícitamente que el orden se
  conserva.

**Encontrado pero NO corregido (quedan como hallazgos documentados):**

- **`closeOpenBoxes()` puede cerrar la caja vacía de OTRA fila.** El
  ascenso de hasta 8 niveles de ancestros en busca de un botón "Cancelar"
  no tiene ningún límite de alcance por fila (a diferencia de
  `findThreadRoot()`, que sí acota por tamaño/número de openers): con dos
  cajas vacías abiertas a la vez, podría encontrar primero el "Cancelar"
  de la fila equivocada. Impacto acotado (nunca toca una caja con texto,
  solo vacías, así que no hay riesgo de perder un borrador), y arreglarlo
  bien requeriría una búsqueda acotada por fila como la de
  `findThreadRoot()` — no algo para parchear a ciegas sin confirmar el
  alcance real del DOM con `diagnostico-dom.js` primero, siguiendo la
  política ya establecida de este proyecto.

- **`conTope()` no aborta el `fetch()` subyacente al expirar
  (`background.js`).** Una estrategia de transcripción que supera su
  timeout sigue consumiendo red/CPU de fondo aunque la carrera ya haya
  resuelto con el error de timeout. Arreglarlo bien requiere enhebrar un
  `AbortController` por cada función de estrategia (`tracksFromStudio`,
  `tracksFromInnertube`, `tracksFromWatch`...), un cambio estructural
  mayor que no encaja en un parche puntual de esta revisión.

Ambos hallazgos sin corregir son de impacto bajo (ni pérdida de datos del
usuario ni respuesta incorrecta publicada) y se documentan aquí en vez de
parchearse de forma apresurada.

Verificación: 45/45 pruebas de `tests-bg.js` y 40/40 de `tests.js`, las
dos suites re-ejecutadas de forma independiente tras el review (no solo
el autoinforme del propio proceso de revisión).

---

## 19. Respuesta con el contexto de OTRO vídeo, y respuesta con emoticono (v2.2.17)

### El caso real

19/10/2026. Comentario «top!» (de @HNWIRelocator) en el vídeo «Así los ricos
ESCONDEN su bitcoin en una SOCIEDAD». La extensión publicó un párrafo sobre
«supply chain attack», Ledger y «comprar siempre en el fabricante oficial»:
el tema de otro vídeo del canal. El texto era coherente, bien escrito y
proporcionado (cumplía todas las salvaguardas de `vetReply()`), pero hablaba
del vídeo equivocado. Era el mismo síntoma que el caso Hyperliquid / Travel
Rule que §8 del traspaso dejaba como «sin confirmar, probablemente versión
vieja». No era la versión vieja: era un defecto de diseño que seguía en la
2.2.16.

### Causa (confirmada leyendo el código, no deducida del síntoma)

`getVideoId(rowRoot)` y `getVideoContext(rowRoot)` construían una lista de
ámbitos `[fila, padre, abuelo, ... (6 niveles)]` y devolvían el **primer**
`img` con `/vi/<id>/` o el primer enlace con id de vídeo (y el primer título)
que encontraban recorriendo esa lista. Dentro de la fila eso es correcto.
Pero en la bandeja de Comunidad > Comentarios, el **padre de una fila es la
lista con todas las filas**. En cuanto la búsqueda dentro de la propia fila
fallaba por cualquier motivo —miniatura con carga diferida y todavía sin
`src`, enlace no renderizado, fila reciclada por la virtualización de la
lista—, el siguiente ámbito era la lista entera y el «primer match» era la
miniatura de la **primera fila**, normalmente el vídeo más reciente del
canal. Transcripción, título y, por tanto, respuesta: todos del vídeo
equivocado, y todos coherentes entre sí, por lo que ninguna salvaguarda lo
detectaba. El comentario, en cambio, se leía bien (sale de `row`, sin subir),
de ahí que la respuesta «contestara» al comentario correcto con el contexto
incorrecto.

Que el comentario fuera «top!» (sin contenido) hizo el síntoma más visible:
el modelo rellenó la respuesta con la transcripción que tenía, que era la de
Ledger.

### Corrección

Nueva función `getVideoInfo(rowRoot)` (sustituye a las dos anteriores) con
una regla explícita: **un ámbito solo vale si no contiene ninguna otra fila
de comentario y en él aparece un único vídeo.**

- `rowScopes()`: la fila y, como mucho, los ancestros que **no engloben otra
  fila** (`containsOtherRow()`: otro `ytcp-comment-thread` que no sea el
  nuestro ni lo contenga; de respaldo, cualquier `THREAD_TAGS`/`[comment-id]`
  ajeno). Esto admite un envoltorio «hilo + miniatura» si Studio lo tuviera,
  y se para en la lista, siempre.
- `videoIdsInScope()`: conjunto de vídeos distintos en el ámbito (miniaturas
  `/vi/` y `/vi_webp/`, enlaces `/video/`, `?v=`, `/shorts/`, `/live/`,
  `youtu.be`, con límite de 11 caracteres acotado). Si hay **dos o más** →
  ambiguo → `videoId = null` y `title = null`, y no se sube más (subir solo
  puede empeorar). Si hay uno → ese. Si no hay ninguno → siguiente ámbito.
- Datos de página (`location.href`, `h1`, `document.title`, descripción)
  **solo** cuando la URL es la de los comentarios de un vídeo
  (`/video/<id>/comments` o `?video_id=`). En la bandeja del canal no se
  usan nunca: antes, `extractPageTitle()` podía devolver el `h1` de la
  página como «título del vídeo».
- Sin vídeo identificado → `FETCH_TRANSCRIPT` no se pide, motivo «no se ha
  podido identificar el video de esta fila [sin ambiguedad]» → con
  `requireTranscript` (por defecto) la respuesta pasa a revisión. Es el
  comportamiento deseado: mejor pedir revisión que publicar sobre otro vídeo.
- El log `[YRA2] Contexto` incluye `videoSource` (`fila`, `ancestro N`,
  `pagina`, `ambiguo`, `ninguno`) para poder diagnosticar un caso nuevo sin
  pedir nada más.

`diagnostico-dom.js` incorpora la sección **4b**: para las primeras cuatro
filas dice qué vídeos, imágenes y título hay dentro del hilo y cuántos
vídeos distintos ve en el padre. Es lo que hay que pedir al usuario si
vuelve a aparecer un cruce.

### Lo que NO se ha verificado

El DOM real de la bandeja no se ha vuelto a inspeccionar en esta ronda (no
había sesión de Studio disponible). La corrección no depende de la
estructura exacta: en cualquiera de las dos posibles (miniatura dentro del
hilo o en un envoltorio hermano) el resultado es el vídeo de la fila o
`null`, nunca el de otra fila. Las cinco pruebas nuevas de «VIDEO DE LA
FILA» cubren ambas estructuras, la miniatura sin cargar, el envoltorio y la
página de un solo vídeo. Si en el DOM real la miniatura no cuelga ni del
hilo ni de un envoltorio sin otras filas, el efecto será «sin
transcripción → revisión» en todas las filas: visible de inmediato en la
primera prueba y diagnosticable con la sección 4b.

### Respuesta con emoticono (petición del usuario)

Los comentarios de solo emoticonos («👏👏👏», «🔥») o de elogio corto
(«top!», «grande Sergi, crack») no piden una respuesta argumentada, y
pedírsela al modelo es justo lo que produjo el párrafo sobre Ledger. Ahora
se contestan con un emoticono: `esComentarioDeReaccion()` en `content.js`,
ajustes `emojiReply` (true) y `emojiReplyText` («🤙», el gesto de
Ronaldinho, elegido por el usuario) en `DEFAULTS` de `content.js`,
`background.js` y `popup.js`, y en el popup.

Criterio, deliberadamente conservador:

1. Nunca es reacción si contiene `?` o `¿` (una pregunta siempre va al
   modelo).
2. Se quitan los emoticonos (`\p{Extended_Pictographic}`, modificadores,
   banderas, ZWJ, VS16, keycap) y se normaliza (minúsculas, sin acentos).
3. Si no queda nada → reacción (solo emoticonos o signos).
4. Si quedan hasta ocho palabras y **todas** están en `VOCAB_REACCION`
   (elogio y relleno: «gracias», «grande», «crack», «muy», «el», «sergi»…)
   o son risas (`jajaja`, `xd`) → reacción. Una sola palabra fuera del
   vocabulario («pero», «no», «tengo», «duda», «721») → modelo.

El camino de reacción se evalúa tras la salvaguarda 1 (cajas cerradas) y
antes de pedir vídeo o transcripción: no llama a `FETCH_TRANSCRIPT` ni a
`GENERATE_REPLY`. Respeta el modo (en revisión abre el panel con el
emoticono y una etiqueta «comentario de reaccion · emoticono»), la cuenta
atrás y `likeOnPublish`. `vetReply()` no se aplica (un emoticono de un solo
code unit daría «respuesta vacía»); la inserción y la verificación de
`publish()` son las de siempre (`norm()` no toca emoticonos, comprobado).

Sobre la estrategia, para que conste: responder a todo con emoticonos no
«posiciona» por sí mismo; lo que YouTube mide es la interacción total del
vídeo (comentarios, respuestas, likes, tiempo de visualización). Una
respuesta del creador cuenta como comentario y suele provocar más
interacción, así que un emoticono rápido a los elogios tiene sentido como
volumen barato, siempre que las preguntas de verdad sigan recibiendo texto.
Por eso el criterio excluye cualquier cosa con contenido.

### Pruebas

Seis pruebas nuevas de «COMENTARIOS DE REACCION» y cinco de «VIDEO DE LA
FILA» en `tests.js` (51 en total). `harness.js` admite `comentarios`,
`sinMiniaturaEn`, `miniaturaFuera` y `url`, y el mock de `chrome.runtime`
guarda ahora `payloads` (tipo + payload de cada mensaje) para poder afirmar
**qué** vídeo se ha pedido, no solo que se ha pedido algo. `tests-bg.js`
sin cambios (45/45).

---

## 20. Los emoticonos del comentario llegaban vacíos: Studio los pinta como `<img>` (v2.2.18)

Caso real, el mismo día de instalar la 2.2.17: comentario «👏👏👏»
(@perrocosmicoblanco13) contestado con «Parece que no hay comentario aquí
:)». Eso no es un fallo del camino del emoticono: es el modelo contestando a
un comentario vacío. Causa: en el DOM real de Studio los emoticonos del
comentario no son texto sino `<img class="emoji" alt="👏" src="…">`, así que
`txt(#content-text)` (innerText) devolvía «». `extractCommentText()` seguía
entonces con la búsqueda genérica (el texto hoja más largo de la fila, con
más de 10 caracteres), que devolvía una etiqueta de la interfaz («2
suscriptores», «hace 7 días») o el título del vídeo, y eso iba al modelo.

Corrección: `textWithEmoji(root)` recorre los nodos del comentario y compone
el texto con los nodos de texto, el `alt` de cada `<img>`, `\n` por `<br>` y
por bloque. Se usa para todos los `TEXT_SELECTORS` (con `txt()` de
respaldo). Además, si un selector conocido encuentra el nodo del comentario
pero no se le saca texto, `extractCommentText()` devuelve `null` (la fila
aborta con «No se ha podido leer el texto del comentario») en vez de caer en
la búsqueda genérica: antes era preferible publicar algo, ahora sabemos que
ese «algo» era contestar a una etiqueta.

Tres pruebas nuevas en «COMENTARIOS DE REACCION»: emoticonos-imagen → 🤙 sin
llamar al modelo; texto + emoticono-imagen («Grande 🔥») → reacción, y una
pregunta con emoticono-imagen llega al modelo con el emoticono dentro del
texto; nodo de comentario sin texto legible → aborta sin llamar al modelo.
54/54 y 45/45.


---

## 21. Botón «🚫 Buscar estafas» (v2.3.0)

Petición del usuario (19/10/2026): en sus vídeos entran unos diez comentarios
de estafa por vídeo (enjambres de bots: «gracias a la persona X gané dinero»,
WhatsApp/Telegram de un «asesor», el cebo «Bitensity is a position» con
respuestas de cuentas que lo confirman) y quería quitarlos de un tirón
**desde YouTube Studio**. Antes se probó una vía por Telegram (motor de Apps
Script + bot del Content OS en el repo blindaje-patrimonial); el usuario
prefirió Studio y esa vía quedó parada (`estafas_modo = off`).

Diseño, con el principio de §2 («nunca sin certeza») trasladado a la
moderación: **la extensión solo selecciona; la acción la hace el usuario**
con la barra de acciones nativa de Studio. Nada irreversible sin su clic.

- `injectScamButton()` (llamado en `activate()`, retirado en `deactivate()`):
  botón fijo abajo a la izquierda, lejos de toasts y cuenta atrás.
- `scamUnits()`: cada nodo `#content-text` visible es un comentario; su
  «unidad» es el ancestro más alto que no contiene otro `#content-text`. Hilo
  = `ytcp-comment-thread`. Autor con `scamAutor()` (selectores de atributo
  `[id='author-text']`…: jsdom no resuelve `#id` repetidos dentro de un
  elemento y Chrome sí; con atributo funcionan los dos). Los del propio canal
  (`/sergi[\s_.-]?andr[eé]s/i`) se excluyen.
- Clasificación: `scamReglas()` (mismas reglas que `estafas.py` del Content
  OS, con límites de palabra Unicode `(?<![\p{L}\p{N}_])`: el `\b` de JS no
  entiende acentos) + `scamEnjambre()` (≥3 cuentas distintas citando el
  mismo nombre propio en un hilo → todo el hilo) + Claude para los dudosos
  (`CLASSIFY_SCAMS` en `background.js`, lotes de 40, modelo del popup, sin
  razonamiento, temperatura 0, «ante la duda, NO es estafa»). Si la API
  falla, se aplican solo las reglas y el panel lo dice.
- `scamCheckbox()`: sube desde el texto; en el primer ancestro con casillas,
  si hay una y el ámbito no contiene otro comentario, es esa; si hay varias,
  la que está a la altura del comentario (|dy| < 60 px y 30 px de margen
  con la segunda); si no hay certeza, `null` → se marca en rojo y el panel
  dice «sin casilla reconocible». Una casilla ya marcada no se toca.
- Panel (`showScamPanel`): recuento, lista con motivo, «No es estafa»
  (desmarca y quita el rojo), «Ver» (scroll) y «Quitar todas las marcas».

**No verificado contra el DOM real**: qué elemento es la casilla de Studio y
dónde cuelga. `diagnostico-dom.js` tiene la sección **4c** para eso. Si en la
primera prueba sale «sin casilla reconocible», pedir esa sección.

Pruebas: 9 nuevas en «BUSCAR ESTAFAS» (`tests.js`) y 4 en `tests-bg.js`;
`harness.js` admite `casillas`, `autores` y `respuestas`, y el mock contesta
`CLASSIFY_SCAMS` (`scamVeredictos`, `scamFalla`). `SOLO=texto node tests.js`
ejecuta solo las pruebas cuyo nombre lo contiene (la batería completa tarda
varios minutos). `tests-bg.js` da al sandbox `setInterval`/`clearInterval` y
`chrome.runtime.getPlatformInfo` (el latido del service worker).


---

## 22. Aprendizaje: cada respuesta publicada se guarda y la IA escribe con las reales (v2.4.0)

Petición del usuario (26/10/2026), con un caso real: respondió a mano a una
crítica («Tío metes mucho humo…») con «cuando he dicho yo eso? si la gracia de
comprar p2p es no decir nada :)», justo lo contrario de la regla fija del
prompt («ante críticas: nunca defensivo… cierra con humildad»). Quería que lo
que responde a mano, o lo que retoca de la IA, se guarde y vaya mejorando el
modelo sin hacer nada.

**Captura (content.js, sección 11).**
- `onClickEnviar`, en fase de captura sobre `document` (se pone en
  `activate()` y se quita en `deactivate()`): si el clic cae en el botón de
  enviar de una caja con texto (`findSubmitButton(field)` de esa caja, nunca
  un «Responder» sin pulsar) y no lo está pulsando la extensión
  (`state.publicando`, que pone el envoltorio de `publish()`), espera hasta 10 s
  a que Studio confirme el envío (la caja desaparece o se vacía). Solo
  entonces guarda la fila con el comentario al que contesta
  (`comentarioDeCaja`: el último `#content-text` del hilo ANTES del campo, que
  vale también para responder a una respuesta).
- `tipo`: «a_mano»; «editada» si el texto del campo lo había metido la IA
  (`state.textoIA`, puesto en `publishInner` tras `insertText`) y Sergi lo
  cambió; «ia» si lo envía igual. El panel guarda «ia» o «editada» comparando
  con lo que propuso la IA (`generado`, que «Regenerar» actualiza). `runFlow`
  guarda «ia». El camino del emoticono no guarda nada.
- `guardarRespuesta()` → mensaje `GUARDAR_RESPUESTA` → `background.js`: cola en
  `chrome.storage.local` (`ytrCola`, máximo 500) y envío en lote
  (`{yt:'guardar_lote'}`) al motor de BD VÍDEOS (Apps Script, aplicación web,
  `apps-script/v3/YouTubeRespuestas.gs` del repo blindaje-patrimonial). Si no hay
  clave o conexión, queda en la cola y sale con la siguiente.

**Uso (background.js, sección 1c).** `contextoAprendido()` pide al motor
`{yt:'contexto', n:500}` (reglas del documento + respuestas reales, las
escritas o retocadas por Sergi primero) y lo cachea una hora en `ytrContexto`.
`elegirEjemplos()` puntúa por palabras clave en común (sin acentos ni palabras
vacías), longitud parecida del comentario y tipo (+0,25 a_mano/editada, −0,15
ia), sin repetir respuestas. Con 8 o más ejemplos o con reglas,
`buildSystemPrompt(…, aprendido)` sustituye el bloque fijo entre «PATRÓN DE
RESPUESTA» y «PRECISIÓN (regla dura» (patrón, 13 ejemplos, jerarquía y «cómo
escribes») por: reglas del documento, las 10 respuestas reales más parecidas
(las editadas, como «La IA propuso… Sergi lo cambió y publicó…»), jerarquía
nueva (lo que hace Sergi manda) y tres reglas por defecto. PRECISIÓN,
SEGURIDAD, PROHIBIDO y FORMATO no se tocan. Sin conexión ni caché: los 13 fijos.

**Lado Google (repo blindaje-patrimonial).** Pestaña YOUTUBE_RESPUESTAS (id,
fecha, video_id, video_titulo, autor, comentario, respuesta_ia,
respuesta_final, tipo, fuente, comment_id, archivado). Histórico: el motor
recorrió los 15.593 hilos del canal y guardó las 2.469 respuestas de Sergi
(desde 2022), emparejando cada una con el comentario al que contesta
(«@usuario» al principio → el último comentario de esa persona en el hilo).
Después, cada hora, las 2 primeras páginas (respuestas dadas fuera de la
extensión, fuente «youtube»). El bot (`src/bp/contentos/youtube_respuestas.py`)
archiva las nuevas en el documento y cada semana reescribe REGLAS APRENDIDAS
con Claude; la sección REGLAS DE VOZ la escribe Sergi y no se toca.

Pruebas: 5 e2e nuevas en «APRENDIZAJE» (`tests.js`, 68 en total) y 5 en
`tests-bg.js` (54). El mock de `chrome.runtime` contesta `GUARDAR_RESPUESTA`.


---

## 23. Limpieza automática de estafas y hate, sin botón (v2.5.0)

Petición del usuario (29/10/2026), con captura de Studio («Te recomiendo en
paralelo, un curso de ESPAÑOL» con el menú ⋮ abierto): no quiere botones
aparte (ni el de estafas de la v2.3.0); quiere que al usar «Responder con IA»
se vaya limpiando todo solo, también el hate, y que se bloquee a esa gente.
Se le propuso ocultar del canal con 5 s para cancelar o solo marcar; eligió
**«Ocultar sola, sin aviso»**.

**Diseño (content.js, sección 10).**
- Disparo: `runFlow` → `finally` → `setTimeout(limpiezaAutomatica, 200)`. Así
  nunca toca menús mientras se escribe o se publica una respuesta; si aun así
  hay un flujo en curso (`state.busy`), se aplaza al siguiente clic.
- Qué revisa: `scamUnits()` (cada `#content-text` visible), sin los del canal
  (`OWN_AUTHOR_RE`), sin los ya revisados (`claveComentario` = autor + texto
  normalizado, en `state.revisados` y en `chrome.storage.local.yraRevisados`,
  máximo 4.000) ni los ya ocultos. Reglas y enjambre de la v2.3.0 → «estafa»
  sin llamar a Claude; el resto, `CLASSIFY_COMMENTS` (lotes de 40) → `tipo`
  estafa · hate · ok. Si la API falla, valen las reglas y los no clasificados
  se reintentan la próxima vez.
- Cómo oculta (`ocultarDelCanal`): `menuDe(u)` busca en el hilo los botones de
  icono con aria-label tipo «Acción/Más/More/Opciones» o icono «more/vert», y
  coge el que tiene a ESTE comentario como `#content-text` inmediatamente
  anterior en orden de documento (vale para el menú del principal en la barra
  de acciones y para el de cada respuesta). Clic → espera la opción
  «Ocultar del canal» (`OCULTAR_RE`, hasta 3 s) → clic → si sale un diálogo,
  pulsa el botón de confirmar (`CONFIRMAR_RE`, hasta 1,5 s). Nunca «Quitar».
  Sin menú o sin la opción: Escape, rojo con el motivo y fila con «error» en
  la hoja.
- Registro: `GUARDAR_OCULTADO` → `background.js` (cola `ytrOcultados`) →
  motor `{yt:'ocultados'}` → pestaña YOUTUBE_OCULTADOS de BD VÍDEOS (fecha,
  autor, comentario, tipo, motivo, video_id, video_titulo, resultado; lo más
  nuevo arriba). Toast final «🧹 N ocultados del canal (x estafa, y hate)».
- Prompt (`SCAM_SYSTEM` en background.js): define ESTAFA, HATE y OK, con la
  regla de que las críticas con argumentos son OK (Sergi las contesta) y
  «ante la duda, ok», porque no hay revisión humana. `parseScamVerdicts`
  devuelve `tipo` y sigue aceptando el formato `{estafa: true}`.
- Ajuste `limpieza` (true por defecto) en el popup. `diagnostico-dom.js` §4d
  lista los botones de icono de los dos primeros hilos y cuál tomaría como
  menú, y las opciones visibles si el menú está abierto.

**No verificado contra el DOM real**: el aria-label o el icono del ⋮ de
Studio, el texto exacto de la opción (la captura muestra «Ocultar del canal»)
y si pide confirmación. Si en Studio sale en rojo «no encuentro el menú ⋮» o
«el menú no tiene…», pedir la sección 4d.

Pruebas: «BUSCAR ESTAFAS» (9, del botón) sustituidas por 8 de «LIMPIEZA
AUTOMATICA» (67 en total). `harness.js`: menú ⋮ por comentario (principal en
la barra de acciones; respuestas después de la barra, como en Studio),
`sinOcultar`, `confirmarOcultar`, `scamVeredictos` devuelve el tipo, y
`chrome.storage.local.set` del mock guarda de verdad.


---

## 24. Studio recicla las cajas de la lista: la limpieza podía ocultar a otro (v2.5.1)

Caso real (29/10/2026, captura de Sergi): con el filtro «Estado de respuesta:
Sin responder», la etiqueta «🧹 Oculto del canal · hate: Burla sobre el
español de Sergi» (era del comentario «Te recomiendo en paralelo, un curso de
ESPAÑOL») apareció pegada a «Sandbox?», de @Miguel_Joves_De_Luca. Causa: al
publicar una respuesta, ese comentario deja de cumplir el filtro y Studio
(lista de Polymer) reutiliza las mismas cajas para los de debajo. La v2.5.0
guardaba la caja (`u.el`) al clasificar y la usaba después para abrir el ⋮ y
para la etiqueta: si la lista se movía entre medias, el ⋮ y la etiqueta eran
de otro comentario. No hay forma de saber desde la extensión a quién se
ocultó ese día (la clave del motor no estaba puesta y YOUTUBE_OCULTADOS
quedó vacía): Sergi lo comprueba en Studio → Configuración → Comunidad →
Usuarios ocultos.

Corrección:
- `esperarCalma()` (MutationObserver: sin cambios en 800 ms, máximo 5 s)
  antes de empezar a ocultar y entre uno y otro (400 ms / 3 s).
- `resolverActual(u)`: si la caja ya no tiene el mismo texto y autor, busca
  el comentario en la página por `claveComentario`; si no está, se aplaza.
- `ocultarDelCanal` comprueba `sigueIgual(u)` antes de abrir el ⋮ y otra vez
  con el menú abierto, justo antes de pulsar «Ocultar del canal». Si ha
  cambiado: Escape, `reintentar`, no se marca como revisado ni se apunta.
- Marcas atadas al texto (`data-yra2-texto` en la etiqueta y en la unidad);
  `quitarMarcasMovidas()` en cada `scan()` borra las que han quedado en un
  comentario distinto.

Prueba nueva: `reciclar: true` en `harness.js` (al publicar, el texto y el
autor de cada caja pasan a ser los de la siguiente y la última desaparece) y
`doc.__ocultados` registra el autor que había en la caja al pulsar «Ocultar»:
tiene que ser solo el del hate.
