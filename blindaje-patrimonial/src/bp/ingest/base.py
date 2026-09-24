"""Clase base de los conectores (docs/01 §3).

Cada conector: fetch() → RawResponse(s) → parse() → Observations. En modo offline lee fixtures de
tests/fixtures/<connector>/<name> en lugar de llamar a la red (el entorno de desarrollo bloquea estas APIs;
las pruebas en vivo se hacen desde el VPS con `bp smoke`).

Reglas: timeout por petición, reintentos con backoff solo para errores de conexión/5xx/429, nunca eludir
protecciones anti-bot, User-Agent identificado, URLs guardadas SIN claves.
"""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from bp.config import Config
from bp.models import Observation, RawResponse, RunContext, utcnow
from bp.store.base import Store

USER_AGENT = os.environ.get("BP_USER_AGENT", "BlindajePatrimonial/0.1 (+contacto en config)")


class ConnectorError(RuntimeError):
    pass


@dataclass
class ConnectorRun:
    connector: str
    ok: bool
    observations: list[Observation] = field(default_factory=list)
    error: str | None = None
    raw_ids: list[int] = field(default_factory=list)


class Connector(ABC):
    id: str = ""
    source_id: str = ""

    def __init__(self, cfg: Config, fixtures_dir: Path | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self.cfg = cfg
        self.fixtures_dir = fixtures_dir
        self.transport = transport

    # ─── HTTP ───
    def _headers(self) -> dict[str, str]:
        h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        auth = self.cfg.sources.get(self.source_id, {}).get("auth") or {}
        if auth.get("header") and auth.get("env") and os.environ.get(auth["env"]):
            h[auth["header"]] = auth.get("prefix", "") + os.environ[auth["env"]]
        return h

    def get(self, ctx: RunContext, url: str, fixture: str, params: dict | None = None, accept: str | None = None) -> RawResponse:
        if ctx.offline:
            if not self.fixtures_dir:
                raise ConnectorError("modo offline sin directorio de fixtures")
            p = self.fixtures_dir / self.id / fixture
            if not p.exists():
                raise ConnectorError(f"fixture inexistente: {p}")
            return RawResponse(self.source_id, url, 200, p.read_bytes(), None, utcnow(), fixture)
        headers = self._headers()
        if accept:
            headers["Accept"] = accept
        last: Exception | None = None
        with httpx.Client(timeout=20.0, transport=self.transport, headers=headers, follow_redirects=False) as client:
            for attempt in range(3):
                try:
                    r = client.get(url, params=params)
                except httpx.HTTPError as exc:
                    last = exc
                    time.sleep(2 ** attempt)
                    continue
                if r.status_code in (403, 503) and "cf-mitigated" in r.headers:
                    raise ConnectorError("protección anti-bot: fuente marcada DOWN (no se elude)")
                if r.status_code == 429 or r.status_code >= 500:
                    last = ConnectorError(f"HTTP {r.status_code}")
                    time.sleep(int(r.headers.get("retry-after", 2 ** attempt)))
                    continue
                if r.status_code != 200:
                    raise ConnectorError(f"HTTP {r.status_code}: {r.text[:200]}")
                return RawResponse(self.source_id, str(r.request.url.copy_remove_param("x_cg_pro_api_key")), r.status_code,
                                   r.content, r.headers.get("content-type"), utcnow(), fixture)
        raise ConnectorError(f"reintentos agotados: {last}")

    def obs(self, ctx: RunContext, metric_id: str, value, as_of, raw: RawResponse, unit: str | None = None, **kw) -> Observation:
        m = self.cfg.metrics.get(metric_id)
        return Observation(metric_id=metric_id, as_of=as_of, value=value, unit=unit or (m.unit if m else ""),
                           source_id=self.source_id, retrieved_at=ctx.now, source_url=raw.request_url, **kw)

    # ─── contrato ───
    @abstractmethod
    def fetch(self, ctx: RunContext) -> list[RawResponse]: ...

    @abstractmethod
    def parse(self, ctx: RunContext, raws: list[RawResponse]) -> list[Observation]: ...

    def run(self, ctx: RunContext, store: Store) -> ConnectorRun:
        try:
            raws = self.fetch(ctx)
            ids = [store.save_raw(r) for r in raws]
            obs = self.parse(ctx, raws)
            for o in obs:
                if o.raw_payload_id is None and ids:
                    o.raw_payload_id = ids[0]
            store.save_observations(obs)
            return ConnectorRun(self.id, True, obs, raw_ids=ids)
        except Exception as exc:          # un conector caído no tumba la ingesta
            return ConnectorRun(self.id, False, error=f"{type(exc).__name__}: {exc}")
