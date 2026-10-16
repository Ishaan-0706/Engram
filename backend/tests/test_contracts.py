from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError

from app.agent.confirm import ConfirmView, evaluate_confirm
from app.agent.evidence import (
    UnverifiableClaimException,
    content_hash,
    evidence_ids_from_tool_response,
    synthesis_turn_status,
    validate_claims,
)
from app.agent.turn_state import StaleFence, fence_cas, heartbeat_ttl, TURN_TTL_SECONDS
from app.contracts import validate
from app.security.tenant import graph_key_from_claims

EV_ID = "ev_018f5e1b-7d4a-7c3e-8a12-4b6d9e0f1234"
TURN_ID = "018f5e1b-7d4a-7c3e-8a12-4b6d9e0f1234"
IDEMPOTENCY = "018f5e1c-7d4a-7c3e-8a12-4b6d9e0f1234"
HASH_A = "sha256:" + ("a" * 64)
HASH_B = "sha256:" + ("b" * 64)


def _mcp_ok() -> dict:
    excerpt = "Compatibility tests are failing on the new endpoint."
    uri = "https://example.test/tickets/482"
    return {
        "ok": True,
        "tenant_id": "acme",
        "trace_id": "tr-1",
        "as_of": "2026-10-15T14:30:00Z",
        "records": [
            {
                "id": "ticket_482",
                "label": "Ticket",
                "properties": {"title": "Payments API migration"},
            }
        ],
        "evidence": [
            {
                "id": EV_ID,
                "record_id": "ticket_482",
                "excerpt": excerpt,
                "source_uri": uri,
                "source_timestamp": "2026-10-15T14:30:00Z",
                "content_hash": content_hash(excerpt, uri),
            }
        ],
    }


def _turn(**overrides) -> dict:
    blob = {
        "turn_id": TURN_ID,
        "tenant_id": "acme",
        "user_id": "user-1",
        "status": "AWAITING_CONFIRMATION",
        "epoch": 3,
        "working_set": {},
        "tool_trace": [],
        "evidence_bag": {},
        "pending_proposal": {
            "proposal_id": TURN_ID,
            "snapshot_hash": HASH_A,
            "action": {"type": "assign_ticket"},
        },
        "synthesis_traces": [],
        "fail_reason": None,
    }
    blob.update(overrides)
    return blob


def test_mcp_success_and_failure_envelopes():
    validate("mcp-tool-response", _mcp_ok())
    fixture = json.loads(
        (Path(__file__).resolve().parents[2] / "contracts/fixtures/mcp-ok.json").read_text()
    )
    validate("mcp-tool-response", fixture)
    err = json.loads(
        (Path(__file__).resolve().parents[2] / "contracts/fixtures/mcp-error.json").read_text()
    )
    validate("mcp-tool-response", err)


def test_mcp_failure_must_not_carry_evidence():
    with pytest.raises(ValidationError):
        validate(
            "mcp-tool-response",
            {
                "ok": False,
                "error": {"code": "x", "message": "y"},
                "evidence": [],
            },
        )


def test_mcp_rejects_missing_evidence_id():
    payload = _mcp_ok()
    del payload["evidence"][0]["id"]
    with pytest.raises(ValidationError):
        validate("mcp-tool-response", payload)


def test_jwt_graph_key():
    assert graph_key_from_claims({"sub": "user-1", "tid": "acme"}) == "tenant:acme"
    with pytest.raises(ValidationError):
        graph_key_from_claims({"sub": "user-1", "org_id": "acme"})


def test_turn_blob_and_heartbeat_does_not_change_epoch():
    blob = _turn(status="PLANNING", epoch=0, pending_proposal=None)
    validate("agent-turn-state", blob)
    assert heartbeat_ttl() == TURN_TTL_SECONDS
    bumped = fence_cas(blob, 0, "EXECUTING_TOOLS")
    assert bumped["epoch"] == 1
    with pytest.raises(StaleFence):
        fence_cas(blob, 99, "EXECUTING_TOOLS")


def test_unverifiable_claim_retry_then_fail():
    bag = evidence_ids_from_tool_response(_mcp_ok())
    validate_claims(
        {"claims": [{"text": "Tests are blocking.", "cited_evidence_ids": [EV_ID]}]},
        set(bag),
    )
    with pytest.raises(UnverifiableClaimException):
        validate_claims(
            {
                "claims": [
                    {
                        "text": "Invented.",
                        "cited_evidence_ids": [
                            "ev_018f5e1b-7d4a-7c3e-9a12-4b6d9e0f9999"
                        ],
                    }
                ]
            },
            set(bag),
        )
    assert (
        synthesis_turn_status(
            attempt=1, unverifiable=True, streamed_first=False, retry_used_tools=False
        )
        == "RETRY"
    )
    assert (
        synthesis_turn_status(
            attempt=2, unverifiable=True, streamed_first=False, retry_used_tools=False
        )
        == "FAILED"
    )


def test_confirm_mismatch_keeps_proposal_and_returns_current_hash():
    decision = evaluate_confirm(
        ConfirmView(
            turn=_turn(),
            request_epoch=3,
            provided_hash=HASH_A,
            computed_hash=HASH_B,
            idempotency_key=IDEMPOTENCY,
            stored_idempotency=None,
            lock_acquired=True,
        )
    )
    assert decision.status_code == 409
    assert decision.body["error"] == "snapshot_mismatch"
    assert decision.body["current_snapshot_hash"] == HASH_B
    assert decision.execute is False
    assert decision.release_lock is True
    validate("action-confirm", decision.body)


def test_confirm_duplicate_uuid_returns_receipt():
    receipt = {
        "status": "completed",
        "idempotency_key": IDEMPOTENCY,
        "executed": True,
        "result": {"ok": True},
    }
    decision = evaluate_confirm(
        ConfirmView(
            turn=_turn(),
            request_epoch=3,
            provided_hash=HASH_A,
            computed_hash=HASH_B,
            idempotency_key=IDEMPOTENCY,
            stored_idempotency=receipt,
            lock_acquired=False,
        )
    )
    assert decision.status_code == 200
    assert decision.body == receipt
    validate("action-confirm", receipt)


def test_confirm_missing_turn_is_gone():
    decision = evaluate_confirm(
        ConfirmView(
            turn=None,
            request_epoch=0,
            provided_hash=HASH_A,
            computed_hash=HASH_A,
            idempotency_key=IDEMPOTENCY,
            stored_idempotency=None,
            lock_acquired=True,
        )
    )
    assert decision.status_code == 410
    assert decision.body == {"error": "turn_gone"}
    validate("action-confirm", decision.body)


def test_confirm_loser_without_lock_is_conflict():
    decision = evaluate_confirm(
        ConfirmView(
            turn=_turn(),
            request_epoch=3,
            provided_hash=HASH_A,
            computed_hash=HASH_A,
            idempotency_key=IDEMPOTENCY,
            stored_idempotency=None,
            lock_acquired=False,
        )
    )
    assert decision.status_code == 409
    assert decision.error == "conflict_in_progress"
