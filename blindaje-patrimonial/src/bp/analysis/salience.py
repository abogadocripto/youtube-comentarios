"""Puntuación de relevancia (salience) de cada métrica (docs/04 §5.1)."""

from __future__ import annotations

from datetime import datetime

from bp.analysis.rules import EXTREME_STATES, AnalysisResult
from bp.config import Config
from bp.models import CalendarEvent, RunContext
from bp.store.base import Store

# Familias de métricas ligadas a cada tipo de evento (entrada `context` de la salience)
EVENT_CONTEXT = {
    "fomc_decision": {"rates", "liquidity", "fx"},
    "fomc_minutes": {"rates"},
    "fed_chair_speech": {"rates"},
    "us_cpi": {"rates", "fx"},
    "us_nfp": {"rates", "fx"},
    "us_pce": {"rates", "fx"},
    "us_gdp_advance": {"rates"},
    "ecb_decision": {"fx", "rates"},
    "deribit_quarterly_expiry": {"derivatives"},
    "deribit_monthly_expiry": {"derivatives"},
    "cme_btc_last_trade": {"derivatives"},
    "us_market_holiday": {"etf", "markets"},
}


def compute(ctx: RunContext, cfg: Config, store: Store, res: AnalysisResult,
            events_today: list[CalendarEvent], last_published_facts: dict[str, str]) -> None:
    """Rellena Signal.salience. `last_published_facts` = {metric_id: as_of ISO} del último Daily publicado."""
    sr = cfg.rules["salience"]
    w = sr["weights"]
    prev_axes = {a.axis: a for a in res.axes}
    ctx_families = set()
    for e in events_today:
        ctx_families |= EVENT_CONTEXT.get(e.event_type, set())
    for mid, s in res.signals.items():
        m = cfg.metrics.get(mid)
        if not m:
            continue
        z = s.stats.get("z")
        z_part = min(abs(z) / sr["z_cap"], 1.0) if isinstance(z, (int, float)) else 0.0
        prev = store.previous_signal(mid, s.as_of)
        threshold = 0.0
        if s.state_code and prev and prev.state_code and prev.state_code != s.state_code:
            threshold = 1.0
        elif s.state_code in EXTREME_STATES:
            threshold = 0.5
        st = s.stats.get("streak")
        streak_part = min(abs(st) / sr["streak_cap"], 1.0) if isinstance(st, (int, float)) else 0.0
        axis_state = prev_axes.get(m.axis)
        regime = 1.0 if axis_state and axis_state.changed_vs_prev and mid in axis_state.driver_fact_ids else 0.0
        context = 1.0 if m.family in ctx_families else 0.0
        last_asof = last_published_facts.get(mid)
        fresh = sr["freshness"]["stale"] if last_asof and last_asof == _iso(s.as_of) else sr["freshness"]["new"]
        raw = (w["z"] * z_part + w["threshold"] * threshold + w["streak"] * streak_part
               + w["regime"] * regime + w["context"] * context)
        s.salience = round(max(0.0, min(1.0, raw)) * fresh, 3)
        s.stats["salience_parts"] = {"z": z_part, "threshold": threshold, "streak": streak_part,
                                     "regime": regime, "context": context, "freshness": fresh}


def _iso(dt: datetime) -> str:
    return dt.isoformat()
