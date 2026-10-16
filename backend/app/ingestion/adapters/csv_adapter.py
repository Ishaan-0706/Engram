from __future__ import annotations

import csv
import io
from pathlib import Path

from app.ingestion.hashing import decode_utf8_round_trip, sha256_bytes
from app.ingestion.models import LoadedSource


def load_csv(path: Path) -> LoadedSource:
    raw = path.read_bytes()
    text = decode_utf8_round_trip(raw)
    reader = csv.DictReader(io.StringIO(text))
    tickets = [dict(row) for row in reader]
    return LoadedSource(
        path=str(path),
        source_uri=path.resolve().as_uri(),
        system="csv",
        external_id=path.stem,
        raw_bytes=raw,
        text=text,
        content_hash=sha256_bytes(raw),
        payload={"system": "csv", "external_id": path.stem, "tickets": tickets},
    )
