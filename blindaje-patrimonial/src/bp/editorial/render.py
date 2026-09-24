"""Renderizado del Daily para Telegram (docs/09 §2). Única capa que convierte valores en texto."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from bp.config import Config
from bp.editorial.format import date_weekday
from bp.editorial.markers import fill, index_fact_sheet
from bp.llm.models import DailyOutput
from bp.models import RunContext

TEMPLATES = Path(__file__).parent / "templates"
EMOJI = {"green": "🟢", "amber": "🟡", "red": "🔴"}


@dataclass
class RenderedDaily:
    html: str
    plain: str
    lectura_rendered: str
    vigilar_rendered: str
    visible_chars: int
    ai_label: str
    attributions: list[str]


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES)), undefined=StrictUndefined, autoescape=False,
                       trim_blocks=False, keep_trailing_newline=False)


def strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s))


class DailyRenderer:
    def __init__(self, cfg: Config, fact_sheet: dict[str, Any], blocks: dict[str, list[str]]) -> None:
        self.cfg = cfg
        self.fs = fact_sheet
        self.facts, self.hints = index_fact_sheet(fact_sheet)
        self.blocks = blocks
        self.selected = {f["id"] for f in fact_sheet["facts"] if f["selected"]}

    def d(self, mid: str) -> str | None:
        f = self.facts.get(mid)
        return html.escape(f["display"], quote=False) if f and f["id"] in self.selected else None

    def _hint_present(self, mid: str, hid: str) -> bool:
        f = self.facts.get(mid)
        return bool(f) and any(h["id"] == f"{mid}:{hid}" for h in f.get("interpretation_hints", []))

    # ─── líneas deterministas por bloque ───
    def bitcoin_lines(self) -> list[str]:
        lines = []
        top = " · ".join(x for x in (self.d("btc_usd"), self.d("btc_eur")) if x)
        if top:
            lines.append(top)
        chg = []
        if self.d("btc_chg_24h_pct"):
            chg.append(f"24 h: {self.d('btc_chg_24h_pct')}")
        if self.d("btc_chg_7d_pct"):
            s = f"7 d: {self.d('btc_chg_7d_pct')}"
            if self._hint_present("btc_chg_7d_pct", "h.eur_vs_usd") and self.d("btc_chg_7d_eur_pct"):
                s += f" (en euros: {self.d('btc_chg_7d_eur_pct')})"
            chg.append(s)
        if self.d("btc_chg_30d_pct"):
            chg.append(f"30 d: {self.d('btc_chg_30d_pct')}")
        if chg:
            lines.append(" · ".join(chg))
        if self.d("btc_ath_usd") and self.d("btc_drawdown_from_ath_pct"):
            s = f"Máximo histórico: {self.d('btc_ath_usd')}"
            if self.d("btc_ath_usd_date"):
                s += f" ({self.d('btc_ath_usd_date')})"
            s += f" · {self.d('btc_drawdown_from_ath_pct')}"
            if self.d("btc_days_since_ath"):
                s += f" · {self.d('btc_days_since_ath')} días"
            lines.append(s)
        if self.d("halving_days_since"):
            s = f"Halving: {self.d('halving_days_since')} días desde el último"
            if self.d("halving_next_est_date"):
                s += f" · próximo {self.d('halving_next_est_date')}"
            lines.append(s)
        return lines

    def block_lines(self, block: str) -> tuple[list[str], str | None]:
        d = self.d
        lines: list[str] = []
        label = None
        if block == "sentimiento" and d("fng_value"):
            cls = self.facts.get("fng_class", {}).get("display", "")
            s = f"Miedo y Codicia: {d('fng_value')} — {html.escape(cls, quote=False)}"
            extra = [f"ayer {d('fng_value_1d_ago')}" if d("fng_value_1d_ago") else None,
                     f"hace 7 días {d('fng_value_7d_ago')}" if d("fng_value_7d_ago") else None]
            s += "".join(f" · {x}" for x in extra if x)
            s += " <i>(fuente: alternative.me)</i>"
            lines.append(s)
        elif block == "liquidez" and d("liquidity_regime"):
            f = self.facts["liquidity_regime"]
            emoji = EMOJI.get(f["state"]["color"], "")
            s = f"Liquidez global: {emoji} {d('liquidity_regime')}"
            asof = [f.get("as_of_label")] if f.get("as_of_label") else []
            if f.get("is_provisional"):
                asof.append("provisional")
            if asof:
                s += f" ({html.escape(', '.join(asof), quote=False)})"
            if d("us_net_liquidity_chg_4w_pct"):
                s += f" · liquidez EE. UU. 4 sem.: {d('us_net_liquidity_chg_4w_pct')}"
            lines.append(s)
            if d("global_m2_chg_3m_ann_pct"):
                lines.append(f"M2 global: {d('global_m2_chg_3m_ann_pct')} (3 meses, anualizado)")
        elif block == "demanda_etf" and d("etf_net_flow_usd_1d"):
            f = self.facts["etf_net_flow_usd_1d"]
            label = f.get("as_of_label")
            s = f"Flujo neto: {d('etf_net_flow_usd_1d')}"
            if d("etf_net_flow_usd_5d"):
                s += f" · 5 sesiones: {d('etf_net_flow_usd_5d')}"
            streak = self.facts.get("etf_flow_streak_days")
            if streak and streak["id"] in self.selected and isinstance(streak.get("value"), (int, float)) and abs(streak["value"]) >= 3:
                s += f" · {abs(int(streak['value']))}.ª sesión seguida de {'entradas' if streak['value'] > 0 else 'salidas'}"
            if f.get("is_provisional"):
                s += " (provisional)"
            lines.append(s)
        elif block == "onchain":
            parts = []
            if d("mvrv"):
                st = self.facts["mvrv"]["state"]["label_es"]
                parts.append(f"MVRV: {d('mvrv')}" + (f" ({html.escape(st, quote=False)})" if st else ""))
            if d("sopr_7d_ma"):
                parts.append(f"SOPR 7 d: {d('sopr_7d_ma')}")
            if d("supply_in_profit_pct"):
                parts.append(f"en beneficio: {d('supply_in_profit_pct')}")
            if d("lth_supply_chg_30d_btc"):
                parts.append(f"oferta LTH 30 d: {d('lth_supply_chg_30d_btc')}")
            if d("realized_price_usd"):
                parts.append(f"precio realizado: {d('realized_price_usd')}")
            if parts:
                lines.append(" · ".join(parts))
        elif block == "exchanges":
            parts = []
            if d("exch_balance_chg_7d_btc"):
                parts.append(f"BTC en exchanges 7 d: {d('exch_balance_chg_7d_btc')}")
            if d("exch_netflow_btc_7d"):
                parts.append(f"flujo neto 7 d: {d('exch_netflow_btc_7d')}")
            if parts:
                src = self.facts.get("exch_netflow_btc_7d", self.facts.get("exch_balance_chg_7d_btc", {})).get("source", {}).get("name", "")
                lines.append(" · ".join(parts) + (f" <i>(según {html.escape(src, quote=False)})</i>" if src else ""))
        elif block == "macro":
            parts = []
            if d("us10y_yield"):
                s = f"EE. UU. 10 años: {d('us10y_yield')}"
                if d("us10y_real_yield"):
                    s += f" (real {d('us10y_real_yield')})"
                parts.append(s)
            elif d("us10y_real_yield"):
                parts.append(f"Rentabilidad real 10 años: {d('us10y_real_yield')}")
            if d("eurusd"):
                parts.append(f"EUR/USD {d('eurusd')}")
            if d("fed_funds_upper"):
                parts.append(f"tipo Fed (máx.): {d('fed_funds_upper')}")
            if d("us2y_minus_ffr_bp"):
                parts.append(html.escape(self.facts["us2y_minus_ffr_bp"]["state"]["label_es"], quote=False))
            if d("ndx_chg_1d_pct"):
                parts.append(f"Nasdaq-100: {d('ndx_chg_1d_pct')}")
            if parts:
                lines.append(" · ".join(parts))
        elif block == "derivados":
            parts = []
            if d("funding_rate_agg_8h"):
                parts.append(f"Funding: {d('funding_rate_agg_8h')}/8 h")
            if d("oi_chg_24h_pct"):
                parts.append(f"Interés abierto 24 h: {d('oi_chg_24h_pct')} (en BTC)")
            if d("liq_total_usd_24h"):
                parts.append(f"Liquidaciones 24 h: {d('liq_total_usd_24h')} (mín. reportado)")
            if parts:
                lines.append(" · ".join(parts))
        return lines, label

    def axes_line(self) -> str | None:
        axes = self.fs.get("axes", [])
        if len(axes) < self.cfg.rules["axes"]["min_axes_for_thermometer"]:
            return None
        names = self.cfg.editorial["axis_short_names"]
        return " · ".join(f"{names.get(a['axis'], a['axis'])} {EMOJI[a['color']]}" for a in axes)

    def attributions(self) -> list[str]:
        seen: list[str] = []
        for f in self.fs["facts"]:
            if not f["selected"]:
                continue
            name = f["source"]["name"]
            base = name.replace("cálculo propio sobre ", "")
            for n in (base,):
                if n and n not in seen:
                    seen.append(n)
        return seen

    def render(self, ctx: RunContext, output: DailyOutput, origin: str, reviewer: str | None = None) -> RenderedDaily:
        ed = self.cfg.editorial
        lectura_html = " ".join(fill(s.text, self.facts, self.hints, escape=True) for s in output.lectura)
        vigilar_html = fill(output.vigilar.text, self.facts, self.hints, escape=True)
        comments = {c.block: fill(c.text, self.facts, self.hints, escape=True) for c in output.block_comments}
        blocks_out = []
        for b in ed["blocks"]:
            bid = b["id"]
            if bid not in self.blocks:
                continue
            lines, label = self.block_lines(bid)
            if not lines:
                continue
            title = b["title"]
            if bid == "macro" and self.d("ndx_chg_1d_pct"):
                title = "Risk-on y tipos"
            blocks_out.append({"emoji": b["emoji"], "title": title, "as_of_label": html.escape(label, quote=False) if label else None,
                               "lines": lines, "comment": comments.get(bid)})
        if origin == "llm_reviewed" and reviewer:
            ai_label = ed["ai_labels"]["reviewed"].format(reviewer=reviewer)
        elif origin in ("llm", "llm_reviewed"):
            ai_label = ed["ai_labels"]["llm"]
        else:
            ai_label = ed["ai_labels"]["template"]
        footer = ed["footers"]["daily_llm" if origin.startswith("llm") else "daily_template"]
        attrs = self.attributions()
        out = _env().get_template("daily_telegram.html.j2").render(
            title=ed["brand"]["daily_title"], date_line=date_weekday(ctx.report_date), ai_label=ai_label,
            bitcoin_lines=self.bitcoin_lines(), blocks=blocks_out, axes_line=self.axes_line(),
            lectura=lectura_html, vigilar=vigilar_html, footer=html.escape(footer, quote=False),
            data_timestamp=ctx.now_madrid.strftime("%d/%m %H:%M"), attributions=html.escape(" · ".join(attrs), quote=False),
            methodology_url=ed["brand"]["methodology_url"],
        )
        out = re.sub(r"\n{3,}", "\n\n", out).strip()
        plain = strip_tags(out)
        return RenderedDaily(html=out, plain=plain, lectura_rendered=strip_tags(lectura_html),
                             vigilar_rendered=strip_tags(vigilar_html), visible_chars=len(plain), ai_label=ai_label,
                             attributions=attrs)
