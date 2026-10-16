from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from mcp.server.fastmcp import FastMCP

from app.core.config import settings
from app.engram_graph_core.client import get_tenant_graph

ENVELOPE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "shared/contracts/mcp_envelope.schema.json"
)
_ENVELOPE_VALIDATOR = Draft202012Validator(
    json.loads(ENVELOPE_SCHEMA_PATH.read_text()),
    format_checker=Draft202012Validator.FORMAT_CHECKER,
)

HEX64 = re.compile(r"^[0-9a-f]{64}$")

DECISION_HISTORY_CYPHER = """
MATCH (s:System {name: $system_name})<-[:AFFECTS]-(d:Decision)
OPTIONAL MATCH (d)-[:SUPERSEDES*0..2]->(prev:Decision)
OPTIONAL MATCH (d)-[:SUPPORTED_BY]->(e:Evidence)
RETURN s, d, prev, e
"""

DOCUMENTATION_DRIFT_CYPHER = """
MATCH (s:System {name: $system_name})
MATCH (doc:Document)-[:PROPOSED]->(old:Decision)<-[:SUPERSEDES]-(active:Decision)
OPTIONAL MATCH (active)-[:SUPPORTED_BY]->(e:Evidence)
WITH s, doc, old, active, e
WHERE (old)-[:AFFECTS]->(s) OR (active)-[:AFFECTS]->(s) OR (doc)-[:DOCUMENTS]->(s)
RETURN s, doc, old, active, e
"""

SYSTEM_OWNERSHIP_CYPHER = """
MATCH (p:Person)-[r:OWNS]->(s:System {name: $system_name})
WHERE r.valid_to IS NULL
OPTIONAL MATCH (p)-[m:MEMBER_OF]->(t:Team)
WHERE m.valid_to IS NULL
RETURN p, s, t, r
"""


def _fail(code: str, message: str) -> dict[str, Any]:
    payload = {"ok": False, "error": {"code": code, "message": message}}
    _ENVELOPE_VALIDATOR.validate(payload)
    return payload


def _content_hash(raw: Any, excerpt: str, source_uri: str) -> str:
    if isinstance(raw, str) and raw.startswith("sha256:") and HEX64.fullmatch(raw[7:]):
        return raw
    if isinstance(raw, str) and HEX64.fullmatch(raw):
        return f"sha256:{raw}"
    digest = hashlib.sha256(f"{excerpt}\n{source_uri}".encode()).hexdigest()
    return f"sha256:{digest}"


def _node(cell: Any, default_label: str | None = None) -> dict[str, Any] | None:
    if cell is None:
        return None
    props = getattr(cell, "properties", None)
    if props is None and isinstance(cell, dict):
        props = cell
    if props is None:
        return None
    props = dict(props)
    node_id = props.get("id")
    if not node_id:
        return None
    labels = getattr(cell, "labels", None)
    if labels:
        label = labels[0]
    elif default_label:
        label = default_label
    else:
        label = "Node"
    rest = {k: v for k, v in props.items() if k != "id"}
    return {"id": str(node_id), "label": str(label), "properties": rest}


def _evidence(cell: Any) -> dict[str, Any] | None:
    if cell is None:
        return None
    props = getattr(cell, "properties", None)
    if props is None and isinstance(cell, dict):
        props = cell
    if props is None:
        return None
    props = dict(props)
    excerpt = props.get("excerpt")
    source_uri = props.get("source_uri")
    eid = props.get("id")
    record_id = props.get("record_id")
    timestamp = props.get("source_timestamp")
    if not eid or not record_id or not excerpt or not source_uri or not timestamp:
        return None
    return {
        "id": str(eid),
        "record_id": str(record_id),
        "excerpt": str(excerpt),
        "source_uri": str(source_uri),
        "source_timestamp": str(timestamp),
        "content_hash": _content_hash(props.get("content_hash"), str(excerpt), str(source_uri)),
    }


def _ok(tenant_id: str, records: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    seen_r: set[tuple[str, str]] = set()
    unique_records: list[dict[str, Any]] = []
    for rec in records:
        if rec is None:
            continue
        key = (rec["label"], rec["id"])
        if key in seen_r:
            continue
        seen_r.add(key)
        unique_records.append(rec)
    seen_e: set[str] = set()
    unique_evidence: list[dict[str, Any]] = []
    for item in evidence:
        if item is None or item["id"] in seen_e:
            continue
        seen_e.add(item["id"])
        unique_evidence.append(item)
    payload = {
        "ok": True,
        "tenant_id": tenant_id,
        "trace_id": str(uuid.uuid4()),
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "records": unique_records,
        "evidence": unique_evidence,
    }
    _ENVELOPE_VALIDATOR.validate(payload)
    return payload


def _rows(graph: Any, cypher: str, system_name: str) -> list[list[Any]]:
    result = graph.query(cypher, {"system_name": system_name}, timeout=settings.GRAPH_QUERY_TIMEOUT_MS)
    return list(getattr(result, "result_set", None) or [])


def _query_envelope(
    tenant_id: str,
    system_name: str,
    cypher: str,
    record_indexes: list[tuple[int, str]],
    evidence_indexes: list[int],
) -> dict[str, Any]:
    try:
        graph = get_tenant_graph(tenant_id)
        rows = _rows(graph, cypher, system_name)
    except Exception as exc:
        return _fail("query_failed", str(exc))
    records: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for row in rows:
        for idx, label in record_indexes:
            if idx < len(row):
                node = _node(row[idx], label)
                if node:
                    records.append(node)
        for idx in evidence_indexes:
            if idx < len(row):
                item = _evidence(row[idx])
                if item:
                    evidence.append(item)
    try:
        return _ok(tenant_id, records, evidence)
    except Exception as exc:
        return _fail("schema", str(exc))


def get_decision_history(tenant_id: str, system_name: str) -> dict[str, Any]:
    return _query_envelope(
        tenant_id,
        system_name,
        DECISION_HISTORY_CYPHER,
        [(0, "System"), (1, "Decision"), (2, "Decision")],
        [3],
    )


def detect_documentation_drift(tenant_id: str, system_name: str) -> dict[str, Any]:
    return _query_envelope(
        tenant_id,
        system_name,
        DOCUMENTATION_DRIFT_CYPHER,
        [(0, "System"), (1, "Document"), (2, "Decision"), (3, "Decision")],
        [4],
    )


def get_system_ownership(tenant_id: str, system_name: str) -> dict[str, Any]:
    return _query_envelope(
        tenant_id,
        system_name,
        SYSTEM_OWNERSHIP_CYPHER,
        [(0, "Person"), (1, "System"), (2, "Team")],
        [],
    )


mcp = FastMCP("engram-graph")


@mcp.tool(name="get_decision_history")
def get_decision_history_tool(tenant_id: str, system_name: str) -> dict[str, Any]:
    """Decisions that affect a system, a bounded SUPERSEDES chain, and supporting evidence."""
    return get_decision_history(tenant_id, system_name)


@mcp.tool(name="detect_documentation_drift")
def detect_documentation_drift_tool(tenant_id: str, system_name: str) -> dict[str, Any]:
    """Documents that proposed a decision later superseded by an active decision."""
    return detect_documentation_drift(tenant_id, system_name)


@mcp.tool(name="get_system_ownership")
def get_system_ownership_tool(tenant_id: str, system_name: str) -> dict[str, Any]:
    """Active OWNS edges for a system plus the owner's team affiliation."""
    return get_system_ownership(tenant_id, system_name)


from fastapi import FastAPI

app = FastAPI(title="Engram graph MCP")
_http = getattr(mcp, "streamable_http_app", None) or getattr(mcp, "sse_app", None)
if _http is None:
    raise RuntimeError("FastMCP HTTP app is unavailable")
app.mount("/mcp", _http())
