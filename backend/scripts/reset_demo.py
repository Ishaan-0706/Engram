"""Reset and re-seed demo graphs and Redis state.

Cleans and re-seeds both tenant_acme_payments and tenant_nexus_infra
back to pristine initial state in under 2 seconds.
Flushes Redis keys matching turn:* and lock:*.
Prints node and edge counts for both tenants upon completion.
"""

from __future__ import annotations

import argparse
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
import redis as redis_lib

from engram_graph_core.bootstrap import INDEXES, UNIQUE_NODE_CONSTRAINTS
from scripts.seed_nexus_infra import seed_nexus_infra

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ACME_TENANT = "tenant_acme_payments"
NEXUS_TENANT = "tenant_nexus_infra"


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


def seed_acme_payments(db: FalkorDB) -> tuple[int, int]:
    """Re-seed tenant_acme_payments to pristine state."""
    if ACME_TENANT in db.list_graphs():
        db.select_graph(ACME_TENANT).delete()

    graph = db.select_graph(ACME_TENANT)
    bootstrap_indexes(graph, ACME_TENANT)

    # People
    graph.query(
        """
        CREATE (:Person {id: 'usr_018f_aarav', display_name: 'Aarav Sharma', canonical_email: 'aarav@acme.com', role: 'Staff Engineer'}),
               (:Person {id: 'usr_018f_priya', display_name: 'Priya Nair', canonical_email: 'priya@acme.com', role: 'Payments Lead'})
        """
    )

    # Team & System
    graph.query(
        """
        CREATE (:Team {id: 'team_core_pay', name: 'Core Payments'}),
               (:System {id: 'sys_payment_gw', name: 'payment-gateway', status: 'active'})
        """
    )

    # Document & Decisions
    graph.query(
        """
        CREATE (:Document {id: 'doc_auth_rfc', title: 'Payments Auth RFC v1', status: 'stale', uri: 'confluence://acme/docs/auth-rfc-v1'}),
               (:Decision {id: 'dec_oauth_introspection', summary: 'Use centralized OAuth introspection endpoint for payment auth', status: 'superseded'}),
               (:Decision {id: 'dec_ed25519_local', summary: 'Verify tokens locally via Ed25519 public keys to protect p99 latency', status: 'active'})
        """
    )

    # Source & Evidence
    excerpt = (
        "INC-PAYMENTS Incident Retrospective: Due to 250ms p99 latency spikes on OAuth "
        "introspection during flash sales, we are switching payment-gateway token validation "
        "to local Ed25519 public keys."
    )
    source_uri = "slack://channels/inc-payments/p1726000000"
    content_hash = "a58b09339e0839e4e39c4a4a4918e55e5b30693a1cf5937402f1a66ff5d5642d"

    graph.query(
        """
        CREATE (:Source {id: 'src_slack_inc', uri: $uri, source_type: 'slack', content_hash: $content_hash}),
               (:Evidence {
                   id: 'evi_018f_latency_auth',
                   record_id: 'dec_ed25519_local',
                   excerpt: $excerpt,
                   source_uri: $uri,
                   source_timestamp: '2026-09-22T14:30:00Z',
                   valid_from: 1726900000000,
                   content_hash: $content_hash
               })
        """,
        {"uri": source_uri, "content_hash": content_hash, "excerpt": excerpt},
    )

    # Edges
    graph.query(
        """
        MATCH (aarav:Person {id: 'usr_018f_aarav'}),
              (priya:Person {id: 'usr_018f_priya'}),
              (team:Team {id: 'team_core_pay'}),
              (sys:System {id: 'sys_payment_gw'}),
              (doc:Document {id: 'doc_auth_rfc'}),
              (old_dec:Decision {id: 'dec_oauth_introspection'}),
              (new_dec:Decision {id: 'dec_ed25519_local'}),
              (evi:Evidence {id: 'evi_018f_latency_auth'}),
              (src:Source {id: 'src_slack_inc'})
        CREATE (aarav)-[:MEMBER_OF]->(team),
               (aarav)-[:ESTABLISHED]->(new_dec),
               (priya)-[:MEMBER_OF]->(team),
               (priya)-[:OWNS {valid_from: 1700000000000, ingested_at: 1726900000000, valid_to: null}]->(sys),
               (doc)-[:DOCUMENTS]->(sys),
               (doc)-[:PROPOSED]->(old_dec),
               (new_dec)-[:AFFECTS]->(sys),
               (new_dec)-[:SUPERSEDES {reason: 'OAuth introspection latency violated 250ms p99 SLA'}]->(old_dec),
               (new_dec)-[:SUPPORTED_BY]->(evi),
               (evi)-[:PART_OF]->(src)
        """
    )

    nodes = graph.query("MATCH (n) RETURN count(n)").result_set[0][0]
    edges = graph.query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]
    return nodes, edges


def flush_redis_state(host: str, port: int) -> int:
    """Flush Redis keys matching turn:* and lock:* (and idempotency:*)."""
    r = redis_lib.Redis(host=host, port=port, decode_responses=True)
    deleted = 0
    for pattern in ["turn:*", "lock:*", "idempotency:*"]:
        keys = r.keys(pattern)
        if keys:
            deleted += r.delete(*keys)
    return deleted


def reset_demo(
    falkordb_host: str | None = None,
    falkordb_port: int | None = None,
    redis_host: str | None = None,
    redis_port: int | None = None,
) -> dict[str, Any]:
    """Clean and re-seed tenant_acme_payments and tenant_nexus_infra and flush Redis."""
    start_time = time.time()

    f_host = falkordb_host or os.environ.get("FALKORDB_HOST", "localhost")
    f_port = int(falkordb_port or os.environ.get("FALKORDB_PORT", "6379"))
    r_host = redis_host or os.environ.get("REDIS_HOST", f_host)
    r_port = int(redis_port or os.environ.get("REDIS_PORT", str(f_port)))

    db = FalkorDB(host=f_host, port=f_port)

    # 1. Seed tenant_acme_payments
    acme_nodes, acme_edges = seed_acme_payments(db)

    # 2. Seed tenant_nexus_infra
    seed_nexus_infra(host=f_host, port=f_port, reset=True)
    nexus_graph = db.select_graph(NEXUS_TENANT)
    nexus_nodes = nexus_graph.query("MATCH (n) RETURN count(n)").result_set[0][0]
    nexus_edges = nexus_graph.query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]

    # 3. Flush Redis
    redis_keys_deleted = flush_redis_state(r_host, r_port)

    elapsed = time.time() - start_time

    # Print summary
    print("=" * 60)
    print("Engram Demo Graphs & Redis Reset Complete")
    print("=" * 60)
    print(f"Tenant '{ACME_TENANT}': {acme_nodes} nodes, {acme_edges} edges")
    print(f"Tenant '{NEXUS_TENANT}': {nexus_nodes} nodes, {nexus_edges} edges")
    print(f"Redis keys flushed (turn:*, lock:*, idempotency:*): {redis_keys_deleted}")
    print(f"Total time: {elapsed:.3f} seconds (budget: < 2.0s)")
    print("=" * 60)

    return {
        "acme_nodes": acme_nodes,
        "acme_edges": acme_edges,
        "nexus_nodes": nexus_nodes,
        "nexus_edges": nexus_edges,
        "redis_keys_deleted": redis_keys_deleted,
        "elapsed_seconds": elapsed,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean and re-seed demo tenants and Redis state")
    parser.add_argument("--falkordb-host", default=None)
    parser.add_argument("--falkordb-port", type=int, default=None)
    parser.add_argument("--redis-host", default=None)
    parser.add_argument("--redis-port", type=int, default=None)
    args = parser.parse_args()

    reset_demo(
        falkordb_host=args.falkordb_host,
        falkordb_port=args.falkordb_port,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
    )
