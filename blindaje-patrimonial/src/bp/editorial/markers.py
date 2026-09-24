"""Marcadores de slot-filling (docs/06 §3): {{f:<id>}}, {{fa:<id>}}, {{h:<hint_id>}}."""

from __future__ import annotations

import html
import re
from typing import Any

MARKER = re.compile(r"\{\{(f|fa|h):([A-Za-z0-9_.:\-]+)\}\}")


class MarkerError(ValueError):
    pass


def index_fact_sheet(fact_sheet: dict[str, Any]) -> tuple[dict[str, dict], dict[str, str]]:
    facts = {f["id"]: f for f in fact_sheet["facts"]}
    hints = {h["id"]: h["text"] for f in fact_sheet["facts"] for h in f.get("interpretation_hints", [])}
    return facts, hints


def markers_in(text: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for m in MARKER.finditer(text)]


def fill(text: str, facts: dict[str, dict], hints: dict[str, str], escape: bool = False, _depth: int = 0) -> str:
    """Sustituye los marcadores por los valores del fact sheet. escape=True escapa el texto para HTML de Telegram
    (antes de insertar los valores, que no contienen caracteres especiales)."""
    if _depth > 3:
        raise MarkerError("Anidamiento de pistas demasiado profundo")
    src = html.escape(text, quote=False) if escape else text

    def rep(m: re.Match) -> str:
        kind, key = m.group(1), m.group(2)
        if kind == "h":
            if key not in hints:
                raise MarkerError(f"Pista inexistente: {key}")
            return fill(hints[key], facts, hints, escape=escape, _depth=_depth + 1)
        if key not in facts:
            raise MarkerError(f"Hecho inexistente: {key}")
        val = facts[key]["display"] if kind == "f" else facts[key].get("display_abs")
        if val is None:
            raise MarkerError(f"El hecho {key} no tiene valor absoluto para {{{{fa:…}}}}")
        return html.escape(val, quote=False) if escape else val

    return MARKER.sub(rep, src)
