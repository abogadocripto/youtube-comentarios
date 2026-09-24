"""Carga y validación de la configuración (config/*.yaml).

La YAML es la fuente de verdad (docs/02, docs/04). Este módulo la carga una vez, comprueba la coherencia
entre catálogos (métricas ↔ fuentes ↔ reglas) y expone accesores tipados mínimos.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PUBLISHABLE_LICENCES = {"self_computed", "official_open", "licensed_public"}
ALL_LICENCES = PUBLISHABLE_LICENCES | {"permission_pending", "internal_only", "prohibited"}
LAYERS = {"N", "C", "B"}

_ISO_DUR = re.compile(r"^P(?:(?P<d>\d+)D)?(?:T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?)?$")


def parse_iso_duration(value: str) -> timedelta:
    """Convierte duraciones ISO-8601 sencillas (P2D, PT15M, P1DT6H) en timedelta."""
    m = _ISO_DUR.match(value)
    if not m or value in ("P", "PT"):
        raise ValueError(f"Duración ISO-8601 no soportada: {value!r}")
    parts = {k: int(v) if v else 0 for k, v in m.groupdict().items()}
    return timedelta(days=parts["d"], hours=parts["h"], minutes=parts["m"], seconds=parts["s"])


def project_root() -> Path:
    env = os.environ.get("BP_ROOT")
    if env:
        return Path(env)
    # src/bp/config.py → raíz del proyecto (blindaje-patrimonial/)
    return Path(__file__).resolve().parents[2]


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class MetricDef:
    id: str
    raw: dict[str, Any]

    @property
    def label_es(self) -> str:
        return self.raw["label_es"]

    @property
    def family(self) -> str:
        return self.raw["family"]

    @property
    def axis(self) -> str:
        return self.raw["axis"]

    @property
    def unit(self) -> str:
        return self.raw["unit"]

    @property
    def fmt(self) -> str:
        return self.raw["fmt"]

    @property
    def layer(self) -> str:
        return self.raw["layer"]

    @property
    def mvp(self) -> bool:
        return bool(self.raw["mvp"])

    @property
    def licence(self) -> str:
        return self.raw["licence"]

    @property
    def max_staleness(self) -> timedelta:
        return parse_iso_duration(self.raw["max_staleness"])

    @property
    def primary_source(self) -> str | None:
        p = self.raw.get("primary")
        return p.get("source") if isinstance(p, dict) else None

    @property
    def caveat(self) -> dict[str, Any] | None:
        return self.raw.get("caveat")


@dataclass
class Config:
    root: Path
    metrics: dict[str, MetricDef]
    sources: dict[str, dict[str, Any]]
    rules: dict[str, Any]
    editorial: dict[str, Any]
    llm: dict[str, Any]
    fomc: dict[str, Any]
    news_sources: dict[str, Any]
    regulatory: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    # ─── accesores ───
    def metric(self, metric_id: str) -> MetricDef:
        try:
            return self.metrics[metric_id]
        except KeyError as exc:
            raise ConfigError(f"Métrica desconocida: {metric_id}") from exc

    def source(self, source_id: str) -> dict[str, Any]:
        try:
            return self.sources[source_id]
        except KeyError as exc:
            raise ConfigError(f"Fuente desconocida: {source_id}") from exc

    def source_publishable(self, source_id: str) -> bool:
        return self.source(source_id).get("licence") in PUBLISHABLE_LICENCES

    def source_llm_allowed(self, source_id: str) -> bool:
        return bool(self.source(source_id).get("llm_input_allowed", False))

    def prompt_path(self, name: str) -> Path:
        return self.root / "prompts" / name


class _Loader(yaml.SafeLoader):
    """SafeLoader que reconoce la notación científica de YAML 1.2 (1.5e11, -2e9), que PyYAML (YAML 1.1) lee como texto."""


_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^[-+]?(?:[0-9][0-9_]*)(?:\.[0-9_]*)?[eE][-+]?[0-9]+$|" + _Loader.yaml_implicit_resolvers["1"][0][1].pattern,
               re.X),
    list("-+0123456789."),
)


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.load(fh, Loader=_Loader)  # noqa: S506 (_Loader deriva de SafeLoader)
    if not isinstance(data, dict):
        raise ConfigError(f"{path} no contiene un mapa YAML")
    return data


REQUIRED_METRIC_FIELDS = ("label_es", "family", "axis", "unit", "fmt", "freq", "as_of", "max_staleness", "layer", "mvp", "licence")
# Entradas auxiliares que aparecen en derived_from pero no son métricas publicables del catálogo.
AUXILIARY_INPUTS = {
    "market_cap_usd", "realized_cap_usd", "m2_us", "m2_ea", "m2_jp", "m2_cn", "m4_uk", "fx_ecb",
    "us_net_liquidity_chg_4w_usd", "global_m2_fx_effect_pct",
}


def validate(cfg: Config) -> list[str]:
    """Devuelve la lista de errores de coherencia (vacía si todo es correcto)."""
    errors: list[str] = []
    for mid, m in cfg.metrics.items():
        for f in REQUIRED_METRIC_FIELDS:
            if f not in m.raw:
                errors.append(f"métrica {mid}: falta el campo {f}")
        if m.raw.get("layer") not in LAYERS:
            errors.append(f"métrica {mid}: capa inválida {m.raw.get('layer')!r}")
        if m.raw.get("licence") not in ALL_LICENCES:
            errors.append(f"métrica {mid}: licencia inválida {m.raw.get('licence')!r}")
        try:
            parse_iso_duration(m.raw.get("max_staleness", ""))
        except ValueError as exc:
            errors.append(f"métrica {mid}: {exc}")
        src = m.primary_source
        if src and src not in cfg.sources:
            errors.append(f"métrica {mid}: fuente primaria {src!r} no está en sources.yaml")
        for fb in m.raw.get("fallback", []) or []:
            if fb.get("source") not in cfg.sources:
                errors.append(f"métrica {mid}: fuente de respaldo {fb.get('source')!r} no está en sources.yaml")
        for dep in m.raw.get("derived_from", []) or []:
            if dep not in cfg.metrics and dep not in AUXILIARY_INPUTS:
                errors.append(f"métrica {mid}: entrada derivada desconocida {dep!r}")
        # una métrica publicable no puede depender de una fuente primaria no publicable
        if src and m.licence in PUBLISHABLE_LICENCES and src in cfg.sources and not cfg.source_publishable(src):
            errors.append(
                f"métrica {mid}: licencia {m.licence} incoherente con su fuente {src} ({cfg.sources[src].get('licence')})"
            )
    for sid, s in cfg.sources.items():
        if s.get("licence") not in ALL_LICENCES:
            errors.append(f"fuente {sid}: licencia inválida {s.get('licence')!r}")
    sal = cfg.rules.get("salience", {})
    for mid in list(sal.get("core_always", [])) + list(sal.get("z_basis", {})):
        if mid not in cfg.metrics:
            errors.append(f"rules.salience: métrica desconocida {mid}")
    w = sal.get("weights", {})
    if w and abs(sum(w.values()) - 1.0) > 1e-9:
        errors.append(f"rules.salience.weights debe sumar 1 (suma {sum(w.values())})")
    nw = cfg.rules.get("news", {}).get("weights", {})
    if nw and abs(sum(nw.values()) - 1.0) > 1e-9:
        errors.append(f"rules.news.weights debe sumar 1 (suma {sum(nw.values())})")
    for name in {c.get("prompt_system") for c in cfg.llm.get("calls", {}).values()} | {
        c.get("prompt_user") for c in cfg.llm.get("calls", {}).values()
    }:
        if name and not cfg.prompt_path(name).exists():
            errors.append(f"llm.yaml: prompt inexistente {name}")
    return errors


@lru_cache(maxsize=4)
def load_config(root: str | None = None) -> Config:
    base = Path(root) if root else project_root()
    c = base / "config"
    metrics_raw = _load_yaml(c / "metrics.yaml")["metrics"]
    cfg = Config(
        root=base,
        metrics={k: MetricDef(k, v) for k, v in metrics_raw.items()},
        sources=_load_yaml(c / "sources.yaml")["sources"],
        rules=_load_yaml(c / "rules.yaml"),
        editorial=_load_yaml(c / "editorial.yaml"),
        llm=_load_yaml(c / "llm.yaml"),
        fomc=_load_yaml(c / "fomc.yaml"),
        news_sources=_load_yaml(c / "news_sources.yaml"),
        regulatory=_load_yaml(c / "calendar" / "regulatory.yaml"),
    )
    errors = validate(cfg)
    if errors:
        raise ConfigError("Configuración incoherente:\n- " + "\n- ".join(errors))
    return cfg
