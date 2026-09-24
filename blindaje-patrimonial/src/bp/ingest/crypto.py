"""Conectores de datos cripto: CoinGecko, alternative.me, mempool.space, SoSoValue (docs/02 §3.1–3.5).

Los formatos de respuesta siguen la documentación pública verificada en la investigación; los fixtures de
tests/fixtures/ son sintéticos con esa forma y deben sustituirse por respuestas grabadas desde el VPS (Fase 0).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from bp.ingest.base import Connector, ConnectorError
from bp.models import NEW_YORK, Observation, RawResponse, RunContext

UTC = timezone.utc


def _ts(v) -> datetime:
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(float(v), tz=UTC)
    s = str(v).replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class CoinGecko(Connector):
    id = "coingecko"
    source_id = "coingecko_basic"
    BASE = "https://pro-api.coingecko.com/api/v3"

    def fetch(self, ctx: RunContext) -> list[RawResponse]:
        return [
            self.get(ctx, f"{self.BASE}/coins/bitcoin", "coins_bitcoin.json",
                     params={"localization": "false", "tickers": "false", "market_data": "true", "community_data": "false",
                             "developer_data": "false", "sparkline": "false"}),
            self.get(ctx, f"{self.BASE}/simple/price", "simple_price.json",
                     params={"ids": "tether,usd-coin,pax-gold", "vs_currencies": "usd", "include_last_updated_at": "true"}),
        ]

    def parse(self, ctx: RunContext, raws: list[RawResponse]) -> list[Observation]:
        coin, simple = (json.loads(r.body) for r in raws)
        md = coin["market_data"]
        as_of = _ts(md.get("last_updated") or coin.get("last_updated"))
        r0, r1 = raws
        out = [
            self.obs(ctx, "btc_usd", float(md["current_price"]["usd"]), as_of, r0),
            self.obs(ctx, "btc_eur", float(md["current_price"]["eur"]), as_of, r0),
            self.obs(ctx, "btc_chg_24h_pct", float(md["price_change_percentage_24h_in_currency"]["usd"]), as_of, r0),
            self.obs(ctx, "btc_chg_7d_pct", float(md["price_change_percentage_7d_in_currency"]["usd"]), as_of, r0),
            self.obs(ctx, "btc_chg_7d_eur_pct", float(md["price_change_percentage_7d_in_currency"]["eur"]), as_of, r0),
            self.obs(ctx, "btc_chg_30d_pct", float(md["price_change_percentage_30d_in_currency"]["usd"]), as_of, r0),
            self.obs(ctx, "btc_ath_usd", float(md["ath"]["usd"]), as_of, r0),
            self.obs(ctx, "btc_ath_usd_date", str(md["ath_date"]["usd"]), as_of, r0),
            self.obs(ctx, "btc_ath_eur", float(md["ath"]["eur"]), as_of, r0),
            self.obs(ctx, "btc_ath_eur_date", str(md["ath_date"]["eur"]), as_of, r0),
        ]
        for coin_id, mid in (("tether", "usdt_peg"), ("usd-coin", "usdc_peg"), ("pax-gold", "paxg_usd")):
            row = simple.get(coin_id)
            if row and "usd" in row:
                out.append(self.obs(ctx, mid, float(row["usd"]), _ts(row.get("last_updated_at", ctx.now.timestamp())), r1))
        # contraste implícito EUR/USD frente al BCE lo hace validation (I-XSRC); aquí solo se normaliza
        return out


class AlternativeMe(Connector):
    """Índice de Miedo y Codicia. Asignación hoy / D-1 / D-7 POR TIMESTAMP (día UTC), no por posición."""

    id = "alternative_me"
    source_id = "alternative_me"

    def fetch(self, ctx: RunContext) -> list[RawResponse]:
        return [self.get(ctx, "https://api.alternative.me/fng/", "fng.json", params={"limit": "8"})]

    def parse(self, ctx: RunContext, raws: list[RawResponse]) -> list[Observation]:
        data = json.loads(raws[0].body)
        if (data.get("metadata") or {}).get("error"):
            raise ConnectorError(f"alternative.me: {data['metadata']['error']}")
        by_day: dict[date, dict] = {}
        for row in data["data"]:
            d = _ts(int(row["timestamp"])).date()
            by_day[d] = row
        today = ctx.now.astimezone(UTC).date()
        out: list[Observation] = []
        if today not in by_day:
            raise ConnectorError("alternative.me: aún no hay valor de hoy (UTC)")
        r = raws[0]
        t = by_day[today]
        as_of = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        out.append(self.obs(ctx, "fng_value", int(t["value"]), as_of, r))
        out.append(self.obs(ctx, "fng_class", str(t["value_classification"]), as_of, r))
        for days, mid in ((1, "fng_value_1d_ago"), (7, "fng_value_7d_ago")):
            d = today - timedelta(days=days)
            if d in by_day:
                out.append(self.obs(ctx, mid, int(by_day[d]["value"]), datetime.combine(d, datetime.min.time(), tzinfo=UTC), r))
        # guardar también la serie histórica (para rachas y percentiles)
        for d, row in by_day.items():
            if d != today:
                ts = datetime.combine(d, datetime.min.time(), tzinfo=UTC)
                out.append(self.obs(ctx, "fng_value", int(row["value"]), ts, r))
                out.append(self.obs(ctx, "fng_class", str(row["value_classification"]), ts, r))
        return out


class Mempool(Connector):
    """Altura de bloque y ritmo reciente de bloques (solo hechos de la blockchain; nunca sus precios)."""

    id = "mempool"
    source_id = "mempool_space"

    def fetch(self, ctx: RunContext) -> list[RawResponse]:
        return [self.get(ctx, "https://mempool.space/api/blocks/tip/height", "tip_height.txt", accept="text/plain"),
                self.get(ctx, "https://mempool.space/api/v1/difficulty-adjustment", "difficulty_adjustment.json")]

    def parse(self, ctx: RunContext, raws: list[RawResponse]) -> list[Observation]:
        height = int(raws[0].body.decode().strip())
        da = json.loads(raws[1].body)
        out = [self.obs(ctx, "block_height", height, ctx.now, raws[0])]
        if da.get("timeAvg"):
            out.append(Observation(metric_id="block_time_avg_s", as_of=ctx.now, value=float(da["timeAvg"]) / 1000.0, unit="s",
                                   source_id=self.source_id, retrieved_at=ctx.now, source_url=raws[1].request_url))
        return out


class SoSoValueETF(Connector):
    """Flujos de ETF spot BTC de EE. UU. (licencia pendiente: L3). Datación por sesión de EE. UU."""

    id = "sosovalue"
    source_id = "sosovalue_api"

    def fetch(self, ctx: RunContext) -> list[RawResponse]:
        return [self.get(ctx, "https://openapi.sosovalue.com/openapi/v1/etfs/summary-history", "summary_history.json",
                         params={"symbol": "BTC", "country_code": "US", "limit": "30"})]

    def parse(self, ctx: RunContext, raws: list[RawResponse]) -> list[Observation]:
        data = json.loads(raws[0].body)
        rows = data.get("data") or []
        if isinstance(rows, dict):
            rows = rows.get("list") or rows.get("items") or []
        out: list[Observation] = []
        for row in rows:
            d = date.fromisoformat(str(row.get("date") or row.get("trade_date"))[:10])
            flow = row.get("total_net_inflow", row.get("totalNetInflow"))
            if flow is None:
                continue
            as_of = datetime.combine(d, datetime.min.time().replace(hour=16), tzinfo=NEW_YORK).astimezone(UTC)
            from bp.editorial.format import session_label
            complete = row.get("is_complete", True)
            out.append(self.obs(ctx, "etf_net_flow_usd_1d", float(flow), as_of, raws[0], as_of_label=session_label(d),
                                status="final" if (ctx.now - as_of) > timedelta(hours=36) and complete else "provisional"))
            if row.get("total_btc_holdings") is not None:
                out.append(self.obs(ctx, "etf_total_btc_held", float(row["total_btc_holdings"]), as_of, raws[0], as_of_label=session_label(d)))
        return out
