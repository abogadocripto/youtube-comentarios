"""Interfaz de almacenamiento. Implementaciones: MemoryStore (pruebas, modo offline) y PostgresStore (producción)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any

from bp.models import Observation, RawResponse, Signal


class LockBusy(RuntimeError):
    """Otro proceso tiene el cerrojo de esta familia de jobs."""


class Store(ABC):
    @contextmanager
    def lock(self, name: str) -> Iterator[None]:
        """Cerrojo por familia de jobs (docs/01 §5). En memoria no hace falta: un solo proceso."""
        yield

    # ─── datos ───
    @abstractmethod
    def save_raw(self, raw: RawResponse) -> int: ...

    @abstractmethod
    def save_observations(self, obs: list[Observation]) -> None: ...

    @abstractmethod
    def history(self, metric_id: str, limit: int = 400, dimension: str = "", until: datetime | None = None) -> list[Observation]:
        """Serie ascendente por as_of; para cada as_of, la lectura más reciente no rechazada."""

    @abstractmethod
    def vintage_series(self, metric_id: str, vintage_id: str, dimension: str = "") -> list[Observation]:
        """Todas las observaciones de una misma lectura (vintage), ascendentes por as_of (docs/03 §1.3)."""

    @abstractmethod
    def dimensions(self, metric_id: str) -> list[str]:
        """Dimensiones con datos para una métrica (p. ej. componentes por país del M2 global)."""

    def latest(self, metric_id: str, dimension: str = "", until: datetime | None = None) -> Observation | None:
        h = self.history(metric_id, limit=1, dimension=dimension, until=until)
        return h[-1] if h else None

    def values(self, metric_id: str, limit: int = 400, until: datetime | None = None) -> list[float]:
        return [o.num for o in self.history(metric_id, limit=limit, until=until) if o.num is not None]

    # ─── análisis ───
    @abstractmethod
    def save_signals(self, signals: list[Signal], rules_version: int) -> None: ...

    @abstractmethod
    def previous_signal(self, metric_id: str, before: datetime) -> Signal | None: ...

    @abstractmethod
    def save_axis_states(self, report_date: date, axes: list[Any], rules_version: int) -> None: ...

    @abstractmethod
    def previous_axis_states(self, before: date) -> dict[str, str]:
        """{eje: color} del último día anterior a `before`."""

    # ─── informes y publicación ───
    @abstractmethod
    def save_daily_report(self, report_date: date, fields: dict[str, Any]) -> None: ...

    @abstractmethod
    def get_daily_report(self, report_date: date) -> dict[str, Any] | None: ...

    @abstractmethod
    def last_published_daily(self, before: date) -> dict[str, Any] | None: ...

    @abstractmethod
    def claim_publication(self, idempotency_key: str, channel: str, target_type: str, target_key: str, payload_sha256: str) -> bool:
        """Registra un envío 'pending'. Devuelve False si ya existe (no reenviar)."""

    @abstractmethod
    def update_publication(self, idempotency_key: str, **fields: Any) -> None: ...

    @abstractmethod
    def get_publication(self, idempotency_key: str) -> dict[str, Any] | None: ...

    # ─── auditoría ───
    @abstractmethod
    def log_llm_call(self, record: dict[str, Any]) -> int: ...

    @abstractmethod
    def save_validation_report(self, target_type: str, target_key: str, attempt: int, report: dict[str, Any]) -> int: ...

    @abstractmethod
    def log_job(self, job_name: str, idempotency_key: str | None, status: str, stats: dict[str, Any] | None = None, error: str | None = None) -> None: ...
