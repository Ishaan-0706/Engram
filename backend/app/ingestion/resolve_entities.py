from __future__ import annotations

import uuid
from typing import Any

from engram_graph_core.store import GraphStore

from app.ingestion.models import ExtractedBatch, PersonRef

_NS = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")


def _person_id(ref: PersonRef) -> str:
    if ref.canonical_email:
        key = ref.canonical_email.strip().lower()
    elif ref.identity_key:
        key = ref.identity_key.strip()
    else:
        key = "unresolved:" + (ref.source_local_id or ref.name or "unknown")
    return "usr_" + str(uuid.uuid5(_NS, key))


def resolve_person(ref: PersonRef, store: GraphStore) -> dict[str, Any]:
    email = ref.canonical_email.strip().lower() if ref.canonical_email else None
    identity_key = ref.identity_key.strip() if ref.identity_key else None
    if email:
        found = store.find_person_by_email(email)
        if found:
            if identity_key:
                _link_identity(store, found["id"], identity_key)
            return found
    if identity_key:
        found = store.find_person_by_identity(identity_key)
        if found:
            return found
    needs_link = not email and not identity_key
    person_id = _person_id(ref)
    props: dict[str, Any] = {
        "id": person_id,
        "display_name": ref.name or email or identity_key or person_id,
        "needs_identity_link": needs_link,
    }
    if email:
        props["canonical_email"] = email
    if ref.role:
        props["role"] = ref.role
    store.merge_node("Person", person_id, props)
    if identity_key:
        _link_identity(store, person_id, identity_key)
    return store.get_node("Person", person_id) or props


def _link_identity(store: GraphStore, person_id: str, identity_key: str) -> None:
    system, _, external_id = identity_key.partition(":")
    store.merge_node(
        "Identity",
        identity_key,
        {
            "id": identity_key,
            "key": identity_key,
            "composite_key": identity_key,
            "system": system or "unknown",
            "external_id": external_id or identity_key,
            "person_id": person_id,
        },
    )
    store.merge_edge("HAS_IDENTITY", "Person", person_id, "Identity", identity_key)


def resolve_batch(batch: ExtractedBatch, store: GraphStore) -> dict[str, str]:
    """Map person refs (email:/id:/raw) to Person.id. Never fuzzy-matches names."""
    resolved: dict[str, str] = {}
    for ref in batch.people:
        person = resolve_person(ref, store)
        pid = person["id"]
        if ref.canonical_email:
            resolved[f"email:{ref.canonical_email.strip().lower()}"] = pid
        if ref.identity_key:
            resolved[f"idkey:{ref.identity_key.strip()}"] = pid
        if ref.source_local_id:
            resolved[ref.source_local_id] = pid
        resolved[pid] = pid
    return resolved
