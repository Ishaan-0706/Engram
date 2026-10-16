# AgentTurnState protocol (Developer 1 / Developer 2 handshake)

Schemas in this directory are the contract. Validate fixtures against them before writing Redis or FastAPI wiring. FalkorDB stays the company graph; Redis holds turn/session state only.

## JWT → graph key

| Claim | Required | Meaning |
| --- | --- | --- |
| `tid` | yes | Tenant id. Graph key is `tenant:{tid}`. |
| `sub` | yes | User id. Stored on the turn blob as `user_id`. |
| `org_id` | no | Ignored. Do not use it for graph selection. |

Missing `tid` or `sub` → 401. Do not trust client-supplied tenant ids.

## Redis keys

| Key | TTL | Notes |
| --- | --- | --- |
| `turn:{turn_id}` | 7200s | JSON blob (`agent-turn-state.schema.json`). Expiry = 410 `turn_gone`. Never resurrect. |
| `lock:{proposal_id}` | 30s | `SET NX`. Shorter than turn TTL. |
| `idempotency:{idempotency_key}` | 7200s | `in_progress` then receipt. Write `in_progress` **before** the external action. |

Heartbeat (if used): `EXPIRE turn:{turn_id} 7200` only. Must not increment `epoch`.

## Fence

Every status write is compare-and-set: `if epoch == expected: epoch += 1; apply mutation else reject`.

`POST /resume` must send the last-known epoch. Wrong epoch or missing key → 410 and a new `turn_id`. Resume does not replay tools and does not invent an evidence bag.

Late workers with a stale epoch are dropped. Partial `EXECUTING_TOOLS` bags stay as written.

Allowed status edges:

```
PLANNING → EXECUTING_TOOLS → AWAITING_CONFIRMATION → COMPLETED
                           → COMPLETED
                           → FAILED
AWAITING_CONFIRMATION → FAILED   (execute crash)
```

## MCP tool responses

See `mcp-tool-response.schema.json`.

- Cite **only** `evidence[].id`. Record ids are not evidence.
- Developer 1 mints `evidence[].id` (`ev_` + UUIDv7). One missing `id` or `record_id` fails the whole tool call.
- Facts only in `records` are uncitable.
- `ok: false` has `{error: {code, message}}` and **no** `evidence` array. Do not insert error strings into the bag.
- `content_hash` = `sha256:` + hex(sha256(utf-8(`excerpt + "\n" + source_uri`))).
- Snapshot hash for actions is computed by Developer 2 from a FalkorDB re-read, not copied from MCP.

## Synthesis / UnverifiableClaimException

See `synthesis-answer.schema.json`.

- Max 2 attempts. Attempt 1 is never streamed. Retry path: no tool calls; allowed ids = `evidence_bag` keys only.
- Empty `cited_evidence_ids` or any id not in the bag → `UnverifiableClaimException`.
- Attempt 2 still failing → status `FAILED`, `fail_reason=unverifiable_claim`, keep bag + both traces until TTL. No answer body.

## Confirm / stale snapshot

See `action-confirm.schema.json`.

1. Missing turn → 410 `turn_gone`.
2. Request epoch ≠ blob epoch → 409 `stale_fence`.
3. Status ≠ `AWAITING_CONFIRMATION` → 409 `stale_fence`.
4. Existing **receipt** for this UUIDv7 → return it (200), even if the hash would now mismatch.
5. `SET lock:{proposal_id} NX`. Loser: wait; same key → receipt or 409 `conflict_in_progress`; different key → 409 `conflict_in_progress`.
6. Winner writes `idempotency:{key} = in_progress`, re-reads graph, recomputes hash.
7. Hash mismatch → 409 `snapshot_mismatch` with `current_snapshot_hash` and current `epoch`. Proposal stays `AWAITING_CONFIRMATION`. Release the lock. Client retries same `proposal_id` with the new hash.
8. Hash match → execute, write receipt, fence-CAS to `COMPLETED`.
9. Winner crash after lock, before receipt: lock expires; retry with the **same** UUIDv7 may run once. `in_progress` is the duplicate-execute fence: do not execute if that key is already `in_progress` or `completed`.
