"""Integración con PostgreSQL 16 real: el Daily completo contra PostgresStore.

Se ejecuta solo si BP_TEST_DATABASE_URL apunta a una base DESECHABLE (el test borra y recrea el esquema public).
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

import pytest

from bp.config import load_config
from bp.demo import DemoBackend, seed_history
from bp.distribution.telegram import TelegramClient
from bp.ingest.registry import run_daily_ingest
from bp.models import Observation, RunContext
from bp.orchestrator.daily import build_daily, publish_daily

DSN = os.environ.get("BP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="BP_TEST_DATABASE_URL no definida")


@pytest.fixture()
def pg():
    import psycopg

    from bp.store.postgres import PostgresStore
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    store = PostgresStore(DSN)
    cfg = load_config()
    assert store.init_schema(cfg) is True
    assert store.init_schema(cfg) is False                 # idempotente
    store.sync_catalog(cfg)
    store.sync_catalog(cfg)
    yield store
    store.close()


def test_history_semantics(pg):
    t = lambda d, h=0: datetime(2026, 9, d, h, tzinfo=timezone.utc)  # noqa: E731
    pg.save_observations([
        Observation("btc_usd", t(20), 100.0, "USD", "coingecko_basic", t(20, 1)),
        Observation("btc_usd", t(21), 101.0, "USD", "coingecko_basic", t(21, 1)),
        Observation("btc_usd", t(21), 102.0, "USD", "coingecko_basic", t(21, 5), status="revised"),   # revisión posterior
        Observation("btc_usd", t(22), 999.0, "USD", "coingecko_basic", t(22, 1), status="rejected"),
        Observation("fng_class", t(21), "Neutral", "index", "alternative_me", t(21, 1)),
    ])
    assert [o.value for o in pg.history("btc_usd")] == [100.0, 102.0]
    assert [o.value for o in pg.history("btc_usd", until=t(21, 2))] == [100.0, 101.0]     # como se veía entonces
    assert pg.latest("fng_class").value == "Neutral"


def test_full_daily_on_postgres(pg):
    cfg = load_config()
    rd = date(2026, 9, 24)
    ctx = RunContext(report_date=rd, now=datetime(2026, 9, 24, 6, 50, tzinfo=timezone.utc), offline=True)
    seed_history(pg, rd)
    runs = run_daily_ingest(ctx, cfg, pg, fixtures_dir=cfg.root / "tests" / "fixtures")
    assert all(r.ok for r in runs), [(r.connector, r.error) for r in runs if not r.ok]
    res = build_daily(ctx, cfg, pg, DemoBackend())
    assert res.status == "validated"
    rep = pg.get_daily_report(rd)
    assert rep["status"] == "validated" and rep["fact_sheet"]["meta"]["report_date"] == "2026-09-24"
    assert rep["rendered_telegram"].startswith("☀️")
    n = pg._exec("SELECT count(*) AS n FROM llm_calls")[0]["n"]
    assert n == 2
    # reconstrucción el mismo día: sin errores de unicidad en señales ni ejes
    assert build_daily(ctx, cfg, pg, None).status == "fallback"

    import httpx

    sent = []

    def handler(req):
        sent.append(req)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    client = TelegramClient(token="T", transport=httpx.MockTransport(handler), sleep=lambda s: None)
    ctx_pub = RunContext(report_date=rd, now=datetime(2026, 9, 24, 7, 0, tzinfo=timezone.utc))
    assert publish_daily(ctx_pub, cfg, pg, client, "@canal").status == "sent"
    assert publish_daily(ctx_pub, cfg, pg, client, "@canal").status == "skipped_duplicate"
    assert len(sent) == 1
    assert pg.get_daily_report(rd)["status"] == "published"
    with pg.lock("daily"):
        other = type(pg)(DSN)
        from bp.store.base import LockBusy
        with pytest.raises(LockBusy), other.lock("daily"):
            pass
        other.close()
    pg.log_job("publish_daily", "publish_daily:2026-09-24", "sent", {"message_id": 42})
    pg.log_job("publish_daily", "publish_daily:2026-09-24", "sent", {"message_id": 42})
    assert pg._exec("SELECT attempt FROM job_runs")[0]["attempt"] == 2
