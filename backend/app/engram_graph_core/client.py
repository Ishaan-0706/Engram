from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

MCP_QUERY_TIMEOUT_MS = 2500


def tenant_graph_name(tenant_id: str) -> str:
    tid = (tenant_id or "").strip()
    if not tid or any(c in tid for c in " \n\t"):
        raise ValueError("tenant_id must be a non-empty token")
    if tid.startswith("tenant_") or ":" in tid:
        return tid
    return f"tenant_{tid}"


@dataclass
class TenantGraph:
    name: str
    _graph: Any

    def query(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        timeout: int = MCP_QUERY_TIMEOUT_MS,
    ) -> Any:
        return self._graph.query(cypher, params or {}, timeout=timeout)


def get_tenant_graph(tenant_id: str) -> TenantGraph:
    name = tenant_graph_name(tenant_id)
    host = os.environ.get("FALKORDB_HOST", "localhost")
    port = int(os.environ.get("FALKORDB_PORT", "6379"))
    try:
        from falkordb import FalkorDB
    except ImportError as exc:
        raise RuntimeError(
            "falkordb is not installed; pip install 'company-brain[graph]'"
        ) from exc
    graph = FalkorDB(host=host, port=port).select_graph(name)
    return TenantGraph(name=name, _graph=graph)
