"""FastAPI application – Developer 2 HTTP layer.

Routes
------
POST /api/turn     – Run one agent turn.
POST /api/resume   – Resume a turn using last_known_epoch.
POST /api/confirm  – Confirm a staged mutation proposal.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import redis as redis_lib
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agent.orchestrator import run_agent_turn
from app.agent.state import (
    SnapshotMismatchException,
    StaleEpochException,
    TurnGoneException,
    cas_transition,
    compute_snapshot_hash,
    confirm_proposal,
    generate_uuidv7,
    get_turn,
    idempotency_key,
    lock_key,
    resume_turn,
    save_turn,
)
from app.mcp_server.action_tools import mark_document_updated, reassign_system_owner
from app.mcp_server.tools import get_live_graph_topology

from app.core.config import settings

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

CORS_ORIGINS = settings.CORS_ORIGINS

app = FastAPI(title="Company Brain API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Redis dependency
# ---------------------------------------------------------------------------

_redis_client: Any = None


def set_redis_client(client: Any) -> None:
    """Override the Redis client (used in tests with FakeRedis)."""
    global _redis_client
    _redis_client = client


def _get_redis() -> Any:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    return redis_lib.from_url(settings.REDIS_URL, decode_responses=False)


def get_redis(request: Request) -> Any:  # FastAPI dependency
    return _get_redis()


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class TurnRequest(BaseModel):
    tenant_id: str
    session_id: str
    user_query: str
    epoch: int = Field(default=0, ge=0)


class TurnResponse(BaseModel):
    turn: dict
    epoch: int


class ResumeRequest(BaseModel):
    tenant_id: str
    session_id: str
    last_known_epoch: int = Field(ge=0)


class ConfirmRequest(BaseModel):
    tenant_id: str
    session_id: str
    proposal_id: str
    snapshot_hash: str
    idempotency_key: str


# ---------------------------------------------------------------------------
# POST /api/turn
# ---------------------------------------------------------------------------


@app.post("/api/turn", response_model=TurnResponse)
def api_turn(
    body: TurnRequest,
    redis: Any = Depends(get_redis),
) -> TurnResponse:
    """Run one agent turn and return the updated state + new epoch."""
    try:
        updated = run_agent_turn(
            tenant_id=body.tenant_id,
            session_id=body.session_id,
            user_query=body.user_query,
            client_epoch=body.epoch,
            redis_client=redis,
        )
    except StaleEpochException as exc:
        raise exc
    except Exception as exc:
        log.exception("api_turn unexpected error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return TurnResponse(turn=updated, epoch=updated["epoch"])


# ---------------------------------------------------------------------------
# POST /api/resume
# ---------------------------------------------------------------------------


@app.post("/api/resume")
def api_resume(
    body: ResumeRequest,
    redis: Any = Depends(get_redis),
) -> dict:
    """Return current turn state; 410 if expired or epoch mismatch."""
    # Raises StaleEpochException (HTTP 410) on failure
    return resume_turn(redis, body.tenant_id, body.session_id, body.last_known_epoch)


# ---------------------------------------------------------------------------
# POST /api/confirm
# ---------------------------------------------------------------------------


@app.post("/api/confirm")
def api_confirm(
    body: ConfirmRequest,
    redis: Any = Depends(get_redis),
) -> dict:
    """Confirm a staged mutation proposal.

    Flow (mirrors PROTOCOL.md §Confirm / stale snapshot):
    1.  Missing turn → 410 turn_gone.
    2.  Epoch or status mismatch → 409 stale_fence.
    3.  Idempotency receipt present → 200 (replay).
    4.  Acquire lock:{proposal_id} NX (30 s TTL) → 409 conflict_in_progress if lost.
    5.  Re-read FalkorDB entities; recompute snapshot hash.
    6.  Hash mismatch → 409 snapshot_mismatch + current_snapshot_hash.
    7.  Execute action, write receipt, fence-CAS → COMPLETED.
    """
    turn = get_turn(redis, body.tenant_id, body.session_id)
    if turn is None:
        raise HTTPException(status_code=410, detail={"error": "turn_gone"})

    proposal = turn.get("pending_proposal")
    if not proposal or proposal.get("proposal_id") != body.proposal_id:
        raise HTTPException(status_code=409, detail={"error": "stale_fence", "epoch": turn["epoch"]})

    action_meta: dict = proposal.get("action", {})
    action_type: str = action_meta.get("type", "")
    system_name: str = action_meta.get("system_name", "")
    if not system_name:
        for rec_id, rec_info in (turn.get("working_set") or {}).items():
            if rec_info.get("label") == "System":
                system_name = rec_info.get("properties", {}).get("name") or rec_id
                break

    def _fetch_live_ats() -> dict[str, str]:
        """Re-read updated_at proxies from the proposal record_ids."""
        record_ids = action_meta.get("record_ids", [])
        ws: dict = turn.get("working_set") or {}
        if record_ids:
            return {rid: ws.get(rid, {}).get("label", "") for rid in record_ids}
        return {rid: info.get("label", "") for rid, info in ws.items()}

    def _execute_action() -> dict:
        tenant = body.tenant_id
        if action_type == "reassign_owner":
            new_email = action_meta.get("new_owner_email", "")
            if not new_email:
                raise HTTPException(status_code=422, detail="new_owner_email missing in proposal")
            result = reassign_system_owner(tenant, system_name, new_email)
        elif action_type in ("documentation_drift_fix", "mark_document_updated"):
            doc_id = action_meta.get("document_id", "")
            decision_id = action_meta.get("superseding_decision_id", "")
            if not doc_id or not decision_id:
                ws = turn.get("working_set") or {}
                for rid, rinfo in ws.items():
                    if rinfo.get("label") == "Document" and not doc_id:
                        doc_id = rid
                    if rinfo.get("label") == "Decision" and rinfo.get("properties", {}).get("status") == "active" and not decision_id:
                        decision_id = rid
            if not doc_id or not decision_id:
                raise HTTPException(status_code=422, detail="document_id or superseding_decision_id missing")
            result = mark_document_updated(tenant, doc_id, decision_id)
        else:
            # Unknown action type – reject cleanly
            raise HTTPException(status_code=422, detail=f"unknown action_type: {action_type!r}")

        if not result.get("ok"):
            raise HTTPException(
                status_code=502,
                detail={"error": "action_failed", "detail": result.get("error")},
            )
        return result

    try:
        receipt = confirm_proposal(
            redis_client=redis,
            tenant_id=body.tenant_id,
            session_id=body.session_id,
            proposal_id=body.proposal_id,
            expected_epoch=turn["epoch"],
            provided_snapshot_hash=body.snapshot_hash,
            live_updated_ats=_fetch_live_ats,
            idempotency_k=body.idempotency_key,
            action_executor=_execute_action,
        )
    except (StaleEpochException, TurnGoneException, SnapshotMismatchException) as exc:
        raise exc
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("api_confirm unexpected error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return receipt


# ---------------------------------------------------------------------------
# GET /api/graph/{tenant_id}
# ---------------------------------------------------------------------------


@app.get("/api/graph/{tenant_id}")
def api_get_graph(tenant_id: str) -> dict[str, Any]:
    """Expose live graph topology and chronological decision timeline directly from FalkorDB.

    Returns live nodes, edges, and decision timeline.
    If FalkorDB is unreachable, returns HTTP 503 Service Unavailable. Never returns hardcoded mock objects.
    """
    try:
        topology = get_live_graph_topology(tenant_id)
        return topology
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("api_get_graph error for tenant=%s: %s", tenant_id, exc)
        raise HTTPException(
            status_code=503,
            detail=f"FalkorDB Connection Required: Unable to load live graph topology for '{tenant_id}'. Error: {exc}",
        )
