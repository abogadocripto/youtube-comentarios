"""Publicación idempotente en Telegram (docs/09 §5): nunca duplicar, nunca reintentar un envío ambiguo."""

import httpx

from bp.distribution.telegram import TelegramClient, publish_once
from bp.store.memory import MemoryStore


def client_with(handler) -> TelegramClient:
    return TelegramClient(token="TEST", transport=httpx.MockTransport(handler), sleep=lambda s: None)


def ok(message_id=101):
    return httpx.Response(200, json={"ok": True, "result": {"message_id": message_id}})


def test_sends_once_and_skips_duplicates():
    calls = []

    def handler(req):
        calls.append(req)
        return ok()

    store, c = MemoryStore(), client_with(handler)
    r1 = publish_once(store, c, channel="tg", chat_id="@x", target_type="daily", target_key="2026-09-24", html="<b>hola</b>")
    r2 = publish_once(store, c, channel="tg", chat_id="@x", target_type="daily", target_key="2026-09-24", html="<b>hola</b>")
    assert (r1.status, r1.message_id) == ("sent", 101)
    assert r2.status == "skipped_duplicate" and len(calls) == 1


def test_payload_uses_html_and_no_link_preview():
    seen = {}

    def handler(req):
        import json
        seen.update(json.loads(req.content))
        return ok()

    publish_once(MemoryStore(), client_with(handler), channel="tg", chat_id="@x", target_type="daily", target_key="k", html="<b>a</b>")
    assert seen["parse_mode"] == "HTML" and seen["chat_id"] == "@x"
    assert seen.get("link_preview_options", {}).get("is_disabled") is True or seen.get("disable_web_page_preview") is True


def test_ambiguous_timeout_is_never_retried():
    calls = []

    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout("timeout", request=req)

    store, c = MemoryStore(), client_with(handler)
    r1 = publish_once(store, c, channel="tg", chat_id="@x", target_type="daily", target_key="k", html="a")
    r2 = publish_once(store, c, channel="tg", chat_id="@x", target_type="daily", target_key="k", html="a")
    assert r1.status == "unknown" and r2.status == "skipped_duplicate"
    assert len(calls) == 1, "un timeout tras enviar puede haber publicado: no se reenvía automáticamente"


def test_connect_error_is_retried_safely():
    attempts = {"n": 0}

    def handler(req):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise httpx.ConnectError("down", request=req)
        return ok(7)

    r = publish_once(MemoryStore(), client_with(handler), channel="tg", chat_id="@x", target_type="daily", target_key="k", html="a")
    assert (r.status, r.message_id, attempts["n"]) == ("sent", 7, 3)


def test_rate_limit_honours_retry_after():
    waits, n = [], {"i": 0}

    def handler(req):
        n["i"] += 1
        if n["i"] == 1:
            return httpx.Response(429, json={"ok": False, "description": "Too Many Requests", "parameters": {"retry_after": 3}})
        return ok()

    c = TelegramClient(token="T", transport=httpx.MockTransport(handler), sleep=waits.append)
    assert publish_once(MemoryStore(), c, channel="tg", chat_id="@x", target_type="daily", target_key="k", html="a").status == "sent"
    assert waits == [3]


def test_explicit_failure_can_be_retried_later():
    responses = [httpx.Response(400, json={"ok": False, "description": "Bad Request: can't parse entities"}), ok(9)]

    def handler(req):
        return responses.pop(0)

    store, c = MemoryStore(), client_with(handler)
    r1 = publish_once(store, c, channel="tg", chat_id="@x", target_type="daily", target_key="k", html="a")
    r2 = publish_once(store, c, channel="tg", chat_id="@x", target_type="daily", target_key="k", html="a")
    assert r1.status == "failed" and (r2.status, r2.message_id) == ("sent", 9)
