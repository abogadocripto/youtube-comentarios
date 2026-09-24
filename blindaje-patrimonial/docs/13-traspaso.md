# 13 · Traspaso a otra sesión (estado a 24 sep 2026)

Documento autocontenido para retomar el proyecto en otra conversación o con otro asistente.

## 1. Dónde está todo

- **Repositorio:** `github.com/abogadocripto/youtube-comentarios`, rama `claude/festive-galileo-qqxq09`, carpeta `blindaje-patrimonial/`. El resto del repositorio es una extensión de Chrome ajena al proyecto. Conviene moverlo a un repositorio propio.
- **CI:** `.github/workflows/blindaje-patrimonial-ci.yml`, en verde en los últimos commits.
- **No hay PR abierta.** No se ha publicado nada: ni canal, ni servidor, ni claves.
- **Entrada recomendada:** `README.md` → `docs/00-resumen-ejecutivo.md` → este documento.

## 2. Encargo original (resumen)

Sistema automático de inteligencia patrimonial con tres productos:

- **Daily Bitcoin:** Telegram, 09:00 Europe/Madrid, lectura de 1–2 minutos, 5–8 indicadores, «La lectura» y «Hoy vigilaría…».
- **Informe semanal de Blindaje Patrimonial:** email con cuatro frentes (financiero, fiscal, regulatorio y protección), «La semana en 60 segundos» y, por asunto, «Qué ha pasado / Por qué importa / A quién afecta / Qué deberías vigilar». «Sin cambios relevantes esta semana» es una salida válida.
- **Alertas patrimoniales:** por puntuación de impacto de 0 a 100.

Filosofía: datos → filtro → contexto → impacto patrimonial. Sin predicciones, sin señales, sin análisis técnico. El LLM nunca inventa cifras. Prima la fuente primaria. Cada dato guarda valor, fecha, fuente, URL y momento de obtención.

## 3. Qué está hecho

### 3.1 Diseño (docs 00–12, completo)

| Doc | Contenido |
|---|---|
| 00 | Resumen ejecutivo: cinco conclusiones, costes, qué se necesita del despacho |
| 01 | Arquitectura, orquestación, despliegue, observabilidad, seguridad |
| 02 | 91 métricas: fuente primaria y de respaldo por métrica, licencia, frescura, costes por escenario, licencias L1–L10 |
| 03 | Modelo de datos (`schema/schema.sql`, 22 tablas, PostgreSQL 16) |
| 04 | Reglas matemáticas de interpretación (`config/rules.yaml`) |
| 05 | Noticias: 70 fuentes, prefiltro, agrupación, *scoring* 0–100, Weekly y alertas |
| 06 | Contrato JSON con el LLM (`schema/llm/*.schema.json`) |
| 07 | Prompts (`prompts/*.md`) y ejemplo de principio a fin |
| 08 | Validación antialucinaciones: 5 capas, 28 validadores, batería A1–A25 |
| 09 | Telegram: canal, plantillas, publicación idempotente, correcciones, bot de edición |
| 10 | Newsletter: Brevo (UE) o Listmonk + SES, doble opt-in, sin píxeles de seguimiento |
| 11 | Cumplimiento: MiCA, Reglamento de IA art. 50.4, Andorra, LSSI, RGPD, deontología |
| 12 | Plan por fases, qué necesita el despacho, decisiones D1–D10 |

### 3.2 Código (`src/bp/`, Python 3.11+)

| Capa | Módulos | Estado |
|---|---|---|
| Configuración | `config.py` (valida el cruce métricas ↔ fuentes ↔ reglas; lee la notación científica de YAML 1.2) | ✔ |
| Ingesta | `ingest/base.py`, `crypto.py` (CoinGecko, alternative.me, mempool.space, SoSoValue), `official.py` (Tesoro, Fed NY, Fiscal Data, H.4.1, BCE), `registry.py` | ✔ con fixtures; **sin probar en vivo** |
| Análisis | `analysis/derive.py`, `rules.py`, `salience.py`, `watch.py`, `stats.py`; `calendar/events.py` | ✔ |
| Selección | `select/fact_sheet.py` (filtro de licencias, frescura, bloques, pistas) | ✔ |
| LLM | `llm/client.py` (salida estructurada, *fallback* del servidor, rechazos, costes), `llm/models.py` | ✔; **sin probar con el modelo real** |
| Validación | `validation/deterministic.py` (28 validadores), `verifier.py` (verificador LLM independiente) | ✔ |
| Editorial | `editorial/format.py` (formato es-ES), `markers.py`, `render.py`, plantilla Jinja, `fallback_reading.py` | ✔ |
| Distribución | `distribution/telegram.py` (idempotente; un timeout ambiguo no se reintenta) | ✔ |
| Orquestación | `orchestrator/daily.py`, `cli.py` | ✔ |
| Almacenes | `store/memory.py`, `store/postgres.py` (cerrojos `pg_advisory_lock`) | ✔ probado en PostgreSQL 16 real |
| Demo | `demo.py` (historia sintética y backend LLM simulado) | ✔ |

Órdenes: `bp doctor`, `bp db-init`, `bp demo [--llm static]`, `bp ingest-daily`, `bp build-daily`, `bp publish-daily [--only-if-missing|--force|--dry-run]`, `bp run-daily`, `bp smoke [--record]`.

### 3.3 Pruebas

- **Resultado:** 85 pasan y 1 se omite (A17, inyección en documentos: depende del clasificador de noticias).
- **Unitarias:** formato es-ES, estadística, marcadores, calendario (incluido el desfase de cambio de hora de octubre y la regla de CME), licencias y Telegram (duplicados, timeout ambiguo, 429).
- **Adversariales A1–A25:** bloqueantes en CI.
- **Extremo a extremo offline:** ruta de plantillas, ruta del LLM, reintento ante un marcador inexistente, rechazo del modelo, precio caducado.
- **Golden:** el ejemplo renderizado coincide byte a byte con el renderizador.
- **Integración con PostgreSQL:** se ejecuta con la variable `BP_TEST_DATABASE_URL`.

### 3.4 Despliegue

- `Dockerfile` (usuario sin privilegios) y `compose.yml` (Postgres sin puertos expuestos).
- `deploy/systemd/`, con temporizadores en `Europe/Madrid` y `AccuracySec=1s`:
  - 08:30 ingesta;
  - 08:45 borrador;
  - 09:00 publicación;
  - 09:07 respaldo `--only-if-missing`;
  - 03:30 copia cifrada con age.
- `.env.example` y `deploy/README.md`.

## 4. Qué funciona y qué no

**Comprobado que funciona:**

- Pipeline completo offline (`bp demo`).
- Publicación idempotente contra un Telegram simulado.
- Reconstrucción del mismo día sin conflictos.
- El filtro de licencias retira ETF y derivados.
- La URL de metodología pendiente bloquea la publicación en producción.
- Los temporizadores respetan el cambio de hora.
- La instalación no editable incluye las plantillas.

**No comprobado o no funciona todavía:**

1. **Ninguna fuente se ha llamado en vivo.** El proxy de la sesión devuelve 403 para todas las APIs de datos. Se programó contra la documentación y se probó con fixtures **sintéticos** (`tests/fixtures/_generate_synthetic.py`).
2. **Conector H.4.1:** usa un identificador de paquete provisional (`[●paquete WALCL]`) y la vía está condenada, porque la Fed retira «Build Your Package» del DDP la semana del 9 nov 2026 (anuncio del 16 jul 2026). Hay que reescribirlo contra el XML de `federalreserve.gov/releases/h41/current/`.
3. **CoinGecko** usa `pro-api.coingecko.com`, que exige la clave del plan Basic (L1). Sin clave falla.
4. **SoSoValue:** endpoint y campos (`total_net_inflow`, `total_btc_holdings`) no confirmados.
5. **La imagen Docker** no se ha construido: no había demonio Docker en la sesión.
6. **No existen todavía:** conectores del M2 global, índice del dólar, CoinMarketCap, BRK (on-chain), Coinalyze, CoinGlass, CryptoQuant; bot de edición; informe operativo de las 09:05; noticias y alertas; flujo del Weekly y newsletter; Sentry; logs JSON.

**Qué publicaría hoy en producción:**

- Bloque Bitcoin (precio en USD y EUR, 24 h, 7 d, máximo histórico).
- Sentimiento (alternative.me).
- Tipos y dólar.
- «La lectura» y «Hoy vigilaría…».

No aparecerían:

- **Liquidez:** exige el componente global del M2.
- **ETF y derivados:** exigen las licencias L3–L5.
- **On-chain:** exige BRK.

## 5. De dónde salen los datos

| Dato | Fuente (URL base) | Licencia en config | Estado |
|---|---|---|---|
| Precio BTC USD/EUR, variaciones, máximo histórico | CoinGecko `https://pro-api.coingecko.com/api/v3/coins/bitcoin` | licensed_public (con plan Basic, L1) | conector hecho |
| USDT, USDC, PAXG | CoinGecko `/simple/price` | ídem | hecho |
| Contraste de precio | CoinMarketCap `https://pro-api.coinmarketcap.com` | permission_pending (L2) | pendiente |
| Miedo y Codicia | `https://api.alternative.me/fng/` (atribución junto al dato) | licensed_public | hecho |
| Altura de bloque, tiempo medio de bloque | `https://mempool.space/api/blocks/tip/height`, `/api/v1/difficulty-adjustment` | self_computed | hecho |
| Rentabilidad nominal 2 y 10 años, real 10 años | Tesoro de EE. UU. (XML) `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve` y `daily_treasury_real_yield_curve` | official_open | hecho; campo real «*10YEAR» (tolerante) |
| EFFR y ON RRP | Fed de Nueva York `https://markets.newyorkfed.org/api/rates/unsecured/effr/last/5.json`, `/api/rp/all/all/results/lastTwoWeeks.json` | official_open | hecho; unidades de RRP con salvaguarda |
| TGA | Fiscal Data `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance` | official_open | hecho. **Verificado:** desde el 18 abr 2022 el saldo de cierre va en `open_today_bal` de la fila «TGA Closing Balance» |
| Balance de la Fed (WALCL) | H.4.1: hoy DDP, a migrar a XML de `federalreserve.gov/releases/h41/` | official_open | **reescribir** |
| EUR/USD | BCE `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml` | official_open | hecho |
| Rango objetivo de la Fed | `config/fomc.yaml` (3,75–4,00 %, decidido el 16 sep 2026) | official_open | manual tras cada FOMC |
| M2 global | Fed H.6, BCE Data Portal `https://data-api.ecb.europa.eu/service/data` (`BSI.M.U2.Y.V.M20.X.1.U2.2300.Z01.E`), BoE IADB (`LPMAUYN`), PBoC (HTML), BoJ (`MD02`, permiso L6) | official_open (BoJ pendiente) | **pendiente** |
| Índice amplio del dólar | Fed H.10 (a migrar a XML de la publicación) | official_open | **pendiente** |
| Flujos ETF | SoSoValue `https://openapi.sosovalue.com/openapi/v1/etfs/summary-history` | permission_pending (L3) | conector hecho, bloqueado por licencia |
| Derivados (funding, OI, liquidaciones) | Coinalyze `https://api.coinalyze.net/v1` (L4) o CoinGlass `https://open-api-v4.coinglass.com` (L5) | permission_pending | pendiente |
| Saldos en exchanges | CryptoQuant `https://api.cryptoquant.com/v1` | permission_pending | pendiente |
| On-chain (MVRV, SOPR, LTH, precio realizado) | BRK sobre nodo propio | self_computed | pendiente (servidor del nodo) |
| Calendario macro, festivos NYSE, plazos regulatorios | `config/calendar/*.yaml` (BLS, BEA, FOMC, BCE, NYSE) | official_open | hecho; revisar cada año |
| Vencimientos | Deribit (último viernes, 08:00 UTC); CME (16:00 de Londres, hábil en EE. UU. y Reino Unido) | — | hecho |

Descartadas por licencia: FRED (sus términos impiden almacenar), Coin Metrics Community, Glassnode, APIs de exchanges para publicar y Nasdaq-100 sin licencia (D2).

## 6. Decisiones y datos que faltan del despacho

| # | Pendiente | Efecto |
|---|---|---|
| — | URL de metodología, aviso legal y declaración de intereses (`config/editorial.yaml`, hoy `[●]`) | **Bloquea** publicar |
| D4 | Sociedad editora y responsable del despliegue de IA; responsable editorial nominativo | Pie legal, normas colegiales, ámbito del Reglamento de IA |
| — | Contenido de la declaración de intereses (posiciones del despacho y socios) | Pie legal (MiCA art. 91.3.c) |
| D1 | Escenario de datos A/B/C (140–240 / 430–580 / 580–1.070 €/mes) | Qué bloques existen |
| L1–L10 | Licencias: CoinGecko Basic, CMC, SoSoValue, Coinalyze, CoinGlass, BoJ, Farside, Deribit, Nasdaq-100, FRED | Bloques ETF, derivados, M2 Japón |
| — | Servidor UE (Hetzner CX23), clave de Anthropic, dos bots y dos canales de Telegram, Healthchecks, User-Agent con contacto | Arranque |
| D2, D3, D5–D10 | Nasdaq-100 fuera; sin revisión humana diaria (con etiqueta de IA); Brevo; Weekly el domingo a las 18:00; sin comentarios; `claude-opus-5`; 2 alertas por semana como máximo; solo castellano | Recomendaciones ya documentadas, pendientes de confirmar |

## 7. Dudas abiertas

**Técnicas (se resuelven con `bp smoke --record` desde el VPS):**

- Nombre exacto del campo real de 10 años del Tesoro (se lee cualquier campo acabado en `10YEAR`).
- Unidades de `totalAmtAccepted` de la ON RRP (salvaguarda: si es menor que 1e7 se multiplica por 1e9).
- Campos y autenticación de SoSoValue.
- Categoría de stablecoins en CoinGecko `/coins/categories`.
- Formato del XML de las publicaciones de la Fed (H.4.1, H.6 y H.10) que sustituye al DDP.

**Jurídicas (doc 11 §10):**

- Numeración del art. 91.3.c) de MiCA.
- Párrafos de las directrices del art. 50 del Reglamento de IA y autoridad española competente mientras se tramita la LO de IA.
- Andorra (con abogado andorrano o con la AFA): si el comentario impersonal queda fuera de «recomanacions específiques» (Llei 24/2022) y el alcance de la «recomanació general» (Llei 7/2013).
- Art. 6 del Código Deontológico de 2019 y normas colegiales sobre newsletters.
- Directrices de ESMA y CNMV sobre *finfluencers*.

**Económicas:** precios de Brevo por volumen, coste del servidor del nodo (40–80 €/mes), licencia del Nasdaq-100 (150–500 $), precios del LLM en `config/llm.yaml`.

## 8. Cómo seguir (orden recomendado)

1. Reescribir `FedH41` contra el XML de la publicación. Añadir los conectores del M2 global (BCE SDMX, BoE IADB, PBoC, H.6 y BoJ si hay permiso) y H.10. Cada uno con fixture y test. Criterio: aparece el bloque de liquidez en `bp demo` con datos derivados de conectores y no de `demo.py`.
2. Bot de edición privado (docs/09 §3): previsualización a las 08:50 con botones Retener, Publicar ya y Corregir; corrección con `editMessageText` y registro en `editor_actions`.
3. Informe operativo de las 09:05 y logs JSON.
4. En el servidor, siguiendo `deploy/README.md`: `db-init`, `doctor`, `smoke --record`; ajustar parsers con las respuestas reales; primera prueba con el modelo real.
5. Modo sombra en un canal privado: 14 días seguidos a las 09:00 sin fallos no detectados; valoración editorial ≥ 4/5.
6. Fases 4–7: BRK, ETF y derivados (según licencias), noticias y alertas, Weekly y newsletter.

## 9. Reglas del proyecto que no deben romperse

- El LLM solo escribe marcadores `{{f:id}}`, `{{fa:id}}` y `{{h:id}}`. Ningún dígito fuera de ellos (V-NUM).
- Un dato solo se publica si su fuente, y todas las fuentes de las que deriva, tienen licencia publicable (V-LIC, `licence.py`).
- El Daily con lectura del LLM lleva «🤖 Lectura elaborada con IA» en la primera línea (V-AILABEL, Reglamento de IA art. 50.4).
- El Weekly y las alertas requieren revisión sustantiva de un abogado identificado y hash del contenido aprobado (V-HASH).
- Nunca se reintenta un envío ambiguo a Telegram. Después de las 10:30 no se publica sin `--force`.
- No se entregan al LLM datos de fuentes con `llm_input_allowed: false`.
- Sin semáforo de compra o venta; solo ejes (liquidez, macro, demanda, apalancamiento, sentimiento).
