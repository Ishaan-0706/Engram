from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import settings

MCP_QUERY_TIMEOUT_MS = settings.GRAPH_QUERY_TIMEOUT_MS


def resolve_tenant_graph_name(tenant_id: str) -> str:
    tid = (tenant_id or "").strip()
    if not tid:
        raise ValueError("tenant_id must be a non-empty token")
    if " " in tid or "\t" in tid or "\n" in tid:
        tid = tid.lower().replace(" ", "_").replace("\t", "_").replace("\n", "_")
    if tid.startswith("tenant_") or ":" in tid:
        return tid
    return f"tenant_{tid}"


tenant_graph_name = resolve_tenant_graph_name


@dataclass
class TenantGraph:
    name: str
    _graph: Any

    def query(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        timeout: int = settings.GRAPH_QUERY_TIMEOUT_MS,
    ) -> Any:
        return self._graph.query(cypher, params or {}, timeout=timeout)


def get_tenant_graph(tenant_id: str) -> TenantGraph:
    name = resolve_tenant_graph_name(tenant_id)
    host = settings.FALKORDB_HOST
    port = settings.FALKORDB_PORT
    try:
        from falkordb import FalkorDB
    except ImportError as exc:
        raise RuntimeError(
            "falkordb is not installed; pip install 'company-brain[graph]'"
        ) from exc
    graph = FalkorDB(host=host, port=port).select_graph(name)
    return TenantGraph(name=name, _graph=graph)
