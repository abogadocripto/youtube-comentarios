"""Publicación en Telegram (docs/09 §3).

- parse_mode=HTML (el renderizador ya escapa los valores dinámicos).
- Idempotencia con publications.idempotency_key: nunca se publica dos veces lo mismo.
- 429 → se espera retry_after y se reintenta; 5xx explícito → backoff (máx. 3); 400 → error de formato.
- Timeout de red DESPUÉS de enviar (ambiguo) → NO se reintenta: estado 'unknown' y aviso al editor.
  La Bot API no tiene clave de idempotencia y un bot no puede leer el historial del canal.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from bp.store.base import Store

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(RuntimeError):
    pass


class AmbiguousSend(TelegramError):
    """No se sabe si el mensaje llegó a publicarse."""


@dataclass
class PublishResult:
    status: str               # sent | skipped_duplicate | unknown | failed
    message_id: int | None = None
    error: str | None = None


class TelegramClient:
    def __init__(self, token: str | None = None, transport: httpx.BaseTransport | None = None, timeout: float = 20.0,
                 sleep=time.sleep) -> None:
        self.token = token or os.environ.get("TELEGRAM_PUBLISHER_TOKEN", "")
        self.http = httpx.Client(timeout=timeout, transport=transport)
        self.sleep = sleep

    def call(self, method: str, payload: dict[str, Any], max_attempts: int = 4) -> dict[str, Any]:
        url = API.format(token=self.token, method=method)
        for attempt in range(1, max_attempts + 1):
            try:
                r = self.http.post(url, json=payload)
            except httpx.ConnectError as exc:          # no se llegó a enviar: reintento seguro
                if attempt == max_attempts:
                    raise TelegramError(f"conexión fallida: {exc}") from exc
                self.sleep(2 ** attempt)
                continue
            except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError) as exc:
                raise AmbiguousSend(f"{type(exc).__name__} tras enviar la petición") from exc
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code == 200 and data.get("ok"):
                return data["result"]
            if r.status_code == 429:
                wait = int((data.get("parameters") or {}).get("retry_after", 5))
                self.sleep(wait)
                continue
            if r.status_code >= 500 and attempt < max_attempts:
                self.sleep(2 ** attempt)
                continue
            raise TelegramError(f"{r.status_code}: {data.get('description', r.text[:200])}")
        raise TelegramError("reintentos agotados")

    def send_message(self, chat_id: str, html: str, disable_notification: bool = False) -> dict[str, Any]:
        return self.call("sendMessage", {"chat_id": chat_id, "text": html, "parse_mode": "HTML",
                                         "link_preview_options": {"is_disabled": True},
                                         "disable_notification": disable_notification, "protect_content": False})

    def edit_message(self, chat_id: str, message_id: int, html: str) -> dict[str, Any]:
        return self.call("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": html, "parse_mode": "HTML",
                                             "link_preview_options": {"is_disabled": True}})


def publish_once(store: Store, client: TelegramClient, *, channel: str, chat_id: str, target_type: str, target_key: str,
                 html: str, disable_notification: bool = False) -> PublishResult:
    """Publica una sola vez por (canal, tipo, clave)."""
    key = f"{channel}:{target_type}:{target_key}"
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    if not store.claim_publication(key, channel, target_type, target_key, digest):
        prev = store.get_publication(key) or {}
        if prev.get("status") != "failed":          # sent / pending / unknown → no se reenvía nunca automáticamente
            return PublishResult("skipped_duplicate", prev.get("external_id"), f"ya existe ({prev.get('status')})")
        store.update_publication(key, status="pending", payload_sha256=digest, error=None)   # un fallo explícito sí se reintenta
    try:
        res = client.send_message(chat_id, html, disable_notification=disable_notification)
    except AmbiguousSend as exc:
        store.update_publication(key, status="unknown", error=str(exc))
        return PublishResult("unknown", None, str(exc))
    except TelegramError as exc:
        store.update_publication(key, status="failed", error=str(exc))
        return PublishResult("failed", None, str(exc))
    store.update_publication(key, status="sent", external_id=res.get("message_id"))
    return PublishResult("sent", res.get("message_id"))
