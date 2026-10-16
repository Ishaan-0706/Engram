from __future__ import annotations

from app.ingestion.hashing import sha256_bytes
from app.ingestion.models import (
    MIN_EXCERPT_CHARS,
    MAX_EXCERPT_WORDS,
    DecisionDraft,
    EvidenceDraft,
    ExtractedBatch,
    LoadedSource,
)


class UngroundedError(ValueError):
    pass


def find_span(text: str, excerpt: str) -> tuple[int, int] | None:
    if not excerpt:
        return None
    start = text.find(excerpt)
    if start < 0:
        return None
    return start, start + len(excerpt)


def verify_excerpt(source: LoadedSource, excerpt: str, start: int, end: int) -> None:
    if sha256_bytes(source.raw_bytes) != source.content_hash:
        raise UngroundedError("source content_hash does not match SHA-256 of raw bytes")
    words = excerpt.split()
    if len(excerpt) < MIN_EXCERPT_CHARS:
        raise UngroundedError("excerpt shorter than minimum")
    if len(words) > MAX_EXCERPT_WORDS:
        raise UngroundedError("excerpt exceeds 300 words")
    if start < 0 or end > len(source.text) or start >= end:
        raise UngroundedError("excerpt offsets out of range")
    if source.text[start:end] != excerpt:
        raise UngroundedError("excerpt is not a verbatim slice of the source")


def validate_batch(batch: ExtractedBatch) -> ExtractedBatch:
    source = batch.source
    kept_evidence: list[EvidenceDraft] = []
    for ev in batch.evidence:
        try:
            span = (ev.start_offset, ev.end_offset)
            if source.text[span[0] : span[1]] != ev.excerpt:
                found = find_span(source.text, ev.excerpt)
                if found is None:
                    raise UngroundedError("excerpt not in source")
                ev.start_offset, ev.end_offset = found
            verify_excerpt(source, ev.excerpt, ev.start_offset, ev.end_offset)
        except UngroundedError:
            batch.ungrounded_rejected += 1
            continue
        kept_evidence.append(ev)

    kept_decisions: list[DecisionDraft] = []
    for decision in batch.decisions:
        try:
            found = find_span(source.text, decision.excerpt)
            if found is None:
                raise UngroundedError("decision excerpt not in source")
            verify_excerpt(source, decision.excerpt, found[0], found[1])
        except UngroundedError:
            batch.ungrounded_rejected += 1
            continue
        if not any(decision.excerpt in ev.excerpt or ev.excerpt in decision.excerpt for ev in kept_evidence):
            kept_evidence.append(
                EvidenceDraft(
                    excerpt=decision.excerpt,
                    start_offset=found[0],
                    end_offset=found[1],
                    chunk_index=len(kept_evidence),
                    token_count=len(decision.excerpt.split()),
                    derived_from_label="Decision",
                    derived_from_id=decision.local_id,
                )
            )
        kept_decisions.append(decision)

    batch.evidence = kept_evidence
    batch.decisions = kept_decisions
    return batch
