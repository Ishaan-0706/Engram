from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"

_SCHEMA_FILES = {
    "mcp-tool-response": "mcp-tool-response.schema.json",
    "mcp-envelope": "mcp-tool-response.schema.json",
    "mcp_envelope": "mcp-tool-response.schema.json",
    "jwt-tenant-claims": "jwt-tenant-claims.schema.json",
    "agent-turn-state": "agent-turn-state.schema.json",
    "synthesis-answer": "synthesis-answer.schema.json",
    "action-confirm": "action-confirm.schema.json",
}


def _load_raw(name: str) -> dict:
    if name in _SCHEMA_FILES:
        path = CONTRACTS_DIR / _SCHEMA_FILES[name]
    elif (CONTRACTS_DIR / name).is_file():
        path = CONTRACTS_DIR / name
    elif Path(name).is_file():
        path = Path(name)
    elif (Path(__file__).resolve().parents[2] / name).is_file():
        path = Path(__file__).resolve().parents[2] / name
    else:
        stem = Path(name).stem.replace("_", "-")
        if stem in _SCHEMA_FILES:
            path = CONTRACTS_DIR / _SCHEMA_FILES[stem]
        else:
            path = CONTRACTS_DIR / _SCHEMA_FILES[name]
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def _registry() -> Registry:
    registry = Registry()
    for name in _SCHEMA_FILES:
        schema = _load_raw(name)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry


def validator(name: str) -> Draft202012Validator:
    schema = _load_raw(name)
    return Draft202012Validator(
        schema,
        registry=_registry(),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def validate(name: str, instance: object) -> None:
    validator(name).validate(instance)
