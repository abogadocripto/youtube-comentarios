# Banco de pruebas

Requiere Node 18+ y jsdom.

```bash
npm install jsdom
node tests.js      # 68 pruebas (SOLO=texto para filtrar por nombre): flujo de publicacion, DOM, salvaguardas, SPA
node tests-bg.js   # 54 pruebas: parseo, transcripcion, prompts, errores de API
```

`harness.js` monta un YouTube Studio simulado. Reproduce lo esencial del
comportamiento de Angular: el boton de enviar arranca deshabilitado y solo se
habilita cuando el campo recibe un evento `input` de verdad.

Variantes del simulador (parametro `studio` en cada prueba):

| Opcion | Que simula |
|---|---|
| `campoExtra: true` | Un segundo contenteditable en la caja (overlay de menciones) |
| `soloPuntero: true` | Boton que reacciona a `mousedown` y no a `click` |
| `angularRegistersInput: false` | El framework nunca registra el texto escrito |
| `submitStartsEnabled: true` | El boton de enviar ya viene habilitado |
| `openDelay: N` | Milisegundos que tarda la caja en aparecer |
| `rows: N` | Numero de comentarios en la lista |
| `comentarios: [...]` | Textos de las filas (p.ej. solo emoticonos o elogios cortos) |
| `sinMiniaturaEn: [i, ...]` | Filas cuya miniatura aun no tiene `src` ni enlace al video (carga diferida) |
| `miniaturaFuera: true` | La miniatura cuelga de un envoltorio hermano del hilo, no del hilo |
| `casillas: true` | Casilla de selección de Studio (`ytcp-checkbox-lit`, `aria-checked`) en cada comentario |
| `autores: [...]` / `respuestas: {i: [[autor, texto], ...]}` | Autor de cada fila y respuestas de cada hilo |
| `url: "..."` | URL de la pagina simulada (bandeja del canal por defecto; `/video/<id>/comments` para la pagina de un video) |

AVISO: que las pruebas pasen no significa que funcione en Studio. Significa que
la logica es coherente con el modelo de DOM que se supuso. Ese modelo es
justamente lo que esta en duda. Ajusta `harness.js` al DOM real que revele
`diagnostico-dom.js` antes de fiarte de estos numeros.
