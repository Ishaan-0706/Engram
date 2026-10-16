from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.ingestion.hashing import decode_utf8_round_trip, sha256_bytes
from app.ingestion.models import LoadedSource


def load_json(path: Path) -> LoadedSource:
    raw = path.read_bytes()
    text = decode_utf8_round_trip(raw)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    payload: dict[str, Any] = dict(data)
    system = str(payload.get("system") or "json")
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
