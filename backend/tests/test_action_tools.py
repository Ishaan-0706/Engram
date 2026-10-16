from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.engram_graph_core.client import MCP_QUERY_TIMEOUT_MS
from app.mcp_server import action_tools


# ---------------------------------------------------------------------------
# Fake graph helpers (same pattern as test_mcp_tools.py)
# ---------------------------------------------------------------------------

class _Node:
    def __init__(self, label: str, **props):
        self.labels = [label]
        self.properties = props


class _Result:
    def __init__(self, rows):
        self.result_set = rows


class FakeGraph:
    """Dispatches queries by matching a substring against the Cypher text."""

    def __init__(self, rows_by_fragment: dict[str, list]):
        self.rows_by_fragment = rows_by_fragment
        self.calls: list[dict] = []

    def query(self, cypher, params=None, timeout=None):
        self.calls.append({"cypher": cypher, "params": params, "timeout": timeout})
        for fragment, rows in self.rows_by_fragment.items():
            if fragment in cypher:
                return _Result(rows)
        return _Result([])


# ---------------------------------------------------------------------------
# reassign_system_owner
# ---------------------------------------------------------------------------

class TestReassignSystemOwner:

    def _graph_with_person_and_system(self) -> FakeGraph:
        return FakeGraph(
            {
                # existence checks – match the RETURN p.id / s.id LIMIT fragments
                "RETURN p.id LIMIT": [
                    [_Node("Person", id="usr_018f_priya", display_name="Priya Nair")]
                ],
                "RETURN s.id LIMIT": [
                    [_Node("System", id="sys_payment_gw", name="payment-gateway")]
                ],
                # mutation result: uses RETURN new, s (or RETURN p, s)
                "RETURN new, s": [
                    [
                        _Node(
                            "Person",
                            id="usr_018f_priya",
                            canonical_email="priya@acme.dev",
                            display_name="Priya Nair",
                        ),
                        _Node("System", id="sys_payment_gw", name="payment-gateway"),
                    ]
                ],
                "RETURN p, s": [
                    [
                        _Node(
                            "Person",
                            id="usr_018f_priya",
                            canonical_email="priya@acme.dev",
                            display_name="Priya Nair",
                        ),
                        _Node("System", id="sys_payment_gw", name="payment-gateway"),
                    ]
                ],
            }
        )

    def test_happy_path(self, monkeypatch):
        graph = self._graph_with_person_and_system()
        monkeypatch.setattr(action_tools, "get_tenant_graph", lambda tid: graph)

        result = action_tools.reassign_system_owner(
            "acme_payments", "payment-gateway", "priya@acme.dev"
        )

        assert result["ok"] is True
        labels = {r["label"] for r in result["records"]}
        assert labels == {"Person", "System"}
        assert result["evidence"] == []
        assert result["tenant_id"] == "acme_payments"
        assert "trace_id" in result
        assert "as_of" in result

    def test_timeout_respected(self, monkeypatch):
        graph = self._graph_with_person_and_system()
        monkeypatch.setattr(action_tools, "get_tenant_graph", lambda tid: graph)

        action_tools.reassign_system_owner(
            "acme_payments", "payment-gateway", "priya@acme.dev"
        )

        # Every query call must respect the timeout
        for call in graph.calls:
            assert call["timeout"] == MCP_QUERY_TIMEOUT_MS

    def test_person_not_found(self, monkeypatch):
        graph = FakeGraph(
            {
                # person existence check returns empty (no RETURN p.id LIMIT key)
                "RETURN s.id LIMIT": [
                    [_Node("System", id="sys_payment_gw", name="payment-gateway")]
                ],
            }
        )
        monkeypatch.setattr(action_tools, "get_tenant_graph", lambda tid: graph)

        result = action_tools.reassign_system_owner(
            "acme_payments", "payment-gateway", "nobody@acme.dev"
        )

        assert result["ok"] is False
        assert result["error"]["code"] == "not_found"
        assert "nobody@acme.dev" in result["error"]["message"]

    def test_system_not_found(self, monkeypatch):
        graph = FakeGraph(
            {
                "RETURN p.id LIMIT": [
                    [_Node("Person", id="usr_018f_priya", display_name="Priya Nair")]
                ],
                # system existence check returns empty (no RETURN s.id LIMIT key)
            }
        )
        monkeypatch.setattr(action_tools, "get_tenant_graph", lambda tid: graph)

        result = action_tools.reassign_system_owner(
            "acme_payments", "no-such-system", "priya@acme.dev"
        )

        assert result["ok"] is False
        assert result["error"]["code"] == "not_found"
        assert "no-such-system" in result["error"]["message"]

    def test_mutation_exception(self, monkeypatch):
        """If the mutation query itself raises, we get a mutation_failed envelope."""
        call_count = 0

        class BrokenGraph:
            def query(self, cypher, params=None, timeout=None):
                nonlocal call_count
                call_count += 1
                # First two calls: existence checks succeed
                if call_count <= 2:
                    return _Result([[SimpleNamespace(id="x")]])
                raise RuntimeError("FalkorDB timeout")

        monkeypatch.setattr(action_tools, "get_tenant_graph", lambda tid: BrokenGraph())

        result = action_tools.reassign_system_owner(
            "acme_payments", "payment-gateway", "priya@acme.dev"
        )

        assert result["ok"] is False
        assert result["error"]["code"] == "mutation_failed"

    def test_graph_connection_failure(self, monkeypatch):
        monkeypatch.setattr(
            action_tools,
            "get_tenant_graph",
            lambda tid: (_ for _ in ()).throw(ConnectionError("unreachable")),
        )

        result = action_tools.reassign_system_owner(
            "acme_payments", "payment-gateway", "priya@acme.dev"
        )

        assert result["ok"] is False
        assert result["error"]["code"] == "query_failed"


# ---------------------------------------------------------------------------
# mark_document_updated
# ---------------------------------------------------------------------------

class TestMarkDocumentUpdated:

    def _graph_with_doc_and_decision(self) -> FakeGraph:
        return FakeGraph(
            {
                # existence checks
                "RETURN d.id LIMIT": [
                    [_Node("Document", id="doc_auth_rfc", title="Auth RFC v1")]
                ],
                "RETURN dec.id LIMIT": [
                    [_Node("Decision", id="dec_ed25519_local", status="active")]
                ],
                # mutation result
                "RETURN doc": [
                    [
                        _Node(
                            "Document",
                            id="doc_auth_rfc",
                            title="Auth RFC v1",
                            status="updated",
                        ),
                    ]
                ],
            }
        )

    def test_happy_path(self, monkeypatch):
        graph = self._graph_with_doc_and_decision()
        monkeypatch.setattr(action_tools, "get_tenant_graph", lambda tid: graph)

        result = action_tools.mark_document_updated(
            "acme_payments", "doc_auth_rfc", "dec_ed25519_local"
        )

        assert result["ok"] is True
        assert len(result["records"]) == 1
        assert result["records"][0]["label"] == "Document"
        assert result["records"][0]["properties"]["status"] == "updated"
        assert result["evidence"] == []

    def test_timeout_respected(self, monkeypatch):
        graph = self._graph_with_doc_and_decision()
        monkeypatch.setattr(action_tools, "get_tenant_graph", lambda tid: graph)

        action_tools.mark_document_updated(
            "acme_payments", "doc_auth_rfc", "dec_ed25519_local"
        )

        for call in graph.calls:
            assert call["timeout"] == MCP_QUERY_TIMEOUT_MS

    def test_document_not_found(self, monkeypatch):
        graph = FakeGraph(
            {
                "RETURN dec.id LIMIT": [
                    [_Node("Decision", id="dec_ed25519_local", status="active")]
                ],
            }
        )
        monkeypatch.setattr(action_tools, "get_tenant_graph", lambda tid: graph)

        result = action_tools.mark_document_updated(
            "acme_payments", "doc_missing", "dec_ed25519_local"
        )

        assert result["ok"] is False
        assert result["error"]["code"] == "not_found"
        assert "doc_missing" in result["error"]["message"]

    def test_decision_not_found(self, monkeypatch):
        graph = FakeGraph(
            {
                "RETURN d.id LIMIT": [
                    [_Node("Document", id="doc_auth_rfc", title="Auth RFC v1")]
                ],
                # decision existence check returns empty (no second RETURN d.id key)
            }
        )
        monkeypatch.setattr(action_tools, "get_tenant_graph", lambda tid: graph)

        result = action_tools.mark_document_updated(
            "acme_payments", "doc_auth_rfc", "dec_missing"
        )

        assert result["ok"] is False
        assert result["error"]["code"] == "not_found"
        assert "dec_missing" in result["error"]["message"]

    def test_mutation_exception(self, monkeypatch):
        call_count = 0

        class BrokenGraph:
            def query(self, cypher, params=None, timeout=None):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    return _Result([[SimpleNamespace(id="x")]])
                raise RuntimeError("FalkorDB timeout")

        monkeypatch.setattr(action_tools, "get_tenant_graph", lambda tid: BrokenGraph())

        result = action_tools.mark_document_updated(
            "acme_payments", "doc_auth_rfc", "dec_ed25519_local"
        )

        assert result["ok"] is False
        assert result["error"]["code"] == "mutation_failed"

    def test_graph_connection_failure(self, monkeypatch):
        monkeypatch.setattr(
            action_tools,
            "get_tenant_graph",
            lambda tid: (_ for _ in ()).throw(ConnectionError("unreachable")),
        )

        result = action_tools.mark_document_updated(
            "acme_payments", "doc_auth_rfc", "dec_ed25519_local"
        )

        assert result["ok"] is False
        assert result["error"]["code"] == "query_failed"
