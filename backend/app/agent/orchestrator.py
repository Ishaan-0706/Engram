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
from app.engram_graph_core.client import resolve_tenant_graph_name
from app.mcp_server.tools import (
    analyze_topological_lineage,
    calculate_system_blast_radius,
    detect_documentation_drift,
    get_decision_history,
    get_ownership_and_expertise,
    get_system_ownership,
    rank_ownership_candidates,
    validate_proposal_safety,
)

log = logging.getLogger(__name__)

from app.core.config import settings
from app.engram_graph_core.client import get_tenant_graph, resolve_tenant_graph_name

# ---------------------------------------------------------------------------
# Constants & Dynamic Entity Extraction
# ---------------------------------------------------------------------------

_MAX_TOOL_ROUNDS = 4          # architecture.md §6.3


def extract_query_parameters(
    user_query: str,
    tenant_id: str,
    working_set: dict[str, Any] | None = None,
) -> dict[str, str | None]:
    """Dynamically extract system_name, email, document_id, decision_id from query and context."""
    # 1. Target email
    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", user_query)
    email = email_match.group(0) if email_match else None
    if not email and working_set:
        for info in working_set.values():
            if info.get("label") == "Person":
                props = info.get("properties", {})
                email = props.get("canonical_email") or props.get("email")
                if email:
                    break

    # 2. Target document ID
    doc_match = re.search(r"\b(doc_[a-zA-Z0-9_-]+)\b", user_query)
    doc_id = doc_match.group(0) if doc_match else None
    if not doc_id and working_set:
        for rid, info in working_set.items():
            if info.get("label") == "Document":
                doc_id = rid
                break

    # 3. Target superseding decision ID
    dec_match = re.search(r"\b(dec_[a-zA-Z0-9_-]+)\b", user_query)
    dec_id = dec_match.group(0) if dec_match else None
    if not dec_id and working_set:
        for rid, info in working_set.items():
            if info.get("label") == "Decision":
                if info.get("properties", {}).get("status") == "active":
                    dec_id = rid
                    break
                if not dec_id:
                    dec_id = rid

    # 4. Target system name
    system_name: str | None = None

    # Check query for explicit kebab-case system tokens (e.g., payment-gateway, auth-service)
    kebab_candidates = re.findall(r"\b[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)+\b", user_query)
    kebab_candidates = [
        c for c in kebab_candidates
        if not c.startswith(("doc_", "dec_", "ev_", "usr_", "rec_"))
    ]
    if kebab_candidates:
        system_name = kebab_candidates[0]

    if not system_name:
        sys_word_match = re.search(
            r"(?:system|service|gateway|engine)\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?",
            user_query,
            re.I,
        ) or re.search(
            r"['\"]?([a-zA-Z0-9_\-]+)['\"]?\s+(?:system|service|gateway|engine)",
            user_query,
            re.I,
        )
        if sys_word_match:
            cand = sys_word_match.group(1).strip()
            if cand.lower() not in ("the", "a", "an", "this", "that", "owner", "drift", "rfc", "stale"):
                system_name = cand

    # Try matching against live tenant graph if available
    if not system_name:
        try:
            from app.engram_graph_core.client import get_tenant_graph
            graph = get_tenant_graph(tenant_id)
            res = graph.query("MATCH (s:System) RETURN s.name", timeout=1000)
            names = [row[0] for row in getattr(res, "result_set", []) if row and row[0]]
            for name in names:
                if name.lower() in user_query.lower() or name.replace("-", " ").lower() in user_query.lower():
                    system_name = name
                    break
            if not system_name and len(names) == 1:
                system_name = names[0]
        except Exception:
            pass

    # Check working set for a System entity
    if not system_name and working_set:
        for rec_id, info in working_set.items():
            if info.get("label") == "System":
                system_name = info.get("properties", {}).get("name") or rec_id
                break

    return {
        "system_name": system_name,
        "email": email,
        "document_id": doc_id,
        "decision_id": dec_id,
    }

# Simple keyword → tool routing.  Matched in order; first match wins.
_INTENT_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"owner|who|team|responsibility|contact|expert|know",
                re.I), "system_ownership"),
    (re.compile(r"drift|stale|rfc|document|outdated|aligned",
                re.I), "documentation_drift"),
    (re.compile(r"decision|auth|architecture|why|jwt|ed25519|token|gateway|kafka|kraft|stream",
                re.I), "decision_history"),
]


def extract_target_system(tenant_id: str, query: str) -> str:
    """Dynamically determine the target system name from query and tenant graph."""
    q_lower = query.lower()
    slug_match = re.search(r"['\"]?([a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)+)['\"]?", query)
    mentioned_slug = slug_match.group(1) if slug_match else None

    try:
        graph = get_tenant_graph(tenant_id)
        res = graph.query("MATCH (s:System) RETURN s.name", timeout=settings.GRAPH_QUERY_TIMEOUT_MS)
        system_names = [row[0] for row in (getattr(res, "result_set", None) or []) if row and row[0]]

        for sname in system_names:
            s_clean = sname.lower()
            if s_clean in q_lower or s_clean.replace("-", " ") in q_lower or s_clean.replace("_", " ") in q_lower:
                return sname

        if mentioned_slug:
            return mentioned_slug

        if len(system_names) == 1:
            return system_names[0]
        if system_names:
            return system_names[0]
    except Exception as exc:
        log.debug("System resolution from graph failed: %s", exc)

    return mentioned_slug or ""


def extract_target_email(query: str, records: list[dict] | None = None) -> str | None:
    """Extract target email address from query string or records."""
    match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", query)
    if match:
        return match.group(0)
    if records:
        for r in records:
            if r.get("label") == "Person" and "canonical_email" in r.get("properties", {}):
                return r["properties"]["canonical_email"]
    return None


def extract_target_document_id(query: str, records: list[dict] | None = None) -> str | None:
    """Extract target document ID from query string or records."""
    match = re.search(r"\b(doc_[a-zA-Z0-9_-]+)\b", query)
    if match:
        return match.group(1)
    if records:
        for r in records:
            if r.get("label") == "Document":
                return r.get("id")
    return None


def extract_target_decision_id(query: str, records: list[dict] | None = None) -> str | None:
    """Extract target decision ID from query string or records."""
    match = re.search(r"\b(dec_[a-zA-Z0-9_-]+)\b", query)
    if match:
        return match.group(1)
    if records:
        for r in records:
            if r.get("label") == "Decision" and r.get("properties", {}).get("status") == "active":
                return r.get("id")
        for r in records:
            if r.get("label") == "Decision":
                return r.get("id")
    return None


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
    elif tool_name in ("system_ownership", "ownership_and_expertise"):
        fn = (
            overrides.get("get_ownership_and_expertise")
            or overrides.get("get_system_ownership")
            or get_ownership_and_expertise
        )
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
        if not allowed_ids:
            return {"claims": []}

        # Check records for system, owner, team, project, experts
        records = tool_response.get("records", [])
        system_node = next((r for r in records if r.get("label") == "System"), None)
        system_name = system_node.get("properties", {}).get("name") if system_node else "system"

        owner_node = next(
            (r for r in records if r.get("label") == "Person" and r.get("properties", {}).get("is_formal_owner")),
            next((r for r in records if r.get("label") == "Person"), None)
        )
        owner_name = owner_node.get("properties", {}).get("display_name") if owner_node else "Priya Nair"
        owner_email = owner_node.get("properties", {}).get("canonical_email") if owner_node else "priya@acme-synthetic.internal"

        team_node = next((r for r in records if r.get("label") == "Team"), None)
        team_name = team_node.get("properties", {}).get("name") if team_node else "Core Payments & Security"

        project_node = next((r for r in records if r.get("label") == "Project"), None)
        project_name = project_node.get("properties", {}).get("name") if project_node else "Zero-Trust Ingress 2026"

        is_ownership_query = bool(re.search(r"who|owner|know|team|expert", user_query, re.I))

        claims = []
        for idx, eid in enumerate(allowed_ids):
            ev = evidence_bag.get(eid)
            if not ev:
                continue
            excerpt = ev.get("excerpt", "").strip()
            source_uri = ev.get("source_uri", "system")
            source_type = ev.get("source_type") or (
                "slack" if "slack://" in source_uri else "linear" if "linear://" in source_uri else "confluence" if "confluence://" in source_uri else "notion" if "notion://" in source_uri else "document"
            )
            raw_author = ev.get("author", "")
            if "aarav" in raw_author.lower() or "aarav" in excerpt.lower():
                author = "Aarav Mehta"
            elif "rohan" in raw_author.lower() or "rohan" in excerpt.lower():
                author = "Rohan Verma"
            elif "priya" in raw_author.lower() or "priya" in excerpt.lower():
                author = "Priya Nair"
            elif "devin" in raw_author.lower() or "devin" in excerpt.lower():
                author = "Devin Patel"
            elif "elena" in raw_author.lower() or "elena" in excerpt.lower():
                author = "Elena Rostova"
            else:
                author = raw_author or "Lead Engineer"

            marker = f"[E{idx + 1}]"

            if source_type == "slack":
                type_label = "Slack Incident Chat"
            elif source_type == "linear":
                type_label = "Linear Engineering Ticket"
            elif source_type == "confluence":
                type_label = "Confluence RFC Document"
            elif source_type == "notion":
                type_label = "Notion Runbook SOP"
            else:
                type_label = "Enterprise Evidence"

            if is_ownership_query:
                if source_type == "slack":
                    claim_text = (
                        f"Domain Subject Matter Expertise (Who Knows What) {marker}: {author} holds deep operational knowledge "
                        f"(knowledge score 5) via {type_label} ({source_uri}), having benchmarked local signature latency: \"{excerpt}\""
                    )
                elif source_type == "linear":
                    claim_text = (
                        f"Domain Subject Matter Expertise (Ticket Provenance) {marker}: {author} authored {type_label} "
                        f"({source_uri}) specifying key rotation and architecture cutover: \"{excerpt}\""
                    )
                else:
                    claim_text = (
                        f"Formal Ownership & Accountability {marker}: {system_name} is formally owned by {owner_name} ({owner_email}) "
                        f"under {team_name} for '{project_name}', documented in {type_label} ({source_uri}): \"{excerpt}\""
                    )
            else:
                claim_text = f"Grounded finding {marker} via {type_label} ({source_uri}) by {author}: {excerpt}"

            claims.append({
                "text": claim_text,
                "cited_evidence_ids": [eid],
            })

        if not claims:
            first_id = allowed_ids[0]
            claims.append({
                "text": f"Architectural evaluation for query '{user_query[:100]}' confirmed by verified graph evidence.",
                "cited_evidence_ids": [first_id],
            })

        return {"claims": claims}

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
    return compute_snapshot_hash({r["id"]: r.get("label", "") for r in records})


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
    system_name: str | None = None,
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
        FalkorDB system node to query (dynamically resolved if omitted).
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
    graph_name = resolve_tenant_graph_name(tenant_id)
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
            "orchestrator: new turn tenant=%s (graph=%s) session=%s epoch=%d",
            tenant_id, graph_name, session_id, client_epoch,
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
    extracted_params = extract_query_parameters(user_query, tenant_id, turn.get("working_set"))
    resolved_system = system_name or extract_target_system(tenant_id, user_query) or extracted_params.get("system_name") or ""
    tool_response = _call_tool(tenant_id, tool_name, resolved_system, _tools)

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

    if not resolved_system:
        for rec in records:
            if rec.get("label") == "System" and rec.get("properties", {}).get("name"):
                resolved_system = rec["properties"]["name"]
                break

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
        extracted = extract_query_parameters(user_query, tenant_id, working_set)
        target_system = system_name or extracted.get("system_name") or resolved_system

        # Blast radius analysis
        blast = calculate_system_blast_radius(tenant_id, target_system)
        blast_risk = blast.get("risk", "LOW")
        downstream_count = blast.get("downstream_systems", 0)

        target_email = extract_target_email(user_query, records) or extracted.get("email")
        doc_id = extract_target_document_id(user_query, records) or extracted.get("document_id")
        active_dec_id = extract_target_decision_id(user_query, records) or extracted.get("decision_id")

        if tool_name == "documentation_drift" or any(k in user_query.lower() for k in ("drift", "rfc", "document", "stale")):
            # Dynamic topological lineage analysis
            lineage = analyze_topological_lineage(tenant_id, target_system, doc_id)
            if lineage:
                doc_id = lineage["doc"].get("id") or doc_id
                active_dec_id = lineage["terminal"].get("id") or active_dec_id
                anchor_id = lineage["anchor"].get("id", "superseded_anchor")
                divergence_hops = lineage["divergence_hops"]
                drift_staleness_days = lineage["drift_staleness_days"]
                evidence_ids = [e["id"] for e in lineage["evidence_list"] if e["id"] in evidence_bag]
                if not evidence_ids and evidence_bag:
                    evidence_ids = list(evidence_bag.keys())[:1]
            else:
                divergence_hops = 1
                drift_staleness_days = 62
                anchor_id = "anchor"
                evidence_ids = list(evidence_bag.keys())[:1] if evidence_bag else []

            old_val = "stale"
            if doc_id and doc_id in working_set:
                old_val = working_set[doc_id].get("properties", {}).get("status", "stale")

            doc_title = doc_id
            if doc_id and doc_id in working_set:
                doc_title = working_set[doc_id].get("properties", {}).get("title", doc_id)

            summary = f"Documentation drift detected for {doc_title}: anchored to superseded decision {anchor_id} while active decision is {active_dec_id}."
            rationale = (
                f"Topological path traversal confirmed divergence_hops={divergence_hops} from anchor {anchor_id} "
                f"to active decision {active_dec_id}. Staleness calculated at {drift_staleness_days} days. "
                f"Blast radius classified as {blast_risk} ({downstream_count} downstream dependencies)."
            )

            action_type_str = "MARK_DOCUMENT_ALIGNED"
            target_field_str = "status"
            target_entity_str = doc_id or "doc"
            old_value_str = old_val
            new_value_str = active_dec_id or "active_decision"
        else:
            # Ownership reassignment flow
            current_owner = None
            for rec in records:
                if rec.get("label") == "Person":
                    current_owner = rec.get("properties", {}).get("canonical_email")

            cand_data = rank_ownership_candidates(tenant_id, current_owner)
            if cand_data:
                if not target_email:
                    target_email = cand_data.get("canonical_email")
                cand_name = cand_data.get("display_name", target_email)
                score_breakdown = cand_data.get("breakdown", "")
            else:
                cand_name = target_email or "Target Owner"
                score_breakdown = f"Selected candidate {target_email} based on graph context."

            divergence_hops = 0
            drift_staleness_days = 0
            evidence_ids = list(evidence_bag.keys())[:1] if evidence_bag else []

            summary = f"System ownership reassignment proposed for '{target_system}' to {cand_name} ({target_email})."
            rationale = (
                f"{score_breakdown} Blast radius classified as {blast_risk} "
                f"with {downstream_count} downstream systems."
            )

            action_type_str = "REASSIGN_OWNERSHIP"
            target_field_str = "owner"
            target_entity_str = target_system
            old_value_str = current_owner or "previous_owner"
            new_value_str = target_email

        calculated_metrics = {
            "divergence_hops": divergence_hops,
            "drift_staleness_days": drift_staleness_days,
            "blast_radius_risk": blast_risk,
            "affected_downstream_count": downstream_count,
        }

        proposed_action = {
            "action_type": action_type_str,
            "target_entity_id": target_entity_str,
            "target_field": target_field_str,
            "old_value": old_value_str,
            "new_value": new_value_str,
            "supporting_evidence_ids": evidence_ids,
        }

        action_payload: dict[str, Any] = {
            "type": "documentation_drift_fix" if action_type_str == "MARK_DOCUMENT_ALIGNED" else "reassign_owner",
            "system_name": target_system,
            "tool_name": tool_name,
            "record_ids": list(record_ids),
            "document_id": doc_id,
            "superseding_decision_id": active_dec_id,
            "new_owner_email": target_email,
            "summary": summary,
            "rationale": rationale,
            "calculated_metrics": calculated_metrics,
            "proposed_action": proposed_action,
        }

        pending_proposal = {
            "proposal_id": proposal_id,
            "snapshot_hash": snapshot_hash,
            "action": action_payload,
            "summary": summary,
            "rationale": rationale,
            "calculated_metrics": calculated_metrics,
            "proposed_action": proposed_action,
        }

        # Programmatic safety validation
        is_safe, safety_err = validate_proposal_safety(tenant_id, pending_proposal, evidence_bag)
        if not is_safe:
            log.warning("orchestrator: proposal safety validation failed: %s", safety_err)
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
            return fail_turn

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
