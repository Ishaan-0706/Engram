import json
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

from app.engram_graph_core.client import MCP_QUERY_TIMEOUT_MS, tenant_graph_name
from app.mcp_server import action_tools, tools as mcp_tools

ENVELOPE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "shared/contracts/mcp_envelope.schema.json"
)
ENVELOPE_SCHEMA = json.loads(ENVELOPE_SCHEMA_PATH.read_text())


class _Node:
    def __init__(self, label: str, **props):
        self.labels = [label]
        self.properties = props


class _Result:
    def __init__(self, rows):
        self.result_set = rows


class FakeGraph:
    def __init__(self, rows_by_fragment: dict[str, list]):
        self.rows_by_fragment = rows_by_fragment
        self.last_timeout = None

    def query(self, cypher, params=None, timeout=None):
        self.last_timeout = timeout
        for fragment, rows in self.rows_by_fragment.items():
            if fragment in cypher:
                return _Result(rows)
        return _Result([])


def test_tenant_graph_name_matches_live_convention():
    assert tenant_graph_name("acme_payments") == "tenant_acme_payments"
    assert tenant_graph_name("tenant_acme_payments") == "tenant_acme_payments"


def test_decision_history_envelope(monkeypatch):
    graph = FakeGraph(
        {
            "AFFECTS": [
                [
                    _Node("System", id="sys_payment_gw", name="payment-gateway"),
                    _Node("Decision", id="dec_ed25519_local", status="active"),
                    _Node("Decision", id="dec_oauth_introspection", status="superseded"),
                    _Node(
                        "Evidence",
                        id="evi_018f_latency_auth",
                        record_id="dec_ed25519_local",
                        excerpt="switching payment-gateway token validation to local Ed25519",
                        source_uri="slack://channels/inc-payments/p1726000000",
                        source_timestamp="2026-09-22T14:30:00Z",
                        content_hash="a" * 64,
                    ),
                ]
            ]
        }
    )
    monkeypatch.setattr(mcp_tools, "get_tenant_graph", lambda tenant_id: graph)
    payload = mcp_tools.get_decision_history("acme_payments", "payment-gateway")
    assert graph.last_timeout == MCP_QUERY_TIMEOUT_MS
    assert payload["ok"] is True
    labels = {r["label"] for r in payload["records"]}
    assert labels == {"System", "Decision"}
    assert payload["evidence"][0]["id"] == "evi_018f_latency_auth"
    assert payload["evidence"][0]["content_hash"].startswith("sha256:")
    jsonschema.validate(instance=payload, schema=ENVELOPE_SCHEMA)


def test_drift_and_ownership(monkeypatch):
    graph = FakeGraph(
        {
            "PROPOSED": [
                [
                    _Node("System", id="sys_payment_gw", name="payment-gateway"),
                    _Node("Document", id="doc_auth_rfc", title="Payments Auth RFC v1"),
                    _Node("Decision", id="dec_oauth_introspection", status="superseded"),
                    _Node("Decision", id="dec_ed25519_local", status="active"),
                    _Node(
                        "Evidence",
                        id="evi_018f_latency_auth",
                        record_id="dec_ed25519_local",
                        excerpt="switching payment-gateway token validation to local Ed25519",
                        source_uri="slack://channels/inc-payments/p1726000000",
                        source_timestamp="2026-09-22T14:30:00Z",
                        content_hash="b" * 64,
                    ),
                ]
            ],
            "OWNS": [
                [
                    _Node("Person", id="usr_018f_priya", display_name="Priya Nair"),
                    _Node("System", id="sys_payment_gw", name="payment-gateway"),
                    _Node("Team", id="team_core_pay", name="Core Payments"),
                    SimpleNamespace(properties={"valid_from": 1, "valid_to": None}),
                ]
            ],
        }
    )
    monkeypatch.setattr(mcp_tools, "get_tenant_graph", lambda tenant_id: graph)
    drift = mcp_tools.detect_documentation_drift("acme_payments", "payment-gateway")
    assert {r["label"] for r in drift["records"]} >= {"Document", "Decision", "System"}
    assert drift["evidence"]
    jsonschema.validate(instance=drift, schema=ENVELOPE_SCHEMA)

    own = mcp_tools.get_system_ownership("acme_payments", "payment-gateway")
    names = {r["label"]: r["properties"].get("display_name") or r["properties"].get("name") for r in own["records"]}
    assert names["Person"] == "Priya Nair"
    assert names["Team"] == "Core Payments"
    assert own["evidence"] == []
    jsonschema.validate(instance=own, schema=ENVELOPE_SCHEMA)


@pytest.mark.integration
def test_live_tenant_acme_payments():
    pytest.importorskip("falkordb")

    # 1. get_decision_history
    history = mcp_tools.get_decision_history("acme_payments", "payment-gateway")
    if not history.get("ok"):
        pytest.skip(history["error"]["message"])
    assert any(r["label"] == "Decision" for r in history["records"])
    assert any(e["id"] in {"evi_slack_inc", "evi_018f_latency_auth"} for e in history["evidence"])
    jsonschema.validate(instance=history, schema=ENVELOPE_SCHEMA)

    # 2. detect_documentation_drift
    drift = mcp_tools.detect_documentation_drift("acme_payments", "payment-gateway")
    assert drift["ok"]
    assert any(r["id"] == "doc_auth_rfc" for r in drift["records"])
    jsonschema.validate(instance=drift, schema=ENVELOPE_SCHEMA)

    # 3. get_system_ownership
    own = mcp_tools.get_system_ownership("acme_payments", "payment-gateway")
    assert own["ok"]
    assert any(r["id"] in {"person_priya", "person_aarav", "usr_018f_priya", "usr_018f_aarav"} for r in own["records"])
    jsonschema.validate(instance=own, schema=ENVELOPE_SCHEMA)

    # 4. reassign_system_owner
    current_person = next((r for r in own["records"] if r["label"] == "Person"), None)
    current_email = (
        current_person["properties"].get("canonical_email")
        if current_person
        else "priya@acme-synthetic.internal"
    )
    target_email = "aarav@acme-synthetic.internal" if "priya" in current_email else "priya@acme-synthetic.internal"

    reassigned = action_tools.reassign_system_owner(
        "acme_payments", "payment-gateway", target_email
    )
    assert reassigned["ok"] is True
    assert any(
        r["label"] == "Person" and r["properties"].get("canonical_email") == target_email
        for r in reassigned["records"]
    )
    assert any(r["label"] == "System" for r in reassigned["records"])
    assert reassigned["evidence"] == []
    jsonschema.validate(instance=reassigned, schema=ENVELOPE_SCHEMA)

    # Revert ownership back to restore initial state
    restored = action_tools.reassign_system_owner(
        "acme_payments", "payment-gateway", current_email or "priya@acme-synthetic.internal"
    )
    assert restored["ok"] is True
    jsonschema.validate(instance=restored, schema=ENVELOPE_SCHEMA)

