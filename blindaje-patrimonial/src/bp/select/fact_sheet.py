"""Construcción del fact sheet del Daily (docs/04 §5.2, docs/06 §4.1).

Solo entran hechos publicables y admitidos como entrada del LLM (filtro de licencias I-LIC). La selección de lo
que el lector verá es determinista; el LLM recibe todos los hechos con estado pero solo puede citar los `selected`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from bp.analysis.rules import AnalysisResult
from bp.analysis.watch import WatchCandidate
from bp.calendar.events import is_us_session, nyse_holidays
from bp.config import Config
from bp.editorial.format import fmt_abs, fmt_value
from bp.licence import metric_llm_allowed, metric_publishable
from bp.models import MADRID, RunContext, Signal
from bp.store.base import Store

FAMILY_BLOCK = {
    "price": "bitcoin", "cycle": "bitcoin", "sentiment": "sentimiento", "liquidity": "liquidez", "etf": "demanda_etf",
    "onchain": "onchain", "rates": "macro", "fx": "macro", "markets": "macro", "derivatives": "derivados",
}
EXCHANGE_METRICS = {"exch_balance_btc", "exch_balance_chg_7d_btc", "exch_balance_chg_30d_btc", "exch_netflow_btc_1d", "exch_netflow_btc_7d"}
CORE_BLOCKS = ["bitcoin", "sentimiento", "liquidez", "demanda_etf"]
OPTIONAL_BLOCKS = ["onchain", "exchanges", "macro", "derivados"]


def block_of(cfg: Config, metric_id: str) -> str | None:
    if metric_id in EXCHANGE_METRICS:
        return "exchanges"
    m = cfg.metrics.get(metric_id)
    return FAMILY_BLOCK.get(m.family) if m else None


@dataclass
class FactSheetBuild:
    fact_sheet: dict[str, Any]
    excluded: dict[str, str] = field(default_factory=dict)      # metric_id → motivo (licencia, obsoleto…)
    blocks: dict[str, list[str]] = field(default_factory=dict)  # bloque → hechos seleccionados en orden


def _source_ref(cfg: Config, source_id: str, metric_id: str) -> dict[str, str]:
    m = cfg.metrics[metric_id]
    sid = source_id if source_id != "computed" else (m.primary_source or "computed")
    s = cfg.sources.get(sid, {})
    name = s.get("attribution_short") or s.get("name") or sid
    if source_id == "computed" and sid != "computed":
        name = f"cálculo propio sobre {name}" if s.get("licence") != "self_computed" else name
    url = s.get("attribution_url") or s.get("base_url") or cfg.editorial["brand"]["methodology_url"]
    return {"name": name, "url": url}


def _freshness(cfg: Config, ctx: RunContext, metric_id: str, as_of: datetime) -> str:
    m = cfg.metrics[metric_id]
    return "fresh" if ctx.now - as_of <= m.max_staleness else "stale"


def build(ctx: RunContext, cfg: Config, store: Store, res: AnalysisResult, watch_cands: list[WatchCandidate],
          watch_selected: WatchCandidate | None, prompt_version: str) -> FactSheetBuild:
    sal = cfg.rules["salience"]
    excluded: dict[str, str] = {}
    facts: dict[str, dict[str, Any]] = {}
    signals: dict[str, Signal] = res.signals

    for mid, s in signals.items():
        m = cfg.metrics.get(mid)
        if not m:
            continue
        obs = store.latest(mid, until=ctx.now)
        if obs is None:
            continue
        if not metric_publishable(cfg, mid, obs.source_id):
            excluded[mid] = "licencia: fuente sin derechos de difusión pública"
            continue
        if not metric_llm_allowed(cfg, mid, obs.source_id):
            excluded[mid] = "licencia: fuente no admitida como entrada del LLM"
            continue
        fresh = _freshness(cfg, ctx, mid, obs.as_of)
        value = obs.value
        try:
            display = fmt_value(value, m.fmt)
        except (TypeError, ValueError):
            display = str(value)
        if mid == "fng_class":
            display = m.raw.get("translate", {}).get(str(value), str(value))
        if mid == "liquidity_regime":
            display = s.state_label_es or str(value)
        facts[mid] = {
            "id": mid,
            "label_es": m.label_es,
            "value": value if isinstance(value, (int, float, str)) or value is None else str(value),
            "display": display,
            "display_abs": fmt_abs(value, m.fmt),
            "unit": m.unit,
            "as_of": obs.as_of.isoformat(),
            "as_of_label": obs.as_of_label,
            "source": _source_ref(cfg, obs.source_id, mid),
            "is_provisional": obs.status == "provisional",
            "freshness": fresh,
            "stats": {k: v for k, v in s.stats.items() if k in ("z", "pctl_4y", "pctl_365", "streak", "delta_7d", "sigma")},
            "state": {"axis": m.axis, "code": s.state_code or "n/a", "label_es": s.state_label_es or "", "color": s.color or "none"},
            "salience": s.salience,
            "selected": False,
            "interpretation_hints": [{"id": h["id"], "text": h["text"], "_refs": h.get("refs", [])} for h in s.hints],
            "caveats": list(s.caveats),
        }

    # ─── Selección ───
    selected: set[str] = set()
    for mid in sal["core_always"]:
        f = facts.get(mid)
        if f:
            if f["freshness"] == "stale":
                f["freshness"] = "stale_shown"          # núcleo: se muestra con su fecha, sin tratarlo como novedad
            selected.add(mid)
    # fecha del ATH y ATH (acompañan a la distancia)
    for mid in ("btc_ath_usd", "btc_ath_usd_date"):
        if mid in facts:
            selected.add(mid)
    cands = [f for mid, f in facts.items()
             if mid not in selected and cfg.metrics[mid].layer == "C" and f["freshness"] == "fresh"
             and f["salience"] >= sal["candidate_min"]]
    cands.sort(key=lambda f: -f["salience"])
    per_family: dict[str, list[float]] = {}
    core_blocks_present = {block_of(cfg, m) for m in selected}
    visible = len([b for b in core_blocks_present if b])
    optional_ok = {b for b in OPTIONAL_BLOCKS if any(
        f["salience"] >= sal["optional_block_min"] for mid, f in facts.items() if block_of(cfg, mid) == b and f["freshness"] == "fresh")}
    for f in cands:
        mid = f["id"]
        fam = cfg.metrics[mid].family
        blk = block_of(cfg, mid)
        if blk in OPTIONAL_BLOCKS and blk not in optional_ok:
            continue
        taken = per_family.setdefault(fam, [])
        if len(taken) >= 2 or (len(taken) == 1 and (taken[0] < sal["second_per_family_min"] or f["salience"] < sal["second_per_family_min"])):
            continue
        if visible >= sal["max_visible_indicators"]:
            break
        selected.add(mid)
        taken.append(f["salience"])
        visible += 1
    # pistas: sus hechos referenciados pasan a seleccionados; se eliminan las que citan hechos no publicables
    for mid in list(selected):
        f = facts[mid]
        keep = []
        for h in f["interpretation_hints"]:
            refs = h.pop("_refs", [])
            if all(r in facts for r in refs):
                keep.append(h)
                selected.update(refs)
        f["interpretation_hints"] = keep
    for mid, f in facts.items():
        for h in f["interpretation_hints"]:
            h.pop("_refs", None)
        f["selected"] = mid in selected

    # ─── Bloques ───
    blocks: dict[str, list[str]] = {}
    for mid in selected:
        b = block_of(cfg, mid)
        if b:
            blocks.setdefault(b, []).append(mid)

    # ─── Ejes ───
    axes = [{"axis": a.axis, "color": a.color, "label_es": a.label_es, "changed_vs_prev": a.changed_vs_prev,
             "driver_fact_ids": [d for d in a.driver_fact_ids if d in facts]} for a in res.axes
            if any(d in facts for d in a.driver_fact_ids)]

    # ─── Contexto ───
    hol = nyse_holidays(cfg)
    yday = ctx.report_date - timedelta(days=1)
    lim = cfg.editorial["limits"]
    prev = store.last_published_daily(ctx.report_date)
    wd = cfg.editorial["weekdays_es"][ctx.report_date.weekday()]
    watch = {
        "selected_id": watch_selected.id if watch_selected else "none",
        "candidates": [
            {"id": c.id, "kind": c.kind, "title_es": c.title_es, "when_madrid": c.when_madrid, "weight": c.weight,
             "fact_ids": [x for x in c.fact_ids if x in facts],
             "source": {"name": c.source_name or "calendario", "url": c.source_url or cfg.editorial["brand"]["methodology_url"]}}
            for c in watch_cands[:4]
        ],
    }
    if watch_selected and watch_selected.id not in {c["id"] for c in watch["candidates"]}:
        watch["candidates"].insert(0, {"id": watch_selected.id, "kind": watch_selected.kind, "title_es": watch_selected.title_es,
                                       "when_madrid": watch_selected.when_madrid, "weight": watch_selected.weight,
                                       "fact_ids": [x for x in watch_selected.fact_ids if x in facts],
                                       "source": {"name": watch_selected.source_name or "calendario",
                                                  "url": watch_selected.source_url or cfg.editorial["brand"]["methodology_url"]}})
    fact_sheet = {
        "meta": {
            "report_date": ctx.report_date.isoformat(),
            "weekday_es": wd,
            "timezone": "Europe/Madrid",
            "rules_version": cfg.rules["rules_version"],
            "prompt_version": prompt_version,
            "market_context": {
                "us_session_yesterday": is_us_session(yday, hol),
                "weekend": ctx.report_date.weekday() >= 5,
                "us_holiday_today": ctx.report_date in hol,
                "blocks_available": [b for b in ["bitcoin", "sentimiento", "liquidez", "demanda_etf", "exchanges", "onchain", "macro", "derivados"] if b in blocks],
            },
            "limits": {"lectura_max_sentences": lim["lectura_max_sentences"], "lectura_max_chars": lim["lectura_max_chars"],
                       "vigilar_max_chars": lim["vigilar_max_chars"], "block_comment_max_chars": lim["block_comment_max_chars"]},
        },
        "facts": sorted(facts.values(), key=lambda f: (not f["selected"], -f["salience"], f["id"])),
        "axes": axes,
        "watch": watch,
        "previous_daily": ({"report_date": str(prev["report_date"]), "lectura_rendered": prev.get("lectura_rendered", ""),
                            "vigilar_rendered": prev.get("vigilar_rendered", "")} if prev else None),
    }
    return FactSheetBuild(fact_sheet=fact_sheet, excluded=excluded, blocks=blocks)


def madrid_date(dt: datetime) -> date:
    return dt.astimezone(MADRID).date()
