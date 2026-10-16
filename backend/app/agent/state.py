from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Callable

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

try:
    import uuid_utils

    def generate_uuidv7() -> str:
        return str(uuid_utils.uuid7())
except ImportError:
    import time
    import os

    def generate_uuidv7() -> str:
        timestamp_ms = int(time.time() * 1000)
        rand_bytes = os.urandom(10)
        time_high = (timestamp_ms >> 16) & 0xFFFFFFFF
        time_mid = timestamp_ms & 0xFFFF
        ver_and_rand = (0x7000) | ((rand_bytes[0] << 8 | rand_bytes[1]) & 0x0FFF)
        var_and_rand = (0x80) | (rand_bytes[2] & 0x3F)
        rest = rand_bytes[3:10].hex()
        return f"{time_high:08x}-{time_mid:04x}-{ver_and_rand:04x}-{var_and_rand:02x}{rand_bytes[3]:02x}-{rand_bytes[4:10].hex()}"


TURN_TTL_SECONDS = 7200  # 2 hours
LOCK_TTL_SECONDS = 30  # 30 seconds
IDEMPOTENCY_TTL_SECONDS = 7200

TURN_PREFIX = "turn:"
LOCK_PREFIX = "lock:"
IDEMPOTENCY_PREFIX = "idempotency:"

ALLOWED_TRANSITIONS = {
    "PLANNING": {"EXECUTING_TOOLS", "FAILED"},
    "EXECUTING_TOOLS": {"AWAITING_CONFIRMATION", "COMPLETED", "FAILED"},
    "AWAITING_CONFIRMATION": {"COMPLETED", "FAILED"},
    "COMPLETED": set(),
    "FAILED": set(),
}


class StaleEpochException(HTTPException):
    """Raised when epoch is stale or turn has expired/gone (HTTP 410)."""

    def __init__(self, detail: str = "stale_epoch", current_epoch: int | None = None):
        super().__init__(
            status_code=410,
            detail={"error": detail, "current_epoch": current_epoch}
            if current_epoch is not None
            else {"error": detail},
        )
        self.error = detail
        self.current_epoch = current_epoch
        self.status_code = 410


class TurnGoneException(StaleEpochException):
    def __init__(self, detail: str = "turn_gone"):
        super().__init__(detail=detail)


class IllegalTransitionException(HTTPException):
    def __init__(self, current_status: str, new_status: str):
        super().__init__(
            status_code=400,
            detail={
                "error": "illegal_transition",
                "current": current_status,
                "target": new_status,
            },
        )
        self.current_status = current_status
        self.new_status = new_status


class SnapshotMismatchException(HTTPException):
    """Raised when proposal snapshot hash mismatches live entity updated_at values (HTTP 409)."""

    def __init__(self, current_snapshot_hash: str, epoch: int):
        super().__init__(
            status_code=409,
            detail={
                "error": "snapshot_mismatch",
                "current_snapshot_hash": current_snapshot_hash,
                "epoch": epoch,
            },
        )
        self.current_snapshot_hash = current_snapshot_hash
        self.epoch = epoch
        self.status_code = 409


class ProposalConflictException(HTTPException):
    def __init__(self, detail: str = "conflict_in_progress"):
        super().__init__(status_code=409, detail={"error": detail})
        self.error = detail
        self.status_code = 409


def turn_key(tenant_id: str, session_id: str | None = None) -> str:
    """Returns Redis key for turn storage with format turn:{tenant_id}:{session_id}."""
    if session_id is None:
        if tenant_id.startswith(TURN_PREFIX):
            return tenant_id
        return f"{TURN_PREFIX}{tenant_id}"
    return f"{TURN_PREFIX}{tenant_id}:{session_id}"


def lock_key(proposal_id: str) -> str:
    """Returns Redis key for proposal confirmation lock."""
    if proposal_id.startswith(LOCK_PREFIX):
        return proposal_id
    return f"{LOCK_PREFIX}{proposal_id}"


def idempotency_key(key: str) -> str:
    """Returns Redis key for action idempotency."""
    if key.startswith(IDEMPOTENCY_PREFIX):
        return key
    return f"{IDEMPOTENCY_PREFIX}{key}"


CAS_LUA_SCRIPT = """
local key = KEYS[1]
local expected_epoch = tonumber(ARGV[1])
local new_status = ARGV[2]
local updates_raw = ARGV[3]
local ttl = tonumber(ARGV[4]) or 7200

local raw = redis.call('GET', key)
if not raw then
    return cjson.encode({ok = false, error = "turn_gone", status_code = 410})
end

local blob = cjson.decode(raw)
local current_epoch = tonumber(blob["epoch"])

if current_epoch ~= expected_epoch then
    return cjson.encode({ok = false, error = "stale_epoch", current_epoch = current_epoch, status_code = 410})
end

local current_status = blob["status"]
local valid = false

if current_status == "PLANNING" and (new_status == "EXECUTING_TOOLS" or new_status == "FAILED") then
    valid = true
elseif current_status == "EXECUTING_TOOLS" and (new_status == "AWAITING_CONFIRMATION" or new_status == "COMPLETED" or new_status == "FAILED") then
    valid = true
elseif current_status == "AWAITING_CONFIRMATION" and (new_status == "COMPLETED" or new_status == "FAILED") then
    valid = true
end

if not valid then
    return cjson.encode({ok = false, error = "illegal_transition", current_status = current_status, new_status = new_status, status_code = 400})
end

blob["epoch"] = expected_epoch + 1
blob["status"] = new_status

if updates_raw and updates_raw ~= "" and updates_raw ~= "{}" then
    local updates = cjson.decode(updates_raw)
    for k, v in pairs(updates) do
        if k ~= "epoch" and k ~= "status" then
            blob[k] = v
        end
    end
end

local updated_raw = cjson.encode(blob)
redis.call('SET', key, updated_raw, 'EX', ttl)

return cjson.encode({ok = true, data = blob})
"""


def cas_transition(
    redis_client: Any,
    turn_key_or_tenant: str,
    expected_epoch: int,
    new_status: str,
    session_id: str | None = None,
    updates: dict | None = None,
    ttl: int = TURN_TTL_SECONDS,
) -> dict:
    """
    Atomic Redis Lua CAS transition:
    CAS(expected_epoch) -> epoch + 1.
    Rejects stale epochs with StaleEpochException (HTTP 410).
    Rejects illegal transitions with IllegalTransitionException (HTTP 400).
    """
    if session_id is not None:
        key = turn_key(turn_key_or_tenant, session_id)
    else:
        key = turn_key(turn_key_or_tenant)

    updates_json = json.dumps(updates) if updates else "{}"
    res_raw = redis_client.eval(
        CAS_LUA_SCRIPT, 1, key, expected_epoch, new_status, updates_json, ttl
    )
    if isinstance(res_raw, (bytes, bytearray)):
        res_raw = res_raw.decode("utf-8")
    res = json.loads(res_raw)

    if not res.get("ok"):
        err = res.get("error")
        if err == "turn_gone":
            raise StaleEpochException(detail="turn_gone")
        elif err == "stale_epoch":
            raise StaleEpochException(
                detail="stale_epoch", current_epoch=res.get("current_epoch")
            )
        elif err == "illegal_transition":
            raise IllegalTransitionException(
                res.get("current_status"), res.get("new_status")
            )
        else:
            raise RuntimeError(f"Lua CAS failure: {err}")

    return res["data"]


def create_initial_turn(
    tenant_id: str,
    user_id: str,
    session_id: str | None = None,
    turn_id: str | None = None,
    status: str = "PLANNING",
    epoch: int = 0,
    working_set: dict | None = None,
    tool_trace: list | None = None,
    evidence_bag: dict | None = None,
    pending_proposal: dict | None = None,
    synthesis_traces: list | None = None,
    fail_reason: str | None = None,
) -> dict:
    """Creates a validated AgentTurnState dict matching agent-turn-state.schema.json."""
    t_id = turn_id or generate_uuidv7()
    return {
        "turn_id": t_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "status": status,
        "epoch": epoch,
        "working_set": working_set if working_set is not None else {},
        "tool_trace": tool_trace if tool_trace is not None else [],
        "evidence_bag": evidence_bag if evidence_bag is not None else {},
        "pending_proposal": pending_proposal,
        "synthesis_traces": synthesis_traces if synthesis_traces is not None else [],
        "fail_reason": fail_reason,
    }


def save_turn(
    redis_client: Any,
    turn: dict,
    tenant_id: str | None = None,
    session_id: str | None = None,
    ttl: int = TURN_TTL_SECONDS,
) -> str:
    """Saves turn state to Redis with key turn:{tenant_id}:{session_id} and TTL 7200s."""
    t_id = tenant_id or turn["tenant_id"]
    s_id = session_id or turn.get("session_id") or turn["turn_id"]
    key = turn_key(t_id, s_id)
    raw = json.dumps(turn)
    redis_client.set(key, raw, ex=ttl)
    return key


def get_turn(
    redis_client: Any,
    tenant_id: str,
    session_id: str | None = None,
) -> dict | None:
    """Retrieves turn state from Redis. Returns None if expired or non-existent."""
    key = turn_key(tenant_id, session_id)
    raw = redis_client.get(key)
    if not raw:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def delete_turn(
    redis_client: Any,
    tenant_id: str,
    session_id: str | None = None,
) -> bool:
    """Deletes turn state from Redis."""
    key = turn_key(tenant_id, session_id)
    return bool(redis_client.delete(key))


def compute_snapshot_hash(
    updated_ats: dict[str, str | int] | list[tuple[str, str | int]] | str,
) -> str:
    """
    Computes deterministic snapshot hash from entity updated_at values.
    Returns format sha256:<64 hex chars>.
    """
    if isinstance(updated_ats, str):
        if updated_ats.startswith("sha256:") and len(updated_ats) == 71:
            return updated_ats
        canonical = updated_ats.encode("utf-8")
    elif isinstance(updated_ats, dict):
        pairs = [f"{k}={updated_ats[k]}" for k in sorted(updated_ats.keys())]
        canonical = "\n".join(pairs).encode("utf-8")
    elif isinstance(updated_ats, list):
        pairs = [f"{k}={v}" for k, v in sorted(updated_ats, key=lambda p: str(p[0]))]
        canonical = "\n".join(pairs).encode("utf-8")
    else:
        canonical = str(updated_ats).encode("utf-8")

    digest = hashlib.sha256(canonical).hexdigest()
    return f"sha256:{digest}"


def confirm_proposal(
    redis_client: Any,
    tenant_id: str,
    session_id: str,
    proposal_id: str,
    expected_epoch: int,
    provided_snapshot_hash: str,
    live_updated_ats: dict[str, str | int]
    | list[tuple[str, str | int]]
    | Callable[[], dict[str, str | int]]
    | str,
    idempotency_k: str | None = None,
    action_executor: Callable[[], dict] | None = None,
) -> dict:
    """
    Implements proposal confirmation lock lock:{proposal_id} (30s TTL) with snapshot hash
    re-verification against live entity updated_at values.
    Returns HTTP 409 Conflict with current_snapshot_hash on mismatch.
    """
    lk = lock_key(proposal_id)
    tk = turn_key(tenant_id, session_id)

    # 1. Proposal confirmation lock lock:{proposal_id} (30s TTL)
    lock_acquired = redis_client.set(lk, "locked", nx=True, ex=LOCK_TTL_SECONDS)
    if not lock_acquired:
        raise ProposalConflictException("conflict_in_progress")

    try:
        # Check existing receipt for idempotency key if provided
        if idempotency_k:
            ik = idempotency_key(idempotency_k)
            stored_idem_raw = redis_client.get(ik)
            if stored_idem_raw:
                if isinstance(stored_idem_raw, (bytes, bytearray)):
                    stored_idem_raw = stored_idem_raw.decode("utf-8")
                stored_idem = json.loads(stored_idem_raw)
                if stored_idem.get("status") == "completed":
                    return stored_idem
                elif stored_idem.get("status") == "in_progress":
                    raise ProposalConflictException("conflict_in_progress")

        turn = get_turn(redis_client, tenant_id, session_id)
        if turn is None:
            raise TurnGoneException("turn_gone")

        if turn.get("epoch") != expected_epoch:
            raise StaleEpochException(
                detail="stale_fence", current_epoch=turn.get("epoch")
            )

        if turn.get("status") != "AWAITING_CONFIRMATION":
            raise HTTPException(
                status_code=409,
                detail={"error": "stale_fence", "epoch": turn.get("epoch")},
            )

        # Re-verify snapshot hash against live entity updated_at values
        if callable(live_updated_ats):
            live_vals = live_updated_ats()
        else:
            live_vals = live_updated_ats

        current_hash = compute_snapshot_hash(live_vals)

        if provided_snapshot_hash != current_hash:
            # Mismatch: Return HTTP 409 Conflict with current_snapshot_hash
            raise SnapshotMismatchException(
                current_snapshot_hash=current_hash,
                epoch=turn["epoch"],
            )

        # Mark idempotency in_progress if key provided
        if idempotency_k:
            ik = idempotency_key(idempotency_k)
            redis_client.set(
                ik,
                json.dumps(
                    {"status": "in_progress", "idempotency_key": idempotency_k}
                ),
                ex=IDEMPOTENCY_TTL_SECONDS,
            )

        # Transition state to COMPLETED using atomic Lua CAS
        updated_turn = cas_transition(
            redis_client,
            tk,
            expected_epoch,
            "COMPLETED",
        )

        # Execute the action
        action_result = {}
        if action_executor is not None:
            action_result = action_executor()

        receipt = {
            "status": "completed",
            "idempotency_key": idempotency_k or generate_uuidv7(),
            "executed": True,
            "result": action_result,
            "epoch": updated_turn["epoch"],
        }

        if idempotency_k:
            ik = idempotency_key(idempotency_k)
            redis_client.set(ik, json.dumps(receipt), ex=IDEMPOTENCY_TTL_SECONDS)

        return receipt

    finally:
        # Always release proposal lock
        redis_client.delete(lk)


def resume_turn(
    redis_client: Any,
    tenant_id: str,
    session_id: str,
    last_known_epoch: int,
) -> dict:
    """
    Validates turn resumption:
    Accepts last_known_epoch.
    Missing/expired turn or stale epoch -> HTTP 410 (StaleEpochException).
    """
    turn = get_turn(redis_client, tenant_id, session_id)
    if turn is None:
        raise StaleEpochException(detail="turn_gone")
    if turn.get("epoch") != last_known_epoch:
        raise StaleEpochException(
            detail="stale_epoch", current_epoch=turn.get("epoch")
        )
    return turn


# -----------------------------------------------------------------------------
# FastAPI Router and Application
# -----------------------------------------------------------------------------

router = APIRouter()
_DEFAULT_REDIS_CLIENT: Any = None


def set_redis_client(client: Any) -> None:
    global _DEFAULT_REDIS_CLIENT
    _DEFAULT_REDIS_CLIENT = client


def get_redis_client() -> Any:
    global _DEFAULT_REDIS_CLIENT
    if _DEFAULT_REDIS_CLIENT is not None:
        return _DEFAULT_REDIS_CLIENT
    import redis

    return redis.Redis()


class ResumePayload(BaseModel):
    last_known_epoch: int
    tenant_id: str | None = None
    session_id: str | None = None
    turn_id: str | None = None


@router.post("/resume")
def resume_endpoint(
    payload: ResumePayload,
    request: Request = None,
    redis_client: Any = Depends(get_redis_client),
):
    """POST /resume endpoint accepting last_known_epoch."""
    tenant = payload.tenant_id
    session = payload.session_id or payload.turn_id
    if not tenant or not session:
        raise HTTPException(
            status_code=400, detail="tenant_id and session_id (or turn_id) required"
        )

    return resume_turn(redis_client, tenant, session, payload.last_known_epoch)


app = FastAPI(title="Agent Turn State API")
app.include_router(router)
