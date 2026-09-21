# Banco de pruebas

Requiere Node 18+ y jsdom.

```bash
npm install jsdom
node tests.js      # 24 pruebas: flujo de publicacion, DOM, salvaguardas, SPA
node tests-bg.js   # 33 pruebas: parseo, transcripcion, prompts, errores de API
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

AVISO: que las pruebas pasen no significa que funcione en Studio. Significa que
la logica es coherente con el modelo de DOM que se supuso. Ese modelo es
justamente lo que esta en duda. Ajusta `harness.js` al DOM real que revele
`diagnostico-dom.js` antes de fiarte de estos numeros.
