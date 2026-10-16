from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable

from app.contracts import validate

SYNTHESIS_MAX_ATTEMPTS = 2
MCP_SCHEMA_NAME = "shared/contracts/mcp_envelope.schema.json"


class UnverifiableClaimException(Exception):
    pass


class ProtocolViolation(Exception):
    pass


def content_hash(excerpt: str, source_uri: str) -> str:
    digest = hashlib.sha256(f"{excerpt}\n{source_uri}".encode()).hexdigest()
    return f"sha256:{digest}"


def parse_mcp_tool_response(payload: dict) -> dict[str, dict]:
    """Parse MCP tool response matching shared/contracts/mcp_envelope.schema.json and return evidence bag."""
    validate(MCP_SCHEMA_NAME, payload)
    if not payload.get("ok"):
        return {}
    bag = {}
    for item in payload.get("evidence", []):
        bag[item["id"]] = item
    return bag


def records_from_mcp_response(payload: dict) -> list[str]:
    """Extract record IDs from an MCP tool response."""
    validate(MCP_SCHEMA_NAME, payload)
    if not payload.get("ok"):
        return []
    return [r["id"] for r in payload.get("records", [])]


def evidence_ids_from_tool_response(payload: dict) -> dict[str, dict]:
    """Backward-compatible alias for parse_mcp_tool_response."""
    return parse_mcp_tool_response(payload)


def validate_claims(
    answer: dict,
    evidence_ids: set[str] | dict,
    record_ids: set[str] | list[str] | None = None,
) -> None:
    """
    Two-phase validation check: verify every claim cites an ID in evidence_bag.keys().
    Enforces rule: LLM synthesis may ONLY cite evidence[].id, never records[].id.
    """
    try:
        validate("synthesis-answer", answer)
    except Exception as exc:
        raise UnverifiableClaimException("synthesis schema invalid") from exc

    valid_ids = set(evidence_ids.keys()) if isinstance(evidence_ids, dict) else set(evidence_ids)
    records = set(record_ids or [])

    for claim in answer.get("claims", []):
        cited = claim.get("cited_evidence_ids", [])
        if not cited:
            raise UnverifiableClaimException("empty cited_evidence_ids")
        for eid in cited:
            if records and eid in records:
                raise UnverifiableClaimException(
                    f"LLM synthesis may ONLY cite evidence[].id, never records[].id: cited '{eid}'"
                )
            if eid not in valid_ids:
                raise UnverifiableClaimException(
                    f"cited_evidence_id '{eid}' not in evidence_bag"
                )


def build_constrained_prompt(base_prompt: str, allowed_evidence_ids: list[str]) -> str:
    """Builds a constrained re-synthesis prompt restricting allowed IDs strictly to evidence_bag.keys()."""
    sorted_ids = sorted(allowed_evidence_ids)
    ids_str = ", ".join(f'"{i}"' for i in sorted_ids)
    return (
        f"{base_prompt}\n\n"
        f"CRITICAL CONSTRAINT: You may ONLY cite the following verified evidence IDs: [{ids_str}]. "
        f"Do NOT invent any evidence IDs. Do NOT cite record IDs. Every claim must have at least one valid cited evidence ID."
    )


@dataclass
class TwoPhaseSynthesisResult:
    status: str  # "COMPLETED" or "FAILED"
    answer: dict | None  # None if FAILED
    error: str | None  # "unverifiable_claim" if FAILED
    synthesis_traces: list[dict]
    attempts: int
    streamed: bool = False


class TwoPhaseEvidenceValidator:
    """
    Two-Phase Evidence Bag Validator:
    - Enforces: LLM synthesis may ONLY cite evidence[].id, never records[].id.
    - Two-phase validation: verify every claim in LLM output cites an ID in evidence_bag.keys().
    - If unknown/empty ID: catch UnverifiableClaimException, suppress streaming, execute EXACTLY ONE
      constrained re-synthesis prompt restricting allowed IDs strictly to evidence_bag.keys().
    - If attempt 2 fails: set status to FAILED with error unverifiable_claim (no answer body).
    """

    def __init__(
        self,
        evidence_bag: dict[str, dict],
        record_ids: set[str] | list[str] | None = None,
    ):
        self.evidence_bag = evidence_bag
        self.evidence_ids = set(evidence_bag.keys())
        self.record_ids = set(record_ids or [])

    def validate(self, answer: dict) -> None:
        validate_claims(answer, self.evidence_ids, self.record_ids)

    def execute(
        self,
        prompt: str,
        synthesize_fn: Callable[[str, list[str]], dict],
        stream_fn: Callable[[dict], None] | None = None,
    ) -> TwoPhaseSynthesisResult:
        traces: list[dict] = []
        allowed_ids = sorted(list(self.evidence_ids))

        # Phase 1: Attempt 1 - Streaming is suppressed to client
        raw_answer_1 = None
        try:
            raw_answer_1 = synthesize_fn(prompt, allowed_ids)
            self.validate(raw_answer_1)
            traces.append({"attempt": 1, "ok": True, "payload": raw_answer_1})
            if stream_fn:
                stream_fn(raw_answer_1)
            return TwoPhaseSynthesisResult(
                status="COMPLETED",
                answer=raw_answer_1,
                error=None,
                synthesis_traces=traces,
                attempts=1,
                streamed=bool(stream_fn),
            )
        except UnverifiableClaimException as exc:
            # Catch UnverifiableClaimException and suppress streaming
            traces.append({
                "attempt": 1,
                "ok": False,
                "payload": raw_answer_1 if isinstance(raw_answer_1, dict) else {"error": str(exc)},
            })

        # Phase 2: EXACTLY ONE constrained re-synthesis prompt
        constrained_prompt = build_constrained_prompt(prompt, allowed_ids)
        raw_answer_2 = None
        try:
            raw_answer_2 = synthesize_fn(constrained_prompt, allowed_ids)
            self.validate(raw_answer_2)
            traces.append({"attempt": 2, "ok": True, "payload": raw_answer_2})
            if stream_fn:
                stream_fn(raw_answer_2)
            return TwoPhaseSynthesisResult(
                status="COMPLETED",
                answer=raw_answer_2,
                error=None,
                synthesis_traces=traces,
                attempts=2,
                streamed=bool(stream_fn),
            )
        except UnverifiableClaimException as exc:
            traces.append({
                "attempt": 2,
                "ok": False,
                "payload": raw_answer_2 if isinstance(raw_answer_2, dict) else {"error": str(exc)},
            })
            # Second attempt fails: set status to FAILED with error unverifiable_claim (no answer body)
            return TwoPhaseSynthesisResult(
                status="FAILED",
                answer=None,
                error="unverifiable_claim",
                synthesis_traces=traces,
                attempts=2,
                streamed=False,
            )


def run_two_phase_validation(
    evidence_bag: dict[str, dict],
    prompt: str,
    synthesize_fn: Callable[[str, list[str]], dict],
    *,
    record_ids: set[str] | list[str] | None = None,
    stream_fn: Callable[[dict], None] | None = None,
) -> TwoPhaseSynthesisResult:
    validator = TwoPhaseEvidenceValidator(evidence_bag, record_ids)
    return validator.execute(prompt, synthesize_fn, stream_fn)


def synthesis_turn_status(
    *,
    attempt: int,
    unverifiable: bool,
    streamed_first: bool,
    retry_used_tools: bool,
) -> str:
    if streamed_first or (attempt > 1 and retry_used_tools):
        raise ProtocolViolation("retry path must not stream attempt 1 or call tools")
    if not unverifiable:
        return "COMPLETED"
    if attempt < SYNTHESIS_MAX_ATTEMPTS:
        return "RETRY"
    return "FAILED"
