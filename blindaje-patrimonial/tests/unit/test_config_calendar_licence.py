from datetime import date, datetime, timezone

from bp.calendar.events import build_events, is_us_session, nyse_holidays, previous_us_session
from bp.config import load_config, validate
from bp.licence import metric_publishable
from bp.models import MADRID


def test_config_is_consistent():
    cfg = load_config()
    assert validate(cfg) == []
    assert isinstance(cfg.rules["liquidity"]["us_net_liquidity"]["expansion_above_usd"], float)   # 1.5e11 no es texto


def test_every_mvp_metric_has_a_known_primary_source():
    cfg = load_config()
    for mid, m in cfg.metrics.items():
        if m.mvp and m.primary_source and not m.primary_source.startswith("TBD"):
            assert m.primary_source in cfg.sources, f"{mid}: fuente {m.primary_source} desconocida"


def test_licence_gate():
    cfg = load_config()
    assert metric_publishable(cfg, "btc_usd")
    assert metric_publishable(cfg, "fng_value")
    assert not metric_publishable(cfg, "etf_net_flow_usd_1d")          # SoSoValue: permiso pendiente
    assert not metric_publishable(cfg, "etf_flow_streak_days")         # un derivado hereda la restricción


def test_us_sessions_and_holidays():
    cfg = load_config()
    hol = nyse_holidays(cfg)
    assert date(2026, 11, 26) in hol                                   # Acción de Gracias 2026
    assert not is_us_session(date(2026, 9, 26), hol)                   # sábado
    assert previous_us_session(date(2026, 9, 28), hol) == date(2026, 9, 25)


def test_calendar_events_are_utc_and_include_quarterly_expiry():
    cfg = load_config()
    evs = build_events(cfg, date(2026, 9, 23), date(2026, 10, 31))
    keys = {e.event_key for e in evs}
    assert any(k.startswith("deribit_expiry") and "2026-09-25" in k for k in keys)
    fomc = [e for e in evs if "fomc" in e.event_key.lower()]
    assert fomc and all(e.scheduled_at.tzinfo is not None for e in evs)
    # 14:00 ET del 28 oct 2026: Europa ya está en horario de invierno (25 oct) y EE. UU. aún no (1 nov) → 19:00 en Madrid
    assert fomc[0].event_key == "fomc_decision:2026-10-28"
    assert fomc[0].scheduled_at.astimezone(MADRID).hour == 19


def test_expiry_time_is_0800_utc():
    cfg = load_config()
    exp = next(e for e in build_events(cfg, date(2026, 9, 25), date(2026, 9, 25)) if e.event_key.startswith("deribit_expiry"))
    assert exp.scheduled_at == datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)
