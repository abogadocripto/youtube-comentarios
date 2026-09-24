"""Almacén en memoria con la misma semántica que PostgresStore (para pruebas y ejecuciones offline)."""

from __future__ import annotations

import copy
from datetime import date, datetime
from typing import Any

from bp.models import Observation, RawResponse, Signal, utcnow
from bp.store.base import Store


class MemoryStore(Store):
    def __init__(self) -> None:
        self.raw: list[RawResponse] = []
        self.observations: list[Observation] = []
        self.signals: list[tuple[int, Signal]] = []
        self.axes: dict[date, dict[str, str]] = {}
        self.daily: dict[date, dict[str, Any]] = {}
        self.publications: dict[str, dict[str, Any]] = {}
        self.llm_calls: list[dict[str, Any]] = []
        self.validation_reports: list[dict[str, Any]] = []
        self.jobs: list[dict[str, Any]] = []

    def save_raw(self, raw: RawResponse) -> int:
        self.raw.append(raw)
        return len(self.raw)

    def save_observations(self, obs: list[Observation]) -> None:
        self.observations.extend(obs)

    def history(self, metric_id: str, limit: int = 400, dimension: str = "", until: datetime | None = None) -> list[Observation]:
        by_asof: dict[datetime, Observation] = {}
        for o in self.observations:
            if o.metric_id != metric_id or o.dimension != dimension or o.status == "rejected" or o.quality == "error":
                continue
            if until is not None and o.retrieved_at > until:
                continue
            cur = by_asof.get(o.as_of)
            if cur is None or o.retrieved_at >= cur.retrieved_at:
                by_asof[o.as_of] = o
        series = [by_asof[k] for k in sorted(by_asof)]
        return series[-limit:]

    def vintage_series(self, metric_id: str, vintage_id: str, dimension: str = "") -> list[Observation]:
        rows = [o for o in self.observations
                if o.metric_id == metric_id and o.vintage_id == vintage_id and o.dimension == dimension and o.status != "rejected"]
        return sorted(rows, key=lambda o: o.as_of)

    def dimensions(self, metric_id: str) -> list[str]:
        return sorted({o.dimension for o in self.observations if o.metric_id == metric_id and o.dimension})

    def save_signals(self, signals: list[Signal], rules_version: int) -> None:
        for s in signals:
            self.signals.append((rules_version, copy.deepcopy(s)))

    def previous_signal(self, metric_id: str, before: datetime) -> Signal | None:
        cands = [s for _, s in self.signals if s.metric_id == metric_id and s.as_of < before]
        return max(cands, key=lambda s: s.as_of) if cands else None

    def save_axis_states(self, report_date: date, axes: list[Any], rules_version: int) -> None:
        self.axes[report_date] = {a.axis: a.color for a in axes}

    def previous_axis_states(self, before: date) -> dict[str, str]:
        days = [d for d in self.axes if d < before]
        return dict(self.axes[max(days)]) if days else {}

    def save_daily_report(self, report_date: date, fields: dict[str, Any]) -> None:
        self.daily.setdefault(report_date, {"report_date": report_date}).update(copy.deepcopy(fields))

    def get_daily_report(self, report_date: date) -> dict[str, Any] | None:
        return copy.deepcopy(self.daily.get(report_date))

    def last_published_daily(self, before: date) -> dict[str, Any] | None:
        days = [d for d, r in self.daily.items() if d < before and r.get("status") in ("published", "corrected")]
        return copy.deepcopy(self.daily[max(days)]) if days else None

    def claim_publication(self, idempotency_key: str, channel: str, target_type: str, target_key: str, payload_sha256: str) -> bool:
        if idempotency_key in self.publications:
            return False
        self.publications[idempotency_key] = {
            "idempotency_key": idempotency_key, "channel": channel, "target_type": target_type,
            "target_key": target_key, "payload_sha256": payload_sha256, "status": "pending",
        }
        return True

    def update_publication(self, idempotency_key: str, **fields: Any) -> None:
        self.publications[idempotency_key].update(fields)

    def get_publication(self, idempotency_key: str) -> dict[str, Any] | None:
        return copy.deepcopy(self.publications.get(idempotency_key))

    def log_llm_call(self, record: dict[str, Any]) -> int:
        self.llm_calls.append(copy.deepcopy(record))
        return len(self.llm_calls)

    def save_validation_report(self, target_type: str, target_key: str, attempt: int, report: dict[str, Any]) -> int:
        self.validation_reports.append({"target_type": target_type, "target_key": target_key, "attempt": attempt, **report})
        return len(self.validation_reports)

    def log_job(self, job_name: str, idempotency_key: str | None, status: str, stats: dict[str, Any] | None = None, error: str | None = None) -> None:
        self.jobs.append({"job_name": job_name, "idempotency_key": idempotency_key, "status": status,
                          "stats": stats or {}, "error": error, "at": utcnow()})
