"""Filtro de licencias (docs/02 §1, validadores I-LIC y V-LIC).

Una métrica es publicable si:
  1) su licencia en el catálogo no es `prohibited` ni `internal_only`; y
  2) la fuente de la observación (o, si es calculada, su fuente primaria) es publicable
     (self_computed | official_open | licensed_public); y
  3) si es derivada, TODAS sus entradas son publicables (un dato calculado hereda las restricciones de sus insumos).
Así, cuando un proveedor concede permiso basta con cambiar su licencia en config/sources.yaml.
"""

from __future__ import annotations

from bp.config import Config

BLOCKED_METRIC_LICENCES = {"prohibited", "internal_only"}


def metric_publishable(cfg: Config, metric_id: str, obs_source_id: str | None = None, _seen: set[str] | None = None) -> bool:
    seen = _seen or set()
    if metric_id in seen:
        return True
    seen.add(metric_id)
    m = cfg.metrics.get(metric_id)
    if m is None or m.licence in BLOCKED_METRIC_LICENCES:
        return False
    sources: set[str] = set()
    if obs_source_id and obs_source_id != "computed":
        sources.add(obs_source_id)
    elif m.primary_source and not m.raw.get("derived_from"):
        sources.add(m.primary_source)
    for dep in m.raw.get("derived_from", []) or []:
        if dep in cfg.metrics and not metric_publishable(cfg, dep, None, seen):
            return False
    for comp in (m.raw.get("components") or {}).values():
        src = comp.get("source")
        if comp.get("licence") == "permission_pending":
            continue            # componente excluible (p. ej. BoJ): el agregado lo omite si no hay permiso
        if src:
            sources.add(src)
    return all(s in cfg.sources and cfg.source_publishable(s) for s in sources)


def metric_llm_allowed(cfg: Config, metric_id: str, obs_source_id: str | None = None) -> bool:
    m = cfg.metrics.get(metric_id)
    if m is None:
        return False
    src = obs_source_id if obs_source_id and obs_source_id != "computed" else m.primary_source
    return src is None or src == "computed" or cfg.source_llm_allowed(src)
