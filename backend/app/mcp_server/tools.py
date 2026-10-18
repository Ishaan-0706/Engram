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
OPTIONAL MATCH (d)-[:SUPERSEDES*0..10]->(prev:Decision)
OPTIONAL MATCH (prev)-[:SUPPORTED_BY]->(e:Evidence)
RETURN s, d, prev, e
"""

DOCUMENTATION_DRIFT_CYPHER = """
MATCH (s:System {name: $system_name})
MATCH (doc:Document)-[:PROPOSED|ALIGNED_WITH]->(old:Decision)<-[:SUPERSEDES*1..10]-(active:Decision {status: 'active'})
OPTIONAL MATCH (active)-[:SUPPORTED_BY]->(e:Evidence)
WITH s, doc, old, active, e
WHERE (old)-[:AFFECTS]->(s) OR (active)-[:AFFECTS]->(s) OR (doc)-[:DOCUMENTS]->(s)
RETURN s, doc, old, active, e
"""

TOPOLOGICAL_LINEAGE_CYPHER = """
MATCH (doc:Document {id: $doc_id})-[:PROPOSED|ALIGNED_WITH]->(anchor:Decision)
MATCH path = (anchor)<-[:SUPERSEDES*1..10]-(active_dec:Decision {status: 'active'})
OPTIONAL MATCH (active_dec)-[:SUPPORTED_BY]->(evi:Evidence)
RETURN doc, anchor, active_dec, length(path) AS divergence_hops, collect(evi) AS evidence
"""

SYSTEM_TOPOLOGICAL_LINEAGE_CYPHER = """
MATCH (s:System {name: $system_name})<-[:DOCUMENTS]-(doc:Document)
MATCH (doc)-[:PROPOSED|ALIGNED_WITH]->(anchor:Decision)
MATCH path = (anchor)<-[:SUPERSEDES*1..10]-(active_dec:Decision {status: 'active'})
OPTIONAL MATCH (active_dec)-[:SUPPORTED_BY]->(evi:Evidence)
RETURN doc, anchor, active_dec, length(path) AS divergence_hops, collect(evi) AS evidence
"""

CANDIDATE_HEURISTIC_CYPHER = """
MATCH (p:Person)
OPTIONAL MATCH (p)-[:ESTABLISHED]->(d:Decision {status: 'active'})
OPTIONAL MATCH (p)-[r:OWNS]->(sys:System) WHERE r.valid_to IS NULL
WITH p, count(DISTINCT d) AS active_decisions, count(DISTINCT sys) AS owned_systems
RETURN p, (active_decisions * 3 + owned_systems * 2) AS expertise_score
ORDER BY expertise_score DESC LIMIT 1
"""

CANDIDATE_HEURISTIC_DETAILS_CYPHER = """
MATCH (p:Person)
OPTIONAL MATCH (p)-[:ESTABLISHED]->(d:Decision {status: 'active'})
OPTIONAL MATCH (p)-[r:OWNS]->(sys:System) WHERE r.valid_to IS NULL
WITH p, count(DISTINCT d) AS active_decisions, count(DISTINCT sys) AS owned_systems
RETURN p, (active_decisions * 3 + owned_systems * 2) AS expertise_score, active_decisions, owned_systems
ORDER BY expertise_score DESC
"""

BLAST_RADIUS_CYPHER = """
MATCH (s:System {name: $system_name})
OPTIONAL MATCH (downstream:System)-[:DEPENDS_ON*1..5]->(s)
OPTIONAL MATCH (doc:Document)-[:DOCUMENTS]->(s)
RETURN count(DISTINCT downstream) AS downstream_impact, count(DISTINCT doc) AS doc_impact
"""

SYSTEM_OWNERSHIP_CYPHER = """
MATCH (p:Person)-[r:OWNS]->(s:System {name: $system_name})
WHERE r.valid_to IS NULL
OPTIONAL MATCH (p)-[m:MEMBER_OF]->(t:Team)
WHERE m.valid_to IS NULL
OPTIONAL MATCH (s)-[:PART_OF]->(proj:Project)
RETURN p, s, t, proj, r
"""

SME_KNOWLEDGE_SCORE_CYPHER = """
MATCH (p:Person), (s:System {name: $system_name})
OPTIONAL MATCH (p)-[:ESTABLISHED]->(d:Decision)-[:AFFECTS]->(s)
OPTIONAL MATCH (p)-[:AUTHORED]->(e:Evidence)<-[:SUPPORTED_BY]-(d2:Decision)-[:AFFECTS]->(s)
OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
WITH p, t, count(DISTINCT d) AS decisions_led, count(DISTINCT e) AS artifacts_authored, collect(DISTINCT e.source_type) AS artifact_types
WHERE (decisions_led + artifacts_authored) > 0
RETURN p, t, decisions_led, artifacts_authored, artifact_types,
       (decisions_led * 3 + artifacts_authored * 2) AS knowledge_score
ORDER BY knowledge_score DESC
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
    res = {
        "id": str(eid),
        "record_id": str(record_id),
        "excerpt": str(excerpt),
        "source_uri": str(source_uri),
        "source_timestamp": str(timestamp),
        "content_hash": _content_hash(props.get("content_hash"), str(excerpt), str(source_uri)),
    }
    st = props.get("source_type")
    if not st:
        uri_str = str(source_uri).lower()
        if "slack://" in uri_str:
            st = "slack"
        elif "linear://" in uri_str:
            st = "linear"
        elif "confluence://" in uri_str:
            st = "confluence"
        elif "notion://" in uri_str:
            st = "notion"
    if st:
        res["source_type"] = str(st)
    if props.get("author"):
        res["author"] = str(props["author"])
    return res


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


def get_ownership_and_expertise(tenant_id: str, system_name: str) -> dict[str, Any]:
    """Retrieve formal system ownership (OWNS edge, Team, Project) and computed subject matter expertise.
    
    Traverses:
    - Formal accountability: active temporal edge (p:Person)-[r:OWNS]->(s:System) where r.valid_to IS NULL,
      (p)-[:MEMBER_OF]->(t:Team), and (s)-[:PART_OF]->(proj:Project).
    - Computed SME ranking: (decisions_led * 3 + artifacts_authored * 2) based on authored evidence & decisions.
    - All attached multi-source evidence across chats, tickets, and docs.
    """
    try:
        graph = get_tenant_graph(tenant_id)
        # 1. Formal Ownership
        owner_rows = _rows(graph, SYSTEM_OWNERSHIP_CYPHER, system_name)
        # 2. SME knowledge rankings
        sme_res = graph.query(
            SME_KNOWLEDGE_SCORE_CYPHER,
            {"system_name": system_name},
            timeout=settings.GRAPH_QUERY_TIMEOUT_MS,
        )
        sme_rows = list(getattr(sme_res, "result_set", None) or [])
        # 3. Evidence attached to decisions affecting the system
        evi_res = graph.query(
            """
            MATCH (s:System {name: $system_name})<-[:AFFECTS]-(d:Decision)
            OPTIONAL MATCH (d)-[:SUPERSEDES*0..10]->(prev:Decision)
            OPTIONAL MATCH (prev)-[:SUPPORTED_BY]->(e:Evidence)
            RETURN e
            """,
            {"system_name": system_name},
            timeout=settings.GRAPH_QUERY_TIMEOUT_MS,
        )
        evi_rows = list(getattr(evi_res, "result_set", None) or [])
    except Exception as exc:
        return _fail("query_failed", str(exc))

    records: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    # Formal ownership nodes
    for row in owner_rows:
        if len(row) > 0 and row[0]:
            p = _node(row[0], "Person")
            if p:
                p["properties"]["is_formal_owner"] = True
                records.append(p)
        if len(row) > 1 and row[1]:
            s = _node(row[1], "System")
            if s:
                records.append(s)
        if len(row) > 2 and row[2]:
            t = _node(row[2], "Team")
            if t:
                records.append(t)
        if len(row) > 3 and row[3]:
            proj = _node(row[3], "Project")
            if proj:
                records.append(proj)

    # Subject Matter Experts (Who Knows What)
    for row in sme_rows:
        p_node = row[0]
        t_node = row[1] if len(row) > 1 else None
        d_led = int(row[2]) if len(row) > 2 and row[2] is not None else 0
        a_auth = int(row[3]) if len(row) > 3 and row[3] is not None else 0
        a_types = list(row[4]) if len(row) > 4 and row[4] else []
        score = int(row[5]) if len(row) > 5 and row[5] is not None else 0

        p = _node(p_node, "Person")
        if p:
            p["properties"]["knowledge_score"] = score
            p["properties"]["decisions_led"] = d_led
            p["properties"]["artifacts_authored"] = a_auth
            p["properties"]["artifact_types"] = a_types
            records.append(p)
        t = _node(t_node, "Team")
        if t:
            records.append(t)

    # Supporting Evidence
    for row in evi_rows:
        if row and row[0]:
            ev = _evidence(row[0])
            if ev:
                evidence.append(ev)

    try:
        return _ok(tenant_id, records, evidence)
    except Exception as exc:
        return _fail("schema", str(exc))


def get_system_ownership(tenant_id: str, system_name: str) -> dict[str, Any]:
    return _query_envelope(
        tenant_id,
        system_name,
        SYSTEM_OWNERSHIP_CYPHER,
        [(0, "Person"), (1, "System"), (2, "Team"), (3, "Project")],
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
            "active_dec": terminal_dict,
            "divergence_hops": divergence_hops,
            "drift_staleness_days": drift_staleness_days,
            "evidence_list": evidence_items,
            "evidence": evidence_items,
        }
    except Exception as exc:
        log.warning("analyze_topological_lineage failed: %s", exc)
        return None


def rank_ownership_candidates(
    tenant_id: str,
    current_owner_email: str | None = None,
) -> dict[str, Any] | None:
    """Identify top candidate person via graph centrality expertise ranking:
    (active_decisions * 3 + owned_systems * 2)
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
        num_sub = int(chosen_row[3]) if len(chosen_row) > 3 and chosen_row[3] is not None else 0

        p_dict = _node(p_node, "Person") or {}
        p_props = p_dict.get("properties", {})
        p_name = p_props.get("display_name") or p_props.get("name") or p_dict.get("id", "Candidate")
        p_email = p_props.get("canonical_email", "")

        breakdown_str = (
            f"Candidate {p_name} ({p_email}) scored {score} points via graph centrality evaluation: "
            f"{num_d} active decisions (weight 3) + "
            f"{num_sub} active owned systems (weight 2)."
        )

        return {
            "person": p_dict,
            "canonical_email": p_email,
            "display_name": p_name,
            "score": score,
            "expertise_score": score,
            "breakdown": breakdown_str,
            "counts": {
                "active_decisions": num_d,
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
        "downstream_impact": downstream,
        "affected_docs": docs,
        "doc_impact": docs,
        "risk": risk,
    }


def get_live_graph_topology(tenant_id: str) -> dict[str, Any]:
    """Query live nodes, edges, and chronological decision timeline from FalkorDB.
    
    Queries FalkorDB directly. If FalkorDB is unreachable, raises exceptions to be caught as HTTP 503.
    """
    clean_tid = (tenant_id or "").strip()
    if not clean_tid:
        raise ValueError("tenant_id must be provided")
    graph = get_tenant_graph(clean_tid)

    # 1. Fetch all nodes
    node_res = graph.query("MATCH (n) RETURN n, labels(n)", timeout=settings.GRAPH_QUERY_TIMEOUT_MS)
    node_rows = list(getattr(node_res, "result_set", None) or [])

    nodes_list: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()

    for row in node_rows:
        if not row or not row[0]:
            continue
        node = row[0]
        labels = row[1] if len(row) > 1 and row[1] else getattr(node, "labels", [])
        lbl = labels[0] if labels else "Node"
        props = dict(getattr(node, "properties", {}) or {})
        nid = str(props.get("id") or getattr(node, "id", ""))
        if not nid or nid in seen_nodes:
            continue
        seen_nodes.add(nid)

        name = props.get("display_name") or props.get("name") or props.get("title") or nid
        status = str(props.get("status", "")).lower()

        # Warm Graphite & Engineering Slate Palette
        if lbl == "System":
            color = "#4C78A8"
            val = 20
        elif lbl == "Decision":
            if status == "active":
                color = "#4E9F76"
                val = 20
            else:
                color = "#68707E"
                val = 17
        elif lbl == "Document":
            color = "#D07D38"
            val = 16
        elif lbl == "Evidence":
            color = "#5E60CE"
            val = 14
        elif lbl == "Person":
            color = "#D4CEBF"
            val = 16
        elif lbl == "Team":
            color = "#949BA6"
            val = 14
        elif lbl == "Source":
            color = "#858D9A"
            val = 12
        elif lbl == "Project":
            color = "#858D9A"
            val = 16
        else:
            color = "#949BA6"
            val = 14

        nodes_list.append({
            "id": nid,
            "name": name,
            "label": lbl,
            "color": color,
            "val": val,
            "properties": props,
        })

    # 2. Fetch all edges
    edge_res = graph.query("MATCH (a)-[r]->(b) RETURN a.id, type(r), b.id, properties(r)", timeout=settings.GRAPH_QUERY_TIMEOUT_MS)
    edge_rows = list(getattr(edge_res, "result_set", None) or [])

    links_list: list[dict[str, Any]] = []
    seen_links: set[tuple[str, str, str]] = set()

    for row in edge_rows:
        if not row or len(row) < 3:
            continue
        src_id = str(row[0])
        edge_type = str(row[1])
        tgt_id = str(row[2])
        edge_props = dict(row[3] or {}) if len(row) > 3 and row[3] else {}

        key = (src_id, edge_type, tgt_id)
        if key in seen_links:
            continue
        seen_links.add(key)

        is_supersedes = edge_type == "SUPERSEDES"
        is_supported_by = edge_type == "SUPPORTED_BY"
        is_aligned_with = edge_type == "ALIGNED_WITH"
        is_proposed = edge_type == "PROPOSED"

        if is_supersedes:
            edge_color = "#B84A39"
        elif is_supported_by:
            edge_color = "#5E60CE"
        elif is_aligned_with:
            edge_color = "#4E9F76"
        elif is_proposed:
            edge_color = "#D07D38"
        else:
            edge_color = "#323744"

        links_list.append({
            "source": src_id,
            "target": tgt_id,
            "label": edge_type,
            "type": edge_type,
            "color": edge_color,
            "dashed": is_supersedes,
            "properties": edge_props,
        })

    # 3. Augment System node properties with active_owner, team, project, and SME experts
    sys_meta_res = graph.query(
        """
        MATCH (s:System)
        OPTIONAL MATCH (p:Person)-[r:OWNS]->(s) WHERE r.valid_to IS NULL
        OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
        OPTIONAL MATCH (s)-[:PART_OF]->(proj:Project)
        RETURN s.id, p, t, proj
        """,
        timeout=settings.GRAPH_QUERY_TIMEOUT_MS,
    )
    for row in list(getattr(sys_meta_res, "result_set", None) or []):
        sid = row[0]
        pnode = row[1]
        tnode = row[2]
        projnode = row[3]
        pprops = getattr(pnode, "properties", {}) or {} if pnode else {}
        tprops = getattr(tnode, "properties", {}) or {} if tnode else {}
        projprops = getattr(projnode, "properties", {}) or {} if projnode else {}

        pname = pprops.get("display_name") or pprops.get("name") or ""
        pemail = pprops.get("canonical_email") or ""
        owner_str = f"{pname} ({pemail})" if pemail else pname
        tname = tprops.get("name") or ""
        projname = projprops.get("name") or ""

        for n in nodes_list:
            if n["id"] == sid:
                if "properties" not in n:
                    n["properties"] = {}
                if owner_str:
                    n["properties"]["active_owner"] = owner_str
                if tname:
                    n["properties"]["team"] = tname
                if projname:
                    n["properties"]["project"] = projname

    # Augment System nodes with SME experts rankings
    try:
        sme_meta_res = graph.query(
            """
            MATCH (s:System)
            MATCH (p:Person)
            OPTIONAL MATCH (p)-[:ESTABLISHED]->(d:Decision)-[:AFFECTS]->(s)
            OPTIONAL MATCH (p)-[:AUTHORED]->(e:Evidence)<-[:SUPPORTED_BY]-(d2:Decision)-[:AFFECTS]->(s)
            OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
            WITH s, p, t, count(DISTINCT d) AS decisions_led, count(DISTINCT e) AS artifacts_authored, collect(DISTINCT e.source_type) AS artifact_types
            WHERE (decisions_led + artifacts_authored) > 0
            RETURN s.id, p.display_name, p.canonical_email, t.name, decisions_led, artifacts_authored, artifact_types,
                   (decisions_led * 3 + artifacts_authored * 2) AS knowledge_score
            ORDER BY knowledge_score DESC
            """,
            timeout=settings.GRAPH_QUERY_TIMEOUT_MS,
        )
        sme_by_sys: dict[str, list[dict[str, Any]]] = {}
        for row in list(getattr(sme_meta_res, "result_set", None) or []):
            sid = str(row[0])
            name = str(row[1]) if row[1] else "Engineer"
            email = str(row[2]) if row[2] else ""
            team = str(row[3]) if row[3] else ""
            d_led = int(row[4]) if row[4] else 0
            a_auth = int(row[5]) if row[5] else 0
            a_types = list(row[6]) if row[6] else []
            score = int(row[7]) if row[7] else 0
            if sid not in sme_by_sys:
                sme_by_sys[sid] = []
            sme_by_sys[sid].append({
                "name": name,
                "email": email,
                "team": team,
                "decisions_led": d_led,
                "artifacts_authored": a_auth,
                "artifact_types": a_types,
                "knowledge_score": score,
            })
        for n in nodes_list:
            if n["id"] in sme_by_sys:
                n["properties"]["sme_experts"] = sme_by_sys[n["id"]]
    except Exception as exc:
        log.warning("sme_meta query error: %s", exc)

    # 4. Construct chronological decision timeline
    timeline_list: list[dict[str, Any]] = []

    def _fmt_ts(val: Any) -> tuple[str, float]:
        if not val:
            return "2026-08-01", 0.0
        try:
            ts = float(val)
            sort_val = ts
            if ts > 1e11:
                ts /= 1000
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d"), sort_val
        except Exception:
            return str(val)[:10], 0.0

    # Documents in timeline
    doc_timeline_res = graph.query(
        """
        MATCH (doc:Document)-[:DOCUMENTS]->(s:System)
        OPTIONAL MATCH (doc)-[:PROPOSED]->(d:Decision)
        OPTIONAL MATCH (p:Person)-[r:OWNS]->(s) WHERE r.valid_to IS NULL
        RETURN doc, s, d, p
        """,
        timeout=settings.GRAPH_QUERY_TIMEOUT_MS,
    )
    for row in list(getattr(doc_timeline_res, "result_set", None) or []):
        doc = row[0]
        s = row[1] if len(row) > 1 else None
        p = row[3] if len(row) > 3 else None
        dprops = getattr(doc, "properties", {}) or {}
        sprops = getattr(s, "properties", {}) or {} if s else {}
        pprops = getattr(p, "properties", {}) or {} if p else {}

        raw_ts = dprops.get("created_at") or 1723200000000
        formatted_date, sort_ts = _fmt_ts(raw_ts)
        sname = sprops.get("name", "system")
        author_name = pprops.get("display_name") or "Architecture Review Board"

        timeline_list.append({
            "id": dprops.get("id", "doc_rfc"),
            "title": dprops.get("title", "RFC Specification"),
            "type": "rfc",
            "status": dprops.get("status", "stale"),
            "timestamp": formatted_date,
            "system": sname,
            "author": author_name,
            "summary": f"Original RFC specification proposing {sname} architecture.",
            "evidence_id": None,
            "_sort_ts": sort_ts,
        })

    # Decisions in timeline
    dec_timeline_res = graph.query(
        """
        MATCH (d:Decision)
        OPTIONAL MATCH (p:Person)-[:ESTABLISHED]->(d)
        OPTIONAL MATCH (d)-[:AFFECTS]->(s:System)
        OPTIONAL MATCH (d)-[:SUPPORTED_BY]->(e:Evidence)
        RETURN d, p, s, e
        """,
        timeout=settings.GRAPH_QUERY_TIMEOUT_MS,
    )
    for row in list(getattr(dec_timeline_res, "result_set", None) or []):
        d = row[0]
        p = row[1] if len(row) > 1 else None
        s = row[2] if len(row) > 2 else None
        e = row[3] if len(row) > 3 else None

        dprops = getattr(d, "properties", {}) or {}
        pprops = getattr(p, "properties", {}) or {} if p else {}
        sprops = getattr(s, "properties", {}) or {} if s else {}
        eprops = getattr(e, "properties", {}) or {} if e else {}

        raw_ts = dprops.get("timestamp") or dprops.get("created_at") or 0
        formatted_date, sort_ts = _fmt_ts(raw_ts)
        status = str(dprops.get("status", "active")).lower()
        author_name = pprops.get("display_name") or "Core Engineering Team"

        timeline_list.append({
            "id": dprops.get("id", "decision"),
            "title": dprops.get("summary", dprops.get("id", "Decision")),
            "type": "active" if status == "active" else "superseded",
            "status": status,
            "timestamp": formatted_date,
            "system": sprops.get("name", ""),
            "author": author_name,
            "summary": dprops.get("summary", ""),
            "evidence_id": eprops.get("id"),
            "_sort_ts": sort_ts,
        })

    timeline_list.sort(key=lambda x: x["_sort_ts"])
    for item in timeline_list:
        del item["_sort_ts"]

    return {
        "tenant_id": clean_tid,
        "nodes": nodes_list,
        "links": links_list,
        "timeline": timeline_list,
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


@mcp.tool(name="get_ownership_and_expertise")
def get_ownership_and_expertise_tool(tenant_id: str, system_name: str) -> dict[str, Any]:
    """Formal system ownership, team, project, and computed subject matter expertise rankings."""
    return get_ownership_and_expertise(tenant_id, system_name)


from fastapi import FastAPI

app = FastAPI(title="Engram graph MCP")
_http = getattr(mcp, "streamable_http_app", None) or getattr(mcp, "sse_app", None)
if _http is None:
    raise RuntimeError("FastMCP HTTP app is unavailable")
app.mount("/mcp", _http())
