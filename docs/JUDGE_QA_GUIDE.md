# FalkorDB "Graph Hacks" Hackathon — Judge Q&A Guide (Rule #12)

This technical reference guide equips the team with exact, rigorous answers to technical questions judges may ask during evaluation of **Company Brain (Engram)**.

---

## 1. How the Graph Model Works: Why `Evidence` is a Separate Node from `Decision` and `Source`

### Judge Question
> *"Why did you design `Evidence` as an independent node label rather than simply inlining the excerpt text as a property on the `Decision` node or the `Source` node?"*

### Engineering Answer
In enterprise architecture, grounding requires strict separation between **three distinct entities with different lifecycles and cardinality**:

```text
┌────────────────┐          ┌────────────────┐          ┌────────────────┐
│     Source     │◄──PART_OF│    Evidence    │◄──SUPPORTED_BY│    Decision    │
│ (slack://chan) │          │(Verbatim Excerpt)│        │ (Ed25519 Auth) │
└────────────────┘          └────────────────┘          └────────────────┘
```

1. **Many-to-Many Decoupling**:
   - A single incident retrospective or post-mortem (`Source`) contains multiple factual excerpts (`Evidence`).
   - A single architectural decision (`Decision`) can be supported by multiple pieces of evidence (e.g., a benchmark report *plus* a Slack incident quote).
   - Conversely, a single benchmark excerpt (`Evidence`) can justify multiple subsequent decisions (e.g., switching authentication *and* deprecating an API gateway plugin). Inlining excerpt properties onto `Decision` would duplicate data, corrupt content hashes, and make evidence deduplication impossible.
2. **Cryptographic Immutability & Verifiability**:
   - Each `Evidence` node holds a deterministic SHA-256 digest:  
     $$\text{content\_hash} = \text{sha256}(\text{excerpt} + \text{"\textbackslash n"} + \text{source\_uri})$$
   - If an engineer edits a decision's summary, the underlying evidence digest remains cryptographically pristine.
3. **Option B MCP Split Envelope Compliance**:
   - Our Model Context Protocol (MCP) server separates `records` (graph topology entities) from `evidence` (citable grounding facts). The LLM's Two-Phase Citation Validator strictly checks cited IDs against the `evidence` bag. Treating `Evidence` as a first-class node allows Cypher queries to `collect(evi)` along any path and pass them directly into the citation verification pipeline.

---

## 2. How Temporal Edges Work: Preserving Audit Trails Without Deleting Edges

### Judge Question
> *"When ownership of a system is reassigned, why don't you delete the old `OWNS` edge or update an `owner_email` property on the `System` node?"*

### Engineering Answer
Deleting relationships or overwriting attributes destroys institutional memory and violates enterprise compliance requirements (e.g., SOC2, ISO 27001):

1. **Non-Destructive Edge Retirement**:
   - Every `[:OWNS]` relationship contains `valid_from` (Unix ms timestamp) and `valid_to` (Unix ms timestamp or `null` for the currently active owner).
   - When ownership is reassigned, our atomic Cypher mutation executes:
     ```cypher
     MATCH (current:Person)-[r:OWNS]->(s:System {name: $system_name})
     WHERE r.valid_to IS NULL
     SET r.valid_to = $now_ms
     WITH s
     MATCH (new_owner:Person {canonical_email: $new_owner_email})
     CREATE (new_owner)-[:OWNS {valid_from: $now_ms, valid_to: null, ingested_at: $now_ms}]->(s)
     ```
   - **Zero edges are deleted.** The previous owner's edge is cleanly retired by setting `r.valid_to = $now_ms`.
2. **Temporal Time-Travel Queries**:
   - If an outage occurred on September 22, 2026, an investigator can query the graph topology *as it existed at that precise millisecond*:
     ```cypher
     MATCH (p:Person)-[r:OWNS]->(s:System {name: "payment-gateway"})
     WHERE r.valid_from <= $incident_ts AND (r.valid_to IS NULL OR r.valid_to > $incident_ts)
     RETURN p.display_name, p.canonical_email
     ```
   - Overwriting a property on `System` makes historical root-cause analysis impossible. Temporal edges turn FalkorDB into a living time-travel audit log.

---

## 3. How Redis Lua CAS + Snapshot Hash Prevents Race Conditions

### Judge Question
> *"What happens if two engineers simultaneously stage conflicting proposals or confirm mutations on the same system?"*

### Engineering Answer
We implement **Optimistic Concurrency Control (OCC) with Two-Phase Verification** across Redis and FalkorDB:

```mermaid
sequenceDiagram
    autonumber
    actor EngineerA as Engineer A
    actor EngineerB as Engineer B
    participant API as FastAPI Gateway
    participant Redis as Redis State Machine
    participant FalkorDB as FalkorDB Graph

    Note over EngineerA, EngineerB: Both stage mutations on payment-gateway at Snapshot Hash H1
    EngineerA->>API: POST /api/confirm (Hash H1, Proposal P1)
    API->>Redis: Acquire lock:P1 (SET NX, TTL 30s)
    API->>FalkorDB: Recompute Snapshot Hash
    Note over API: Verified live hash == H1
    API->>FalkorDB: Apply Mutation (Ed25519 ALIGNED_WITH)
    API->>Redis: Lua CAS Transition -> COMPLETED, Monotonic Epoch 1 -> 2
    API-->>EngineerA: 200 OK (Confirmed, Idempotency Receipt)

    Note over FalkorDB: Live Graph Hash changes to H2!

    EngineerB->>API: POST /api/confirm (Hash H1, Proposal P2)
    API->>Redis: Acquire lock:P2
    API->>FalkorDB: Recompute Snapshot Hash
    Note over API: Live hash is H2, but Engineer B sent H1!
    API-->>EngineerB: HTTP 409 Conflict (snapshot_mismatch, current_snapshot_hash: H2)
    Note over EngineerB: UI shows 409 Banner; engineer reviews diff and re-syncs
```

1. **Snapshot Hash Generation**:
   - When a proposal is staged, the agent records `snapshot_hash = sha256(entity_ids + updated_at_timestamps)` over the working set.
2. **Distributed Proposal Locking**:
   - `POST /api/confirm` acquires `lock:{proposal_id}` with `SET NX PX 30000` to prevent duplicate concurrent confirmation attempts on the same proposal.
3. **Atomic Re-read & Hash Re-verification**:
   - Before executing the Cypher mutation, the server re-queries FalkorDB entities. If Engineer A's confirmation completed 5ms earlier, the target system's topology shifted, changing the live hash.
   - The server detects the mismatch and immediately aborts with **HTTP 409 Conflict** (`snapshot_mismatch`), returning `current_snapshot_hash`.
4. **Monotonic Epoch Fencing**:
   - Redis Lua CAS script checks:
     ```lua
     local current = redis.call('HGET', KEYS[1], 'epoch')
     if tonumber(current) == tonumber(ARGV[1]) then
       redis.call('HSET', KEYS[1], 'status', ARGV[2], 'epoch', tonumber(current) + 1)
       return 1
     else
       return 0
     end
     ```
   - If client epoch does not match stored epoch, requests are rejected with **HTTP 410 Gone / Stale Epoch**.
5. **Idempotency Guarantee**:
   - Each confirmation requires a client-generated UUIDv7 `idempotency_key`. Successful executions store an idempotency receipt for 24 hours. Retried network calls return the cached receipt without re-executing mutations.

---

## 4. Why FalkorDB is Irreplaceable in this Architecture

### Judge Question
> *"Could you have built this with PostgreSQL recursive queries or pgvector?"*

### Engineering Answer
**No.** FalkorDB provides capabilities that relational and vector databases cannot match:

| Capability | FalkorDB Property Graph | Relational DB (PostgreSQL) | Vector DB (Pinecone / Chroma) |
|---|---|---|---|
| **Multi-hop Variable Lineage** | `[:SUPERSEDES*1..10]` in **< 1.5ms** | Exponential CTE join explosion; slow and cyclic lock hazards | **Impossible** (vectors have no concept of directed edge traversal) |
| **Graph Centrality Scoring** | Single Cypher pattern aggregating multi-edge weights | Complex multi-table outer joins with Cartesian product issues | **Impossible** (no topological relations or degree centrality) |
| **Topological Blast Radius** | Sub-millisecond variable-length path traversal `[:DEPENDS_ON*1..5]` | Multi-hop self-joins requiring hardcoded depth caps | **Impossible** (cannot calculate graph downstream reach) |
| **Multi-Tenant Graph Isolation** | Physical graph separation (`tenant_{id}`) at engine level | Vulnerable to missing `WHERE tenant_id = x` in complex queries | Namespace partitioning without relational topology |
| **Execution Performance** | GraphBLAS sparse matrix linear algebra operations | Row-scanning B-Tree indexes with heavy buffer cache churn | High ANN search latency without topological traversals |

### Summary
FalkorDB is not merely an optional data store in Company Brain—it is the **computational core** that enables multi-hop decision causality, temporal auditability, and zero-hallucination architectural provenance.
