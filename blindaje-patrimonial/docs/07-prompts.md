# 07 — Prompts

> Los prompts viven como ficheros en `prompts/` y el código los carga tal cual. Esta página explica cómo están construidos y por qué.

| Fichero | Uso | Versión |
|---|---|---|
| `prompts/daily.system.md` | Sistema del Daily (se cachea) | daily-v1.0 |
| `prompts/daily.user.md` | Plantilla Jinja2 del mensaje de usuario del Daily (fact sheet + feedback de validación en los reintentos) | daily-v1.0 |
| `prompts/weekly.system.md` | Sistema del Weekly (se cachea) | weekly-v1.0 |
| `prompts/weekly.user.md` | Plantilla del mensaje de usuario del Weekly | weekly-v1.0 |
| `prompts/alert.system.md` | Borrador de alerta por noticia | alert-v1.0 |
| `prompts/classify.system.md` | Clasificación de noticias y documentos | classify-v1.0 |
| `prompts/verify.system.md` | Verificador independiente (Daily, Weekly y alertas) | verify-v1.0 |

## 1. Criterios de diseño

1. **Contexto antes que órdenes.** Cada prompt explica para quién se escribe (patrimonio, España y Andorra, no traders), la pregunta editorial que responde y por qué existen las reglas. Los modelos actuales siguen mejor una regla cuando entienden su propósito.
2. **Pocas reglas duras, inequívocas y comprobables por código.** Cada regla "sin excepción" tiene un validador que la hace cumplir (doc 08). El prompt reduce la tasa de error y el validador garantiza el resultado.
   - "No escribas ninguna cifra" → V-NUM.
   - "Solo hechos seleccionados" → V-SEL.
   - "Cita literal" → V-QUOTE.
   - "Sin predicciones" → V-LEX + verificador.
3. **El texto de terceros se declara como datos.** Documentos y noticias van dentro de etiquetas (`<fact_sheet>`, `<weekly_input>`) y se advierte explícitamente de que pueden contener instrucciones que hay que ignorar. El clasificador marca `injection_suspected`.
4. **Salida solo JSON con esquema.** La forma la garantiza la salida estructurada; el prompt se centra en el contenido.
5. **Tono con ejemplos de contraste** (✘/✔), tomados del propio encargo: "Tiene que sonar a alguien que protege patrimonio, no a crypto Twitter".
6. **Estabilidad para la caché.** El prompt de sistema no contiene nada variable (ni fechas ni datos); todo lo variable va en el mensaje de usuario.

## 2. Montaje de cada llamada

```
system:   [daily.system.md]  (cache_control: ephemeral)
messages: [ {role: user, content: render(daily.user.md, fact_sheet_json=…, validation_feedback=None)} ]
output_config: {format: <daily_output.schema.json vía Pydantic>, effort: "high"}
thinking: {type: "adaptive"}
fallbacks: "default"  (beta server-side-fallback-2026-07-01)
```

**Bucle de reintento** (máximo 1 en el Daily y 2 en el Weekly):
1. Validación determinista y verificador (doc 08).
2. Si hay fallos bloqueantes, se construye `validation_feedback` en lenguaje llano, con la ruta y el problema ("lectura[1]: contiene la cifra '3' fuera de marcador; usa {{fa:etf_flow_streak_days}}").
3. Nueva llamada con **el mismo fact sheet** y el feedback en el mensaje de usuario.
4. No se reenvía la respuesta anterior: se pide una versión nueva y corregida, lo que evita arrastrar errores.

## 3. Ejemplo de principio a fin (Daily)

Entrada: `schema/examples/daily_input.example.json`, con datos ficticios pero realistas. Muestra:
- ETF con la 3.ª sesión de salidas;
- OI +7,1 % con el precio plano;
- F&G de 71 a 58.

Salida del LLM: `schema/examples/daily_output.example.json`.

Mensaje final renderizado (`schema/examples/daily_rendered.example.html`, generado por el renderizador real; 2.250 caracteres visibles, 1,5–2 min de lectura). Los bloques ETF y derivados solo aparecen si se obtienen las licencias L3–L4; sin ellas, el filtro de licencias los retira:

```
☀️ BITCOIN MORNING BRIEF · Miércoles, 23 sep 2026 · 🤖 Lectura elaborada con IA

₿ Bitcoin
$101.250 · 86.540 €
24 h: +0,3 % · 7 d: −2,4 % (en euros: −0,6 %)
Máximo histórico: $126.080 (6 oct 2025) · −19,7 % · 352 días

🧠 Sentimiento
Miedo y Codicia: 58 — neutral · ayer 61 · hace 7 días 71 (fuente: alternative.me)
El índice pasa de 71 a 58 en siete días: el mercado se enfría sin llegar al miedo.

🌊 Liquidez
Liquidez global: 🟢 expansión (M2 global a agosto, provisional) · liquidez EE. UU. 4 sem.: +1,5 %

🏦 Demanda ETF · sesión del martes 22 sep
Flujo neto: −$420 M · 5 sesiones: −$610 M · 3.ª sesión seguida de salidas
Indicador de demanda a través de productos regulados, no de compras o ventas institucionales.

⚡ Derivados
Funding: +0,012 %/8 h · Interés abierto 24 h: +7,1 % (en BTC)
El apalancamiento crece sin movimiento de precio.

🌡️ Liquidez 🟢 · Demanda 🔴 · Apalancamiento 🔴 · Sentimiento 🟢

🧭 La lectura
Bitcoin apenas se mueve, pero bajo la superficie cambian dos cosas: los ETF encadenan 3 sesiones seguidas de salidas y el interés abierto sube un 7,1 % sin que el precio acompañe. Es una combinación que suele reflejar más posicionamiento apalancado que demanda de contado, y que aumenta la sensibilidad a movimientos bruscos en el corto plazo. El fondo no ha cambiado: la liquidez global sigue en expansión y el sentimiento se ha normalizado tras salir de la zona de codicia.

👀 Hoy vigilaría…
Si los ETF vuelven a registrar salidas: con el apalancamiento al alza, la demanda de contado es hoy la variable que más pesa.

ℹ️ Información general. No es asesoramiento financiero, fiscal ni jurídico personalizado ni una recomendación de inversión, y no tiene en cuenta tu situación. Los criptoactivos son volátiles y se puede perder todo lo invertido. Texto interpretativo generado por IA a partir de los datos citados; las cifras se insertan automáticamente desde las fuentes. ABAST y sus profesionales pueden mantener posiciones en bitcoin (declaración de intereses en el enlace). Datos a 23/09 08:50: CoinGecko · alternative.me · cálculo propio (Reserva Federal, BCE, BoE, PBoC, BoJ) · cálculo propio (Reserva Federal, Tesoro de EE. UU., Fed de Nueva York) · SoSoValue · Coinalyze. Metodología, aviso legal y declaración de intereses
```

Notas sobre el ejemplo:
- Las cifras de "La lectura" (3 y 7,1 %) **no las escribió el LLM**. El texto original dice `{{fa:etf_flow_streak_days}}` y `{{fa:oi_chg_24h_pct}}`.
- Al construir este ejemplo, el renderizado destapó dos defectos que se corrigieron en el contrato:
  - incrustar una pista completa producía redundancias ("…de salidas en los ETF" repetido);
  - usar el valor con signo tras un verbo producía "sube +7,1 %".

  De ahí nacen el marcador `{{fa:…}}` y la recomendación de parafrasear las pistas. Es el tipo de detalle que el conjunto de evaluación debe vigilar.
- Este ejemplo corresponde al **escenario B**, con ETF y derivados licenciados. En el escenario A desaparecen esos bloques y aparece "🏛️ Tipos y dólar" y/o "🔗 On-chain" según su *salience*.

## 4. Mantenimiento de los prompts

- **Una persona responsable** (editor): las modificaciones se hacen en ficheros versionados, nunca en caliente en producción.
- **Antes de subir una versión:**
  - pasar el conjunto de evaluación (doc 08 §7);
  - comparar la tasa de validación, los veredictos del verificador y la valoración a ciegas del editor.
- **Señales para revisar un prompt:**
  - más del 10 % de Dailies necesitan reintento;
  - el editor corrige más de 1 texto por semana;
  - el verificador marca de forma recurrente el mismo tipo de problema.
