"""Reset and re-seed demo graphs and Redis state.

Cleans and re-seeds both tenant_acme_payments and tenant_nexus_infra
back to pristine initial state in under 2 seconds.
Flushes Redis keys matching turn:* and lock:*.
Prints node and edge counts for both tenants upon completion.
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
import redis as redis_lib

from engram_graph_core.bootstrap import INDEXES, UNIQUE_NODE_CONSTRAINTS
from scripts.seed_acme_payments import seed_acme_payments
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
