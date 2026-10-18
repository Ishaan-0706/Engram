"""Seed script for tenant_acme_payments graph.

Seeds the unified enterprise graph for Acme FinTech (100% synthetic, .internal domain):
- People (@acme-synthetic.internal):
  - person_priya (Priya Nair, Staff Engineer)
  - person_aarav (Aarav Mehta, Principal Security Architect)
  - person_rohan (Rohan Verma, Senior SRE)
- Teams:
  - team_core_payments ("Core Payments & Security")
  - team_ledger ("Settlement & Ledger SRE")
- Project:
  - proj_zero_trust ("Zero-Trust Ingress 2026")
- Systems:
  - sys_payment_gw (payment-gateway)
  - sys_settlement (settlement-worker, depends on payment-gateway)
- Decisions:
  - dec_oauth_introspect (superseded)
  - dec_ed25519_local (active, supersedes dec_oauth_introspect)
- Documents:
  - doc_auth_rfc (stale, "Payments Auth RFC v1")
- Multi-Source Evidence (Slack chat + Linear ticket + Confluence doc)
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

GRAPH_NAME = "tenant_acme_payments"


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


def seed_acme_payments(db: FalkorDB) -> tuple[int, int]:
    """Re-seed tenant_acme_payments to pristine state with 100% synthetic enterprise data."""
    if GRAPH_NAME in db.list_graphs():
        db.select_graph(GRAPH_NAME).delete()

    graph = db.select_graph(GRAPH_NAME)
    bootstrap_indexes(graph, GRAPH_NAME)

    # 1. People (@acme-synthetic.internal)
    graph.query(
        """
        CREATE (:Person {id: 'person_priya', display_name: 'Priya Nair', canonical_email: 'priya@acme-synthetic.internal', role: 'Staff Engineer'}),
               (:Person {id: 'person_aarav', display_name: 'Aarav Mehta', canonical_email: 'aarav@acme-synthetic.internal', role: 'Principal Security Architect'}),
               (:Person {id: 'person_rohan', display_name: 'Rohan Verma', canonical_email: 'rohan@acme-synthetic.internal', role: 'Senior SRE'})
        """
    )

    # 2. Teams, Projects & Systems
    graph.query(
        """
        CREATE (:Team {id: 'team_core_payments', name: 'Core Payments & Security'}),
               (:Team {id: 'team_ledger', name: 'Settlement & Ledger SRE'}),
               (:Project {id: 'proj_zero_trust', name: 'Zero-Trust Ingress 2026', status: 'in_progress'}),
               (:System {id: 'sys_payment_gw', name: 'payment-gateway', status: 'active'}),
               (:System {id: 'sys_settlement', name: 'settlement-worker', status: 'active'})
        """
    )

    # 3. Document & Decisions
    now_ms = int(time.time() * 1000)
    anchor_ts = now_ms - (62 * 86400 * 1000)
    graph.query(
        """
        CREATE (:Document {id: 'doc_auth_rfc', title: 'Payments Auth RFC v1', status: 'stale', uri: 'confluence://acme-synthetic/docs/auth-rfc-v1', created_at: $anchor_ts}),
               (:Decision {id: 'dec_oauth_introspect', summary: 'Centralized OAuth2 token introspection on every API request', status: 'superseded', timestamp: $anchor_ts}),
               (:Decision {id: 'dec_ed25519_local', summary: 'Local Ed25519 cryptographic signature verification with 5-minute JWKS rotation', status: 'active', timestamp: $now_ms})
        """,
        {"anchor_ts": anchor_ts, "now_ms": now_ms},
    )

    # 4. Multi-Source Evidence (Slack chat + Linear ticket + Confluence doc)
    # Chat: Slack incident thread
    slack_excerpt = (
        "Centralized OAuth token introspection spiked p99 latency to 250ms under peak checkout load. "
        "Switching payment-gateway to local Ed25519 public-key verification reduced p99 auth latency to 1.2ms."
    )
    slack_uri = "slack://acme-synthetic/inc-payments/p1726000000"
    slack_hash = hashlib.sha256(f"{slack_excerpt}\n{slack_uri}".encode("utf-8")).hexdigest()

    # Ticket: Linear issue
    linear_excerpt = (
        "Ticket PAY-402: Rolled out Envoy WASM filter for local Ed25519 verification across all ingress pods; "
        "deprecated OAuth introspection endpoint."
    )
    linear_uri = "linear://acme-synthetic/issue/PAY-402"
    linear_hash = hashlib.sha256(f"{linear_excerpt}\n{linear_uri}".encode("utf-8")).hexdigest()

    # Doc: Confluence RFC proposal
    doc_excerpt = (
        "Payments Auth RFC v1 (confluence://acme-synthetic/docs/auth-rfc-v1): Authored by Priya Nair "
        "(priya@acme-synthetic.internal). Centralized OAuth token introspection architecture for payment-gateway ingress."
    )
    doc_uri = "confluence://acme-synthetic/docs/auth-rfc-v1"
    doc_hash = hashlib.sha256(f"{doc_excerpt}\n{doc_uri}".encode("utf-8")).hexdigest()

    graph.query(
        """
        CREATE (:Source {id: 'src_slack_inc', uri: $slack_uri, source_type: 'slack', content_hash: $slack_hash}),
               (:Evidence {
                   id: 'evi_slack_inc',
                   record_id: 'dec_ed25519_local',
                   source_type: 'slack',
                   author: 'aarav@acme-synthetic.internal',
                   excerpt: $slack_excerpt,
                   source_uri: $slack_uri,
                   source_timestamp: '2026-09-22T14:30:00Z',
                   valid_from: 1726900000000,
                   content_hash: $slack_hash
               }),
               (:Source {id: 'src_linear_pay_402', uri: $linear_uri, source_type: 'linear', content_hash: $linear_hash}),
               (:Evidence {
                   id: 'evi_ticket_pay402',
                   record_id: 'dec_ed25519_local',
                   source_type: 'linear',
                   author: 'rohan@acme-synthetic.internal',
                   excerpt: $linear_excerpt,
                   source_uri: $linear_uri,
                   source_timestamp: '2026-09-23T09:15:00Z',
                   valid_from: 1726950000000,
                   content_hash: $linear_hash
               }),
               (:Source {id: 'src_confluence_rfc', uri: $doc_uri, source_type: 'confluence', content_hash: $doc_hash}),
               (:Evidence {
                   id: 'evi_doc_auth_rfc',
                   record_id: 'doc_auth_rfc',
                   source_type: 'confluence',
                   author: 'priya@acme-synthetic.internal',
                   excerpt: $doc_excerpt,
                   source_uri: $doc_uri,
                   source_timestamp: '2026-08-10T11:00:00Z',
                   valid_from: 1723280000000,
                   content_hash: $doc_hash
               })
        """,
        {
            "slack_uri": slack_uri,
            "slack_excerpt": slack_excerpt,
            "slack_hash": slack_hash,
            "linear_uri": linear_uri,
            "linear_excerpt": linear_excerpt,
            "linear_hash": linear_hash,
            "doc_uri": doc_uri,
            "doc_excerpt": doc_excerpt,
            "doc_hash": doc_hash,
        },
    )

    # 5. Edges Connecting People, Teams, Projects, Systems, Documents, Tickets, Chats, Decisions
    graph.query(
        """
        MATCH (aarav:Person {id: 'person_aarav'}),
              (priya:Person {id: 'person_priya'}),
              (rohan:Person {id: 'person_rohan'}),
              (team_core:Team {id: 'team_core_payments'}),
              (team_ledg:Team {id: 'team_ledger'}),
              (proj:Project {id: 'proj_zero_trust'}),
              (sys_gw:System {id: 'sys_payment_gw'}),
              (sys_set:System {id: 'sys_settlement'}),
              (doc:Document {id: 'doc_auth_rfc'}),
              (old_dec:Decision {id: 'dec_oauth_introspect'}),
              (new_dec:Decision {id: 'dec_ed25519_local'}),
              (slack_evi:Evidence {id: 'evi_slack_inc'}),
              (slack_src:Source {id: 'src_slack_inc'}),
              (linear_evi:Evidence {id: 'evi_ticket_pay402'}),
              (linear_src:Source {id: 'src_linear_pay_402'}),
              (doc_evi:Evidence {id: 'evi_doc_auth_rfc'}),
              (doc_src:Source {id: 'src_confluence_rfc'})
        CREATE
            /* People & Teams */
            (priya)-[:MEMBER_OF {role: 'Staff Engineer'}]->(team_core),
            (aarav)-[:MEMBER_OF {role: 'Principal Security Architect'}]->(team_core),
            (rohan)-[:MEMBER_OF {role: 'Senior SRE'}]->(team_ledg),
            (team_core)-[:RESPONSIBLE_FOR]->(sys_gw),
            (team_ledg)-[:RESPONSIBLE_FOR]->(sys_set),

            /* Formal Accountability (OWNS) */
            (priya)-[:OWNS {valid_from: 1700000000000, ingested_at: 1726900000000, valid_to: null}]->(sys_gw),
            (rohan)-[:OWNS {valid_from: 1700000000000, ingested_at: 1726900000000, valid_to: null}]->(sys_set),

            /* Projects & Systems */
            (sys_gw)-[:PART_OF]->(proj),
            (sys_set)-[:PART_OF]->(proj),
            (sys_set)-[:DEPENDS_ON {protocol: 'gRPC', tier: 'core'}]->(sys_gw),
            (new_dec)-[:IMPACTS_PROJECT]->(proj),

            /* Decisions & Systems */
            (aarav)-[:ESTABLISHED]->(new_dec),
            (new_dec)-[:AFFECTS]->(sys_gw),
            (old_dec)-[:AFFECTS]->(sys_gw),
            (new_dec)-[:SUPERSEDES {reason: 'OAuth introspection latency violated 250ms p99 SLA'}]->(old_dec),

            /* Authorship of Knowledge Artifacts */
            (aarav)-[:AUTHORED]->(slack_evi),
            (rohan)-[:AUTHORED]->(linear_evi),
            (priya)-[:AUTHORED]->(doc_evi),
            (priya)-[:AUTHORED]->(doc),

            /* Document relationships */
            (doc)-[:DOCUMENTS]->(sys_gw),
            (doc)-[:PROPOSED]->(old_dec),

            /* Evidence grounding across Chat, Ticket, Doc */
            (new_dec)-[:SUPPORTED_BY]->(slack_evi),
            (slack_evi)-[:PART_OF]->(slack_src),
            (new_dec)-[:SUPPORTED_BY]->(linear_evi),
            (linear_evi)-[:PART_OF]->(linear_src),
            (old_dec)-[:SUPPORTED_BY]->(doc_evi),
            (doc_evi)-[:PART_OF]->(doc_src)
        """
    )

    nodes = graph.query("MATCH (n) RETURN count(n)").result_set[0][0]
    edges = graph.query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]
    log.info("Seeding complete for %s: %d nodes, %d edges.", GRAPH_NAME, nodes, edges)
    return nodes, edges


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed tenant_acme_payments graph")
    parser.add_argument("--host", default=None, help="FalkorDB host")
    parser.add_argument("--port", type=int, default=None, help="FalkorDB port")
    args = parser.parse_args()

    host = args.host or os.environ.get("FALKORDB_HOST", "localhost")
    port = args.port or int(os.environ.get("FALKORDB_PORT", "6379"))

    db = FalkorDB(host=host, port=port)
    seed_acme_payments(db)
