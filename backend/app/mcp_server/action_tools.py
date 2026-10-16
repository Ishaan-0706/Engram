"""MCP action tools – agent-proposed graph mutations.

Every action:
  1. Verifies that all referenced entities exist before mutating.
  2. Runs within the MCP_QUERY_TIMEOUT_MS (2500 ms) budget.
  3. Logs the change via ``logging.getLogger(__name__)``.
  4. Returns the standard *split envelope* (``_ok`` / ``_fail`` from ``tools``).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.core.config import settings
from app.engram_graph_core.client import get_tenant_graph
from app.mcp_server.tools import _fail, _node, _ok, mcp

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cypher templates
# ---------------------------------------------------------------------------

# Step 1: close the existing active OWNS edge, create the new one, return both
# nodes.  FalkorDB does not support multi-statement transactions, so we merge
# close + create into a single atomic GRAPH.QUERY.
REASSIGN_OWNER_CYPHER = """\
MATCH (new:Person {canonical_email: $email})
MATCH (s:System {name: $system_name})
OPTIONAL MATCH (old:Person)-[r:OWNS]->(s)
  WHERE r.valid_to IS NULL
FOREACH (_ IN CASE WHEN r IS NOT NULL THEN [1] ELSE [] END |
  SET r.valid_to = $now_ms
)
CREATE (new)-[r2:OWNS {valid_from: $now_ms, valid_to: null, updated_via: 'agent_proposal'}]->(s)
RETURN new, s
"""

MARK_DOCUMENT_UPDATED_CYPHER = """\
MATCH (doc:Document {id: $document_id})
MATCH (dec:Decision {id: $superseding_decision_id})
SET doc.status = 'updated', doc.last_reviewed_at = $now_ms
CREATE (doc)-[:ALIGNED_WITH {created_at: $now_ms}]->(dec)
RETURN doc
"""

# ---------------------------------------------------------------------------
# Existence checks (lightweight MATCH + RETURN id)
# ---------------------------------------------------------------------------

_PERSON_EXISTS = "MATCH (p:Person {canonical_email: $email}) RETURN p.id LIMIT 1"
_SYSTEM_EXISTS = "MATCH (s:System {name: $name}) RETURN s.id LIMIT 1"
_DOCUMENT_EXISTS = "MATCH (d:Document {id: $id}) RETURN d.id LIMIT 1"
_DECISION_EXISTS = "MATCH (dec:Decision {id: $id}) RETURN dec.id LIMIT 1"


def _exists(graph: Any, cypher: str, params: dict[str, Any]) -> bool:
    result = graph.query(cypher, params, timeout=settings.GRAPH_QUERY_TIMEOUT_MS)
    rows = getattr(result, "result_set", None) or []
    return len(rows) > 0


# ---------------------------------------------------------------------------
# Core action functions
# ---------------------------------------------------------------------------


def reassign_system_owner(
    tenant_id: str,
    system_name: str,
    new_owner_email: str,
) -> dict[str, Any]:
    """Close the active OWNS edge on *system_name* and create a new one
    pointing to the Person identified by *new_owner_email*.

    Returns the standard envelope with the updated ``Person`` and ``System``
    records (no evidence array for mutations).
    """
    try:
        graph = get_tenant_graph(tenant_id)
    except Exception as exc:
        log.error("reassign_system_owner: graph connection failed – %s", exc)
        return _fail("query_failed", str(exc))

    # --- existence guard ---------------------------------------------------
    if not _exists(graph, _PERSON_EXISTS, {"email": new_owner_email}):
        msg = f"Person with canonical_email '{new_owner_email}' not found"
        log.warning("reassign_system_owner: %s", msg)
        return _fail("not_found", msg)

    if not _exists(graph, _SYSTEM_EXISTS, {"name": system_name}):
        msg = f"System '{system_name}' not found"
        log.warning("reassign_system_owner: %s", msg)
        return _fail("not_found", msg)

    # --- atomic mutation ----------------------------------------------------
    now_ms = int(time.time() * 1000)
    try:
        result = graph.query(
            REASSIGN_OWNER_CYPHER,
            {
                "system_name": system_name,
                "email": new_owner_email,
                "new_owner_email": new_owner_email,
                "now_ms": now_ms,
            },
            timeout=settings.GRAPH_QUERY_TIMEOUT_MS,
        )
    except Exception as exc:
        log.error("reassign_system_owner: mutation failed – %s", exc)
        return _fail("mutation_failed", str(exc))

    rows = getattr(result, "result_set", None) or []
    records: list[dict[str, Any]] = []
    for row in rows:
        person = _node(row[0], "Person")
        system = _node(row[1], "System")
        if person:
            records.append(person)
        if system:
            records.append(system)

    log.info(
        "reassign_system_owner: tenant=%s system=%s new_owner=%s now_ms=%d",
        tenant_id,
        system_name,
        new_owner_email,
        now_ms,
    )

    try:
        return _ok(tenant_id, records, [])
    except Exception as exc:
        return _fail("schema", str(exc))


def mark_document_updated(
    tenant_id: str,
    document_id: str,
    superseding_decision_id: str,
) -> dict[str, Any]:
    """Set ``doc.status = 'updated'`` and link the Document to the
    superseding Decision via an ``ALIGNED_WITH`` edge.

    Returns the standard envelope with the updated ``Document`` record.
    """
    try:
        graph = get_tenant_graph(tenant_id)
    except Exception as exc:
        log.error("mark_document_updated: graph connection failed – %s", exc)
        return _fail("query_failed", str(exc))

    # --- existence guard ---------------------------------------------------
    if not _exists(graph, _DOCUMENT_EXISTS, {"id": document_id}):
        msg = f"Document '{document_id}' not found"
        log.warning("mark_document_updated: %s", msg)
        return _fail("not_found", msg)

    if not _exists(graph, _DECISION_EXISTS, {"id": superseding_decision_id}):
        msg = f"Decision '{superseding_decision_id}' not found"
        log.warning("mark_document_updated: %s", msg)
        return _fail("not_found", msg)

    # --- atomic mutation ----------------------------------------------------
    now_ms = int(time.time() * 1000)
    try:
        result = graph.query(
            MARK_DOCUMENT_UPDATED_CYPHER,
            {
                "document_id": document_id,
                "superseding_decision_id": superseding_decision_id,
                "now_ms": now_ms,
            },
            timeout=settings.GRAPH_QUERY_TIMEOUT_MS,
        )
    except Exception as exc:
        log.error("mark_document_updated: mutation failed – %s", exc)
        return _fail("mutation_failed", str(exc))

    rows = getattr(result, "result_set", None) or []
    records: list[dict[str, Any]] = []
    for row in rows:
        doc = _node(row[0], "Document")
        if doc:
            records.append(doc)

    log.info(
        "mark_document_updated: tenant=%s doc=%s superseding_decision=%s now_ms=%d",
        tenant_id,
        document_id,
        superseding_decision_id,
        now_ms,
    )

    try:
        return _ok(tenant_id, records, [])
    except Exception as exc:
        return _fail("schema", str(exc))


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------

@mcp.tool(name="reassign_system_owner")
def reassign_system_owner_tool(
    tenant_id: str,
    system_name: str,
    new_owner_email: str,
) -> dict[str, Any]:
    """Reassign ownership of a system to a different person (by email).

    Closes the existing active OWNS edge and creates a new one.
    Requires confirmation before execution.
    """
    return reassign_system_owner(tenant_id, system_name, new_owner_email)


@mcp.tool(name="mark_document_updated")
def mark_document_updated_tool(
    tenant_id: str,
    document_id: str,
    superseding_decision_id: str,
) -> dict[str, Any]:
    """Mark a document as updated and link it to the superseding decision.

    Sets doc.status = 'updated' and creates an ALIGNED_WITH edge.
    """
    return mark_document_updated(tenant_id, document_id, superseding_decision_id)
