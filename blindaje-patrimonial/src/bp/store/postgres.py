"""Almacén PostgreSQL 16 sobre schema/schema.sql (producción). Misma semántica que MemoryStore.

- Observaciones append-only: nunca se sobrescriben; una revisión es una fila nueva con otro vintage.
- Cada método usa su propia transacción corta; un cerrojo serializa el uso de la conexión, porque la ingesta
  ejecuta conectores en paralelo (hilos) sobre el mismo almacén.
- `init_schema()` aplica schema.sql si la base está vacía; `sync_catalog()` vuelca sources.yaml y metrics.yaml
  (la YAML manda) en `sources` y `metric_definitions`.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from bp.config import Config
from bp.models import AxisState, Observation, RawResponse, Signal
from bp.store.base import LockBusy, Store

DAILY_COLUMNS = {
    "status", "fact_sheet", "selected_metrics", "rules_version", "prompt_version", "model", "llm_output",
    "validation_report_id", "rendered_telegram", "rendered_plain", "lectura_rendered", "vigilar_rendered",
    "fallback_reason", "telegram_message_id", "published_at",
}
JSON_DAILY = {"fact_sheet", "llm_output"}
JOB_STATUS = {"ok": "succeeded", "partial": "succeeded", "validated": "succeeded", "fallback": "succeeded",
              "sent": "succeeded", "skipped_duplicate": "skipped", "withheld": "failed", "failed": "failed",
              "unknown": "failed", "running": "running", "skipped": "skipped"}
LLM_COLUMNS = ("purpose", "model", "served_model", "prompt_version", "request", "response", "stop_reason", "input_tokens",
               "output_tokens", "cache_read_tokens", "cache_write_tokens", "cost_usd", "latency_ms", "batch_id", "error")


def _num(v: Any) -> Any:
    return float(v) if isinstance(v, Decimal) else v


class PostgresStore(Store):
    def __init__(self, dsn: str) -> None:
        self.conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
        self._lock = threading.RLock()

    def close(self) -> None:
        self.conn.close()

    def _exec(self, sql: str, params: Any = None) -> list[dict[str, Any]]:
        with self._lock, self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else []

    @contextmanager
    def lock(self, name: str) -> Iterator[None]:
        """pg_try_advisory_lock por familia de jobs: si otro proceso lo tiene, LockBusy (no se espera ni se duplica)."""
        key = int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big", signed=True)
        if not self._exec("SELECT pg_try_advisory_lock(%s) AS ok", (key,))[0]["ok"]:
            raise LockBusy(name)
        try:
            yield
        finally:
            self._exec("SELECT pg_advisory_unlock(%s)", (key,))

    # ─── esquema y catálogos ───
    def init_schema(self, cfg: Config) -> bool:
        """Aplica schema.sql si la base está vacía. Devuelve True si lo aplicó."""
        with self._lock:
            exists = self._exec("SELECT to_regclass('public.metric_observations') AS t")[0]["t"]
            if exists:
                return False
            sql = (cfg.root / "schema" / "schema.sql").read_text("utf-8")
            with self.conn.transaction(), self.conn.cursor() as cur:
                cur.execute(sql)
            return True

    def sync_catalog(self, cfg: Config) -> None:
        with self._lock, self.conn.transaction(), self.conn.cursor() as cur:
            for sid, s in cfg.sources.items():
                cur.execute(
                    """INSERT INTO sources (id, name, kind, base_url, tier, licence_status, attribution_text, attribution_inline,
                                            llm_input_allowed, notes)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, kind=EXCLUDED.kind, base_url=EXCLUDED.base_url,
                           tier=EXCLUDED.tier, licence_status=EXCLUDED.licence_status, attribution_text=EXCLUDED.attribution_text,
                           attribution_inline=EXCLUDED.attribution_inline, llm_input_allowed=EXCLUDED.llm_input_allowed,
                           notes=EXCLUDED.notes, updated_at=now()""",
                    (sid, s.get("name", sid), s.get("kind", "api"), s.get("base_url"), s.get("tier"), s["licence"],
                     s.get("attribution_text"), bool(s.get("attribution_inline", False)), bool(s.get("llm_input_allowed", False)),
                     s.get("notes")))
            for mid, m in cfg.metrics.items():
                r = m.raw
                cur.execute(
                    """INSERT INTO metric_definitions (metric_id, label_es, family, axis, unit, fmt, freq, as_of_semantics,
                                                       max_staleness, layer, mvp, licence_status, definition)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::interval,%s,%s,%s,%s)
                       ON CONFLICT (metric_id) DO UPDATE SET label_es=EXCLUDED.label_es, family=EXCLUDED.family,
                           axis=EXCLUDED.axis, unit=EXCLUDED.unit, fmt=EXCLUDED.fmt, freq=EXCLUDED.freq,
                           as_of_semantics=EXCLUDED.as_of_semantics, max_staleness=EXCLUDED.max_staleness, layer=EXCLUDED.layer,
                           mvp=EXCLUDED.mvp, licence_status=EXCLUDED.licence_status, definition=EXCLUDED.definition,
                           updated_at=now()""",
                    (mid, r["label_es"], r["family"], r["axis"], r["unit"], r["fmt"], str(r["freq"]), str(r["as_of"]),
                     r["max_staleness"], r["layer"], bool(r["mvp"]), r["licence"], Jsonb(_jsonable(r))))

    # ─── datos ───
    def save_raw(self, raw: RawResponse) -> int:
        rows = self._exec(
            """INSERT INTO raw_payloads (source_id, request_url, http_status, fetched_at, content_type, sha256, body)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (raw.source_id, raw.request_url, raw.status, raw.fetched_at, raw.content_type,
             hashlib.sha256(raw.body).hexdigest(), raw.body))
        return rows[0]["id"]

    def save_observations(self, obs: list[Observation]) -> None:
        if not obs:
            return
        params = []
        for o in obs:
            v = o.value
            vnum = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
            vtext = v if isinstance(v, str) else None
            vjson = Jsonb(v) if isinstance(v, (dict, list)) else None
            if vnum is None and vtext is None and vjson is None:
                continue                                  # el esquema exige un valor; un None no es una observación
            params.append((o.metric_id, o.dimension, o.as_of, o.as_of_label, vnum, vtext, vjson, o.unit, o.source_id, o.source_url,
                           o.retrieved_at, o.raw_payload_id, o.method, o.vintage_id, o.status, o.quality,
                           Jsonb(o.quality_notes) if o.quality_notes else None, o.secondary_value, o.deviation_pct))
        with self._lock, self.conn.transaction(), self.conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO metric_observations (metric_id, dimension, as_of, as_of_label, value_num, value_text, value_json, unit,
                       source_id, source_url, retrieved_at, raw_payload_id, method, vintage_id, status, quality, quality_notes,
                       secondary_value, deviation_pct)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (metric_id, dimension, as_of, source_id, vintage_id) DO NOTHING""", params)

    @staticmethod
    def _obs(r: dict[str, Any]) -> Observation:
        value = _num(r["value_num"]) if r["value_num"] is not None else r["value_text"] if r["value_text"] is not None else r["value_json"]
        return Observation(metric_id=r["metric_id"], as_of=r["as_of"], value=value, unit=r["unit"], source_id=r["source_id"],
                           retrieved_at=r["retrieved_at"], method=r["method"], source_url=r["source_url"], as_of_label=r["as_of_label"],
                           dimension=r["dimension"], status=r["status"], quality=r["quality"], quality_notes=r["quality_notes"] or {},
                           secondary_value=_num(r["secondary_value"]), deviation_pct=_num(r["deviation_pct"]),
                           vintage_id=str(r["vintage_id"]), raw_payload_id=r["raw_payload_id"])

    def history(self, metric_id: str, limit: int = 400, dimension: str = "", until: datetime | None = None) -> list[Observation]:
        rows = self._exec(
            """SELECT * FROM (
                   SELECT DISTINCT ON (as_of) * FROM metric_observations
                   WHERE metric_id = %(m)s AND dimension = %(d)s AND status <> 'rejected' AND quality <> 'error'
                     AND (%(u)s::timestamptz IS NULL OR retrieved_at <= %(u)s::timestamptz)
                   ORDER BY as_of, retrieved_at DESC, id DESC) latest
               ORDER BY as_of DESC LIMIT %(n)s""",
            {"m": metric_id, "d": dimension, "u": until, "n": limit})
        return [self._obs(r) for r in reversed(rows)]

    def vintage_series(self, metric_id: str, vintage_id: str, dimension: str = "") -> list[Observation]:
        rows = self._exec(
            """SELECT * FROM metric_observations WHERE metric_id=%s AND vintage_id=%s AND dimension=%s AND status <> 'rejected'
               ORDER BY as_of""", (metric_id, vintage_id, dimension))
        return [self._obs(r) for r in rows]

    def dimensions(self, metric_id: str) -> list[str]:
        rows = self._exec("SELECT DISTINCT dimension FROM metric_observations WHERE metric_id=%s AND dimension <> '' ORDER BY 1",
                          (metric_id,))
        return [r["dimension"] for r in rows]

    # ─── análisis ───
    def save_signals(self, signals: list[Signal], rules_version: int) -> None:
        with self._lock, self.conn.transaction(), self.conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO derived_signals (metric_id, as_of, rules_version, stats, state_code, state_label_es, axis, color,
                                                salience, hints, caveats)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (metric_id, as_of, rules_version) DO UPDATE SET computed_at=now(), stats=EXCLUDED.stats,
                       state_code=EXCLUDED.state_code, state_label_es=EXCLUDED.state_label_es, axis=EXCLUDED.axis,
                       color=EXCLUDED.color, salience=EXCLUDED.salience, hints=EXCLUDED.hints, caveats=EXCLUDED.caveats""",
                [(s.metric_id, s.as_of, rules_version, Jsonb(_jsonable(s.stats)), s.state_code, s.state_label_es, s.axis,
                  s.color or "none", round(min(max(s.salience, 0.0), 9.999), 3), Jsonb(_jsonable(s.hints)), Jsonb(s.caveats))
                 for s in signals])

    def previous_signal(self, metric_id: str, before: datetime) -> Signal | None:
        rows = self._exec(
            """SELECT * FROM derived_signals WHERE metric_id=%s AND as_of < %s ORDER BY as_of DESC, computed_at DESC LIMIT 1""",
            (metric_id, before))
        if not rows:
            return None
        r = rows[0]
        return Signal(metric_id=r["metric_id"], as_of=r["as_of"], stats=r["stats"], state_code=r["state_code"],
                      state_label_es=r["state_label_es"], axis=r["axis"], color=r["color"], salience=float(r["salience"] or 0),
                      hints=r["hints"] or [], caveats=r["caveats"] or [])

    def save_axis_states(self, report_date: date, axes: list[AxisState], rules_version: int) -> None:
        with self._lock, self.conn.transaction(), self.conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO axis_states (report_date, axis, color, label_es, inputs, rules_version) VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (report_date, axis, rules_version) DO UPDATE SET color=EXCLUDED.color, label_es=EXCLUDED.label_es,
                       inputs=EXCLUDED.inputs""",
                [(report_date, a.axis, a.color, a.label_es, Jsonb({"driver_fact_ids": a.driver_fact_ids}), rules_version)
                 for a in axes])

    def previous_axis_states(self, before: date) -> dict[str, str]:
        rows = self._exec(
            """SELECT axis, color FROM axis_states
               WHERE report_date = (SELECT max(report_date) FROM axis_states WHERE report_date < %s)""", (before,))
        return {r["axis"]: r["color"] for r in rows}

    # ─── informes y publicación ───
    def save_daily_report(self, report_date: date, fields: dict[str, Any]) -> None:
        unknown = set(fields) - DAILY_COLUMNS
        if unknown:
            raise ValueError(f"daily_reports: columnas desconocidas {sorted(unknown)}")
        cols = list(fields)
        vals = [Jsonb(_jsonable(fields[c])) if c in JSON_DAILY and fields[c] is not None else fields[c] for c in cols]
        sets = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols)
        self._exec(
            f"""INSERT INTO daily_reports (report_date, {", ".join(cols)}) VALUES (%s, {", ".join(["%s"] * len(cols))})
                ON CONFLICT (report_date) DO UPDATE SET {sets}, updated_at=now()""",
            [report_date, *vals])

    def get_daily_report(self, report_date: date) -> dict[str, Any] | None:
        rows = self._exec("SELECT * FROM daily_reports WHERE report_date=%s", (report_date,))
        return rows[0] if rows else None

    def last_published_daily(self, before: date) -> dict[str, Any] | None:
        rows = self._exec(
            """SELECT * FROM daily_reports WHERE report_date < %s AND status IN ('published','corrected')
               ORDER BY report_date DESC LIMIT 1""", (before,))
        return rows[0] if rows else None

    def claim_publication(self, idempotency_key: str, channel: str, target_type: str, target_key: str, payload_sha256: str) -> bool:
        rows = self._exec(
            """INSERT INTO publications (channel, target_type, target_key, payload_sha256, status, idempotency_key)
               VALUES (%s,%s,%s,%s,'pending',%s) ON CONFLICT (idempotency_key) DO NOTHING RETURNING id""",
            (channel, target_type, target_key, payload_sha256, idempotency_key))
        return bool(rows)

    def update_publication(self, idempotency_key: str, **fields: Any) -> None:
        allowed = {"status", "payload_sha256", "error", "external_id"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"publications: campos desconocidos {sorted(unknown)}")
        if "external_id" in fields and fields["external_id"] is not None:
            fields["external_id"] = str(fields["external_id"])
        sets = [f"{k}=%s" for k in fields]
        if fields.get("status") == "sent":
            sets.append("sent_at=now()")
        self._exec(f"UPDATE publications SET {', '.join(sets)} WHERE idempotency_key=%s", [*fields.values(), idempotency_key])

    def get_publication(self, idempotency_key: str) -> dict[str, Any] | None:
        rows = self._exec("SELECT * FROM publications WHERE idempotency_key=%s", (idempotency_key,))
        if not rows:
            return None
        r = rows[0]
        if r.get("external_id") and str(r["external_id"]).isdigit():
            r["external_id"] = int(r["external_id"])
        return r

    # ─── auditoría ───
    def log_llm_call(self, record: dict[str, Any]) -> int:
        data = {k: record.get(k) for k in LLM_COLUMNS if k in record}
        data.setdefault("request", {})
        for k in ("request", "response"):
            if data.get(k) is not None:
                data[k] = Jsonb(_jsonable(data[k]))
        cols = list(data)
        rows = self._exec(f"INSERT INTO llm_calls ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) RETURNING id",
                          [data[c] for c in cols])
        return rows[0]["id"]

    def save_validation_report(self, target_type: str, target_key: str, attempt: int, report: dict[str, Any]) -> int:
        rows = self._exec(
            """INSERT INTO validation_reports (target_type, target_key, attempt, passed, blocking, warnings, checks)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (target_type, target_key, attempt, bool(report.get("passed")), int(report.get("blocking", 0)),
             int(report.get("warnings", 0)), Jsonb(_jsonable(report.get("checks", [])))))
        return rows[0]["id"]

    def log_job(self, job_name: str, idempotency_key: str | None, status: str, stats: dict[str, Any] | None = None,
                error: str | None = None) -> None:
        st = dict(stats or {})
        st["outcome"] = status
        self._exec(
            """INSERT INTO job_runs (job_name, status, idempotency_key, stats, error, finished_at)
               VALUES (%s,%s,%s,%s,%s,now())
               ON CONFLICT (idempotency_key) DO UPDATE SET status=EXCLUDED.status, stats=EXCLUDED.stats, error=EXCLUDED.error,
                   attempt=job_runs.attempt + 1, started_at=now(), finished_at=now()""",
            (job_name, JOB_STATUS.get(status, "failed"), idempotency_key, Jsonb(_jsonable(st)), error))


def _jsonable(x: Any) -> Any:
    """Convierte fechas y decimales para jsonb."""
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (datetime, date)):
        return x.isoformat()
    if isinstance(x, Decimal):
        return float(x)
    return x
