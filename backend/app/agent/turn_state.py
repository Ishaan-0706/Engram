from app.core.config import settings

TURN_TTL_SECONDS = settings.TURN_TTL_SECONDS
LOCK_TTL_SECONDS = settings.PROPOSAL_LOCK_TTL_SECONDS
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


class StaleFence(Exception):
    pass


class IllegalTransition(Exception):
    pass


def turn_key(turn_id: str) -> str:
    return f"{TURN_PREFIX}{turn_id}"


def lock_key(proposal_id: str) -> str:
    return f"{LOCK_PREFIX}{proposal_id}"


def idempotency_key(key: str) -> str:
    return f"{IDEMPOTENCY_PREFIX}{key}"


def fence_cas(blob: dict, expected_epoch: int, new_status: str) -> dict:
    if blob["epoch"] != expected_epoch:
        raise StaleFence("epoch mismatch")
    current = blob["status"]
    if new_status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise IllegalTransition(f"{current} -> {new_status}")
    return {**blob, "epoch": expected_epoch + 1, "status": new_status}


def heartbeat_ttl() -> int:
    """EXPIRE only. Callers must not bump epoch."""
    return TURN_TTL_SECONDS
