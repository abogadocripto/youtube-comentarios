"""Fixtures compartidas: ejecución completa del Daily en modo offline (historia sintética + fixtures)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from bp.config import load_config
from bp.demo import DemoBackend, seed_history
from bp.ingest.registry import run_daily_ingest
from bp.models import RunContext
from bp.orchestrator.daily import build_daily
from bp.store.memory import MemoryStore

REPORT_DATE = date(2026, 9, 24)
NOW = datetime(2026, 9, 24, 6, 50, tzinfo=timezone.utc)


def offline_store(report_date: date = REPORT_DATE, now: datetime = NOW) -> tuple[RunContext, MemoryStore, list]:
    cfg = load_config()
    ctx = RunContext(report_date=report_date, now=now, offline=True)
    store = MemoryStore()
    seed_history(store, report_date)
    runs = run_daily_ingest(ctx, cfg, store, fixtures_dir=cfg.root / "tests" / "fixtures")
    return ctx, store, runs


@pytest.fixture(scope="session")
def demo_run():
    cfg = load_config()
    ctx, store, runs = offline_store()
    fallback = build_daily(ctx, cfg, store, backend=None)
    ctx2, store2, _ = offline_store()
    backend = DemoBackend()
    llm = build_daily(ctx2, cfg, store2, backend=backend)
    return {"ctx": ctx, "store": store, "runs": runs, "fallback": fallback, "llm": llm, "llm_store": store2, "backend": backend}
