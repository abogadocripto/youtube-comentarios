"""Conectores de fuentes oficiales: Tesoro de EE. UU., Fed de Nueva York, Fiscal Data (TGA), Reserva Federal (H.4.1)
y BCE (docs/02 §3.3). Datos de dominio público o reutilizables con atribución.
"""

from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

from bp.ingest.base import Connector, ConnectorError
from bp.models import Observation, RawResponse, RunContext

UTC = timezone.utc


def _day(d: str) -> datetime:
    return datetime.combine(date.fromisoformat(d[:10]), datetime.min.time(), tzinfo=UTC)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class TreasuryYields(Connector):
    """Curvas diarias nominal y real (XML OData). Elementos BC_2YEAR/BC_10YEAR (nominal) y *_10YEAR (real)."""

    id = "treasury"
    source_id = "us_treasury_xml"
    BASE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"

    def fetch(self, ctx: RunContext) -> list[RawResponse]:
        month = ctx.now.strftime("%Y%m")
        return [self.get(ctx, self.BASE, "nominal.xml", params={"data": "daily_treasury_yield_curve", "field_tdr_date_value_month": month}, accept="application/xml"),
                self.get(ctx, self.BASE, "real.xml", params={"data": "daily_treasury_real_yield_curve", "field_tdr_date_value_month": month}, accept="application/xml")]

    @staticmethod
    def _rows(body: bytes) -> list[dict[str, str]]:
        root = ET.fromstring(body)
        rows = []
        for props in root.iter():
            if _local(props.tag) == "properties":
                rows.append({_local(c.tag): (c.text or "").strip() for c in props})
        return rows

    def parse(self, ctx: RunContext, raws: list[RawResponse]) -> list[Observation]:
        out: list[Observation] = []
        for r, kind in zip(raws, ("nominal", "real"), strict=True):
            for row in self._rows(r.body):
                d = row.get("NEW_DATE") or row.get("Date") or row.get("DATE")
                if not d:
                    continue
                as_of = _day(d)
                if kind == "nominal":
                    for field, mid in (("BC_10YEAR", "us10y_yield"), ("BC_2YEAR", "us2y_yield")):
                        if row.get(field):
                            out.append(self.obs(ctx, mid, float(row[field]), as_of, r))
                else:
                    k = next((k for k in row if k.endswith("10YEAR")), None)     # nombre exacto [VERIFICAR]
                    if k and row[k]:
                        out.append(self.obs(ctx, "us10y_real_yield", float(row[k]), as_of, r))
        if not out:
            raise ConnectorError("Tesoro: sin filas reconocibles (¿cambio de esquema?)")
        return out


class NYFed(Connector):
    """EFFR y operaciones de repo inverso (ON RRP)."""

    id = "nyfed"
    source_id = "nyfed_markets"

    def fetch(self, ctx: RunContext) -> list[RawResponse]:
        return [self.get(ctx, "https://markets.newyorkfed.org/api/rates/unsecured/effr/last/5.json", "effr.json"),
                self.get(ctx, "https://markets.newyorkfed.org/api/rp/all/all/results/lastTwoWeeks.json", "rrp.json")]

    def parse(self, ctx: RunContext, raws: list[RawResponse]) -> list[Observation]:
        out: list[Observation] = []
        effr = json.loads(raws[0].body)
        for row in effr.get("refRates", []):
            if row.get("type", "EFFR") == "EFFR" and row.get("percentRate") is not None:
                out.append(self.obs(ctx, "fed_funds_effective", float(row["percentRate"]), _day(row["effectiveDate"]), raws[0]))
        rrp = json.loads(raws[1].body)
        ops = (rrp.get("repo") or {}).get("operations", [])
        for op in ops:
            if "reverse" not in str(op.get("operationType", "")).lower():
                continue
            amt = op.get("totalAmtAccepted")
            if amt is None:
                continue
            v = float(amt)
            if v < 1e7:                        # salvaguarda de unidades: importes en miles de millones → USD [VERIFICAR]
                v *= 1e9
            out.append(self.obs(ctx, "on_rrp_usd", v, _day(op["operationDate"]), raws[1]))
        return out


class FiscalDataTGA(Connector):
    """Saldo de la TGA (Daily Treasury Statement, millones de USD)."""

    id = "fiscaldata"
    source_id = "fiscaldata_dts"

    def fetch(self, ctx: RunContext) -> list[RawResponse]:
        since = (ctx.now - timedelta(days=45)).date().isoformat()
        return [self.get(ctx, "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance",
                         "operating_cash_balance.json", params={"filter": f"record_date:gte:{since}", "sort": "-record_date", "page[size]": "100"})]

    def parse(self, ctx: RunContext, raws: list[RawResponse]) -> list[Observation]:
        data = json.loads(raws[0].body)
        out: list[Observation] = []
        for row in data.get("data", []):
            if "closing balance" not in str(row.get("account_type", "")).lower():
                continue
            val = row.get("open_today_bal") or row.get("close_today_bal")     # columna exacta [VERIFICAR]
            if val in (None, "", "null"):
                continue
            out.append(self.obs(ctx, "tga_usd", float(val) * 1e6, _day(row["record_date"]), raws[0]))
        return out


class FedH41(Connector):
    """Balance de la Reserva Federal (H.4.1, nivel del miércoles) vía Data Download Program (CSV)."""

    id = "fed_h41"
    source_id = "fed_board_ddp"

    def fetch(self, ctx: RunContext) -> list[RawResponse]:
        return [self.get(ctx, "https://www.federalreserve.gov/datadownload/Output.aspx", "h41.csv",
                         params={"rel": "H41", "series": "[●paquete WALCL]", "filetype": "csv", "label": "include", "layout": "seriescolumn"},
                         accept="text/csv")]

    def parse(self, ctx: RunContext, raws: list[RawResponse]) -> list[Observation]:
        text = raws[0].body.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
        multiplier = 1.0
        out: list[Observation] = []
        for row in rows:
            if not row:
                continue
            head = row[0].strip().lower()
            if head.startswith("multiplier"):
                multiplier = float(row[1])
            elif len(row) >= 2 and len(row[0]) == 10 and row[0][4] == "-":
                try:
                    out.append(self.obs(ctx, "fed_total_assets_usd", float(row[1]) * multiplier, _day(row[0]), raws[0]))
                except ValueError:
                    continue
        return out


class ECBFx(Connector):
    """Tipos de referencia del BCE (≈16:00 CET de cada día TARGET)."""

    id = "ecb_fx"
    source_id = "ecb_fx_xml"

    def fetch(self, ctx: RunContext) -> list[RawResponse]:
        return [self.get(ctx, "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml", "eurofxref-hist-90d.xml", accept="application/xml")]

    def parse(self, ctx: RunContext, raws: list[RawResponse]) -> list[Observation]:
        root = ET.fromstring(raws[0].body)
        out: list[Observation] = []
        for cube in root.iter():
            if _local(cube.tag) == "Cube" and cube.get("time"):
                for c in cube:
                    if c.get("currency") == "USD":
                        out.append(self.obs(ctx, "eurusd", float(c.get("rate")), _day(cube.get("time")), raws[0]))
        return out


class FOMCConfig(Connector):
    """Rango objetivo desde config/fomc.yaml (lo materializa analysis.derive); aquí no hay red."""

    id = "fomc"
    source_id = "config_fomc"

    def fetch(self, ctx: RunContext) -> list[RawResponse]:
        return []

    def parse(self, ctx: RunContext, raws: list[RawResponse]) -> list[Observation]:
        return []
