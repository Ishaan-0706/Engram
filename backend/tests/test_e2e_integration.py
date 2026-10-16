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
        "team_core_pay",
        "src_slack_inc",
        "evi_018f_latency_auth",
    }

    for forbidden in acme_forbidden_ids:
        assert forbidden not in working_set, f"Leaked record {forbidden} in working_set"
        assert forbidden not in evidence_bag, f"Leaked evidence {forbidden} in evidence_bag"

    # Also assert that no content string mentions acme_payments
    for record in working_set.values():
        assert "acme" not in str(record).lower(), f"Leaked acme data in record: {record}"
    for evidence in evidence_bag.values():
        assert "acme" not in str(evidence).lower(), f"Leaked acme data in evidence: {evidence}"
