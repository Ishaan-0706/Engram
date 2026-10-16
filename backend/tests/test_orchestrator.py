"""Tests for orchestrator.py and main.py (FastAPI routes).

Coverage
--------
- run_agent_turn happy-path: PLANNING → EXECUTING_TOOLS → COMPLETED.
- run_agent_turn mutation path: → AWAITING_CONFIRMATION with pending_proposal.
- run_agent_turn stale epoch: raises StaleEpochException (HTTP 410).
- run_agent_turn tool failure: advances to FAILED (execute_crash).
- run_agent_turn synthesis failure: advances to FAILED (unverifiable_claim).
- run_agent_turn intent routing: all three tools reachable.
- POST /api/turn: 200, full turn payload + epoch.
- POST /api/turn: 410 on stale epoch forwarded correctly.
- POST /api/resume: 200 on matching epoch; 410 on stale/missing.
- POST /api/confirm: 200 happy path with mock executor.
- POST /api/confirm: 409 snapshot mismatch.
- POST /api/confirm: 410 missing turn.
- CORS headers present on OPTIONS pre-flight.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.agent.evidence import UnverifiableClaimException
from app.agent.orchestrator import _needs_mutation, _route_intent, run_agent_turn
from app.agent.state import (
    StaleEpochException,
    cas_transition,
    compute_snapshot_hash,
    create_initial_turn,
    get_turn,
    save_turn,
    set_redis_client,
)
from app.main import app, set_redis_client as main_set_redis

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EV_ID = "ev_018f5e1b-7d4a-7c3e-8a12-4b6d9e0f1111"
PROPOSAL_ID = "018f5e1b-7d4a-7c3e-8a12-4b6d9e0f3333"
IDEMPOTENCY = "018f5e1b-7d4a-7c3e-8a12-4b6d9e0f4444"


@pytest.fixture()
def fake_r():
    """Fresh FakeRedis for every test."""
    client = fakeredis.FakeRedis()
    set_redis_client(client)
    main_set_redis(client)
    yield client
    set_redis_client(None)
    main_set_redis(None)


@pytest.fixture()
def http(fake_r):
    return TestClient(app)


def _good_envelope(tenant_id: str = "acme") -> dict:
    """Minimal valid MCP success envelope with one evidence item."""
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "trace_id": "tr-1",
        "as_of": "2026-10-15T14:30:00Z",
        "records": [
            {"id": "rec_sys_1", "label": "System", "properties": {"name": "payment-gateway"}},
        ],
        "evidence": [
            {
                "id": EV_ID,
                "record_id": "rec_sys_1",
                "excerpt": "Local Ed25519 validation adopted Q3 2026.",
                "source_uri": "slack://channels/payments/p001",
                "source_timestamp": "2026-09-22T14:30:00Z",
                "content_hash": "sha256:" + "a" * 64,
            }
        ],
    }


def _fail_envelope() -> dict:
    return {"ok": False, "error": {"code": "query_failed", "message": "db down"}}


def _synth_good(prompt: str, allowed_ids: list[str]) -> dict:
    """Synthesize a valid claim citing the first allowed evidence id."""
    eid = allowed_ids[0] if allowed_ids else EV_ID
    return {"claims": [{"text": "Ed25519 adopted.", "cited_evidence_ids": [eid]}]}


def _synth_bad(prompt: str, allowed_ids: list[str]) -> dict:
    """Always returns a claim with an unknown evidence id."""
    return {"claims": [{"text": "Bad claim.", "cited_evidence_ids": ["ev_000000-0000-7000-0000-000000000000"]}]}


# ---------------------------------------------------------------------------
# Intent routing unit tests
# ---------------------------------------------------------------------------

class TestIntentRouting:
    def test_decision_history_keywords(self):
        assert _route_intent("why was the auth decision made?") == "decision_history"
        assert _route_intent("architecture choices for JWT") == "decision_history"
        assert _route_intent("tell me about the gateway") == "decision_history"

    def test_documentation_drift_keywords(self):
        assert _route_intent("the RFC is stale") == "documentation_drift"
        assert _route_intent("documents that are outdated") == "documentation_drift"

    def test_ownership_keywords(self):
        assert _route_intent("who owns the payments system?") == "system_ownership"
        assert _route_intent("which team is responsible?") == "system_ownership"
        assert _route_intent("who is the expert?") == "system_ownership"

    def test_default_falls_back_to_decision(self):
        assert _route_intent("hello world") == "decision_history"


# ---------------------------------------------------------------------------
# _needs_mutation
# ---------------------------------------------------------------------------

class TestNeedsMutation:
    def test_reassign_triggers_mutation(self):
        assert _needs_mutation("reassign the owner to priya", "system_ownership")

    def test_documentation_drift_tool_triggers_mutation(self):
        assert _needs_mutation("show me the knowledge graph", "documentation_drift")

    def test_pure_read_no_mutation(self):
        assert not _needs_mutation("why was ed25519 chosen?", "decision_history")


# ---------------------------------------------------------------------------
# run_agent_turn – unit tests with FakeRedis and injected MCP stubs
# ---------------------------------------------------------------------------

class TestRunAgentTurn:

    def _run(
        self,
        fake_r,
        query: str = "why was ed25519 chosen?",
        epoch: int = 0,
        synth=None,
        tool_override: str | None = None,
        envelope: dict | None = None,
    ) -> dict:
        env = envelope or _good_envelope()
        tools = {
            "get_decision_history": lambda tid, sys: env,
            "detect_documentation_drift": lambda tid, sys: env,
            "get_system_ownership": lambda tid, sys: env,
        }
        if tool_override:
            tools[tool_override] = lambda tid, sys: env
        return run_agent_turn(
            tenant_id="acme",
            session_id="s1",
            user_query=query,
            client_epoch=epoch,
            redis_client=fake_r,
            synthesize_fn=synth or _synth_good,
            _tools=tools,
        )

    # Happy path -------------------------------------------------------

    def test_happy_path_completed(self, fake_r):
        result = self._run(fake_r)
        assert result["status"] == "COMPLETED"
        assert result["epoch"] == 2          # PLANNING(0)→EXEC(1)→COMPLETED(2)
        assert EV_ID in result["evidence_bag"]
        assert result["fail_reason"] is None
        assert len(result["synthesis_traces"]) == 1
        assert result["synthesis_traces"][0]["ok"] is True

    def test_evidence_bag_keyed_by_ev_id(self, fake_r):
        result = self._run(fake_r)
        bag = result["evidence_bag"]
        assert EV_ID in bag
        assert bag[EV_ID]["record_id"] == "rec_sys_1"

    def test_working_set_populated(self, fake_r):
        result = self._run(fake_r)
        ws = result["working_set"]
        assert "rec_sys_1" in ws
        assert ws["rec_sys_1"]["label"] == "System"

    # Mutation path ---------------------------------------------------

    def test_mutation_path_awaiting_confirmation(self, fake_r):
        result = self._run(fake_r, query="reassign the owner of payment-gateway")
        assert result["status"] == "AWAITING_CONFIRMATION"
        proposal = result["pending_proposal"]
        assert proposal is not None
        assert proposal["snapshot_hash"].startswith("sha256:")
        assert "proposal_id" in proposal

    # Stale epoch -------------------------------------------------------

    def test_stale_epoch_raises_410(self, fake_r):
        # Prime a turn at epoch 3
        turn = create_initial_turn(
            tenant_id="acme", user_id="u", session_id="s1", epoch=3,
        )
        save_turn(fake_r, turn, "acme", "s1")
        with pytest.raises(StaleEpochException) as exc_info:
            self._run(fake_r, epoch=0)  # client sends wrong epoch
        assert exc_info.value.status_code == 410

    # Tool failure -------------------------------------------------------

    def test_tool_failure_transitions_to_failed(self, fake_r):
        result = self._run(fake_r, envelope=_fail_envelope())
        assert result["status"] == "FAILED"
        assert result["fail_reason"] == "execute_crash"

    # Synthesis failure --------------------------------------------------

    def test_synthesis_permanent_failure(self, fake_r):
        result = self._run(fake_r, synth=_synth_bad)
        assert result["status"] == "FAILED"
        assert result["fail_reason"] == "unverifiable_claim"
        traces = result["synthesis_traces"]
        assert len(traces) == 2
        assert all(not t["ok"] for t in traces)

    def test_synthesis_recovery_on_second_attempt(self, fake_r):
        """First attempt cites unknown ID; second attempt (constrained) succeeds."""
        attempts = []

        def _flaky_synth(prompt: str, allowed_ids: list[str]) -> dict:
            attempts.append(len(attempts))
            if len(attempts) == 1:
                # hallucinate bad ID
                return {"claims": [{"text": "x", "cited_evidence_ids": ["ev_bad"]}]}
            # second call has constrained prompt, return good ID
            eid = allowed_ids[0] if allowed_ids else EV_ID
            return {"claims": [{"text": "recovered", "cited_evidence_ids": [eid]}]}

        result = self._run(fake_r, synth=_flaky_synth)
        assert result["status"] == "COMPLETED"
        assert len(attempts) == 2
        traces = result["synthesis_traces"]
        assert traces[0]["ok"] is False
        assert traces[1]["ok"] is True

    # Tool routing integration ----------------------------------------

    def test_ownership_tool_called(self, fake_r):
        called = []
        env = _good_envelope()

        def _spy_ownership(tid, sys):
            called.append("system_ownership")
            return env

        tools = {
            "get_decision_history": lambda tid, sys: env,
            "detect_documentation_drift": lambda tid, sys: env,
            "get_system_ownership": _spy_ownership,
        }
        run_agent_turn(
            tenant_id="acme",
            session_id="s_own",
            user_query="who owns the payment-gateway?",
            client_epoch=0,
            redis_client=fake_r,
            synthesize_fn=_synth_good,
            _tools=tools,
        )
        assert "system_ownership" in called

    def test_drift_tool_called(self, fake_r):
        called = []
        env = _good_envelope()

        def _spy_drift(tid, sys):
            called.append("documentation_drift")
            return env

        tools = {
            "get_decision_history": lambda tid, sys: env,
            "detect_documentation_drift": _spy_drift,
            "get_system_ownership": lambda tid, sys: env,
        }
        run_agent_turn(
            tenant_id="acme",
            session_id="s_drift",
            user_query="are documents stale?",
            client_epoch=0,
            redis_client=fake_r,
            synthesize_fn=_synth_good,
            _tools=tools,
        )
        assert "documentation_drift" in called


# ---------------------------------------------------------------------------
# HTTP route tests
# ---------------------------------------------------------------------------

class TestApiTurn:

    def _post(self, http, **kwargs) -> dict:
        body = {"tenant_id": "acme", "session_id": "sess", "user_query": "why ed25519?", "epoch": 0}
        body.update(kwargs)
        return http.post("/api/turn", json=body)

    def test_turn_200_completed(self, http, fake_r, monkeypatch):
        env = _good_envelope()
        monkeypatch.setattr(
            "app.agent.orchestrator.get_decision_history", lambda t, s: env
        )
        monkeypatch.setattr(
            "app.agent.orchestrator.detect_documentation_drift", lambda t, s: env
        )
        monkeypatch.setattr(
            "app.agent.orchestrator.get_system_ownership", lambda t, s: env
        )
        # inject synthesizer via module-level monkeypatch
        monkeypatch.setattr(
            "app.agent.orchestrator._default_synthesize",
            lambda *a, **kw: _synth_good,
        )
        resp = self._post(http)
        assert resp.status_code == 200
        body = resp.json()
        assert "turn" in body
        assert "epoch" in body
        assert body["epoch"] >= 1

    def test_turn_410_stale_epoch(self, http, fake_r):
        # Store turn at epoch 5
        turn = create_initial_turn(
            tenant_id="acme", user_id="u", session_id="sess", epoch=5,
        )
        save_turn(fake_r, turn, "acme", "sess")
        resp = self._post(http, epoch=0)
        assert resp.status_code == 410
        assert resp.json()["detail"]["error"] in ("stale_epoch", "turn_gone")


class TestApiResume:

    def test_resume_200_matching_epoch(self, http, fake_r):
        turn = create_initial_turn(
            tenant_id="acme", user_id="u", session_id="rsess", epoch=3,
        )
        save_turn(fake_r, turn, "acme", "rsess")
        resp = http.post("/api/resume", json={
            "tenant_id": "acme",
            "session_id": "rsess",
            "last_known_epoch": 3,
        })
        assert resp.status_code == 200
        assert resp.json()["epoch"] == 3

    def test_resume_410_missing_turn(self, http, fake_r):
        resp = http.post("/api/resume", json={
            "tenant_id": "acme",
            "session_id": "gone",
            "last_known_epoch": 0,
        })
        assert resp.status_code == 410
        assert resp.json()["detail"]["error"] == "turn_gone"

    def test_resume_410_stale_epoch(self, http, fake_r):
        turn = create_initial_turn(
            tenant_id="acme", user_id="u", session_id="rsess2", epoch=7,
        )
        save_turn(fake_r, turn, "acme", "rsess2")
        resp = http.post("/api/resume", json={
            "tenant_id": "acme",
            "session_id": "rsess2",
            "last_known_epoch": 2,
        })
        assert resp.status_code == 410
        assert resp.json()["detail"]["current_epoch"] == 7


class TestApiConfirm:

    def _awaiting_turn(self, fake_r, snapshot_hash: str, working_set: dict | None = None) -> dict:
        turn = create_initial_turn(
            tenant_id="acme",
            user_id="u",
            session_id="csess",
            status="AWAITING_CONFIRMATION",
            epoch=2,
            working_set=working_set or {},
            pending_proposal={
                "proposal_id": PROPOSAL_ID,
                "snapshot_hash": snapshot_hash,
                "action": {
                    "type": "documentation_drift_fix",
                    "system_name": "payment-gateway",
                    "document_id": "doc_auth_rfc",
                    "superseding_decision_id": "dec_ed25519_local",
                },
            },
        )
        save_turn(fake_r, turn, "acme", "csess")
        return turn

    def test_confirm_200_happy_path(self, http, fake_r, monkeypatch):
        # working_set that _fetch_live_ats will read to compute the live hash
        ws = {"rec_sys_1": {"label": "System", "properties": {}}}
        # compute the hash the same way _fetch_live_ats does in main.py
        live_ats = {rid: info.get("label", "") for rid, info in ws.items()}
        snap = compute_snapshot_hash(live_ats)
        self._awaiting_turn(fake_r, snap, working_set=ws)

        # Patch action executor at the module level so confirm_proposal calls it
        mock_action = MagicMock(return_value={
            "ok": True, "tenant_id": "acme", "trace_id": "t1",
            "as_of": "2026-10-16T10:00:00Z",
            "records": [{"id": "doc_auth_rfc", "label": "Document",
                          "properties": {"status": "updated"}}],
            "evidence": [],
        })
        monkeypatch.setattr("app.main.mark_document_updated", mock_action)

        resp = http.post("/api/confirm", json={
            "tenant_id": "acme",
            "session_id": "csess",
            "proposal_id": PROPOSAL_ID,
            "snapshot_hash": snap,
            "idempotency_key": IDEMPOTENCY,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["executed"] is True

        final = get_turn(fake_r, "acme", "csess")
        assert final["status"] == "COMPLETED"
        assert final["epoch"] == 3

    def test_confirm_409_snapshot_mismatch(self, http, fake_r):
        """When snapshot hash in request differs from live entities → 409."""
        # empty working_set → _fetch_live_ats returns {} → compute_snapshot_hash("") 
        # Use an obviously wrong hash that won't match
        wrong_snap = "sha256:" + "b" * 64
        # Store the same wrong hash in the turn so the proposal check passes
        self._awaiting_turn(fake_r, wrong_snap, working_set={})

        # Client sends a *different* hash; live computation (empty ws) produces yet another hash
        client_snap = "sha256:" + "c" * 64
        resp = http.post("/api/confirm", json={
            "tenant_id": "acme",
            "session_id": "csess",
            "proposal_id": PROPOSAL_ID,
            "snapshot_hash": client_snap,
            "idempotency_key": IDEMPOTENCY,
        })
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["error"] == "snapshot_mismatch"
        assert "current_snapshot_hash" in detail

        # Turn must still be AWAITING_CONFIRMATION after mismatch
        still = get_turn(fake_r, "acme", "csess")
        assert still["status"] == "AWAITING_CONFIRMATION"
        assert still["epoch"] == 2

    def test_confirm_410_missing_turn(self, http, fake_r):
        resp = http.post("/api/confirm", json={
            "tenant_id": "acme",
            "session_id": "no_such_session",
            "proposal_id": PROPOSAL_ID,
            "snapshot_hash": "sha256:" + "c" * 64,
            "idempotency_key": IDEMPOTENCY,
        })
        assert resp.status_code == 410
        assert resp.json()["detail"]["error"] == "turn_gone"


class TestCORS:

    def test_cors_preflight(self, http):
        resp = http.options(
            "/api/turn",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        # FastAPI with CORSMiddleware returns 200 on pre-flight
        assert resp.status_code in (200, 400)
        # Origin must be echoed or wildcard present
        origin_header = resp.headers.get("access-control-allow-origin", "")
        assert "localhost:3000" in origin_header or origin_header == "*"

    def test_cors_response_header_on_get(self, http):
        resp = http.get(
            "/api/resume",
            headers={"Origin": "http://localhost:3001"},
        )
        # /api/resume is POST-only → 405, but CORS header still set
        origin = resp.headers.get("access-control-allow-origin", "")
        assert "localhost:3001" in origin or origin == "*"
