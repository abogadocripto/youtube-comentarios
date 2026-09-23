# 03 — Modelo de datos

> DDL de referencia: `schema/schema.sql`. Es PostgreSQL 16 y **se ha validado aplicándolo a una instancia real**: carga las 90 definiciones de `config/metrics.yaml` y responde la vista `v_latest_metric`. En desarrollo se gestionará con migraciones de Alembic, partiendo de este fichero.

## 1. Principios

1. **Append-only para los datos.** Las observaciones nunca se sobrescriben. Una corrección o revisión es una fila nueva con `revision_n+1` y `status='revised'`, y la anterior queda intacta. Así se puede responder siempre a "¿qué sabíamos a las 08:50 del día X?".
2. **Dos tiempos distintos:**
   - `as_of` es el momento al que se refiere el dato: la sesión de EE. UU., el cierre diario UTC o el mes del M2.
   - `retrieved_at` es cuándo lo obtuvimos.

   El validador de frescura compara `as_of` con `max_staleness`.
3. **Vintages.** Todas las observaciones obtenidas en una misma lectura de una fuente comparten `vintage_id`. Las variaciones (7 o 30 días) de las fuentes que revisan su historia, como los saldos en exchanges, se calculan **dentro de un mismo vintage**.
4. **Trazabilidad completa.** Toda cifra publicada se puede seguir hasta su origen:

   ```
   publicación → daily_report.fact_sheet → derived_signals → metric_observations → raw_payloads (respuesta HTTP original, hash SHA-256)
   ```
5. **Licencia en el dato.** Cada observación referencia la licencia vigente de su fuente (`licence_id`). El renderizador consulta `source_licences.display_allowed` antes de publicar.
6. **Minimización (RGPD).** La base de datos no guarda datos personales de suscriptores; los gestiona el proveedor de email con su DPA. Solo se guardan los identificadores de Telegram de los editores autorizados, para auditar sus acciones.

## 2. Mapa de entidades

```
sources ─┬─< source_licences          (registro de licencias con evidencia)
         ├─< source_health            (disponibilidad por fuente)
         ├─< raw_payloads ─┐
         │                 └─< metric_observations >── metric_definitions (sincronizada desde metrics.yaml)
         │                           │
         │                           └─< derived_signals ──> axis_states (por día y eje)
         ├─< calendar_events
         └─< news_sources ─< news_items >── news_events ─< alerts
                               └─< news_classifications ──> llm_calls

daily_reports  ── fact_sheet, llm_output, validation_report_id ──> validation_reports
weekly_reports ── selected_event_ids, source_documents, validation_report_id
alerts         ── event_id | rule_id, validation_report_id
publications   (una fila por envío a cada canal, con clave de idempotencia)
job_runs · editor_actions · settings
```

## 3. Tablas y decisiones relevantes

| Tabla | Para qué | Claves y decisiones |
|---|---|---|
| `sources` | Catálogo de fuentes (datos y noticias) | `licence_status`, `attribution_text`, `attribution_inline` (alternative.me exige la atribución junto al dato), `llm_input_allowed` (p. ej. Coin Metrics Community = false) |
| `source_licences` | Evidencia de lo que permite cada fuente | Solo una licencia vigente por fuente (índice único parcial); guarda el hash de los términos archivados; revisión trimestral |
| `metric_definitions` | Copia en BD de `metrics.yaml` | La YAML manda; se sincroniza al arrancar y la entrada completa se guarda en `definition` (jsonb) |
| `raw_payloads` | Respuesta HTTP original | URL **sin claves**; `sha256`; el cuerpo se purga a los 180 días (los metadatos se conservan) |
| `metric_observations` | Dato normalizado | Identidad = (métrica, dimensión, as_of, fuente, vintage). `dimension` permite guardar componentes: `venue=binance`, `ticker=IBIT`, `country=CN`. `secondary_value` y `deviation_pct` registran el contraste entre fuentes |
| `derived_signals` | Salida de la capa de análisis | Una fila por (métrica, as_of, `rules_version`). Contiene estadísticos, estado, color, *salience*, pistas y cautelas |
| `axis_states` | Color de cada eje por día | Permite detectar cambios de color (entrada `regime` de la *salience*) |
| `calendar_events` | Agenda | Hora en UTC + `tz_origin`; `time_precision`; estados `postponed` y `cancelled` para cierres de la administración de EE. UU. |
| `news_sources`, `news_items` | Ingesta de noticias | `url_hash` único (deduplicación exacta); `simhash` (casi duplicados); `content_sha256`; `etag`/`last_modified` para peticiones condicionales |
| `news_events` | Agrupación de noticias sobre un mismo hecho | `impact_score` y desglose; `corroboration` (número de fuentes independientes); `best_tier` |
| `news_classifications` | Salida del clasificador LLM | Rasgos 0–5 con justificación; perfiles afectados; salida completa validada contra esquema |
| `llm_calls` | Auditoría y coste de cada llamada | Modelo solicitado y modelo servido (fallback del servidor), tokens, coste, `stop_reason`, petición y respuesta **sin secretos** |
| `validation_reports` | Resultado de cada validación | Lista de comprobaciones con severidad; número de intento |
| `daily_reports` | Un registro por día | Guarda el `fact_sheet` exacto enviado al LLM, la salida validada, el mensaje final y el `telegram_message_id`; estados, incluidos `fallback`, `withheld`, `corrected` y `retracted` |
| `weekly_reports` | Uno por semana ISO | Documentos fuente entregados al LLM (`S01…Sn`), HTML y texto final, id de campaña del ESP, aprobación |
| `alerts` | Borradores y alertas publicadas | `dedup_key` único mientras la alerta está viva; flujo de aprobación; caducidad |
| `publications` | Envíos por canal | `idempotency_key` único (p. ej. `telegram_public:daily:2026-09-23`): **impide publicar dos veces** aunque un job se reintente |
| `job_runs` | Ejecuciones programadas | Clave de idempotencia por job y fecha; estadísticas; error |
| `editor_actions` | Auditoría de decisiones humanas | Aprobar, rechazar, editar, corregir, retirar, pausar |
| `settings` | Interruptores en caliente | `daily.hold`, `alerts.autopublish_market_rules`, `weekly.send_time`… |

## 4. Semántica de `as_of` por tipo de dato

| `as_of_semantics` (en metrics.yaml) | Qué guarda `as_of` | Ejemplo |
|---|---|---|
| `provider_ts` | Marca temporal del proveedor (`last_updated`) | precio a las 06:30:12 UTC |
| `utc_day_close` | 00:00 UTC del día **siguiente** al periodo (cierre del día D‑1) | SOPR del 22 sep → `2026-09-23T00:00Z` |
| `us_session` | 16:00 America/New_York de la sesión, convertido a UTC | flujos ETF del lunes 21 → `2026-09-21T20:00Z` |
| `business_day_p1` / `business_day_p2` | Fecha de observación del dato oficial | curva del Tesoro del 22 sep |
| `week_wed` | Miércoles de referencia (H.4.1) | balance de la Fed del 16 sep |
| `month_end` / `month_avg` | Último día del mes de referencia | M2 de agosto → `2026-08-31` |
| `computed` | El `as_of` más antiguo de sus entradas | liquidez neta = mínimo(as_of del balance de la Fed, TGA, RRP) |

`as_of_label` guarda la etiqueta legible que imprimirá el renderizador ("sesión del lunes 21 sep", "M2 de agosto").

## 5. Ciclo de vida de una observación

```
provisional ──(sin cambios en 2 lecturas separadas ≥24 h y conciliada)──> final
     │                                                                │
     └──(una nueva lectura difiere más de la tolerancia)──> revised (nueva fila, revision_n+1)
cualquier estado ──(control de calidad fallido)──> rejected (no entra en v_latest_metric)
```

Si se revisa un dato **ya publicado** por encima de la tolerancia definida por métrica en `rules.yaml` (p. ej. max(10 M $, 5 %) para los ETF):
- se registra en `quality_notes`;
- el Weekly incluye una nota de "revisado";
- se avisa al editor, que decide si corregir el mensaje de Telegram.

Nunca se edita en silencio.

## 6. Retención y copias

| Dato | Retención |
|---|---|
| `metric_observations`, `derived_signals`, informes, `llm_calls`, `validation_reports`, `editor_actions`, `publications` | Indefinida (auditoría; volumen pequeño, <1 GB/año estimado) |
| `raw_payloads.body` | 180 días (después solo metadatos y hash) |
| `news_items.content_text` | 2 años (solo el texto necesario para el análisis; se respetan los términos de cada fuente) |
| `source_health` | 90 días |

**Copias de seguridad:**
- `pg_dump` diario cifrado (age/GPG) en almacenamiento de objetos en la UE: 30 copias diarias y 12 mensuales.
- Prueba de restauración mensual automatizada: se restaura en una base temporal y se ejecuta una consulta de control.

## 7. Consultas que el diseño debe resolver (criterios de aceptación)

1. "¿Qué valor tenía `etf_net_flow_usd_1d` para la sesión del 21 sep, según lo que sabíamos a las 08:50 del 22 sep?". Se obtiene filtrando `retrieved_at ≤ '2026-09-22 06:50Z'`.
2. "¿Cuántos días seguidos lleva el F&G en codicia extrema?". Se resuelve con `derived_signals` y el estado por día.
3. "¿Qué cifras del Daily del 23 sep no procedían de una fuente con licencia de difusión?". La respuesta debe ser siempre **ninguna**: se cruzan `publications`, `daily_reports.fact_sheet`, `metric_observations` y `source_licences`.
4. "¿Qué noticias fiscales de España con puntuación ≥ 50 no entraron en el Weekly de la semana 39, y por qué?". Se consulta `news_events` con su estado y su desglose de puntuación.
5. "Coste de LLM del mes por producto". Se agrupa `llm_calls` por `purpose`.
