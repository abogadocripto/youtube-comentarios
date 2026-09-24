"""Flujo del Daily (docs/01 §4.2): derivar → analizar → seleccionar → LLM → validar → renderizar → publicar.

Garantías:
- Si faltan los datos núcleo (precio fresco) → no se publica (status 'withheld') y se avisa.
- Si el LLM falla o no supera la validación tras 1 reintento → lectura por plantillas (status 'fallback').
- La publicación es un job aparte e idempotente; después de las 10:30 no publica sin confirmación humana.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

from bp.analysis import derive, salience, watch
from bp.analysis.rules import analyze
from bp.calendar.events import build_events
from bp.config import Config
from bp.distribution.telegram import PublishResult, TelegramClient, publish_once
from bp.editorial import fallback_reading
from bp.editorial.markers import fill, index_fact_sheet
from bp.editorial.render import DailyRenderer, RenderedDaily
from bp.llm.client import LLMBackend, LLMError, call_structured, load_prompt, render_user_prompt
from bp.llm.models import DailyOutput
from bp.models import MADRID, RunContext
from bp.schemas import validate_instance
from bp.select.fact_sheet import build as build_fact_sheet
from bp.store.base import Store
from bp.validation.deterministic import precheck_refs, validate_daily
from bp.validation.verifier import daily_fragments, verify

CORE_REQUIRED = ["btc_usd"]


@dataclass
class DailyBuildResult:
    status: str                                   # validated | fallback | withheld
    fact_sheet: dict[str, Any] | None = None
    output: DailyOutput | None = None
    rendered: RenderedDaily | None = None
    origin: str | None = None                     # llm | template
    reports: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None
    excluded: dict[str, str] = field(default_factory=dict)


def _core_ok(cfg: Config, fact_sheet: dict[str, Any]) -> tuple[bool, str]:
    facts = {f["id"]: f for f in fact_sheet["facts"]}
    for mid in CORE_REQUIRED:
        f = facts.get(mid)
        if not f:
            return False, f"falta el dato núcleo {mid}"
        if f["freshness"] != "fresh":
            return False, f"el dato núcleo {mid} está obsoleto ({f['as_of']})"
    return True, ""


def build_daily(ctx: RunContext, cfg: Config, store: Store, backend: LLMBackend | None,
                verify_with_llm: bool = True) -> DailyBuildResult:
    derive.derive_all(ctx, cfg, store)
    res = analyze(ctx, cfg, store)
    events = build_events(cfg, ctx.report_date - timedelta(days=1), ctx.report_date + timedelta(days=10))
    events_today = [e for e in events if e.scheduled_at.astimezone(MADRID).date() == ctx.report_date]
    prev = store.last_published_daily(ctx.report_date)
    last_facts = {f["id"]: f["as_of"] for f in (prev or {}).get("fact_sheet", {}).get("facts", []) if f.get("selected")}
    salience.compute(ctx, cfg, store, res, events_today, last_facts)
    cands = watch.candidates(ctx, cfg, res, events)
    chosen = watch.select(ctx, cfg, cands)
    _, prompt_version = load_prompt(cfg, "daily.system.md")
    fsb = build_fact_sheet(ctx, cfg, store, res, cands, chosen, prompt_version)
    fs = fsb.fact_sheet
    result = DailyBuildResult(status="withheld", fact_sheet=fs, excluded=fsb.excluded)

    schema_errors = validate_instance(fs, "daily_input.schema.json", cfg.root)
    if schema_errors:
        result.reason = "I-SCHEMA: " + "; ".join(schema_errors[:5])
        store.save_daily_report(ctx.report_date, {"status": "withheld", "fact_sheet": fs, "fallback_reason": result.reason})
        return result
    ok, why = _core_ok(cfg, fs)
    if not ok:
        result.reason = why
        store.save_daily_report(ctx.report_date, {"status": "withheld", "fact_sheet": fs, "fallback_reason": why})
        return result

    renderer = DailyRenderer(cfg, fs, fsb.blocks)
    facts, hints = index_fact_sheet(fs)
    previous_lectura = (prev or {}).get("lectura_rendered")
    feedback = None
    system, _ = load_prompt(cfg, "daily.system.md")
    if backend is not None:
        for attempt in (1, 2):
            try:
                user = render_user_prompt(cfg, "daily.user.md", meta=fs["meta"],
                                          fact_sheet_json=json.dumps(fs, ensure_ascii=False, indent=1),
                                          validation_feedback=feedback)
                llm = call_structured(cfg, store, backend, call="daily", system=system, user=user,
                                      model_cls=DailyOutput, prompt_version=prompt_version)
                out: DailyOutput = llm.parsed  # type: ignore[assignment]
                pre = precheck_refs(fs, out)
                if not pre.passed:                       # no se puede renderizar: se reintenta con el motivo
                    result.reports.append(pre.to_dict())
                    store.save_validation_report("daily", ctx.report_date.isoformat(), attempt, pre.to_dict())
                    feedback = pre.feedback()
                    continue
                rendered = renderer.render(ctx, out, origin="llm")
                rep = validate_daily(cfg, fs, out, rendered, origin="llm", previous_lectura=previous_lectura,
                                     allow_placeholders=ctx.offline)
                ver_fb = ""
                if rep.passed and verify_with_llm:
                    frags = daily_fragments(out, lambda t: fill(t, facts, hints))
                    approved, vout, ver_fb = verify(cfg, store, backend, "daily_verify", fs, frags)
                    rep.add("VERIFIER", "B", approved, "verificador", vout.summary if not approved else "")
                result.reports.append(rep.to_dict())
                store.save_validation_report("daily", ctx.report_date.isoformat(), attempt, rep.to_dict())
                if rep.passed:
                    result.status, result.output, result.rendered, result.origin = "validated", out, rendered, "llm"
                    break
                feedback = rep.feedback() + ("\n" + ver_fb if ver_fb else "")
            except LLMError as exc:
                result.reports.append({"passed": False, "error": str(exc), "attempt": attempt})
                feedback = None
                if "rechaz" in str(exc):
                    break                                # un rechazo no se arregla reintentando igual
    if result.status != "validated":
        out = fallback_reading.build(fs)
        rendered = renderer.render(ctx, out, origin="template")
        rep = validate_daily(cfg, fs, out, rendered, origin="template", previous_lectura=previous_lectura,
                             allow_placeholders=ctx.offline)
        result.reports.append(rep.to_dict())
        store.save_validation_report("daily", ctx.report_date.isoformat(), 99, rep.to_dict())
        if rep.passed:
            result.status, result.output, result.rendered, result.origin = "fallback", out, rendered, "template"
            result.reason = result.reason or ("LLM no disponible" if backend is None else "el LLM no superó la validación")
        else:
            result.status, result.reason = "withheld", "la lectura de respaldo no superó la validación: " + rep.feedback()
    store.save_daily_report(ctx.report_date, {
        "status": result.status, "fact_sheet": fs, "selected_metrics": sorted(f["id"] for f in fs["facts"] if f["selected"]),
        "rules_version": cfg.rules["rules_version"], "prompt_version": prompt_version,
        "model": cfg.llm["defaults"]["model"] if result.origin == "llm" else None,
        "llm_output": result.output.model_dump() if result.output else None,
        "rendered_telegram": result.rendered.html if result.rendered else None,
        "rendered_plain": result.rendered.plain if result.rendered else None,
        "lectura_rendered": result.rendered.lectura_rendered if result.rendered else None,
        "vigilar_rendered": result.rendered.vigilar_rendered if result.rendered else None,
        "fallback_reason": result.reason,
    })
    return result


PUBLISH_DEADLINE = time(10, 30)


def publish_daily(ctx: RunContext, cfg: Config, store: Store, client: TelegramClient, chat_id: str,
                  force: bool = False) -> PublishResult:
    rep = store.get_daily_report(ctx.report_date)
    if rep and rep.get("status") in ("published", "corrected"):
        return PublishResult("skipped_duplicate", rep.get("telegram_message_id"), "ya publicado")
    if not rep or rep.get("status") not in ("validated", "fallback"):
        return PublishResult("failed", None, f"no hay borrador publicable (estado: {rep.get('status') if rep else 'inexistente'})")
    if not force and ctx.now_madrid.time() > PUBLISH_DEADLINE and ctx.now_madrid.date() == ctx.report_date:
        return PublishResult("failed", None, "pasadas las 10:30: se requiere confirmación humana (--force)")
    res = publish_once(store, client, channel="telegram_public", chat_id=chat_id, target_type="daily",
                       target_key=ctx.report_date.isoformat(), html=rep["rendered_telegram"])
    if res.status == "sent":
        store.save_daily_report(ctx.report_date, {"status": "published", "telegram_message_id": res.message_id,
                                                  "published_at": ctx.now.isoformat()})
    return res


def publication_time(report_date, hour: int = 9) -> datetime:
    return datetime.combine(report_date, time(hour, 0), tzinfo=MADRID)
