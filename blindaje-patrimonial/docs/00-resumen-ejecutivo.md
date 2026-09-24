# 00 — Resumen ejecutivo

**Proyecto:** Sistema automático de inteligencia patrimonial (Blindaje Patrimonial).
**Productos:**
- Daily Bitcoin (Telegram, 09:00);
- Informe semanal (email);
- Alertas patrimoniales.

**Estado:** diseño técnico completo (docs 01–12, con configuración y esquemas validados) y desarrollo iniciado. Fecha: 23–24 sep 2026.

## 1. Las cinco conclusiones que condicionan todo

1. **La licencia de los datos decide la fuente, no el precio.** El canal y la newsletter son públicos y comerciales. Casi todos los datos gratuitos prohíben mostrarlos a terceros:
   - planes gratuitos de proveedores de precio;
   - APIs de exchanges;
   - índices bursátiles;
   - Glassnode y Coin Metrics.

   El diseño lo resuelve con cálculo propio (nodo Bitcoin + BRK para on-chain; fórmulas propias sobre series oficiales), datos oficiales reutilizables (Tesoro, Reserva Federal, Fed de Nueva York, BCE, BoE) y **pocos proveedores con licencia comercial expresa**. Un filtro de código impide publicar cualquier dato cuya fuente no lo permita (doc 02).
2. **El LLM nunca escribe cifras.** Escribe marcadores (`{{f:etf_net_flow_usd_1d}}`) que el sistema sustituye por valores de la base de datos. En el Weekly, cada afirmación lleva una **cita literal** de la fuente, y el código comprueba que existe. Encima hay 27 validadores deterministas, un verificador LLM independiente y revisión humana en el Weekly y las alertas (docs 06–08).
3. **El Daily se publica siempre a las 09:00 si hay precio**, con degradación elegante:
   - sin LLM → lectura por plantillas;
   - sin una métrica → se omite su bloque.

   Nunca se publica un dato caducado como actual. La publicación es idempotente y un timeout ambiguo de Telegram no se reintenta a ciegas (docs 01 y 09).
4. **Reglamento de IA:** el art. 50.4 se aplica desde el 2 ago 2026 (el Digital Omnibus no lo modificó). El Daily, publicado sin revisión humana, lleva **"🤖 Lectura elaborada con IA" en su primera línea**. El Weekly y las alertas exigen **revisión sustantiva de un abogado identificado** y congelación del contenido aprobado mediante hash (doc 11).
5. **El producto no asesora.** Información general sin recomendaciones personalizadas ni específicas:
   - MiCA art. 3.1.24;
   - la Llei andorrana 24/2022, más amplia;
   - semáforo por **ejes** (liquidez, macro, demanda, apalancamiento, sentimiento) y **nunca** de compra o venta;
   - declaración de intereses pública (MiCA art. 91.3.c);
   - léxico vetado bloqueante (docs 04 y 11).

## 2. Qué verá el lector

Ejemplo real generado con el contrato validado (datos ficticios; doc 07 §3):

```
☀️ BITCOIN MORNING BRIEF · Miércoles, 23 sep 2026 · 🤖 Lectura elaborada con IA
₿ Bitcoin  $101.250 · 86.540 € · 24 h: +0,3 % · 7 d: −2,4 % (en euros: −0,6 %)
Máximo histórico: $126.080 (6 oct 2025) · −19,7 % · 352 días
🧠 Sentimiento  Miedo y Codicia: 58 — neutral · ayer 61 · hace 7 días 71 (fuente: alternative.me)
🌊 Liquidez  🟢 expansión (M2 global a agosto) · liquidez EE. UU. 4 sem.: +$84 mm
🏦 Demanda ETF · sesión del martes  −$420 M · 5 sesiones: −$610 M · 3.ª sesión de salidas
⚡ Derivados  Interés abierto 24 h: +7,1 % (en BTC)
🧭 La lectura  Bitcoin apenas se mueve, pero bajo la superficie cambian dos cosas: los ETF encadenan
3 sesiones seguidas de salidas y el interés abierto sube un 7,1 % sin que el precio acompañe…
👀 Hoy vigilaría…  Si los ETF vuelven a registrar salidas: con el apalancamiento al alza, la demanda
de contado es hoy la variable que más pesa.
```

**Weekly:**
- "La semana en 60 segundos": 3 puntos;
- frente financiero;
- frentes fiscal, regulatorio y protección, con "Qué ha pasado / Por qué importa / A quién afecta / Qué deberías vigilar" o "Sin cambios relevantes esta semana";
- agenda.

## 3. Coste mensual orientativo

| Escenario | Qué incluye | Coste total |
|---|---|---|
| **A · mínimo licencia-limpio** | Precio y ATH, sentimiento, liquidez y tipos oficiales, on-chain propio, calendario, noticias, Weekly | **140–240 €** |
| **B · recomendado** | A + ETF, derivados y saldos en exchanges (CoinGlass Standard, 299 $, si confirma por escrito la difusión pública) | **430–580 €** |
| **C · completo** | B + licencia del Nasdaq-100 (150–500 $, sin confirmar) | **580–1.070 €** |

Si SoSoValue y Coinalyze dan permiso gratuito con atribución, el escenario B cuesta casi lo mismo que el A.

## 4. Arquitectura en un párrafo

Una aplicación Python 3.12 organizada en capas deterministas (ingesta → análisis → selección → LLM → validación → editorial → distribución), sobre PostgreSQL 16. Se despliega con Docker en un VPS de la UE (Hetzner), con temporizadores de systemd en hora de Madrid, *dead-man switch* (Healthchecks) y copias cifradas. Un servidor aparte ejecuta el nodo Bitcoin y BRK. Claude (`claude-opus-5`, salida estructurada, sin herramientas) solo interpreta datos ya validados. Un bot privado de Telegram permite al equipo previsualizar, aprobar, corregir y retener. Trazabilidad completa: de cada cifra publicada se llega a la respuesta HTTP original, con su hash y su licencia (docs 01 y 03).

## 5. Lo que necesito del despacho (bloquea el lanzamiento)

1. **Decisiones:**
   - sociedad editora y responsable editorial (abogado);
   - declaración de intereses;
   - escenario de datos (A o B);
   - nombre del canal;
   - textos legales finales (doc 11 §7 y §10).
2. **Gestiones de licencia** (doc 02 §7):
   - contratar CoinGecko Basic;
   - confirmaciones escritas de CoinMarketCap, SoSoValue, Coinalyze y CoinGlass;
   - permiso del Banco de Japón.
3. **Infraestructura y credenciales** (doc 12 §3): VPS en la UE, clave de la API de Anthropic, bots y canales de Telegram, Brevo, subdominio de envío.
4. **Revisión jurídica** de los puntos [VERIFICAR] del doc 11, en especial Andorra (AFA) y las directrices del art. 50.

## 6. Índice de la documentación

| Doc | Contenido |
|---|---|
| 01 | Arquitectura técnica, orquestación, despliegue, observabilidad, seguridad |
| 02 | Métricas, fuentes, licencias, costes, gestiones previas (+ `config/metrics.yaml`) |
| 03 | Modelo de datos (+ `schema/schema.sql`, validado en PostgreSQL 16) |
| 04 | Reglas matemáticas de interpretación, semáforo por ejes, *salience*, "Hoy vigilaría…" (+ `config/rules.yaml`) |
| 05 | Noticias: fuentes, prefiltro, clustering, scoring, Weekly, alertas (+ `config/news_sources.yaml`, `config/calendar/regulatory.yaml`) |
| 06 | Contrato JSON con el LLM (+ `schema/llm/*.schema.json`, `schema/examples/`) |
| 07 | Prompts (+ `prompts/*.md`) y ejemplo de principio a fin |
| 08 | Validación anti-alucinaciones: cinco capas, validadores, batería adversarial, evaluación |
| 09 | Telegram: canal, plantillas, publicación, correcciones, bot de edición |
| 10 | Newsletter: proveedor, flujo, consentimiento, entregabilidad |
| 11 | Cumplimiento normativo y riesgos del propio producto |
| 12 | Plan de desarrollo, dependencias y decisiones pendientes |

## 7. Límites de este trabajo

- **Endpoints sin probar en vivo.** Las APIs de datos no se pudieron llamar desde el entorno de diseño (bloqueo de red). Los endpoints, precios y términos se verificaron con búsqueda web, réplicas oficiales en GitHub y fuentes secundarias fechadas en 2026. Lo que no se pudo confirmar va marcado **[VERIFICAR]**. La Fase 0 incluye una prueba en vivo de cada fuente desde el VPS.
- **Precios y términos cambiantes.** Pueden variar sin aviso (precedente: CoinDesk Data retiró su plan gratuito en mayo de 2026). El registro de licencias se revisa cada trimestre.
- **Análisis jurídico no cerrado.** El doc 11 es orientación de diseño y no un dictamen; sus referencias deben contrastarse con el texto oficial.
