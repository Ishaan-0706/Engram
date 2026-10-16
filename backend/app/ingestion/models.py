from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


MIN_EXCERPT_CHARS = 40
MAX_EXCERPT_WORDS = 300
EXTRACTOR_VERSION = "ingest-1"


@dataclass
class LoadedSource:
    path: str
    source_uri: str
    system: str
    external_id: str
    raw_bytes: bytes
    text: str
    content_hash: str
    payload: dict[str, Any]


@dataclass
class PersonRef:
    name: str | None = None
    canonical_email: str | None = None
    identity_key: str | None = None
    role: str | None = None
    source_local_id: str | None = None


@dataclass
class EvidenceDraft:
    excerpt: str
    start_offset: int
    end_offset: int
    chunk_index: int
    token_count: int
    valid_from: str | None = None
    valid_to: str | None = None
    derived_from_label: str | None = None
    derived_from_id: str | None = None


@dataclass
class DecisionDraft:
    local_id: str
    summary: str
    timestamp: str | None
    status: str
    excerpt: str
    project_id: str | None = None
    recorded_in_id: str | None = None


@dataclass
class EdgeDraft:
    rel_type: str
    from_label: str
    from_ref: str
    to_label: str
    to_id: str
    temporal: bool = False


@dataclass
class ExtractedBatch:
    source: LoadedSource
    people: list[PersonRef] = field(default_factory=list)
    teams: list[dict[str, Any]] = field(default_factory=list)
    projects: list[dict[str, Any]] = field(default_factory=list)
    tickets: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[EvidenceDraft] = field(default_factory=list)
    decisions: list[DecisionDraft] = field(default_factory=list)
    edges: list[EdgeDraft] = field(default_factory=list)
    ungrounded_rejected: int = 0
