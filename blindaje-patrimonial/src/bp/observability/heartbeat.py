"""Heartbeats (dead-man switch) para Healthchecks.io u otro servicio compatible (docs/01 §7)."""

from __future__ import annotations

import os

import httpx


def ping(check: str, suffix: str = "") -> None:
    """check = nombre lógico (daily-published, ingest-news…); la URL se lee de HC_<CHECK> en el entorno."""
    url = os.environ.get("HC_" + check.upper().replace("-", "_"))
    if not url:
        return
    try:
        httpx.get(url.rstrip("/") + (f"/{suffix}" if suffix else ""), timeout=5.0)
    except httpx.HTTPError:
        pass            # un fallo del heartbeat nunca debe tumbar el job; la ausencia de ping ya es la alarma
