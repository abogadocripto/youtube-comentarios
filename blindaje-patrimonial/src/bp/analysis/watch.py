"""«Hoy vigilaría…»: selección determinista de una variable o evento (docs/04 §6). El LLM solo la redacta."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from bp.analysis.rules import AnalysisResult
from bp.config import Config
from bp.editorial.format import WEEKDAYS
from bp.models import MADRID, CalendarEvent, RunContext


@dataclass
class WatchCandidate:
    id: str
    kind: str                      # event | metric | regulatory_deadline | alert_followup
    title_es: str
    when_madrid: str | None
    weight: float
    fact_ids: list[str] = field(default_factory=list)
    source_name: str = ""
    source_url: str = ""
    day: date | None = None


def _when(e: CalendarEvent, today: date) -> str | None:
    local = e.scheduled_at.astimezone(MADRID)
    d = local.date()
    if d == today:
        day = "hoy"
    elif d == today + timedelta(days=1):
        day = "mañana"
    else:
        day = f"el {WEEKDAYS[d.weekday()]} {d.day}"
    if e.time_precision == "date_only":
        return day
    return f"{day}, {local.strftime('%H:%M')}"


def event_weight(cfg: Config, e: CalendarEvent) -> float:
    if e.weight_override is not None:
        return float(e.weight_override)
    return float(cfg.rules["watch_today"]["event_weights"].get(e.event_type, 0))


def candidates(ctx: RunContext, cfg: Config, res: AnalysisResult, events: list[CalendarEvent]) -> list[WatchCandidate]:
    wt = cfg.rules["watch_today"]
    today = ctx.report_date
    out: list[WatchCandidate] = []
    for e in events:
        if e.status in ("postponed", "cancelled"):
            continue                                   # nunca se anuncia un evento aplazado o cancelado
        d = e.scheduled_at.astimezone(MADRID).date()
        if not (today <= d <= today + timedelta(days=wt["lookahead_days"] + (2 if today.weekday() >= 5 else 0))):
            continue
        title = e.title_es + (" (previsto, pendiente de confirmación oficial)" if e.status == "tentative" else "")
        kind = "regulatory_deadline" if e.event_type == "regulatory_deadline" else "event"
        out.append(WatchCandidate(f"cal:{e.event_key}", kind, title, _when(e, today), event_weight(cfg, e),
                                  [], e.source_name, e.source_url, d))
    uw = wt["unscheduled_weights"]
    dd = res.signals.get("btc_drawdown_from_ath_pct")
    ddv = dd.stats.get("value") if dd else None
    if isinstance(ddv, (int, float)) and -cfg.rules["price"]["ath_proximity_watch_pct"] <= ddv < 0:
        out.append(WatchCandidate("metric:ath_proximity", "metric", "El nivel del máximo histórico", None,
                                  uw["ath_proximity"], ["btc_drawdown_from_ath_pct", "btc_ath_usd"], "CoinGecko", "", today))
    etf = res.signals.get("etf_net_flow_usd_1d")
    if etf and abs(etf.stats.get("streak") or 0) >= 4:
        word = "entradas" if etf.stats["streak"] > 0 else "salidas"
        out.append(WatchCandidate("metric:etf_streak", "metric", f"Si continúa la racha de {word} en los ETF", None,
                                  uw["etf_streak_4plus"], ["etf_net_flow_usd_1d", "etf_flow_streak_days"], "", "", today))
    fr = res.signals.get("funding_rate_agg_8h")
    if fr and fr.state_code == "funding_extreme_pos":
        out.append(WatchCandidate("metric:funding_extreme", "metric", "El funding de los perpetuos en zona extrema", None,
                                  uw["funding_extreme_settlement"], ["funding_rate_agg_8h"], "", "", today))
    return sorted(out, key=lambda c: (-c.weight, c.day or today))


def select(ctx: RunContext, cfg: Config, cands: list[WatchCandidate]) -> WatchCandidate | None:
    wt = cfg.rules["watch_today"]
    today = ctx.report_date
    todays = [c for c in cands if c.day == today and c.weight >= wt["min_today"]]
    if todays:
        return todays[0]
    ahead = [c for c in cands if c.day and c.day > today and c.weight >= wt["min_today"]]
    if ahead:
        return ahead[0]
    return cands[0] if cands else None
