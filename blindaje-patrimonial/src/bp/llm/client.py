"""Cliente de Claude (docs/06 §2).

- SDK oficial `anthropic`, API beta para poder combinar salida estructurada y fallback del servidor.
- output_config.format con JSON Schema estricto generado desde los modelos Pydantic (bp.llm.models).
- thinking adaptativo; esfuerzo por tipo de llamada (config/llm.yaml).
- fallbacks="default" (beta server-side-fallback-2026-07-01): si el modelo rechaza por sus clasificadores,
  la API reintenta en otro modelo dentro de la misma llamada. Se registra el modelo que respondió.
- Se comprueba stop_reason == "refusal" antes de leer el contenido.
- Sin herramientas: el modelo no puede actuar ni salir a internet.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from jinja2 import Environment, StrictUndefined
from pydantic import BaseModel, ValidationError

from bp.config import Config
from bp.llm.models import strict_schema
from bp.store.base import Store

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class LLMRefusal(LLMError):
    pass


@dataclass
class LLMResult:
    parsed: BaseModel
    raw_text: str
    served_model: str
    stop_reason: str
    usage: dict[str, int]
    cost_usd: float
    llm_call_id: int | None


class LLMBackend(Protocol):
    def complete(self, *, system: str, user: str, schema: dict, call: str) -> dict[str, Any]:
        """Devuelve {'text', 'model', 'stop_reason', 'usage'}."""


def load_prompt(cfg: Config, name: str) -> tuple[str, str]:
    """(texto sin la cabecera de comentario, versión) de prompts/<name>."""
    text = cfg.prompt_path(name).read_text(encoding="utf-8")
    version = "unknown"
    if text.startswith("<!--"):
        header, _, text = text.partition("-->")
        for part in header.split("·"):
            if "version:" in part:
                version = part.split("version:")[1].strip()
        text = text.lstrip("\n")
    return text, version


def render_user_prompt(cfg: Config, name: str, **kwargs: Any) -> str:
    tpl, _ = load_prompt(cfg, name)
    return Environment(undefined=StrictUndefined, autoescape=False).from_string(tpl).render(**kwargs)


class AnthropicBackend:
    """Backend real: SDK de Anthropic."""

    def __init__(self, cfg: Config) -> None:
        import anthropic  # importación diferida: las pruebas no requieren la clave

        self.cfg = cfg
        d = cfg.llm["defaults"]
        self.client = anthropic.Anthropic(timeout=float(d["timeout_s"]), max_retries=int(d["max_retries"]))

    def complete(self, *, system: str, user: str, schema: dict, call: str) -> dict[str, Any]:
        d = self.cfg.llm["defaults"]
        c = self.cfg.llm["calls"][call]
        kwargs: dict[str, Any] = dict(
            model=c.get("model", d["model"]),
            max_tokens=int(c["max_tokens"]),
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            thinking=d["thinking"],
            output_config={"effort": c.get("effort", "high"), "format": {"type": "json_schema", "schema": schema}},
        )
        if d.get("fallbacks"):
            kwargs["betas"] = [d["fallback_beta"]]
            kwargs["extra_body"] = {"fallbacks": d["fallbacks"]}
        if c.get("stream"):
            with self.client.beta.messages.stream(**kwargs) as stream:
                resp = stream.get_final_message()
        else:
            resp = self.client.beta.messages.create(**kwargs)
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        u = resp.usage
        usage = {"input_tokens": getattr(u, "input_tokens", 0) or 0, "output_tokens": getattr(u, "output_tokens", 0) or 0,
                 "cache_read_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
                 "cache_write_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0}
        return {"text": text, "model": resp.model, "stop_reason": resp.stop_reason, "usage": usage,
                "stop_details": getattr(resp, "stop_details", None)}


class StaticBackend:
    """Backend para pruebas y ensayos: devuelve una respuesta fija (o una cola de respuestas)."""

    def __init__(self, responses: list[dict | str | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def complete(self, *, system: str, user: str, schema: dict, call: str) -> dict[str, Any]:
        self.calls.append({"system": system, "user": user, "call": call})
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        text = r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
        return {"text": text, "model": "static", "stop_reason": "end_turn",
                "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0}}


def default_backend(cfg: Config) -> LLMBackend:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise LLMError("Sin credenciales de Anthropic (ANTHROPIC_API_KEY)")
    return AnthropicBackend(cfg)


def _cost(cfg: Config, model: str, usage: dict[str, int]) -> float:
    p = cfg.llm.get("pricing", {}).get(model) or cfg.llm.get("pricing", {}).get(cfg.llm["defaults"]["model"], {})
    if not p:
        return 0.0
    return round((usage["input_tokens"] * p["input"] + usage["output_tokens"] * p["output"]
                  + usage.get("cache_read_tokens", 0) * p.get("cache_read", 0)) / 1e6, 5)


def call_structured(cfg: Config, store: Store | None, backend: LLMBackend, *, call: str, system: str, user: str,
                    model_cls: type[T], prompt_version: str) -> LLMResult:
    """Una llamada con salida estructurada. Lanza LLMRefusal / LLMError. Registra la llamada en llm_calls."""
    schema = strict_schema(model_cls)
    t0 = time.monotonic()
    record: dict[str, Any] = {"purpose": call, "model": cfg.llm["calls"][call].get("model", cfg.llm["defaults"]["model"]),
                              "prompt_version": prompt_version, "request": {"system_chars": len(system), "user": user}}
    try:
        r = backend.complete(system=system, user=user, schema=schema, call=call)
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        if store:
            store.log_llm_call(record)
        raise LLMError(str(exc)) from exc
    latency = int((time.monotonic() - t0) * 1000)
    record.update({"served_model": r["model"], "stop_reason": r["stop_reason"], "response": {"text": r["text"]},
                   "latency_ms": latency, **{k: v for k, v in r["usage"].items()}})
    record["cost_usd"] = _cost(cfg, r["model"], r["usage"])
    if r["stop_reason"] == "refusal":
        record["error"] = "refusal"
        call_id = store.log_llm_call(record) if store else None
        raise LLMRefusal(f"El modelo rechazó la petición (llm_call_id={call_id})")
    if r["stop_reason"] == "max_tokens":
        record["error"] = "max_tokens"
        if store:
            store.log_llm_call(record)
        raise LLMError("Respuesta truncada (max_tokens)")
    try:
        parsed = model_cls.model_validate_json(r["text"])
    except ValidationError as exc:
        record["error"] = f"schema: {exc.errors()[:3]}"
        if store:
            store.log_llm_call(record)
        raise LLMError(f"La salida no cumple el esquema: {exc.errors()[:3]}") from exc
    call_id = store.log_llm_call(record) if store else None
    return LLMResult(parsed=parsed, raw_text=r["text"], served_model=r["model"], stop_reason=r["stop_reason"],
                     usage=r["usage"], cost_usd=record["cost_usd"], llm_call_id=call_id)
