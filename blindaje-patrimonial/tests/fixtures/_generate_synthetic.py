"""Genera fixtures SINTÉTICOS con la forma documentada de cada API (docs/02).

AVISO: los valores son ficticios. Sirven para desarrollar y probar sin red. En la Fase 0 se sustituyen por
respuestas reales grabadas desde el VPS con `bp smoke --record`.

Uso: python tests/fixtures/_generate_synthetic.py  (fecha de referencia: 2026-09-24)
"""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
REF = date(2026, 9, 24)
UTC = timezone.utc
rnd = random.Random(42)


def w(rel: str, content: str | bytes) -> None:
    p = HERE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))


def main() -> None:
    # CoinGecko /coins/bitcoin
    w("coingecko/coins_bitcoin.json", json.dumps({
        "id": "bitcoin", "symbol": "btc", "last_updated": "2026-09-24T06:49:30.000Z",
        "market_data": {
            "current_price": {"usd": 101250.0, "eur": 86540.0},
            "price_change_percentage_24h_in_currency": {"usd": 0.3, "eur": 0.1},
            "price_change_percentage_7d_in_currency": {"usd": -2.4, "eur": -0.6},
            "price_change_percentage_30d_in_currency": {"usd": 3.1, "eur": 2.0},
            "ath": {"usd": 126080.0, "eur": 108400.0},
            "ath_date": {"usd": "2025-10-06T18:57:42.558Z", "eur": "2025-10-06T18:57:42.558Z"},
            "ath_change_percentage": {"usd": -19.69, "eur": -20.17},
            "last_updated": "2026-09-24T06:49:30.000Z",
        }}, indent=1))
    ts = int(datetime(2026, 9, 24, 6, 49, tzinfo=UTC).timestamp())
    w("coingecko/simple_price.json", json.dumps({
        "tether": {"usd": 1.0001, "last_updated_at": ts}, "usd-coin": {"usd": 0.9999, "last_updated_at": ts},
        "pax-gold": {"usd": 3810.5, "last_updated_at": ts}}, indent=1))
    # alternative.me
    vals = [(0, 52, "Neutral"), (1, 57, "Greed"), (2, 63, "Greed"), (3, 66, "Greed"), (4, 68, "Greed"), (5, 69, "Greed"),
            (6, 70, "Greed"), (7, 71, "Greed")]
    data = [{"value": str(v), "value_classification": c,
             "timestamp": str(int(datetime.combine(REF - timedelta(days=d), datetime.min.time(), tzinfo=UTC).timestamp()))}
            for d, v, c in vals]
    data[0]["time_until_update"] = "61200"
    w("alternative_me/fng.json", json.dumps({"name": "Fear and Greed Index", "data": data, "metadata": {"error": None}}, indent=1))
    # mempool
    w("mempool/tip_height.txt", "967612")
    w("mempool/difficulty_adjustment.json", json.dumps({"progressPercent": 42.1, "difficultyChange": 1.3, "remainingBlocks": 1167,
                                                        "timeAvg": 598000, "nextRetargetHeight": 969024}, indent=1))
    # Tesoro (OData Atom)
    def atom(fields_by_day: dict[date, dict[str, float]]) -> str:
        entries = []
        for d, fields in sorted(fields_by_day.items()):
            props = "".join(f"<d:{k} m:type=\"Edm.Double\">{v}</d:{k}>" for k, v in fields.items())
            entries.append(f"<entry><content type=\"application/xml\"><m:properties><d:NEW_DATE m:type=\"Edm.DateTime\">{d.isoformat()}T00:00:00</d:NEW_DATE>{props}</m:properties></content></entry>")
        return ("<?xml version=\"1.0\" encoding=\"utf-8\"?><feed xmlns=\"http://www.w3.org/2005/Atom\" "
                "xmlns:m=\"http://schemas.microsoft.com/ado/2007/08/dataservices/metadata\" "
                "xmlns:d=\"http://schemas.microsoft.com/ado/2007/08/dataservices\">" + "".join(entries) + "</feed>")
    days = [REF - timedelta(days=i) for i in range(1, 25) if (REF - timedelta(days=i)).weekday() < 5 and (REF - timedelta(days=i)) != date(2026, 9, 7)]
    nominal = {d: {"BC_2YEAR": round(4.02 + 0.01 * i, 2), "BC_10YEAR": round(4.21 - 0.005 * i, 2)} for i, d in enumerate(sorted(days, reverse=True))}
    real = {d: {"TC_10YEAR": round(1.92 - 0.004 * i, 2)} for i, d in enumerate(sorted(days, reverse=True))}
    w("treasury/nominal.xml", atom(nominal))
    w("treasury/real.xml", atom(real))
    # NY Fed
    w("nyfed/effr.json", json.dumps({"refRates": [
        {"effectiveDate": (REF - timedelta(days=i)).isoformat(), "type": "EFFR", "percentRate": 3.88 if REF - timedelta(days=i) >= date(2026, 9, 17) else 3.63}
        for i in (2, 3, 4, 7, 8)]}, indent=1))
    w("nyfed/rrp.json", json.dumps({"repo": {"operations": [
        {"operationDate": (REF - timedelta(days=i)).isoformat(), "operationType": "Reverse Repo", "totalAmtAccepted": 22_400_000_000 - i * 1e8}
        for i in (1, 2, 3, 6, 7)]}}, indent=1))
    # Fiscal Data (millones USD)
    w("fiscaldata/operating_cash_balance.json", json.dumps({"data": [
        {"record_date": (REF - timedelta(days=i)).isoformat(), "account_type": "Treasury General Account (TGA) Closing Balance",
         "open_today_bal": str(850000 - i * 1500), "close_today_bal": "null"} for i in (2, 3, 4, 5)]}, indent=1))
    # Reserva Federal H.4.1 (DDP CSV)
    rows = ["Series Description,Total assets (less eliminations from consolidation): Wednesday level",
            "Unit:,Millions of Dollars", "Multiplier:,1000000", "Currency:,USD", "Unique Identifier:,H41/H41/RESPPMA_N.WW",
            "Time Period,RESPPMA_N.WW"]
    wed = REF - timedelta(days=(REF.weekday() - 2) % 7 or 7)
    for i in range(8, -1, -1):
        d = wed - timedelta(weeks=i)
        rows.append(f"{d.isoformat()},{6742000 - i * 3000}")
    w("fed_h41/h41.csv", "\n".join(rows) + "\n")
    # BCE
    cubes = "".join(f"<Cube time=\"{(REF - timedelta(days=i)).isoformat()}\"><Cube currency=\"USD\" rate=\"{1.1700 + 0.002 * (i % 5):.4f}\"/><Cube currency=\"JPY\" rate=\"171.20\"/></Cube>"
                    for i in range(1, 20) if (REF - timedelta(days=i)).weekday() < 5)
    w("ecb_fx/eurofxref-hist-90d.xml", "<?xml version=\"1.0\" encoding=\"UTF-8\"?><gesmes:Envelope xmlns:gesmes=\"http://www.gesmes.org/xml/2002-08-01\" "
      "xmlns=\"http://www.ecb.int/vocabulary/2002-08-01/eurofxref\"><Cube>" + cubes + "</Cube></gesmes:Envelope>")
    # SoSoValue (sesiones de EE. UU.)
    sessions = []
    d = REF - timedelta(days=1)
    while len(sessions) < 30:
        if d.weekday() < 5 and d != date(2026, 9, 7):
            sessions.append(d)
        d -= timedelta(days=1)
    flows = [-420e6, -95e6, -160e6] + [rnd.uniform(-250e6, 450e6) for _ in range(27)]
    w("sosovalue/summary_history.json", json.dumps({"code": 0, "data": [
        {"date": s.isoformat(), "total_net_inflow": round(f), "total_btc_holdings": 1_320_000 - i * 150}
        for i, (s, f) in enumerate(zip(sessions, flows, strict=True))]}, indent=1))


if __name__ == "__main__":
    main()
    print("fixtures sintéticos generados en", HERE)
