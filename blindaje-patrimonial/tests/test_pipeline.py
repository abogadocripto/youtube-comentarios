"""Extremo a extremo en modo offline: ingesta (fixtures) → derivación → análisis → fact sheet → LLM/respaldo → validación."""

from __future__ import annotations

import json

from bp.config import load_config
from bp.llm.client import StaticBackend
from bp.orchestrator.daily import build_daily
from bp.schemas import validate_instance
from conftest import offline_store


def test_all_connectors_parse_their_fixtures(demo_run):
    failed = [(r.connector, r.error) for r in demo_run["runs"] if not r.ok]
    assert not failed
    ids = {o.metric_id for r in demo_run["runs"] for o in r.observations}
    for mid in ("btc_usd", "btc_eur", "fng_value", "us10y_yield", "us10y_real_yield", "fed_funds_effective", "on_rrp_usd",
                "tga_usd", "fed_total_assets_usd", "eurusd", "etf_net_flow_usd_1d", "block_height"):
        assert mid in ids, f"falta {mid}"


def test_observations_carry_provenance(demo_run):
    for r in demo_run["runs"]:
        for o in r.observations:
            assert o.source_id and o.retrieved_at and o.as_of.tzinfo is not None
            assert o.raw_payload_id is not None


def test_fallback_daily_is_valid_and_labelled(demo_run):
    res = demo_run["fallback"]
    cfg = load_config()
    assert res.status == "fallback" and res.origin == "template"
    assert validate_instance(res.fact_sheet, "daily_input.schema.json", cfg.root) == []
    first_line = res.rendered.html.split("\n", 1)[0]
    assert cfg.editorial["ai_labels"]["template"] in first_line
    assert "Lectura elaborada con IA" not in first_line
    assert res.rendered.visible_chars <= cfg.editorial["limits"]["telegram_max_chars"]


def test_llm_path_validated_with_verifier(demo_run):
    res, backend = demo_run["llm"], demo_run["backend"]
    cfg = load_config()
    assert res.status == "validated" and res.origin == "llm"
    assert backend.calls == ["daily", "daily_verify"]
    assert res.rendered.html.split("\n", 1)[0].count(cfg.editorial["ai_labels"]["llm"]) == 1
    assert len(demo_run["llm_store"].llm_calls) == 2


def test_selected_indicator_count_in_range(demo_run):
    fs = demo_run["fallback"].fact_sheet
    blocks = fs["meta"]["market_context"]["blocks_available"]
    assert "bitcoin" in blocks and len(blocks) >= 2


def test_no_digits_leak_from_template_reading(demo_run):
    out = demo_run["fallback"].output
    import re

    from bp.editorial.markers import MARKER
    for s in out.lectura:
        assert not re.search(r"\d", MARKER.sub("", s.text).replace("24 horas", ""))


def test_llm_bad_marker_retries_then_falls_back():
    """Un marcador inexistente no tumba el job: se reintenta con el motivo y, si persiste, respaldo por plantillas."""
    cfg = load_config()
    ctx, store, _ = offline_store()
    bad = {"lectura": [{"text": "Los ETF suman {{f:inventado}}.", "kind": "hecho", "fact_ids": ["btc_usd"], "hint_ids": []},
                       {"text": "Sin más.", "kind": "matiz", "fact_ids": ["btc_usd"], "hint_ids": []}],
           "vigilar": {"watch_id": "none", "text": "Nada.", "fact_ids": []}, "block_comments": [], "watch_override_reason": None}
    backend = StaticBackend([bad])
    res = build_daily(ctx, cfg, store, backend)
    assert res.status == "fallback" and res.origin == "template"
    assert len(backend.calls) == 2
    assert "inventado" in backend.calls[1]["user"]           # el reintento recibe el motivo


def test_llm_refusal_goes_straight_to_fallback():
    cfg = load_config()
    ctx, store, _ = offline_store()

    class Refuser:
        calls = 0

        def complete(self, **kw):
            Refuser.calls += 1
            return {"text": "", "model": "x", "stop_reason": "refusal", "usage": {"input_tokens": 0, "output_tokens": 0}}

    res = build_daily(ctx, cfg, store, Refuser())
    assert res.status == "fallback" and Refuser.calls == 1


def test_stale_core_price_withholds_publication():
    """Sin precio fresco no se publica (ni con respaldo)."""
    from datetime import datetime, timedelta, timezone
    cfg = load_config()
    ctx, store, _ = offline_store()
    ctx.now = datetime(2026, 9, 24, 6, 50, tzinfo=timezone.utc) + timedelta(days=2)
    res = build_daily(ctx, cfg, store, backend=None)
    assert res.status == "withheld" and "btc_usd" in (res.reason or "")


def test_fact_sheet_matches_what_llm_receives(demo_run):
    """El prompt del LLM contiene exactamente el fact sheet validado (sin campos internos)."""
    res = demo_run["llm"]
    fs_json = json.dumps(res.fact_sheet, ensure_ascii=False)
    assert "_refs" not in fs_json
    assert all("source" in f and "as_of" in f for f in res.fact_sheet["facts"])
