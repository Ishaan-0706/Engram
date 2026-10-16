from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.ingestion.hashing import decode_utf8_round_trip, sha256_bytes
from app.ingestion.models import LoadedSource


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    rest = text[3:]
    if rest.startswith("\n"):
        rest = rest[1:]
    marker = "\n---"
    end = rest.find(marker)
    if end < 0:
        return {}, text
    raw_fm = rest[:end]
    body = rest[end + len(marker) :].lstrip("\n")
    loaded = yaml.safe_load(raw_fm) or {}
    if not isinstance(loaded, dict):
        raise ValueError("markdown frontmatter must be a YAML mapping")
    return loaded, body


def load_markdown(path: Path) -> LoadedSource:
    raw = path.read_bytes()
    text = decode_utf8_round_trip(raw)
    frontmatter, body = _split_frontmatter(text)
    payload: dict[str, Any] = dict(frontmatter)
    payload["body"] = body
    system = str(payload.get("system") or "markdown")
    external_id = str(payload.get("external_id") or path.stem)
    return LoadedSource(
        path=str(path),
        source_uri=payload.get("source_uri") or path.resolve().as_uri(),
        system=system,
        external_id=external_id,
        raw_bytes=raw,
        text=text,
        content_hash=sha256_bytes(raw),
        payload=payload,
    )
