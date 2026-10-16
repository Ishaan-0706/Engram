from __future__ import annotations

import json
from unittest.mock import MagicMock
import pytest
import fakeredis
from fastapi.testclient import TestClient

from app.agent.evidence import (
    TwoPhaseEvidenceValidator,
    UnverifiableClaimException,
    parse_mcp_tool_response,
    records_from_mcp_response,
    run_two_phase_validation,
    validate_claims,
)
from app.agent.state import (
    ALLOWED_TRANSITIONS,
    LOCK_PREFIX,
    TURN_PREFIX,
    TURN_TTL_SECONDS,
    IllegalTransitionException,
    ProposalConflictException,
    SnapshotMismatchException,
    StaleEpochException,
    TurnGoneException,
    app,
    cas_transition,
    compute_snapshot_hash,
    confirm_proposal,
    create_initial_turn,
    get_turn,
    lock_key,
    resume_turn,
    save_turn,
    set_redis_client,
    turn_key,
)
from app.contracts import validate

EV_1 = "ev_018f5e1b-7d4a-7c3e-8a12-4b6d9e0f1111"
EV_2 = "ev_018f5e1b-7d4a-7c3e-8a12-4b6d9e0f2222"
UNKNOWN_EV = "ev_018f5e1b-7d4a-7c3e-8a12-4b6d9e0f9999"
PROPOSAL_ID = "018f5e1b-7d4a-7c3e-8a12-4b6d9e0f3333"
IDEMPOTENCY_KEY = "018f5e1b-7d4a-7c3e-8a12-4b6d9e0f4444"


@pytest.fixture
def fake_r():
    client = fakeredis.FakeRedis()
    set_redis_client(client)
    yield client
    set_redis_client(None)


def test_turn_storage_and_ttl(fake_r):
    turn = create_initial_turn(
        tenant_id="tenant-alpha",
        user_id="user-1",
        session_id="session-100",
        status="PLANNING",
        epoch=0,
    )
    key = save_turn(fake_r, turn, "tenant-alpha", "session-100", ttl=TURN_TTL_SECONDS)
    assert key == "turn:tenant-alpha:session-100"
    assert fake_r.ttl(key) == 7200

    loaded = get_turn(fake_r, "tenant-alpha", "session-100")
    assert loaded is not None
    assert loaded["tenant_id"] == "tenant-alpha"
    assert loaded["epoch"] == 0
    validate("agent-turn-state", loaded)


def test_lua_cas_rejection_on_stale_epoch(fake_r):
    """
    Test Lua CAS:
    - Enforce monotonic epoch fencing on all transitions:
      PLANNING -> EXECUTING_TOOLS -> AWAITING_CONFIRMATION -> COMPLETED | FAILED
    - Atomic Redis Lua CAS script: CAS(expected_epoch) -> epoch + 1
    - Reject stale epochs with StaleEpochException (HTTP 410)
    """
    turn = create_initial_turn(
        tenant_id="tenant-alpha",
        user_id="user-1",
        session_id="session-100",
        status="PLANNING",
        epoch=0,
    )
    save_turn(fake_r, turn, "tenant-alpha", "session-100")

    # 1. Successful CAS transition: 0 -> 1, PLANNING -> EXECUTING_TOOLS
    updated = cas_transition(
        fake_r,
        "tenant-alpha",
        expected_epoch=0,
        new_status="EXECUTING_TOOLS",
        session_id="session-100",
    )
    assert updated["epoch"] == 1
    assert updated["status"] == "EXECUTING_TOOLS"

    # 2. Reject stale epoch 0 with StaleEpochException (HTTP 410)
    with pytest.raises(StaleEpochException) as exc_info:
        cas_transition(
            fake_r,
            "tenant-alpha",
            expected_epoch=0,
            new_status="AWAITING_CONFIRMATION",
            session_id="session-100",
        )
    assert exc_info.value.status_code == 410
    assert exc_info.value.current_epoch == 1

    # Epoch should not have incremented
    cur = get_turn(fake_r, "tenant-alpha", "session-100")
    assert cur["epoch"] == 1
    assert cur["status"] == "EXECUTING_TOOLS"

    # 3. Successful transition: 1 -> 2, EXECUTING_TOOLS -> AWAITING_CONFIRMATION
    updated2 = cas_transition(
        fake_r,
        "tenant-alpha",
        expected_epoch=1,
        new_status="AWAITING_CONFIRMATION",
        session_id="session-100",
    )
    assert updated2["epoch"] == 2
    assert updated2["status"] == "AWAITING_CONFIRMATION"

    # 4. Reject stale epoch 1 with StaleEpochException (HTTP 410)
    with pytest.raises(StaleEpochException) as exc_info2:
        cas_transition(
            fake_r,
            "tenant-alpha",
            expected_epoch=1,
            new_status="COMPLETED",
            session_id="session-100",
        )
    assert exc_info2.value.status_code == 410
    assert exc_info2.value.current_epoch == 2

    # 5. Successful transition: 2 -> 3, AWAITING_CONFIRMATION -> COMPLETED
    updated3 = cas_transition(
        fake_r,
        "tenant-alpha",
        expected_epoch=2,
        new_status="COMPLETED",
        session_id="session-100",
    )
    assert updated3["epoch"] == 3
    assert updated3["status"] == "COMPLETED"

    # 6. Reject invalid transition out of terminal state COMPLETED
    with pytest.raises(IllegalTransitionException):
        cas_transition(
            fake_r,
            "tenant-alpha",
            expected_epoch=3,
            new_status="PLANNING",
            session_id="session-100",
        )


def test_410_on_expired_or_missing_turn(fake_r):
    """Test 410 when turn is expired or non-existent in Lua CAS and resume endpoint."""
    # 1. CAS transition on missing/expired turn key
    with pytest.raises(StaleEpochException) as exc_info:
        cas_transition(
            fake_r,
            "tenant-alpha",
            expected_epoch=0,
            new_status="EXECUTING_TOOLS",
            session_id="non-existent",
        )
    assert exc_info.value.status_code == 410
    assert exc_info.value.error == "turn_gone"

    # 2. Python resume_turn function on missing/expired turn
    with pytest.raises(StaleEpochException) as exc_info2:
        resume_turn(
            fake_r,
            tenant_id="tenant-alpha",
            session_id="expired-session",
            last_known_epoch=0,
        )
    assert exc_info2.value.status_code == 410
    assert exc_info2.value.error == "turn_gone"

    # 3. HTTP POST /resume endpoint on missing/expired turn
    client = TestClient(app)
    resp = client.post(
        "/resume",
        json={
            "tenant_id": "tenant-alpha",
            "session_id": "expired-session",
            "last_known_epoch": 0,
        },
    )
    assert resp.status_code == 410
    assert resp.json()["detail"]["error"] == "turn_gone"

    # 4. HTTP POST /resume with stale epoch on existing turn
    turn = create_initial_turn(
        tenant_id="tenant-alpha",
        user_id="user-1",
        session_id="active-session",
        epoch=3,
    )
    save_turn(fake_r, turn, "tenant-alpha", "active-session")

    resp_stale = client.post(
        "/resume",
        json={
            "tenant_id": "tenant-alpha",
            "session_id": "active-session",
            "last_known_epoch": 1,  # Stale: actual is 3
        },
    )
    assert resp_stale.status_code == 410
    assert resp_stale.json()["detail"]["error"] == "stale_epoch"
    assert resp_stale.json()["detail"]["current_epoch"] == 3

    # 5. HTTP POST /resume with matching epoch succeeds
    resp_ok = client.post(
        "/resume",
        json={
            "tenant_id": "tenant-alpha",
            "session_id": "active-session",
            "last_known_epoch": 3,
        },
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["epoch"] == 3
    assert resp_ok.json().get("session_id") == "active-session" or resp_ok.json().get("turn_id")


def test_unverifiable_claim_recovery():
    """
    Test TwoPhaseEvidenceValidator:
    - Attempt 1 fails (unknown evidence ID or record ID): UnverifiableClaimException caught.
    - Streaming to client suppressed.
    - Exactly one constrained re-synthesis prompt restricting allowed IDs strictly to evidence_bag.keys().
    - Attempt 2 succeeds: returns COMPLETED, streaming called.
    """
    evidence_bag = {
        EV_1: {
            "id": EV_1,
            "record_id": "rec_ticket_1",
            "excerpt": "Database migration started at 10:00 UTC.",
            "source_uri": "https://company.internal/tickets/1",
            "source_timestamp": "2026-10-15T10:00:00Z",
            "content_hash": "sha256:" + ("1" * 64),
        },
        EV_2: {
            "id": EV_2,
            "record_id": "rec_ticket_2",
            "excerpt": "Migration completed successfully.",
            "source_uri": "https://company.internal/tickets/2",
            "source_timestamp": "2026-10-15T11:00:00Z",
            "content_hash": "sha256:" + ("2" * 64),
        },
    }
    record_ids = {"rec_ticket_1", "rec_ticket_2"}

    # Case A: Citing a record ID or unknown ID raises UnverifiableClaimException
    with pytest.raises(UnverifiableClaimException):
        validate_claims(
            {"claims": [{"text": "Claim citing record ID.", "cited_evidence_ids": ["rec_ticket_1"]}]},
            set(evidence_bag.keys()),
            record_ids,
        )

    with pytest.raises(UnverifiableClaimException):
        validate_claims(
            {"claims": [{"text": "Claim with unknown ID.", "cited_evidence_ids": [UNKNOWN_EV]}]},
            set(evidence_bag.keys()),
            record_ids,
        )

    with pytest.raises(UnverifiableClaimException):
        validate_claims(
            {"claims": [{"text": "Claim with empty IDs.", "cited_evidence_ids": []}]},
            set(evidence_bag.keys()),
            record_ids,
        )

    # Case B: Two-Phase recovery flow
    attempt_counter = 0
    prompts_received = []

    def mock_llm_synthesize(prompt: str, allowed_ids: list[str]) -> dict:
        nonlocal attempt_counter
        attempt_counter += 1
        prompts_received.append(prompt)
        if attempt_counter == 1:
            # Attempt 1: Returns hallucinated / unknown evidence ID
            return {
                "claims": [
                    {
                        "text": "Migration was delayed due to lock contention.",
                        "cited_evidence_ids": [UNKNOWN_EV],
                    }
                ]
            }
        else:
            # Attempt 2: Constrained retry, correctly cites valid evidence ID
            return {
                "claims": [
                    {
                        "text": "Migration completed successfully.",
                        "cited_evidence_ids": [EV_2],
                    }
                ]
            }

    streamed_chunks = []

    def mock_stream(chunk: dict):
        streamed_chunks.append(chunk)

    result = run_two_phase_validation(
        evidence_bag=evidence_bag,
        prompt="Synthesize status of the database migration.",
        synthesize_fn=mock_llm_synthesize,
        record_ids=record_ids,
        stream_fn=mock_stream,
    )

    assert result.status == "COMPLETED"
    assert result.attempts == 2
    assert result.error is None
    assert result.answer is not None
    assert result.answer["claims"][0]["cited_evidence_ids"] == [EV_2]
    # Streaming was suppressed on attempt 1 and emitted on successful attempt 2
    assert len(streamed_chunks) == 1
    assert streamed_chunks[0] == result.answer
    # Exactly one constrained re-synthesis prompt was executed
    assert len(prompts_received) == 2
    assert "CRITICAL CONSTRAINT" in prompts_received[1]
    assert EV_1 in prompts_received[1]
    assert EV_2 in prompts_received[1]
    # Check synthesis traces
    assert len(result.synthesis_traces) == 2
    assert result.synthesis_traces[0]["attempt"] == 1
    assert result.synthesis_traces[0]["ok"] is False
    assert result.synthesis_traces[1]["attempt"] == 2
    assert result.synthesis_traces[1]["ok"] is True


def test_unverifiable_claim_permanent_failure():
    """If attempt 2 also fails: set status to FAILED with error unverifiable_claim (no answer body)."""
    evidence_bag = {
        EV_1: {
            "id": EV_1,
            "record_id": "rec_1",
            "excerpt": "Excerpt",
            "source_uri": "https://example.test",
            "source_timestamp": "2026-10-15T10:00:00Z",
            "content_hash": "sha256:" + ("1" * 64),
        }
    }

    # Both attempts fail
    def mock_failing_synthesize(prompt: str, allowed_ids: list[str]) -> dict:
        return {
            "claims": [
                {
                    "text": "Persistent hallucination.",
                    "cited_evidence_ids": [UNKNOWN_EV],
                }
            ]
        }

    streamed = []
    result = run_two_phase_validation(
        evidence_bag=evidence_bag,
        prompt="Tell me about project X",
        synthesize_fn=mock_failing_synthesize,
        stream_fn=lambda c: streamed.append(c),
    )

    assert result.status == "FAILED"
    assert result.error == "unverifiable_claim"
    assert result.answer is None  # No answer body
    assert len(streamed) == 0  # No streaming to client
    assert len(result.synthesis_traces) == 2
    assert result.synthesis_traces[0]["ok"] is False
    assert result.synthesis_traces[1]["ok"] is False


def test_409_conflict_on_snapshot_hash_mismatch(fake_r):
    """
    Test proposal confirmation lock lock:{proposal_id} (30s TTL) with snapshot hash re-verification:
    - Return HTTP 409 Conflict with current_snapshot_hash on mismatch.
    - Proposal stays in AWAITING_CONFIRMATION.
    - Lock is released.
    - Retrying with matching current_snapshot_hash succeeds.
    """
    initial_updated_ats = {"ticket_482": "2026-10-15T12:00:00Z"}
    expected_snapshot_hash = compute_snapshot_hash(initial_updated_ats)

    turn = create_initial_turn(
        tenant_id="acme",
        user_id="user-1",
        session_id="session-42",
        status="AWAITING_CONFIRMATION",
        epoch=2,
        pending_proposal={
            "proposal_id": PROPOSAL_ID,
            "snapshot_hash": expected_snapshot_hash,
            "action": {"type": "assign_ticket", "ticket_id": "ticket_482"},
        },
    )
    save_turn(fake_r, turn, "acme", "session-42")

    # Live entity has been modified in FalkorDB!
    live_updated_ats = {"ticket_482": "2026-10-15T14:30:00Z"}
    new_snapshot_hash = compute_snapshot_hash(live_updated_ats)
    assert new_snapshot_hash != expected_snapshot_hash

    # Attempt to confirm proposal with old snapshot hash
    with pytest.raises(SnapshotMismatchException) as exc_info:
        confirm_proposal(
            redis_client=fake_r,
            tenant_id="acme",
            session_id="session-42",
            proposal_id=PROPOSAL_ID,
            expected_epoch=2,
            provided_snapshot_hash=expected_snapshot_hash,
            live_updated_ats=live_updated_ats,
            idempotency_k=IDEMPOTENCY_KEY,
        )

    # 1. Returned HTTP 409 Conflict with current_snapshot_hash
    assert exc_info.value.status_code == 409
    assert exc_info.value.current_snapshot_hash == new_snapshot_hash
    assert exc_info.value.epoch == 2

    # 2. Lock was released so future requests can proceed
    lk = lock_key(PROPOSAL_ID)
    assert fake_r.get(lk) is None

    # 3. Turn status remains AWAITING_CONFIRMATION, epoch remains 2
    current_turn = get_turn(fake_r, "acme", "session-42")
    assert current_turn["status"] == "AWAITING_CONFIRMATION"
    assert current_turn["epoch"] == 2

    # 4. Retry with the current_snapshot_hash succeeds!
    action_mock = MagicMock(return_value={"ticket_id": "ticket_482", "assigned": True})
    receipt = confirm_proposal(
        redis_client=fake_r,
        tenant_id="acme",
        session_id="session-42",
        proposal_id=PROPOSAL_ID,
        expected_epoch=2,
        provided_snapshot_hash=new_snapshot_hash,
        live_updated_ats=live_updated_ats,
        idempotency_k=IDEMPOTENCY_KEY,
        action_executor=action_mock,
    )

    assert receipt["status"] == "completed"
    assert receipt["executed"] is True
    assert receipt["result"] == {"ticket_id": "ticket_482", "assigned": True}
    assert receipt["epoch"] == 3

    # Turn status transitioned to COMPLETED, epoch incremented
    final_turn = get_turn(fake_r, "acme", "session-42")
    assert final_turn["status"] == "COMPLETED"
    assert final_turn["epoch"] == 3

    # Action executor was called
    action_mock.assert_called_once()

    # Lock is released after completion
    assert fake_r.get(lk) is None


def test_lock_contention_rejects_with_409_conflict(fake_r):
    """If proposal confirmation lock is already held, reject with 409 conflict_in_progress."""
    turn = create_initial_turn(
        tenant_id="acme",
        user_id="user-1",
        session_id="session-1",
        status="AWAITING_CONFIRMATION",
        epoch=0,
    )
    save_turn(fake_r, turn, "acme", "session-1")

    # Manually hold the lock
    lk = lock_key(PROPOSAL_ID)
    fake_r.set(lk, "locked", ex=30)

    with pytest.raises(ProposalConflictException) as exc_info:
        confirm_proposal(
            redis_client=fake_r,
            tenant_id="acme",
            session_id="session-1",
            proposal_id=PROPOSAL_ID,
            expected_epoch=0,
            provided_snapshot_hash="sha256:" + ("0" * 64),
            live_updated_ats={},
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.error == "conflict_in_progress"
