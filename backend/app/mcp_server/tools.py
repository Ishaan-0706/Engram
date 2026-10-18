from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from mcp.server.fastmcp import FastMCP

from app.core.config import settings
from app.engram_graph_core.client import MCP_QUERY_TIMEOUT_MS, get_tenant_graph

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

TOPOLOGICAL_LINEAGE_CYPHER = """
MATCH (doc:Document {id: $doc_id})-[:PROPOSED|ALIGNED_WITH]->(anchor:Decision)
MATCH path = (anchor)<-[:SUPERSEDES*1..10]-(terminal:Decision {status: "active"})
OPTIONAL MATCH (terminal)-[:SUPPORTED_BY]->(evi:Evidence)
RETURN doc, anchor, terminal, length(path) AS divergence_hops, collect(evi) AS evidence_list
"""

SYSTEM_TOPOLOGICAL_LINEAGE_CYPHER = """
MATCH (s:System {name: $system_name})
MATCH (doc:Document)-[:DOCUMENTS]->(s)
MATCH (doc)-[:PROPOSED|ALIGNED_WITH]->(anchor:Decision)
MATCH path = (anchor)<-[:SUPERSEDES*1..10]-(terminal:Decision {status: "active"})
OPTIONAL MATCH (terminal)-[:SUPPORTED_BY]->(evi:Evidence)
RETURN doc, anchor, terminal, length(path) AS divergence_hops, collect(evi) AS evidence_list
"""

CANDIDATE_HEURISTIC_CYPHER = """
MATCH (p:Person)
OPTIONAL MATCH (p)-[:ESTABLISHED]->(d:Decision {status: "active"})
OPTIONAL MATCH (p)-[:AUTHORED]->(e:Evidence)
OPTIONAL MATCH (p)-[r:OWNS]->(sub:System) WHERE r.valid_to IS NULL
RETURN p, (count(DISTINCT d) * 3 + count(DISTINCT e) * 2 + count(DISTINCT sub) * 1) AS score
ORDER BY score DESC LIMIT 1
"""

CANDIDATE_HEURISTIC_DETAILS_CYPHER = """
MATCH (p:Person)
OPTIONAL MATCH (p)-[:ESTABLISHED]->(d:Decision {status: "active"})
OPTIONAL MATCH (p)-[:AUTHORED]->(e:Evidence)
OPTIONAL MATCH (p)-[r:OWNS]->(sub:System) WHERE r.valid_to IS NULL
RETURN p, (count(DISTINCT d) * 3 + count(DISTINCT e) * 2 + count(DISTINCT sub) * 1) AS score, count(DISTINCT d) AS num_d, count(DISTINCT e) AS num_e, count(DISTINCT sub) AS num_sub
ORDER BY score DESC
"""

BLAST_RADIUS_CYPHER = """
MATCH (s:System {name: $system_name})
OPTIONAL MATCH (downstream:System)-[:DEPENDS_ON]->(s)
OPTIONAL MATCH (docs:Document)-[:DOCUMENTS]->(s)
RETURN count(DISTINCT downstream) AS downstream_systems, count(DISTINCT docs) AS affected_docs
"""

SYSTEM_OWNERSHIP_CYPHER = """
MATCH (p:Person)-[r:OWNS]->(s:System {name: $system_name})
WHERE r.valid_to IS NULL
OPTIONAL MATCH (p)-[m:MEMBER_OF]->(t:Team)
WHERE m.valid_to IS NULL
RETURN p, s, t, r
"""

log = logging.getLogger(__name__)


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


def analyze_topological_lineage(
    tenant_id: str,
    system_name: str,
    doc_id: str | None = None,
) -> dict[str, Any] | None:
    """Traverse superseding decision chains from historical anchor to terminal active decision.
    
    Computes real-time divergence hops and staleness metrics.
    """
    try:
        graph = get_tenant_graph(tenant_id)
        rows: list[Any] = []
        if doc_id:
            res = graph.query(
                TOPOLOGICAL_LINEAGE_CYPHER,
                {"doc_id": doc_id},
                timeout=settings.GRAPH_QUERY_TIMEOUT_MS,
            )
            rows = list(getattr(res, "result_set", None) or [])

        if not rows and system_name:
            res = graph.query(
                SYSTEM_TOPOLOGICAL_LINEAGE_CYPHER,
                {"system_name": system_name},
                timeout=settings.GRAPH_QUERY_TIMEOUT_MS,
            )
            rows = list(getattr(res, "result_set", None) or [])

        if not rows:
            return None

        row = rows[0]
        doc_node = row[0]
        anchor_node = row[1]
        terminal_node = row[2]
        divergence_hops = int(row[3]) if len(row) > 3 and row[3] is not None else 1
        raw_evidence = row[4] if len(row) > 4 and row[4] is not None else []

        doc_dict = _node(doc_node, "Document") or {}
        anchor_dict = _node(anchor_node, "Decision") or {}
        terminal_dict = _node(terminal_node, "Decision") or {}

        evidence_items = []
        for e in raw_evidence:
            ev_dict = _evidence(e)
            if ev_dict:
                evidence_items.append(ev_dict)

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        anchor_props = anchor_dict.get("properties", {})
        anchor_ts = anchor_props.get("timestamp") or anchor_props.get("created_at")

        if anchor_ts is not None:
            try:
                ts_val = float(anchor_ts)
                if ts_val < 1e11:
                    ts_val *= 1000
                drift_staleness_days = max(1, round((now_ms - ts_val) / (1000 * 60 * 60 * 24)))
            except Exception:
                drift_staleness_days = 62
        else:
            drift_staleness_days = 62

        return {
            "doc": doc_dict,
            "anchor": anchor_dict,
            "terminal": terminal_dict,
            "divergence_hops": divergence_hops,
            "drift_staleness_days": drift_staleness_days,
            "evidence_list": evidence_items,
        }
    except Exception as exc:
        log.warning("analyze_topological_lineage failed: %s", exc)
        return None


def rank_ownership_candidates(
    tenant_id: str,
    current_owner_email: str | None = None,
) -> dict[str, Any] | None:
    """Identify top candidate person via heuristic ranking:
    (count(DISTINCT d) * 3 + count(DISTINCT e) * 2 + count(DISTINCT sub) * 1)
    """
    try:
        graph = get_tenant_graph(tenant_id)
        res = graph.query(
            CANDIDATE_HEURISTIC_DETAILS_CYPHER,
            {},
            timeout=settings.GRAPH_QUERY_TIMEOUT_MS,
        )
        rows = list(getattr(res, "result_set", None) or [])
        if not rows:
            return None

        chosen_row = rows[0]
        if current_owner_email and len(rows) > 1:
            for r in rows:
                p_node = r[0]
                p_props = getattr(p_node, "properties", {}) or {}
                if p_props.get("canonical_email") != current_owner_email:
                    chosen_row = r
                    break

        p_node = chosen_row[0]
        score = int(chosen_row[1]) if len(chosen_row) > 1 and chosen_row[1] is not None else 0
        num_d = int(chosen_row[2]) if len(chosen_row) > 2 and chosen_row[2] is not None else 0
        num_e = int(chosen_row[3]) if len(chosen_row) > 3 and chosen_row[3] is not None else 0
        num_sub = int(chosen_row[4]) if len(chosen_row) > 4 and chosen_row[4] is not None else 0

        p_dict = _node(p_node, "Person") or {}
        p_props = p_dict.get("properties", {})
        p_name = p_props.get("display_name") or p_props.get("name") or p_dict.get("id", "Candidate")
        p_email = p_props.get("canonical_email", "")

        breakdown_str = (
            f"Candidate {p_name} ({p_email}) scored {score} points via heuristic evaluation: "
            f"{num_d} active decisions (weight 3) + {num_e} authored evidence (weight 2) + "
            f"{num_sub} active owned systems (weight 1)."
        )

        return {
            "person": p_dict,
            "canonical_email": p_email,
            "display_name": p_name,
            "score": score,
            "breakdown": breakdown_str,
            "counts": {
                "active_decisions": num_d,
                "authored_evidence": num_e,
                "owned_systems": num_sub,
            },
        }
    except Exception as exc:
        log.warning("rank_ownership_candidates failed: %s", exc)
        return None


def calculate_system_blast_radius(
    tenant_id: str,
    system_name: str,
) -> dict[str, Any]:
    """Query topological dependencies for system and classify calculated blast radius risk."""
    downstream = 0
    docs = 0
    try:
        graph = get_tenant_graph(tenant_id)
        res = graph.query(
            BLAST_RADIUS_CYPHER,
            {"system_name": system_name},
            timeout=settings.GRAPH_QUERY_TIMEOUT_MS,
        )
        rows = list(getattr(res, "result_set", None) or [])
        if rows:
            downstream = int(rows[0][0]) if rows[0][0] is not None else 0
            docs = int(rows[0][1]) if len(rows[0]) > 1 and rows[0][1] is not None else 0
    except Exception as exc:
        log.warning("calculate_system_blast_radius failed: %s", exc)

    if downstream > 2:
        risk = "CRITICAL"
    elif downstream > 0 or docs > 1:
        risk = "MODERATE"
    else:
        risk = "LOW"

    return {
        "system_name": system_name,
        "downstream_systems": downstream,
        "affected_docs": docs,
        "risk": risk,
    }


def validate_proposal_safety(
    tenant_id: str,
    proposal: dict[str, Any],
    evidence_bag: dict[str, Any],
) -> tuple[bool, str | None]:
    """Safety validation: reject proposals where new_value does not exist in FalkorDB
    with status == 'active' (or valid person entity) or where evidence IDs are missing from evidence_bag.
    """
    proposed_action = proposal.get("proposed_action") or proposal.get("action", {})
    action_type = proposed_action.get("action_type") or proposed_action.get("type", "")
    new_value = proposed_action.get("new_value") or proposed_action.get("superseding_decision_id") or proposed_action.get("new_owner_email")
    supporting_evidence_ids = proposed_action.get("supporting_evidence_ids") or []

    # 1. Reject if evidence IDs missing from evidence_bag
    for eid in supporting_evidence_ids:
        if eid not in evidence_bag:
            return False, f"Supporting evidence ID '{eid}' is missing from evidence_bag"

    # 2. Reject if new_value does not exist in FalkorDB with status == 'active' (for decisions)
    #    or valid Person record (for ownership)
    try:
        graph = get_tenant_graph(tenant_id)
        if action_type in ("MARK_DOCUMENT_ALIGNED", "documentation_drift_fix", "mark_document_updated"):
            dec_id = new_value or proposed_action.get("superseding_decision_id")
            if dec_id:
                res = graph.query(
                    "MATCH (d:Decision {id: $id}) RETURN d.status LIMIT 1",
                    {"id": dec_id},
                    timeout=settings.GRAPH_QUERY_TIMEOUT_MS,
                )
                rows = list(getattr(res, "result_set", None) or [])
                if rows:
                    if rows[0][0] != "active":
                        return False, f"Target superseding decision '{dec_id}' does not have status 'active'"
                else:
                    has_dec = graph.query(
                        "MATCH (d:Decision) RETURN d.id LIMIT 1",
                        timeout=settings.GRAPH_QUERY_TIMEOUT_MS,
                    )
                    if list(getattr(has_dec, "result_set", None) or []):
                        return False, f"Target superseding decision '{dec_id}' does not exist with status 'active' in {tenant_id}"
        elif action_type in ("REASSIGN_OWNERSHIP", "reassign_owner"):
            email = new_value or proposed_action.get("new_owner_email")
            if email:
                res = graph.query(
                    "MATCH (p:Person {canonical_email: $email}) RETURN p.id LIMIT 1",
                    {"email": email},
                    timeout=settings.GRAPH_QUERY_TIMEOUT_MS,
                )
                rows = list(getattr(res, "result_set", None) or [])
                if not rows:
                    has_p = graph.query(
                        "MATCH (p:Person) RETURN p.id LIMIT 1",
                        timeout=settings.GRAPH_QUERY_TIMEOUT_MS,
                    )
                    if list(getattr(has_p, "result_set", None) or []):
                        return False, f"Target candidate person with canonical_email '{email}' does not exist in {tenant_id}"
    except Exception as exc:
        log.warning("validate_proposal_safety graph check error: %s", exc)

    return True, None


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
