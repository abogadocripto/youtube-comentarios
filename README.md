# YouTube Reply Assistant v2.3.0

> **¿Vienes a retomar el desarrollo?** Lee `TRASPASO.md` primero. Contiene el
> estado real del proyecto, los dos problemas abiertos, las hipótesis ordenadas
> y lo que ya está descartado. Este README es solo el manual de uso.

## Novedades en 2.3.0 — botón «🚫 Buscar estafas»

En la página de comentarios aparece un botón rojo abajo a la izquierda,
**🚫 Buscar estafas**. Al pulsarlo revisa los comentarios **cargados** en
pantalla (principales y respuestas) y detecta los de estafa: teléfono o
WhatsApp/Telegram de un «asesor», testimonios de ganancias «gracias a» una
persona, y enjambres (tres o más cuentas citando el mismo nombre en un hilo,
más el comentario cebo que lo abre, tipo «Bitensity is a position»). Los
dudosos los revisa Claude (sin razonamiento extendido, temperatura 0). Los
comentarios del propio canal nunca se marcan.

A los que son estafa los **marca en rojo y les marca la casilla de Studio**.
No borra ni denuncia nada: con las casillas marcadas, Studio enseña arriba su
barra de acciones y ahí eliges tú (eliminar, denunciar spam u ocultar al
usuario del canal). En el panel puedes quitar uno («No es estafa»), ir a él
(«Ver») o quitar todas las marcas. Solo ve lo cargado: baja hasta el final
para que Studio cargue más y vuelve a pulsar. Detalle en `TRASPASO.md` §21.

## Novedades en 2.2.18 — los emoticonos del comentario se leen (Studio los pinta como imágenes)

Caso real, nada más instalar la 2.2.17: a «👏👏👏» se le contestó «Parece
que no hay comentario aquí :)». Studio no pinta los emoticonos como texto
sino como imágenes (`<img alt="👏">`), así que el texto del comentario
llegaba vacío, la búsqueda genérica de respaldo cogía una etiqueta de la
interfaz («2 suscriptores», «hace 7 días») y eso era lo que recibía el
modelo. Ahora el texto del comentario se compone recorriendo los nodos y
sustituyendo cada imagen por su `alt`, con lo que «👏👏👏» se lee como tal y
entra por el camino del emoticono. Además, si el nodo del comentario existe
pero no se le saca texto, se aborta con aviso en vez de caer en la búsqueda
genérica. Detalle en `TRASPASO.md` §20.

## Novedades en 2.2.17 — el vídeo de la fila, nunca el de otra; respuesta con emoticono

**Corregido el cruce de vídeos.** Caso real: a un «top!» en el vídeo «Así los
ricos ESCONDEN su bitcoin en una SOCIEDAD» se le contestó un párrafo sobre
Ledger y ataques a la cadena de suministro, el tema de otro vídeo. La
extensión buscaba la miniatura y el título del vídeo subiendo hasta seis
niveles por encima de la fila y se quedaba con el **primer** resultado. En
la bandeja de Comunidad > Comentarios, el padre de una fila es la lista con
todas las filas: si la miniatura de la fila aún no había cargado (o el
enlace no estaba renderizado), el «primer resultado» era la miniatura de la
primera fila de la lista, normalmente el vídeo más reciente. Ahora solo se
mira dentro de la fila (y, como mucho, en un envoltorio que no contenga otras
filas); si en el ámbito aparecen dos vídeos distintos, se considera ambiguo
y no se usa ninguno. Sin vídeo identificado no hay transcripción, y con «No
publicar sola si falta la transcripción» (por defecto) la respuesta pasa a
revisión. En la consola, la línea `[YRA2] Contexto` muestra ahora
`videoSource` (`fila`, `ancestro N`, `pagina`, `ambiguo` o `ninguno`).
Detalle en `TRASPASO.md` §19.

**Respuesta con emoticono.** Los comentarios de solo emoticonos («👏👏👏») o
de elogio corto («top!», «grande Sergi, crack») ya no pasan por el modelo: se
contestan con el emoticono configurado en el popup (por defecto 🤙), con la
misma cuenta atrás, el mismo modo (revisión o automático) y el «me gusta».
Nunca se aplica a un comentario con una pregunta ni a uno con palabras que
no sean de elogio o relleno conocido. Se puede desactivar en el popup.

**Diagnóstico ampliado.** `diagnostico-dom.js` incluye una sección 4b que
dice, para las primeras filas, qué miniaturas, enlaces y título hay dentro
de cada hilo y cuántos vídeos distintos ve en el padre. Si sospechas otro
cruce de vídeos, pásalo y pega la salida.

## Novedades en 2.2.16 — revisión integral del proyecto

Review completo a máximo esfuerzo (no solo el último diff) con corrección
automática y doble verificación manual posterior. Cinco bugs reales
corregidos: timeout de `GENERATE_REPLY` demasiado corto para razonamiento
extendido bajo carga, comentarios reales de 1-4 caracteres descartados
por `extractCommentText()`, el botón "Regenerar" del panel sin el
cerrojo `state.busy` que ya tenía "Publicar", toast tapado por la cuenta
atrás en la misma esquina, y `handleDiagnose()` lanzando sus cinco
estrategias en serie en vez de en paralelo. Dos hallazgos de impacto bajo
quedan documentados sin corregir (no parcheados a ciegas). Detalle
completo en `TRASPASO.md` §18.

## Novedades en 2.2.15 — objetivo de longitud bajado a 1.5x-2x (tope real 2x)

Dos casos reales seguidos cumplían el objetivo 2x-3x (ratios 2.44x y 2.78x,
ambos por debajo del tope de 3x) y aun así el usuario los vio largos.
Confirmado directamente con él: el objetivo en sí estaba puesto demasiado
alto, no solo el tope. Bajado el rango completo a 1.5x-2x, con el tope
duro ahora en 2x (mismo criterio que la bajada anterior: tope real =
extremo superior del objetivo, sin margen entre ambos). Afecta a
`vetReply()` y al reintento de acortado en `content.js`, y a la
orientación del prompt en `buildUserMessage()` (`background.js`). Detalle
en `TRASPASO.md` §16.

## Novedades en 2.2.14 — Escape para cerrar una caja vacía se despachaba en `document`, nunca llegaba

Caso real: "Hay un cuadro de respuesta abierto que no se ha podido
cerrar" en una caja confirmada vacía (sin texto de borrador). Causa: el
intento de cierre por Escape despachaba el evento en `document`, que solo
invoca listeners atados al propio `document` — nunca llega a un listener
en el campo o sus ancestros, que es donde Angular/CDK suele escucharlo.
Ahora se despacha sobre cada campo (con foco primero, como un usuario
real), con reintento. Detalle en `TRASPASO.md` §17.

## Novedades en 2.2.13 — un párrafo nuevo es para un punto nuevo, no para cada paso del mismo punto

Caso real: comentario de 253 caracteres, respuesta de 618 (ratio 2.44x,
dentro del objetivo 2x-3x) y aun así el usuario la vio larga — no por
proporción, sino porque el segundo y el tercer párrafo desarrollaban el
mismo punto ("problema al volver a fiat" + "cómo evitarlo") partido en
dos párrafos en vez de uno. El prompt ya pedía fusionar puntos
secundarios, pero no decía nada sobre no partir el desarrollo de un único
punto en varios párrafos. Añadida esa instrucción explícita en
`buildUserMessage()` (`background.js`). Detalle en `TRASPASO.md` §15.

## Novedades en 2.2.12 — reintento automático también para la fuga de prompt

Caso real: una respuesta con fuga de prompt (repetía literalmente
"COMENTARIO A RESPONDER") se descartaba siempre a la primera con el panel
de error, sin darle al sistema la oportunidad de arreglarlo solo — a
diferencia de los problemas de longitud, que ya reintentaban automático
desde la 2.2.11. Ahora `runFlow()` reintenta hasta 2 veces con un aviso
explícito de no repetir encabezados del prompt (`payload.evitarFuga`)
antes de rendirse y mostrar el panel. Detalle en `TRASPASO.md` §14.

## Novedades en 2.2.11 — reintento automático en vez de panel a la primera

Caso real: el tope absoluto de "respuesta muy larga" (2000 caracteres)
interrumpió con el panel. El usuario no quiere seguir viendo ese panel por
este motivo — quiere que el sistema lo arregle solo primero. Ahora, si las
únicas incidencias son de longitud (nunca si hay fuga de prompt, muletilla
u otro problema real), se reintenta la generación hasta 2 veces con un
aviso reforzado de brevedad antes de rendirse y mostrar el panel. El
chequeo original sigue siendo la red de seguridad final: si el modelo no
coopera tras los 2 intentos, se abre el panel igual que antes. Detalle en
`TRASPASO.md` §13.

## Novedades en 2.2.10 — tope bajado a 3x, por petición directa

Tras la 2.2.9 (tope a 4x), el usuario pidió bajarlo directamente a 3x sin
esperar a ver si 4x repetía el patrón. Aplicado en `vetReply()`
(`content.js`) y en la orientación del prompt (`buildUserMessage()`,
`background.js`). Con esto el tope real coincide exactamente con el extremo
superior del objetivo (2x-3x): ya no hay margen entre "objetivo" y "límite
absoluto". Si hiciera falta bajar más, el objetivo mismo tendría que
estrecharse también — no queda recorrido en la fórmula actual.

## Novedades en 2.2.9 — el tope de proporción de 2.2.8 era demasiado permisivo

Caso real traído por el usuario: comentario de 315 caracteres, respuesta
publicada de 1514 (4.81x) — por debajo del tope de 5x de la 2.2.8, así que
no se bloqueó, pero a simple vista se veía claramente desproporcionada. El
modelo tendía a acercarse al tope en vez de quedarse en el objetivo real
(2x-3x). Dos cambios:

- **Tope duro: 5x → 4x** (mínimo 200 sin cambios) en `vetReply()`
  (`content.js`) y en la orientación del prompt (`background.js`).
- **Prompt más directivo**: ya no solo avisa del tope — pide decidir los
  2-3 puntos que de verdad hay que responder y resumir o fusionar el
  resto, dejando claro que un comentario corto con una pregunta densa no
  es licencia para desarrollar cada concepto por separado.

Detalle completo del diagnóstico en `TRASPASO.md` §12.

## Novedades en 2.2.8 — longitud proporcional al comentario

Pedido directo del usuario: algunas respuestas salían demasiado largas para
comentarios cortos. Dos capas, no una sola:

- **Orientación suave en el prompt** (`buildUserMessage`, `background.js`):
  se le dice al modelo, con las cifras concretas ya calculadas a partir del
  comentario, que ronde entre el doble y el triple de su longitud — "no
  rígido, puede salirse si el comentario lo pide de verdad".
- **Tope duro real** (`vetReply()`, `content.js`): si aun así la respuesta
  supera la proporción permitida (con un mínimo de 200 caracteres para no
  castigar comentarios de pocas palabras), **no se autopublica** — pasa a
  revisión en el panel, igual que ya hacía el chequeo preexistente de
  "respuesta muy larga" (>2000 caracteres), que sigue intacto y es
  independiente de este.

## Novedades en 2.2.5–2.2.7 — revisión exhaustiva con verificación adversarial

Ronda de revisión a fondo de todo el proyecto (10 agentes en paralelo por
dimensión; 25 hallazgos brutos, cada uno refutado adversarialmente por 3
verificadores independientes antes de aplicarse — solo 5 sobrevivieron la
verificación completa). 17 hallazgos confirmados y corregidos en total,
entre ellos uno crítico: `publish()` no releía el contenido del campo entre
la cuenta atrás y el clic real de envío, así que un cambio de texto durante
esos segundos se publicaba sin haber sido verificado. También: una condición
de carrera en el plan B de inserción y otra en la caché de transcripción
(ambas podían mezclar el trabajo de dos filas/pestañas), una defensa contra
inyección de instrucciones desde comentarios de terceros, la API key dejó de
llegar al content script, y el banco de pruebas ya no modela un
`id="submit-button"` que el DOM real confirmado nunca tiene. Detalle
completo, incluido lo refutado y lo que queda pendiente, en `TRASPASO.md`
§11.

73 pruebas en verde (36 en `tests.js`, 37 en `tests-bg.js`).

## Novedades en 2.2.4 — el campo real ya está confirmado y corregido

El usuario ejecutó `diagnostico-dom.js` contra Studio real: **el campo de
respuesta es un `<textarea>`, no un `contenteditable`** (ya no es hipótesis).
Esto invalidaba tanto la detección (`FIELD_SELECTOR`) como la inserción
(`execCommand` con selección de `Range`, que no aplica a un `<textarea>`).
Corregido con los datos exactos del diagnóstico:

- `FIELD_SELECTOR` detecta ahora el `<textarea>` real dentro de `ytcp-commentbox`.
- La inserción usa el setter nativo de `HTMLTextAreaElement.prototype.value` +
  eventos `input`/`change`, tanto en `content.js` como en el plan B
  (`handleInsertMain` en `background.js`).
- La lectura del contenido (verificación, detección de borradores a medias,
  confirmación de envío) usa `.value` en vez de `.innerText` cuando el campo
  es un `<textarea>`.
- El banco de pruebas reproduce ahora esta estructura exacta (textarea sin
  `id`, botón de enviar sin `id`, solo texto "Responder") en vez del modelo
  antiguo — ver `pruebas/tests.js`, sección "CAMPO REAL".

Ver `TRASPASO.md` para el detalle completo y lo que queda por confirmar (los
botones de reacción / "me gusta", sección 6 del diagnóstico, que se cortó
antes de llegar).

Nueva función pedida por el usuario: dar "me gusta" al comentario justo
después de publicar la respuesta. Ajuste "Dar 'me gusta' al comentario al
publicar la respuesta" en el popup (activado por defecto). Es "best effort" a
propósito: busca un botón visible con `aria-label` o texto "me gusta"/"like"
cerca del comentario, excluyendo "no me gusta", "corazón" (la reacción propia
del canal) y los botones de la extensión. **Tampoco verificado contra Studio
real** — si no encuentra un candidato con confianza razonable, se omite en
silencio y la respuesta se publica igual; nunca puede hacer fallar ni
deshacer una publicación ya confirmada. `diagnostico-dom.js` (sección 6, ya
ampliada) es lo que confirmará el selector real.

## Novedades en 2.2.2

Endurecido `publish()` contra los tres candidatos de la hipótesis H1/H2/H3 del
traspaso, sin necesitar acceso real al DOM de Studio (son correcciones de
lógica, no de selectores nuevos):

- **Confirmación de envío por dos señales, no una.** Antes, "el campo ha
  desaparecido" se interpretaba como "se ha publicado". Ahora se exige
  también que el botón de enviar se haya deshabilitado, desconectado u
  ocultado. Evita el falso positivo descrito en el síntoma ("desaparece la
  ventana y no pasa nada").
- **Comprobación de conexión justo antes de pulsar enviar.** Si la página ha
  cambiado durante la cuenta atrás, se aborta en vez de publicar a ciegas
  sobre un nodo que ya no existe.
- **`findSubmitButton` acotado a la fila.** Antes subía por los ancestros del
  campo sin límite de contexto; ahora busca primero dentro de la fila ya
  identificada, y solo si no lo encuentra ahí recurre a la subida por
  ancestros (acotada, como antes).
- **La desactivación al cambiar de ruta se aplaza mientras se está
  publicando.** Un cambio de URL interno de Studio en pleno envío ya no
  puede borrar el panel o la cuenta atrás a media publicación.

Con estos cambios: 31 pruebas de `tests.js` (antes 24) y 33 de `tests-bg.js`,
todas en verde. Sigue aplicando la misma advertencia de siempre: esto no ha
podido probarse contra el DOM real de Studio. Ver `TRASPASO.md` para el
siguiente paso.


Versión nueva y completa. No sustituye nada de la v1: usa otro nombre, otros
prefijos de CSS (`yra2-`) y otro almacenamiento, así que las dos pueden convivir
mientras pruebas.

---

## Instalación

1. Descomprime la carpeta donde quieras dejarla de forma permanente. Chrome lee
   los ficheros de ahí cada vez que arranca: si la mueves o la borras, la
   extensión deja de funcionar.
2. Ve a `chrome://extensions`.
3. Activa **Modo de desarrollador** (arriba a la derecha).
4. **Desactiva la v1** con su interruptor. Si dejas las dos activas verás dos
   botones en cada comentario.
5. **Cargar descomprimida** → selecciona la carpeta.
6. Abre el icono de la extensión, pega tu API key y pulsa **Probar conexión**
   antes de **Guardar**.

### La API key hay que meterla a mano

`chrome.storage` está aislado por extensión: la v1 y la v2 tienen IDs distintos
y almacenamientos separados, así que la v2 **no puede leer** la key de la v1.

Para recuperar la de la v1: `chrome://extensions` → con la v1 activada, pulsa el
enlace **«service worker»** de su tarjeta → en la Consola que se abre, ejecuta

```js
chrome.storage.sync.get(null, r => console.log(r))
```

y copia el valor de `apiKey`.

Alternativa preferible: crea una key nueva en
[console.anthropic.com](https://console.anthropic.com/settings/keys) y revoca la
antigua cuando la v2 funcione. Esa key ha estado replicándose por `storage.sync`
a todos los Chrome con tu cuenta de Google iniciada, y con dos keys distintas
puedes separar el consumo de cada extensión mientras pruebas en paralelo.

---

## Qué hace el botón

Pulsas **Responder con IA** una sola vez. A partir de ahí:

1. Lee el comentario del DOM en ese instante.
2. Si el comentario es solo emoticonos o un elogio corto, salta al paso 5 con
   el emoticono configurado (sin modelo ni transcripción).
3. Saca el `videoId` de la miniatura o el enlace **de esa fila** (nunca de la
   lista) y descarga la transcripción.
4. Llama a la API con tu prompt de estilo.
5. Revisa el texto generado (vacío, fugas del prompt, muletillas prohibidas).
6. Abre el cuadro de respuesta **de esa fila**.
7. Escribe el texto y **comprueba que está realmente dentro**.
8. Espera a que se habilite el botón de enviar, que es la prueba de que
   YouTube ha registrado el texto.
9. Te da unos segundos para cancelar.
10. Envía y confirma que el cuadro se ha cerrado.

**Si cualquier paso falla, aborta y no publica.** Abre el panel con el texto ya
escrito, y además lo deja en el portapapeles.

---

## Ajustes

**Modo.** Tres opciones, cada una dice exactamente qué pasa al pulsar:

- *Publica sola, con margen para frenar* — recomendada. Todo automático, con N
  segundos para cancelar. `Esc` también cancela.
- *Publica sola, al instante* — sin margen. La respuesta sale sin que la leas.
- *Nunca publica sola* — abre el panel y pulsas tú.

**No publicar sola si falta la transcripción.** Activada por defecto. Sin
transcripción el modelo no sabe qué dijiste en el vídeo, así que esas respuestas
pasan siempre por tu revisión aunque el modo sea automático.

**Modelo.** Por defecto `claude-sonnet-4-6`, el que ya usabas. Si eliges uno que
tu cuenta no tenga habilitado, **Probar conexión** te lo dice antes de que lo
descubras a mitad de una tanda.

**Razonamiento extendido.** Mejor criterio técnico, entre 5 y 15 segundos más
por respuesta. Para comentarios de una línea puedes apagarlo.

**Responder con un emoticono a los comentarios de solo emoticonos o elogio
corto.** Activado por defecto, con 🤙. Un «top!», «👏👏👏» o «grande Sergi»
se contesta con ese emoticono (o el texto corto que pongas) sin llamar al
modelo. Cualquier comentario con una pregunta o con palabras que no sean de
elogio sigue yendo al modelo.

**Contexto del vídeo.** Se añade a todas las respuestas. Útil cuando trabajas
los comentarios de un solo vídeo.

**Instrucciones permanentes.** Se añaden al final de tu prompt de estilo,
siempre. Por ejemplo: no mencionar nombres de clientes.

---

## Diferencias con la v1

| | v1 | v2 |
|---|---|---|
| Arranque | Solo si cargabas la URL de comentarios de cero | Siempre, al entrar en Comunidad desde cualquier sitio |
| Clics para publicar | 3 o 4 | 1 |
| Identificación del cuadro | El último `contenteditable` visible de la página | El que aparece tras pulsar, dentro de esa fila |
| Espera tras abrir | 1200 ms fijos | Sondeo hasta que aparece |
| Verificación | Ninguna | Contenido releído + botón de enviar habilitado |
| Transcripción | Regex frágil, 3.000 caracteres | Parseo JSON, 5 fuentes, 4 formatos, 15.000 caracteres, con caché |
| Longitud de respuesta | «Máximo 4 líneas», en contra de tus propios ejemplos | Proporcional al comentario |
| Modelo | El popup decía Haiku, el código usaba Sonnet | Lo eliges y se puede probar |
| API key | `storage.sync`, replicada a todos tus Chrome | `storage.local`, solo este navegador |
| Panel | Barra fija arriba, tapaba el primer comentario | Anclado bajo el comentario, acompaña al scroll |

---

## Errores y qué significan

### Si dice «sin transcripción»

Abre el popup → despliega **Diagnóstico de transcripción** → pega el ID o la URL
del vídeo → **Ejecutar**, con la pestaña de Studio abierta.

Prueba las cinco vías de obtención y los cuatro formatos de descarga, y dice
exactamente cuál falla y con qué código. Pulsa **Copiar informe**: no incluye
tokens de sesión, solo su longitud.

| Mensaje | Qué ha pasado | Qué hacer |
|---|---|---|
| Hay un cuadro de respuesta abierto con texto escrito | Tenías un borrador a medias en otra fila. No se ha tocado. | Envíalo o descártalo |
| Al pulsar Responder no se ha abierto ningún cuadro | El botón no ha reaccionado | Mira la consola: la traza dice qué botón se pulsó |
| La caja se ha abierto pero fuera de esta fila | Se abrió un cuadro que no pertenece al comentario | No escribe nada. Cierra cuadros abiertos y reintenta |
| YouTube ha recargado la lista de comentarios | Angular reemplazó la fila durante la llamada | Vuelve a pulsar el botón |
| El botón de enviar sigue deshabilitado | El texto se ve pero YouTube no lo ha registrado | Está escrito: púlsalo tú |
| El modelo X no existe o no está disponible | Tu cuenta no tiene ese modelo | Cambia de modelo en los ajustes |
| YouTube ha encontrado los subtítulos pero no deja descargarlos | Las pistas existen; el endpoint `timedtext` devuelve vacío | Ejecuta el diagnóstico |
| El vídeo no tiene subtítulos publicados | Ninguna vía encuentra pistas | Genera subtítulos en Studio, o rellena «Contexto del vídeo» |

**Para diagnosticar:** F12 → Consola → filtra por `YRA2`. Cada paso deja rastro:
qué fila, qué método de inserción ha funcionado, y por qué no ha publicado sola.

---

## Lo que esta versión no puede garantizar

La publicación se hace pulsando botones del DOM de YouTube Studio, que no es
código nuestro. Si Google cambia la estructura de esa página, los pasos 5 a 7
dejarán de encontrar lo que buscan.

Lo que sí está garantizado es el comportamiento ante ese fallo: **aborta y no
publica**. Nunca publica vacío, nunca en la fila equivocada, nunca a medias.

Si en algún momento necesitas certeza real en el envío, la vía es la YouTube
Data API v3 (`comments.insert` con el `comment-id` como `parentId`), que
convierte el paso final en una llamada HTTP sin DOM de por medio. Requiere OAuth
y un proyecto en Google Cloud.

---

## Detalle menor

Si YouTube aplana los saltos de párrafo al insertar respuestas largas, la
verificación lo da por bueno igualmente (compara ignorando espacios en blanco),
pero lo avisa en consola. Si lo ves, dilo y se cambia la inserción a párrafo por
párrafo.
