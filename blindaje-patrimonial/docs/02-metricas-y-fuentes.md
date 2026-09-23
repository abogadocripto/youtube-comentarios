# 02 — Métricas, fuentes, coste y licencias

> Estado: diseño v1 (23 sep 2026). Basado en investigación web contrastada. Las APIs de datos no se pudieron llamar desde el entorno de diseño (bloqueo de red), así que todo lo marcado **[VERIFICAR]** debe confirmarse con una llamada real en la Fase 0 del desarrollo (`scripts/smoke_sources.py`, ver doc 12).
> Catálogo máquina-legible: `config/metrics.yaml`.

## 1. Conclusión

1. **La licencia decide la fuente; el precio es secundario.** El canal de Telegram y la newsletter son públicos y sirven a la actividad de un despacho, así que su uso es **comercial**. Casi todas las fuentes gratuitas o "personales" prohíben mostrar sus datos a terceros:
   - planes gratuitos de proveedores de precios: CoinGecko Demo, CoinMarketCap sin clave;
   - APIs de los propios exchanges: Coinbase, Kraken, Bitstamp, Binance, Bybit;
   - índices bursátiles: Nasdaq, S&P DJI, ICE, Cboe;
   - proveedores on-chain: Glassnode Studio y Coin Metrics Community, esta última con licencia CC BY-NC.
2. **Por eso el diseño combina tres tipos de fuente:**
   - **Cálculo propio sobre datos públicos:** blockchain con nodo propio y BRK; fórmulas propias sobre series oficiales.
   - **Datos oficiales reutilizables:** Tesoro de EE. UU., Fed de Nueva York, Reserva Federal, BCE y Banco de Inglaterra.
   - **Pocos proveedores con licencia comercial expresa:** CoinGecko en plan de pago; alternative.me con atribución; y, según lo que decidas, CoinGlass Standard o los permisos escritos de SoSoValue y Coinalyze.
3. **Filtro de licencias en el renderizador.** Cada fuente lleva uno de estos estados: `self_computed`, `official_open`, `licensed_public`, `permission_pending`, `internal_only` o `prohibited`. El renderizador **se niega** a publicar un dato cuya fuente no sea `self_computed`, `official_open` o `licensed_public`. Es una regla de código, no un criterio editorial (doc 08, validador V-LIC).
4. **FRED no puede ser fuente de lo que se almacena y publica.** Un investigador informa de que su aviso legal (revisado el 1 sep 2026) prohíbe almacenar su contenido en bases de datos sin consentimiento e incluye una cláusula sobre usos en IA. Aún **[VERIFICAR]**. Mientras tanto, las series macro se toman de los publicadores originales y FRED queda como verificación interna puntual, sin almacenar.
5. **Hay tres escenarios de coste** (§6). El mínimo "limpio" cuesta unos **100–160 €/mes** en total (datos, infraestructura y LLM) y publica un Daily completo sin ETF, sin derivados y sin Nasdaq. Añadir ETF, derivados y saldos en exchanges con un único proveedor (CoinGlass Standard, unos 299 $/mes) lo lleva a unos **400–450 €/mes**.

## 2. Criterios de selección de fuente (por orden)

1. **Licencia de difusión pública comercial** (con atribución si se exige). Sin ella, la fuente como mucho sirve para verificación interna, y solo si sus términos permiten ese uso interno.
2. **Fiabilidad y metodología documentada.** Se prefiere la fuente primaria (el emisor o el organismo que publica) al agregador.
3. **Disponibilidad a las 08:30 Europe/Madrid** del dato de la sesión anterior.
4. **Estabilidad técnica:** API documentada frente a scraping; límites razonables.
5. **Coste.**

Regla de oro: **nunca se elude una protección anti-bot** (Cloudflare, CAPTCHA) ni se usan proxies residenciales. Si una fuente devuelve 403 o un *challenge*, se marca `DOWN` y se pasa al fallback.

## 3. Catálogo de métricas

Leyenda:
- **Capa:**
  - `N` = núcleo, aparece siempre en el Daily;
  - `C` = candidata, aparece si su *salience* lo justifica (doc 04);
  - `B` = solo backend, Weekly y alertas.
- **Licencia:**
  - `SC` = cálculo propio;
  - `OF` = oficial reutilizable;
  - `LP` = licencia pública de pago o gratuita con atribución;
  - `PP` = pendiente de permiso escrito;
  - `—` = no publicable.
- **MVP** = entra en el escenario mínimo.

### 3.1 Precio y ciclo

| metric_id | Capa | Fuente primaria | Fallback / verificación | Lic. | A las 08:30 | MVP |
|---|---|---|---|---|---|---|
| `btc_usd`, `btc_eur` | N | CoinGecko Basic `GET /api/v3/coins/bitcoin` → `market_data.current_price.{usd,eur}` | CMC Basic `/v2/cryptocurrency/quotes/latest?id=1` (publicable, licencia de "un producto" **[VERIFICAR]**); Coinbase Exchange ticker **solo interno, nunca publicado** | LP | tiempo real | ✔ |
| `btc_chg_24h_pct`, `btc_chg_7d_pct`, `btc_chg_30d_pct` | N | CoinGecko `price_change_percentage_{24h,7d,30d}_in_currency` | recalculado desde snapshots propios (tolerancia ±0,5 pp) | LP | tiempo real | ✔ |
| `btc_ath_usd`, `btc_ath_usd_date`, `btc_ath_eur`, `btc_ath_eur_date` | N | CoinGecko `ath.{usd,eur}`, `ath_date.{usd,eur}` | máximo acumulado propio (`ath_t = max(ath_{t-1}, provider_ath_t)`) | LP | ✔ | ✔ |
| `btc_drawdown_from_ath_pct`, `btc_days_since_ath` | N | calculado: `(precio/ATH − 1)·100`; días naturales en Europe/Madrid | contraste con `ath_change_percentage` (±0,1 pp) | SC | ✔ | ✔ |
| `btc_realized_vol_30d` | B | calculado sobre cierres diarios propios (desv. típica de rendimientos log × √365) | — | SC | ✔ | ✔ |
| `block_height` | B | nodo propio `getblockcount` | mempool.space `/api/blocks/tip/height`; Blockstream `/api/blocks/tip/height` (±2 bloques) | SC | tiempo real | ✔ |
| `halving_last_date`, `halving_days_since`, `halving_blocks_to_next`, `halving_next_est_date` | C | constantes (bloque 840.000 = 2024‑04‑20 00:09:27 UTC) + altura actual | ritmo reciente de bloques (media de los últimos 2.016 o más) | SC | ✔ | ✔ |
| `hashrate_7d` | B | nodo propio `getnetworkhashps 1008` / BRK | mempool.space `/api/v1/mining/hashrate/1m` | SC | ✔ | ✔ |

Notas:
- **ATH publicado** = máximo intradía del precio agregado del mismo proveedor que el precio spot. Nunca se mezclan proveedores: sus ATH difieren hasta un 0,35 % (el 6 oct 2025, CMC dio 126.198 $ y CoinGecko unos 126.080 $). Se guarda aparte, para uso interno, el máximo cierre diario (`ath_close_*`).
- **ATH en EUR:** se calcula por separado, porque su fecha puede no coincidir con la del USD por el tipo de cambio. Se sembrará y verificará a mano una vez en el arranque.
- **Guardarraíles del ATH:**
  - Si el proveedor cambia su ATH sin un movimiento de precio que lo justifique, se congela el valor publicado y se avisa al operador.
  - Un nuevo ATH real (precio > ATH almacenado, confirmado por la fuente secundaria) dispara una alerta de mercado (doc 05).
- **Halving:**
  - Solo se publica el **mes estimado** del próximo ("~abril 2028"), con los bloques restantes; nunca un día concreto.
  - A 23 sep 2026 se cumplen 886 días desde el último.
- **Contraste de precio** entre las dos fuentes, pedidas con menos de 60 s de diferencia, según la desviación relativa:
  - **≤0,5 %:** se publica la primaria.
  - **Entre 0,5 % y 1,5 %:** se consulta una tercera referencia interna y se publica el valor licenciado más cercano a la mediana, con `quality_flag=warn`.
  - **>1,5 %, o dato de más de 15 min:** se reintenta hasta las 08:50; si persiste, se omite la línea de precio y se avisa al operador. Como sin precio no hay Daily, esto activa el protocolo de no publicación (doc 01 §6).

### 3.2 Sentimiento

| metric_id | Capa | Fuente | Lic. | A las 08:30 | MVP |
|---|---|---|---|---|---|
| `fng_value`, `fng_class`, `fng_value_1d_ago`, `fng_value_7d_ago` | N | alternative.me `GET https://api.alternative.me/fng/?limit=8` | LP (gratuito; uso comercial permitido con **atribución junto al dato**) | nuevo valor a las 00:00 UTC ✔ | ✔ |

- Se asignan hoy, D‑1 y D‑7 **por `timestamp`** (día UTC), no por posición en el array. Los valores llegan como texto y se convierten a entero.
- El índice de CMC es **otro índice**, con otra metodología. Nunca se mezcla en la misma serie. Como mucho aparece en el Weekly, con su propia etiqueta.
- Si falta el dato de hoy a las 08:50, la línea se omite.

### 3.3 Liquidez, tipos y dólar (fuentes oficiales)

| metric_id | Capa | Fuente primaria | Fallback | Lic. | Dato disponible a las 08:30 (día P) | MVP |
|---|---|---|---|---|---|---|
| `us10y_yield`, `us2y_yield` | C | Tesoro de EE. UU., curva nominal diaria (XML `daily_treasury_yield_curve`, `BC_10YEAR`, `BC_2YEAR`) | Fed Board H.15 (`H15_H15.XML`) | OF (dominio público) | P‑1 (el lunes, el del viernes) | ✔ |
| `us10y_real_yield` | C | Tesoro, curva real diaria (XML `daily_treasury_real_yield_curve`, 10Y; nombre del elemento **[VERIFICAR]**) | H.15 | OF | P‑1 | ✔ |
| `us10y_breakeven` (derivada) | B | calculada = nominal 10Y − real 10Y del mismo día | — | SC | P‑1 | ✔ |
| `fed_funds_effective` | B | Fed de Nueva York, Markets API (EFFR) | H.15 | OF (atribución NY Fed obligatoria) | P‑2 | ✔ |
| `fed_funds_upper` (+ inferior) | C | configuración que se actualiza con cada comunicado del FOMC; se contrasta a diario con H.15 | — | OF | vigente | ✔ |
| `us2y_minus_ffr_bp` | C | calculada: 2Y (P‑1) − EFFR (último) | — | SC | ✔ | ✔ |
| `us_net_liquidity_usd`, `us_net_liquidity_chg_4w_pct` | C | calculada (ver fórmula abajo) con el balance de la Fed (H.4.1, `WALCL`), la TGA diaria (Fiscal Data DTS) y la ON RRP (Fed de Nueva York) | variante semanal toda en miércoles | SC sobre OF | balance: último miércoles; TGA: P‑2; ON RRP: P‑1 | ✔ |
| `global_m2_usd`, `global_m2_chg_3m_ann_pct`, `global_m2_yoy_pct` | C | calculado: M2 de EE. UU. (H.6) + M2 zona euro (BCE `BSI.M.U2.Y.V.M20.X.1.U2.2300.Z01.E`) + M2 Japón (API BoJ, db `MD02`) + M2 China (PBoC, HTML) + M4 Reino Unido (BoE IADB `LPMAUYN`), convertidos con tipos del BCE | — | SC sobre OF (**Japón pendiente de permiso del BoJ**) | mensual, con 9–33 días de retraso | ✔ (sin Japón si no hay permiso) |
| `liquidity_regime` | N | calculado (doc 04 §3.3) | — | SC | ✔ | ✔ |
| `eurusd` | C | tipo de referencia del BCE (`eurofxref-daily.xml`) | Fed H.10 | OF ("Fuente: BCE") | P‑1 (16:00 CET; nada en fin de semana ni festivos TARGET) | ✔ |
| `usd_index` | B | Índice Amplio Nominal del Dólar de la Fed (H.10, *Data Download Program*) | — | OF | semanal (3–9 días de retraso) → **solo Weekly** | ✔ |
| `fed_next_meeting_date` | C | calendario de la Fed (`calendar.json`) | página del FOMC | OF | ✔ | ✔ |
| `fed_next_meeting_cut_prob` | — | **descartada en el MVP**. La API FedWatch de CME (desde ~25 $/mes) no incluye difusión pública sin licencia específica. Kalshi y Polymarket: términos no comerciales; además, la DGOJ los bloquea en España desde el 26 may 2026 **[VERIFICAR]** | proxy gratuito: `us2y_minus_ffr_bp` | — | — | ✘ |

**Liquidez neta de EE. UU.: fórmula y unidades.** Es un error clásico, así que se fija aquí:

```
Serie semanal (convención popular, compatible con las gráficas de FRED; todo en millones de USD):
  NETLIQ = WALCL − 1000·WTREGEN − 1000·RRPONTSYD
  (WALCL está en millones; WTREGEN y RRPONTSYD están en MILES DE MILLONES)

Serie semanal preferida (todos los valores del mismo miércoles):
  NETLIQ = WALCL − WDTGAL − 1000·RRPONTSYD[miércoles]

Serie diaria (la que usa el Daily):
  NETLIQ_t = WALCL[último miércoles ≤ t] − TGA_DTS[t] − ONRRP_NYFed[t]   (todo convertido a millones)
Se publica en miles de millones de USD con un decimal, junto al cambio a 4 semanas.
```

- **Control de rango:** 3 bill. $ ≤ NETLIQ ≤ 9 bill. $. Un cambio diario de más de 300.000 M $ exige revisión manual; los días de pago de impuestos y los fines de mes mueven mucho la TGA.
- **No mezclar series:** la TGA del DTS y la del H.4.1 no se empalman en una misma serie. `WLRRAL` no sustituye a `RRPONTSYD`, porque incluye el *pool* de recompras de clientes oficiales extranjeros.

**M2 global:**
- Se publican tres series: en USD, a tipo de cambio constante y el **efecto divisa** (la diferencia entre ambas). Muchas "expansiones" del M2 en USD son en realidad un dólar más débil.
- Un mes queda "provisional" hasta que llegan los cinco componentes; los que faltan se arrastran y se marcan.
- Hay revisiones: se guardan vintages.
- China (HTML sin API, unidades en 亿元) lleva límites de cordura: variación mensual <3 %; si se supera, confirmación manual.

**Licencias macro:**
- Tesoro, Reserva Federal y DTS: dominio público.
- BCE: reutilización libre citando la fuente y sin modificar los datos; los derivados se marcan como "cálculo propio".
- BoE: Open Government Licence v3.
- Fed de Nueva York: aviso y atribución obligatorios ("© 2026 Federal Reserve Bank of New York…").
- **BoJ: prohíbe la reproducción comercial sin permiso previo.** Hay que pedirlo antes del lanzamiento; si lo deniega, Japón sale del agregado público.

**Nota de coherencia:** la investigación sitúa el rango objetivo de los fondos federales en 3,75–4,00 % tras una **subida** decidida el 16 sep 2026 **[VERIFICAR]**. El sistema nunca "sabe" este dato: lo lee de la configuración, que se actualiza con cada comunicado del FOMC, y lo contrasta a diario.

### 3.4 Mercados tradicionales (risk-on)

| metric_id | Capa | Fuente | Lic. | Decisión MVP |
|---|---|---|---|---|
| `ndx_close`, `ndx_chg_1d_pct`, `ndx_chg_5d_pct` | C | **exige licencia de difusión** (Nasdaq GIDS directa, o un plan de empresa de Twelve Data con derechos de *display*, 149–499 $/mes según la fuente **[VERIFICAR]**, o Massive Business, unos 2.499 $/mes) | — | ✘ **Bloque oculto hasta tener licencia** (decisión pendiente, §7) |
| `spx_close`, `spx_chg_1d_pct` | — | licencia de S&P DJI | — | ✘ |
| `vix_close` | — | licencia de Cboe | — | ✘ |
| `usd_index` (DXY de ICE) | — | ICE prohíbe su uso sin consentimiento; se sustituye por el índice amplio de la Fed (§3.3) | — | ✘ (se usa el sustituto oficial) |
| `gold_usd`, `gold_chg_5d_pct` | B | **proxy PAXG/XAUT** del mismo proveedor cripto con licencia (CoinGecko), con la etiqueta "token respaldado por oro (proxy)". El precio LBMA exige licencia de IBA | LP | ✔ como proxy; `gold_usd` queda reservado para una fuente spot con licencia |

Consecuencia editorial: mientras no haya licencia del Nasdaq-100, el bloque "📈 Risk-on" del Daily pasa a llamarse **"🏛️ Tipos y dólar"**, con los rendimientos a 10 años nominal y real, EUR/USD y la liquidez neta. Todo ello es oficial y reutilizable. Ofrece la misma función de "condiciones financieras" sin riesgo de licencia.

Tampoco se usan como contexto interno FRED, Yahoo, Stooq, Alpha Vantage ni los planes individuales de Twelve Data, FMP, EODHD o Tiingo: sus licencias excluyen el uso comercial incluso interno.

### 3.5 Demanda vía ETFs spot de EE. UU.

No existe un feed oficial, gratuito y con licencia. Todos los agregadores reconstruyen los flujos a partir de lo que publican los emisores.

| metric_id | Capa | Fuente primaria | Fallback | Lic. | MVP |
|---|---|---|---|---|---|
| `etf_net_flow_usd_1d` | N (si hay licencia) | SoSoValue OpenAPI v1 `GET /openapi/v1/etfs/summary-history?symbol=BTC&country_code=US` (cabecera `x-soso-api-key`) **condicionado a permiso escrito de difusión** | CoinGlass v4 `GET /api/etf/bitcoin/flow-history` (**plan Standard, 299 $/mes**; Hobbyist y Startup son de uso personal) | PP | ✘ hasta tener permiso o plan |
| `etf_net_flow_usd_5d`, `etf_net_flow_usd_20d`, `etf_flow_streak_days` | C | calculado sobre la serie diaria propia (5 y 20 **sesiones**, no días naturales) | — | SC sobre PP | ✘ |
| `etf_flow_by_issuer` | B | SoSoValue `/etfs/{ticker}/history` o CoinGlass | contraste: Grayscale (XLSX diario en S3, ~04:52 UTC) e iShares (XLS de NAV y participaciones), mediante ΔParticipaciones × NAV | PP | ✘ |
| `etf_total_btc_held` | B | CoinGlass `/api/etf/bitcoin/history` | — | PP | ✘ |
| `etf_flow_is_provisional` | — | indicador interno de completitud | — | — | — |

**Reglas operativas:**
- **Datación.** Cada dato se asocia a la **fecha de sesión de EE. UU.** (calendario XNYS, librería `exchange_calendars`). El Daily del lunes muestra la sesión del viernes. Siempre se imprime "sesión del <día>".
- **Completitud.** La sesión T solo está completa si:
  - T es la última sesión de la NYSE;
  - existe la fila agregada;
  - todos los tickers esperados tienen valor;
  - no es una fila "0.0" de relleno.

  Si no está completa, se publica la última sesión completa con su fecha, o "dato de ETF pendiente".
- **Conciliación.** Primaria y fallback son CONSISTENTES si |a−b| ≤ max(10 M $, 5 %). Si no lo son, se publica la primaria como "provisional" y sin desglose por emisor.
- **Versionado.** Cada dato se guarda como `provisional` y pasa a `final` cuando no cambia en dos lecturas separadas por 24 h o más y concilia con la segunda fuente. Se reingiere a las 14:00 y a las 23:30 para recoger los retrasos (históricamente, IBIT).
- **Farside:** no se hace scraping. Desde julio de 2026 está detrás de un *challenge* de Cloudflare y no se ha encontrado licencia de reutilización. Se le pedirá permiso por escrito.
- **Redacción obligatoria:** los flujos son **un indicador de la demanda canalizada a través de vehículos regulados**, no "compras institucionales". Entre los partícipes hay minoristas, asesores y estrategias de arbitraje no direccionales (*basis trade*).
- **Registro de fondos:** 12 tickers vivos a 10 sep 2026 (IBIT, FBTC, BITB, ARKB, BTCO, EZBC, BRRR, HODL, BTCW, MSBT, GBTC, BTC). Cada día se compara esa lista con la de la fuente y se avisa si aparece o desaparece un fondo.

### 3.6 On-chain

**Decisión: las métricas de valoración y cohortes se calculan con infraestructura propia.** Se usa BRK/Bitview (Bitcoin Research Kit, licencia MIT, financiado por OpenSats hasta junio de 2027) sobre un nodo Bitcoin Core propio. Al calcularse sobre la blockchain pública, **no dependen de ninguna licencia de terceros**. Los saldos y flujos de exchanges no se pueden calcular limpiamente, porque exigen etiquetar direcciones; para esos hay que licenciar un proveedor.

| metric_id | Capa | Fuente primaria | Fallback | Lic. | MVP |
|---|---|---|---|---|---|
| `realized_price_usd` | C | BRK (día D‑1 UTC) | BGeometrics `/v1/realized-price` (licencia **[VERIFICAR]**) | SC | ✔ |
| `mvrv`, `mvrv_z` | C | BRK: capitalización / capitalización realizada; Z calculado en casa: (MC − RC) / σ(MC, toda la historia) | BGeometrics `/v1/mvrv`, `/v1/mvrv-zscore` (nunca se empalman series de distintas fuentes) | SC | ✔ |
| `sopr`, `sopr_7d_ma`, `sth_sopr` | C | BRK (SOPR, aSOPR, STH/LTH‑SOPR); la media de 7 días se calcula en casa | BGeometrics; CryptoQuant si se contrata | SC | ✔ |
| `lth_supply_btc`, `lth_supply_chg_30d_btc` | C | BRK, cohorte LTH. **BRK usa ≥150 días; el estándar del sector es 155.** O se etiqueta ("monedas sin mover ≥150 días") o se implementa una cohorte propia de 155 días con el *plugin* de BRK | BGeometrics `/v1/long-term-hodler-supply` | SC | ✔ |
| `supply_in_profit_pct` | C | BRK `supply_in_profit` / suministro circulante | BGeometrics | SC | ✔ |
| `exch_balance_btc`, `exch_balance_chg_7d_btc`, `exch_balance_chg_30d_btc` | C | CryptoQuant Professional `/v1/btc/exchange-flows/reserve?exchange=all_exchange&window=day` (unos 99 $/mes en pago anual o 109 $/mes mensual, **y permiso escrito de difusión**) | CoinGlass `/api/exchange/balance/list?symbol=BTC` (incluido si se contrata Standard; términos **[VERIFICAR]**) | PP | ✘ |
| `exch_netflow_btc_1d`, `exch_netflow_btc_7d` | C | CryptoQuant `/exchange-flows/netflow` (y `inflow`/`outflow`) | Variación de saldo de CoinGlass, con la etiqueta "variación de saldo", no "flujo neto" | PP | ✘ |

**Cautelas metodológicas** (vinculantes para la redacción):
- **Saldos en exchanges:** cada proveedor agrupa direcciones a su manera. Los niveles no son comparables entre proveedores; solo las variaciones dentro de una misma fuente. Siempre "según <fuente>".
- **Revisiones:** los datos de exchanges se revisan hacia atrás; CryptoQuant no garantiza la precisión *point-in-time*. Cada lectura se guarda como un **vintage**; las variaciones se calculan dentro de un mismo vintage y nunca se reescriben en silencio mensajes ya publicados.
- **Movimientos custodios:** rotaciones de *cold wallets* de exchanges, migraciones de custodios de ETF o repartos de quiebras reinician la edad de las monedas. Hinchan el SOPR y reducen la oferta LTH sin que haya "venta de holders". Por eso **las métricas on-chain nunca disparan alertas públicas por sí solas**: solo generan un aviso interno para revisión humana.
- **Hashrate:** es una estimación. Solo se publica la media de 7 días.

**Descartadas para uso público:**
- Glassnode: difusión solo en planes institucionales de precio personalizado; la API Professional cuesta 799–999 $/mes más un complemento.
- Coin Metrics Community: CC BY-NC y una cláusula que, según se informa, prohíbe usar sus datos para generar salidas de modelos. **Tampoco se introducen en el LLM.**
- Arkham: sus términos limitan el uso a fines internos.
- Blockchain.com: sus términos prohíben almacenar sus datos.
- Santiment gratuito: retiene los últimos 30 días.

**Infraestructura BRK:**
- Servidor dedicado en la UE, separado del VPS de la aplicación: 2 TB NVMe y 32 GB de RAM, frente a un mínimo documentado de 16 GB. Coste estimado de 40–80 €/mes **[VERIFICAR]**.
- Alternativa gestionada: 0,01 BTC/mes.
- Hay que **fijar la versión** de `bitviewd`: la v0.11.0 (5 ago 2026) renombró series.
- Respaldo durante caídas: la instancia pública bitview.space, de uso razonable y sin garantía de servicio.

### 3.7 Derivados

| metric_id | Capa | Fuente primaria | Fallback | Lic. | MVP |
|---|---|---|---|---|---|
| `funding_rate_agg_8h`, `funding_rate_agg_ann_pct` | C | Coinalyze API v1 (clave gratuita; 40 llamadas/min): funding por mercado y OI en USD → media ponderada por OI, calculada en casa | CoinGlass `/api/futures/funding-rate/oi-weight-history` (Standard) | PP (Coinalyze no publica términos: **pedir permiso escrito**) | ✘ |
| `oi_usd`, `oi_btc`, `oi_chg_24h_pct` | C | Coinalyze `open-interest-history` (1 h; `convert_to_usd` true y false) sumado por mercado | CoinGlass `/api/futures/open-interest/aggregated-history` | PP | ✘ |
| `liq_long_usd_24h`, `liq_short_usd_24h`, `liq_total_usd_24h` | C | Coinalyze `liquidation-history` (1 h, últimas 24 h, campos `l`/`s`) | CoinGlass `/api/futures/liquidation/aggregated-history` | PP | ✘ |
| `dvol` | B | Deribit `public/get_volatility_index_data` (1D) | — | PP (términos de Deribit: datos derivados solo para uso personal salvo aprobación escrita) | ✘ |
| `cme_basis_ann_pct` | — | solo a través de un proveedor con licencia (CoinGlass Standard, Velo) | CFTC COT (código 133741), semanal y público, para el Weekly | — | ✘ |

**Reglas metodológicas:**
- **Funding normalizado a 8 h:** `FR8_i = FR_i × 8 / horas_intervalo_i`. Hyperliquid liquida cada hora; revisar las excepciones de Binance en `fundingInfo`.
- **Agregado ponderado por OI:** `Σ(FR8_i·OIusd_i)/Σ OIusd_i`.
- **Anualización:** APR = FR8 × 3 × 365; 0,01 %/8 h equivale a un 10,95 % anual.
- **OI:** en la lectura se prioriza la variación en **BTC**. En USD, el OI se mueve con el precio y se confundiría con apalancamiento.
- **Liquidaciones:** siempre con la etiqueta "**mínimo reportado**". El flujo de Binance solo emite una liquidación por símbolo y segundo, así que todos los agregados se quedan cortos.
- **Cobertura:** se guardan los componentes por mercado y un campo `coverage_pct`. Si cambian los mercados incluidos, se registra y se reexpresa la historia.
- **Sin colector 24/7:** no hace falta un colector websocket para el Daily ni para el Weekly. Para alertas en tiempo real basta con consultar Coinalyze cada 1–5 min. El websocket de futuros de Binance no emite datos desde servidores en la UE; se observó en julio de 2026.
- **APIs de exchanges** (Binance, Bybit, OKX, Hyperliquid): sirven de *fallback* técnico solo para verificación interna. Sus términos prohíben la explotación comercial y el reempaquetado de sus datos.

**Alternativa a estudiar [VERIFICAR]:** CoinGecko ofrece `/api/v3/derivatives`, con funding y OI por contrato. Si el plan Basic lo incluye y su licencia comercial lo cubre, funding y OI podrían publicarse **sin coste adicional**; las liquidaciones seguirían dependiendo de Coinalyze o CoinGlass. Se comprobará en la Fase 0.

### 3.8 Calendario

| Dato | Fuente | Lic. |
|---|---|---|
| FOMC (decisiones, actas, conferencias), comparecencias del presidente de la Fed | `https://www.federalreserve.gov/json/calendar.json` + página FOMC + RSS `press_monetary.xml` | OF |
| PIB, PCE (BEA) | `https://apps.bea.gov/API/signup/release_dates.json` + ICS | OF |
| IPC, empleo, IPP (BLS) | la ICS de BLS devuelve 403 a scripts → **YAML anual mantenido a mano** (`config/calendar/bls_2026.yaml`), contrastado con la API de fechas de FRED (solo interno) | OF |
| Reuniones del BCE | página oficial de calendario (YAML anual + comprobación de cambios) | OF |
| Festivos y cierres anticipados de la NYSE | `exchange_calendars` (XNYS) + lista anual | hechos |
| Vencimientos de opciones BTC (Deribit) | `public/get_instruments` (08:00 UTC; trimestrales el último viernes de mar/jun/sep/dic) | la **fecha** es un hecho publicable; el **nocional** exige aprobación de Deribit |
| Último día de negociación de futuros BTC en CME | motor de reglas (último viernes del mes, 16:00 Londres) + excepciones revisadas a mano cada enero | hechos |
| Plazos fiscales y regulatorios (ES/AD/UE) | `config/calendar/regulatory.yaml` (doc 05) | propio |

Todos los eventos se guardan en UTC con su zona de origen y se muestran en Europe/Madrid.

**Semanas de desfase horario** entre EE. UU. y la UE: 25–31 oct 2026 y 14–27 mar 2027. En ellas los datos de las 08:30 ET se publican a las 13:30 en Madrid y el FOMC a las 19:00. Por eso nunca se escribe una hora a mano en el código.

### 3.9 Stablecoins (para alertas y Weekly)

| metric_id | Fuente | Lic. | MVP |
|---|---|---|---|
| `usdt_peg`, `usdc_peg` | CoinGecko Basic `/simple/price?ids=tether,usd-coin&vs_currencies=usd` (sondeo cada 5 min para alertas) | LP | ✔ |
| `stablecoin_mcap_usd`, `stablecoin_mcap_chg_7d_pct` | CoinGecko `/coins/categories` (categoría stablecoins) **[VERIFICAR]** | LP | ✔ |

## 4. Resultado: qué ve el lector en cada escenario

| Bloque del Daily | Escenario A (mínimo limpio) | Escenario B (+ CoinGlass Standard) | Escenario C (+ licencia NDX) |
|---|---|---|---|
| ₿ Bitcoin (precio, variaciones, ATH) | ✔ | ✔ | ✔ |
| 🧠 Sentimiento (F&G) | ✔ | ✔ | ✔ |
| 🌊 Liquidez (régimen + M2 global + liquidez neta EE. UU.) | ✔ | ✔ | ✔ |
| 🏦 Demanda ETF | ✘ (o ✔ si SoSoValue da permiso gratuito) | ✔ | ✔ |
| 🔗 On-chain (MVRV, SOPR, LTH, suministro en beneficio) | ✔ | ✔ | ✔ |
| 🔗 Exchanges (saldo/netflow) | ✘ | ✔ si los términos de CoinGlass lo cubren; si no, CryptoQuant (+109 $/mes) | ✔ |
| ⚡ Derivados (funding, OI, liquidaciones) | ✘ (o ✔ si Coinalyze da permiso) | ✔ | ✔ |
| 🏛️ Tipos y dólar / 📈 Risk-on | "Tipos y dólar" (oficial) | "Tipos y dólar" | "Risk-on" con Nasdaq-100 + tipos |
| 👀 Hoy vigilaría | ✔ | ✔ | ✔ |

## 5. Métricas descartadas y por qué

| Métrica | Motivo |
|---|---|
| S&P 500, VIX, DXY (ICE), oro LBMA | licencia de difusión cara o prohibitiva; redundantes con Nasdaq y tipos para este público |
| Probabilidades de la Fed (CME FedWatch, Kalshi, Polymarket) | licencia de CME para difusión pública; términos no comerciales de Kalshi y Polymarket y bloqueo de la DGOJ en España; el proxy 2Y−EFFR cubre la función |
| M2 global ya elaborado por terceros (BGeometrics, BM Pro, MacroMicro, TradingView) | redistribución prohibida o con precio a medida; metodología opaca; se construye propio con fuentes oficiales |
| Nocional de opciones en Deribit, *max pain*, put/call | exige aprobación escrita de Deribit (se solicita; mientras tanto solo se publica la fecha del vencimiento) |
| Métricas de Glassnode o Coin Metrics | licencias incompatibles (ver §3.6) |
| Análisis técnico (medias, RSI, soportes) | fuera de la filosofía editorial |

## 6. Escenarios de coste mensual (orientativos, sin IVA)

| Partida | A: mínimo limpio | B: recomendado | C: completo |
|---|---|---|---|
| CoinGecko Basic (precio, ATH, stablecoins, proxy de oro) | ~35 $ | ~35 $ | ~35 $ |
| CoinMarketCap Basic (contraste) | 0 | 0 | 0 |
| alternative.me, fuentes oficiales, calendario | 0 | 0 | 0 |
| Servidor del nodo Bitcoin + BRK (UE) | 40–80 € | 40–80 € | 40–80 € |
| VPS de la aplicación + PostgreSQL + copias | 10–25 € | 10–25 € | 10–25 € |
| CoinGlass Standard (ETF + derivados + saldos en exchanges) | — | ~299 $ | ~299 $ |
| CryptoQuant Professional (solo si CoinGlass no cubre exchanges) | — | (0–109 $) | (0–109 $) |
| Licencia EOD del Nasdaq-100 | — | — | 150–500 $ **[VERIFICAR]** |
| LLM (Claude Opus 5; ver doc 06 §7) | 15–40 $ | 15–40 $ | 15–40 $ |
| Proveedor de email (doc 10) | 0–50 € | 0–50 € | 0–50 € |
| **Total aproximado** | **100–230 €** | **400–560 €** | **550–1.050 €** |

La mayor palanca es **una sola negociación con CoinGlass** que cubra en términos escritos la difusión pública de flujos de ETF, derivados y saldos en exchanges. Si SoSoValue y Coinalyze conceden permiso gratuito con atribución, el escenario B cuesta casi lo mismo que el A.

## 7. Gestiones previas al lanzamiento (responsable: ABAST)

| # | Gestión | Para qué | Bloquea |
|---|---|---|---|
| L1 | Contratar CoinGecko Basic y archivar sus términos (PDF + hash) | precio y ATH con licencia comercial | Daily (núcleo) |
| L2 | Confirmar por escrito con CMC que "canal de Telegram + newsletter + archivo web" cuentan como **un producto** | fuente secundaria publicable | contraste de precio publicable |
| L3 | Pedir permiso escrito a **SoSoValue**: difusión pública comercial, texto de atribución y plan de pago | flujos ETF sin coste | bloque ETF (escenario A) |
| L4 | Pedir permiso escrito a **Coinalyze** para mostrar agregados derivados con atribución | derivados sin coste | bloque derivados (escenario A) |
| L5 | Pedir a **CoinGlass** confirmación escrita de que Standard cubre la difusión pública en Telegram y newsletter de flujos de ETF, funding, OI, liquidaciones y saldos en exchanges | escenario B | bloques ETF, derivados y exchanges |
| L6 | Pedir permiso al **Banco de Japón** (Departamento de Relaciones Públicas; notificar a Investigación y Estadística) | Japón en el M2 global | componente japonés |
| L7 | Pedir a **Farside** permiso o licencia | fuente de respaldo de ETF | no bloquea |
| L8 | Pedir a **Deribit** aprobación para publicar OI y nocional de vencimientos y DVOL | contexto de vencimientos | no bloquea |
| L9 | Decidir la **postura sobre el Nasdaq-100**: (a) licencia; (b) omitirlo; (c) criterio jurídico propio sobre citar el cierre de un índice como hecho noticioso con atribución. **Recomendación: (b) en el MVP y (a) si el bloque demuestra valor** | bloque risk-on | no bloquea |
| L10 | Aclarar los términos vigentes de **FRED** (almacenamiento y cláusula de IA) | uso como verificación | no bloquea (el diseño no depende de FRED) |

Todas las respuestas se archivan en el **registro de licencias** (tabla `source_licences`, doc 03), con la evidencia y la fecha de revisión. La revisión es trimestral.

## 8. Riesgos principales

1. **Cambios unilaterales de términos o de planes.** Precedente: CoinDesk Data retiró su plan gratuito el 21 may 2026. Mitigación: registro de licencias, revisión trimestral y fuente alternativa identificada para cada métrica.
2. **Interpretación de "un producto" en CMC** y términos no publicados de SoSoValue, Coinalyze y BGeometrics. Mitigación: permiso escrito antes de publicar.
3. **Fragilidad técnica:**
   - PBoC (HTML irregular);
   - endpoints no documentados de los emisores de ETF;
   - BRK en rápida evolución;
   - límites no documentados de mempool.space y alternative.me.

   Mitigación: pruebas de contrato por fuente, versiones fijadas y avisos de cambio de esquema.
4. **Desalineación de fechas:** sesión de EE. UU. frente a fecha de Madrid; semanas de cambio de hora; festivos. Mitigación: cada dato guarda `as_of` con la semántica de su fuente y el calendario XNYS.
5. **Datos obsoletos que "funcionan".** Un proyecto similar sufrió tres semanas de datos congelados sin detectarlo. Mitigación: controles de frescura por métrica (`max_staleness` en `metrics.yaml`) y alerta al operador.
