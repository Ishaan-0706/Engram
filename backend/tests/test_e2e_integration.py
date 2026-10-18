"""End-to-end integration test suite testing the live FastAPI API against FalkorDB and Redis.

Tests:
1. test_grounded_citation_turn:
   Sends query "Why was payment gateway auth changed?", verifies HTTP 200, status COMPLETED,
   epoch incremented, and that all statements cite valid IDs in evidence_bag.
2. test_documentation_drift_and_proposal:
   Sends query about stale documentation, verifies status transitions to AWAITING_CONFIRMATION
   with a staged proposal and valid snapshot_hash.
3. test_proposal_confirmation_execution:
   Calls POST /api/confirm with valid idempotency key and snapshot hash, confirms HTTP 200,
   and verifies via Cypher query that the document now has status 'updated' and [:ALIGNED_WITH] edge in FalkorDB.
4. test_concurrent_stale_hash_conflict:
   Submits a confirmation with a stale/tampered snapshot_hash, asserting an HTTP 409 Conflict
   response containing current_snapshot_hash.
5. test_cross_tenant_isolation:
   Calls /api/turn on tenant_nexus_infra asking about payment-gateway, asserting zero records
   or evidence from acme_payments are leaked.
"""

from __future__ import annotations

import os
from typing import Generator

from fastapi.testclient import TestClient
import pytest

pytest.importorskip("falkordb")

from app.agent.state import generate_uuidv7
from app.engram_graph_core.client import get_tenant_graph
from app.main import app
from scripts.reset_demo import reset_demo


@pytest.fixture(scope="module")
def live_client() -> Generator[TestClient, None, None]:
    """TestClient wired to live FastAPI app, with fresh pristine graphs."""
    reset_demo()
    with TestClient(app) as client:
        yield client
    # Clean up after suite
    reset_demo()


def test_grounded_citation_turn(live_client: TestClient) -> None:
    """Sends query 'Why was payment gateway auth changed?', verifies HTTP 200,
    status COMPLETED, epoch incremented, and that all statements cite valid IDs
    in evidence_bag."""
    resp = live_client.post(
        "/api/turn",
        json={
            "tenant_id": "acme_payments",
            "session_id": "session_e2e_grounded",
            "user_query": "Why was payment gateway auth changed?",
            "epoch": 0,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    turn = data["turn"]

    # Status must be COMPLETED
    assert turn["status"] == "COMPLETED"
    # Epoch must be incremented (0 -> 1 -> 2)
    assert turn["epoch"] > 0
    assert data["epoch"] == turn["epoch"]

    # Evidence bag must contain valid evidence
    evidence_bag = turn.get("evidence_bag", {})
    assert len(evidence_bag) > 0

    # Verify that all synthesized statements cite valid IDs in evidence_bag
    synthesis_traces = turn.get("synthesis_traces", [])
    assert len(synthesis_traces) > 0
    last_trace = synthesis_traces[-1]
    assert last_trace["ok"] is True
    claims = last_trace["payload"].get("claims", [])
    assert len(claims) > 0

    for claim in claims:
        cited_ids = claim.get("cited_evidence_ids", [])
        assert len(cited_ids) > 0, "Claim must cite at least one evidence ID"
        for eid in cited_ids:
            assert eid in evidence_bag, f"Cited ID {eid} not found in evidence_bag"


def test_documentation_drift_and_proposal(live_client: TestClient) -> None:
    """Sends query about stale documentation, verifies status transitions to
    AWAITING_CONFIRMATION with a staged proposal and valid snapshot_hash."""
    resp = live_client.post(
        "/api/turn",
        json={
            "tenant_id": "acme_payments",
            "session_id": "session_e2e_drift",
            "user_query": "Is the documentation for payment-gateway stale or out of date?",
            "epoch": 0,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    turn = data["turn"]

    # Status must transition to AWAITING_CONFIRMATION
    assert turn["status"] == "AWAITING_CONFIRMATION"

    # Staged proposal must be present with valid snapshot_hash
    proposal = turn.get("pending_proposal")
    assert proposal is not None
    assert "proposal_id" in proposal
    assert proposal["snapshot_hash"].startswith("sha256:")
    assert len(proposal["snapshot_hash"]) == 71  # "sha256:" (7) + 64 hex chars


def test_proposal_confirmation_execution(live_client: TestClient) -> None:
    """Calls POST /api/confirm with valid idempotency key and snapshot hash,
    confirms HTTP 200, and verifies via Cypher query that the document now has
    status 'updated' and [:ALIGNED_WITH] edge in FalkorDB."""
    # 1. Stage the proposal
    session_id = "session_e2e_confirm_exec"
    turn_resp = live_client.post(
        "/api/turn",
        json={
            "tenant_id": "acme_payments",
            "session_id": session_id,
            "user_query": "Fix stale documentation drift for payment-gateway",
            "epoch": 0,
        },
    )
    assert turn_resp.status_code == 200, turn_resp.text
    turn = turn_resp.json()["turn"]
    assert turn["status"] == "AWAITING_CONFIRMATION"
    proposal = turn["pending_proposal"]

    # 2. Confirm the proposal
    idempotency_k = generate_uuidv7()
    confirm_resp = live_client.post(
        "/api/confirm",
        json={
            "tenant_id": "acme_payments",
            "session_id": session_id,
            "proposal_id": proposal["proposal_id"],
            "snapshot_hash": proposal["snapshot_hash"],
            "idempotency_key": idempotency_k,
        },
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    receipt = confirm_resp.json()
    assert receipt["status"] == "completed"
    assert receipt["executed"] is True

    # 3. Verify via Cypher query in FalkorDB that doc.status = 'updated'
    # and [:ALIGNED_WITH] edge was created
    graph = get_tenant_graph("acme_payments")
    doc_res = graph.query("MATCH (d:Document {id: 'doc_auth_rfc'}) RETURN d.status").result_set
    assert len(doc_res) > 0
    assert doc_res[0][0] == "updated"

    edge_res = graph.query(
        "MATCH (d:Document {id: 'doc_auth_rfc'})-[:ALIGNED_WITH]->(dec:Decision) RETURN dec.id"
    ).result_set
    assert len(edge_res) > 0


def test_concurrent_stale_hash_conflict(live_client: TestClient) -> None:
    """Submits a confirmation with a stale/tampered snapshot_hash, asserting
    an HTTP 409 Conflict response containing current_snapshot_hash."""
    session_id = "session_e2e_stale_hash"
    turn_resp = live_client.post(
        "/api/turn",
        json={
            "tenant_id": "acme_payments",
            "session_id": session_id,
            "user_query": "Check outdated documentation drift for payment-gateway",
            "epoch": 0,
        },
    )
    assert turn_resp.status_code == 200, turn_resp.text
    turn = turn_resp.json()["turn"]
    proposal = turn["pending_proposal"]

    # Tampered snapshot hash
    stale_hash = "sha256:" + ("0" * 64)
    confirm_resp = live_client.post(
        "/api/confirm",
        json={
            "tenant_id": "acme_payments",
            "session_id": session_id,
            "proposal_id": proposal["proposal_id"],
            "snapshot_hash": stale_hash,
            "idempotency_key": generate_uuidv7(),
        },
    )
    assert confirm_resp.status_code == 409
    body = confirm_resp.json()
    detail = body.get("detail", body)
    assert "current_snapshot_hash" in detail
    assert detail["current_snapshot_hash"].startswith("sha256:")


def test_cross_tenant_isolation(live_client: TestClient) -> None:
    """Calls /api/turn on tenant_nexus_infra asking about payment-gateway,
    asserting zero records or evidence from acme_payments are leaked."""
    resp = live_client.post(
        "/api/turn",
        json={
            "tenant_id": "nexus_infra",
            "session_id": "session_e2e_isolation",
            "user_query": "What is the architecture and decision history for payment-gateway?",
            "epoch": 0,
        },
    )
    assert resp.status_code == 200, resp.text
    turn = resp.json()["turn"]

    working_set = turn.get("working_set", {})
    evidence_bag = turn.get("evidence_bag", {})

    # Ensure zero entities from acme_payments leaked into nexus_infra turn
    acme_forbidden_ids = {
        "sys_payment_gw",
        "doc_auth_rfc",
        "dec_oauth_introspection",
        "dec_ed25519_local",
        "usr_018f_priya",
        "usr_018f_aarav",
        "usr_018f_rohan",
        "team_core_pay",
        "proj_zero_trust_2026",
        "src_slack_inc",
        "src_linear_pay_402",
        "src_confluence_rfc",
        "evi_018f_latency_auth",
        "evi_018f_ticket_pay402",
        "evi_018f_rfc_proposal",
    }

    for forbidden in acme_forbidden_ids:
        assert forbidden not in working_set, f"Leaked record {forbidden} in working_set"
        assert forbidden not in evidence_bag, f"Leaked evidence {forbidden} in evidence_bag"

    # Also assert that no content string mentions acme_payments
    for record in working_set.values():
        assert "acme" not in str(record).lower(), f"Leaked acme data in record: {record}"
    for evidence in evidence_bag.values():
        assert "acme" not in str(evidence).lower(), f"Leaked acme data in evidence: {evidence}"


# ==============================================================================
# PHASE 4: 5 MANDATORY "COMPANY BRAIN" RUBRIC VERIFICATION TESTS
# ==============================================================================

def test_unified_graph_sources(live_client: TestClient) -> None:
    """Verifies docs, tickets, and chats are retrieved together in a unified graph
    for tenant_acme_payments (Slack chat, Linear ticket, and Confluence doc)."""
    # 1. Verify via live graph topology endpoint
    graph_resp = live_client.get("/api/graph/acme_payments")
    assert graph_resp.status_code == 200, graph_resp.text
    graph_data = graph_resp.json()
    nodes = graph_data["nodes"]
    
    # Collect source types represented in the graph
    source_types = set()
    for n in nodes:
        props = n.get("properties", {})
        if "source_type" in props:
            source_types.add(props["source_type"].lower())
            
    assert "slack" in source_types, "Slack chat source missing from unified graph"
    assert "linear" in source_types, "Linear ticket source missing from unified graph"
    assert "confluence" in source_types, "Confluence doc source missing from unified graph"

    # 2. Verify via conversational turn tracing payment-gateway auth
    resp = live_client.post(
        "/api/turn",
        json={
            "tenant_id": "acme_payments",
            "session_id": "session_e2e_unified_sources",
            "user_query": "Why was the payment gateway authentication method changed? Trace the decision back to its Slack and ticket sources.",
            "epoch": 0,
        },
    )
    assert resp.status_code == 200, resp.text
    turn = resp.json()["turn"]
    evidence_bag = turn.get("evidence_bag", {})
    assert len(evidence_bag) >= 3, "Evidence bag must contain multi-source enterprise evidence"

    bag_source_types = {e.get("source_type") for e in evidence_bag.values() if e.get("source_type")}
    assert "slack" in bag_source_types, "Slack chat evidence missing from evidence bag"
    assert "linear" in bag_source_types, "Linear ticket evidence missing from evidence bag"
    assert "confluence" in bag_source_types, "Confluence RFC evidence missing from evidence bag"


def test_who_owns_and_who_knows(live_client: TestClient) -> None:
    """Verifies both temporal formal ownership ([:OWNS], Team, Project) and computed
    deep domain expertise (knowledge_score from authored evidence/decisions)."""
    from app.mcp_server.tools import get_ownership_and_expertise

    # Direct tool verification
    res = get_ownership_and_expertise("acme_payments", "payment-gateway")
    assert "error" not in res, f"Tool error: {res}"
    records = res.get("records", [])

    # Formal Ownership checks
    active_owner = next(
        (r for r in records if r.get("label") == "Person" and r.get("properties", {}).get("is_formal_owner")),
        None,
    )
    assert active_owner is not None
    assert active_owner["properties"]["display_name"] == "Priya Nair"
    assert active_owner["properties"]["canonical_email"] == "priya@acme.com"

    team = next((r for r in records if r.get("label") == "Team"), None)
    assert team is not None
    assert team["id"] == "team_core_pay"
    assert "Core Payments" in team["properties"]["name"]

    project = next((r for r in records if r.get("label") == "Project"), None)
    assert project is not None
    assert project["id"] == "proj_zero_trust_2026"

    # Computed SME checks
    smes = [r for r in records if r.get("label") == "Person" and "knowledge_score" in r.get("properties", {})]
    assert len(smes) >= 2, "Must return ranked Subject Matter Experts"

    sme_names = [s["properties"]["display_name"] for s in smes]
    assert "Aarav Mehta" in sme_names
    assert "Rohan Verma" in sme_names

    top_sme = smes[0]
    assert top_sme["properties"]["knowledge_score"] > 0
    # Formula check: score == decisions_led * 3 + artifacts_authored * 2
    for s in smes:
        props = s["properties"]
        expected = props["decisions_led"] * 3 + props["artifacts_authored"] * 2
        assert props["knowledge_score"] == expected, f"Knowledge score mismatch for {props['display_name']}"

    # Verify conversational turn synthesis explains both
    resp = live_client.post(
        "/api/turn",
        json={
            "tenant_id": "acme_payments",
            "session_id": "session_e2e_who_owns_vs_knows",
            "user_query": "Who formally owns payment-gateway, which team is responsible, and who knows the most about its Ed25519 implementation?",
            "epoch": 0,
        },
    )
    assert resp.status_code == 200
    turn_data = resp.json()["turn"]
    assert turn_data["status"] == "COMPLETED"
    payload = turn_data["synthesis_traces"][-1]["payload"]
    all_text = payload.get("summary", "") + " " + " ".join(c.get("text", "") for c in payload.get("claims", []))
    assert "Priya" in all_text or "Core Payments" in all_text
    assert "Aarav" in all_text or "Rohan" in all_text


def test_decision_lineage_trace(live_client: TestClient) -> None:
    """Verifies multi-hop [:SUPERSEDES*0..10] traversal back to original source quotes,
    authors, timestamps, and SHA-256 hashes."""
    from app.mcp_server.tools import get_decision_history

    history = get_decision_history("acme_payments", "payment-gateway")
    assert "error" not in history
    records = history.get("records", [])
    assert len(records) >= 2, "Lineage must contain both active and superseded decisions"

    active_dec = next(
        (r for r in records if r.get("label") == "Decision" and r.get("properties", {}).get("status") == "active"),
        None,
    )
    superseded_dec = next(
        (r for r in records if r.get("label") == "Decision" and r.get("properties", {}).get("status") == "superseded"),
        None,
    )
    assert active_dec is not None, "Missing active decision in lineage"
    assert superseded_dec is not None, "Missing superseded decision in lineage"

    # Lineage connection in graph
    graph = get_tenant_graph("acme_payments")
    sup_cnt = graph.query(
        "MATCH (a:Decision {id: $aid})-[:SUPERSEDES]->(b:Decision {id: $bid}) RETURN count(*)",
        {"aid": active_dec["id"], "bid": superseded_dec["id"]},
    ).result_set[0][0]
    assert sup_cnt == 1, "Lineage chain broken: [:SUPERSEDES] edge missing"

    # Evidence envelope
    evidence = history.get("evidence", [])
    assert len(evidence) >= 1
    for evi in evidence:
        assert evi["content_hash"].startswith("sha256:")
        assert len(evi["content_hash"]) == 71
        assert evi.get("excerpt"), "Evidence excerpt must not be empty"
        assert evi.get("author"), "Evidence author must be present"


def test_keeping_knowledge_current_and_409_safety(live_client: TestClient) -> None:
    """Verifies drift detection -> AWAITING_CONFIRMATION -> 409 stale snapshot rejection ->
    200 atomic mutation confirmation ([:ALIGNED_WITH])."""
    session_id = "session_e2e_knowledge_current_409"

    # Step 1: Detect drift
    turn_resp = live_client.post(
        "/api/turn",
        json={
            "tenant_id": "acme_payments",
            "session_id": session_id,
            "user_query": "Check if the Payments Auth RFC v1 document has drifted from current decisions and stage an update to keep knowledge current.",
            "epoch": 0,
        },
    )
    assert turn_resp.status_code == 200, turn_resp.text
    turn = turn_resp.json()["turn"]
    assert turn["status"] == "AWAITING_CONFIRMATION"
    proposal = turn.get("pending_proposal")
    assert proposal is not None
    assert proposal["action"]["type"] == "documentation_drift_fix"
    assert proposal["action"]["document_id"] == "doc_auth_rfc"
    assert proposal["snapshot_hash"].startswith("sha256:")

    # Step 2: 409 Stale Snapshot Rejection
    stale_hash = "sha256:" + ("f" * 64)
    conflict_resp = live_client.post(
        "/api/confirm",
        json={
            "tenant_id": "acme_payments",
            "session_id": session_id,
            "proposal_id": proposal["proposal_id"],
            "snapshot_hash": stale_hash,
            "idempotency_key": generate_uuidv7(),
        },
    )
    assert conflict_resp.status_code == 409, f"Expected 409 Conflict, got {conflict_resp.status_code}"
    conflict_data = conflict_resp.json().get("detail", conflict_resp.json())
    assert conflict_data["current_snapshot_hash"] == proposal["snapshot_hash"]

    # Step 3: 200 Atomic Mutation Confirmation
    confirm_resp = live_client.post(
        "/api/confirm",
        json={
            "tenant_id": "acme_payments",
            "session_id": session_id,
            "proposal_id": proposal["proposal_id"],
            "snapshot_hash": proposal["snapshot_hash"],
            "idempotency_key": generate_uuidv7(),
        },
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    receipt = confirm_resp.json()
    assert receipt["status"] == "completed"
    assert receipt["executed"] is True

    # Step 4: Verify in FalkorDB
    graph = get_tenant_graph("acme_payments")
    res = graph.query("MATCH (d:Document {id: 'doc_auth_rfc'}) RETURN d.status").result_set
    assert res[0][0] == "updated"
    edge_res = graph.query(
        "MATCH (d:Document {id: 'doc_auth_rfc'})-[:ALIGNED_WITH]->(dec:Decision {id: 'dec_ed25519_local'}) RETURN dec.id"
    ).result_set
    assert len(edge_res) == 1, "[:ALIGNED_WITH] edge to active decision must exist"


def test_strict_multi_tenant_isolation(live_client: TestClient) -> None:
    """Verifies strict zero-leakage cross-tenant isolation between acme_payments and nexus_infra."""
    # Run turn with isolated session
    resp = live_client.post(
        "/api/turn",
        json={
            "tenant_id": "nexus_infra",
            "session_id": "session_e2e_isolation_strict",
            "user_query": "What is the architecture and decision history for payment-gateway?",
            "epoch": 0,
        },
    )
    assert resp.status_code == 200, resp.text
    turn = resp.json()["turn"]
    working_set = turn.get("working_set", {})
    evidence_bag = turn.get("evidence_bag", {})

    acme_forbidden_ids = {
        "sys_payment_gw",
        "doc_auth_rfc",
        "dec_oauth_introspection",
        "dec_ed25519_local",
        "usr_018f_priya",
        "usr_018f_aarav",
        "usr_018f_rohan",
        "team_core_pay",
        "proj_zero_trust_2026",
        "src_slack_inc",
        "src_linear_pay_402",
        "src_confluence_rfc",
        "evi_018f_latency_auth",
        "evi_018f_ticket_pay402",
        "evi_018f_rfc_proposal",
    }

    for forbidden in acme_forbidden_ids:
        assert forbidden not in working_set, f"Leaked record {forbidden} in working_set"
        assert forbidden not in evidence_bag, f"Leaked evidence {forbidden} in evidence_bag"

    # In addition, check live graph topology endpoints for both tenants
    acme_graph = live_client.get("/api/graph/acme_payments").json()
    nexus_graph = live_client.get("/api/graph/nexus_infra").json()

    acme_node_ids = {n["id"] for n in acme_graph["nodes"]}
    nexus_node_ids = {n["id"] for n in nexus_graph["nodes"]}

    # Intersection must be empty - absolute isolation
    overlap = acme_node_ids.intersection(nexus_node_ids)
    assert len(overlap) == 0, f"Cross-tenant node ID leakage detected: {overlap}"
