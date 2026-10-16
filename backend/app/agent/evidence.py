from __future__ import annotations

import hashlib

from app.contracts import validate

SYNTHESIS_MAX_ATTEMPTS = 2


class UnverifiableClaimException(Exception):
    pass


def content_hash(excerpt: str, source_uri: str) -> str:
    digest = hashlib.sha256(f"{excerpt}\n{source_uri}".encode()).hexdigest()
    return f"sha256:{digest}"


def evidence_ids_from_tool_response(payload: dict) -> dict[str, dict]:
    validate("mcp-tool-response", payload)
    if not payload.get("ok"):
        return {}
    bag = {}
    for item in payload["evidence"]:
        bag[item["id"]] = item
    return bag


def validate_claims(answer: dict, evidence_ids: set[str]) -> None:
    try:
        validate("synthesis-answer", answer)
    except Exception as exc:
        raise UnverifiableClaimException("synthesis schema invalid") from exc
    for claim in answer["claims"]:
        cited = claim["cited_evidence_ids"]
        if not cited or any(eid not in evidence_ids for eid in cited):
            raise UnverifiableClaimException("cited_evidence_ids not in evidence_bag")


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


class ProtocolViolation(Exception):
    pass
