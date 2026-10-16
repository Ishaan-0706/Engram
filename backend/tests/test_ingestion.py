from __future__ import annotations

import json
from pathlib import Path

from engram_graph_core.store import InMemoryGraphStore, open_store

from app.ingestion.adapters import load_fixtures
from app.ingestion.extract import extract
from app.ingestion.hashing import sha256_bytes
from app.ingestion.models import DecisionDraft, EvidenceDraft, ExtractedBatch, LoadedSource, PersonRef
from app.ingestion.resolve_entities import resolve_person
from app.ingestion.sync import ingest_dir, main
from app.ingestion.validate import UngroundedError, validate_batch, verify_excerpt

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ingest"


def _store() -> InMemoryGraphStore:
    return open_store("018f0000-0000-7000-8000-000000000001", backend="memory")


def test_adapters_hash_and_source_payload():
    loaded = load_fixtures(FIXTURES)
    by_suffix = {Path(item.path).suffix: item for item in loaded}
    assert set(by_suffix) >= {".json", ".md", ".csv"}
    for item in loaded:
        assert item.content_hash == sha256_bytes(item.raw_bytes)
        assert item.text.encode("utf-8") == item.raw_bytes


def test_rejects_ungrounded_excerpt_and_short_decision():
    source = LoadedSource(
        path="mem",
        source_uri="mem:test",
        system="test",
        external_id="t1",
        raw_bytes=b"Compatibility tests are failing on the new endpoint and block the payments migration.",
        text="Compatibility tests are failing on the new endpoint and block the payments migration.",
        content_hash=sha256_bytes(
            b"Compatibility tests are failing on the new endpoint and block the payments migration."
        ),
        payload={},
    )
    text = source.text
    good = text
    batch = ExtractedBatch(
        source=source,
        evidence=[
            EvidenceDraft(
                excerpt="this excerpt does not appear in the source document at all!!",
                start_offset=0,
                end_offset=10,
                chunk_index=0,
                token_count=10,
            ),
            EvidenceDraft(
                excerpt=good,
                start_offset=0,
                end_offset=len(good),
                chunk_index=1,
                token_count=len(good.split()),
            ),
        ],
        decisions=[
            DecisionDraft(
                local_id="bad",
                summary="nope",
                timestamp=None,
                status="recorded",
                excerpt="xyz",
            ),
            DecisionDraft(
                local_id="ok",
                summary="pause",
                timestamp=None,
                status="recorded",
                excerpt=good,
            ),
        ],
    )
    out = validate_batch(batch)
    assert out.ungrounded_rejected >= 2
    assert len(out.decisions) == 1
    assert out.decisions[0].local_id == "ok"
    broken = LoadedSource(**{**source.__dict__, "content_hash": "sha256:" + ("0" * 64)})
    try:
        verify_excerpt(broken, source.text, 0, len(source.text))
        raise AssertionError("expected hash mismatch")
    except UngroundedError:
        pass


def test_identity_resolution_is_exact_only():
    store = InMemoryGraphStore("tenant:t")
    ada = resolve_person(
        PersonRef(name="Ada", canonical_email="ada@example.test", identity_key="slack:U123"),
        store,
    )
    again = resolve_person(PersonRef(canonical_email="ADA@example.test"), store)
    assert again["id"] == ada["id"]
    via_slack = resolve_person(PersonRef(identity_key="slack:U123"), store)
    assert via_slack["id"] == ada["id"]
    contractor = resolve_person(PersonRef(name="Unknown Contractor"), store)
    assert contractor["needs_identity_link"] is True
    assert contractor["id"] != ada["id"]
    other = resolve_person(PersonRef(name="Ada Lovelace"), store)
    assert other["id"] != ada["id"]
    assert other["needs_identity_link"] is True


def test_ingest_is_idempotent_and_rejects_ungrounded_json_decision():
    store = _store()
    first = ingest_dir(store, FIXTURES)
    assert first.sources == 3
    assert first.ungrounded_items_rejected >= 1
    assert store.get_node("Source", "src_handbook_org-export")
    ada = store.find_person_by_email("ada@example.test")
    assert ada is not None
    assert store.find_person_by_identity("slack:U123")["id"] == ada["id"]
    assert store.find_person_by_identity("linear:usr_456") is not None
    owns = store.active_edges("OWNS", "proj_payments")
    assert len(owns) == 1
    assert owns[0]["from_id"] == ada["id"]
    decision = store.get_node("Decision", "dec_pause")
    assert decision is not None
    assert store.get_node("Decision", "dec_ungrounded") is None
    assert store.get_node("Decision", "dec_dec_ungrounded") is None
    created = first.nodes_created
    second = ingest_dir(store, FIXTURES)
    assert second.nodes_created == 0
    assert store.stats.nodes_created == created
    assert len(store.active_edges("OWNS", "proj_payments")) == 1


def test_cli_prints_metrics(capsys, tmp_path):
    code = main(
        [
            "--tenant",
            "018f0000-0000-7000-8000-000000000001",
            "--fixtures-dir",
            str(FIXTURES),
            "--backend",
            "memory",
        ]
    )
    assert code == 0
    metrics = json.loads(capsys.readouterr().out.strip())
    assert metrics["sources"] == 3
    assert "nodes_created" in metrics
    assert "relationships_updated" in metrics
    assert metrics["ungrounded_items_rejected"] >= 1
