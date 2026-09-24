"""Reglas de interpretación (docs/04 §3–4): estado por métrica, pistas verificadas y color por eje.

Todo es determinista. Los textos de las pistas pueden contener marcadores {{f:<id>}} que el renderizador
sustituye; nunca cifras escritas a mano.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from bp.analysis import stats
from bp.config import Config
from bp.editorial.format import date_short
from bp.models import AxisState, Observation, RunContext, Signal
from bp.store.base import Store

EXTREME_STATES = {
    "move_large_up", "move_large_down", "ath_new", "drawdown_severe", "inflow_strong", "outflow_strong",
    "funding_extreme_pos", "funding_extreme_neg", "oi_surge", "oi_flush", "liq_spike", "Extreme Fear", "Extreme Greed",
    "expansion", "contraction",
}


@dataclass
class AnalysisResult:
    signals: dict[str, Signal] = field(default_factory=dict)
    axes: list[AxisState] = field(default_factory=list)
    extra_obs: list[Observation] = field(default_factory=list)


def _hint(metric_id: str, hid: str, text: str, refs: list[str] | None = None) -> dict:
    return {"id": f"{metric_id}:{hid}", "text": text, "refs": refs or []}


class Analyzer:
    def __init__(self, ctx: RunContext, cfg: Config, store: Store) -> None:
        self.ctx, self.cfg, self.store = ctx, cfg, store
        self.r = cfg.rules
        self.res = AnalysisResult()

    # ─── utilidades ───
    def latest(self, mid: str) -> Observation | None:
        return self.store.latest(mid, until=self.ctx.now)

    def hist(self, mid: str, n: int = 400) -> list[Observation]:
        return self.store.history(mid, limit=n, until=self.ctx.now)

    def vals(self, mid: str, n: int = 400) -> list[float]:
        return [o.num for o in self.hist(mid, n) if o.num is not None]

    def prev_state(self, mid: str, as_of: datetime) -> str | None:
        p = self.store.previous_signal(mid, as_of)
        return p.state_code if p else None

    def put(self, mid: str, obs: Observation, stats_: dict, code: str | None = None, label: str | None = None,
            color: str = "none", hints: list | None = None, caveats: list | None = None) -> Signal:
        m = self.cfg.metrics.get(mid)
        axis = m.axis if m else None
        stats_ = dict(stats_)
        stats_.setdefault("value", obs.num)
        caveat_list = list(caveats or [])
        if m and m.caveat and m.caveat.get("text_es") and not m.caveat.get("only_if") and not m.caveat.get("only_if_state"):
            caveat_list.append(m.caveat["text_es"])
        s = Signal(metric_id=mid, as_of=obs.as_of, stats=stats_, state_code=code, state_label_es=label, axis=axis,
                   color=color, hints=hints or [], caveats=caveat_list)
        self.res.signals[mid] = s
        return s

    def generic(self, mid: str) -> None:
        """Señal mínima (sin estado) para métricas sin regla específica: z del nivel para la salience."""
        o = self.latest(mid)
        if not o:
            return
        xs = self.vals(mid)
        z = stats.zscore(xs, self.r["stats"]["z_window_default"], self.r["stats"]["min_history"]["z"]) if o.num is not None else None
        self.put(mid, o, {"z": z})

    # ─── precio ───
    def price(self) -> None:
        pr = self.r["price"]
        p = self.latest("btc_usd")
        c24 = self.latest("btc_chg_24h_pct")
        if p:
            vol_obs = self.latest("btc_realized_vol_30d")
            vol_daily = (vol_obs.quality_notes or {}).get("vol_daily") if vol_obs else None
            sig = stats.sigma_move(c24.num if c24 else None, vol_daily)
            if sig is None:
                code, label = "move_calm", "movimiento contenido"
            elif abs(sig) >= pr["sigma_move"]["large"]:
                code, label = ("move_large_up", "movimiento amplio al alza") if sig > 0 else ("move_large_down", "movimiento amplio a la baja")
            elif abs(sig) >= pr["sigma_move"]["moderate"]:
                code, label = ("move_moderate_up", "subida moderada") if sig > 0 else ("move_moderate_down", "caída moderada")
            else:
                code, label = "move_calm", "movimiento contenido"
            hints = []
            prices = self.vals("btc_usd", 100)
            for n in pr["range_break_windows"]:
                ext = stats.n_day_extreme(prices, n)
                if ext:
                    hints.append(_hint("btc_usd", f"h.range_break_{n}", f"{'máximo' if ext == 'max' else 'mínimo'} de {n} días"))
                    break
            self.put("btc_usd", p, {"sigma": sig, "z": sig, "chg_24h": c24.num if c24 else None}, code, label, hints=hints)
            for mid in ("btc_eur", "btc_chg_24h_pct"):
                o = self.latest(mid)
                if o:
                    self.put(mid, o, {"z": sig}, code, label)
        c7 = self.latest("btc_chg_7d_pct")
        c7e = self.latest("btc_chg_7d_eur_pct")
        if c7:
            hints = []
            if c7e and c7.num is not None and c7e.num is not None and abs(c7e.num - c7.num) >= pr["eur_vs_usd_hint_pp"]:
                hints.append(_hint("btc_chg_7d_pct", "h.eur_vs_usd", "en euros, la semana es {{f:btc_chg_7d_eur_pct}}", ["btc_chg_7d_eur_pct"]))
            self.put("btc_chg_7d_pct", c7, {"z": None}, hints=hints)
        if c7e:
            self.put("btc_chg_7d_eur_pct", c7e, {"z": None})
        dd = self.latest("btc_drawdown_from_ath_pct")
        if dd and dd.num is not None:
            bands = pr["ath_bands"]
            raw = next(b for b in bands if dd.num >= b["min"])
            code, label = raw["code"], raw["label_es"]
            prev = self.prev_state("btc_drawdown_from_ath_pct", dd.as_of)
            if prev and prev != code:
                # histéresis: para volver a la banda anterior hay que superar su límite con margen
                prev_band = next((b for b in bands if b["code"] == prev), None)
                if prev_band and prev_band["min"] - pr["ath_band_hysteresis_pp"] <= dd.num < prev_band["min"]:
                    code, label = prev, prev_band["label_es"]
            if (dd.quality_notes or {}).get("new_ath_candidate") and (p is None or p.quality == "ok"):
                code, label = "ath_new", "nuevo máximo histórico"
            hints = [_hint("btc_drawdown_from_ath_pct", "h.ath_days", "{{f:btc_days_since_ath}} días desde el máximo", ["btc_days_since_ath"])]
            self.put("btc_drawdown_from_ath_pct", dd, {"z": None}, code, label, hints=hints)
        for mid in ("btc_days_since_ath", "btc_ath_usd", "btc_ath_usd_date", "btc_ath_eur", "btc_ath_eur_date"):
            o = self.latest(mid)
            if o:
                self.put(mid, o, {"z": None})

    # ─── ciclo ───
    def cycle(self) -> None:
        d = self.latest("halving_days_since")
        if d and d.num is not None:
            hints = []
            days = int(d.num)
            if days % 100 == 0:
                hints.append(_hint("halving_days_since", "h.halving_milestone", "hoy se cumplen {{f:halving_days_since}} días del último halving", ["halving_days_since"]))
            self.put("halving_days_since", d, {"z": None, "milestone": bool(hints)}, hints=hints)
        for mid in ("halving_blocks_to_next", "halving_next_est_date", "hashrate_7d", "block_height"):
            o = self.latest(mid)
            if o:
                self.put(mid, o, {"z": None})

    # ─── sentimiento ───
    def sentiment(self) -> None:
        sr = self.r["sentiment"]
        v = self.latest("fng_value")
        cls = self.latest("fng_class")
        if not v or v.num is None:
            return
        d7 = self.latest("fng_value_7d_ago")
        delta = v.num - d7.num if d7 and d7.num is not None else None
        trend = None
        if delta is not None:
            trend = next(x["label_es"] for x in sr["delta7_labels"] if delta >= x["min"])
        cname = str(cls.value) if cls else ""
        color = sr["colors"].get(cname, "amber")
        tr = self.cfg.metric("fng_class").raw.get("translate", {})
        label = tr.get(cname, cname) + (f" ({trend})" if trend and trend != "estable" else "")
        hints = []
        if d7 and d7.num is not None:
            hints.append(_hint("fng_value", "h.fng_path", "de {{f:fng_value_7d_ago}} a {{f:fng_value}} en siete días", ["fng_value_7d_ago", "fng_value"]))
        cls_hist = [str(o.value) for o in self.hist("fng_class", 400)]
        if len(cls_hist) >= 2 and cls_hist[-1] != cls_hist[-2]:
            prev_name = tr.get(cls_hist[-2], cls_hist[-2])
            hints.append(_hint("fng_value", "h.fng_regime_change", f"sale de la zona de {prev_name}"))
        if cname.startswith("Extreme") and len(cls_hist) >= 2:
            run = 0
            for c in reversed(cls_hist):
                if c == cname:
                    run += 1
                else:
                    break
            if run == 1:
                hs = self.hist("fng_class", 400)
                prev_same = [o for o in hs[:-1] if str(o.value) == cname]
                gap_ok = not prev_same or (hs[-1].as_of - prev_same[-1].as_of).days >= sr["first_since_min_days"]
                if gap_ok and prev_same:
                    hints.append(_hint("fng_value", "h.fng_first_since",
                                       f"primer día en {tr.get(cname, cname)} desde el {date_short(prev_same[-1].as_of)}"))
            elif run >= 3:
                hints.append(_hint("fng_value", "h.fng_extreme_days", f"{run} días seguidos en {tr.get(cname, cname)}"))
        xs = self.vals("fng_value")
        z = stats.zscore(xs, 365, self.r["stats"]["min_history"]["z"])
        self.put("fng_value", v, {"z": z, "delta_7d": delta}, cname or None, label, color, hints)
        for mid in ("fng_class", "fng_value_1d_ago", "fng_value_7d_ago"):
            o = self.latest(mid)
            if o:
                self.put(mid, o, {"z": None})

    # ─── liquidez ───
    def liquidity(self) -> None:
        lr = self.r["liquidity"]
        m2 = self.latest("global_m2_chg_3m_ann_pct")
        m2_state = None
        if m2 and m2.num is not None:
            hist = self.vals("global_m2_chg_3m_ann_pct", 200)
            g = lr["global_m2"]
            if g["method"] == "terciles" and len(hist) >= g["terciles_lookback_years"] * 12:
                win = hist[-g["terciles_lookback_years"] * 12:]
                lo, hi = stats.pctl_of(win, 1 / 3), stats.pctl_of(win, 2 / 3)
                raw = "expansion" if m2.num >= hi else "contraction" if m2.num <= lo else "neutral"
            else:
                raw = ("expansion" if m2.num > g["fixed"]["expansion_above_ann_pct"]
                       else "contraction" if m2.num < g["fixed"]["contraction_below_ann_pct"] else "neutral")
            prev = self.prev_state("global_m2_chg_3m_ann_pct", m2.as_of)
            m2_state = raw if prev is None or raw == prev else raw  # histéresis mensual: se aplica en la calibración (dato mensual)
            label = {"expansion": "expansión", "contraction": "contracción", "neutral": "neutral"}[m2_state]
            self.put("global_m2_chg_3m_ann_pct", m2, {"z": None}, m2_state, label)
            gm = self.latest("global_m2_usd")
            if gm:
                self.put("global_m2_usd", gm, {"z": None})
        nl = self.latest("us_net_liquidity_chg_4w_pct")
        us_state = None
        if nl:
            n4 = (nl.quality_notes or {}).get("chg_4w_usd")
            u = lr["us_net_liquidity"]
            if n4 is not None:
                raw = "expansion" if n4 > u["expansion_above_usd"] else "contraction" if n4 < u["contraction_below_usd"] else "neutral"
                prev = self.prev_state("us_net_liquidity_chg_4w_pct", nl.as_of)
                raw_hist = [s for s in [prev] if s]
                us_state = stats.hysteresis(prev, raw, raw_hist, u["confirmations"])
                label = {"expansion": "expansión", "contraction": "contracción", "neutral": "neutral"}[us_state]
                self.put("us_net_liquidity_chg_4w_pct", nl, {"z": None, "chg_4w_usd": n4}, us_state, label)
            usl = self.latest("us_net_liquidity_usd")
            if usl:
                self.put("us_net_liquidity_usd", usl, {"z": None})
        if m2_state is None and us_state is None:
            return
        m2s = m2_state or "neutral"
        uss = us_state or "neutral"
        regime = lr["regime_matrix"][m2s][uss]
        color = lr["colors"][regime]
        labels = {"expansion": "expansión", "contraction": "contracción", "neutral": "neutral", "mixed": "mixta",
                  "neutral_us_up": "neutral (impulso de corto plazo al alza en EE. UU.)",
                  "neutral_us_down": "neutral (impulso de corto plazo a la baja en EE. UU.)"}
        as_of = min(o.as_of for o in (m2, nl) if o is not None)
        m2_month = self.latest("global_m2_usd")
        obs = Observation(metric_id="liquidity_regime", as_of=as_of, value=regime, unit="index", source_id="computed",
                          retrieved_at=self.ctx.now, method="computed",
                          as_of_label=m2_month.as_of_label if m2_month else None,
                          status="provisional" if (m2_month and m2_month.status == "provisional") else "final")
        self.res.extra_obs.append(obs)
        self.store.save_observations([obs])
        self.put("liquidity_regime", obs, {"z": None, "m2_state": m2_state, "us_state": us_state}, regime, labels[regime], color,
                 caveats=["La relación histórica entre liquidez y activos de riesgo no es estable."])

    # ─── tipos y dólar ───
    def macro(self) -> None:
        mr = self.r["macro"]
        votes: list[int] = []
        ry = self.hist("us10y_real_yield", 30)
        if ry:
            d20 = (ry[-1].num - ry[-21].num) * 100 if len(ry) >= 21 else None
            if d20 is None:
                code, label, v = "real_flat", "estables", 0
            elif d20 >= mr["real_yield_20d_bp"]["up"]:
                code, label, v = "real_up", "condiciones financieras más restrictivas", -1
            elif d20 <= mr["real_yield_20d_bp"]["down"]:
                code, label, v = "real_down", "condiciones financieras más holgadas", 1
            else:
                code, label, v = "real_flat", "estables", 0
            votes.append(v)
            self.put("us10y_real_yield", ry[-1], {"z": None, "chg_20d_bp": d20}, code, label)
        y10 = self.latest("us10y_yield")
        c5 = self.latest("us10y_chg_5d_bp")
        if y10:
            hints = []
            if c5 and c5.num is not None and abs(c5.num) >= mr["yield_10y_5d_notable_bp"]:
                verb = "sube" if c5.num > 0 else "baja"
                hints.append(_hint("us10y_yield", "h.yield_move", f"la rentabilidad a 10 años {verb} {{{{fa:us10y_chg_5d_bp}}}} en cinco sesiones", ["us10y_chg_5d_bp"]))
            self.put("us10y_yield", y10, {"z": (c5.num / 15) if c5 and c5.num is not None else None}, hints=hints)
        if c5:
            self.put("us10y_chg_5d_bp", c5, {"z": None})
        sp = self.latest("us2y_minus_ffr_bp")
        if sp and sp.num is not None:
            t = mr["us2y_minus_ffr_bp"]
            if sp.num > t["hikes_above"]:
                code, label = "pricing_hikes", "el mercado descuenta subidas de tipos (proxy 2A−EFFR)"
            elif sp.num < t["cuts_below"]:
                code, label = "pricing_cuts", "el mercado descuenta bajadas de tipos (proxy 2A−EFFR)"
            else:
                code, label = "pricing_hold", "el mercado descuenta estabilidad de tipos (proxy 2A−EFFR)"
            self.put("us2y_minus_ffr_bp", sp, {"z": None}, code, label)
        usd = self.hist("usd_index", 30)
        if len(usd) >= 21 and usd[-21].num:
            d4 = (usd[-1].num / usd[-21].num - 1) * 100
            if d4 >= mr["usd_index_4w_pct"]["strong"]:
                code, label, v = "usd_strong", "dólar fuerte", -1
            elif d4 <= mr["usd_index_4w_pct"]["weak"]:
                code, label, v = "usd_weak", "dólar débil", 1
            else:
                code, label, v = "usd_flat", "dólar estable", 0
            votes.append(v)
            self.put("usd_index", usd[-1], {"z": None, "chg_4w_pct": d4}, code, label)
        eur = self.hist("eurusd", 10)
        if eur:
            hints = []
            if len(eur) >= 6 and eur[-6].num:
                d5 = (eur[-1].num / eur[-6].num - 1) * 100
                if abs(d5) >= mr["eurusd_5d_hint_pct"]:
                    hints.append(_hint("eurusd", "h.eurusd_move", "el euro " + ("se aprecia" if d5 > 0 else "se deprecia") + " frente al dólar en cinco sesiones"))
            self.put("eurusd", eur[-1], {"z": None}, hints=hints)
        ndx = self.latest("ndx_chg_1d_pct")
        if ndx and ndx.num is not None:
            v = 1 if ndx.num >= mr["ndx"]["strong_1d_pct"] else -1 if ndx.num <= -mr["ndx"]["strong_1d_pct"] else 0
            votes.append(v)
        for mid in ("fed_funds_upper", "fed_funds_effective", "us2y_yield", "us10y_breakeven", "fed_next_meeting_date"):
            o = self.latest(mid)
            if o:
                self.put(mid, o, {"z": None})
        if votes:
            total = sum(votes)
            color = "green" if total >= 2 else "red" if total <= -2 else "amber"
            self.axis("macro", color, [m for m in ("us10y_real_yield", "usd_index", "ndx_chg_1d_pct") if m in self.res.signals])

    # ─── demanda ───
    def demand(self) -> None:
        er = self.r["etf"]
        etf_vote = None
        f1 = self.latest("etf_net_flow_usd_1d")
        if f1 and f1.num is not None:
            flows = self.vals("etf_net_flow_usd_1d", er["lookback_sessions"] + 1)
            absf = [abs(x) for x in flows[:-1]] or [abs(f1.num)]
            flat_thr = max(stats.pctl_of(absf, er["flat_abs_pctl"]) or 0, er["flat_abs_min_usd"])
            strong_thr = stats.pctl_of(absf, er["strong_abs_pctl"]) or float("inf")
            x = f1.num
            if abs(x) < flat_thr:
                code, label, color = "flat", "flujos reducidos", "amber"
            elif x > 0:
                code, label, color = ("inflow_strong", "entradas muy fuertes", "green") if abs(x) >= strong_thr else ("inflow", "entradas", "green")
            else:
                code, label, color = ("outflow_strong", "salidas muy fuertes", "red") if abs(x) >= strong_thr else ("outflow", "salidas", "red")
            hints = []
            st = stats.streak(flows)
            if abs(st) >= er["streak_hint_min"]:
                word = "entradas" if st > 0 else "salidas"
                hints.append(_hint("etf_net_flow_usd_1d", "h.etf_streak",
                                   f"{{{{fa:etf_flow_streak_days}}}} sesiones seguidas de {word} en los ETF", ["etf_flow_streak_days"]))
            back = stats.biggest_since(flows, er["biggest_since_min_sessions"])
            if back:
                series = self.hist("etf_net_flow_usd_1d", er["lookback_sessions"] + 1)
                ref = series[-1 - back] if back < len(series) else series[0]
                word = "entrada" if x > 0 else "salida"
                hints.append(_hint("etf_net_flow_usd_1d", "h.etf_biggest_since", f"mayor {word} desde el {date_short(ref.as_of)}"))
            if f1.status == "provisional" or (f1.quality_notes or {}).get("provisional"):
                hints.append(_hint("etf_net_flow_usd_1d", "h.etf_provisional", "dato provisional, sujeto a revisión"))
            robust = stats.robust_z(flows, er["lookback_sessions"], min_hist=20)
            self.put("etf_net_flow_usd_1d", f1, {"z": robust, "streak": st}, code, label, color, hints)
            f5 = self.latest("etf_net_flow_usd_5d")
            if f5 and f5.num is not None:
                etf_vote = 1 if f5.num > 0 else -1 if f5.num < 0 else 0
                self.put("etf_net_flow_usd_5d", f5, {"z": None})
            for mid in ("etf_flow_streak_days", "etf_net_flow_usd_20d", "etf_total_btc_held"):
                o = self.latest(mid)
                if o:
                    self.put(mid, o, {"z": None, "streak": st if mid == "etf_flow_streak_days" else None})
        exch_vote = None
        nf7 = self.latest("exch_netflow_btc_7d")
        if nf7 and nf7.num is not None:
            xs = self.vals("exch_netflow_btc_7d", 366)
            z = stats.robust_z(xs, 365, min_hist=30)
            t = self.r["exchanges"]["netflow_7d_z"]
            if z is not None and z <= t["outflow_below"]:
                code, label, exch_vote = "outflow", "salidas netas de exchanges", 1
            elif z is not None and z >= t["inflow_above"]:
                code, label, exch_vote = "inflow", "entradas netas en exchanges", -1
            else:
                code, label, exch_vote = "neutral", "flujos equilibrados", 0
            self.put("exch_netflow_btc_7d", nf7, {"z": z}, code, label)
            for mid in ("exch_balance_btc", "exch_balance_chg_7d_btc", "exch_balance_chg_30d_btc", "exch_netflow_btc_1d"):
                o = self.latest(mid)
                if o:
                    self.put(mid, o, {"z": None})
        if etf_vote is None and exch_vote is None:
            return
        e, x = etf_vote or 0, exch_vote or 0
        if (e > 0 and x >= 0) or (etf_vote is None and x > 0):
            color = "green"
        elif (e < 0 and x <= 0) or (etf_vote is None and x < 0):
            color = "red"
        else:
            color = "amber"
        drivers = [m for m in ("etf_net_flow_usd_1d", "exch_netflow_btc_7d") if m in self.res.signals]
        self.axis("demanda", color, drivers)

    # ─── on-chain ───
    def onchain(self) -> None:
        oc = self.r["onchain"]
        for mid in ("mvrv", "mvrv_z"):
            o = self.latest(mid)
            if not o or o.num is None:
                continue
            xs = self.vals(mid, 20000)
            win = xs[-oc["mvrv_publish_window_years"] * 365:]
            p = stats.pctl(win, len(win), min_hist=90)
            label = None
            if p is not None:
                label = next(x["label_es"] for x in oc["mvrv_pctl_labels"] if p <= x["max"])
            hints = []
            if mid == "mvrv" and o.num < 1:
                hints.append(_hint("mvrv", "h.mvrv_below_1", "precio por debajo del coste medio on-chain (históricamente infrecuente)"))
            self.put(mid, o, {"z": stats.zscore(xs, 365, 60), "pctl_4y": p}, f"pctl_{label}" if label else None,
                     f"valoración {label}" if label else None, hints=hints)
        sip = self.latest("supply_in_profit_pct")
        if sip and sip.num is not None:
            hints = []
            if sip.num >= oc["supply_in_profit"]["high_pct"]:
                hints.append(_hint("supply_in_profit_pct", "h.sip_high", "casi todo el suministro está en beneficio, algo habitual en zonas de máximos"))
            elif sip.num <= oc["supply_in_profit"]["low_pct"]:
                hints.append(_hint("supply_in_profit_pct", "h.sip_low", "la mitad o más del suministro está en pérdidas"))
            self.put("supply_in_profit_pct", sip, {"z": stats.zscore(self.vals("supply_in_profit_pct"), 365, 60)}, hints=hints)
        sm = self.hist("sopr_7d_ma", 3)
        if sm:
            cur = sm[-1].num
            code, label = ("profit_taking", "realización neta de beneficios") if cur > 1 else ("loss_realization", "venta neta con pérdidas")
            hints = []
            if len(sm) >= 2 and stats.crossed(sm[-2].num, cur, 1.0):
                hints.append(_hint("sopr_7d_ma", "h.sopr_cross", "el SOPR (7 días) vuelve a situarse " + ("por encima" if cur > 1 else "por debajo") + " de 1"))
            self.put("sopr_7d_ma", sm[-1], {"z": None}, code, label, hints=hints)
        lc = self.latest("lth_supply_chg_30d_btc")
        if lc and lc.num is not None:
            chg_pct = (lc.quality_notes or {}).get("chg_pct")
            t = oc["lth_change_30d_pct"]
            caveats = []
            code, label = None, None
            if chg_pct is not None and chg_pct < t["distribution_below"]:
                code, label = "lth_distribution", "reducción de la oferta de largo plazo"
                caveats.append("Puede reflejar movimientos de custodios o exchanges, no necesariamente ventas.")
            elif chg_pct is not None and chg_pct > t["accumulation_above"]:
                code, label = "lth_accumulation", "maduración o acumulación de largo plazo"
            caveats.append(oc["lth_definition_label_es"])
            self.put("lth_supply_chg_30d_btc", lc, {"z": None, "chg_pct": chg_pct}, code, label, caveats=caveats)
        for mid in ("realized_price_usd", "lth_supply_btc", "sopr", "sth_sopr"):
            o = self.latest(mid)
            if o:
                self.put(mid, o, {"z": None})

    # ─── derivados ───
    def derivatives(self) -> None:
        dr = self.r["derivatives"]
        anchors = {k: v * 100 for k, v in dr["funding_8h_anchors"].items()}   # fracción → porcentaje
        red = green = False
        fr = self.latest("funding_rate_agg_8h")
        p = None
        if fr and fr.num is not None:
            xs = self.vals("funding_rate_agg_8h", 366)
            p = stats.pctl(xs, 365, min_hist=90)
            x = fr.num
            if p is not None and p >= dr["funding_pctl"]["extreme_high"]:
                code, label = "funding_extreme_pos", "funding en zona extrema positiva"
            elif p is not None and p <= dr["funding_pctl"]["extreme_low"]:
                code, label = "funding_extreme_neg", "funding en zona extrema negativa"
            elif x <= 0:
                code, label = "funding_neg", "posicionamiento corto dominante"
            elif x < anchors["neutral_max"]:
                code, label = "funding_neutral", "funding neutral"
            elif x < anchors["long_mild_max"]:
                code, label = "funding_long_mild", "sesgo largo moderado"
            else:
                code, label = "funding_long_high", "apalancamiento largo elevado"
            red |= (p is not None and p >= dr["funding_pctl"]["red_above"]) or x >= anchors["long_high"]
            green = 0 <= x and (p is None or p <= dr["funding_pctl"]["green_max"])
            self.put("funding_rate_agg_8h", fr, {"z": stats.zscore(xs, 365, 60), "pctl_365": p}, code, label)
        oi = self.latest("oi_chg_24h_pct")
        sigma = (self.res.signals.get("btc_usd").stats.get("sigma") if "btc_usd" in self.res.signals else None)
        if oi and oi.num is not None:
            t = dr["oi_24h_btc_pct"]
            x = oi.num
            if x >= t["surge"]:
                code, label = "oi_surge", "fuerte aumento del apalancamiento"
            elif x >= t["up"]:
                code, label = "oi_up", "aumento del apalancamiento"
            elif x <= t["flush"]:
                code, label = "oi_flush", "limpieza intensa de posiciones"
            elif x <= t["down"]:
                code, label = "oi_down", "desapalancamiento"
            else:
                code, label = "oi_flat", "apalancamiento estable"
            hints = []
            if code in ("oi_up", "oi_surge") and (sigma is None or abs(sigma) < 1):
                hints.append(_hint("oi_chg_24h_pct", "h.lev_without_price", "el apalancamiento crece sin movimiento de precio"))
            red |= x >= t["surge"]
            green = green and abs(x) < t["up"]
            self.put("oi_chg_24h_pct", oi, {"z": x / 5.0}, code, label, hints=hints)
        lq = self.latest("liq_total_usd_24h")
        if lq and lq.num is not None:
            xs = self.vals("liq_total_usd_24h", 366)
            pq = stats.pctl(xs, 365, min_hist=90)
            code, label, hints = None, None, []
            if pq is not None and pq >= dr["liquidations"]["spike_pctl"]:
                code, label = "liq_spike", "episodio de liquidaciones elevado"
                red = True
            share = (lq.quality_notes or {}).get("long_share")
            if share is not None and pq is not None and pq >= dr["liquidations"]["side_min_total_pctl"]:
                if share >= dr["liquidations"]["side_share"]:
                    hints.append(_hint("liq_total_usd_24h", "h.liq_side", "liquidaciones concentradas en posiciones largas"))
                elif 1 - share >= dr["liquidations"]["side_share"]:
                    hints.append(_hint("liq_total_usd_24h", "h.liq_side", "liquidaciones concentradas en posiciones cortas"))
            if oi and oi.num is not None and oi.num <= dr["oi_24h_btc_pct"]["flush"] and pq is not None and pq >= dr["liquidations"]["flush_min_pctl"]:
                hints.append(_hint("liq_total_usd_24h", "h.flush", "limpieza de posiciones apalancadas"))
            self.put("liq_total_usd_24h", lq, {"z": stats.zscore(xs, 365, 60), "pctl_365": pq}, code, label, hints=hints)
        for mid in ("funding_rate_agg_ann_pct", "oi_btc", "oi_usd", "liq_long_usd_24h", "liq_short_usd_24h", "dvol"):
            o = self.latest(mid)
            if o:
                self.put(mid, o, {"z": None})
        if fr or oi or lq:
            color = "red" if red else "green" if green else "amber"
            self.axis("apalancamiento", color, [m for m in ("funding_rate_agg_8h", "oi_chg_24h_pct", "liq_total_usd_24h") if m in self.res.signals])

    # ─── otros (stablecoins, oro, calendario) ───
    def misc(self) -> None:
        for mid in ("usdt_peg", "usdc_peg", "stablecoin_mcap_usd", "stablecoin_mcap_chg_7d_pct", "paxg_usd", "gold_chg_5d_pct"):
            o = self.latest(mid)
            if o:
                self.generic(mid)

    # ─── ejes ───
    def axis(self, name: str, color: str, drivers: list[str]) -> None:
        labels = self.r["axes"]["labels_es"][name]
        self.res.axes = [a for a in self.res.axes if a.axis != name]
        self.res.axes.append(AxisState(axis=name, color=color, label_es=labels[color], driver_fact_ids=drivers))

    def run(self) -> AnalysisResult:
        self.price()
        self.cycle()
        self.sentiment()
        self.liquidity()
        self.macro()
        self.demand()
        self.onchain()
        self.derivatives()
        self.misc()
        if "liquidity_regime" in self.res.signals:
            s = self.res.signals["liquidity_regime"]
            self.axis("liquidez", s.color if s.color != "none" else "amber", ["liquidity_regime"])
        if "fng_value" in self.res.signals:
            s = self.res.signals["fng_value"]
            self.axis("sentimiento", s.color, ["fng_value"])
        prev_axes = self.store.previous_axis_states(self.ctx.report_date)
        for a in self.res.axes:
            a.changed_vs_prev = prev_axes.get(a.axis) not in (None, a.color)
        order = self.r["axes"]["shown"]
        self.res.axes.sort(key=lambda a: order.index(a.axis) if a.axis in order else 99)
        if any(a.changed_vs_prev for a in self.res.axes):
            for a in self.res.axes:
                if a.changed_vs_prev:
                    for mid in a.driver_fact_ids:
                        sig = self.res.signals.get(mid)
                        if sig:
                            sig.hints.append(_hint(mid, "h.axis_change", f"el eje {a.axis} pasa a {a.label_es}"))
        return self.res


def analyze(ctx: RunContext, cfg: Config, store: Store) -> AnalysisResult:
    res = Analyzer(ctx, cfg, store).run()
    store.save_signals(list(res.signals.values()), cfg.rules["rules_version"])
    store.save_axis_states(ctx.report_date, res.axes, cfg.rules["rules_version"])
    return res
