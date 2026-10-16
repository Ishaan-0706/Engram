from __future__ import annotations

GRAPH_QUERY_TIMEOUT_MS = 2000

INDEXES = (
    "CREATE INDEX FOR (p:Person) ON (p.id)",
    "CREATE INDEX FOR (p:Person) ON (p.canonical_email)",
    "CREATE INDEX FOR (i:Identity) ON (i.key)",
    "CREATE INDEX FOR (s:Source) ON (s.id)",
    "CREATE INDEX FOR (s:Source) ON (s.content_hash)",
    "CREATE INDEX FOR (e:Evidence) ON (e.id)",
    "CREATE INDEX FOR (d:Decision) ON (d.id)",
    "CREATE INDEX FOR (t:Ticket) ON (t.id)",
    "CREATE INDEX FOR (p:Project) ON (p.id)",
    "CREATE INDEX FOR (t:Team) ON (t.id)",
    "CREATE INDEX FOR (d:Document) ON (d.id)",
)

# Unique node keys. Relationship uniqueness for active temporal edges is
# enforced in one GRAPH.QUERY (valid_to IS NULL is not constrainable).
UNIQUE_NODE_CONSTRAINTS = (
    ("Person", ["id"]),
    ("Identity", ["key"]),
    ("Source", ["id"]),
    ("Evidence", ["id"]),
    ("Decision", ["id"]),
    ("Ticket", ["id"]),
    ("Project", ["id"]),
    ("Team", ["id"]),
    ("Document", ["id"]),
)


def graph_name(tenant_id: str) -> str:
    if not tenant_id or any(c in tenant_id for c in " \n\t"):
        raise ValueError("tenant_id must be a non-empty token")
    return f"tenant:{tenant_id}"


def bootstrap_graph(store: object) -> None:
    store.bootstrap(INDEXES, UNIQUE_NODE_CONSTRAINTS)
