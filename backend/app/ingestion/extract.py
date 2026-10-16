from __future__ import annotations

from typing import Any

from app.ingestion.models import (
    MAX_EXCERPT_WORDS,
    MIN_EXCERPT_CHARS,
    DecisionDraft,
    EdgeDraft,
    EvidenceDraft,
    ExtractedBatch,
    LoadedSource,
    PersonRef,
)
from app.ingestion.validate import find_span


def _get(row: dict[str, Any], *names: str) -> str | None:
    lower = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        value = lower.get(name.lower())
        if value is None or value == "":
            continue
        return str(value).strip()
    return None


def _chunks(text: str) -> list[EvidenceDraft]:
    words: list[tuple[str, int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        start = i
        while i < n and not text[i].isspace():
            i += 1
        words.append((text[start:i], start, i))
    drafts: list[EvidenceDraft] = []
    idx = 0
    cursor = 0
    while cursor < len(words):
        take = min(MAX_EXCERPT_WORDS, len(words) - cursor)
        start = words[cursor][1]
        end = words[cursor + take - 1][2]
        excerpt = text[start:end]
        if len(excerpt) >= MIN_EXCERPT_CHARS:
            drafts.append(
                EvidenceDraft(
                    excerpt=excerpt,
                    start_offset=start,
                    end_offset=end,
                    chunk_index=idx,
                    token_count=take,
                )
            )
            idx += 1
        cursor += take
    return drafts


def _person_from_mapping(item: dict[str, Any]) -> PersonRef:
    return PersonRef(
        name=_get(item, "name", "display_name"),
        canonical_email=_get(item, "canonical_email", "email"),
        identity_key=_get(item, "identity_key", "identity"),
        role=_get(item, "role"),
        source_local_id=_get(item, "id", "person_id"),
    )


def extract(source: LoadedSource) -> ExtractedBatch:
    payload = source.payload
    batch = ExtractedBatch(source=source, evidence=_chunks(source.text))

    for item in payload.get("people") or []:
        if isinstance(item, dict):
            batch.people.append(_person_from_mapping(item))

    for item in payload.get("teams") or []:
        if isinstance(item, dict):
            team_id = _get(item, "id")
            if team_id:
                batch.teams.append({"id": team_id, "name": _get(item, "name") or team_id})

    for item in payload.get("projects") or []:
        if not isinstance(item, dict):
            continue
        project_id = _get(item, "id")
        if not project_id:
            continue
        batch.projects.append(
            {
                "id": project_id,
                "name": _get(item, "name") or project_id,
                "status": _get(item, "status") or "unknown",
            }
        )
        owner_email = _get(item, "owner_email", "owner")
        if owner_email:
            batch.people.append(PersonRef(canonical_email=owner_email, source_local_id=owner_email))
            batch.edges.append(
                EdgeDraft(
                    rel_type="OWNS",
                    from_label="Person",
                    from_ref=f"email:{owner_email.lower()}",
                    to_label="Project",
                    to_id=project_id,
                    temporal=True,
                )
            )

    for item in payload.get("tickets") or []:
        if not isinstance(item, dict):
            continue
        ticket_id = _get(item, "id", "ticket_id")
        if not ticket_id:
            continue
        title = _get(item, "title") or ticket_id
        body = _get(item, "description", "body", "excerpt") or ""
        batch.tickets.append(
            {
                "id": ticket_id,
                "title": title,
                "status": _get(item, "status") or "open",
                "priority": _get(item, "priority"),
                "external_id": _get(item, "external_id") or ticket_id,
            }
        )
        project_id = _get(item, "project_id")
        if project_id:
            batch.edges.append(
                EdgeDraft(
                    rel_type="HAS_TICKET",
                    from_label="Project",
                    from_ref=project_id,
                    to_label="Ticket",
                    to_id=ticket_id,
                )
            )
        assignee = _get(item, "assignee_email", "assignee")
        if assignee:
            batch.people.append(PersonRef(canonical_email=assignee, source_local_id=assignee))
            batch.edges.append(
                EdgeDraft(
                    rel_type="ASSIGNED_TO",
                    from_label="Person",
                    from_ref=f"email:{assignee.lower()}",
                    to_label="Ticket",
                    to_id=ticket_id,
                    temporal=True,
                )
            )
        if body and find_span(source.text, body):
            span = find_span(source.text, body)
            assert span is not None
            batch.evidence.append(
                EvidenceDraft(
                    excerpt=body,
                    start_offset=span[0],
                    end_offset=span[1],
                    chunk_index=len(batch.evidence),
                    token_count=len(body.split()),
                    derived_from_label="Ticket",
                    derived_from_id=ticket_id,
                )
            )

    docs = payload.get("documents") or []
    if payload.get("body") and not docs:
        docs = [
            {
                "id": payload.get("document_id") or source.external_id,
                "title": payload.get("title") or source.external_id,
                "body": payload.get("body"),
            }
        ]
    for item in docs:
        if not isinstance(item, dict):
            continue
        doc_id = _get(item, "id") or source.external_id
        batch.documents.append({"id": doc_id, "title": _get(item, "title") or doc_id})
        author = _get(item, "author_email", "author")
        if author:
            batch.people.append(PersonRef(canonical_email=author, source_local_id=author))
            batch.edges.append(
                EdgeDraft(
                    rel_type="AUTHORED",
                    from_label="Person",
                    from_ref=f"email:{author.lower()}",
                    to_label="Document",
                    to_id=doc_id,
                )
            )

    for item in payload.get("decisions") or []:
        if not isinstance(item, dict):
            continue
        excerpt = _get(item, "excerpt") or ""
        local_id = _get(item, "id") or excerpt[:32]
        batch.decisions.append(
            DecisionDraft(
                local_id=local_id,
                summary=_get(item, "summary") or excerpt[:120],
                timestamp=_get(item, "timestamp"),
                status=_get(item, "status") or "recorded",
                excerpt=excerpt,
                project_id=_get(item, "project_id"),
            )
        )

    for item in payload.get("memberships") or []:
        if not isinstance(item, dict):
            continue
        email = _get(item, "canonical_email", "email")
        team_id = _get(item, "team_id")
        if email and team_id:
            batch.people.append(PersonRef(canonical_email=email, source_local_id=email))
            batch.edges.append(
                EdgeDraft(
                    rel_type="MEMBER_OF",
                    from_label="Person",
                    from_ref=f"email:{email.lower()}",
                    to_label="Team",
                    to_id=team_id,
                    temporal=True,
                )
            )

    return batch
