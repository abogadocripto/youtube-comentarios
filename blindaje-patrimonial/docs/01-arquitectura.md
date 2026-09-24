# 01 — Arquitectura técnica

## 1. Resumen

El sistema tiene dos piezas:
- **Una aplicación Python**, organizada en capas deterministas alrededor de una base PostgreSQL. Se despliega con Docker Compose en un VPS de la UE.
- **Un servidor dedicado con nodo Bitcoin + BRK** para las métricas on-chain propias.

El LLM (Claude, vía API oficial) es un componente más: recibe datos ya validados y devuelve JSON con esquema. **No tiene herramientas, ni acceso a red, ni capacidad de actuar**. Cada salida pasa por validadores de código antes de publicarse.

No se usan plataformas *low-code* (n8n, Make, Zapier), por tres motivos:
- la trazabilidad dato → fuente → licencia;
- las validaciones anti-alucinación;
- la idempotencia de la publicación.

Estas tres cosas son el núcleo del producto y en esas plataformas quedan frágiles y difíciles de probar.

## 2. Vista de capas

```
                         ┌──────────────────────── Servidor NODO (UE) ────────────────────────┐
                         │  bitcoind (nodo completo, sin podar)  ──►  BRK/bitviewd (API local)  │
                         └──────────────────────────────┬──────────────────────────────────────┘
                                                        │ WireGuard (red privada)
┌────────────────────────────────────── VPS APLICACIÓN (UE) ──────────────────────────────────────┐
│                                                                                                   │
│  scheduler (supercronic, CRON_TZ=Europe/Madrid) ──► lanza jobs CLI (`bp <job>`), uno por proceso   │
│                                                                                                   │
│  ┌──────────┐   ┌───────────┐   ┌──────────┐   ┌─────────┐   ┌───────────┐   ┌────────────┐        │
│  │ ingest   │──►│ analysis  │──►│ select   │──►│  llm    │──►│validation │──►│ editorial  │        │
│  │(fuentes) │   │(estados,  │   │(salience,│   │(Claude, │   │(V-*, doc08)│   │(Jinja2,    │        │
│  │          │   │ pistas)   │   │ fact     │   │ JSON)   │   │           │   │ slot-fill) │        │
│  └────┬─────┘   └───────────┘   │ sheet)   │   └─────────┘   └───────────┘   └─────┬──────┘        │
│       │                          └──────────┘                                        │               │
│  ┌────▼─────┐   ┌───────────┐                                                 ┌─────▼──────┐        │
│  │  news    │──►│ scoring / │──► alertas (borrador) ──► adminbot (aprobación)─►│distribution│──► Telegram canal
│  │(RSS/API/ │   │ clustering│──► candidatos Weekly                             │            │──► ESP (email)
│  │ scrape)  │   └───────────┘                                                 │            │──► archivo web
│  └──────────┘                                                                 └────────────┘        │
│  calendar ──► calendar_events                                                                      │
│                                                                                                   │
│  PostgreSQL 16  ◄── todo se persiste (observaciones, señales, informes, llamadas LLM, auditoría)   │
│  adminbot (long polling) ◄──► grupo privado de editores en Telegram                                │
│  observability: logs JSON · heartbeats (Healthchecks) · Sentry UE · informe operativo 09:05       │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## 3. Componentes

| Módulo | Responsabilidad | Notas de diseño |
|---|---|---|
| `ingest` | Un conector por fuente. Cada conector: petición con timeout → `raw_payloads` → parseo → `metric_observations` | Clase base `Connector` con `fetch()`, `parse()` y `contract_test()`. Reintentos con backoff exponencial (tenacity); respeta `Retry-After`. Nunca elude protecciones anti-bot |
| `analysis` | Estadísticos, estados, color por eje, pistas y *salience* (doc 04) | Funciones puras y deterministas; 100 % de tests unitarios con series sintéticas |
| `select` | Construye el **fact sheet** (doc 06): núcleo + candidatas + pistas + cautelas + filtro de licencias | Aquí se aplica el filtro de licencias por primera vez: lo no publicable no entra ni siquiera en el input del LLM |
| `news` | Ingesta de fuentes (RSS, API, HTML, diff de CSV) → normalización → deduplicación → agrupación en eventos → clasificación LLM → puntuación | Ver doc 05. Los textos de terceros se tratan siempre como **datos no fiables** (inyección de instrucciones) |
| `calendar` | Mantiene `calendar_events` desde fuentes oficiales y YAML anuales; conciliación nocturna | Estados `postponed` y `cancelled` |
| `llm` | Cliente de Claude: prompts versionados, salida estructurada, reintentos, fallback del servidor, costes | Sin *tools*. Respuesta validada contra un modelo Pydantic |
| `validation` | Validadores deterministas (V-*) + verificador LLM independiente | Ver doc 08. Un fallo bloqueante impide publicar |
| `editorial` | Plantillas Jinja2 (Telegram HTML, email HTML/texto, web); formato numérico es-ES; sustitución de marcadores `{{f:…}}` | La única capa que convierte números en texto |
| `distribution` | Telegram Bot API, API del ESP, generación del archivo web estático | Idempotencia por `publications.idempotency_key` |
| `admin` / `adminbot` | Bot privado: previsualizaciones, aprobar, editar o rechazar, corregir o retirar, pausar, estado | Solo atiende a una lista cerrada de IDs de usuario de Telegram |
| `orchestrator` | Definición de jobs, dependencias, idempotencia, bloqueos | Cada job es `bp <job> --date YYYY-MM-DD`: reejecutable y seguro |
| `observability` | Logs estructurados, heartbeats, alertas al operador, informe operativo | — |

## 4. Flujos

### 4.1 Ventanas de ingesta (Europe/Madrid)

| Hora | Job | Qué recoge |
|---|---|---|
| cada 5 min | `watch_market` | peg de USDT/USDC, precio de BTC (reglas de alerta de mercado); coste ≈ 8.600 llamadas/mes en CoinGecko |
| cada 15–60 min según la fuente | `ingest_news` | fuentes de noticias según `poll_interval` (doc 05) |
| 00:30 | `ingest_macro_night` | curvas del Tesoro (publicadas hacia las 18:00 ET), H.4.1 (jueves), tipos del BCE, DTS, NY Fed |
| 02:00 | `calendar_reconcile` | concilia calendarios y avisa de cambios de fecha |
| 08:30 | `ingest_daily` | precio, ATH, F&G, BRK, bloque, derivados y ETF (si hay licencia); completa lo que falte del macro |
| 14:00 y 23:30 | `ingest_etf_late` | datos tardíos y revisiones de los ETF |
| sábado 10:00 | `build_weekly` | borrador del Weekly (§4.3) |

### 4.2 Daily Bitcoin (secuencia)

```
08:30  ingest_daily        conectores en paralelo (asyncio), timeout de 20 s por petición y 2 reintentos
08:42  ingest_retry        reintento selectivo de conectores fallidos (hasta las 08:45)
08:45  quality_checks      frescura (max_staleness), rangos, desviación entre fuentes, completitud de ETF
08:48  analyze             derived_signals + axis_states (rules_version)
08:49  build_fact_sheet    salience → selección → pistas → filtro de licencias → fact sheet JSON
08:50  llm_daily           Claude → JSON (lectura, vigilar, frases por bloque) con marcadores {{f:…}}
08:53  validate_daily      V-* deterministas + verificador LLM; si falla: 1 reintento con los errores como feedback
08:57  render_daily        slot-filling → HTML Telegram → previsualización en el grupo admin
09:00  publish_daily       sendMessage al canal (idempotente); guarda el message_id
09:05  ops_report          resumen operativo en el grupo admin (fuentes KO, avisos, coste)
```

Matriz de degradación (el Daily **siempre** sale si hay datos núcleo):

| Fallo | Comportamiento |
|---|---|
| Una métrica candidata falla o está obsoleta | Se omite; si su bloque se queda vacío, desaparece el bloque |
| ETF sin sesión completa | Se publica la última sesión completa con su fecha, o "dato ETF pendiente" |
| F&G sin dato del día | Se omite la línea (nunca se usa el índice de CMC) |
| El LLM falla, rechaza (`refusal`) o la validación falla dos veces | **Versión "solo datos"**: bloques de datos + lectura determinista por plantillas (`editorial/fallback_reading.py`) + aviso al editor |
| Precio no disponible o incoherente (>1,5 % entre fuentes) hasta las 08:50 | **No se publica**; se avisa al editor con el diagnóstico; reintentos automáticos hasta las 10:00; si se resuelve, se publica con la marca "publicado a las HH:MM" |
| Telegram devuelve un error explícito (5xx, 429) | Reintento respetando `retry_after` (la petición no se procesó) |
| Timeout de red **después** de enviar la petición (ambiguo) | **No se reintenta**: la Bot API no tiene clave de idempotencia y el bot no puede leer el historial del canal. Aviso al editor con los botones [Se publicó] / [Publicar ahora] (doc 09 §3) |
| La base de datos no está disponible | El job falla y el heartbeat no llega → alerta al operador (SMS o email de Healthchecks) |

### 4.3 Informe semanal

```
sáb 10:00  build_weekly: agrega daily_reports L–D, selecciona news_events de la semana (doc 05), prepara los documentos fuente S01..Sn
sáb 10:10  llm_weekly (Claude) → JSON por secciones, con citas literales (evidence_quote) por afirmación
sáb 10:20  validate_weekly (V-* + verificador) → render email + web → crea la campaña en el ESP como BORRADOR
sáb 10:25  envía email de prueba al editor + previsualización en el grupo admin con botones [Aprobar] [Editar] [Descartar]
sáb–dom    revisión humana (obligatoria)
dom 18:00  envío programado si está aprobado (hora configurable en settings.weekly.send_time); si no hay aprobación, no se envía y se avisa
```

Hora de envío: domingo a las 18:00 (recomendada). Es cuando el lector planifica la semana, ya tiene cerrados los datos del viernes de EE. UU. y los boletines oficiales del viernes, y hay margen para la revisión.

### 4.4 Alertas

- **Por noticias.** `ingest_news` → clasificación → puntuación ≥ umbral (doc 05) → borrador de alerta (LLM + validación) → grupo admin con botones → publicación en el canal (+ email opcional).
  - SLA objetivo de aprobación: 30 min en horario laboral.
  - Fuera de horario, el borrador espera; las alertas caducan a las 24 h.
- **Por reglas de mercado.** Ejemplos: depeg de USDT/USDC > 3 % sostenido 60 min; nuevo ATH confirmado; flujo ETF extremo (doc 04, `etf.alert`).
  - El texto es de plantilla, sin LLM, porque es un hecho numérico.
  - Por defecto también requiere aprobación. `settings.alerts.autopublish_market_rules=true` permite autopublicarlas.
- **Antifatiga:**
  - máximo 2 alertas públicas por semana, salvo que el editor fuerce una tercera;
  - `dedup_key` por hecho;
  - enfriamiento de 72 h por tema.

## 5. Orquestación, idempotencia y concurrencia

- **Planificador:** **temporizadores de systemd** en el host, que lanzan `docker compose run --rm app bp <job>`.
  - Ejemplo: `publish-daily.timer` con `OnCalendar=*-*-* 09:00:00 Europe/Madrid`, `AccuracySec=1s` (el valor por defecto es 1 minuto) y `RandomizedDelaySec=0`. Los cambios de hora de marzo y octubre no desplazan la publicación.
  - `Persistent=true` solo en la ingesta. La publicación no se recupera sola después de las 10:30: pide confirmación humana.
  - Cada job es un proceso independiente: un fallo no contamina al siguiente.
  - Alternativa equivalente: `supercronic` con `CRON_TZ=Europe/Madrid` dentro del contenedor.
- **Respaldo de publicación:** a las 09:07, un segundo temporizador en el mismo VPS ejecuta `bp publish-daily --only-if-missing`. Cubre un fallo del job de las 09:00, no una caída del servidor.
  - *Corrección respecto a la primera versión del diseño:* un disparador externo (Cloud Scheduler o GitHub Actions) no puede publicar por sí solo, porque publicar exige la base de datos con el borrador validado. Exponer PostgreSQL a internet para ello sería peor remedio que el problema.
  - Ante una caída del VPS, la capa externa es la **alerta de Healthchecks** al operador (sin ping de publicación a las 09:02).
- **Publicación sin borrador:** si a las 09:00 no hay borrador publicable, `publish-daily` genera en el acto la lectura por plantillas (sin LLM) y publica; si faltan los datos núcleo, no publica y avisa.
- **Idempotencia.** Cada job registra `job_runs.idempotency_key` (`publish_daily:2026-09-23`); si ya terminó con éxito, no hace nada. Cada envío registra `publications.idempotency_key`. Reintentar nunca duplica.
- **Bloqueos.** Se usa `pg_advisory_lock` por familia de jobs, para que dos procesos no construyan a la vez el mismo informe.
- **Publicación desacoplada.** `publish_daily` solo envía un borrador ya validado. Si a las 08:58 no hay borrador `validated`, genera la versión de respaldo. Así la puntualidad de las 09:00 no depende de la latencia del LLM.
- **Reloj.** NTP en el VPS; todas las horas internas en UTC, con conversión a Europe/Madrid solo al presentar.

## 6. Despliegue

### 6.1 Infraestructura

| Recurso | Especificación | Proveedor sugerido | Coste orientativo |
|---|---|---|---|
| VPS aplicación | 2 vCPU, 4 GB RAM (Hetzner CX23) o superior, UE | Hetzner (Falkenstein, Núremberg o Helsinki) u OVH (FR) | CX23: 5,49 €/mes sin IVA ni IPv4, tras la subida de precios del 15 jun 2026; ~7–10 €/mes en total. Hetzner subió precios tres veces en 2026: conviene presupuestar con margen |
| Servidor nodo | 2 TB NVMe, 32 GB RAM, UE | Hetzner dedicado / subasta | 40–80 €/mes **[VERIFICAR]** |
| Almacenamiento de objetos (copias) | UE, cifrado | Hetzner Object Storage / Scaleway / Backblaze EU | <5 €/mes |
| DNS + web estática del archivo | — | Cloudflare Pages / GitHub Pages | 0 € |
| Monitorización | heartbeats + errores | Healthchecks.io (plan gratuito) + Sentry (región UE, plan gratuito) | 0 € |

### 6.2 Servicios (docker-compose)

```yaml
services:
  postgres:   {image: postgres:16, volumes: [pgdata:/var/lib/postgresql/data]}
  app:        {build: ., env_file: .env, depends_on: [postgres]}      # lo invocan los temporizadores de systemd: `docker compose run --rm app bp <job>`
  adminbot:   {build: ., command: bp adminbot, env_file: .env, depends_on: [postgres]}
  backup:     {image: <pg-backup-s3>, schedule: "30 3 * * *"}
# Servidor nodo (compose aparte): bitcoind + bitviewd (versión fijada), expuestos solo por WireGuard.
```

### 6.3 Entornos

| Entorno | Uso | Publicación |
|---|---|---|
| `dev` | Local con fixtures grabados de cada fuente | nada (salida a fichero) |
| `staging` / **modo sombra** | Mismo despliegue que producción durante 2–3 semanas antes del lanzamiento | canal de Telegram **privado de pruebas** + ESP con lista de prueba |
| `prod` | Operación | canal público + ESP real |

El paso de sombra a producción se decide con los criterios de aceptación del doc 12:
- 14 días seguidos publicados a las 09:00 ±1 min;
- 0 fallos bloqueantes no detectados;
- evaluación editorial ≥ 4/5.

## 7. Observabilidad

- **Logs** JSON (structlog) con `job`, `run_id`, `report_date` y `source`; rotación local y envío opcional a Grafana Loki.
- **Heartbeats** (Healthchecks.io):
  - `daily-published`: debe llegar antes de las 09:02; si no, email o SMS al operador;
  - `ingest-news`: cada hora;
  - `backup`: diario;
  - `node-sync`: el nodo está a menos de 3 bloques de la punta.
- **Errores:** Sentry, región UE, sin datos personales.
- **Informe operativo** diario a las 09:05 en el grupo admin:
  - qué se publicó;
  - fuentes caídas u obsoletas;
  - métricas omitidas y por qué;
  - avisos de validación;
  - coste de LLM del día;
  - alertas pendientes de aprobar.
- **Panel mínimo** con consultas SQL predefinidas (o Metabase autoalojado): salud por fuente, frescura por métrica y coste mensual.

## 8. Seguridad

1. **Secretos** (claves de API, tokens de bots, credenciales del ESP):
   - en `.env` cifrado con `sops` + `age` en el repositorio, o en el gestor de secretos del proveedor;
   - nunca en logs ni en `raw_payloads.request_url` ni en `llm_calls.request`.
2. **Dos bots de Telegram distintos:**
   - **publicador**, administrador del canal y solo con permiso para publicar;
   - **adminbot**, que solo responde a una lista cerrada de IDs.

   Si se compromete uno, no se compromete el otro. 2FA en la cuenta de Telegram propietaria del canal.
3. **Inyección de instrucciones:**
   - el texto de noticias y documentos de terceros va delimitado y marcado como datos no fiables;
   - el LLM no tiene herramientas;
   - sus salidas se validan contra esquema y reglas;
   - una noticia no puede, por diseño, "ordenar" nada al sistema.
4. **Mínimo privilegio:** usuario de BD de solo lectura para el panel y usuario con escritura para los jobs; el nodo Bitcoin solo es accesible por WireGuard.
5. **Dependencias:** versiones fijadas (`uv.lock`); Dependabot/Renovate; imagen base mínima.
6. **Copias:** cifradas, con prueba de restauración mensual.
7. **Cuentas de proveedores:** 2FA, facturación a nombre de la sociedad correcta del grupo **[confirmar cuál: ABAST Legal / ABAST Global]** y archivo de términos en el registro de licencias.

## 9. Estrategia de pruebas

| Tipo | Qué cubre |
|---|---|
| Unitarias | `analysis` (reglas, histéresis, percentiles), `editorial.format` (formato es-ES, signos, unidades), marcadores |
| Contrato por fuente | Respuestas grabadas (fixtures) + prueba en vivo diaria (`contract_test`) que avisa si cambia el esquema |
| Golden tests de renderizado | Fact sheet fijo → mensaje Telegram exacto esperado |
| Validadores adversariales | Batería de salidas LLM "malas" (cifras inventadas, verbos predictivos, fuentes inexistentes, citas alteradas) que **deben** ser rechazadas (doc 08 §6) |
| Backtest editorial | Regenerar Dailies de 60 días históricos y evaluarlos a ciegas (doc 08 §7) |
| Extremo a extremo | Ensayo completo en staging con reloj simulado (`--now`) |

## 10. Estructura del repositorio (propuesta para el desarrollo)

```
blindaje-patrimonial/
├─ pyproject.toml / uv.lock
├─ deploy/systemd/              # *.service + *.timer (OnCalendar … Europe/Madrid, AccuracySec=1s)
├─ docker/ (Dockerfile, compose.yml, compose.node.yml)
├─ config/ (metrics.yaml, rules.yaml, sources.yaml, news_sources.yaml, fomc.yaml, calendar/*.yaml, editorial.yaml)
├─ prompts/ (daily.system.md, daily.user.md, weekly.*, alert.*, classify.*, verify.*)
├─ schema/ (schema.sql, llm/*.schema.json)
├─ src/bp/
│  ├─ cli.py                    # `bp <job>`
│  ├─ ingest/  (base.py, coingecko.py, alternative_me.py, treasury.py, nyfed.py, fiscaldata.py, fed_board.py,
│  │            ecb.py, boe.py, boj.py, pboc.py, brk.py, mempool.py, sosovalue.py, coinglass.py, coinalyze.py, deribit.py)
│  ├─ analysis/ (stats.py, rules.py, axes.py, hints.py, salience.py)
│  ├─ select/  (fact_sheet.py, licence_gate.py)
│  ├─ news/    (fetchers/, parsers/, dedup.py, cluster.py, classify.py, score.py)
│  ├─ calendar/
│  ├─ llm/     (client.py, models.py [Pydantic], prompts.py)
│  ├─ validation/ (deterministic.py, verifier.py, lexicon.py)
│  ├─ editorial/ (format.py, render.py, fallback_reading.py, templates/)
│  ├─ distribution/ (telegram.py, esp.py, web_archive.py)
│  ├─ admin/   (adminbot.py)
│  ├─ orchestrator/ (jobs.py, locks.py)
│  └─ observability/
├─ tests/ (unit/, contract/fixtures/, golden/, adversarial/)
└─ docs/
```

## 11. Decisiones de stack y alternativas descartadas

| Decisión | Elegido | Alternativas y motivo del descarte |
|---|---|---|
| Lenguaje | Python 3.12 | TypeScript: igual de viable, pero el ecosistema de datos (pandas, calendarios bursátiles, estadística) y el SDK de Anthropic en Python simplifican la capa de análisis |
| Base de datos | PostgreSQL 16 | SQLite: suficiente en volumen, pero peor para concurrencia (adminbot + jobs), bloqueos consultivos y jsonb; TimescaleDB: innecesario con este volumen |
| Planificación | supercronic / systemd en un VPS | GitHub Actions cron: retrasos documentados, inaceptables para las 09:00 (se usa solo para CI); serverless (Cloud Run + Scheduler): viable, pero complica la persistencia y el bot con *long polling* |
| LLM | Claude (`claude-opus-5`) con salida estructurada | — (ver doc 06; el modelo se puede cambiar por configuración) |
| Plantillas | Jinja2 | Generación de texto completo por el LLM: descartada por el principio de *slot-filling* |
| On-chain | BRK autoalojado | Glassnode o CryptoQuant para todo: coste o licencia incompatibles con la difusión pública (doc 02 §3.6) |
| Orquestación | Código propio (jobs idempotentes) | Airflow o Prefect: sobredimensionados para ~15 jobs; n8n o Make: trazabilidad y pruebas insuficientes |
