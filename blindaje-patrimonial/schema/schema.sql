-- Blindaje Patrimonial — esquema PostgreSQL 16 (diseño v1, 2026-09-23)
-- En desarrollo se gestionará con Alembic; este fichero es la especificación de referencia.
-- Convenciones:
--   * Todas las marcas temporales en UTC (timestamptz). La presentación en Europe/Madrid es responsabilidad de `editorial`.
--   * `as_of`      = momento al que se refiere el dato (sesión, cierre diario UTC, fecha de observación).
--   * `retrieved_at` = momento en que lo obtuvimos. Nunca se confunden.
--   * Sin datos personales de suscriptores (los gestiona el proveedor de email).

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- ─────────────────────────── ENUMS ───────────────────────────
CREATE TYPE licence_status AS ENUM ('self_computed','official_open','licensed_public','permission_pending','internal_only','prohibited');
CREATE TYPE obs_status     AS ENUM ('provisional','final','revised','rejected');
CREATE TYPE quality_flag   AS ENUM ('ok','warn','error');
CREATE TYPE axis_color     AS ENUM ('green','amber','red','none');
CREATE TYPE source_tier    AS ENUM ('T1','T2','T3');
CREATE TYPE job_status     AS ENUM ('scheduled','running','succeeded','failed','skipped');

-- ─────────────────────────── FUENTES Y LICENCIAS ───────────────────────────
CREATE TABLE sources (
    id                text PRIMARY KEY,                 -- p. ej. 'coingecko_basic', 'us_treasury_xml', 'brk_selfhosted'
    name              text NOT NULL,
    kind              text NOT NULL,                    -- api | rss | ics | csv | html | rpc | config | computed
    base_url          text,
    tier              source_tier,                      -- relevante para noticias
    licence_status    licence_status NOT NULL,
    attribution_text  text,                             -- texto exacto exigido ("Data provided by CoinGecko")
    attribution_inline boolean NOT NULL DEFAULT false,  -- la atribución debe ir junto al dato (alternative.me)
    llm_input_allowed boolean NOT NULL DEFAULT true,    -- false p. ej. si los términos prohíben usar datos para generar salidas de modelos
    notes             text,
    active            boolean NOT NULL DEFAULT true,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

-- Registro de licencias: evidencia de lo que permite cada fuente (revisión trimestral).
CREATE TABLE source_licences (
    id                  bigserial PRIMARY KEY,
    source_id           text NOT NULL REFERENCES sources(id),
    plan                text,                            -- 'Basic', 'Standard', 'free-with-attribution', 'permiso escrito 2026-10-02'
    display_allowed     boolean NOT NULL,                -- ¿se puede mostrar públicamente?
    commercial_allowed  boolean NOT NULL,
    storage_allowed     boolean NOT NULL DEFAULT true,   -- ¿se puede almacenar histórico?
    llm_input_allowed   boolean NOT NULL DEFAULT true,
    attribution_text    text,
    conditions          text,                            -- límites (usuarios, productos, retención tras baja…)
    evidence_url        text,
    evidence_sha256     text,                            -- hash del PDF/captura archivado de los términos
    reviewed_at         date NOT NULL,
    reviewer            text NOT NULL,
    valid_until         date,
    is_current          boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_source_licences_current ON source_licences(source_id) WHERE is_current;

CREATE TABLE source_health (
    id           bigserial PRIMARY KEY,
    source_id    text NOT NULL REFERENCES sources(id),
    checked_at   timestamptz NOT NULL DEFAULT now(),
    ok           boolean NOT NULL,
    http_status  int,
    latency_ms   int,
    error        text
);
CREATE INDEX ix_source_health_src_time ON source_health(source_id, checked_at DESC);

-- ─────────────────────────── MÉTRICAS ───────────────────────────
-- Sincronizada desde config/metrics.yaml al arrancar (la YAML manda).
CREATE TABLE metric_definitions (
    metric_id            text PRIMARY KEY,
    label_es             text NOT NULL,
    family               text NOT NULL,
    axis                 text NOT NULL,
    unit                 text NOT NULL,
    fmt                  text NOT NULL,
    freq                 text NOT NULL,
    as_of_semantics      text NOT NULL,
    max_staleness        interval NOT NULL,
    layer                char(1) NOT NULL CHECK (layer IN ('N','C','B')),
    mvp                  boolean NOT NULL,
    licence_status       licence_status NOT NULL,
    methodology_version  int NOT NULL DEFAULT 1,
    definition           jsonb NOT NULL,                 -- entrada completa de la YAML
    updated_at           timestamptz NOT NULL DEFAULT now()
);

-- Respuestas brutas de las fuentes (auditoría y reprocesado).
CREATE TABLE raw_payloads (
    id            bigserial PRIMARY KEY,
    source_id     text NOT NULL REFERENCES sources(id),
    request_url   text NOT NULL,                         -- SIN claves ni secretos
    http_status   int,
    fetched_at    timestamptz NOT NULL DEFAULT now(),
    content_type  text,
    sha256        text NOT NULL,
    body          bytea,                                 -- se purga a los 180 días (metadatos se conservan)
    storage_key   text,                                  -- alternativa: objeto en almacenamiento externo
    job_run_id    bigint,
    purged_at     timestamptz
);
CREATE INDEX ix_raw_payloads_src_time ON raw_payloads(source_id, fetched_at DESC);
CREATE INDEX ix_raw_payloads_sha ON raw_payloads(sha256);

-- Observaciones: append-only. Una fila por (métrica, dimensión, as_of, fuente, vintage).
CREATE TABLE metric_observations (
    id               bigserial PRIMARY KEY,
    metric_id        text NOT NULL REFERENCES metric_definitions(metric_id),
    dimension        text NOT NULL DEFAULT '',           -- '' = agregado; 'venue=binance', 'ticker=IBIT', 'country=CN'
    as_of            timestamptz NOT NULL,
    as_of_label      text,                               -- 'sesión EE. UU. 2026-09-22', 'M2 ago-2026'
    value_num        numeric,
    value_text       text,
    value_json       jsonb,
    unit             text NOT NULL,
    source_id        text NOT NULL REFERENCES sources(id),
    source_url       text,                               -- endpoint sin claves
    retrieved_at     timestamptz NOT NULL,
    raw_payload_id   bigint REFERENCES raw_payloads(id),
    method           text NOT NULL CHECK (method IN ('provider_field','computed','fallback','manual')),
    vintage_id       uuid NOT NULL DEFAULT gen_random_uuid(),   -- misma lectura = mismo vintage
    status           obs_status NOT NULL DEFAULT 'provisional',
    revision_n       int NOT NULL DEFAULT 0,
    quality          quality_flag NOT NULL DEFAULT 'ok',
    quality_notes    jsonb,                              -- desviación entre fuentes, controles fallidos…
    secondary_value  numeric,                            -- valor de la fuente de contraste
    deviation_pct    numeric,
    licence_id       bigint REFERENCES source_licences(id),
    job_run_id       bigint,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_has_value CHECK (value_num IS NOT NULL OR value_text IS NOT NULL OR value_json IS NOT NULL)
);
CREATE UNIQUE INDEX ux_obs_identity ON metric_observations(metric_id, dimension, as_of, source_id, vintage_id);
CREATE INDEX ix_obs_metric_asof ON metric_observations(metric_id, dimension, as_of DESC);
CREATE INDEX ix_obs_retrieved ON metric_observations(retrieved_at DESC);

-- Última observación válida por métrica (agregada), para el fact sheet.
CREATE VIEW v_latest_metric AS
SELECT DISTINCT ON (o.metric_id)
       o.metric_id, o.as_of, o.as_of_label, o.value_num, o.value_text, o.value_json, o.unit,
       o.source_id, o.source_url, o.retrieved_at, o.status, o.quality, o.id AS observation_id
FROM metric_observations o
WHERE o.dimension = '' AND o.status <> 'rejected' AND o.quality <> 'error'
ORDER BY o.metric_id, o.as_of DESC, o.retrieved_at DESC;

-- Señales derivadas (capa de análisis). Una fila por métrica, as_of y versión de reglas.
CREATE TABLE derived_signals (
    id              bigserial PRIMARY KEY,
    metric_id       text NOT NULL REFERENCES metric_definitions(metric_id),
    as_of           timestamptz NOT NULL,
    computed_at     timestamptz NOT NULL DEFAULT now(),
    rules_version   int NOT NULL,
    observation_id  bigint REFERENCES metric_observations(id),
    stats           jsonb NOT NULL,          -- {chg_1d, chg_7d, z_365, pctl_365, streak, n_day_extreme, degraded}
    state_code      text,
    state_label_es  text,
    axis            text,
    color           axis_color NOT NULL DEFAULT 'none',
    salience        numeric(4,3),
    hints           jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{id, text_template, params, verified:true}]
    caveats         jsonb NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (metric_id, as_of, rules_version)
);

CREATE TABLE axis_states (
    id             bigserial PRIMARY KEY,
    report_date    date NOT NULL,
    axis           text NOT NULL,
    color          axis_color NOT NULL,
    label_es       text NOT NULL,
    inputs         jsonb NOT NULL,          -- estados de las métricas que lo determinan
    rules_version  int NOT NULL,
    UNIQUE (report_date, axis, rules_version)
);

-- ─────────────────────────── CALENDARIO ───────────────────────────
CREATE TABLE calendar_events (
    id               bigserial PRIMARY KEY,
    event_key        text NOT NULL UNIQUE,              -- 'us_cpi:2026-10-14', 'fomc_decision:2026-10-28'
    event_type       text NOT NULL,                     -- clave de rules.yaml → watch_today.event_weights
    title_es         text NOT NULL,
    country          text,                              -- US | EA | ES | AD | EU | GLOBAL
    scheduled_at     timestamptz NOT NULL,              -- UTC
    time_precision   text NOT NULL CHECK (time_precision IN ('exact','date_only')),
    tz_origin        text,                              -- 'America/New_York'
    weight_override  int,
    status           text NOT NULL DEFAULT 'scheduled'
                     CHECK (status IN ('tentative','scheduled','confirmed','postponed','cancelled','released')),
    source_id        text REFERENCES sources(id),
    source_url       text,
    notes            text,
    updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_calendar_time ON calendar_events(scheduled_at);

-- ─────────────────────────── NOTICIAS ───────────────────────────
CREATE TABLE news_sources (
    id                 text PRIMARY KEY,               -- 'boe_sumario', 'esma_news', 'rekt_news'
    source_id          text REFERENCES sources(id),
    name               text NOT NULL,
    tier               source_tier NOT NULL,
    jurisdictions      text[] NOT NULL,                -- {ES}, {AD}, {EU}, {US}, {INTL}, {AE}
    fronts             text[] NOT NULL,                -- {fiscal, regulatorio, proteccion, financiero}
    access_method      text NOT NULL,                  -- rss | api | html | csv_diff | ics | email
    url                text NOT NULL,
    poll_interval      interval NOT NULL,
    parser             text NOT NULL,                  -- nombre del parser en news/parsers
    etag               text,
    last_modified      text,
    last_success_at    timestamptz,
    last_error         text,
    active             boolean NOT NULL DEFAULT true
);

CREATE TABLE news_events (
    id                bigserial PRIMARY KEY,
    title_es          text,
    first_seen_at     timestamptz NOT NULL DEFAULT now(),
    last_seen_at      timestamptz NOT NULL DEFAULT now(),
    primary_item_id   bigint,                          -- FK añadida abajo (dependencia circular)
    fronts            text[] NOT NULL DEFAULT '{}',
    jurisdictions     text[] NOT NULL DEFAULT '{}',
    impact_score      numeric(5,2),
    score_breakdown   jsonb,
    corroboration     int NOT NULL DEFAULT 1,          -- nº de fuentes independientes
    best_tier         source_tier,
    status            text NOT NULL DEFAULT 'candidate'
                      CHECK (status IN ('candidate','alert_draft','alerted','weekly_candidate','included_weekly','archived','discarded')),
    week_iso          text,
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_news_events_week ON news_events(week_iso, impact_score DESC);

CREATE TABLE news_items (
    id               bigserial PRIMARY KEY,
    news_source_id   text NOT NULL REFERENCES news_sources(id),
    url              text NOT NULL,
    canonical_url    text NOT NULL,
    url_hash         text NOT NULL,                    -- sha256(canonical_url)
    title            text NOT NULL,
    summary          text,
    content_text     text,                             -- texto extraído (el que ve el LLM, recortado)
    language         text,
    doc_type         text,                             -- norma | proyecto | consulta | resolucion | nota_prensa | guia | noticia | incidente
    published_at     timestamptz,
    fetched_at       timestamptz NOT NULL DEFAULT now(),
    content_sha256   text NOT NULL,
    simhash          bigint,
    raw_payload_id   bigint REFERENCES raw_payloads(id),
    event_id         bigint REFERENCES news_events(id),
    duplicate_of     bigint REFERENCES news_items(id),
    status           text NOT NULL DEFAULT 'new' CHECK (status IN ('new','classified','duplicate','discarded','error')),
    UNIQUE (url_hash)
);
CREATE INDEX ix_news_items_pub ON news_items(published_at DESC);
CREATE INDEX ix_news_items_event ON news_items(event_id);
ALTER TABLE news_events ADD CONSTRAINT fk_news_events_primary FOREIGN KEY (primary_item_id) REFERENCES news_items(id);

CREATE TABLE news_classifications (
    id                 bigserial PRIMARY KEY,
    item_id            bigint NOT NULL REFERENCES news_items(id),
    llm_call_id        bigint,                         -- FK a llm_calls
    prompt_version     text NOT NULL,
    relevant           boolean NOT NULL,
    fronts             text[] NOT NULL,
    jurisdictions      text[] NOT NULL,
    affected_profiles  text[] NOT NULL,                -- holder_particular, empresa, residente_es, residente_ad, usuario_exchange, autocustodia, stablecoins…
    features           jsonb NOT NULL,                 -- {economic_impact, affected_population, legal_force, urgency, novelty, icp_fit} 0–5 + justificaciones
    summary_es         text,
    key_dates          jsonb,
    output             jsonb NOT NULL,                 -- salida completa validada contra esquema
    created_at         timestamptz NOT NULL DEFAULT now()
);

-- ─────────────────────────── LLM Y VALIDACIÓN ───────────────────────────
CREATE TABLE llm_calls (
    id                  bigserial PRIMARY KEY,
    purpose             text NOT NULL,                 -- daily | daily_verify | weekly | weekly_verify | alert | alert_verify | classify
    model               text NOT NULL,                 -- modelo solicitado
    served_model        text,                          -- modelo que respondió (fallback del servidor)
    prompt_version      text NOT NULL,
    request             jsonb NOT NULL,                -- sin secretos
    response            jsonb,
    stop_reason         text,
    input_tokens        int,
    output_tokens       int,
    cache_read_tokens   int,
    cache_write_tokens  int,
    cost_usd            numeric(10,4),
    latency_ms          int,
    batch_id            text,
    error               text,
    created_at          timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE news_classifications ADD CONSTRAINT fk_nc_llm FOREIGN KEY (llm_call_id) REFERENCES llm_calls(id);

CREATE TABLE validation_reports (
    id            bigserial PRIMARY KEY,
    target_type   text NOT NULL,                       -- daily | weekly | alert
    target_key    text NOT NULL,                       -- '2026-09-23', '2026-W39', alert id
    attempt       int NOT NULL,
    passed        boolean NOT NULL,
    blocking      int NOT NULL,                        -- nº de fallos bloqueantes
    warnings      int NOT NULL,
    checks        jsonb NOT NULL,                      -- [{check_id, severity, passed, details}]
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_validation_target ON validation_reports(target_type, target_key);

-- ─────────────────────────── PRODUCTOS ───────────────────────────
CREATE TABLE daily_reports (
    report_date           date PRIMARY KEY,           -- fecha Europe/Madrid de publicación
    status                text NOT NULL DEFAULT 'building'
                          CHECK (status IN ('building','draft','validated','fallback','published','withheld','corrected','retracted')),
    fact_sheet            jsonb,                       -- input exacto al LLM (doc 06)
    selected_metrics      text[],
    rules_version         int,
    prompt_version        text,
    model                 text,
    llm_output            jsonb,                       -- salida estructurada validada
    validation_report_id  bigint REFERENCES validation_reports(id),
    rendered_telegram     text,                        -- HTML de Telegram final
    rendered_plain        text,
    fallback_reason       text,
    telegram_message_id   bigint,
    published_at          timestamptz,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE weekly_reports (
    week_iso              text PRIMARY KEY,           -- '2026-W39'
    period_start          date NOT NULL,
    period_end            date NOT NULL,
    status                text NOT NULL DEFAULT 'building'
                          CHECK (status IN ('building','draft','in_review','approved','scheduled','sent','cancelled')),
    selected_event_ids    bigint[],
    data_summary          jsonb,                       -- resumen financiero semanal (derivado de daily_reports)
    source_documents      jsonb,                       -- documentos S01..Sn entregados al LLM
    prompt_version        text,
    model                 text,
    llm_output            jsonb,
    validation_report_id  bigint REFERENCES validation_reports(id),
    html                  text,
    plain_text            text,
    web_url               text,
    esp_campaign_id       text,
    approved_by           text,
    approved_at           timestamptz,
    scheduled_for         timestamptz,
    sent_at               timestamptz,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE alerts (
    id                    bigserial PRIMARY KEY,
    trigger_type          text NOT NULL CHECK (trigger_type IN ('news','market_rule')),
    rule_id               text,                        -- 'stablecoin_depeg', 'etf_flow_extreme', 'ath_new'…
    event_id              bigint REFERENCES news_events(id),
    impact_score          numeric(5,2),
    status                text NOT NULL DEFAULT 'draft'
                          CHECK (status IN ('draft','pending_approval','approved','published','rejected','expired','superseded')),
    dedup_key             text NOT NULL,               -- evita alertas repetidas del mismo hecho
    llm_output            jsonb,
    validation_report_id  bigint REFERENCES validation_reports(id),
    rendered_telegram     text,
    rendered_email_html   text,
    approved_by           text,
    approved_at           timestamptz,
    telegram_message_id   bigint,
    esp_campaign_id       text,
    published_at          timestamptz,
    expires_at            timestamptz,
    created_at            timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_alerts_dedup ON alerts(dedup_key) WHERE status NOT IN ('rejected','expired');

-- ─────────────────────────── DISTRIBUCIÓN, OPERACIÓN Y AUDITORÍA ───────────────────────────
CREATE TABLE publications (
    id             bigserial PRIMARY KEY,
    channel        text NOT NULL CHECK (channel IN ('telegram_public','telegram_admin','email','web')),
    target_type    text NOT NULL,                     -- daily | weekly | alert | correction
    target_key     text NOT NULL,
    external_id    text,                              -- message_id de Telegram, id de campaña del ESP, URL
    payload_sha256 text NOT NULL,
    status         text NOT NULL CHECK (status IN ('pending','sent','failed','edited','deleted')),
    idempotency_key text NOT NULL UNIQUE,             -- 'telegram_public:daily:2026-09-23'
    sent_at        timestamptz,
    edited_at      timestamptz,
    deleted_at     timestamptz,
    error          text
);

CREATE TABLE job_runs (
    id               bigserial PRIMARY KEY,
    job_name         text NOT NULL,                   -- ingest_daily, analyze, build_daily, publish_daily, ingest_news…
    scheduled_for    timestamptz,
    started_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz,
    status           job_status NOT NULL DEFAULT 'running',
    attempt          int NOT NULL DEFAULT 1,
    idempotency_key  text UNIQUE,
    stats            jsonb,
    error            text
);

CREATE TABLE editor_actions (
    id           bigserial PRIMARY KEY,
    actor        text NOT NULL,                       -- id/nombre del editor (Telegram user id)
    action       text NOT NULL CHECK (action IN ('approve','reject','edit','correct','retract','hold','resume','publish_now','override_metric','mute_source')),
    target_type  text NOT NULL,
    target_key   text NOT NULL,
    before       jsonb,
    after        jsonb,
    reason       text,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE settings (
    key         text PRIMARY KEY,                     -- 'alerts.autopublish_market_rules', 'daily.hold', 'weekly.send_time'
    value       jsonb NOT NULL,
    updated_by  text,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
