from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from engram_graph_core.bootstrap import GRAPH_QUERY_TIMEOUT_MS, graph_name

TEMPORAL_SCOPES = {
    "OWNS": "target",
    "ASSIGNED_TO": "target",
    "MEMBER_OF": "pair",
}


@dataclass
class WriteStats:
    nodes_created: int = 0
    nodes_merged: int = 0
    relationships_created: int = 0
    relationships_updated: int = 0


class GraphStore(Protocol):
    stats: WriteStats

    def merge_node(self, label: str, node_id: str, props: dict[str, Any]) -> bool:
        """MERGE on id. Returns True if created."""

    def merge_edge(
        self,
        rel_type: str,
        from_label: str,
        from_id: str,
        to_label: str,
        to_id: str,
        props: dict[str, Any] | None = None,
    ) -> bool:
        """Idempotent edge. Temporal types must use supersede_temporal."""

    def supersede_temporal(
        self,
        rel_type: str,
        from_label: str,
        from_id: str,
        to_label: str,
        to_id: str,
        *,
        valid_from: str,
        ingested_at: str,
    ) -> str:
        """Close active edges in scope and create at most one new edge. One query."""

    def get_node(self, label: str, node_id: str) -> dict[str, Any] | None:
        ...

    def find_person_by_email(self, email: str) -> dict[str, Any] | None:
        ...

    def find_person_by_identity(self, key: str) -> dict[str, Any] | None:
        ...

    def bootstrap(self, indexes: tuple[str, ...], unique_nodes: tuple) -> None:
        ...

    def active_edges(self, rel_type: str, to_id: str | None = None) -> list[dict[str, Any]]:
        ...


def _active(props: dict[str, Any]) -> bool:
    return props.get("valid_to") in (None, "", 0)


class InMemoryGraphStore:
    def __init__(self, name: str) -> None:
        self.name = name
        self.stats = WriteStats()
        self.nodes: dict[tuple[str, str], dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        self._bootstrapped = False

    def bootstrap(self, indexes: tuple[str, ...], unique_nodes: tuple) -> None:
        self._bootstrapped = True

    def merge_node(self, label: str, node_id: str, props: dict[str, Any]) -> bool:
        key = (label, node_id)
        created = key not in self.nodes
        existing = self.nodes.get(key, {})
        merged = {**existing, **props, "id": node_id}
        self.nodes[key] = merged
        if created:
            self.stats.nodes_created += 1
        else:
            self.stats.nodes_merged += 1
        return created

    def get_node(self, label: str, node_id: str) -> dict[str, Any] | None:
        node = self.nodes.get((label, node_id))
        return dict(node) if node else None

    def find_person_by_email(self, email: str) -> dict[str, Any] | None:
        needle = email.strip().lower()
        for (label, _), props in self.nodes.items():
            if label == "Person" and (props.get("canonical_email") or "").lower() == needle:
                return dict(props)
        return None

    def find_person_by_identity(self, key: str) -> dict[str, Any] | None:
        ident = self.nodes.get(("Identity", key))
        if not ident:
            for (label, _), props in self.nodes.items():
                if label == "Identity" and props.get("key") == key:
                    ident = props
                    break
        if not ident:
            return None
        person_id = ident.get("person_id")
        if not person_id:
            for edge in self.edges:
                if (
                    edge["rel_type"] == "HAS_IDENTITY"
                    and edge["to_id"] == ident.get("id", key)
                ):
                    person_id = edge["from_id"]
                    break
        if not person_id:
            return None
        return self.get_node("Person", person_id)

    def merge_edge(
        self,
        rel_type: str,
        from_label: str,
        from_id: str,
        to_label: str,
        to_id: str,
        props: dict[str, Any] | None = None,
    ) -> bool:
        if rel_type in TEMPORAL_SCOPES:
            raise ValueError(f"{rel_type} must use supersede_temporal")
        props = dict(props or {})
        for edge in self.edges:
            if (
                edge["rel_type"] == rel_type
                and edge["from_id"] == from_id
                and edge["to_id"] == to_id
            ):
                edge["props"].update(props)
                self.stats.relationships_updated += 1
                return False
        self.edges.append(
            {
                "rel_type": rel_type,
                "from_label": from_label,
                "from_id": from_id,
                "to_label": to_label,
                "to_id": to_id,
                "props": props,
            }
        )
        self.stats.relationships_created += 1
        return True

    def active_edges(self, rel_type: str, to_id: str | None = None) -> list[dict[str, Any]]:
        out = []
        for edge in self.edges:
            if edge["rel_type"] != rel_type:
                continue
            if to_id is not None and edge["to_id"] != to_id:
                continue
            if _active(edge["props"]):
                out.append(edge)
        return out

    def supersede_temporal(
        self,
        rel_type: str,
        from_label: str,
        from_id: str,
        to_label: str,
        to_id: str,
        *,
        valid_from: str,
        ingested_at: str,
    ) -> str:
        if (from_label, from_id) not in self.nodes or (to_label, to_id) not in self.nodes:
            raise KeyError("temporal endpoints missing")
        scope = TEMPORAL_SCOPES[rel_type]
        actives = [
            e
            for e in self.edges
            if e["rel_type"] == rel_type and _active(e["props"]) and _in_scope(e, scope, from_id, to_id)
        ]
        same = [
            e
            for e in actives
            if e["from_id"] == from_id and e["to_id"] == to_id
        ]
        if same:
            return "noop"
        for edge in actives:
            edge["props"]["valid_to"] = ingested_at
            self.stats.relationships_updated += 1
        self.edges.append(
            {
                "rel_type": rel_type,
                "from_label": from_label,
                "from_id": from_id,
                "to_label": to_label,
                "to_id": to_id,
                "props": {
                    "valid_from": valid_from,
                    "ingested_at": ingested_at,
                    "valid_to": None,
                },
            }
        )
        self.stats.relationships_created += 1
        return "created"


def _in_scope(edge: dict[str, Any], scope: str, from_id: str, to_id: str) -> bool:
    if scope == "target":
        return edge["to_id"] == to_id
    if scope == "pair":
        return edge["from_id"] == from_id and edge["to_id"] == to_id
    raise ValueError(scope)


class FalkorGraphStore:
    def __init__(self, graph: Any, name: str) -> None:
        self._graph = graph
        self.name = name
        self.stats = WriteStats()

    def _query(self, cypher: str, params: dict[str, Any] | None = None) -> Any:
        return self._graph.query(cypher, params or {}, timeout=GRAPH_QUERY_TIMEOUT_MS)

    def bootstrap(self, indexes: tuple[str, ...], unique_nodes: tuple) -> None:
        for stmt in indexes:
            try:
                self._query(stmt)
            except Exception as exc:
                if "already indexed" in str(exc).lower() or "already exists" in str(exc).lower():
                    continue
                raise
        client = getattr(self._graph, "_client", None) or getattr(self._graph, "client", None)
        redis = getattr(client, "connection", None) or getattr(client, "_redis", None)
        for label, props in unique_nodes:
            if redis is None:
                continue
            try:
                redis.execute_command(
                    "GRAPH.CONSTRAINT",
                    "CREATE",
                    self.name,
                    "UNIQUE",
                    "NODE",
                    label,
                    "PROPERTIES",
                    str(len(props)),
                    *props,
                )
            except Exception as exc:
                msg = str(exc).lower()
                if "already" in msg or "constraint" in msg:
                    continue

    def merge_node(self, label: str, node_id: str, props: dict[str, Any]) -> bool:
        assignments = ", ".join(f"n.{k} = ${k}" for k in props)
        params = {"id": node_id, **props}
        result = self._query(
            f"MERGE (n:{label} {{id: $id}}) "
            f"ON CREATE SET {assignments} "
            f"ON MATCH SET {assignments} "
            f"RETURN n.id AS id, exists(n.id) AS ok",
            params,
        )
        created = bool(getattr(result, "nodes_created", 0))
        if created:
            self.stats.nodes_created += 1
        else:
            self.stats.nodes_merged += 1
        return created

    def get_node(self, label: str, node_id: str) -> dict[str, Any] | None:
        result = self._query(
            f"MATCH (n:{label} {{id: $id}}) RETURN n",
            {"id": node_id},
        )
        rows = getattr(result, "result_set", None) or []
        if not rows:
            return None
        node = rows[0][0]
        props = dict(getattr(node, "properties", node))
        props.setdefault("id", node_id)
        return props

    def find_person_by_email(self, email: str) -> dict[str, Any] | None:
        result = self._query(
            "MATCH (p:Person {canonical_email: $email}) RETURN p LIMIT 1",
            {"email": email.strip().lower()},
        )
        rows = getattr(result, "result_set", None) or []
        if not rows:
            return None
        node = rows[0][0]
        return dict(getattr(node, "properties", node))

    def find_person_by_identity(self, key: str) -> dict[str, Any] | None:
        result = self._query(
            "MATCH (p:Person)-[:HAS_IDENTITY]->(i:Identity {key: $key}) RETURN p LIMIT 1",
            {"key": key},
        )
        rows = getattr(result, "result_set", None) or []
        if not rows:
            return None
        return dict(getattr(rows[0][0], "properties", rows[0][0]))

    def merge_edge(
        self,
        rel_type: str,
        from_label: str,
        from_id: str,
        to_label: str,
        to_id: str,
        props: dict[str, Any] | None = None,
    ) -> bool:
        if rel_type in TEMPORAL_SCOPES:
            raise ValueError(f"{rel_type} must use supersede_temporal")
        props = props or {}
        set_clause = ", ".join(f"r.{k} = ${k}" for k in props) if props else "r._present = true"
        params = {"from_id": from_id, "to_id": to_id, **props}
        result = self._query(
            f"MATCH (a:{from_label} {{id: $from_id}}) "
            f"MATCH (b:{to_label} {{id: $to_id}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            f"SET {set_clause} "
            f"RETURN type(r)",
            params,
        )
        created = bool(getattr(result, "relationships_created", 0))
        if created:
            self.stats.relationships_created += 1
        else:
            self.stats.relationships_updated += 1
        return created

    def active_edges(self, rel_type: str, to_id: str | None = None) -> list[dict[str, Any]]:
        if to_id:
            result = self._query(
                f"MATCH (a)-[r:{rel_type}]->(b {{id: $to_id}}) "
                f"WHERE r.valid_to IS NULL RETURN a.id, b.id, r",
                {"to_id": to_id},
            )
        else:
            result = self._query(
                f"MATCH (a)-[r:{rel_type}]->(b) WHERE r.valid_to IS NULL RETURN a.id, b.id, r"
            )
        rows = getattr(result, "result_set", None) or []
        out = []
        for row in rows:
            out.append({"from_id": row[0], "to_id": row[1], "rel_type": rel_type})
        return out

    def supersede_temporal(
        self,
        rel_type: str,
        from_label: str,
        from_id: str,
        to_label: str,
        to_id: str,
        *,
        valid_from: str,
        ingested_at: str,
    ) -> str:
        scope = TEMPORAL_SCOPES[rel_type]
        if scope == "target":
            match_old = (
                f"MATCH (to:{to_label} {{id: $to_id}}) "
                f"OPTIONAL MATCH (cur:{from_label})-[r:{rel_type}]->(to) "
                f"WHERE r.valid_to IS NULL "
            )
        else:
            match_old = (
                f"MATCH (from:{from_label} {{id: $from_id}}) "
                f"MATCH (to:{to_label} {{id: $to_id}}) "
                f"OPTIONAL MATCH (from)-[r:{rel_type}]->(to) "
                f"WHERE r.valid_to IS NULL "
            )
        cypher = (
            match_old
            + "WITH to, collect(r) AS olds, collect(startNode(r).id) AS owner_ids "
            "WITH to, olds, ($from_id IN owner_ids) AS already "
            "FOREACH (r IN CASE WHEN already THEN [] ELSE [x IN olds WHERE x IS NOT NULL] END "
            "| SET r.valid_to = $ingested_at) "
            "WITH to, already WHERE NOT already "
            f"MATCH (from:{from_label} {{id: $from_id}}) "
            f"CREATE (from)-[:{rel_type} {{valid_from: $valid_from, ingested_at: $ingested_at}}]->(to) "
            "RETURN already"
        )
        result = self._query(
            cypher,
            {
                "from_id": from_id,
                "to_id": to_id,
                "valid_from": valid_from,
                "ingested_at": ingested_at,
            },
        )
        created = bool(getattr(result, "relationships_created", 0))
        if created:
            self.stats.relationships_created += 1
            return "created"
        self.stats.relationships_updated += 1
        return "noop"


def open_store(tenant_id: str, backend: str | None = None) -> GraphStore:
    name = graph_name(tenant_id)
    chosen = (backend or os.environ.get("ENGRAM_GRAPH_BACKEND") or "falkordb").lower()
    if chosen == "memory":
        store = InMemoryGraphStore(name)
        store.bootstrap((), ())
        return store
    host = os.environ.get("FALKORDB_HOST", "localhost")
    port = int(os.environ.get("FALKORDB_PORT", "6379"))
    try:
        from falkordb import FalkorDB
    except ImportError as exc:
        raise RuntimeError(
            "falkordb is not installed; pip install 'company-brain[graph]' "
            "or set ENGRAM_GRAPH_BACKEND=memory"
        ) from exc
    client = FalkorDB(host=host, port=port)
    graph = client.select_graph(name)
    store = FalkorGraphStore(graph, name)
    from engram_graph_core.bootstrap import INDEXES, UNIQUE_NODE_CONSTRAINTS

    store.bootstrap(INDEXES, UNIQUE_NODE_CONSTRAINTS)
    return store
