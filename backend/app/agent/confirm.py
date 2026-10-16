from __future__ import annotations

from dataclasses import dataclass

from app.agent.turn_state import StaleFence, fence_cas


@dataclass(frozen=True)
class ConfirmView:
    turn: dict | None
    request_epoch: int
    provided_hash: str
    computed_hash: str
    idempotency_key: str
    stored_idempotency: dict | None
    lock_acquired: bool


@dataclass(frozen=True)
class ConfirmDecision:
    status_code: int
    error: str | None
    body: dict
    write_in_progress: bool = False
    execute: bool = False
    release_lock: bool = False


def evaluate_confirm(view: ConfirmView) -> ConfirmDecision:
    if view.turn is None:
        return ConfirmDecision(410, "turn_gone", {"error": "turn_gone"})

    blob = view.turn
    stored = view.stored_idempotency
    if stored and stored.get("status") == "completed" and stored.get("idempotency_key") == view.idempotency_key:
        return ConfirmDecision(200, None, stored)

    try:
        if blob["epoch"] != view.request_epoch:
            raise StaleFence("epoch mismatch")
        if blob["status"] != "AWAITING_CONFIRMATION":
            raise StaleFence("not awaiting confirmation")
    except StaleFence:
        return ConfirmDecision(
            409,
            "stale_fence",
            {"error": "stale_fence", "epoch": blob["epoch"]},
        )

    if stored and stored.get("status") == "in_progress":
        return ConfirmDecision(409, "conflict_in_progress", {"error": "conflict_in_progress"})

    if not view.lock_acquired:
        return ConfirmDecision(409, "conflict_in_progress", {"error": "conflict_in_progress"})

    if view.provided_hash != view.computed_hash:
        return ConfirmDecision(
            409,
            "snapshot_mismatch",
            {
                "error": "snapshot_mismatch",
                "current_snapshot_hash": view.computed_hash,
                "epoch": blob["epoch"],
            },
            write_in_progress=False,
            execute=False,
            release_lock=True,
        )

    fence_cas(blob, view.request_epoch, "COMPLETED")
    return ConfirmDecision(
        200,
        None,
        {
            "status": "completed",
            "idempotency_key": view.idempotency_key,
            "executed": True,
            "result": {},
        },
        write_in_progress=True,
        execute=True,
        release_lock=True,
    )
