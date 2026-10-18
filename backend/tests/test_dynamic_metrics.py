"""Unit and integration tests for autonomous dynamic decision & metric engine."""

from __future__ import annotations

import pytest

from app.mcp_server.tools import (
    analyze_topological_lineage,
    calculate_system_blast_radius,
    rank_ownership_candidates,
    validate_proposal_safety,
)
from scripts.reset_demo import reset_demo


@pytest.fixture(scope="module", autouse=True)
def setup_demo_graphs():
    pytest.importorskip("falkordb")
    reset_demo()


def test_topological_lineage_and_drift_calculation():
    """Verify dynamic Cypher traversal computes divergence_hops and staleness."""
    lineage = analyze_topological_lineage(
        tenant_id="acme_payments",
        system_name="payment-gateway",
        doc_id="doc_auth_rfc",
    )
    assert lineage is not None
    assert lineage["doc"]["id"] == "doc_auth_rfc"
    assert lineage["anchor"]["id"] in ("dec_oauth_introspect", "dec_oauth_introspection")
    assert lineage["terminal"]["id"] == "dec_ed25519_local"
    assert lineage["terminal"]["properties"]["status"] == "active"
    assert lineage["divergence_hops"] >= 1
    assert lineage["drift_staleness_days"] == 62
    assert len(lineage["evidence_list"]) > 0


def test_autonomous_heuristic_candidate_scoring():
    """Verify heuristic score formula: 3 * active_decisions + 2 * owned_systems."""
    ranking = rank_ownership_candidates(tenant_id="acme_payments")
    assert ranking is not None
    assert ranking["canonical_email"] in ("aarav@acme-synthetic.internal", "aarav@acme.com")
    # Aarav established 1 active decision -> 1 * 3 = 3 points
    assert ranking["score"] == 3
    assert ranking["counts"]["active_decisions"] == 1
    assert "scored 3 points" in ranking["breakdown"]

    # When Aarav is current owner, Priya or Rohan (both score 2) is ranked
    ranking_next = rank_ownership_candidates(
        tenant_id="acme_payments",
        current_owner_email=ranking["canonical_email"],
    )
    assert ranking_next is not None
    assert ranking_next["canonical_email"] in ("priya@acme-synthetic.internal", "rohan@acme-synthetic.internal", "priya@acme.com")
    assert ranking_next["score"] == 2  # 1 owned system * 2 = 2


def test_blast_radius_and_calculated_risk():
    """Verify topological dependencies and risk classification."""
    blast = calculate_system_blast_radius(
        tenant_id="acme_payments",
        system_name="payment-gateway",
    )
    assert blast["system_name"] == "payment-gateway"
    assert blast["downstream_systems"] in (0, 1)
    assert blast["affected_docs"] >= 1
    assert blast["risk"] in ("LOW", "MODERATE", "MEDIUM")


def test_proposal_safety_validation():
    """Verify programmatic rejection of inactive decisions or invalid evidence IDs."""
    valid_proposal = {
        "summary": "Valid proposal",
        "rationale": "Valid rationale",
        "calculated_metrics": {
            "divergence_hops": 1,
            "drift_staleness_days": 62,
            "blast_radius_risk": "LOW",
            "affected_downstream_count": 0,
        },
        "proposed_action": {
            "action_type": "MARK_DOCUMENT_ALIGNED",
            "target_entity_id": "doc_auth_rfc",
            "target_field": "status",
            "old_value": "stale",
            "new_value": "dec_ed25519_local",
            "supporting_evidence_ids": ["evi_018f_latency_auth"],
        },
    }
    evidence_bag = {
        "evi_018f_latency_auth": {
            "id": "evi_018f_latency_auth",
            "record_id": "dec_ed25519_local",
        }
    }

    # 1. Happy path: valid active decision and valid evidence ID
    is_safe, err = validate_proposal_safety("acme_payments", valid_proposal, evidence_bag)
    assert is_safe is True
    assert err is None

    # 2. Reject if evidence ID missing from evidence_bag
    tampered_evidence = dict(valid_proposal)
    tampered_evidence["proposed_action"] = {
        **valid_proposal["proposed_action"],
        "supporting_evidence_ids": ["evi_unknown_fabricated"],
    }
    is_safe, err = validate_proposal_safety("acme_payments", tampered_evidence, evidence_bag)
    assert is_safe is False
    assert "missing from evidence_bag" in str(err)

    # 3. Reject if new_value does not exist with status == 'active' (superseded decision)
    tampered_decision = dict(valid_proposal)
    tampered_decision["proposed_action"] = {
        **valid_proposal["proposed_action"],
        "new_value": "dec_oauth_introspect",  # status is 'superseded'
    }
    is_safe, err = validate_proposal_safety("acme_payments", tampered_decision, evidence_bag)
    assert is_safe is False
    assert "active" in str(err)


def test_live_graph_topology_query():
    """Verify get_live_graph_topology returns live nodes, links, and timeline from FalkorDB."""
    from app.mcp_server.tools import get_live_graph_topology

    topology = get_live_graph_topology("acme_payments")
    assert topology["tenant_id"] == "acme_payments"
    assert len(topology["nodes"]) >= 9
    assert len(topology["links"]) >= 10
    assert len(topology["timeline"]) >= 3

    node_ids = {n["id"] for n in topology["nodes"]}
    assert "sys_payment_gw" in node_ids
    assert "dec_ed25519_local" in node_ids
    assert "doc_auth_rfc" in node_ids

    # Verify timeline chronology
    tl = topology["timeline"]
    assert tl[0]["type"] == "rfc" or tl[0]["status"] == "stale"
    assert any(item["type"] == "active" for item in tl)


def test_live_graph_topology_http_endpoint():
    """Verify GET /api/graph/{tenant_id} returns HTTP 200 with live FalkorDB topology."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/graph/acme_payments")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "links" in data
    assert "timeline" in data
    assert len(data["nodes"]) >= 9

