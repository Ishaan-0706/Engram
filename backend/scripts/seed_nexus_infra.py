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

    # Team & Project
    graph.query(
        """
        MERGE (t:Team {id: $team_id})
        SET t.name = $team_name
        MERGE (proj:Project {id: $proj_id})
        SET proj.name = $proj_name,
            proj.status = $proj_status
        """,
        {
            "team_id": "team_platform_sre",
            "team_name": "Platform Reliability",
            "proj_id": "proj_kafka_kraft",
            "proj_name": "KRaft Consensus Upgrade",
            "proj_status": "in_progress",
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

    # Sources & Evidence (Linear ticket + Slack chat + Notion doc)
    slack_excerpt = (
        "INC-KAFKA Slack incident thread (#inc-kafka): Elena Rostova reported cross-AZ "
        "heartbeat packet drops causing broker split-brain during ZooKeeper leader elections."
    )
    slack_uri = "slack://channels/inc-kafka/p1723600000"
    slack_hash = hashlib.sha256(f"{slack_excerpt}\n{slack_uri}".encode("utf-8")).hexdigest()

    notion_excerpt = (
        "Event Bus Partitioning SOP v2 (notion://nexus/eng/event-bus-v2): Elena Rostova runbook "
        "specifying ZooKeeper ensemble controller configuration for partition rebalances."
    )
    notion_uri = "notion://nexus/eng/event-bus-v2"
    notion_hash = hashlib.sha256(f"{notion_excerpt}\n{notion_uri}".encode("utf-8")).hexdigest()

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
            evi.source_type = $source_type,
            evi.author = $author,
            evi.excerpt = $excerpt,
            evi.source_uri = $source_uri,
            evi.source_timestamp = $source_timestamp,
            evi.valid_from = $valid_from,
            evi.content_hash = $content_hash
        """,
        {
            "id": "evi_018f_kraft_consensus",
            "record_id": "dec_018f_kraft",
            "source_type": "linear",
            "author": "devin@nexus.io",
            "excerpt": EXCERPT,
            "source_uri": SOURCE_URI,
            "source_timestamp": SOURCE_TIMESTAMP,
            "valid_from": 1723650000000,
            "content_hash": DIGEST,
        },
    )

    graph.query(
        """
        MERGE (src:Source {id: 'src_018f_slack_inc'})
        SET src.uri = $slack_uri,
            src.source_type = 'slack',
            src.content_hash = $slack_hash
        MERGE (evi:Evidence {id: 'evi_018f_zk_heartbeat'})
        SET evi.record_id = 'dec_018f_kraft',
            evi.source_type = 'slack',
            evi.author = 'elena@nexus.io',
            evi.excerpt = $slack_excerpt,
            evi.source_uri = $slack_uri,
            evi.source_timestamp = '2026-08-14T14:15:00Z',
            evi.valid_from = 1723640000000,
            evi.content_hash = $slack_hash
        MERGE (src_doc:Source {id: 'src_018f_notion_runbook'})
        SET src_doc.uri = $notion_uri,
            src_doc.source_type = 'notion',
            src_doc.content_hash = $notion_hash
        MERGE (evi_doc:Evidence {id: 'evi_018f_sop_runbook'})
        SET evi_doc.record_id = 'doc_018f_kafka_runbook',
            evi_doc.source_type = 'notion',
            evi_doc.author = 'elena@nexus.io',
            evi_doc.excerpt = $notion_excerpt,
            evi_doc.source_uri = $notion_uri,
            evi_doc.source_timestamp = '2026-06-10T10:00:00Z',
            evi_doc.valid_from = 1718000000000,
            evi_doc.content_hash = $notion_hash
        """,
        {
            "slack_uri": slack_uri,
            "slack_excerpt": slack_excerpt,
            "slack_hash": slack_hash,
            "notion_uri": notion_uri,
            "notion_excerpt": notion_excerpt,
            "notion_hash": notion_hash,
        },
    )

    # 3. Seed Relationships
    log.info("Creating relationships in %s...", GRAPH_NAME)

    graph.query(
        """
        MATCH (devin:Person {id: 'usr_018f_devin'}),
              (elena:Person {id: 'usr_018f_elena'}),
              (team:Team {id: 'team_platform_sre'}),
              (proj:Project {id: 'proj_kafka_kraft'}),
              (s:System {id: 'sys_018f_kafka'}),
              (doc:Document {id: 'doc_018f_kafka_runbook'}),
              (zk:Decision {id: 'dec_018f_zookeeper'}),
              (kraft:Decision {id: 'dec_018f_kraft'}),
              (evi_ticket:Evidence {id: 'evi_018f_kraft_consensus'}),
              (src_ticket:Source {id: 'src_018f_linear_eng_4091'}),
              (evi_slack:Evidence {id: 'evi_018f_zk_heartbeat'}),
              (src_slack:Source {id: 'src_018f_slack_inc'}),
              (evi_doc:Evidence {id: 'evi_018f_sop_runbook'}),
              (src_doc:Source {id: 'src_018f_notion_runbook'})
        CREATE
            /* People & Teams */
            (devin)-[:MEMBER_OF {role: 'Principal SRE'}]->(team),
            (elena)-[:MEMBER_OF {role: 'Platform Lead'}]->(team),
            (team)-[:RESPONSIBLE_FOR]->(s),

            /* Ownership (formal accountability) */
            (elena)-[:OWNS {valid_from: 1710000000000, valid_to: null}]->(s),

            /* Systems & Projects */
            (s)-[:PART_OF]->(proj),
            (kraft)-[:IMPACTS_PROJECT]->(proj),

            /* Documents & Decisions */
            (doc)-[:DOCUMENTS]->(s),
            (doc)-[:PROPOSED]->(zk),
            (kraft)-[:AFFECTS]->(s),
            (zk)-[:AFFECTS]->(s),
            (kraft)-[:SUPERSEDES {reason: 'Cross-AZ consensus timeouts'}]->(zk),
            (devin)-[:ESTABLISHED]->(kraft),

            /* Authorship */
            (devin)-[:AUTHORED]->(evi_ticket),
            (elena)-[:AUTHORED]->(evi_slack),
            (elena)-[:AUTHORED]->(evi_doc),
            (elena)-[:AUTHORED]->(doc),

            /* Multi-Source Evidence grounding */
            (kraft)-[:SUPPORTED_BY]->(evi_ticket),
            (evi_ticket)-[:PART_OF]->(src_ticket),
            (kraft)-[:SUPPORTED_BY]->(evi_slack),
            (evi_slack)-[:PART_OF]->(src_slack),
            (zk)-[:SUPPORTED_BY]->(evi_doc),
            (evi_doc)-[:PART_OF]->(src_doc)
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
