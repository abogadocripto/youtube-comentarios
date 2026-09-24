"""Modelos Pydantic de las salidas del LLM (espejo de schema/llm/*_output.schema.json).

Se usan para (1) generar el JSON Schema estricto que se envía en output_config.format y (2) validar la respuesta.
Las longitudes se validan en cliente (V-LEN), no en el esquema enviado a la API.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ─────────── Daily ───────────
class LecturaSentence(_Strict):
    text: str
    kind: Literal["hecho", "interpretacion", "matiz"]
    fact_ids: list[str]
    hint_ids: list[str]


class Vigilar(_Strict):
    watch_id: str
    text: str
    fact_ids: list[str]


class BlockComment(_Strict):
    block: Literal["sentimiento", "liquidez", "demanda_etf", "exchanges", "onchain", "macro", "derivados"]
    text: str
    fact_ids: list[str]
    hint_ids: list[str]


class DailyOutput(_Strict):
    lectura: list[LecturaSentence]
    vigilar: Vigilar
    block_comments: list[BlockComment]
    watch_override_reason: str | None


# ─────────── Verificador ───────────
IssueType = Literal[
    "none", "claim_not_in_sources", "wrong_direction_or_magnitude", "prediction", "investment_advice",
    "personalised_advice", "causal_claim", "overstatement_certainty", "missing_mandatory_caveat",
    "legal_status_misstated", "wrong_jurisdiction", "wrong_date", "sensationalism", "stale_presented_as_new",
    "attribution_error",
]


class VerifierCheck(_Strict):
    path: str
    rendered_text: str
    verdict: Literal["supported", "unsupported", "problematic"]
    issue_types: list[IssueType]
    explanation: str
    suggested_fix: str | None


class VerifierOutput(_Strict):
    checks: list[VerifierCheck]
    overall_pass: bool
    summary: str


# ─────────── Clasificación de noticias ───────────
class Feature(_Strict):
    score: Literal[0, 1, 2, 3, 4, 5]
    why: str


class Features(_Strict):
    economic_impact: Feature
    affected_population: Feature
    legal_force: Feature
    urgency: Feature
    novelty: Feature
    icp_fit: Feature


class KeyDate(_Strict):
    date: str
    what: str
    quote: str


Front = Literal["financiero", "fiscal", "regulatorio", "proteccion"]
Jurisdiction = Literal["ES", "AD", "EU", "US", "INTL", "AE", "OTHER"]
DocType = Literal["norma", "proyecto_normativo", "consulta_publica", "resolucion_administrativa", "consulta_vinculante",
                  "sentencia", "nota_prensa", "guia_o_qa", "informe", "noticia", "incidente_seguridad", "otro"]
LegalStatus = Literal["vigente", "publicada_pendiente_de_entrada_en_vigor", "aprobada_pendiente_de_publicacion",
                      "en_tramitacion", "propuesta", "consulta", "criterio_administrativo", "jurisprudencia",
                      "declaracion_o_anuncio", "incidente", "no_aplica"]
Profile = Literal["holder_particular", "residente_es", "residente_ad", "residente_ae", "empresa", "usuario_exchange",
                  "autocustodia", "usuarios_stablecoins", "inversor_etf", "no_residente", "herederos_sucesion"]


class NewsClassification(_Strict):
    relevant: bool
    relevance_reason: str
    fronts: list[Front]
    jurisdictions: list[Jurisdiction]
    doc_type: DocType
    legal_status: LegalStatus
    affected_profiles: list[Profile]
    features: Features
    key_dates: list[KeyDate]
    summary_es: str
    event_key_hint: str
    injection_suspected: bool


# ─────────── Weekly y alertas ───────────
class Evidence(_Strict):
    source_id: str
    quote: str


class ClaimText(_Strict):
    text: str
    source_ids: list[str]
    evidence: list[Evidence]
    fact_ids: list[str]


class AQuienAfecta(_Strict):
    profiles: list[Profile]
    text: str


class DateItem(_Strict):
    date: str
    what: str
    source_id: str


class QueVigilar(_Strict):
    text: str
    source_ids: list[str]
    dates: list[DateItem]


class WeeklyItem(_Strict):
    event_id: int
    titulo: str
    jurisdictions: list[str]
    legal_status: LegalStatus
    que_ha_pasado: ClaimText
    por_que_importa: ClaimText
    a_quien_afecta: AQuienAfecta
    que_vigilar: QueVigilar
    confidence: Literal["confirmado_fuente_primaria", "confirmado_fuente_secundaria", "pendiente_confirmacion"]


class FrontSection(_Strict):
    status: Literal["con_novedades", "sin_cambios_relevantes"]
    intro: str | None
    items: list[WeeklyItem]


class FinancialSection(_Strict):
    status: Literal["con_novedades", "sin_cambios_relevantes"]
    lectura_semanal: list[LecturaSentence]
    items: list[WeeklyItem]


class In60s(_Strict):
    rank: int
    front: Front
    text: str
    event_id: int | None
    fact_ids: list[str]
    source_ids: list[str]


class AgendaItem(_Strict):
    calendar_id: str
    text: str


class WeeklyOutput(_Strict):
    subject: str
    preheader: str
    semana_en_60s: list[In60s]
    financiero: FinancialSection
    fiscal: FrontSection
    regulatorio: FrontSection
    proteccion: FrontSection
    agenda: list[AgendaItem]
    editor_notes: list[str]


class AlertOutput(_Strict):
    titular: str
    legal_status: LegalStatus
    que_ha_pasado: ClaimText
    por_que_importa: ClaimText
    a_quien_afecta: AQuienAfecta
    que_vigilar: QueVigilar
    source_ids: list[str]
    editor_notes: list[str]


UNSUPPORTED_KEYS = {"minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                    "multipleOf", "minItems", "maxItems", "uniqueItems", "pattern", "title", "default"}


def strict_schema(model: type[BaseModel]) -> dict:
    """JSON Schema apto para output_config.format: additionalProperties:false y todos los campos requeridos."""
    schema = model.model_json_schema()

    def walk(node):
        if isinstance(node, dict):
            for k in list(node):
                if k in UNSUPPORTED_KEYS:
                    node.pop(k)
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema
