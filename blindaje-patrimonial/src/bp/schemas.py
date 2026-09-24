"""Carga de los JSON Schemas de schema/llm y validación de instancias (I-SCHEMA)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from bp.config import project_root


@lru_cache(maxsize=1)
def _registry(root: str) -> tuple[Registry, dict[str, dict]]:
    base = Path(root) / "schema" / "llm"
    reg = Registry()
    schemas: dict[str, dict] = {}
    for f in base.glob("*.schema.json"):
        s = json.loads(f.read_text(encoding="utf-8"))
        r = Resource.from_contents(s)
        reg = reg.with_resource(s["$id"], r).with_resource(f.name, r)
        schemas[f.name] = s
    return reg, schemas


def validate_instance(instance: dict, schema_file: str, root: Path | None = None) -> list[str]:
    reg, schemas = _registry(str(root or project_root()))
    v = Draft202012Validator(schemas[schema_file], registry=reg)
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '(raíz)'}: {e.message}" for e in v.iter_errors(instance)]
