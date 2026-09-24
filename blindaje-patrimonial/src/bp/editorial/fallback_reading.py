"""Lectura determinista por plantillas (respaldo cuando el LLM falla o no supera la validación; docs/01 §4.2).

Produce un DailyOutput con la misma forma que el del LLM, de modo que el renderizador y los validadores
se aplican igual. Solo usa estados y pistas ya calculados; no hay texto libre.
"""

from __future__ import annotations

from typing import Any

from bp.llm.models import BlockComment, DailyOutput, LecturaSentence, Vigilar

_FEM = ("subida", "caída", "limpieza", "reducción", "maduración", "realización", "venta")


def _indef(label: str) -> str:
    """Artículo indefinido concordado con la etiqueta de estado (un movimiento / una subida)."""
    first = label.split()[0].lower()
    if first == "fuerte":
        first = label.split()[1].lower()
    return ("una " if first.startswith(_FEM) else "un ") + label


def _state(facts: dict[str, dict], mid: str) -> str | None:
    f = facts.get(mid)
    if not f or not f["selected"]:
        return None
    return f["state"]["label_es"] or None


_LIQ = {"expansion": "La liquidez global sigue en expansión", "contraction": "La liquidez global está en contracción",
        "neutral": "La liquidez global se mantiene neutral", "mixed": "Las señales de liquidez global son mixtas",
        "neutral_us_up": "La liquidez global se mantiene neutral, con impulso de corto plazo al alza en EE. UU.",
        "neutral_us_down": "La liquidez global se mantiene neutral, con impulso de corto plazo a la baja en EE. UU."}


def _liquidity_phrase(facts: dict[str, dict]) -> str | None:
    f = facts.get("liquidity_regime")
    if not f or not f["selected"] or f["state"]["code"] not in _LIQ:
        return None
    return _LIQ[f["state"]["code"]]


def _fng_phrase(facts: dict[str, dict]) -> str | None:
    """«el índice de Miedo y Codicia está en zona neutral (enfriamiento notable)»."""
    f = facts.get("fng_value")
    if not f or not f["selected"] or not f["state"]["label_es"]:
        return None
    label = f["state"]["label_es"]
    base, _, trend = label.partition(" (")
    zone = "en zona neutral" if base == "neutral" else f"en zona de {base}"
    return f"el índice de Miedo y Codicia está {zone}" + (f" ({trend}" if trend else "")


def build(fact_sheet: dict[str, Any]) -> DailyOutput:
    facts = {f["id"]: f for f in fact_sheet["facts"]}
    sentences: list[LecturaSentence] = []

    move = _state(facts, "btc_usd")
    band = _state(facts, "btc_drawdown_from_ath_pct")
    if move and band and "btc_drawdown_from_ath_pct" in facts:
        sentences.append(LecturaSentence(
            text=f"Bitcoin registra {_indef(move)} en las últimas 24 horas y se sitúa {band}, a {{{{fa:btc_drawdown_from_ath_pct}}}} del máximo histórico.",
            kind="hecho", fact_ids=["btc_usd", "btc_drawdown_from_ath_pct"], hint_ids=[]))
    elif move:
        sentences.append(LecturaSentence(text=f"Bitcoin registra {_indef(move)} en las últimas 24 horas.", kind="hecho",
                                         fact_ids=["btc_usd"], hint_ids=[]))

    parts, ids = [], []
    etf = _state(facts, "etf_net_flow_usd_1d")
    if etf:
        parts.append(f"los ETF spot de EE. UU. registran {etf}")
        ids.append("etf_net_flow_usd_1d")
    oi = _state(facts, "oi_chg_24h_pct")
    if oi:
        parts.append(f"en derivados se observa {_indef(oi)}")
        ids.append("oi_chg_24h_pct")
    mvrv = _state(facts, "mvrv")
    if mvrv and not parts:
        parts.append(f"el MVRV indica una {mvrv}")
        ids.append("mvrv")
    if parts:
        sentences.append(LecturaSentence(text=(" y ".join(parts)).capitalize() + ".", kind="hecho", fact_ids=ids, hint_ids=[]))

    liq = _liquidity_phrase(facts)
    fng = _fng_phrase(facts)
    if liq and fng:
        sentences.append(LecturaSentence(text=f"{liq} y {fng}.", kind="hecho", fact_ids=["liquidity_regime", "fng_value"], hint_ids=[]))
    elif liq or fng:
        sentences.append(LecturaSentence(text=f"{(liq or fng)[0].upper()}{(liq or fng)[1:]}.", kind="hecho",
                                         fact_ids=["liquidity_regime" if liq else "fng_value"], hint_ids=[]))
    if len(sentences) < 2:
        sentences.append(LecturaSentence(text="Jornada sin cambios de fondo en los indicadores seguidos.", kind="matiz",
                                         fact_ids=[next(iter(f["id"] for f in fact_sheet["facts"] if f["selected"]))], hint_ids=[]))

    watch = fact_sheet["watch"]
    sel = next((c for c in watch["candidates"] if c["id"] == watch["selected_id"]), None)
    if sel:
        when = f" ({sel['when_madrid']})" if sel.get("when_madrid") else ""
        vig = Vigilar(watch_id=sel["id"], text=f"{sel['title_es']}{when}.", fact_ids=sel.get("fact_ids", []))
    else:
        vig = Vigilar(watch_id="none", text="La evolución de los indicadores de demanda y liquidez.", fact_ids=[])

    comments: list[BlockComment] = []
    for f in fact_sheet["facts"]:
        if f["id"] == "etf_net_flow_usd_1d" and f["selected"] and f["caveats"]:
            comments.append(BlockComment(block="demanda_etf", text=f["caveats"][0], fact_ids=[f["id"]], hint_ids=[]))
    return DailyOutput(lectura=sentences[:4], vigilar=vig, block_comments=comments, watch_override_reason=None)
