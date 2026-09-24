"""Validadores deterministas (docs/08 §4). Severidad: B = bloqueante, W = aviso.

Uso: `validate_daily(...)` y `validate_weekly(...)` devuelven un ValidationReport; `report.feedback()` genera el texto
que se envía al LLM en el reintento.
"""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from bp.config import Config
from bp.editorial.markers import MARKER, markers_in
from bp.editorial.render import RenderedDaily, strip_tags
from bp.licence import metric_publishable
from bp.llm.models import DailyOutput, WeeklyOutput

SIGNED_FMTS = {"pct_signed_1dp", "pct_signed_3dp", "bp_signed", "int_signed", "btc_signed_int", "usd_millions", "pp_signed"}


@dataclass
class Check:
    check_id: str
    severity: str        # B | W
    passed: bool
    path: str = ""
    details: str = ""


@dataclass
class ValidationReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, check_id: str, severity: str, passed: bool, path: str = "", details: str = "") -> None:
        self.checks.append(Check(check_id, severity, passed, path, details))

    @property
    def blocking(self) -> list[Check]:
        return [c for c in self.checks if not c.passed and c.severity == "B"]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if not c.passed and c.severity == "W"]

    @property
    def passed(self) -> bool:
        return not self.blocking

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "blocking": len(self.blocking), "warnings": len(self.warnings),
                "checks": [c.__dict__ for c in self.checks]}

    def feedback(self) -> str:
        lines = [f"- [{c.check_id}] {c.path}: {c.details}" for c in self.blocking]
        lines += [f"- (aviso) [{c.check_id}] {c.path}: {c.details}" for c in self.warnings]
        return "\n".join(lines)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.replace(" ", " ").replace(" ", " ")
    s = re.sub(r"[“”«»„]", '"', s)
    s = re.sub(r"[‘’‚]", "'", s)
    s = re.sub(r"[‐‑‒–—−]", "-", s)
    return re.sub(r"\s+", " ", s).strip()


def _lower_plain(s: str) -> str:
    return _norm(strip_tags(s)).lower()


class _TagChecker(HTMLParser):
    def __init__(self, allowed: set[str]) -> None:
        super().__init__()
        self.allowed, self.stack, self.errors, self.hrefs = allowed, [], [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.allowed:
            self.errors.append(f"etiqueta no permitida <{tag}>")
        if tag == "a":
            self.hrefs.extend(v for k, v in attrs if k == "href")
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"cierre desequilibrado </{tag}>")
        else:
            self.stack.pop()


# ═══════════════════════════════ DAILY ═══════════════════════════════

def _llm_items(out: DailyOutput) -> list[tuple[str, str, list[str], list[str], str | None]]:
    """(ruta, texto, fact_ids, hint_ids, kind)"""
    items = [(f"lectura[{i}]", s.text, s.fact_ids, s.hint_ids, s.kind) for i, s in enumerate(out.lectura)]
    items.append(("vigilar", out.vigilar.text, out.vigilar.fact_ids, [], None))
    items += [(f"block_comments[{c.block}]", c.text, c.fact_ids, c.hint_ids, None) for c in out.block_comments]
    return items


def validate_daily(cfg: Config, fact_sheet: dict[str, Any], out: DailyOutput, rendered: RenderedDaily,
                   origin: str, previous_lectura: str | None = None, reviewed: bool = False,
                   allow_placeholders: bool = False) -> ValidationReport:
    """`allow_placeholders` solo se activa en ensayos offline: en producción un marcador [●] bloquea la publicación."""
    ed = cfg.editorial
    rep = ValidationReport()
    facts = {f["id"]: f for f in fact_sheet["facts"]}
    hints = {h["id"]: h for f in fact_sheet["facts"] for h in f.get("interpretation_hints", [])}
    hint_owner = {h["id"]: f["id"] for f in fact_sheet["facts"] for h in f.get("interpretation_hints", [])}
    selected = {f["id"] for f in fact_sheet["facts"] if f["selected"]}
    lim = fact_sheet["meta"]["limits"]
    items = _llm_items(out)
    from bp.editorial.markers import fill
    hint_texts = {k: v["text"] for k, v in hints.items()}

    def rendered_text(t: str) -> str:
        try:
            return fill(t, facts, hint_texts)
        except Exception:     # los errores de referencia los reporta V-REF
            return MARKER.sub("", t)

    # V-LEN
    n = len(out.lectura)
    lectura_plain = " ".join(rendered_text(s.text) for s in out.lectura)
    rep.add("V-LEN", "B", ed["limits"]["lectura_min_sentences"] <= n <= lim["lectura_max_sentences"], "lectura",
            f"{n} frases (permitido {ed['limits']['lectura_min_sentences']}–{lim['lectura_max_sentences']})")
    rep.add("V-LEN", "B", len(lectura_plain) <= lim["lectura_max_chars"], "lectura",
            f"{len(lectura_plain)} caracteres renderizados (máx. {lim['lectura_max_chars']})")
    vig_plain = rendered_text(out.vigilar.text)
    rep.add("V-LEN", "B", len(vig_plain) <= lim["vigilar_max_chars"], "vigilar",
            f"{len(vig_plain)} caracteres (máx. {lim['vigilar_max_chars']})")
    seen_blocks = set()
    for c in out.block_comments:
        rep.add("V-LEN", "B", len(rendered_text(c.text)) <= lim["block_comment_max_chars"], f"block_comments[{c.block}]",
                f"{len(rendered_text(c.text))} caracteres (máx. {lim['block_comment_max_chars']})")
        rep.add("V-LEN", "B", c.block not in seen_blocks, f"block_comments[{c.block}]", "más de un comentario para el mismo bloque")
        seen_blocks.add(c.block)

    whitelist = [p.lower() for p in ed.get("number_whitelist_phrases", [])]
    lex = {cat: [re.compile(p, re.IGNORECASE) for p in pats] for cat, pats in ed["lexicon"].items()}
    ath_new = any(f["state"]["code"] == "ath_new" and f["selected"] for f in fact_sheet["facts"])
    pos_words = [w.lower() for w in ed["direction"]["positive"]]
    neg_words = [w.lower() for w in ed["direction"]["negative"]]
    window = ed["direction"]["window_words"]
    stale_words = ed["stale_today_words"]
    for path, text, fids, hids, kind in items:
        # V-REF / V-SEL / V-DECL
        for mk, key in markers_in(text):
            if mk == "h":
                ok = key in hints
                rep.add("V-REF", "B", ok, path, f"pista inexistente {{{{h:{key}}}}}" if not ok else "")
                if ok:
                    owner = hint_owner[key]
                    rep.add("V-SEL", "B", owner in selected, path, f"la pista {key} pertenece a un hecho no seleccionado")
                    rep.add("V-DECL", "B", key in hids, path, f"la pista {key} no figura en hint_ids")
            else:
                ok = key in facts
                rep.add("V-REF", "B", ok, path, f"hecho inexistente {{{{{mk}:{key}}}}}" if not ok else "")
                if ok:
                    rep.add("V-SEL", "B", key in selected, path, f"el hecho {key} no está seleccionado")
                    rep.add("V-DECL", "B", key in fids, path, f"el hecho {key} no figura en fact_ids")
                    if mk == "fa":
                        rep.add("V-REF", "B", facts[key].get("display_abs") is not None, path, f"{key} no admite {{{{fa:…}}}}")
        for fid in fids:
            rep.add("V-SEL", "B", fid in selected, path, f"fact_id declarado no seleccionado o inexistente: {fid}")
        if kind == "interpretacion":
            rep.add("V-DECL", "B", len(fids) > 0, path, "frase de interpretación sin fact_ids")
        # V-NUM
        stripped = MARKER.sub(" ", text)
        low = stripped.lower()
        allowed = list(whitelist)
        if path == "vigilar":                       # la hora y el título del evento llegan ya formateados
            cand = next((c for c in fact_sheet["watch"]["candidates"] if c["id"] == out.vigilar.watch_id), None)
            if cand:
                allowed += [x.lower() for x in (cand.get("when_madrid"), cand.get("title_es")) if x]
        for ph in sorted(allowed, key=len, reverse=True):
            low = low.replace(ph, " ")
        digits = re.findall(r"\d", low)
        rep.add("V-NUM", "B", not digits, path, "contiene cifras fuera de marcadores: usa {{f:…}} o {{fa:…}}" if digits else "")
        # V-NUMWORD (aviso)
        nw = [w for w in ed["number_words"] if re.search(rf"\b{re.escape(w)}\b", low)]
        rep.add("V-NUMWORD", "W", not nw, path, f"números escritos con letra: {', '.join(nw)}" if nw else "")
        # V-LEX
        plain = rendered_text(text)
        for cat, pats in lex.items():
            for p in pats:
                m = p.search(plain)
                if m and not (cat == "sensacionalismo" and "histór" in m.group(0).lower() and ath_new):
                    rep.add("V-LEX", "B", False, path, f"expresión vetada ({cat}): «{m.group(0)}»")
        # V-CAUSAL (aviso → verificador)
        cz = [w for w in ed["causal_connectors"] if re.search(rf"\b{re.escape(w)}\b", plain.lower())]
        rep.add("V-CAUSAL", "W", not cz, path, f"conectores causales: {', '.join(cz)}" if cz else "")
        # V-DIR (métricas con signo)
        tokens = re.findall(r"\{\{(?:f|fa|h):[^}]+\}\}|[\wáéíóúñü]+|[,.;:]", text.lower())
        for i, tok in enumerate(tokens):
            m = re.match(r"\{\{(f|fa):([^}]+)\}\}", tok)
            if not m or m.group(2) not in facts:
                continue
            f = facts[m.group(2)]
            fmt = cfg.metrics[f["id"]].fmt if f["id"] in cfg.metrics else ""
            v = f.get("value")
            if fmt not in SIGNED_FMTS or not isinstance(v, (int, float)) or v == 0:
                continue
            lo, hi = i, i
            while lo > 0 and i - lo < window and tokens[lo - 1] not in ",.;:":
                lo -= 1
            while hi < len(tokens) - 1 and hi - i < window and tokens[hi + 1] not in ",.;:":
                hi += 1
            win = " ".join(tokens[lo:hi + 1])
            bad = (v < 0 and any(re.search(rf"\b{re.escape(w)}\b", win) for w in pos_words)) or \
                  (v > 0 and any(re.search(rf"\b{re.escape(w)}\b", win) for w in neg_words))
            rep.add("V-DIR", "B", not bad, path, f"la dirección del texto contradice el signo de {f['id']} ({f['display']})" if bad else "")
        # V-STATE
        state_forbidden = {"outflow": ["entradas"], "outflow_strong": ["entradas"], "inflow": ["salidas"], "inflow_strong": ["salidas"],
                           "expansion": ["contracción"], "contraction": ["expansión"],
                           "oi_up": ["desapalancamiento"], "oi_surge": ["desapalancamiento"],
                           "oi_down": ["aumento del apalancamiento"], "oi_flush": ["aumento del apalancamiento"]}
        for fid in fids:
            f = facts.get(fid)
            if not f:
                continue
            for w in state_forbidden.get(f["state"]["code"], []):
                if w in plain.lower() and len(fids) == 1:
                    rep.add("V-STATE", "B", False, path, f"«{w}» contradice el estado de {fid} ({f['state']['label_es']})")
        # V-FRESH
        for fid in fids:
            f = facts.get(fid)
            if f and (f["freshness"] == "stale_shown" or f["is_provisional"]):
                hit = [w for w in stale_words if re.search(rf"\b{re.escape(w)}\b", plain.lower())]
                rep.add("V-FRESH", "B", not hit, path, f"{fid} es un dato antiguo o provisional presentado como de hoy («{', '.join(hit)}»)" if hit else "")
        # V-WEEKEND
        if not fact_sheet["meta"]["market_context"]["us_session_yesterday"]:
            hit = [w for w in ed["weekend_forbidden"] if w in plain.lower()]
            rep.add("V-WEEKEND", "B", not hit, path, f"no hubo sesión en EE. UU.: «{', '.join(hit)}»" if hit else "")

    # V-WATCH
    watch = fact_sheet["watch"]
    cand_ids = {c["id"] for c in watch["candidates"]}
    rep.add("V-WATCH", "B", out.vigilar.watch_id in cand_ids or (out.vigilar.watch_id == "none" and not cand_ids), "vigilar",
            f"watch_id {out.vigilar.watch_id} no está entre los candidatos")
    if out.vigilar.watch_id != watch["selected_id"]:
        rep.add("V-WATCH", "B", bool(out.watch_override_reason), "vigilar", "se cambió el candidato sin watch_override_reason")

    # V-CAVEAT (sobre el mensaje completo)
    full_plain = _lower_plain(rendered.html)
    declared = {fid for _, _, fids, _, _ in items for fid in fids}
    interp_declared = {fid for _, _, fids, _, kind in items if kind == "interpretacion" for fid in fids}
    for fid in selected:
        m = cfg.metrics.get(fid)
        cav = m.caveat if m else None
        if not cav or not cav.get("must_contain_any"):
            continue
        if cav.get("only_if") == "interpretacion" and fid not in interp_declared:
            continue
        if cav.get("only_if_state") and facts[fid]["state"]["code"] not in cav["only_if_state"]:
            continue
        if cav.get("only_if") == "interpretacion" or fid in declared or fid in selected:
            ok = any(k.lower() in full_plain for k in cav["must_contain_any"])
            rep.add("V-CAVEAT", "B", ok, fid, f"falta la cautela obligatoria de {fid} (una de: {', '.join(cav['must_contain_any'])})" if not ok else "")

    # V-AILABEL
    first_line = rendered.html.split("\n", 1)[0]
    expected = ed["ai_labels"]["llm"] if origin == "llm" else ed["ai_labels"]["template"] if origin == "template" else None
    if origin == "llm_reviewed":
        rep.add("V-AILABEL", "B", reviewed and "revisado por" in first_line, "cabecera",
                "«revisado por» sin registro de revisión sustantiva" if not reviewed else "")
    else:
        rep.add("V-AILABEL", "B", bool(expected) and expected in first_line, "cabecera", f"falta la etiqueta «{expected}» en la primera línea")

    # V-HTML
    tc = _TagChecker(set(ed["telegram_allowed_tags"]))
    tc.feed(rendered.html)
    tc.close()
    rep.add("V-HTML", "B", not tc.errors and not tc.stack, "html", "; ".join(tc.errors + [f"sin cerrar <{t}>" for t in tc.stack]))
    rep.add("V-HTML", "B", rendered.visible_chars <= ed["limits"]["telegram_max_chars"], "html",
            f"{rendered.visible_chars} caracteres visibles (máx. {ed['limits']['telegram_max_chars']})")
    for href in tc.hrefs:
        if "[●]" in href:
            rep.add("V-HTML", "W" if allow_placeholders else "B", False, "html", f"enlace sin configurar: {href}")
            continue
        try:
            host = urlparse(href).hostname or ""
        except ValueError:
            host = ""
        ok = bool(host) and any(host == d or host.endswith("." + d) for d in ed["link_domains_allowed"])
        rep.add("V-HTML", "B", ok, "html", f"enlace a dominio no permitido: {host or href}")
    if "[●]" in rendered.plain:
        rep.add("V-PLACEHOLDER", "W" if allow_placeholders else "B", False, "texto", "quedan marcadores [●] sin completar")

    # V-LIC
    for fid in selected:
        f = facts[fid]
        pub = metric_publishable(cfg, fid)
        rep.add("V-LIC", "B", pub, fid, f"{fid} no tiene licencia de difusión pública" if not pub else "")
    if "fng_value" in selected:
        rep.add("V-LIC", "B", "fuente: alternative.me" in full_plain, "fng_value", "falta la atribución de alternative.me junto al dato")
    for a in rendered.attributions:
        rep.add("V-LIC", "B", a.lower() in full_plain, "pie", f"falta la atribución «{a}» en el pie")

    # V-REPEAT (aviso)
    if previous_lectura and out.lectura:
        a = set(re.findall(r"\w+", lectura_plain.split(".")[0].lower()))
        b = set(re.findall(r"\w+", previous_lectura.split(".")[0].lower()))
        overlap = len(a & b) / max(1, len(a))
        rep.add("V-REPEAT", "W", overlap <= 0.6, "lectura[0]", f"primera frase muy parecida a la de ayer ({overlap:.0%})")
    return rep


# ═══════════════════════════════ WEEKLY / ALERTAS ═══════════════════════════════

LEGAL_RANK = {"vigente": 9, "publicada_pendiente_de_entrada_en_vigor": 8, "aprobada_pendiente_de_publicacion": 7,
              "jurisprudencia": 6, "criterio_administrativo": 5, "en_tramitacion": 4, "propuesta": 3, "consulta": 2,
              "declaracion_o_anuncio": 1, "incidente": 0, "no_aplica": 0}
ASSERTIVE_LEGAL = ["entra en vigor", "es obligatorio", "es obligatoria", "ya aplica", "está vigente", "es vigente", "ya es ley"]
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def quote_in_document(quote: str, text: str) -> bool:
    return len(quote.strip()) >= 8 and _norm(quote) in _norm(text)


def date_variants(iso: str) -> list[str]:
    y, m, d = iso[:10].split("-")
    di, mi = int(d), int(m)
    return [iso[:10], f"{d}/{m}/{y}", f"{di}/{mi}/{y}", f"{di} de {MONTHS[mi - 1]} de {y}", f"{di} de {MONTHS[mi - 1]}",
            f"{d}.{m}.{y}", f"{di} {MONTHS[mi - 1]} {y}"]


def validate_weekly(cfg: Config, weekly_input: dict[str, Any], out: WeeklyOutput, html_body: str | None = None,
                    approved_sha256: str | None = None) -> ValidationReport:
    ed = cfg.editorial
    rep = ValidationReport()
    docs = {d["source_id"]: d for d in weekly_input["documents"]}
    events = {e["event_id"] for e in weekly_input["events"]}
    lex = [re.compile(p, re.IGNORECASE) for pats in ed["lexicon"].values() for p in pats]

    def check_claim(path: str, claim, item_status: str | None = None) -> None:
        for sid in claim.source_ids:
            rep.add("V-SRC", "B", sid in docs, path, f"fuente inexistente {sid}")
        rep.add("V-SRC", "B", bool(claim.evidence) or not claim.source_ids, path, "afirmación basada en documentos sin cita literal")
        quotes_norm = []
        for ev in claim.evidence:
            doc = docs.get(ev.source_id)
            ok = bool(doc) and quote_in_document(ev.quote, doc["text"])
            rep.add("V-QUOTE", "B", ok, path, f"la cita no aparece literalmente en {ev.source_id}: «{ev.quote[:60]}…»" if not ok else "")
            quotes_norm.append(_norm(ev.quote))
        body = MARKER.sub(" ", claim.text)
        for num in re.findall(r"\d[\d.,]*", body):
            ok = any(num in q for q in quotes_norm)
            rep.add("V-NUM-W", "B", ok, path, f"la cifra «{num}» no aparece en ninguna cita aportada" if not ok else "")
        for p in lex:
            m = p.search(claim.text)
            if m:
                rep.add("V-LEX", "B", False, path, f"expresión vetada «{m.group(0)}»")
        if item_status is not None and LEGAL_RANK.get(item_status, 0) <= 4:
            hit = [a for a in ASSERTIVE_LEGAL if a in claim.text.lower()]
            rep.add("V-LEGAL", "B", not hit, path, f"lenguaje de norma vigente para un asunto en estado {item_status}: {hit}" if hit else "")

    for sec_name in ("financiero", "fiscal", "regulatorio", "proteccion"):
        sec = getattr(out, sec_name)
        if sec_name in weekly_input["fronts_without_candidates"]:
            rep.add("V-EMPTY", "B", sec.status == "sin_cambios_relevantes" and not sec.items, sec_name,
                    "frente sin candidatos: debe ser «sin_cambios_relevantes» y sin asuntos")
        if sec.status == "con_novedades" and sec_name != "financiero":
            rep.add("V-EMPTY", "B", len(sec.items) > 0, sec_name, "frente «con_novedades» sin asuntos")
        for i, it in enumerate(sec.items):
            path = f"{sec_name}.items[{i}]"
            rep.add("V-SRC", "B", it.event_id in events, path, f"event_id {it.event_id} inexistente")
            cited = {sid for c in (it.que_ha_pasado, it.por_que_importa) for sid in c.source_ids} | set(it.que_vigilar.source_ids)
            cited_docs = [docs[s] for s in cited if s in docs]
            # V-LEGAL
            if cited_docs:
                max_rank = max(LEGAL_RANK.get(d["legal_status"], 0) for d in cited_docs)
                rep.add("V-LEGAL", "B", LEGAL_RANK.get(it.legal_status, 0) <= max_rank, path,
                        f"estado jurídico {it.legal_status} más asertivo que sus fuentes")
                tiers = {d["tier"] for d in cited_docs}
                if tiers == {"T3"}:
                    rep.add("V-SRC", "B", it.confidence == "pendiente_confirmacion" and "según" in it.que_ha_pasado.text.lower(),
                            path, "asunto solo con fuentes T3: debe ser «pendiente_confirmacion» y usar «según…»")
                # V-JUR
                doc_jur = {j for d in cited_docs for j in d["jurisdictions"]}
                extra = set(it.jurisdictions) - doc_jur
                rep.add("V-JUR", "B", not extra, path, f"jurisdicciones sin respaldo documental: {sorted(extra)}" if extra else "")
                text_all = (it.que_ha_pasado.text + " " + it.por_que_importa.text).lower()
                for word, code in (("españa", "ES"), ("andorra", "AD")):
                    if word in text_all and code not in doc_jur:
                        rep.add("V-JUR", "B", "efecto indirecto" in text_all, path, f"menciona {word} sin documento de esa jurisdicción")
            check_claim(path + ".que_ha_pasado", it.que_ha_pasado, it.legal_status)
            check_claim(path + ".por_que_importa", it.por_que_importa, it.legal_status)
            # V-DATE
            for dt in it.que_vigilar.dates:
                doc = docs.get(dt.source_id)
                ok = bool(doc) and bool(re.match(r"\d{4}-\d{2}-\d{2}", dt.date)) and any(
                    _norm(v).lower() in _norm(doc["text"]).lower() for v in date_variants(dt.date))
                rep.add("V-DATE", "B", ok, path + ".que_vigilar", f"la fecha {dt.date} no aparece en {dt.source_id}" if not ok else "")
    # V-SUBJECT
    subj = out.subject
    alarm = [a for a in ed["subject_alarm"] if a.lower() in subj.lower()]
    caps = re.findall(r"\b[A-ZÁÉÍÓÚÑ]{5,}\b", subj)
    lexhit = [p.pattern for p in lex if p.search(subj)]
    rep.add("V-SUBJECT", "B", len(subj) <= 70 and not alarm and not caps and not lexhit, "subject",
            f"asunto inválido (longitud {len(subj)}, alarma {alarm}, mayúsculas {caps}, léxico {lexhit})")
    rep.add("V-LEN", "B", len(out.semana_en_60s) <= 3, "semana_en_60s", "más de 3 puntos")
    # V-HASH
    if approved_sha256 is not None and html_body is not None:
        cur = hashlib.sha256(html_body.encode("utf-8")).hexdigest()
        rep.add("V-HASH", "B", cur == approved_sha256, "html", "el contenido cambió después de la aprobación" if cur != approved_sha256 else "")
    return rep


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


__all__ = ["ValidationReport", "validate_daily", "validate_weekly", "quote_in_document", "sha256_text", "html"]
