"""Agent turn orchestrator – Developer 2 owned.

Pipeline per turn:
  1.  Fetch or initialise turn state from Redis (key turn:{tenant_id}:{session_id}).
  2.  Lua-CAS PLANNING → EXECUTING_TOOLS, reject stale epoch (410).
  3.  Route the user query to one MCP read tool.
  4.  Validate envelope, populate working_set + evidence_bag.
  5.  Two-phase grounded synthesis – exactly one constrained retry on failure.
  6.  If mutation needed → stage pending_proposal, CAS → AWAITING_CONFIRMATION.
  7.  Otherwise → CAS → COMPLETED.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from app.agent.evidence import (
    TwoPhaseEvidenceValidator,
    UnverifiableClaimException,
    build_constrained_prompt,
    parse_mcp_tool_response,
)
from app.agent.state import (
    StaleEpochException,
    cas_transition,
    compute_snapshot_hash,
    create_initial_turn,
    generate_uuidv7,
    get_turn,
    idempotency_key,
    save_turn,
    turn_key,
)
from app.mcp_server.tools import (
    detect_documentation_drift,
    get_decision_history,
    get_system_ownership,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM = "payment-gateway"
_MAX_TOOL_ROUNDS = 4          # architecture.md §6.3

# Simple keyword → tool routing.  Matched in order; first match wins.
_INTENT_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"owner|who|team|responsibility|contact|expert",
                re.I), "system_ownership"),
    (re.compile(r"drift|stale|rfc|document|outdated|aligned",
                re.I), "documentation_drift"),
    (re.compile(r"decision|auth|architecture|why|jwt|ed25519|token|gateway",
                re.I), "decision_history"),
]


# ---------------------------------------------------------------------------
# Intent routing helpers
# ---------------------------------------------------------------------------

def _route_intent(query: str) -> str:
    """Return a tool-name string based on lightweight keyword matching."""
    for pattern, tool in _INTENT_RULES:
        if pattern.search(query):
            return tool
    # default: decision history surfaces the most context
    return "decision_history"


def _call_tool(
    tenant_id: str,
    tool_name: str,
    system_name: str,
    monkeypatched_tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dispatch to the appropriate MCP read-tool function."""
    overrides = monkeypatched_tools or {}
    if tool_name == "documentation_drift":
        fn = overrides.get("detect_documentation_drift", detect_documentation_drift)
    elif tool_name == "system_ownership":
        fn = overrides.get("get_system_ownership", get_system_ownership)
    else:
        fn = overrides.get("get_decision_history", get_decision_history)
    return fn(tenant_id, system_name)


# ---------------------------------------------------------------------------
# Synthesis shim – real LLM call site (stubbed for unit tests via injection)
# ---------------------------------------------------------------------------

def _default_synthesize(
    tenant_id: str,
    session_id: str,
    user_query: str,
    evidence_bag: dict[str, dict],
    tool_response: dict[str, Any],
) -> Any:
    """Return a callable that produces the structured answer dict.

    In production this would call the LLM provider.  The callable signature
    matches ``TwoPhaseEvidenceValidator.execute``'s ``synthesize_fn``:

        synthesize_fn(prompt: str, allowed_ids: list[str]) -> dict
    """

    def _synthesize(prompt: str, allowed_ids: list[str]) -> dict:
        # Stub: compose a deterministic answer citing the first evidence id,
        # so the orchestrator can be exercised without a live LLM.
        if not allowed_ids:
            return {"claims": []}
        first_id = allowed_ids[0]
        return {
            "claims": [
                {
                    "text": f"[Stub] Answer to: {user_query[:120]}",
                    "cited_evidence_ids": [first_id],
                }
            ]
        }

    return _synthesize


# ---------------------------------------------------------------------------
# Proposal staging
# ---------------------------------------------------------------------------

_MUTATION_PATTERNS = re.compile(
    r"reassign|owner|drift.*(fix|update|mark)|update.*(doc|rfc|document)",
    re.I,
)


def _needs_mutation(query: str, tool_name: str) -> bool:
    """Decide whether the query requires a graph mutation proposal."""
    return bool(_MUTATION_PATTERNS.search(query)) or tool_name == "documentation_drift"


def _snapshot_from_records(records: list[dict]) -> str:
    """Compute a deterministic snapshot hash from the record ids + labels."""
    items = sorted((r["id"], r.get("label", "")) for r in records)
    return compute_snapshot_hash({f"{label}:{rid}": "present" for rid, label in items})


# ---------------------------------------------------------------------------
# Main orchestrator entry-point
# ---------------------------------------------------------------------------

def run_agent_turn(
    tenant_id: str,
    session_id: str,
    user_query: str,
    client_epoch: int,
    *,
    redis_client: Any,
    user_id: str = "anonymous",
    system_name: str = _DEFAULT_SYSTEM,
    synthesize_fn: Any | None = None,
    _tools: dict[str, Any] | None = None,
) -> dict:
    """Run one agent turn and persist the updated state to Redis.

    Parameters
    ----------
    tenant_id:
        Tenant identifier (maps to FalkorDB graph ``tenant_{tenant_id}``).
    session_id:
        Client session identifier; Redis key = ``turn:{tenant_id}:{session_id}``.
    user_query:
        Natural-language question or command.
    client_epoch:
        Last epoch seen by the client – used for Lua CAS fencing.
    redis_client:
        Active Redis / FakeRedis connection.
    user_id:
        Acting user (resolved from JWT in the HTTP layer).
    system_name:
        FalkorDB system node to query (defaults to ``payment-gateway``).
    synthesize_fn:
        Injectable LLM callable for unit tests.  Receives
        ``(prompt, allowed_ids) -> dict``.
    _tools:
        Optional mapping to override MCP tool functions in tests.

    Returns
    -------
    dict
        The final turn state blob as stored in Redis.

    Raises
    ------
    StaleEpochException
        HTTP 410 – client epoch does not match stored epoch.
    """

    # ------------------------------------------------------------------
    # 1. Fetch or initialise turn state
    # ------------------------------------------------------------------
    turn = get_turn(redis_client, tenant_id, session_id)

    if turn is None:
        turn = create_initial_turn(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            status="PLANNING",
            epoch=client_epoch,
        )
        save_turn(redis_client, turn, tenant_id, session_id)
        log.info(
            "orchestrator: new turn tenant=%s session=%s epoch=%d",
            tenant_id, session_id, client_epoch,
        )

    stored_epoch: int = turn["epoch"]

    # Fence: client must supply the current epoch to proceed.
    if client_epoch != stored_epoch:
        raise StaleEpochException(
            detail="stale_epoch",
            current_epoch=stored_epoch,
        )

    # ------------------------------------------------------------------
    # 2. Lua-CAS PLANNING → EXECUTING_TOOLS
    # ------------------------------------------------------------------
    # Raises StaleEpochException (HTTP 410) on mismatch.
    turn = cas_transition(
        redis_client,
        tenant_id,
        expected_epoch=stored_epoch,
        new_status="EXECUTING_TOOLS",
        session_id=session_id,
    )

    # ------------------------------------------------------------------
    # 3. Intent routing
    # ------------------------------------------------------------------
    tool_name = _route_intent(user_query)
    log.info("orchestrator: routing query to tool=%s", tool_name)

    # ------------------------------------------------------------------
    # 4. Call the MCP read tool (up to _MAX_TOOL_ROUNDS respected by contract)
    # ------------------------------------------------------------------
    tool_response = _call_tool(tenant_id, tool_name, system_name, _tools)

    # ------------------------------------------------------------------
    # 5. Ingest tool output
    # ------------------------------------------------------------------
    if not tool_response.get("ok"):
        # Tool failure → terminal FAILED
        log.warning("orchestrator: tool %s failed: %s", tool_name, tool_response)
        fail_turn = cas_transition(
            redis_client,
            tenant_id,
            expected_epoch=turn["epoch"],
            new_status="FAILED",
            session_id=session_id,
            updates={
                "fail_reason": "execute_crash",
                "tool_trace": turn.get("tool_trace", []) + [
                    {"tool": tool_name, "ok": False,
                     "at": _utcnow(),
                     "error_code": tool_response.get("error", {}).get("code", "unknown")}
                ],
            },
        )
        return fail_turn

    # Validate envelope and build evidence bag + working_set
    evidence_new = parse_mcp_tool_response(tool_response)
    records: list[dict] = tool_response.get("records", [])

    working_set: dict[str, Any] = dict(turn.get("working_set") or {})
    for rec in records:
        working_set[rec["id"]] = {"label": rec["label"], "properties": rec.get("properties", {})}

    evidence_bag: dict[str, dict] = dict(turn.get("evidence_bag") or {})
    evidence_bag.update(evidence_new)

    record_ids: set[str] = set(working_set.keys())

    tool_trace = list(turn.get("tool_trace") or [])
    tool_trace.append({"tool": tool_name, "ok": True, "at": _utcnow()})

    # Persist partial state (evidence_bag and working_set) mid-turn.
    # We cannot CAS here (different status), so we overwrite the blob directly.
    turn_mid = {
        **turn,
        "working_set": working_set,
        "evidence_bag": evidence_bag,
        "tool_trace": tool_trace,
    }
    save_turn(redis_client, turn_mid, tenant_id, session_id)

    # ------------------------------------------------------------------
    # 6. Two-phase grounded synthesis
    # ------------------------------------------------------------------
    if synthesize_fn is not None:
        # Directly injected callable (tests / integration)
        _synth_fn = synthesize_fn
    else:
        _synth_fn = _default_synthesize(
            tenant_id, session_id, user_query, evidence_bag, tool_response
        )

    validator = TwoPhaseEvidenceValidator(evidence_bag, record_ids=record_ids)
    result = validator.execute(
        prompt=user_query,
        synthesize_fn=_synth_fn,
    )

    synthesis_traces = list(turn.get("synthesis_traces") or [])
    synthesis_traces.extend(result.synthesis_traces)

    # ------------------------------------------------------------------
    # 7a. Synthesis FAILED → terminal
    # ------------------------------------------------------------------
    if result.status == "FAILED":
        fail_turn = cas_transition(
            redis_client,
            tenant_id,
            expected_epoch=turn["epoch"],
            new_status="FAILED",
            session_id=session_id,
            updates={
                "fail_reason": "unverifiable_claim",
                "evidence_bag": evidence_bag,
                "working_set": working_set,
                "tool_trace": tool_trace,
                "synthesis_traces": synthesis_traces,
            },
        )
        log.warning(
            "orchestrator: synthesis FAILED (unverifiable_claim) tenant=%s session=%s",
            tenant_id, session_id,
        )
        return fail_turn

    # ------------------------------------------------------------------
    # 7b. Mutation required → stage pending_proposal, AWAITING_CONFIRMATION
    # ------------------------------------------------------------------
    if _needs_mutation(user_query, tool_name):
        proposal_id = generate_uuidv7()
        snapshot_hash = _snapshot_from_records(records)

        pending_proposal = {
            "proposal_id": proposal_id,
            "snapshot_hash": snapshot_hash,
            "action": {
                "type": "documentation_drift_fix" if tool_name == "documentation_drift"
                        else "reassign_owner",
                "system_name": system_name,
                "tool_name": tool_name,
                "record_ids": list(record_ids),
            },
        }

        awaiting_turn = cas_transition(
            redis_client,
            tenant_id,
            expected_epoch=turn["epoch"],
            new_status="AWAITING_CONFIRMATION",
            session_id=session_id,
            updates={
                "evidence_bag": evidence_bag,
                "working_set": working_set,
                "tool_trace": tool_trace,
                "synthesis_traces": synthesis_traces,
                "pending_proposal": pending_proposal,
                "fail_reason": None,
            },
        )
        log.info(
            "orchestrator: staged proposal=%s tenant=%s session=%s",
            proposal_id, tenant_id, session_id,
        )
        return awaiting_turn

    # ------------------------------------------------------------------
    # 7c. No mutation → COMPLETED
    # ------------------------------------------------------------------
    completed_turn = cas_transition(
        redis_client,
        tenant_id,
        expected_epoch=turn["epoch"],
        new_status="COMPLETED",
        session_id=session_id,
        updates={
            "evidence_bag": evidence_bag,
            "working_set": working_set,
            "tool_trace": tool_trace,
            "synthesis_traces": synthesis_traces,
            "pending_proposal": None,
            "fail_reason": None,
        },
    )
    log.info(
        "orchestrator: COMPLETED tenant=%s session=%s epoch=%d",
        tenant_id, session_id, completed_turn["epoch"],
    )
    return completed_turn


# ---------------------------------------------------------------------------
# Tiny datetime helper (avoids importing datetime at module level for speed)
# ---------------------------------------------------------------------------

def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
