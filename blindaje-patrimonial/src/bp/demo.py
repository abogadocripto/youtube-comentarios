"""Historia SINTÉTICA para ejecutar el pipeline completo sin red ni base de datos (`bp demo`).

Los valores son ficticios y deterministas (semilla fija). Sirven para probar la arquitectura de principio a fin
(ingesta con fixtures → derivación → análisis → selección → LLM/respaldo → validación → renderizado).
"""

from __future__ import annotations

import math
import random
from datetime import date, datetime, time, timedelta, timezone

from bp.models import NEW_YORK, Observation
from bp.store.base import Store

UTC = timezone.utc


def _o(mid: str, as_of: datetime, value, unit: str, source: str, retrieved: datetime, **kw) -> Observation:
    return Observation(metric_id=mid, as_of=as_of, value=value, unit=unit, source_id=source, retrieved_at=retrieved, **kw)


def seed_history(store: Store, report_date: date, days: int = 420, seed: int = 7) -> None:
    rnd = random.Random(seed)
    obs: list[Observation] = []
    # ─── Precio BTC diario (08:30 Madrid ≈ 06:30 UTC) terminando cerca de 101.250 $ ───
    n = days
    price = 101250.0
    series = []
    for _ in range(n):
        series.append(price)
        price /= math.exp(rnd.gauss(0.0004, 0.022))
    series.reverse()
    for i, p in enumerate(series[:-1]):                        # el último día lo aporta el fixture
        d = report_date - timedelta(days=n - 1 - i)
        ts = datetime.combine(d, time(6, 30), tzinfo=UTC)
        obs.append(_o("btc_usd", ts, round(p, 2), "USD", "coingecko_basic", ts))
        obs.append(_o("btc_ath_usd", ts, max(126080.0, round(p, 2)) if d >= date(2025, 10, 6) else round(max(series[: i + 1]), 2), "USD", "coingecko_basic", ts))
    # ─── Miedo y Codicia (anterior a los 8 días del fixture) ───
    v = 55.0
    for i in range(n, 8, -1):
        d = report_date - timedelta(days=i)
        v = min(95, max(5, v + rnd.gauss(0, 5)))
        ts = datetime.combine(d, time(0, 0), tzinfo=UTC)
        cls = "Extreme Fear" if v < 25 else "Fear" if v < 47 else "Neutral" if v < 55 else "Greed" if v < 76 else "Extreme Greed"
        obs.append(_o("fng_value", ts, int(v), "index", "alternative_me", ts))
        obs.append(_o("fng_class", ts, cls, "index", "alternative_me", ts))
    # ─── Tipos (sesiones anteriores al fixture) ───
    y10, r10 = 4.30, 2.00
    for i in range(120, 24, -1):
        d = report_date - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        ts = datetime.combine(d, time(0, 0), tzinfo=UTC)
        y10 += rnd.gauss(0, 0.03)
        r10 += rnd.gauss(0, 0.02)
        obs.append(_o("us10y_yield", ts, round(y10, 2), "pct", "us_treasury_xml", ts))
        obs.append(_o("us10y_real_yield", ts, round(r10, 2), "pct", "us_treasury_xml", ts))
    # ─── Índice amplio del dólar (Reserva Federal, dato diario publicado semanalmente) ───
    u = 120.0
    for i in range(60, 3, -1):
        d = report_date - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        u *= math.exp(rnd.gauss(0, 0.003))
        ts = datetime.combine(d, time(0, 0), tzinfo=UTC)
        obs.append(_o("usd_index", ts, round(u, 2), "index", "fed_board_ddp", ts))
    # ─── M2 global por componentes (USD, fin de mes) ───
    base = {"country=US": 22.3e12, "country=EA": 17.9e12, "country=CN": 45.1e12, "country=UK": 3.9e12}
    for k in range(24, 0, -1):
        m_end = (date(report_date.year, report_date.month, 1) - timedelta(days=1))
        y, mth = m_end.year, m_end.month
        mth -= k - 1
        while mth <= 0:
            mth += 12
            y -= 1
        last = (date(y + (mth == 12), mth % 12 + 1, 1) - timedelta(days=1))
        ts = datetime.combine(last, time(0, 0), tzinfo=UTC)
        pub = ts + timedelta(days=28)
        for dim, b in base.items():
            if dim == "country=UK" and k == 1:
                continue                                           # UK llega más tarde: componente arrastrado
            val = b * (1 + 0.004) ** (24 - k) * (1 + rnd.gauss(0, 0.002))
            cap = datetime.combine(report_date, time(0, 0), tzinfo=UTC)
            obs.append(_o("global_m2_usd", ts, val, "USD", "computed", min(pub, cap), dimension=dim, method="computed"))
    # ─── Liquidez neta EE. UU. (historia diaria de 60 días) ───
    nl = 5.70e12
    for i in range(60, 0, -1):
        d = report_date - timedelta(days=i)
        nl += rnd.gauss(4e9, 2e10)
        ts = datetime.combine(d, time(0, 0), tzinfo=UTC)
        obs.append(_o("us_net_liquidity_usd", ts, nl, "USD", "computed", ts, method="computed"))
    # ─── ETF: sesiones anteriores a las 30 del fixture ───
    d = report_date - timedelta(days=1)
    sessions = []
    while len(sessions) < 150:
        if d.weekday() < 5:
            sessions.append(d)
        d -= timedelta(days=1)
    for s in sessions[30:]:
        ts = datetime.combine(s, time(16, 0), tzinfo=NEW_YORK).astimezone(UTC)
        obs.append(_o("etf_net_flow_usd_1d", ts, round(rnd.uniform(-300e6, 500e6)), "USD", "sosovalue_api", ts + timedelta(hours=12)))
    # ─── On-chain propio (BRK): 5 años diarios ───
    mv, sp, lth, sip = 1.6, 1.0, 14.2e6, 80.0
    for i in range(5 * 365, 0, -1):
        d = report_date - timedelta(days=i)
        ts = datetime.combine(d + timedelta(days=1), time(0, 0), tzinfo=UTC)
        mv = min(3.8, max(0.7, mv + rnd.gauss(0, 0.03)))
        sp = max(0.9, min(1.1, 1 + rnd.gauss(0, 0.012)))
        lth += rnd.gauss(2000, 15000)
        sip = min(99, max(40, sip + rnd.gauss(0, 1.2)))
        obs += [_o("mvrv", ts, round(mv, 3), "index", "brk_selfhosted", ts), _o("sopr", ts, round(sp, 4), "index", "brk_selfhosted", ts),
                _o("lth_supply_btc", ts, round(lth), "BTC", "brk_selfhosted", ts),
                _o("supply_in_profit_pct", ts, round(sip, 2), "pct", "brk_selfhosted", ts)]
    last_ts = datetime.combine(report_date, time(0, 0), tzinfo=UTC)
    obs.append(_o("realized_price_usd", last_ts, 52800.0, "USD", "brk_selfhosted", last_ts))
    store.save_observations(obs)


class DemoBackend:
    """Backend SIMULADO para `bp demo --llm static`: ejercita la ruta LLM (esquema, marcadores, validadores,
    verificador) sin llamar a la API. Redacta a partir del fact sheet recibido en el prompt, como haría el modelo,
    y en la llamada del verificador aprueba fragmento a fragmento. No sustituye a las pruebas con el modelo real.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, *, system: str, user: str, schema: dict, call: str) -> dict:
        import json
        import re

        from bp.editorial import fallback_reading
        self.calls.append(call)
        if call.endswith("_verify"):
            frags = json.loads(re.search(r"<fragments>\n(.*)\n</fragments>", user, re.S).group(1))
            body = {"checks": [{"path": f["path"], "rendered_text": f["text"], "verdict": "supported", "issue_types": ["none"],
                                "explanation": "Coincide con los datos de entrada.", "suggested_fix": None} for f in frags],
                    "overall_pass": True, "summary": "Sin incidencias (verificador simulado)."}
        else:
            fs = json.loads(re.search(r"<fact_sheet>\n(.*)\n</fact_sheet>", user, re.S).group(1))
            body = fallback_reading.build(fs).model_dump()
        return {"text": json.dumps(body, ensure_ascii=False), "model": "demo-simulado", "stop_reason": "end_turn",
                "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0}}
