"""Métricas derivadas por fórmula (method='computed'). Ver `formula` y `derived_from` en config/metrics.yaml.

Regla general: `as_of` de un dato derivado = el `as_of` más antiguo de sus entradas (docs/03 §4).
Unidades internas:
- porcentajes en puntos porcentuales (−19,7 significa −19,7 %)
- funding_rate_agg_8h en PORCENTAJE por 8 h (0,012 = 0,012 %/8 h)
- importes en unidades (USD, BTC), no en millones
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from statistics import mean

from bp.analysis import stats
from bp.config import Config
from bp.editorial.format import month_year
from bp.models import MADRID, Observation, RunContext
from bp.store.base import Store

HALVING_HEIGHT = 840_000
HALVING_TIME = datetime(2024, 4, 20, 0, 9, 27, tzinfo=timezone.utc)
EPOCH_BLOCKS = 210_000
NOMINAL_BLOCK_S = 600

Deriver = Callable[[RunContext, Config, Store], list[Observation]]


def _obs(ctx: RunContext, metric_id: str, value, unit: str, as_of: datetime, **kw) -> Observation:
    return Observation(metric_id=metric_id, as_of=as_of, value=value, unit=unit, source_id="computed",
                       retrieved_at=ctx.now, method="computed", **kw)


def _madrid_date(dt: datetime) -> date:
    return dt.astimezone(MADRID).date()


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    s = str(value).replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _value_before(series: list[Observation], ref: datetime, delta: timedelta) -> Observation | None:
    """Última observación con as_of ≤ ref − delta."""
    target = ref - delta
    cands = [o for o in series if o.as_of <= target]
    return cands[-1] if cands else None


# ───────────────────────── precio y ciclo ─────────────────────────

def derive_ath(ctx: RunContext, cfg: Config, store: Store) -> list[Observation]:
    out: list[Observation] = []
    price = store.latest("btc_usd", until=ctx.now)
    ath = store.latest("btc_ath_usd", until=ctx.now)
    if not price or not ath or price.num is None or ath.num is None:
        return out
    # Regla del máximo acumulado: ath_t = max(ath_{t-1}, provider_ath_t); una bajada del proveedor se congela.
    prev_series = [o for o in store.history("btc_ath_usd", limit=30, until=ctx.now) if o.as_of < ath.as_of]
    ath_value = ath.num
    notes: dict = {}
    if prev_series and prev_series[-1].num is not None and prev_series[-1].num > ath_value:
        notes["ath_frozen"] = {"provider": ath_value, "kept": prev_series[-1].num}
        ath_value = prev_series[-1].num
    new_ath = price.num > ath_value
    if new_ath:
        notes["new_ath_candidate"] = True     # requiere confirmación con la fuente secundaria (alerta de mercado)
    dd = (price.num / ath_value - 1.0) * 100.0
    out.append(_obs(ctx, "btc_drawdown_from_ath_pct", round(dd, 4), "pct", min(price.as_of, ath.as_of),
                    quality="warn" if notes.get("ath_frozen") else "ok", quality_notes=notes))
    ath_date = store.latest("btc_ath_usd_date", until=ctx.now)
    if ath_date and ath_date.value:
        d = _madrid_date(_parse_dt(ath_date.value))
        days = (ctx.report_date - d).days
        out.append(_obs(ctx, "btc_days_since_ath", days, "days", ath_date.as_of))
    return out


def derive_realized_vol(ctx: RunContext, cfg: Config, store: Store) -> list[Observation]:
    series = store.history("btc_usd", limit=60, until=ctx.now)
    prices = [o.num for o in series if o.num]
    vol = stats.realized_vol_daily(prices, 30)
    if vol is None:
        return []
    return [_obs(ctx, "btc_realized_vol_30d", round(vol * math.sqrt(365) * 100, 4), "pct", series[-1].as_of,
                 quality_notes={"vol_daily": vol})]


def derive_halving(ctx: RunContext, cfg: Config, store: Store) -> list[Observation]:
    h = store.latest("block_height", until=ctx.now)
    if not h or h.num is None:
        return []
    height = int(h.num)
    next_height = (height // EPOCH_BLOCKS + 1) * EPOCH_BLOCKS
    blocks = next_height - height
    avg = store.latest("block_time_avg_s", until=ctx.now)
    avg_s = avg.num if avg and avg.num else NOMINAL_BLOCK_S
    eta = ctx.now + timedelta(seconds=blocks * avg_s)
    eta_nominal = ctx.now + timedelta(seconds=blocks * NOMINAL_BLOCK_S)
    days_since = (ctx.report_date - _madrid_date(HALVING_TIME)).days
    return [
        _obs(ctx, "halving_last_date", HALVING_TIME.date().isoformat(), "date", HALVING_TIME),
        _obs(ctx, "halving_days_since", days_since, "days", h.as_of),
        _obs(ctx, "halving_blocks_to_next", blocks, "blocks", h.as_of,
             quality_notes={"epoch_progress": (height - HALVING_HEIGHT) / EPOCH_BLOCKS}),
        _obs(ctx, "halving_next_est_date", eta.date().isoformat(), "date", h.as_of,
             quality_notes={"eta_nominal": eta_nominal.date().isoformat(), "avg_block_s": avg_s}),
    ]


# ───────────────────────── liquidez y tipos ─────────────────────────

def derive_net_liquidity(ctx: RunContext, cfg: Config, store: Store) -> list[Observation]:
    """NETLIQ = balance Fed (último miércoles) − TGA (DTS) − ON RRP; todo en USD (docs/02 §3.3)."""
    walcl = store.latest("fed_total_assets_usd", until=ctx.now)
    tga = store.latest("tga_usd", until=ctx.now)
    rrp = store.latest("on_rrp_usd", until=ctx.now)
    if not (walcl and tga and rrp) or None in (walcl.num, tga.num, rrp.num):
        return []
    value = walcl.num - tga.num - rrp.num
    as_of = min(walcl.as_of, tga.as_of, rrp.as_of)
    out = [_obs(ctx, "us_net_liquidity_usd", value, "USD", as_of,
                quality="ok" if 3e12 <= value <= 9e12 else "error",
                quality_notes={} if 3e12 <= value <= 9e12 else {"range": "fuera de [3, 9] bill. $: revisar unidades"})]
    hist = [o for o in store.history("us_net_liquidity_usd", limit=80, until=ctx.now) if o.as_of < as_of]
    prev = _value_before(hist + [out[0]], as_of, timedelta(days=28))
    if prev and prev.num:
        chg_usd = value - prev.num
        out.append(_obs(ctx, "us_net_liquidity_chg_4w_pct", round((value / prev.num - 1) * 100, 4), "pct", as_of,
                        quality_notes={"chg_4w_usd": chg_usd, "base_as_of": prev.as_of.isoformat()}))
    return out


def derive_global_m2(ctx: RunContext, cfg: Config, store: Store) -> list[Observation]:
    """Suma de componentes por país (dimensión 'country=XX', ya en USD) del último mes con datos.
    Si falta algún componente para ese mes se arrastra el último disponible y el dato queda provisional."""
    dims = store.dimensions("global_m2_usd")
    if not dims:
        return []
    latest_by_dim = {d: store.latest("global_m2_usd", dimension=d, until=ctx.now) for d in dims}
    latest_by_dim = {d: o for d, o in latest_by_dim.items() if o and o.num is not None}
    if not latest_by_dim:
        return []
    month = max(o.as_of for o in latest_by_dim.values())
    carried = sorted(d for d, o in latest_by_dim.items() if o.as_of < month)
    total = sum(o.num for o in latest_by_dim.values())
    agg = _obs(ctx, "global_m2_usd", total, "USD", month, as_of_label=f"M2 global a {month_year(month, approx=False)}",
               status="provisional" if carried else "final",
               quality_notes={"components": {d: o.as_of.date().isoformat() for d, o in latest_by_dim.items()},
                              "carried_forward": carried})
    out = [agg]
    hist = [o for o in store.history("global_m2_usd", limit=200, until=ctx.now) if o.as_of < month] + [agg]
    prev3 = _value_before(hist, month, timedelta(days=85))
    prev12 = _value_before(hist, month, timedelta(days=360))
    if prev3 and prev3.num:
        g3 = total / prev3.num - 1
        out.append(_obs(ctx, "global_m2_chg_3m_ann_pct", round(((1 + g3) ** 4 - 1) * 100, 4), "pct", month,
                        quality_notes={"chg_3m_pct": g3 * 100}))
    if prev12 and prev12.num:
        out.append(_obs(ctx, "global_m2_yoy_pct", round((total / prev12.num - 1) * 100, 4), "pct", month))
    return out


def derive_rates(ctx: RunContext, cfg: Config, store: Store) -> list[Observation]:
    out: list[Observation] = []
    n10 = store.latest("us10y_yield", until=ctx.now)
    r10 = store.latest("us10y_real_yield", until=ctx.now)
    if n10 and r10 and n10.num is not None and r10.num is not None and n10.as_of == r10.as_of:
        out.append(_obs(ctx, "us10y_breakeven", round(n10.num - r10.num, 4), "pp", n10.as_of))
    series10 = store.history("us10y_yield", limit=10, until=ctx.now)
    if len(series10) >= 6:
        out.append(_obs(ctx, "us10y_chg_5d_bp", round((series10[-1].num - series10[-6].num) * 100, 2), "bp", series10[-1].as_of))
    # Rango objetivo desde config/fomc.yaml
    cur = cfg.fomc.get("current", {})
    if cur:
        eff = datetime.fromisoformat(str(cur["effective"])).replace(tzinfo=timezone.utc)
        out.append(_obs(ctx, "fed_funds_upper", float(cur["upper"]), "pct", eff,
                        quality_notes={"lower": cur["lower"], "source_url": cur.get("source_url")}))
        meetings = [date.fromisoformat(str(d)) for d in cfg.fomc.get("meetings_2026", [])]
        upcoming = [d for d in meetings if d >= ctx.report_date]
        if upcoming:
            nxt = upcoming[0]
            out.append(_obs(ctx, "fed_next_meeting_date", nxt.isoformat(), "date", ctx.now))
    y2 = store.latest("us2y_yield", until=ctx.now)
    effr = store.latest("fed_funds_effective", until=ctx.now)
    if y2 and y2.num is not None:
        ref = effr.num if effr and effr.num is not None else None
        is_fomc_day = cur and str(cfg.fomc.get("current", {}).get("decided")) == ctx.report_date.isoformat()
        if is_fomc_day or ref is None:
            ref = (float(cur["lower"]) + float(cur["upper"])) / 2 if cur else None
        if ref is not None:
            as_of = min(y2.as_of, effr.as_of) if effr else y2.as_of
            out.append(_obs(ctx, "us2y_minus_ffr_bp", round((y2.num - ref) * 100, 2), "bp", as_of))
    usd_idx = store.history("usd_index", limit=10, until=ctx.now)
    if len(usd_idx) >= 6 and usd_idx[-6].num:
        out.append(_obs(ctx, "usd_index_chg_5d_pct", round((usd_idx[-1].num / usd_idx[-6].num - 1) * 100, 4), "pct", usd_idx[-1].as_of))
    return out


# ───────────────────────── ETF ─────────────────────────

def derive_etf(ctx: RunContext, cfg: Config, store: Store) -> list[Observation]:
    series = store.history("etf_net_flow_usd_1d", limit=130, until=ctx.now)
    flows = [o.num for o in series if o.num is not None]
    if not flows:
        return []
    last = series[-1]
    out = [_obs(ctx, "etf_flow_streak_days", stats.streak(flows), "count", last.as_of, as_of_label=last.as_of_label)]
    if len(flows) >= 5:
        out.append(_obs(ctx, "etf_net_flow_usd_5d", sum(flows[-5:]), "USD", last.as_of, as_of_label=last.as_of_label))
    if len(flows) >= 20:
        out.append(_obs(ctx, "etf_net_flow_usd_20d", sum(flows[-20:]), "USD", last.as_of, as_of_label=last.as_of_label))
    return out


# ───────────────────────── on-chain ─────────────────────────

def derive_onchain(ctx: RunContext, cfg: Config, store: Store) -> list[Observation]:
    out: list[Observation] = []
    sopr = store.history("sopr", limit=10, until=ctx.now)
    if len(sopr) >= 7:
        out.append(_obs(ctx, "sopr_7d_ma", round(mean(o.num for o in sopr[-7:]), 5), "index", sopr[-1].as_of))
    lth = store.history("lth_supply_btc", limit=40, until=ctx.now)
    if lth:
        prev = _value_before(lth, lth[-1].as_of, timedelta(days=30))
        if prev and prev.num is not None:
            out.append(_obs(ctx, "lth_supply_chg_30d_btc", lth[-1].num - prev.num, "BTC", lth[-1].as_of,
                            quality_notes={"chg_pct": (lth[-1].num / prev.num - 1) * 100 if prev.num else None}))
    # Saldos y flujos de exchanges: variaciones DENTRO de un mismo vintage (docs/02 §3.6)
    bal = store.latest("exch_balance_btc", until=ctx.now)
    if bal:
        vs = store.vintage_series("exch_balance_btc", bal.vintage_id)
        for days, mid in ((7, "exch_balance_chg_7d_btc"), (30, "exch_balance_chg_30d_btc")):
            prev = _value_before(vs, vs[-1].as_of, timedelta(days=days)) if vs else None
            if prev and prev.num is not None:
                out.append(_obs(ctx, mid, vs[-1].num - prev.num, "BTC", vs[-1].as_of, vintage_id=bal.vintage_id))
    nf = store.latest("exch_netflow_btc_1d", until=ctx.now)
    if nf:
        vs = store.vintage_series("exch_netflow_btc_1d", nf.vintage_id)
        if len(vs) >= 7:
            out.append(_obs(ctx, "exch_netflow_btc_7d", sum(o.num for o in vs[-7:]), "BTC", vs[-1].as_of, vintage_id=nf.vintage_id))
    return out


# ───────────────────────── derivados ─────────────────────────

def derive_derivatives(ctx: RunContext, cfg: Config, store: Store) -> list[Observation]:
    out: list[Observation] = []
    fr = store.latest("funding_rate_agg_8h", until=ctx.now)
    if fr and fr.num is not None:
        out.append(_obs(ctx, "funding_rate_agg_ann_pct", round(fr.num * 3 * 365, 4), "pct", fr.as_of))
    oi = store.history("oi_btc", limit=60, until=ctx.now)
    if oi:
        prev = _value_before(oi, oi[-1].as_of, timedelta(hours=23))
        if prev and prev.num:
            out.append(_obs(ctx, "oi_chg_24h_pct", round((oi[-1].num / prev.num - 1) * 100, 4), "pct", oi[-1].as_of))
    lo = store.latest("liq_long_usd_24h", until=ctx.now)
    sh = store.latest("liq_short_usd_24h", until=ctx.now)
    if lo and sh and lo.num is not None and sh.num is not None:
        total = lo.num + sh.num
        out.append(_obs(ctx, "liq_total_usd_24h", total, "USD", min(lo.as_of, sh.as_of),
                        quality_notes={"long_share": lo.num / total if total else None}))
    return out


# ───────────────────────── otros ─────────────────────────

def derive_misc(ctx: RunContext, cfg: Config, store: Store) -> list[Observation]:
    out: list[Observation] = []
    paxg = store.history("paxg_usd", limit=10, until=ctx.now)
    if paxg:
        prev = _value_before(paxg, paxg[-1].as_of, timedelta(days=5))
        if prev and prev.num:
            out.append(_obs(ctx, "gold_chg_5d_pct", round((paxg[-1].num / prev.num - 1) * 100, 4), "pct", paxg[-1].as_of))
    sc = store.history("stablecoin_mcap_usd", limit=12, until=ctx.now)
    if sc:
        prev = _value_before(sc, sc[-1].as_of, timedelta(days=7))
        if prev and prev.num:
            out.append(_obs(ctx, "stablecoin_mcap_chg_7d_pct", round((sc[-1].num / prev.num - 1) * 100, 4), "pct", sc[-1].as_of))
    return out


DERIVERS: list[Deriver] = [derive_ath, derive_realized_vol, derive_halving, derive_net_liquidity, derive_global_m2,
                           derive_rates, derive_etf, derive_onchain, derive_derivatives, derive_misc]


def derive_all(ctx: RunContext, cfg: Config, store: Store) -> list[Observation]:
    out: list[Observation] = []
    for fn in DERIVERS:
        produced = fn(ctx, cfg, store)
        store.save_observations(produced)       # los siguientes derivadores pueden usarlos
        out.extend(produced)
    return out
