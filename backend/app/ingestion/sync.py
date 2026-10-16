from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engram_graph_core.store import GraphStore, WriteStats, open_store

from app.ingestion.adapters import load_fixtures
from app.ingestion.extract import extract
from app.ingestion.models import EXTRACTOR_VERSION, ExtractedBatch
from app.ingestion.resolve_entities import resolve_batch
from app.ingestion.validate import validate_batch


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _props(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def _source_id(system: str, external_id: str) -> str:
    return f"src_{system}_{external_id}"


def write_batch(batch: ExtractedBatch, store: GraphStore, *, ingested_at: str | None = None) -> None:
    ingested_at = ingested_at or _now()
    source = batch.source
    sid = _source_id(source.system, source.external_id)
    store.merge_node(
        "Source",
        sid,
        _props(
            {
                "id": sid,
                "uri": source.source_uri,
                "source_type": source.system,
                "system": source.system,
                "external_id": source.external_id,
                "content_hash": source.content_hash,
                "ingested_at": ingested_at,
            }
        ),
    )

    people_ids = resolve_batch(batch, store)

    for team in batch.teams:
        store.merge_node("Team", team["id"], _props({"id": team["id"], "name": team.get("name")}))
    for project in batch.projects:
        store.merge_node(
            "Project",
            project["id"],
            _props({"id": project["id"], "name": project.get("name"), "status": project.get("status")}),
        )
    for ticket in batch.tickets:
        store.merge_node(
            "Ticket",
            ticket["id"],
            _props(
                {
                    "id": ticket["id"],
                    "title": ticket.get("title"),
                    "status": ticket.get("status"),
                    "priority": ticket.get("priority"),
                    "external_id": ticket.get("external_id"),
                    "source_uri": source.source_uri,
                }
            ),
        )
    for doc in batch.documents:
        store.merge_node(
            "Document",
            doc["id"],
            _props({"id": doc["id"], "title": doc.get("title"), "uri": source.source_uri}),
        )

    evidence_ids: list[str] = []
    for ev in batch.evidence:
        eid = f"ev_{sid}_{ev.start_offset}_{ev.end_offset}"
        evidence_ids.append(eid)
        store.merge_node(
            "Evidence",
            eid,
            _props(
                {
                    "id": eid,
                    "excerpt": ev.excerpt,
                    "chunk_index": ev.chunk_index,
                    "token_count": ev.token_count,
                    "start_offset": ev.start_offset,
                    "end_offset": ev.end_offset,
                    "extractor_ver": EXTRACTOR_VERSION,
                    "confidence": 1.0,
                    "valid_from": ev.valid_from or ingested_at,
                    "valid_to": ev.valid_to,
                    "content_hash": source.content_hash,
                }
            ),
        )
        store.merge_edge("PART_OF", "Evidence", eid, "Source", sid)

    for decision in batch.decisions:
        did = decision.local_id if decision.local_id.startswith("dec_") else f"dec_{decision.local_id}"
        store.merge_node(
            "Decision",
            did,
            _props(
                {
                    "id": did,
                    "summary": decision.summary,
                    "timestamp": decision.timestamp,
                    "status": decision.status,
                }
            ),
        )
        supported = False
        for ev, eid in zip(batch.evidence, evidence_ids):
            if decision.excerpt in ev.excerpt or ev.excerpt in decision.excerpt:
                store.merge_edge("SUPPORTED_BY", "Decision", did, "Evidence", eid)
                supported = True
        if not supported:
            raise RuntimeError(f"decision {did} has no SUPPORTED_BY evidence after validation")
        if decision.project_id:
            store.merge_edge("HAS_DECISION", "Project", decision.project_id, "Decision", did)

    for edge in batch.edges:
        from_id = people_ids.get(edge.from_ref, edge.from_ref)
        if edge.temporal:
            store.supersede_temporal(
                edge.rel_type,
                edge.from_label,
                from_id,
                edge.to_label,
                edge.to_id,
                valid_from=ingested_at,
                ingested_at=ingested_at,
            )
        else:
            store.merge_edge(
                edge.rel_type,
                edge.from_label,
                from_id,
                edge.to_label,
                edge.to_id,
            )


@dataclass
class IngestMetrics:
    sources: int = 0
    nodes_created: int = 0
    nodes_merged: int = 0
    relationships_created: int = 0
    relationships_updated: int = 0
    ungrounded_items_rejected: int = 0


def ingest_dir(store: GraphStore, fixtures_dir: Path) -> IngestMetrics:
    metrics = IngestMetrics()
    start = WriteStats(
        nodes_created=store.stats.nodes_created,
        nodes_merged=store.stats.nodes_merged,
        relationships_created=store.stats.relationships_created,
        relationships_updated=store.stats.relationships_updated,
    )
    for source in load_fixtures(fixtures_dir):
        batch = validate_batch(extract(source))
        metrics.ungrounded_items_rejected += batch.ungrounded_rejected
        write_batch(batch, store)
        metrics.sources += 1
    metrics.nodes_created = store.stats.nodes_created - start.nodes_created
    metrics.nodes_merged = store.stats.nodes_merged - start.nodes_merged
    metrics.relationships_created = store.stats.relationships_created - start.relationships_created
    metrics.relationships_updated = store.stats.relationships_updated - start.relationships_updated
    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest fixtures into a tenant graph")
    parser.add_argument("--tenant", required=True, help="tenant uuid (server-side graph key)")
    parser.add_argument("--fixtures-dir", required=True, type=Path)
    parser.add_argument("--backend", default=None, help="falkordb or memory")
    args = parser.parse_args(argv)
    store = open_store(args.tenant, backend=args.backend)
    metrics = ingest_dir(store, args.fixtures_dir)
    json.dump(asdict(metrics), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
