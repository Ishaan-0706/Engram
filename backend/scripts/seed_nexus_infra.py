"""Seed script for tenant_nexus_infra graph.

Seeds the unified enterprise graph for Nexus Cloud (100% synthetic, .internal domain):
- People (@nexus-synthetic.internal):
  - person_elena (Elena Rostova, Principal Infra Engineer)
  - person_devin (Devin Patel, Staff Distributed Systems Engineer)
- Teams:
  - team_streaming ("Event Streaming Platform")
- Projects:
  - proj_kraft ("Kafka KRaft Migration")
- Systems:
  - sys_event_stream (event-stream-cluster)
- Decisions:
  - dec_zk_quorum (superseded)
  - dec_kraft_consensus (active, supersedes dec_zk_quorum)
- Documents:
  - doc_kafka_sop (stale, "Kafka Broker Failover Runbook")
- Multi-Source Evidence (Linear ticket + Slack chat + Notion doc)
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


def bootstrap_indexes(graph: Any, name: str) -> None:
    for stmt in INDEXES:
        try:
            graph.query(stmt)
        except Exception as exc:
            msg = str(exc).lower()
            if "already indexed" in msg or "already exists" in msg:
                continue

    for extra_stmt in [
        "CREATE INDEX FOR (s:System) ON (s.id)",
        "CREATE INDEX FOR (s:System) ON (s.name)",
        "CREATE INDEX FOR (t:Team) ON (t.id)",
        "CREATE INDEX FOR (p:Project) ON (p.id)",
        "CREATE INDEX FOR (e:Evidence) ON (e.source_type)",
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
        constraints = list(UNIQUE_NODE_CONSTRAINTS) + [
            ("System", ["id"]),
            ("Team", ["id"]),
            ("Project", ["id"]),
        ]
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


def seed_nexus_infra(
    host: str | None = None,
    port: int | None = None,
    reset: bool = True,
) -> tuple[int, int]:
    """Seed the tenant_nexus_infra graph with pristine synthetic enterprise data."""
    host = host or os.environ.get("FALKORDB_HOST", "localhost")
    port = int(port or os.environ.get("FALKORDB_PORT", "6379"))

    db = FalkorDB(host=host, port=port)

    if reset and GRAPH_NAME in db.list_graphs():
        log.info("Resetting existing graph: %s", GRAPH_NAME)
        db.select_graph(GRAPH_NAME).delete()

    graph = db.select_graph(GRAPH_NAME)
    bootstrap_indexes(graph, GRAPH_NAME)

    # 1. People (@nexus-synthetic.internal)
    graph.query(
        """
        CREATE (:Person {id: 'person_elena', display_name: 'Elena Rostova', canonical_email: 'elena@nexus-synthetic.internal', role: 'Principal Infra Engineer'}),
               (:Person {id: 'person_devin', display_name: 'Devin Patel', canonical_email: 'devin@nexus-synthetic.internal', role: 'Staff Distributed Systems Engineer'})
        """
    )

    # 2. Team, Project, System
    graph.query(
        """
        CREATE (:Team {id: 'team_streaming', name: 'Event Streaming Platform'}),
               (:Project {id: 'proj_kraft', name: 'Kafka KRaft Migration', status: 'in_progress'}),
               (:System {id: 'sys_event_stream', name: 'event-stream-cluster', status: 'active'})
        """
    )

    # 3. Documents & Decisions
    now_ms = int(time.time() * 1000)
    anchor_ts = now_ms - (62 * 86400 * 1000)
    graph.query(
        """
        CREATE (:Document {id: 'doc_kafka_sop', title: 'Kafka Broker Failover Runbook', status: 'stale', uri: 'notion://nexus-synthetic/sop/kafka-failover', created_at: $anchor_ts}),
               (:Decision {id: 'dec_zk_quorum', summary: 'Use ZooKeeper quorum for event-stream-cluster metadata management', status: 'superseded', timestamp: $anchor_ts}),
               (:Decision {id: 'dec_kraft_consensus', summary: 'Migrate event-stream-cluster to KRaft consensus for sub-second controller failover', status: 'active', timestamp: $now_ms})
        """,
        {"anchor_ts": anchor_ts, "now_ms": now_ms},
    )

    # 4. Multi-Source Evidence (Linear ticket + Slack chat + Notion doc)
    # Linear Ticket
    linear_excerpt = (
        "INFRA-118: ZooKeeper cross-AZ split-brain caused 14s partition failover; migrated metadata quorum to Kafka KRaft."
    )
    linear_uri = "linear://nexus-synthetic/issue/INFRA-118"
    linear_hash = hashlib.sha256(f"{linear_excerpt}\n{linear_uri}".encode("utf-8")).hexdigest()

    # Slack Chat
    slack_excerpt = (
        "Confirmed in #sre-war-room: KRaft controller failover completed in 180ms during chaos test."
    )
    slack_uri = "slack://nexus-synthetic/sre-war-room/p1726050000"
    slack_hash = hashlib.sha256(f"{slack_excerpt}\n{slack_uri}".encode("utf-8")).hexdigest()

    # Notion Doc
    notion_excerpt = (
        "Kafka Broker Failover Runbook (notion://nexus-synthetic/sop/kafka-failover): Documents ZooKeeper ensemble quorum requirements for cluster state coordination."
    )
    notion_uri = "notion://nexus-synthetic/sop/kafka-failover"
    notion_hash = hashlib.sha256(f"{notion_excerpt}\n{notion_uri}".encode("utf-8")).hexdigest()

    graph.query(
        """
        CREATE (:Source {id: 'src_linear_infra118', uri: $linear_uri, source_type: 'linear', content_hash: $linear_hash}),
               (:Evidence {
                   id: 'evi_linear_infra118',
                   record_id: 'dec_kraft_consensus',
                   source_type: 'linear',
                   author: 'devin@nexus-synthetic.internal',
                   excerpt: $linear_excerpt,
                   source_uri: $linear_uri,
                   source_timestamp: '2026-08-15T10:00:00Z',
                   valid_from: 1723700000000,
                   content_hash: $linear_hash
               }),
               (:Source {id: 'src_slack_sre88', uri: $slack_uri, source_type: 'slack', content_hash: $slack_hash}),
               (:Evidence {
                   id: 'evi_slack_sre88',
                   record_id: 'dec_kraft_consensus',
                   source_type: 'slack',
                   author: 'devin@nexus-synthetic.internal',
                   excerpt: $slack_excerpt,
                   source_uri: $slack_uri,
                   source_timestamp: '2026-08-15T14:30:00Z',
                   valid_from: 1723720000000,
                   content_hash: $slack_hash
               }),
               (:Source {id: 'src_doc_kafka_sop', uri: $notion_uri, source_type: 'notion', content_hash: $notion_hash}),
               (:Evidence {
                   id: 'evi_doc_kafka_sop',
                   record_id: 'doc_kafka_sop',
                   source_type: 'notion',
                   author: 'elena@nexus-synthetic.internal',
                   excerpt: $notion_excerpt,
                   source_uri: $notion_uri,
                   source_timestamp: '2026-06-10T10:00:00Z',
                   valid_from: 1718000000000,
                   content_hash: $notion_hash
               })
        """,
        {
            "linear_uri": linear_uri,
            "linear_excerpt": linear_excerpt,
            "linear_hash": linear_hash,
            "slack_uri": slack_uri,
            "slack_excerpt": slack_excerpt,
            "slack_hash": slack_hash,
            "notion_uri": notion_uri,
            "notion_excerpt": notion_excerpt,
            "notion_hash": notion_hash,
        },
    )

    # 5. Relationships
    graph.query(
        """
        MATCH (devin:Person {id: 'person_devin'}),
              (elena:Person {id: 'person_elena'}),
              (team:Team {id: 'team_streaming'}),
              (proj:Project {id: 'proj_kraft'}),
              (s:System {id: 'sys_event_stream'}),
              (doc:Document {id: 'doc_kafka_sop'}),
              (zk:Decision {id: 'dec_zk_quorum'}),
              (kraft:Decision {id: 'dec_kraft_consensus'}),
              (evi_ticket:Evidence {id: 'evi_linear_infra118'}),
              (src_ticket:Source {id: 'src_linear_infra118'}),
              (evi_slack:Evidence {id: 'evi_slack_sre88'}),
              (src_slack:Source {id: 'src_slack_sre88'}),
              (evi_doc:Evidence {id: 'evi_doc_kafka_sop'}),
              (src_doc:Source {id: 'src_doc_kafka_sop'})
        CREATE
            /* People & Teams */
            (devin)-[:MEMBER_OF {role: 'Staff Distributed Systems Engineer'}]->(team),
            (elena)-[:MEMBER_OF {role: 'Principal Infra Engineer'}]->(team),
            (team)-[:RESPONSIBLE_FOR]->(s),

            /* Ownership (formal accountability) */
            (elena)-[:OWNS {valid_from: 1710000000000, valid_to: null, ingested_at: 1723700000000}]->(s),

            /* Systems & Projects */
            (s)-[:PART_OF]->(proj),
            (kraft)-[:IMPACTS_PROJECT]->(proj),

            /* Documents & Decisions */
            (doc)-[:DOCUMENTS]->(s),
            (doc)-[:PROPOSED]->(zk),
            (kraft)-[:AFFECTS]->(s),
            (zk)-[:AFFECTS]->(s),
            (kraft)-[:SUPERSEDES {reason: 'ZooKeeper split-brain latency failover'}]->(zk),
            (devin)-[:ESTABLISHED]->(kraft),

            /* Authorship */
            (devin)-[:AUTHORED]->(evi_ticket),
            (devin)-[:AUTHORED]->(evi_slack),
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
    return node_count, edge_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed tenant_nexus_infra graph")
    parser.add_argument("--host", default=None, help="FalkorDB host")
    parser.add_argument("--port", type=int, default=None, help="FalkorDB port")
    args = parser.parse_args()

    seed_nexus_infra(host=args.host, port=args.port)
