from __future__ import annotations

from pathlib import Path

from app.ingestion.adapters.csv_adapter import load_csv
from app.ingestion.adapters.json_adapter import load_json
from app.ingestion.adapters.markdown_adapter import load_markdown
from app.ingestion.models import LoadedSource

_LOADERS = {
    ".json": load_json,
    ".md": load_markdown,
    ".markdown": load_markdown,
    ".csv": load_csv,
}


def load_fixtures(fixtures_dir: Path) -> list[LoadedSource]:
    if not fixtures_dir.is_dir():
        raise FileNotFoundError(fixtures_dir)
    loaded: list[LoadedSource] = []
    for path in sorted(fixtures_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _LOADERS:
            continue
        loaded.append(_LOADERS[path.suffix.lower()](path))
    return loaded
