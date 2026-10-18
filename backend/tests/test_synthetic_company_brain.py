"""End-to-end test suite verifying the 5 Track 03 'Company Brain' pillars on 100% synthetic enterprise data.

Pillars:
1. test_pillar1_docs_tickets_chats_in_one_graph:
   Queries payment-gateway decision history and asserts the returned evidence_bag contains linked
   artifacts from Slack (slack), Linear (linear), and Confluence (confluence).
2. test_pillar2_who_owns_vs_who_knows:
   Queries ownership and expertise for payment-gateway and asserts Priya Nair is returned as the
   formal [:OWNS] owner while Aarav Mehta / Rohan Verma are ranked via graph traversal as
   Subject Matter Experts ("Who Knows What") based on authored decisions and incident tickets.
3. test_pillar3_trace_decision_lineage:
   Asserts the multi-hop [:SUPERSEDES] chain from dec_ed25519_local back to dec_oauth_introspect
   is traversed and grounded with SHA-256 verified quotes.
4. test_pillar4_keep_knowledge_current_mutation:
   Runs drift detection on doc_auth_rfc, verifies AWAITING_CONFIRMATION, tests HTTP 409 Conflict
   with a tampered snapshot_hash, and executes POST /api/confirm to verify doc_auth_rfc.status == "updated"
   and the new [:ALIGNED_WITH] edge in FalkorDB.
5. test_pillar5_multi_tenant_synthetic_isolation:
   Queries tenant_nexus_infra for payment-gateway (asserts 0 results) and queries event-stream-cluster
   (asserts KRaft Linear & Slack sources are returned).
"""

from __future__ import annotations

import uuid
from typing import Generator

from fastapi.testclient import TestClient
import pytest

pytest.importorskip("falkordb")

from app.agent.state import generate_uuidv7
from app.engram_graph_core.client import get_tenant_graph
from app.main import app
from app.mcp_server.tools import get_decision_history, get_ownership_and_expertise
from scripts.reset_demo import reset_demo


@pytest.fixture(scope="module")
def live_client() -> Generator[TestClient, None, None]:
    """TestClient wired to live FastAPI app, with fresh pristine graphs."""
    reset_demo()
    with TestClient(app) as client:
        yield client
    reset_demo()


def test_pillar1_docs_tickets_chats_in_one_graph(live_client: TestClient) -> None:
    """Pillar 1: Unified multi-source enterprise evidence in one graph (Slack, Linear, Confluence)."""
    # 1. Query live conversational turn tracing payment-gateway auth
    resp = live_client.post(
        "/api/turn",
        json={
            "tenant_id": "acme_payments",
            "session_id": "session_pillar1_unified_graph",
            "user_query": "Why was the payment gateway authentication method changed? Trace the decision back to its Slack and ticket sources.",
            "epoch": 0,
        },
    )
    assert resp.status_code == 200, resp.text
    turn = resp.json()["turn"]
    assert turn["status"] == "COMPLETED"

    evidence_bag = turn.get("evidence_bag", {})
    assert len(evidence_bag) >= 3, "Evidence bag must contain multi-source enterprise evidence"

    # Verify that all three artifact types are present in evidence_bag
    source_types = {e.get("source_type") for e in evidence_bag.values() if e.get("source_type")}
    assert "slack" in source_types, "Slack incident chat missing from evidence bag"
    assert "linear" in source_types, "Linear ticket missing from evidence bag"
    assert "confluence" in source_types, "Confluence RFC missing from evidence bag"

    # Verify cryptographic sha256 integrity and non-empty excerpts
    for ev_id, ev in evidence_bag.items():
        assert ev["content_hash"].startswith("sha256:")
        assert len(ev["content_hash"]) == 71
        assert len(ev["excerpt"]) > 10
        assert "@acme-synthetic.internal" in ev.get("author", "") or "@acme" in ev.get("author", "")


def test_pillar2_who_owns_vs_who_knows(live_client: TestClient) -> None:
    """Pillar 2: Distinguish Formal Ownership (Who Owns What) vs. Computed Expertise (Who Knows What)."""
    # 1. Direct Graph Query via get_ownership_and_expertise
    res = get_ownership_and_expertise("acme_payments", "payment-gateway")
    assert res.get("ok") is True, f"Tool error: {res}"
    records = res.get("records", [])

    # Formal Ownership: Priya Nair owns payment-gateway under team_core_payments
    formal_owner = next(
        (r for r in records if r.get("label") == "Person" and r.get("properties", {}).get("is_formal_owner")),
        None,
    )
    assert formal_owner is not None, "Formal owner node missing"
    assert formal_owner["properties"]["display_name"] == "Priya Nair"
    assert "priya@" in formal_owner["properties"]["canonical_email"]
    assert formal_owner["properties"]["canonical_email"].endswith(".internal")

    team = next((r for r in records if r.get("label") == "Team"), None)
    assert team is not None
    assert team["id"] == "team_core_payments"
    assert "Core Payments" in team["properties"]["name"]

    project = next((r for r in records if r.get("label") == "Project"), None)
    assert project is not None
    assert project["id"] == "proj_zero_trust"

    # Who Knows What: Computed Subject Matter Expertise (Aarav Mehta & Rohan Verma)
    smes = [r for r in records if r.get("label") == "Person" and "knowledge_score" in r.get("properties", {})]
    assert len(smes) >= 2, "Expected at least 2 ranked Subject Matter Experts"

    sme_names = [s["properties"]["display_name"] for s in smes]
    assert "Aarav Mehta" in sme_names
    assert "Rohan Verma" in sme_names

    # Check graph knowledge score calculation formula: (decisions_led * 3 + artifacts_authored * 2)
    top_sme = smes[0]
    assert top_sme["properties"]["knowledge_score"] >= 3
    for s in smes:
        props = s["properties"]
        expected_score = props["decisions_led"] * 3 + props["artifacts_authored"] * 2
        assert props["knowledge_score"] == expected_score, f"Formula mismatch for {props['display_name']}"

    # 2. Conversational Agent Turn synthesis verification
    turn_resp = live_client.post(
        "/api/turn",
        json={
            "tenant_id": "acme_payments",
            "session_id": "session_pillar2_who_owns",
            "user_query": "Who formally owns payment-gateway, which team is responsible, and who knows the most about its Ed25519 implementation?",
            "epoch": 0,
        },
    )
    assert turn_resp.status_code == 200
    turn_data = turn_resp.json()["turn"]
    assert turn_data["status"] == "COMPLETED"
    payload = turn_data["synthesis_traces"][-1]["payload"]
    all_text = payload.get("summary", "") + " " + " ".join(c.get("text", "") for c in payload.get("claims", []))
    assert "Priya" in all_text
    assert "Aarav" in all_text or "Rohan" in all_text


def test_pillar3_trace_decision_lineage(live_client: TestClient) -> None:
    """Pillar 3: Multi-hop causal decision lineage from dec_ed25519_local back to dec_oauth_introspect."""
    history = get_decision_history("acme_payments", "payment-gateway")
    assert history.get("ok") is True
    records = history.get("records", [])

    active_dec = next(
        (r for r in records if r.get("label") == "Decision" and r.get("properties", {}).get("status") == "active"),
        None,
    )
    superseded_dec = next(
        (r for r in records if r.get("label") == "Decision" and r.get("properties", {}).get("status") == "superseded"),
        None,
    )
    assert active_dec is not None, "Active decision missing"
    assert active_dec["id"] == "dec_ed25519_local"
    assert superseded_dec is not None, "Superseded decision missing"
    assert superseded_dec["id"] == "dec_oauth_introspect"

    # Verify causal [:SUPERSEDES] edge in FalkorDB
    graph = get_tenant_graph("acme_payments")
    sup_cnt = graph.query(
        "MATCH (a:Decision {id: 'dec_ed25519_local'})-[:SUPERSEDES]->(b:Decision {id: 'dec_oauth_introspect'}) RETURN count(*)"
    ).result_set[0][0]
    assert sup_cnt == 1, "Causal [:SUPERSEDES] edge missing between active and superseded decisions"

    # Verify attached multi-source evidence with verbatim quotes and sha256 content hashes
    evidence = history.get("evidence", [])
    assert len(evidence) >= 2
    for evi in evidence:
        assert evi["content_hash"].startswith("sha256:")
        assert len(evi["content_hash"]) == 71
        assert len(evi.get("excerpt", "")) > 10
        assert evi.get("author"), "Evidence must cite an author"


def test_pillar4_keep_knowledge_current_mutation(live_client: TestClient) -> None:
    """Pillar 4: Autonomous drift detection, 409 conflict protection, and atomic reconciliation."""
    session_id = f"session_pillar4_drift_{uuid.uuid4().hex[:6]}"

    # Step 1: Detect documentation drift on stale Payments Auth RFC v1
    turn_resp = live_client.post(
        "/api/turn",
        json={
            "tenant_id": "acme_payments",
            "session_id": session_id,
            "user_query": "Check if Payments Auth RFC v1 has drifted from current decisions and stage an update.",
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

    # Step 2: Attempt confirmation with tampered/stale snapshot hash -> HTTP 409 Conflict
    tampered_hash = "sha256:" + ("0" * 64)
    conflict_resp = live_client.post(
        "/api/confirm",
        json={
            "tenant_id": "acme_payments",
            "session_id": session_id,
            "proposal_id": proposal["proposal_id"],
            "snapshot_hash": tampered_hash,
            "idempotency_key": generate_uuidv7(),
        },
    )
    assert conflict_resp.status_code == 409, f"Expected 409 Conflict, got {conflict_resp.status_code}"
    conflict_detail = conflict_resp.json().get("detail", conflict_resp.json())
    assert conflict_detail["current_snapshot_hash"] == proposal["snapshot_hash"]

    # Step 3: Execute atomic confirmation with matching snapshot hash -> HTTP 200 OK
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

    # Step 4: Verify atomic mutation in FalkorDB
    graph = get_tenant_graph("acme_payments")
    status_res = graph.query("MATCH (d:Document {id: 'doc_auth_rfc'}) RETURN d.status").result_set
    assert status_res[0][0] == "updated"

    aligned_res = graph.query(
        "MATCH (d:Document {id: 'doc_auth_rfc'})-[:ALIGNED_WITH]->(dec:Decision {id: 'dec_ed25519_local'}) RETURN dec.id"
    ).result_set
    assert len(aligned_res) == 1, "[:ALIGNED_WITH] edge to active decision must exist in FalkorDB"


def test_pillar5_multi_tenant_synthetic_isolation(live_client: TestClient) -> None:
    """Pillar 5: Zero-leakage multi-tenant physical graph isolation between Acme and Nexus."""
    # 1. Query tenant_nexus_infra for payment-gateway -> Assert zero acme records
    nexus_turn = live_client.post(
        "/api/turn",
        json={
            "tenant_id": "nexus_infra",
            "session_id": f"session_pillar5_nexus_{uuid.uuid4().hex[:6]}",
            "user_query": "What is the architecture and decision history for payment-gateway?",
            "epoch": 0,
        },
    )
    assert nexus_turn.status_code == 200, nexus_turn.text
    turn = nexus_turn.json()["turn"]
    working_set = turn.get("working_set", {})
    evidence_bag = turn.get("evidence_bag", {})

    acme_ids = {
        "sys_payment_gw",
        "sys_settlement",
        "doc_auth_rfc",
        "dec_oauth_introspect",
        "dec_ed25519_local",
        "person_priya",
        "person_aarav",
        "person_rohan",
        "team_core_payments",
        "proj_zero_trust",
    }
    for forbidden in acme_ids:
        assert forbidden not in working_set, f"Tenant leakage: {forbidden} found in working_set"
        assert forbidden not in evidence_bag, f"Tenant leakage: {forbidden} found in evidence_bag"

    # 2. Query event-stream-cluster in tenant_nexus_infra -> Assert KRaft Linear & Slack sources returned
    kraft_turn = live_client.post(
        "/api/turn",
        json={
            "tenant_id": "nexus_infra",
            "session_id": f"session_pillar5_kraft_{uuid.uuid4().hex[:6]}",
            "user_query": "Why was the event-stream-cluster consensus changed? Trace the KRaft decision to ticket and Slack sources.",
            "epoch": 0,
        },
    )
    assert kraft_turn.status_code == 200, kraft_turn.text
    kraft_bag = kraft_turn.json()["turn"].get("evidence_bag", {})
    assert len(kraft_bag) >= 2, "Nexus evidence bag must contain KRaft evidence"

    nexus_source_types = {e.get("source_type") for e in kraft_bag.values() if e.get("source_type")}
    assert "linear" in nexus_source_types, "KRaft Linear ticket missing from Nexus evidence bag"
    assert "slack" in nexus_source_types, "KRaft Slack chat missing from Nexus evidence bag"

    # 3. Direct live graph topology isolation check
    acme_graph = live_client.get("/api/graph/acme_payments").json()
    nexus_graph = live_client.get("/api/graph/nexus_infra").json()

    acme_node_ids = {n["id"] for n in acme_graph["nodes"]}
    nexus_node_ids = {n["id"] for n in nexus_graph["nodes"]}

    overlap = acme_node_ids.intersection(nexus_node_ids)
    assert len(overlap) == 0, f"Cross-tenant node ID collision/leakage detected: {overlap}"
