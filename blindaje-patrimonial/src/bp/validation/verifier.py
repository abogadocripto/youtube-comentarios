"""Verificador LLM independiente (docs/08 §5): audita el texto RENDERIZADO contra los datos de entrada."""

from __future__ import annotations

import json
from typing import Any

from bp.config import Config
from bp.llm.client import LLMBackend, call_structured, load_prompt
from bp.llm.models import DailyOutput, VerifierOutput
from bp.store.base import Store

BLOCKING_ISSUES = {"prediction", "investment_advice", "personalised_advice", "legal_status_misstated"}


def daily_fragments(out: DailyOutput, fill) -> list[dict[str, str]]:
    frags = [{"path": f"lectura[{i}]", "text": fill(s.text)} for i, s in enumerate(out.lectura)]
    frags.append({"path": "vigilar", "text": fill(out.vigilar.text)})
    frags += [{"path": f"block_comments[{c.block}]", "text": fill(c.text)} for c in out.block_comments]
    return frags


def verify(cfg: Config, store: Store | None, backend: LLMBackend, call: str, inputs: dict[str, Any],
           fragments: list[dict[str, str]]) -> tuple[bool, VerifierOutput, str]:
    """Devuelve (aprobado, salida, feedback). No aprobado si overall_pass=false, algún 'unsupported' o problema bloqueante."""
    system, version = load_prompt(cfg, "verify.system.md")
    user = ("Datos de entrada exactos que recibió el redactor:\n<inputs>\n"
            + json.dumps(inputs, ensure_ascii=False) + "\n</inputs>\n\nTexto renderizado a auditar, por fragmentos:\n<fragments>\n"
            + json.dumps(fragments, ensure_ascii=False) + "\n</fragments>\n\nAudita cada fragmento.")
    res = call_structured(cfg, store, backend, call=call, system=system, user=user, model_cls=VerifierOutput, prompt_version=version)
    out: VerifierOutput = res.parsed  # type: ignore[assignment]
    bad = [c for c in out.checks if c.verdict == "unsupported" or BLOCKING_ISSUES & set(c.issue_types)]
    approved = out.overall_pass and not bad
    feedback = "\n".join(f"- [verificador] {c.path}: {c.explanation}" + (f" Propuesta: {c.suggested_fix}" if c.suggested_fix else "")
                         for c in out.checks if c.verdict != "supported")
    return approved, out, feedback
