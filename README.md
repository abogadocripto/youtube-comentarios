# YouTube Reply Assistant v2.2.4

> **¿Vienes a retomar el desarrollo?** Lee `TRASPASO.md` primero. Contiene el
> estado real del proyecto, los dos problemas abiertos, las hipótesis ordenadas
> y lo que ya está descartado. Este README es solo el manual de uso.

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
2. Saca el `videoId` de la miniatura de la fila y descarga la transcripción.
3. Llama a la API con tu prompt de estilo.
4. Revisa el texto generado (vacío, fugas del prompt, muletillas prohibidas).
5. Abre el cuadro de respuesta **de esa fila**.
6. Escribe el texto y **comprueba que está realmente dentro**.
7. Espera a que se habilite el botón de enviar, que es la prueba de que
   YouTube ha registrado el texto.
8. Te da unos segundos para cancelar.
9. Envía y confirma que el cuadro se ha cerrado.

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
