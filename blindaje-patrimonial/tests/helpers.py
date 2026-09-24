"""Utilidades compartidas por los tests."""

from __future__ import annotations

import copy
import dataclasses
import json
from datetime import date, datetime, timezone
from typing import Any

from bp.config import Config, load_config
from bp.editorial.render import DailyRenderer, RenderedDaily
from bp.llm.models import DailyOutput, WeeklyOutput
from bp.models import RunContext
from bp.select.fact_sheet import block_of
from bp.validation.deterministic import ValidationReport, precheck_refs, validate_daily, validate_weekly

UTC = timezone.utc
GOLDEN_CTX = RunContext(report_date=date(2026, 9, 23), now=datetime(2026, 9, 23, 6, 50, tzinfo=UTC))


def cfg_licensed(*source_ids: str) -> Config:
    """Copia de la configuración con esas fuentes como `licensed_public` (simula haber obtenido la licencia)."""
    cfg = load_config()
    sources = copy.deepcopy(cfg.sources)
    for sid in source_ids or ("sosovalue_api", "coinalyze"):
        sources[sid]["licence"] = "licensed_public"
        sources[sid]["llm_input_allowed"] = True
    return dataclasses.replace(cfg, sources=sources)


def golden_input() -> dict[str, Any]:
    cfg = load_config()
    return json.loads((cfg.root / "schema" / "examples" / "daily_input.example.json").read_text("utf-8"))


def golden_output() -> dict[str, Any]:
    cfg = load_config()
    return json.loads((cfg.root / "schema" / "examples" / "daily_output.example.json").read_text("utf-8"))


def blocks_for(cfg: Config, fs: dict[str, Any]) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}
    for f in fs["facts"]:
        if f["selected"] and (b := block_of(cfg, f["id"])):
            blocks.setdefault(b, []).append(f["id"])
    return blocks


def render(cfg: Config, fs: dict[str, Any], out: DailyOutput, origin: str = "llm", reviewer: str | None = None) -> RenderedDaily:
    return DailyRenderer(cfg, fs, blocks_for(cfg, fs)).render(GOLDEN_CTX, out, origin=origin, reviewer=reviewer)


def check_daily(out_dict: dict[str, Any], fs: dict[str, Any] | None = None, cfg: Config | None = None, origin: str = "llm",
                rendered: RenderedDaily | None = None, **kw) -> ValidationReport:
    cfg = cfg or cfg_licensed()
    fs = fs or golden_input()
    out = DailyOutput.model_validate(out_dict)
    pre = precheck_refs(fs, out)
    if not pre.passed:
        return pre
    rendered = rendered or render(cfg, fs, out, origin=origin if origin != "llm_reviewed" else "llm")
    return validate_daily(cfg, fs, out, rendered, origin=origin, allow_placeholders=True, **kw)


def blocking_ids(rep: ValidationReport) -> set[str]:
    return {c.check_id for c in rep.blocking}


def warning_ids(rep: ValidationReport) -> set[str]:
    return {c.check_id for c in rep.warnings}


def with_lectura(text: str, fact_ids: list[str], kind: str = "hecho", hint_ids: list[str] | None = None,
                 base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Salida dorada con la primera frase de la lectura sustituida."""
    out = copy.deepcopy(base or golden_output())
    out["lectura"][0] = {"text": text, "kind": kind, "fact_ids": fact_ids, "hint_ids": hint_ids or []}
    return out


# ─── Weekly ───

DOC_ES = ("La Agencia Estatal de Administración Tributaria publica el modelo 721 para el ejercicio 2026. "
          "El plazo de presentación finaliza el 31 de marzo de 2027.")
DOC_EU = ("The Commission adopted a proposal amending Regulation (EU) 2023/1114 on markets in crypto-assets. "
          "The proposal will now be discussed by the European Parliament and the Council.")


def weekly_input() -> dict[str, Any]:
    return {
        "meta": {"week_iso": "2026-W39", "period_start": "2026-09-21", "period_end": "2026-09-25", "send_date": "2026-09-26",
                 "prompt_version": "weekly-v1.0", "rules_version": 1, "audience": "general"},
        "financial": {"facts": [], "axes_start": [], "axes_end": []},
        "events": [{"event_id": 1}, {"event_id": 2}],
        "documents": [
            {"source_id": "doc_es_721", "text": DOC_ES, "legal_status": "vigente", "tier": "T1", "jurisdictions": ["ES"]},
            {"source_id": "doc_eu_mica", "text": DOC_EU, "legal_status": "propuesta", "tier": "T1", "jurisdictions": ["EU"]},
        ],
        "fronts_without_candidates": ["proteccion"],
        "calendar_next_week": [],
        "open_followups": [],
    }


def _claim(text: str, sid: str, quote: str) -> dict[str, Any]:
    return {"text": text, "source_ids": [sid], "evidence": [{"source_id": sid, "quote": quote}], "fact_ids": []}


def weekly_output() -> dict[str, Any]:
    item_es = {
        "event_id": 1, "titulo": "Modelo 721 del ejercicio 2026", "jurisdictions": ["ES"], "legal_status": "vigente",
        "que_ha_pasado": _claim("La AEAT ha publicado el modelo 721 para el ejercicio 2026.", "doc_es_721",
                                "publica el modelo 721 para el ejercicio 2026"),
        "por_que_importa": _claim("Fija el plazo de la declaración informativa de criptoactivos en el extranjero.", "doc_es_721",
                                  "El plazo de presentación finaliza el 31 de marzo de 2027"),
        "a_quien_afecta": {"profiles": ["residente_es"], "text": "Residentes fiscales en España con criptoactivos custodiados fuera."},
        "que_vigilar": {"text": "El cierre del plazo.", "source_ids": ["doc_es_721"],
                        "dates": [{"date": "2027-03-31", "what": "fin del plazo", "source_id": "doc_es_721"}]},
        "confidence": "confirmado_fuente_primaria",
    }
    item_eu = {
        "event_id": 2, "titulo": "Propuesta de modificación de MiCA", "jurisdictions": ["EU"], "legal_status": "propuesta",
        "que_ha_pasado": _claim("La Comisión ha adoptado una propuesta para modificar MiCA.", "doc_eu_mica",
                                "The Commission adopted a proposal amending Regulation (EU) 2023/1114"),
        "por_que_importa": _claim("Todavía debe debatirse en el Parlamento Europeo y el Consejo.", "doc_eu_mica",
                                  "will now be discussed by the European Parliament and the Council"),
        "a_quien_afecta": {"profiles": ["usuario_exchange"], "text": "Usuarios de proveedores de servicios de criptoactivos en la UE."},
        "que_vigilar": {"text": "La tramitación en el Parlamento Europeo.", "source_ids": ["doc_eu_mica"], "dates": []},
        "confidence": "confirmado_fuente_primaria",
    }
    empty = {"status": "sin_cambios_relevantes", "intro": None, "items": []}
    return {
        "subject": "Blindaje Patrimonial · Modelo 721 y reforma de MiCA",
        "preheader": "Las novedades de la semana en cuatro frentes.",
        "semana_en_60s": [{"rank": 1, "front": "fiscal", "text": "Publicado el modelo 721.", "event_id": 1, "fact_ids": [],
                           "source_ids": ["doc_es_721"]}],
        "financiero": {"status": "sin_cambios_relevantes", "lectura_semanal": [], "items": []},
        "fiscal": {"status": "con_novedades", "intro": None, "items": [item_es]},
        "regulatorio": {"status": "con_novedades", "intro": None, "items": [item_eu]},
        "proteccion": empty,
        "agenda": [],
        "editor_notes": [],
    }


def check_weekly(out_dict: dict[str, Any], inp: dict[str, Any] | None = None, **kw) -> ValidationReport:
    return validate_weekly(load_config(), inp or weekly_input(), WeeklyOutput.model_validate(out_dict), **kw)
