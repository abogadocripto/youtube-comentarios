# 04 — Reglas matemáticas de interpretación

> Umbrales y parámetros en `config/rules.yaml`, que está versionado. Cada cambio de umbral incrementa `rules_version` y queda registrado en cada informe generado.
> IDs de métricas: `config/metrics.yaml`.

## 1. Principios

1. **Estados descriptivos, nunca señales.** Cada métrica se traduce a un estado con vocabulario neutro: expansión o contracción, entradas o salidas, elevado o reducido, apetito o aversión. No existe ningún estado "comprar" ni "vender", ni ningún indicador compuesto que lo sugiera.
2. **Percentiles primero, umbrales fijos como ancla.** Cuando hay historia suficiente, el estado se decide por la posición de la métrica en su propia distribución histórica (percentil o z-score). Los umbrales fijos (p. ej. funding 0,03 %/8 h) sirven de referencia, por si la historia es corta o el régimen de mercado ha cambiado.
3. **Histéresis.** Para cambiar de estado hay que cruzar el umbral con margen o durante N lecturas consecutivas. Así se evita que el semáforo parpadee día a día.
4. **El código calcula; el LLM redacta.** Todo lo que el lector pueda contrastar sale del backend, que lo entrega como `state` e `interpretation_hints` ya verificados: rachas, máximos de N días, cruces de umbral, "de X a Y en 7 días". El LLM solo elige qué contar y cómo, sin inventar relaciones.
5. **Sin causalidad.** Las reglas describen coincidencias. Las frases del tipo "la liquidez adelanta al precio N semanas" están prohibidas (doc 08, lista de expresiones vetadas).
6. **Frescura.** Una métrica cuyo `as_of` no ha cambiado desde el último Daily publicado no puede "moverse". Su *salience* se multiplica por 0, salvo que forme parte de un bloque núcleo; en ese caso se muestra con su fecha y sin interpretarla como novedad.

## 2. Estadísticos comunes (módulo `analysis.stats`)

| Estadístico | Definición | Historia mínima |
|---|---|---|
| `chg_abs(x, k)` | x_t − x_{t−k} | k+1 |
| `chg_pct(x, k)` | (x_t / x_{t−k} − 1)·100 | k+1 |
| `z(x, w)` | (x_t − media_w) / desv_w. Para series con colas gordas (flujos, liquidaciones) se usa la variante robusta (x_t − mediana_w) / (1,4826·MAD_w) | w ≥ 60 |
| `pctl(x, w)` | proporción de observaciones de la ventana w que son ≤ x_t (0–1) | w ≥ 90 |
| `streak(x)` | número de observaciones consecutivas con el mismo signo que x_t, con signo (+3 = tres positivas seguidas) | — |
| `n_day_extreme(x, N)` | ¿es x_t el máximo o mínimo de las últimas N observaciones? Devuelve también la fecha del anterior valor mayor o igual ("mayor desde…") | N |
| `crossed(x, u)` | x_{t−1} < u ≤ x_t (o a la inversa) | 2 |
| `hysteresis(state_prev, raw_state, n)` | el estado solo cambia si `raw_state` se repite n lecturas | n |
| `sigma_move` | chg_24h_pct / (vol_diaria_30d·100), donde vol_diaria = desv(ln rendimientos diarios, 30) | 31 |

Si una métrica no tiene la historia mínima para su estadístico, se usa **solo el ancla fija** y el hecho se marca `stats.degraded=true`.

## 3. Reglas por familia

Formato de cada regla: entradas → estado (`code`, `label_es`) → pistas (`interpretation_hints`) → cautelas obligatorias.

### 3.1 Precio

**Magnitud del movimiento**, relativa a la volatilidad reciente y no en términos absolutos:

| Condición (`sigma_move` = variación 24 h / volatilidad diaria de 30 días) | `code` | `label_es` |
|---|---|---|
| \|σ\| < 1 | `move_calm` | "movimiento contenido" |
| 1 ≤ \|σ\| < 2 | `move_moderate_up` / `move_moderate_down` | "subida moderada" / "caída moderada" |
| \|σ\| ≥ 2 | `move_large_up` / `move_large_down` | "movimiento amplio al alza" / "a la baja" |

**Distancia al ATH** (`btc_drawdown_from_ath_pct` = dd):

| Condición | `code` | `label_es` |
|---|---|---|
| nuevo ATH en las últimas 24 h (confirmado por la fuente secundaria) | `ath_new` | "nuevo máximo histórico" |
| dd ≥ −3 % | `ath_zone` | "en zona de máximos" |
| −10 % ≤ dd < −3 % | `ath_near` | "cerca de máximos" |
| −20 % ≤ dd < −10 % | `correction` | "en corrección" |
| −35 % ≤ dd < −20 % | `correction_deep` | "corrección profunda" |
| dd < −35 % | `drawdown_severe` | "caída prolongada desde máximos" |

Histéresis: se exige un margen de 1 pp al volver a la banda anterior. Así, pasar de −3,2 % a −2,9 % y volver no cambia el estado dos veces.

**Pistas:**
- `h.ath_days`: "{{f:btc_days_since_ath}} días desde el máximo".
- `h.eur_vs_usd`: si |var. 7 días en EUR − var. 7 días en USD| ≥ 1,5 pp: "Para un inversor en euros la semana es {{f:btc_chg_7d_eur_pct}}, por el movimiento del dólar". Es especialmente relevante para el público de España y Andorra.
- `h.range_break`: si el precio es máximo o mínimo de 30 o 90 días.

**Cautela:** el precio **no lleva semáforo**. Es el activo, no una fuerza que actúe sobre él. Pintarlo de verde o rojo es exactamente la señal de trading que se quiere evitar.

### 3.2 Ciclo (halving)

- Solo hechos: días desde el halving, % de avance de la época (`(altura − 840.000)/210.000`) y mes estimado del próximo.
- La comparación con ciclos anteriores ("en los ciclos 2016 y 2020, el día N tras el halving…") **solo aparece en el Weekly**. Siempre lleva la cautela "tres observaciones no constituyen una regla" y nunca aparece en el Daily.
- Hitos redondos (1.000 días, 50 % de la época) generan una pista `h.halving_milestone`.

### 3.3 Liquidez

**a) M2 global.** Entrada: variación a 3 meses del M2 global en USD (`g3`) y su efecto divisa (`fx3`).

| Método | Regla |
|---|---|
| Preferido | Terciles de la distribución de `g3` en los últimos 10 años. Tercil superior → `expansion`; inferior → `contraction`; medio → `neutral`. Histéresis: 2 meses |
| Alternativo (poca historia) | `g3` anualizada > +4 % → `expansion`; < 0 % → `contraction`; resto → `neutral` |
| Anotación | Si \|fx3\| > 0,5·\|g3\| → pista `h.m2_fx_driven`: "impulsado sobre todo por el tipo de cambio" |

**b) Liquidez neta de EE. UU.** Entrada: variación a 4 semanas en USD (`n4`).

| Condición | Estado |
|---|---|
| n4 > +150.000 M $ | `expansion` |
| n4 < −150.000 M $ | `contraction` |
| resto | `neutral` |

Para cambiar de estado se exigen 2 lecturas consecutivas. Umbral provisional: se calibrará con la historia 2019–2026 antes del lanzamiento, buscando que cada extremo aparezca aproximadamente en el 20–30 % de las semanas.

**c) Régimen combinado** (`liquidity_regime`, métrica núcleo):

| M2 global | Liquidez neta EE. UU. | `liquidity_regime` | Semáforo |
|---|---|---|---|
| expansión | expansión o neutral | `expansion` "expansión" | 🟢 favorable para la liquidez |
| contracción | contracción o neutral | `contraction` "contracción" | 🔴 desfavorable para la liquidez |
| neutral | neutral | `neutral` "neutral" | 🟡 |
| neutral | expansión o contracción | la de EE. UU. con matiz "(impulso de corto plazo)" | 🟡 |
| expansión | contracción, o a la inversa | `mixed` "mixta" | 🟡 |

La línea diaria siempre indica el mes del último dato de M2: "Liquidez global: expansión (M2 global a agosto; liquidez EE. UU. 4 semanas: +X mm $)".

**Cautelas:** "la relación histórica entre liquidez y activos de riesgo no es estable". Queda prohibido decir que la liquidez "predice" o "adelanta" el precio.

### 3.4 Tipos y dólar (eje "macro")

| Métrica | Regla | Estados |
|---|---|---|
| `us10y_real_yield` | Δ20 sesiones (pb): ≥ +25 → `real_up`; ≤ −25 → `real_down`; resto → `real_flat` | "condiciones financieras más restrictivas" / "más holgadas" / "estables" |
| `us10y_yield` | Δ5 sesiones (pb): \|Δ\| ≥ 15 → notable | pista `h.yield_move`: "repunte (o caída) notable de la rentabilidad a 10 años" |
| `us2y_minus_ffr_bp` | > +25 → `pricing_hikes`; < −25 → `pricing_cuts`; resto → `pricing_hold` | "el mercado descuenta subidas / bajadas / estabilidad de tipos (proxy 2A−EFFR)" |
| `usd_index` (semanal) | Δ4 semanas ≥ +2 % → `usd_strong`; ≤ −2 % → `usd_weak` | "dólar fuerte" / "dólar débil" |
| `eurusd` | Δ5 sesiones ≥ 1,5 % en valor absoluto → pista para el inversor en euros | — |

**Semáforo del eje macro**, por mayoría de las tres señales (real, dólar y Nasdaq si hay licencia):
- 🟢 "condiciones financieras holgadas": tipo real a la baja y dólar débil (o Nasdaq al alza).
- 🔴 "condiciones financieras más restrictivas": tipo real al alza y dólar fuerte (o Nasdaq a la baja).
- 🟡 en los demás casos.

Si hay licencia del Nasdaq-100:

| Condición | Estado |
|---|---|
| Δ1 sesión ≥ +1,5 % o ≥ +2σ | `risk_on_strong` "fuerte apetito por el riesgo" |
| Δ1 sesión ≤ −1,5 % o ≤ −2σ | `risk_off_strong` "aversión al riesgo" |
| Δ5 sesiones ≥ +3 % | `risk_on` |
| Δ5 sesiones ≤ −3 % | `risk_off` |
| resto | `risk_neutral` |

### 3.5 Demanda: ETFs

Entradas: flujo de la última sesión (f1), suma de 5 sesiones (f5), racha y distribución de |f1| en las últimas 120 sesiones.

| Condición | `code` | `label_es` |
|---|---|---|
| \|f1\| < pctl30(\|f\|) o \|f1\| < 50 M $ | `flat` | "flujos reducidos" |
| f1 > 0 y \|f1\| ≥ pctl90(\|f\|) | `inflow_strong` | "entradas muy fuertes" |
| f1 > 0 | `inflow` | "entradas" |
| f1 < 0 y \|f1\| ≥ pctl90(\|f\|) | `outflow_strong` | "salidas muy fuertes" |
| f1 < 0 | `outflow` | "salidas" |

La magnitud se mide sobre \|f\| y no sobre el percentil con signo. Así se evita llamar "salidas" a entradas pequeñas cuando la distribución es mayoritariamente positiva.

**Pistas:**
- `h.etf_streak`: si la racha es de 3 o más sesiones: "{{n}}ª sesión consecutiva de entradas (o salidas)".
- `h.etf_biggest_since`: si f1 es la mayor entrada o salida en 60 o más sesiones: "mayor entrada desde el {{fecha}}".
- `h.etf_week`: signo y magnitud de f5.
- `h.etf_provisional`: si el dato es provisional.

**Cautelas obligatorias:**
- "Proxy de demanda canalizada a través de productos regulados; los partícipes no son necesariamente institucionales".
- Si el dato es provisional, se dice.

### 3.6 Demanda: exchanges (si hay licencia)

| Métrica | Regla | Estados |
|---|---|---|
| `exch_netflow_btc_7d` | z robusto sobre 365 días: ≤ −1 → `outflow`; ≥ +1 → `inflow`; resto → `neutral` | "salidas netas de exchanges" / "entradas netas" / "flujos equilibrados" |
| `exch_balance_chg_30d_btc` | signo y pctl de 365 días | pista `h.exch_balance_trend` |

**Frases permitidas:**
- Para salidas: "consistente con retirada hacia custodia propia, aunque también puede reflejar movimientos internos de los exchanges".
- Para entradas: "podría aumentar la oferta disponible en exchanges, sin que implique necesariamente intención de venta".

**Semáforo del eje demanda** (ETF + exchanges):

| ETF (f5) | Exchanges (7 días) | Semáforo |
|---|---|---|
| entradas | salidas o neutral | 🟢 "presión compradora" |
| salidas | entradas o neutral | 🔴 "presión vendedora" |
| resto | | 🟡 "demanda mixta" |

Si solo hay una de las dos fuentes, el eje se basa en ella y la etiqueta lo dice.

### 3.7 On-chain: valoración y cohortes

**Valoración: sin semáforo.** Los colores verde o rojo sobre la valoración se leerían como "barato/caro = comprar/vender". En su lugar se usa un **termómetro textual** con el percentil histórico:

| Métrica | Regla | Etiquetas |
|---|---|---|
| `mvrv` | pctl de toda la historia (desde 2011) **y** de los últimos 4 años; se publica el de 4 años y el completo va en las pistas | pctl < 0,2 → "baja respecto a su historia"; 0,2–0,6 → "intermedia"; 0,6–0,85 → "alta"; ≥ 0,85 → "muy alta" |
| `mvrv` ancla | < 1 → pista `h.mvrv_below_1`: "el precio está por debajo del coste medio on-chain (históricamente infrecuente)" | — |
| `mvrv_z` | igual que MVRV, por percentiles | ídem |
| `supply_in_profit_pct` | ≥ 95 % → pista "casi todo el suministro está en beneficio, algo habitual en zonas de máximos"; ≤ 50 % → "la mitad o más del suministro está en pérdidas" | — |
| `sopr_7d_ma` | > 1,00 → `profit_taking` "realización neta de beneficios"; < 1,00 → `loss_realization` "venta neta con pérdidas". Cruce de 1 → pista `h.sopr_cross` | — |
| `lth_supply_chg_30d_btc` | < −1 % de la oferta LTH → `lth_distribution` "reducción de la oferta de largo plazo"; > +1 % → `lth_accumulation` "maduración o acumulación de largo plazo" | — |

**Cautelas obligatorias:**
- Definición de LTH: "≥150 días, definición BRK".
- Ante `lth_distribution`, añadir "puede reflejar movimientos de custodios o exchanges, no necesariamente ventas".

### 3.8 Derivados (si hay licencia)

Todas las reglas usan el funding normalizado a 8 h y ponderado por OI (FR8) y el OI en **BTC**.

| Métrica | Regla | Estados |
|---|---|---|
| `funding_rate_agg_8h` | Principal: pctl de 365 días. ≥ p95 → `funding_extreme_pos`; ≤ p5 → `funding_extreme_neg`. Anclas: ≤ 0 → `funding_neg` "posicionamiento corto dominante"; 0–0,01 % → `funding_neutral`; 0,01–0,03 % → `funding_long_mild` "sesgo largo moderado"; ≥ 0,03 % → `funding_long_high` "apalancamiento largo elevado" | — |
| `oi_chg_24h_pct` (BTC) | ≥ +10 % → `oi_surge`; ≥ +5 % → `oi_up` "aumento del apalancamiento"; ≤ −5 % → `oi_down` "desapalancamiento"; ≤ −10 % → `oi_flush` "limpieza intensa de posiciones" | — |
| combinación | `oi_up` o `oi_surge` con \|σ_precio\| < 1 → pista `h.lev_without_price` "el apalancamiento crece sin movimiento de precio"; `oi_flush` con liquidaciones ≥ p90 → pista `h.flush` | — |
| `liq_total_usd_24h` | ≥ p95 de 365 días → `liq_spike` "episodio de liquidaciones elevado"; cuota de largos ≥ 75 % con total ≥ p80 → pista "concentrado en largos" (o en cortos) | — |

**Semáforo del eje apalancamiento:**
- 🔴 "apalancamiento elevado": funding ≥ p90 o ≥ 0,03 %, o OI Δ24h ≥ +10 %, o `liq_spike`.
- 🟢 "apalancamiento contenido": 0 ≤ funding ≤ p60 y \|OI Δ24h\| < 5 %.
- 🟡 en los demás casos.

**Cautelas obligatorias:**
- "Liquidaciones: mínimo reportado".
- Los umbrales fijos son heurísticos y no tienen una fuente autorizada; por eso los estados se expresan de forma descriptiva.

### 3.9 Sentimiento

- **Estado:** se usa la clasificación del proveedor (`fng_class`), traducida.
- **Tendencia** con Δ7 = valor hoy − valor hace 7 días:

| Δ7 | Etiqueta |
|---|---|
| ≥ +15 | "mejora notable del sentimiento" |
| +5 a +14 | "mejora" |
| −4 a +4 | "estable" |
| −5 a −14 | "enfriamiento" |
| ≤ −15 | "enfriamiento notable" |

**Pistas:**
- `h.fng_path`: "de {{f:fng_value_7d_ago}} a {{f:fng_value}} en siete días".
- `h.fng_regime_change`: la clasificación ha cambiado respecto a ayer.
- `h.fng_extreme_days`: n días seguidos en zona extrema.
- `h.fng_first_since`: "primer día en codicia extrema desde el {{fecha}}".

**Semáforo del eje sentimiento**, que mide tensión y no dirección:

| Clasificación | Semáforo |
|---|---|
| "Neutral" | 🟢 "sentimiento equilibrado" |
| "Fear" o "Greed" | 🟡 "sentimiento sesgado" |
| "Extreme Fear" o "Extreme Greed" | 🔴 "sentimiento extremo" |

La etiqueta siempre acompaña al color ("🔴 codicia extrema"). Así el rojo no se lee como "vender".

## 4. Semáforo por ejes: resumen

| Eje | Métricas | Significado de 🟢 / 🟡 / 🔴 |
|---|---|---|
| Liquidez | M2 global, liquidez neta de EE. UU. | favorable / neutral o mixta / desfavorable **para la liquidez** |
| Macro | tipo real, dólar, (Nasdaq) | condiciones holgadas / mixtas / restrictivas |
| Demanda | ETF, exchanges | presión compradora / mixta / presión vendedora |
| Apalancamiento | funding, OI, liquidaciones | contenido / moderado / elevado |
| Sentimiento | F&G | equilibrado / sesgado / extremo |
| Precio, valoración on-chain, ciclo | — | **sin color** (termómetro textual) |

Reglas de presentación:
1. **Nunca hay un semáforo global** ni una puntuación agregada.
2. Cada color va acompañado de su etiqueta textual.
3. El Daily muestra como máximo **una línea de ejes** ("Termómetro"), y solo si hay al menos dos ejes con datos. Ejemplo: `🌊 Liquidez 🟢 · 🏛️ Macro 🟡 · 🏦 Demanda 🟢 · ⚡ Apalancamiento 🔴 · 🧠 Sentimiento 🟡`.

## 5. Selección automática de métricas (*salience*)

### 5.1 Puntuación

Para cada métrica candidata i:

```
salience_i = freshness_i × clip(
      0,35 · min(|z_i| / 3, 1)            # rareza estadística del valor o de su variación
    + 0,25 · threshold_i                  # 1 si cruzó un límite de estado hoy; 0,5 si está en estado extremo; 0 si no
    + 0,15 · min(|streak_i| / 5, 1)       # persistencia
    + 0,15 · regime_i                     # 1 si el color de su eje cambió respecto al último Daily
    + 0,10 · context_i                    # 1 si está ligada a un evento de hoy (p. ej. FOMC → tipos) o a una alerta activa
  , 0, 1)

freshness_i = 1 si el as_of es nuevo desde el último Daily publicado; 0,3 si tiene menos de 2 días pero ya se mostró; 0 si no ha cambiado
```

Para cada métrica, `z_i` se calcula sobre la variable más informativa, definida en `rules.yaml`:
- la variación para precios y OI;
- el nivel para funding y F&G;
- el flujo para ETF y exchanges.

### 5.2 Algoritmo de selección para el Daily

1. **Núcleo, siempre:**
   - precio (USD, EUR, 24 h, 7 días);
   - ATH (distancia y días);
   - F&G (hoy, ayer, hace 7 días);
   - régimen de liquidez;
   - flujo ETF de la última sesión (si hay licencia);
   - "Hoy vigilaría…".
2. **Candidatas** (capa C) con salience ≥ 0,35, ordenadas de mayor a menor, con estas limitaciones:
   - máximo 1 por familia; 2 si ambas superan 0,60;
   - máximo **8 indicadores visibles en total**, contando las líneas del núcleo como un indicador por bloque.
3. **Bloques opcionales** (derivados, on-chain, tipos y dólar): solo aparecen si alguna de sus métricas supera 0,50. Es el "solo destacar si hay algo significativo".
4. **Desempate:**
   - diversidad de ejes;
   - frescura;
   - la métrica con cautela más sencilla, porque cabe mejor en 1–2 minutos de lectura.
5. **Fin de semana y festivos de EE. UU.:** ETF, Nasdaq y tipos no tienen dato nuevo, así que su *freshness* es 0. El bloque ETF se sustituye por "sin sesión en EE. UU." solo el primer día sin sesión y después desaparece.
6. **Salida:** se marca `selected=true` en el fact sheet de cada métrica elegida. El LLM recibe **todas** las métricas con estado, pero solo puede escribir sobre las seleccionadas y sobre las pistas asociadas (doc 06).

### 5.3 Ejemplo

Un martes con estos datos:
- flujo ETF −420 M $, tercera sesión seguida de salidas, percentil 88 de |f|;
- F&G de 71 a 58 en 7 días;
- OI +7 % en BTC con el precio plano;
- MVRV sin cambios.

| Métrica | Salience |
|---|---|
| ETF | 0,35·0,62 + 0,25·0 + 0,15·0,6 + 0,15·1 (el eje demanda pasa de 🟡 a 🔴) + 0 ≈ 0,46 → ya es núcleo; además activa la pista `h.etf_streak` |
| F&G | cambio de clasificación de codicia a neutral: 0,35·0,5 + 0,25·1 + … ≈ 0,5 |
| OI | 0,35·0,8 + 0,25·1 (`oi_up`) + 0 + 0,15·1 (el eje apalancamiento pasa a 🔴) ≈ 0,68 → el bloque de derivados aparece |
| MVRV | freshness 1, pero z ≈ 0 → 0,05 → no aparece |

## 6. "Hoy vigilaría…" (una sola variable o evento)

Puntuación determinista. El LLM solo la redacta.

| Evento (de `calendar_events`) | Peso base |
|---|---|
| Decisión del FOMC (+10 si hay proyecciones SEP) | 100 |
| IPC de EE. UU. | 90 |
| Informe de empleo (NFP) | 85 |
| PCE | 75 |
| PIB de EE. UU., estimación avance (40 si es la 2ª o 3ª) | 70 |
| Vencimiento trimestral de opciones BTC en Deribit | 70 |
| Decisión del BCE | 60 |
| Actas del FOMC; comparecencia del presidente de la Fed (25 si es otro gobernador) | 55 |
| Plazo fiscal o regulatorio relevante para ES/AD que vence hoy o en ≤3 días (`config/calendar/regulatory.yaml`) | 50–80 (según su peso en el fichero) |
| Vencimiento mensual en Deribit | 45 |
| Festivo en EE. UU. (no habrá flujos ETF ni Nasdaq) | 35 |
| Último día de negociación de futuros BTC en CME | 30 |
| Cierre anticipado en EE. UU. | 20 |

**Candidatos no programados:**

| Situación | Peso |
|---|---|
| ATH a menos del 2 % → "el nivel del máximo histórico" | 60 |
| Racha ETF de 4 o más sesiones → "si continúa la racha de salidas (o entradas) en los ETF" | 45 |
| Funding ≥ p95 y liquidación de las 08:00 UTC dentro de la mañana (en invierno coincide con las 09:00 de Madrid) | 40 |
| Alerta patrimonial activa en seguimiento | 65 |

**Regla de selección:**
1. Se elige el candidato de mayor peso de **hoy**. Solo se añade un segundo si pesa 50 o más y es de otra naturaleza (p. ej. IPC + plazo fiscal).
2. Si nada de hoy llega a 40, se mira **hasta 3 días** adelante ("el jueves: IPC de EE. UU., 14:30").
3. En fin de semana se mira la semana siguiente.
4. Las horas siempre en Europe/Madrid, calculadas desde UTC.
5. Un evento `postponed` o `cancelled` nunca se anuncia.

## 7. Catálogo de pistas (`interpretation_hints`)

Cada pista es un hecho derivado calculado por código, con su plantilla y sus condiciones. El LLM puede citarlas literalmente, con marcadores, o parafrasearlas **sin añadir cifras**.

| id | Condición | Plantilla |
|---|---|---|
| `h.etf_streak` | racha ETF ≥ 3 | "{{n}}ª sesión consecutiva de {{entradas\|salidas}} en los ETF" |
| `h.etf_biggest_since` | f1 es extremo de ≥ 60 sesiones | "mayor {{entrada\|salida}} desde el {{fecha}}" |
| `h.fng_path` | siempre | "de {{f:fng_value_7d_ago}} a {{f:fng_value}} en siete días" |
| `h.fng_first_since` | cambio a una clase extrema tras ≥ 30 días fuera | "primer día en {{clase}} desde el {{fecha}}" |
| `h.ath_days` | siempre | "{{f:btc_days_since_ath}} días desde el máximo" |
| `h.range_break` | precio en máximo o mínimo de 30/90 días | "máximo (o mínimo) de {{N}} días" |
| `h.eur_vs_usd` | \|Δ7 EUR − Δ7 USD\| ≥ 1,5 pp | "en euros, la semana es {{f:btc_chg_7d_eur_pct}}" |
| `h.m2_fx_driven` | \|fx3\| > 0,5·\|g3\| | "la variación del M2 global se debe sobre todo al tipo de cambio" |
| `h.yield_move` | \|Δ5 10Y\| ≥ 15 pb | "la rentabilidad a 10 años {{sube\|baja}} {{f:us10y_chg_5d_bp}} en cinco sesiones" |
| `h.sopr_cross` | la media de 7 días del SOPR cruza 1 | "el SOPR (7 días) vuelve a situarse {{por encima\|por debajo}} de 1" |
| `h.mvrv_below_1` | MVRV < 1 | "precio por debajo del coste medio on-chain" |
| `h.lev_without_price` | OI ≥ +5 % y \|σ\| < 1 | "el apalancamiento crece sin movimiento de precio" |
| `h.flush` | OI ≤ −10 % y liquidaciones ≥ p90 | "limpieza de posiciones apalancadas" |
| `h.halving_milestone` | hito redondo | "hoy se cumplen {{n}} días del último halving" |
| `h.axis_change` | un eje cambia de color | "el eje {{eje}} pasa a {{estado}}" |

Todas las pistas se validan antes de pasar al LLM: sus números proceden de datos ya validados y su condición se recalcula en el validador (doc 08, V-HINT).

## 8. Calibración y mantenimiento

1. **Backtest** antes del lanzamiento: se reconstruyen los estados diarios con la historia disponible, 2019–2026 según la métrica. Frecuencias objetivo:
   - los estados "extremos" (`*_strong`, `*_extreme`, `liq_spike`) aparecen el 5–10 % de los días;
   - los ejes no cambian de color más de ~2 veces por semana de media.
2. Los umbrales se revisan **trimestralmente** o tras un cambio de régimen evidente, como la entrada de un nuevo tipo de participante. Cada revisión queda registrada con su motivo en `config/rules.yaml → changelog`.
3. Cada informe guarda `rules_version`. Si se recalibra, los estados pasados no se reescriben.
4. Revisión mensual de los estados que el editor corrigió a mano (tabla `editor_actions`) para detectar reglas mal calibradas.
