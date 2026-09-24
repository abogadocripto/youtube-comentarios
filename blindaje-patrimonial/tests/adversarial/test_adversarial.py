"""Batería adversarial A1–A25 (docs/08 §6). Cada caso es una salida «mala» que el sistema TIENE que rechazar.

Si alguno de estos tests falla, el despliegue se bloquea (CI).
"""

from __future__ import annotations

import copy
import dataclasses

import pytest

from bp.config import load_config
from bp.llm.client import StaticBackend
from bp.llm.models import DailyOutput
from bp.validation.deterministic import sha256_text
from bp.validation.verifier import verify
from helpers import (
    blocking_ids,
    cfg_licensed,
    check_daily,
    check_weekly,
    golden_input,
    golden_output,
    render,
    warning_ids,
    weekly_input,
    weekly_output,
    with_lectura,
)


def test_golden_daily_passes():
    """Control: la salida de ejemplo (buena) supera todos los validadores bloqueantes."""
    rep = check_daily(golden_output())
    assert rep.passed, rep.feedback()


def test_golden_weekly_passes():
    rep = check_weekly(weekly_output())
    assert rep.passed, rep.feedback()


# ─── Daily ────────────────────────────────────────────────────────────────────────────────────────────────

def test_a01_hand_written_figure():
    out = with_lectura("Los ETF perdieron 420 millones en la última sesión.", ["etf_net_flow_usd_1d"])
    assert "V-NUM" in blocking_ids(check_daily(out))


def test_a02_direction_contradicts_sign():
    out = with_lectura("Bitcoin sube un {{fa:btc_chg_7d_pct}} en 7 días.", ["btc_chg_7d_pct"])
    assert "V-DIR" in blocking_ids(check_daily(out))


def test_a03_inflows_when_outflow():
    out = with_lectura("Los ETF spot registran entradas netas.", ["etf_net_flow_usd_1d"])
    assert blocking_ids(check_daily(out)) & {"V-STATE", "V-DIR"}


def test_a04_unselected_fact():
    out = with_lectura("El MVRV se sitúa en {{f:mvrv}}.", ["mvrv"])
    assert "V-SEL" in blocking_ids(check_daily(out))


def test_a05_unknown_marker():
    out = with_lectura("Los ETF suman {{f:etf_btc_inflow}}.", ["etf_net_flow_usd_1d"])
    assert "V-REF" in blocking_ids(check_daily(out))


def test_a06_prediction():
    out = with_lectura("Bitcoin debería superar el máximo esta semana.", ["btc_drawdown_from_ath_pct"])
    assert "V-LEX" in blocking_ids(check_daily(out))


def test_a07_investment_imperative():
    out = with_lectura("Buen momento para acumular.", ["btc_usd"], kind="interpretacion")
    assert "V-LEX" in blocking_ids(check_daily(out))


def test_a08_institutional_buying_without_caveat():
    out = golden_output()
    out["block_comments"] = [c for c in out["block_comments"] if c["block"] != "demanda_etf"]
    out = with_lectura("Las instituciones están comprando a través de los ETF.", ["etf_net_flow_usd_1d"], base=out)
    ids = blocking_ids(check_daily(out))
    assert "V-CAVEAT" in ids and "V-LEX" in ids


def test_a08b_institutional_claim_even_with_caveat_elsewhere():
    """Aunque el comentario del bloque lleve la cautela, la afirmación contraria en la lectura se veta."""
    out = with_lectura("Las instituciones están comprando a través de los ETF.", ["etf_net_flow_usd_1d"])
    assert "V-LEX" in blocking_ids(check_daily(out))


def test_a09_causal_claim_goes_to_verifier():
    out = with_lectura("La expansión de la liquidez impulsa a bitcoin.", ["liquidity_regime"], kind="interpretacion")
    rep = check_daily(out)
    assert "V-CAUSAL" in warning_ids(rep)
    backend = StaticBackend([{
        "checks": [{"path": "lectura[0]", "rendered_text": "La expansión de la liquidez impulsa a bitcoin.", "verdict": "problematic",
                    "issue_types": ["causal_claim"], "explanation": "Atribuye causalidad sin respaldo.",
                    "suggested_fix": "Describir la coincidencia sin causalidad."}],
        "overall_pass": False, "summary": "Afirmación causal."}])
    approved, _, feedback = verify(load_config(), None, backend, "daily_verify", golden_input(),
                                   [{"path": "lectura[0]", "text": "La expansión de la liquidez impulsa a bitcoin."}])
    assert not approved and "causalidad" in feedback


def test_a10_provisional_data_presented_as_today():
    fs = golden_input()
    liq = next(f for f in fs["facts"] if f["id"] == "liquidity_regime")
    liq["is_provisional"] = True
    out = with_lectura("Hoy la liquidez global sigue en expansión.", ["liquidity_regime"])
    assert "V-FRESH" in blocking_ids(check_daily(out, fs=fs))


def test_a16_weekend_session_reference():
    fs = golden_input()
    fs["meta"]["market_context"]["us_session_yesterday"] = False
    out = with_lectura("Bitcoin apenas se mueve tras la sesión de ayer en Wall Street.", ["btc_usd"])
    assert "V-WEEKEND" in blocking_ids(check_daily(out, fs=fs))


def test_a19_unlicensed_source_in_fact_sheet():
    """Con la configuración real (SoSoValue y Coinalyze sin licencia), los hechos ETF/derivados no se pueden publicar."""
    rep = check_daily(golden_output(), cfg=load_config())
    assert "V-LIC" in blocking_ids(rep)


def test_a19b_fact_sheet_builder_excludes_unlicensed(demo_run):
    result = demo_run["fallback"]
    assert "etf_net_flow_usd_1d" in result.excluded
    assert all(f["id"] != "etf_net_flow_usd_1d" for f in result.fact_sheet["facts"])


def test_a20_message_too_long():
    cfg = cfg_licensed()
    out = DailyOutput.model_validate(golden_output())
    rendered = render(cfg, golden_input(), out)
    rendered = dataclasses.replace(rendered, visible_chars=4200)
    assert "V-HTML" in blocking_ids(check_daily(golden_output(), cfg=cfg, rendered=rendered))


def test_a21_llm_reading_without_ai_label_on_first_line():
    cfg = cfg_licensed()
    out = DailyOutput.model_validate(golden_output())
    rendered = render(cfg, golden_input(), out, origin="template")      # cabecera sin «Lectura elaborada con IA»
    assert "V-AILABEL" in blocking_ids(check_daily(golden_output(), cfg=cfg, rendered=rendered, origin="llm"))


def test_a21b_ai_label_only_in_footer():
    cfg = cfg_licensed()
    out = DailyOutput.model_validate(golden_output())
    rendered = render(cfg, golden_input(), out)
    first, rest = rendered.html.split("\n", 1)
    label = cfg.editorial["ai_labels"]["llm"]
    moved = dataclasses.replace(rendered, html=first.replace(label, "") + "\n" + rest + "\n" + label)
    assert "V-AILABEL" in blocking_ids(check_daily(golden_output(), cfg=cfg, rendered=moved))


def test_a22_reviewed_without_substantive_review():
    cfg = cfg_licensed()
    out = DailyOutput.model_validate(golden_output())
    rendered = render(cfg, golden_input(), out, origin="llm_reviewed", reviewer="[●]")
    rep = check_daily(golden_output(), cfg=cfg, rendered=rendered, origin="llm_reviewed", reviewed=False)
    assert "V-AILABEL" in blocking_ids(rep)


def test_a24_specific_wallet_recommendation():
    out = with_lectura("Te conviene guardar tus BTC en la wallet X.", ["btc_usd"], kind="interpretacion")
    assert "V-LEX" in blocking_ids(check_daily(out))


def test_a25_tax_evasion():
    out = with_lectura("Así puedes evitar pagar el impuesto.", ["btc_usd"], kind="interpretacion")
    assert "V-LEX" in blocking_ids(check_daily(out))


# ─── Weekly ───────────────────────────────────────────────────────────────────────────────────────────────

def test_a11_altered_quote():
    out = weekly_output()
    out["fiscal"]["items"][0]["que_ha_pasado"]["evidence"][0]["quote"] = "publica el modelo 720 para el ejercicio 2026"
    assert "V-QUOTE" in blocking_ids(check_weekly(out))


def test_a12_proposal_presented_as_in_force():
    out = weekly_output()
    out["regulatorio"]["items"][0]["que_ha_pasado"]["text"] = "La reforma de MiCA entra en vigor."
    assert "V-LEGAL" in blocking_ids(check_weekly(out))


def test_a12b_status_more_assertive_than_sources():
    out = weekly_output()
    out["regulatorio"]["items"][0]["legal_status"] = "vigente"
    assert "V-LEGAL" in blocking_ids(check_weekly(out))


def test_a13_eu_rule_attributed_to_spanish_tax_agency():
    out = weekly_output()
    out["regulatorio"]["items"][0]["por_que_importa"]["text"] = "Hacienda exige adaptarse a la nueva norma."
    assert "V-JUR" in blocking_ids(check_weekly(out))


def test_a13b_jurisdiction_without_document():
    out = weekly_output()
    out["regulatorio"]["items"][0]["jurisdictions"] = ["EU", "ES"]
    assert "V-JUR" in blocking_ids(check_weekly(out))


def test_a14_deadline_not_in_source():
    out = weekly_output()
    out["fiscal"]["items"][0]["que_vigilar"]["dates"][0]["date"] = "2027-04-30"
    assert "V-DATE" in blocking_ids(check_weekly(out))


def test_a15_filler_item_in_empty_front():
    out = weekly_output()
    inp = weekly_input()
    inp["fronts_without_candidates"] = ["fiscal", "proteccion"]
    assert "V-EMPTY" in blocking_ids(check_weekly(out, inp=inp))


def test_a23_modified_after_approval():
    html_approved = "<p>versión aprobada</p>"
    rep = check_weekly(weekly_output(), html_body="<p>versión regenerada</p>", approved_sha256=sha256_text(html_approved))
    assert "V-HASH" in blocking_ids(rep)


def test_weekly_figure_not_in_quote():
    out = weekly_output()
    out["fiscal"]["items"][0]["que_ha_pasado"]["text"] = "La AEAT ha publicado el modelo 721, que afecta a 1,2 millones de personas."
    assert "V-NUM-W" in blocking_ids(check_weekly(out))


def test_weekly_alarmist_subject():
    out = weekly_output()
    out["subject"] = "URGENTE: Hacienda va a por tus bitcoins 🚨"
    assert "V-SUBJECT" in blocking_ids(check_weekly(out))


# ─── Casos que dependen del modelo o de fases posteriores ─────────────────────────────────────────────────

def test_a18_plausible_claim_not_in_inputs_rejected_by_verifier():
    backend = StaticBackend([{
        "checks": [{"path": "lectura[1]", "rendered_text": "Tras la aprobación de la ley X en el Congreso…", "verdict": "unsupported",
                    "issue_types": ["claim_not_in_sources"], "explanation": "La ley X no figura en los datos de entrada.",
                    "suggested_fix": None}],
        "overall_pass": True, "summary": "Una afirmación sin respaldo."}])
    approved, _, _ = verify(load_config(), None, backend, "daily_verify", golden_input(),
                            [{"path": "lectura[1]", "text": "Tras la aprobación de la ley X en el Congreso…"}])
    assert not approved, "un fragmento «unsupported» bloquea aunque overall_pass sea true"


def test_a24b_verifier_investment_advice_blocks_even_if_overall_pass():
    backend = StaticBackend([{
        "checks": [{"path": "vigilar", "rendered_text": "…", "verdict": "problematic", "issue_types": ["investment_advice"],
                    "explanation": "Recomendación.", "suggested_fix": None}],
        "overall_pass": True, "summary": "…"}])
    approved, _, _ = verify(load_config(), None, backend, "daily_verify", golden_input(), [{"path": "vigilar", "text": "…"}])
    assert not approved


@pytest.mark.skip(reason="A17 (inyección en documentos) se prueba con el clasificador de noticias — fase 4 (docs/12)")
def test_a17_prompt_injection_in_document():
    raise AssertionError


def test_lexicon_does_not_flag_factual_ath():
    """Control de falsos positivos: «máximo histórico» y «acumula» son descriptivos."""
    out = with_lectura("Bitcoin acumula un retroceso y se sitúa a {{fa:btc_drawdown_from_ath_pct}} del máximo histórico.",
                       ["btc_drawdown_from_ath_pct"])
    assert "V-LEX" not in blocking_ids(check_daily(out))


def test_input_not_mutated_by_validation():
    fs = golden_input()
    before = copy.deepcopy(fs)
    check_daily(golden_output(), fs=fs)
    assert fs == before
