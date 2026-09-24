"""Modelos de dominio en memoria (independientes de la base de datos)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")
NEW_YORK = ZoneInfo("America/New_York")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Observation:
    """Un dato normalizado (fila de metric_observations)."""

    metric_id: str
    as_of: datetime
    value: float | str | dict | list | None
    unit: str
    source_id: str
    retrieved_at: datetime
    method: str = "provider_field"          # provider_field | computed | fallback | manual
    source_url: str | None = None
    as_of_label: str | None = None
    dimension: str = ""
    status: str = "final"                   # provisional (datos revisables: ETF, M2…) | final | revised | rejected
    quality: str = "ok"                     # ok | warn | error
    quality_notes: dict[str, Any] = field(default_factory=dict)
    secondary_value: float | None = None
    deviation_pct: float | None = None
    vintage_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    raw_payload_id: int | None = None

    @property
    def num(self) -> float | None:
        return float(self.value) if isinstance(self.value, (int, float)) and not isinstance(self.value, bool) else None


@dataclass
class RawResponse:
    source_id: str
    request_url: str          # sin secretos
    status: int
    body: bytes
    content_type: str | None
    fetched_at: datetime
    fixture: str | None = None      # nombre de fixture equivalente (para `bp smoke --record`)


@dataclass
class Signal:
    """Salida de la capa de análisis para una métrica (fila de derived_signals)."""

    metric_id: str
    as_of: datetime
    stats: dict[str, Any]
    state_code: str | None = None
    state_label_es: str | None = None
    axis: str | None = None
    color: str = "none"
    salience: float = 0.0
    hints: list[dict[str, Any]] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)


@dataclass
class AxisState:
    axis: str
    color: str
    label_es: str
    driver_fact_ids: list[str]
    changed_vs_prev: bool = False


@dataclass
class CalendarEvent:
    event_key: str
    event_type: str
    title_es: str
    scheduled_at: datetime            # UTC
    time_precision: str = "exact"     # exact | date_only
    status: str = "scheduled"
    country: str | None = None
    source_name: str = ""
    source_url: str = ""
    weight_override: int | None = None


@dataclass
class RunContext:
    """Contexto de una ejecución (un día de publicación)."""

    report_date: date                 # fecha Europe/Madrid de publicación
    now: datetime                     # instante UTC "actual" (inyectable para pruebas y reejecuciones)
    offline: bool = False
    dry_run: bool = False

    @property
    def now_madrid(self) -> datetime:
        return self.now.astimezone(MADRID)
