"""Calendario de eventos programados (docs/02 §3.8, docs/04 §6).

Fuentes en esta versión:
- config/calendar/us_macro_2026.yaml (macro EE. UU., FOMC, BCE; mantenido a mano)
- config/calendar/nyse_holidays.yaml (festivos y cierres anticipados)
- config/calendar/regulatory.yaml (plazos fiscales y regulatorios)
- reglas: vencimientos de opciones BTC en Deribit (último viernes, 08:00 UTC; trimestrales mar/jun/sep/dic)
  y último día de negociación de futuros BTC en CME (último viernes, 16:00 Londres).
Todas las horas se guardan en UTC; se presentan en Europe/Madrid.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from bp.config import Config
from bp.models import CalendarEvent

UTC = timezone.utc


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def nyse_holidays(cfg: Config) -> set[date]:
    data = _load(cfg.root / "config" / "calendar" / "nyse_holidays.yaml")
    out: set[date] = set()
    for days in (data.get("holidays") or {}).values():
        out.update(date.fromisoformat(str(d)) for d in days)
    return out


def nyse_early_closes(cfg: Config) -> set[date]:
    data = _load(cfg.root / "config" / "calendar" / "nyse_holidays.yaml")
    out: set[date] = set()
    for days in (data.get("early_close_13h") or {}).values():
        out.update(date.fromisoformat(str(d)) for d in days)
    return out


def is_us_session(d: date, holidays: set[date]) -> bool:
    return d.weekday() < 5 and d not in holidays


def previous_us_session(d: date, holidays: set[date]) -> date:
    """Última sesión de la NYSE estrictamente anterior a d."""
    x = d - timedelta(days=1)
    while not is_us_session(x, holidays):
        x -= timedelta(days=1)
    return x


def last_friday(year: int, month: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    d = nxt - timedelta(days=1)
    while d.weekday() != 4:
        d -= timedelta(days=1)
    return d


def _at(d: date, hhmm: str, tz: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(d, time(h, m), tzinfo=ZoneInfo(tz)).astimezone(UTC)


def build_events(cfg: Config, start: date, end: date) -> list[CalendarEvent]:
    """Eventos entre start y end (inclusive)."""
    events: list[CalendarEvent] = []
    macro = _load(cfg.root / "config" / "calendar" / "us_macro_2026.yaml")
    for e in macro.get("events", []):
        d = date.fromisoformat(str(e["date"]))
        if start <= d <= end:
            events.append(CalendarEvent(
                event_key=e["key"], event_type=e["type"], title_es=e["title_es"],
                scheduled_at=_at(d, e["time"], e["tz"]), time_precision="exact",
                country="US" if e["tz"] == "America/New_York" else "EA", source_name=e.get("source", ""),
                source_url=e.get("url", ""),
                weight_override=(cfg.rules["watch_today"]["event_weights"]["fomc_decision"]
                                 + cfg.rules["watch_today"]["event_weights"]["fomc_decision_sep_bonus"]) if e.get("sep") else None,
            ))
    holidays = nyse_holidays(cfg)
    early = nyse_early_closes(cfg)
    d = start
    while d <= end:
        if d in holidays:
            events.append(CalendarEvent(f"us_market_holiday:{d}", "us_market_holiday",
                                        "Festivo en EE. UU.: sin sesión en Wall Street ni flujos de ETF",
                                        datetime.combine(d, time(14, 30), tzinfo=UTC), "date_only", country="US",
                                        source_name="NYSE", source_url="https://www.nyse.com/markets/hours-calendars"))
        if d in early:
            events.append(CalendarEvent(f"us_early_close:{d}", "us_early_close", "Cierre anticipado en Wall Street (13:00 hora de Nueva York)",
                                        _at(d, "13:00", "America/New_York"), "exact", country="US", source_name="NYSE",
                                        source_url="https://www.nyse.com/markets/hours-calendars"))
        d += timedelta(days=1)
    # Vencimientos de opciones BTC en Deribit y futuros CME
    m = date(start.year, start.month, 1)
    while m <= end:
        lf = last_friday(m.year, m.month)
        if start <= lf <= end:
            quarterly = m.month in (3, 6, 9, 12)
            events.append(CalendarEvent(
                f"deribit_expiry:{lf}", "deribit_quarterly_expiry" if quarterly else "deribit_monthly_expiry",
                ("Vencimiento trimestral" if quarterly else "Vencimiento mensual") + " de opciones BTC en Deribit",
                datetime.combine(lf, time(8, 0), tzinfo=UTC), "exact", country="GLOBAL", source_name="Deribit",
                source_url="https://www.deribit.com"))
            cme_day = lf
            while not is_us_session(cme_day, holidays):     # si el último viernes es festivo, día hábil anterior [VERIFICAR con CME]
                cme_day -= timedelta(days=1)
            events.append(CalendarEvent(
                f"cme_btc_last_trade:{cme_day}", "cme_btc_last_trade", "Último día de negociación de los futuros BTC de CME",
                _at(cme_day, "16:00", "Europe/London"), "exact", country="US", source_name="CME Group",
                source_url="https://www.cmegroup.com"))
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    # Plazos fiscales y regulatorios
    for dl in cfg.regulatory.get("deadlines", []):
        dates: list[date] = []
        if dl.get("date"):
            dates.append(date.fromisoformat(str(dl["date"])))
        if dl.get("date_range"):
            a, b = (date.fromisoformat(str(x)) for x in dl["date_range"])
            dates.extend([a, b])
        for i, dd in enumerate(dates):
            if start <= dd <= end and dl.get("watch_weight"):
                is_end = dl.get("date_range") and i == len(dates) - 1
                events.append(CalendarEvent(
                    f"regulatory:{dl['id']}:{dd}", "regulatory_deadline",
                    (("Fin de plazo: " if is_end else "Inicio de plazo: ") if dl.get("date_range") else "") + dl["obligation"],
                    datetime.combine(dd, time(9, 0), tzinfo=UTC), "date_only", country=dl.get("jurisdiction"),
                    status="scheduled" if dl.get("status") == "confirmed" else "tentative",
                    source_name="calendario regulatorio", source_url=str(dl.get("evidence_url", "")),
                    weight_override=int(dl["watch_weight"])))
    return sorted(events, key=lambda e: e.scheduled_at)
