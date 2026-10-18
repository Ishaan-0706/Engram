"""Seed script for tenant_nexus_infra graph.

Seeds an isolated Infrastructure / Platform Engineering domain graph:
- Graph: tenant_nexus_infra
- People: Devin Vance (Principal SRE), Elena Rostova (Platform Lead)
- System: event-stream-cluster
- Document: Event Bus Partitioning SOP v2 (stale)
- Decisions:
  - dec_018f_zookeeper (superseded)
  - dec_018f_kraft (active, supersedes zookeeper)
- Source & Evidence:
  - Linear ticket ENG-4091 excerpt with valid SHA-256 hash
- Relationships:
  - (elena)-[:OWNS]->(kafka)
  - (doc)-[:DOCUMENTS]->(kafka)
  - (doc)-[:PROPOSED]->(zookeeper)
  - (kraft)-[:AFFECTS]->(kafka)
  - (kraft)-[:SUPERSEDES {reason: "Cross-AZ consensus timeouts"}]->(zookeeper)
  - (devin)-[:ESTABLISHED]->(kraft)
  - (kraft)-[:SUPPORTED_BY]->(evidence)
  - (evidence)-[:PART_OF]->(source)
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any

# Ensure backend root is on sys.path
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from falkordb import FalkorDB

from engram_graph_core.bootstrap import INDEXES, UNIQUE_NODE_CONSTRAINTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

GRAPH_NAME = "tenant_nexus_infra"

EXCERPT = (
    "Migrated event-stream-cluster to KRaft mode on 2026-08-14 after ZooKeeper "
    "consensus timeouts triggered cross-AZ partition deadlocks."
)
SOURCE_URI = "linear://nexus-infra/issue/ENG-4091"
SOURCE_TIMESTAMP = "2026-08-14T15:30:00Z"

# Compute canonical content hash
DIGEST = hashlib.sha256(f"{EXCERPT}\n{SOURCE_URI}".encode("utf-8")).hexdigest()
CONTENT_HASH = f"sha256:{DIGEST}"


def bootstrap_indexes(graph: Any, name: str) -> None:
    """Bootstrap Cypher indexes and unique constraints for the graph."""
    log.info("Bootstrapping indexes on %s...", name)
    for stmt in INDEXES:
        try:
            graph.query(stmt)
        except Exception as exc:
            msg = str(exc).lower()
            if "already indexed" in msg or "already exists" in msg:
                continue
            log.warning("Index statement %s: %s", stmt, exc)

    # Extra exact-match indexes for System(name) and System(id)
    for extra_stmt in [
        "CREATE INDEX FOR (s:System) ON (s.id)",
        "CREATE INDEX FOR (s:System) ON (s.name)",
    ]:
        try:
            graph.query(extra_stmt)
        except Exception as exc:
            msg = str(exc).lower()
            if "already indexed" in msg or "already exists" in msg:
                continue

    client = getattr(graph, "_client", None) or getattr(graph, "client", None)
    redis_conn = getattr(client, "connection", None) or getattr(client, "_redis", None)
    if redis_conn is not None:
        constraints = list(UNIQUE_NODE_CONSTRAINTS) + [("System", ["id"])]
        for label, props in constraints:
            try:
                redis_conn.execute_command(
                    "GRAPH.CONSTRAINT",
                    "CREATE",
                    name,
                    "UNIQUE",
                    "NODE",
                    label,
                    "PROPERTIES",
                    str(len(props)),
                    *props,
                )
            except Exception as exc:
                msg = str(exc).lower()
                if "already" in msg or "constraint" in msg or "pending" in msg:
                    continue
                log.debug("Constraint on %s: %s", label, exc)


def seed_nexus_infra(
    host: str | None = None,
    port: int | None = None,
    reset: bool = True,
) -> None:
    """Seed the tenant_nexus_infra graph with the platform scenario."""
    host = host or os.environ.get("FALKORDB_HOST", "localhost")
    port = int(port or os.environ.get("FALKORDB_PORT", "6379"))

    db = FalkorDB(host=host, port=port)

    if reset and GRAPH_NAME in db.list_graphs():
        log.info("Resetting existing graph: %s", GRAPH_NAME)
        db.select_graph(GRAPH_NAME).delete()

    graph = db.select_graph(GRAPH_NAME)

    # 1. Bootstrap indexes
    bootstrap_indexes(graph, GRAPH_NAME)

    # 2. Seed Nodes
    log.info("Creating entities in %s...", GRAPH_NAME)

    # People
    graph.query(
        """
        MERGE (d:Person {id: $id})
        SET d.display_name = $display_name,
            d.canonical_email = $canonical_email,
            d.role = $role
        """,
        {
            "id": "usr_018f_devin",
            "display_name": "Devin Vance",
            "canonical_email": "devin@nexus.io",
            "role": "Principal SRE",
        },
    )

    graph.query(
        """
        MERGE (e:Person {id: $id})
        SET e.display_name = $display_name,
            e.canonical_email = $canonical_email,
            e.role = $role
        """,
        {
            "id": "usr_018f_elena",
            "display_name": "Elena Rostova",
            "canonical_email": "elena@nexus.io",
            "role": "Platform Lead",
        },
    )

    # System
    graph.query(
        """
        MERGE (s:System {id: $id})
        SET s.name = $name,
            s.status = $status
        """,
        {
            "id": "sys_018f_kafka",
            "name": "event-stream-cluster",
            "status": "active",
        },
    )

    # Document
    graph.query(
        """
        MERGE (doc:Document {id: $id})
        SET doc.title = $title,
            doc.status = $status,
            doc.uri = $uri
        """,
        {
            "id": "doc_018f_kafka_runbook",
            "title": "Event Bus Partitioning SOP v2",
            "status": "stale",
            "uri": "notion://nexus/eng/event-bus-v2",
        },
    )

    # Decisions
    now_ms = int(time.time() * 1000)
    anchor_ts = now_ms - (62 * 86400 * 1000)
    graph.query(
        """
        MERGE (d:Decision {id: $id})
        SET d.summary = $summary,
            d.status = $status,
            d.timestamp = $timestamp
        """,
        {
            "id": "dec_018f_zookeeper",
            "summary": "Use ZooKeeper for partition leadership",
            "status": "superseded",
            "timestamp": anchor_ts,
        },
    )

    graph.query(
        """
        MERGE (d:Decision {id: $id})
        SET d.summary = $summary,
            d.status = $status,
            d.timestamp = $timestamp
        """,
        {
            "id": "dec_018f_kraft",
            "summary": "Migrate to KRaft metadata quorum to remove ZK bottleneck",
            "status": "active",
            "timestamp": now_ms,
        },
    )

    # Source & Evidence
    graph.query(
        """
        MERGE (src:Source {id: $id})
        SET src.uri = $uri,
            src.source_type = $source_type,
            src.content_hash = $content_hash
        """,
        {
            "id": "src_018f_linear_eng_4091",
            "uri": SOURCE_URI,
            "source_type": "linear",
            "content_hash": DIGEST,
        },
    )

    graph.query(
        """
        MERGE (evi:Evidence {id: $id})
        SET evi.record_id = $record_id,
            evi.excerpt = $excerpt,
            evi.source_uri = $source_uri,
            evi.source_timestamp = $source_timestamp,
            evi.valid_from = $valid_from,
            evi.content_hash = $content_hash
        """,
        {
            "id": "evi_018f_kraft_consensus",
            "record_id": "dec_018f_kraft",
            "excerpt": EXCERPT,
            "source_uri": SOURCE_URI,
            "source_timestamp": SOURCE_TIMESTAMP,
            "valid_from": 1723650000000,
            "content_hash": DIGEST,
        },
    )

    # 3. Seed Relationships
    log.info("Creating relationships in %s...", GRAPH_NAME)

    # (elena)-[:OWNS {valid_from: 1710000000000, valid_to: null}]->(sys_018f_kafka)
    graph.query(
        """
        MATCH (p:Person {id: 'usr_018f_elena'})
        MATCH (s:System {id: 'sys_018f_kafka'})
        CREATE (p)-[:OWNS {valid_from: 1710000000000, valid_to: null}]->(s)
        """
    )

    # (doc_018f_kafka_runbook)-[:DOCUMENTS]->(sys_018f_kafka)
    graph.query(
        """
        MATCH (doc:Document {id: 'doc_018f_kafka_runbook'})
        MATCH (s:System {id: 'sys_018f_kafka'})
        MERGE (doc)-[:DOCUMENTS]->(s)
        """
    )

    # (doc_018f_kafka_runbook)-[:PROPOSED]->(dec_018f_zookeeper)
    graph.query(
        """
        MATCH (doc:Document {id: 'doc_018f_kafka_runbook'})
        MATCH (dec:Decision {id: 'dec_018f_zookeeper'})
        MERGE (doc)-[:PROPOSED]->(dec)
        """
    )

    # (dec_018f_kraft)-[:AFFECTS]->(sys_018f_kafka)
    graph.query(
        """
        MATCH (dec:Decision {id: 'dec_018f_kraft'})
        MATCH (s:System {id: 'sys_018f_kafka'})
        MERGE (dec)-[:AFFECTS]->(s)
        """
    )

    # (dec_018f_kraft)-[:SUPERSEDES {reason: "Cross-AZ consensus timeouts"}]->(dec_018f_zookeeper)
    graph.query(
        """
        MATCH (kraft:Decision {id: 'dec_018f_kraft'})
        MATCH (zk:Decision {id: 'dec_018f_zookeeper'})
        MERGE (kraft)-[:SUPERSEDES {reason: 'Cross-AZ consensus timeouts'}]->(zk)
        """
    )

    # (devin)-[:ESTABLISHED]->(dec_018f_kraft)
    graph.query(
        """
        MATCH (devin:Person {id: 'usr_018f_devin'})
        MATCH (kraft:Decision {id: 'dec_018f_kraft'})
        MERGE (devin)-[:ESTABLISHED]->(kraft)
        """
    )

    # (dec_018f_kraft)-[:SUPPORTED_BY]->(evidence)
    graph.query(
        """
        MATCH (kraft:Decision {id: 'dec_018f_kraft'})
        MATCH (evi:Evidence {id: 'evi_018f_kraft_consensus'})
        MERGE (kraft)-[:SUPPORTED_BY]->(evi)
        """
    )

    # (evidence)-[:PART_OF]->(source)
    graph.query(
        """
        MATCH (evi:Evidence {id: 'evi_018f_kraft_consensus'})
        MATCH (src:Source {id: 'src_018f_linear_eng_4091'})
        MERGE (evi)-[:PART_OF]->(src)
        """
    )

    node_count = graph.query("MATCH (n) RETURN count(n)").result_set[0][0]
    edge_count = graph.query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]
    log.info("Seeding complete for %s: %d nodes, %d edges.", GRAPH_NAME, node_count, edge_count)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed tenant_nexus_infra graph")
    parser.add_argument("--host", default=None, help="FalkorDB host")
    parser.add_argument("--port", type=int, default=None, help="FalkorDB port")
    parser.add_argument("--no-reset", dest="reset", action="store_false", help="Do not drop existing graph")
    args = parser.parse_args()

    seed_nexus_infra(host=args.host, port=args.port, reset=args.reset)
