# Company Brain — Engineering Plan

> **Core requirement:** FalkorDB **v1.0.8** is the mandatory primary property-graph database. Do not replace it with Neo4j, a relational database, or a vector database. The v1 target is a single-node FalkorDB deployment supporting up to 50 concurrent active tenant requests; do not claim multi-master consensus, cross-region migration, or distributed sharding.

## 1. Product goal

Build an agent that understands how a company works by connecting people, teams, projects, documents, tickets, conversations, and decisions in one graph. The agent must answer questions and help users get work done across these sources.

The implementation must clearly satisfy all five required focus areas:

1. Knowledge from documents, tickets, and chats in one graph.
2. Who owns what, and who knows what.
3. Decisions traceable to their original sources.
4. Knowledge kept current as source data changes.
5. Answers supported by clear, inspectable citations.

## 2. Engineering principles

- **FalkorDB is the graph backbone.** Company entities, relationships, decision links, provenance links, and graph traversals live in FalkorDB.
- **Evidence nodes are mandatory.** Every extracted knowledge item that is surfaced as a fact must be traceable through an `Evidence` node to a `Source`. Preserve exact verbatim excerpts; summaries are never the sole evidence. A `Decision` must not be written unless it has at least one incoming `SUPPORTED_BY` relationship from validated evidence.
- **Build a modular monolith first.** Keep ingestion, graph access, agent orchestration, and API code in clear modules; do not introduce microservices prematurely.
- **Ground every answer.** The LLM interprets the question and chooses tools; retrieved graph records and source evidence provide the facts.
- **Prefer deterministic tools.** Use validated query templates and bounded traversals for common queries rather than allowing unrestricted model-generated Cypher.
- **Actions require authorization and concurrency checks.** Mutations require user confirmation, an idempotency key, a durable audit record, and proposal snapshot revalidation before execution.
- **Keep data access scoped.** Every read, write, search, graph traversal, and action must enforce tenant and object-level ACLs. Tenant graph selection is server-derived from the authenticated JWT, never client- or LLM-supplied.
- **Keep the model provider replaceable.** The graph and core retrieval path must not depend on a single LLM vendor.

## 3. Proposed architecture

```text
Web UI (chat, citations, graph explorer, actions)
                     |
                Backend API
                     |
       +-------------+--------------+
       |                            |
 Ingestion pipeline            Agent orchestrator
       |                            |
 normalize sources            choose validated tools
 extract entities             search / traverse graph
 resolve entities             retrieve evidence
 validate permissions         verify claims
       |                            |
       +-------------+--------------+
                     |
             FalkorDB graph
  entities, relationships, decisions, provenance
                     |
       Original source records / source storage
```

### Suggested stack

| Component | Initial choice | Notes |
|---|---|---|
| Graph database | **FalkorDB — required** | Primary graph store and graph query engine |
| Backend | Python + FastAPI | Fast iteration and data-processing ecosystem |
| Graph client | Official FalkorDB client compatible with the deployed version | Confirm current client APIs and supported Cypher features |
| Frontend | Next.js + TypeScript | Chat, citations, graph exploration |
| Agent tools | MCP-compatible tools | Standardized interface for graph search and approved actions |
| LLM | Configurable tool-calling model | Entity extraction, query interpretation, answer synthesis |
| Embeddings | Optional compatible embedding model | Add semantic retrieval only when useful |
| Source storage | Local files initially; object storage later if needed | Preserve original documents and excerpts |
| Tests | Pytest plus deterministic fixture dataset | Validate ingestion, queries, citations, permissions, and updates |

Redis is required for agent turn state and conversation history (two-hour TTL). Use a relational store for ingestion checkpoints and the append-only action audit log. Do not add a separate vector database in v1: FalkorDB is used as a property graph, with exact and full-text keyword search only. Vector-based hybrid search is explicitly deferred.

## 4. Graph schema, provenance, and temporal truth

### 4.1 Required node labels

| Label | Required / useful properties |
|---|---|
| `Person` | `id` (type-prefixed UUIDv7), `canonical_email`, `display_name`, `updated_at`, optional `needs_identity_link` |
| `Team` | `id`, `name`, `updated_at` |
| `Project` | `id`, `name`, `status`, `updated_at` |
| `Document` | `id`, `title`, `uri`, `updated_at`, optional `acl_scope` |
| `Ticket` | `id`, `external_id`, `title`, `status`, `updated_at`, optional `acl_scope` |
| `Message` | `id`, `channel`, `timestamp`, `uri`, optional `acl_scope` |
| `Decision` | `id`, `summary`, `updated_at`; must have validated evidence before commit |
| `Source` | `id`, `uri`, `source_type`, `content_hash` (SHA-256), `ingested_at` |
| `Evidence` | `id`, `excerpt`, `chunk_index`, `token_count`, `confidence`, `extractor_ver`, `valid_from`, `valid_to` |
| `Identity` | `composite_key` (`system:external_id`), `system`, `external_id` |

All node IDs are UUIDv7 strings with type prefixes, e.g. `doc_018f...`, `usr_018f...`. IDs must be unique within each tenant graph and generated to avoid cross-tenant collisions.

### 4.2 Structural relationships

Use typed relationships for the company model, including:

- `(:Person)-[:MEMBER_OF]->(:Team)`
- `(:Person)-[:OWNS]->(:Project)`
- `(:Person)-[:ASSIGNED_TO]->(:Ticket)`
- `(:Person)-[:AUTHORED]->(:Document)`
- `(:Person)-[:CREATED]->(:Ticket)`
- `(:Team)-[:RESPONSIBLE_FOR]->(:Project)`
- `(:Project)-[:HAS_TICKET]->(:Ticket)`
- `(:Project)-[:DEPENDS_ON]->(:Project)`
- `(:Decision)-[:RESOLVES]->(:Ticket)`
- `(:Project)-[:HAS_DECISION]->(:Decision)`
- `(:Decision)-[:RECORDED_IN]->(:Message|:Document|:Ticket)` where applicable
- `(:Person)-[:IDENTIFIED_AS]->(:Identity)`
- `(:Evidence)-[:PART_OF]->(:Source)`
- `(:Decision|:Project|:Ticket|:Person)-[:SUPPORTED_BY]->(:Evidence)`

**Structural edges do not store raw textual evidence.** Evidence is always modeled as an `Evidence` node linked to its `Source`; domain facts link to the relevant evidence through `SUPPORTED_BY`.

### 4.3 Mandatory provenance invariant

Every `Evidence` node must contain an exact verbatim excerpt (maximum 300 words) from the ingested source, its source reference, chunk metadata, extraction confidence/version, and temporal metadata. Validate the excerpt against the ingested source content and its SHA-256 content hash before writing.

A `Decision` node cannot be committed unless at least one incoming `SUPPORTED_BY` edge points to an `Evidence` node whose excerpt has passed validation. If extraction detects a decision but cannot produce a validating verbatim excerpt, reject the decision and its dependent write transaction. Do not keep unsupported decisions as partial graph facts.

### 4.4 Temporal edge model

All mutable relationships—including `OWNS`, `MEMBER_OF`, `ASSIGNED_TO`, and `HAS_STATUS` where status is modeled as an edge—must store:

- `valid_from`: epoch timestamp in milliseconds when the fact became true in the source system.
- `valid_to`: epoch timestamp in milliseconds when superseded; `NULL` means active.
- `ingested_at`: epoch timestamp in milliseconds when processed into FalkorDB.

Historical edges may remain, but only one active edge is allowed for each relationship scope. A project has at most one active `OWNS` edge. Relationship transitions must close the old active edge and create the replacement in one transaction. Distinguish the time a fact was true (`valid_from`/`valid_to`) from when the system learned it (`ingested_at`).

Illustrative ownership transition:

```cypher
MATCH (p:Project {id: $project_id})
OPTIONAL MATCH (old_owner:Person)-[old_rel:OWNS]->(p)
WHERE old_rel.valid_to IS NULL
SET old_rel.valid_to = $timestamp
WITH p
MATCH (new_owner:Person {id: $new_person_id})
CREATE (new_owner)-[:OWNS {
  valid_from: $timestamp,
  valid_to: null,
  ingested_at: timestamp()
}]->(p)
```

Run this as a single transaction. Add application-level validation and tests to prevent two active owner edges from being created concurrently.

### 4.5 Canonical identity resolution

Keep internal person identity separate from external provider identities:

```text
(:Person {id, canonical_email, display_name})
  -[:IDENTIFIED_AS]->(:Identity {system, external_id, composite_key})
```

Resolution hierarchy:

1. **Verified corporate email exact match:** automatically link when it matches exactly.
2. **Authenticated SSO GUID / HRIS foreign key exact match:** link only on an exact known mapping.
3. **Conservative fallback:** do not use fuzzy name matching or LLM-based identity reconciliation during automated ingestion. Create a separate `Person` identity and mark `needs_identity_link: true` for administrative review when the mapping is unresolved.

### 4.6 Schema bootstrap, constraints, and indexes

Pin the database engine to **FalkorDB v1.0.8** (Redis module or standalone binary). On creation of every tenant graph, run a versioned schema bootstrap **before ingestion or MCP tools are enabled**. The bootstrap must create uniqueness constraints for `Person.id`, `Project.id`, `Ticket.id`, `Document.id`, `Decision.id`, `Evidence.id`, `Source.id`, and `Identity.composite_key`; and traversal indexes for `Person.canonical_email`, `Source.uri`, `Source.content_hash`, `Ticket.external_id`, `Ticket.status`, `Evidence.valid_from`, and `Evidence.valid_to`.

Keep the exact v1.0.8-compatible constraint/index statements in version-controlled migration files and run an integration test against the pinned binary. Do not silently assume syntax from another graph database version is compatible. Identity `composite_key` is formed as `system + ":" + external_id`.

The intended bootstrap contract is equivalent to the following schema operations; verify the exact syntax against the pinned FalkorDB v1.0.8 binary in CI before enabling tenant ingestion:

```cypher
// Uniqueness constraints: idempotency enablers
CREATE CONSTRAINT ON (p:Person) ASSERT p.id IS UNIQUE;
CREATE CONSTRAINT ON (proj:Project) ASSERT proj.id IS UNIQUE;
CREATE CONSTRAINT ON (t:Ticket) ASSERT t.id IS UNIQUE;
CREATE CONSTRAINT ON (d:Document) ASSERT d.id IS UNIQUE;
CREATE CONSTRAINT ON (dec:Decision) ASSERT dec.id IS UNIQUE;
CREATE CONSTRAINT ON (e:Evidence) ASSERT e.id IS UNIQUE;
CREATE CONSTRAINT ON (s:Source) ASSERT s.id IS UNIQUE;
CREATE CONSTRAINT ON (i:Identity) ASSERT i.composite_key IS UNIQUE;

// Traversal / lookup indexes
CREATE INDEX ON :Person(canonical_email);
CREATE INDEX ON :Source(uri);
CREATE INDEX ON :Source(content_hash);
CREATE INDEX ON :Ticket(external_id);
CREATE INDEX ON :Ticket(status);
CREATE INDEX ON :Evidence(valid_from);
CREATE INDEX ON :Evidence(valid_to);
```

Treat bootstrap as a versioned, idempotent migration step and record its completion per tenant graph. If any required constraint or index fails, tenant initialization fails closed; do not start ingestion or expose MCP tools for that graph.

### 4.7 Relationship Cardinalities, Grounding Bounds & Failure Recovery
* **Cardinality Scopes:**
  * `OWNS`: Exactly 1 active edge per `Project` (`()-[OWNS]->(p:Project)`).
  * `ASSIGNED_TO`: Exactly 1 active edge per `Ticket` (`()-[ASSIGNED_TO]->(t:Ticket)`).
  * `MEMBER_OF`: Multi-active allowed per `Person`; mutations are targeted to specific `(:Person)-[MEMBER_OF]->(:Team)` pairs.
* **Evidence Invariant:** Minimum excerpt length `N = 30` characters. Excerpts `< 30` characters fail validation and abort the transaction.
* **Ingest Grain:** Atomic transaction per source document chunk / record. Never batch entire file drops into a single `GRAPH.QUERY`.
* **Constraint Failure Policy:** If `CALL db.constraints()` reports `FAILED` or anything other than `OPERATIONAL`, the tenant graph is write-locked (returns 503). Ingestion never runs on an unconstrained graph.
## 5. Ingestion pipeline


```text
Source files / exports / connectors
               |
        Normalize records
               |
      Extract entities and facts
               |
        Resolve entity identity
               |
      Attach provenance and time
               |
     Validate schema and permissions
               |
       Idempotent FalkorDB upserts
               |
      Update retrieval indexes
               |
       Record sync checkpoint
```

Implement the pipeline in this order:

1. **Source adapters:** initially support JSON, Markdown, and CSV exports. Add live integrations after the end-to-end workflow works.
2. **Normalization:** convert inputs into a common record format with stable IDs, timestamps, source URI, and version/hash.
3. **Extraction:** identify people, teams, projects, tickets, decisions, blockers, dependencies, and ownership.
4. **Entity resolution:** use stable IDs and conservative matching. Avoid merging people based only on similar names.
5. **Validation:** validate labels, properties, relationship types, tenant scope, and evidence references.
6. **Graph writes:** use idempotent upserts so re-ingestion does not create duplicate nodes or edges.
7. **Atomic record writes:** write each source document/record, its chunks, derived `Evidence` nodes, and associated relationships in one atomic FalkorDB transaction. Reject the transaction if evidence validation fails.
8. **Change handling:** on update, close superseded active edges by setting `valid_to`; retain historical nodes for audit. Implement explicit tombstones for hard deletion.
9. **Checkpoints:** store `(tenant_id, source_id, last_synced_hash, last_synced_at)` in an ingestion metadata table. Resume from checkpoints after failures.
10. **Reconciliation:** compare source records with graph state. If an export contains fewer records than before, mark candidates `missing_from_export` and queue verification; never mass-delete automatically.
11. **Deletion:** on a confirmed source tombstone, find and delete evidence connected to that source, delete dependent evidence-backed `Decision` nodes only when they have no remaining supporting evidence, and remove corresponding raw blobs from object storage. Follow applicable retention/compliance policy.
12. **Observability:** log source counts, extracted entities, evidence validation failures, rejected transactions, errors, sync checkpoints, and source freshness.

Preserve original records in source storage. Store source metadata and bounded evidence excerpts in the graph; link each `Evidence` node to its `Source` using `PART_OF`. Validate every excerpt against the source SHA-256 content hash. Use batch-buffered writes through the shared graph-core library for high-volume ingestion.

## 6. Agent and graph tools

Start with a small set of typed, testable tools exposed through an MCP-compatible interface where appropriate.

| Tool | Responsibility |
|---|---|
| `search_entities` | Find people, teams, projects, tickets, documents, and decisions |
| `get_entity_details` | Return validated properties and adjacent relationships |
| `traverse_relationships` | Perform bounded traversal over an allowlist of relationship types |
| `search_source_evidence` | Retrieve source excerpts and exact source references |
| `get_decision_history` | Return decisions, dates, and supporting evidence |
| `get_project_status` | Assemble owners, blockers, dependencies, and latest verified updates |
| `propose_action` | Prepare a ticket assignment or status update without executing it |
| `execute_action` | Execute a supported action only after authorization and confirmation |

Tool requirements:

- Validate all inputs and outputs with schemas.
- Restrict traversals by depth, result count, labels, and relationship types.
- Use parameterized queries or safe query construction.
- Do not give the model unrestricted write access to FalkorDB.
- Keep read tools read-only.
- Apply tenant and user authorization on every tool call.
- Return structured results with IDs, timestamps, and provenance.
- Log tool calls and errors without leaking sensitive source content.

### 6.1 Agent state machine and Redis session state

The MCP server is stateless and is the system of record only for graph I/O and external tool execution. The FastAPI backend plus Redis session store is the system of record for agent state and conversation history.

Store canonical turn state in Redis with a **two-hour TTL**. It must include:

- `session_id`, `turn_id`, server-resolved `tenant_graph`, and `acting_user_id`.
- `status`: `PLANNING`, `EXECUTING_TOOLS`, `AWAITING_CONFIRMATION`, `COMPLETED`, or `FAILED`.
- `working_set`: canonical `entity_ids` and `entity_types` resolved so far.
- `tool_trace`: step, tool name, arguments, result hash, and duration for each tool call.
- `evidence_bag`: evidence ID, source ID, exact excerpt, and URI.
- `pending_proposal`: proposal ID, action type, target entity IDs, snapshot state hash, and expiry time (15 minutes).

Canonical state shape (illustrative TypeScript interface):

```typescript
interface AgentTurnState {
  session_id: string;
  turn_id: string;
  tenant_graph: string;
  acting_user_id: string;
  status: 'PLANNING' | 'EXECUTING_TOOLS' | 'AWAITING_CONFIRMATION' | 'COMPLETED' | 'FAILED';
  working_set: {
    entity_ids: string[];
    entity_types: Record<string, string>;
  };
  tool_trace: Array<{
    step: number;
    tool_name: string;
    args: Record<string, unknown>;
    result_hash: string;
    duration_ms: number;
  }>;
  evidence_bag: Array<{
    evidence_id: string;
    source_id: string;
    excerpt: string;
    uri: string;
  }>;
  pending_proposal: {
    proposal_id: string;
    action_type: string;
    target_entity_ids: string[];
    snapshot_state_hash: string;
    expires_at: number;
  } | null;
}
```

Before executing a proposal, fetch the target entities' current `updated_at` values from FalkorDB. If their current-state hash differs from `snapshot_state_hash`, or the proposal is expired, reject execution with HTTP `409 Conflict` (`Stale Snapshot`). Never execute against stale proposal state.

### 6.2 MCP process model and shared graph core

Run the MCP server as a separate, long-lived Python or Node process using **Streamable HTTP with Server-Sent Events (SSE)**. FastAPI acts as an authenticated MCP client and pools its HTTP connections. The MCP server remains stateless.

Create a shared internal library named `engram-graph-core` containing all Cypher templates, schema/index definitions, validation rules, and safe graph-write helpers. Use it from both paths:

- **MCP server:** interactive agent tool operations, bounded graph reads, and authorized parameterized user actions.
- **Ingestion worker:** direct use of `engram-graph-core` for bulk, batch-buffered FalkorDB writes, avoiding MCP JSON-RPC overhead during large syncs while preserving the same validation and schema rules.

This is an intentional dual-writer architecture: both writers must use the same shared core and validation. No code path may bypass tenant resolution, evidence validation, temporal-edge handling, or idempotency rules.

### 6.3 Operational limits

Enforce limits in backend-controlled query templates, not just in prompts:

| Limit | v1 value | Failure behavior |
|---|---:|---|
| Traversal depth | 2 hops (`[*1..2]`) | Hard clamp in query template |
| Returned nodes | 50 per tool call | Sort by `updated_at DESC`; return `truncated: true` |
| Returned edges | 100 per tool call | Truncate lowest-weight/oldest edges; return `truncated: true` |
| FalkorDB query timeout | 2,500 ms | Cancel/stop execution where supported; return `ToolTimeoutError` |
| Agent tool rounds | 4 | Synthesize only from evidence already retrieved |
| MCP SSE request total | 10,000 ms | Abort turn and return `504 Gateway Timeout` |
| Concurrent active tenant requests | Up to 50 on single-node v1 target | Apply backpressure and report overload; do not claim horizontal graph scaling |

If FalkorDB is unavailable, abort the agent loop and show: **“Company Brain knowledge graph unavailable. Actions and queries paused to prevent desynchronization.”** The LLM must not answer from residual model knowledge when graph retrieval fails.

## 7. Query and answer flow

For each user question:

1. Authenticate the user and establish tenant/project scope.
2. Identify relevant entities and clarify ambiguity when necessary.
3. Retrieve current task/project context and use graph tools to find connected entities.
4. Traverse related tickets, documents, messages, decisions, owners, and dependencies.
5. Retrieve exact source excerpts for important claims.
6. Check timestamps, status, source reliability, and contradictions.
7. Generate an answer grounded in the retrieved evidence.
8. Attach citations to claims and distinguish evidence from inference.
9. Say when evidence is missing or conflicting instead of inventing an answer.
10. If an action is requested, propose it, validate permissions, obtain confirmation when required, execute through an authorized connector, and record the result.

Example question:

> “Why is the payments migration delayed, and who needs to act?”

Expected process: find the project; retrieve its owner and status; follow its ticket and dependency relationships; inspect recent source messages and decisions; verify the latest evidence; return the blocker, responsible person/team, next step, and citations.

## 8. Evidence bag binding and answer contract

Use a two-phase constrained generation protocol.

### Phase 1 — Fact retrieval

Agent tools retrieve verified excerpts from `Evidence` nodes and populate the turn's `evidence_bag` with `evidence_id`, `source_id`, exact `excerpt`, and source `uri`. The evidence bag is the only allowed factual grounding for final synthesis.

### Phase 2 — Structured synthesis

Require the LLM to produce a typed JSON object, not free-form claims with invented citations:

```json
{
  "summary": "High-level summary of the resolution...",
  "statements": [
    {
      "claim": "Sarah was assigned as the lead architect for Payments on August 15.",
      "cited_evidence_ids": ["evi_018f9e12a", "evi_018f9e12b"]
    }
  ]
}
```

The example is illustrative only. FastAPI validates the JSON before streaming it to the client. Every `cited_evidence_ids` value must exist in the preassembled evidence bag. If a statement cites an unknown ID, strip that statement or abort the turn with `UnverifiableClaimException`. Never allow the model to manufacture evidence IDs, URLs, or excerpts.

The UI should render each claim alongside source title/URI, timestamp, and exact excerpt. Show conflicts and dates when sources disagree. If the evidence bag does not support an answer, say so. If graph retrieval fails, do not fall back to the LLM's parametric knowledge.

## 9. Keeping the graph current

Implement:

- Stable source IDs and content hashes/version numbers.
- `created_at`, `updated_at`, `ingested_at`, and `last_synced_at` as applicable.
- Idempotent upserts.
- Incremental ingestion and periodic reconciliation.
- Explicit tombstones, archival, and access-revocation handling; retain superseded history, but hard-delete source-derived evidence and raw blobs when a verified compliance/source-deletion tombstone requires it.
- Validity intervals for changing ownership, status, and commitments.
- Source freshness indicators in the UI.
- Retry handling and resumable checkpoints for ingestion failures.

Do not assume that a source change has propagated until the graph update succeeds. Surface sync errors and stale status. If asynchronous indexing is introduced, track indexing state so retrieval can handle lag.

## 10. Graph routing, tenant isolation, and authorization

### 10.1 Tenant graph routing

Each tenant gets a separate FalkorDB graph. The graph key is:

```text
tenant_{sha256(tenant_uuid).substring(0, 16)}
```

Never accept `graph_name` from the API client or LLM. Backend middleware validates the authenticated JWT, resolves the verified `tenant_uuid`, computes the graph key, and binds it to request context. Use a central FalkorDB client pool, but explicitly select the server-injected graph for every query:

```python
graph = falkordb_client.select_graph(request_context.tenant_graph_name)
result = graph.query(parameterized_cypher, params)
```

All Cypher must be parameterized and drawn from reviewed templates. No cross-tenant traversal is permitted. Tenant routing must be applied to ingestion and MCP execution alike.

### 10.2 Service-boundary authentication

FastAPI authenticates to the MCP server using mutual TLS (mTLS) and passes a cryptographically signed contextual JWT containing:

- `tenant_id`
- `acting_user_id`
- `user_roles`
- `permitted_acl_scopes`, e.g. `team_payments` or `confidential_level_2`

The MCP server validates the signature, issuer/audience, expiry, and service identity before honoring the context. Do not trust unsigned context supplied in tool arguments.

### 10.3 Object-level ACLs

Restricted nodes carry `acl_scope` (for example, `channel_private_payments`). Every query template that can return protected data must apply the ACL predicate, e.g.:

```cypher
MATCH (n:Document {id: $doc_id})
WHERE n.acl_scope IS NULL OR n.acl_scope IN $user_acl_scopes
RETURN n
```

Apply equivalent authorization to related evidence, traversals, search results, citations, and action targets so a permitted node cannot leak a restricted neighbor's contents. ACL checks must be enforced in backend query construction, not in the prompt.

### 10.4 Graph Explorer parity

The frontend Graph Explorer must not run ad-hoc queries or connect directly to FalkorDB. It must use the same FastAPI endpoints and parameter-capped Cypher templates as MCP tools, enforcing identical tenant and ACL rules.

## 11. Frontend scope

Build three views:

### A. Ask Company Brain
- Chat input and streaming/normal response display.
- Answer with source citations and evidence excerpts.
- Related people, teams, projects, and decisions.
- Suggested follow-up questions.
- Clear “insufficient evidence” and “sources conflict” states.

### B. Graph explorer
- Interactive nodes and edges for people, teams, projects, documents, tickets, and decisions.
- Click a node to inspect properties, connected entities, and provenance.
- Show relationship direction and relevant timestamps.
- Avoid rendering the entire graph at once; explore a bounded neighborhood around a selected entity.

### C. Company activity and actions
- Project owners, status, blockers, dependencies, and recent changes.
- Last-synced status for source systems.
- Proposed action, confirmation, execution result, and audit history.

Prioritize the chat-and-evidence experience first. The graph explorer should help users verify the reasoning rather than become a decorative visualization.

## 12. Action idempotency and audit architecture

Every user-confirmed action must include an `idempotency_key` (UUIDv7 generated when the proposal is created). Store action execution in an append-only relational `action_audit_log` table:

```sql
CREATE TABLE action_audit_log (
  idempotency_key UUID PRIMARY KEY,
  tenant_id VARCHAR(64) NOT NULL,
  user_id VARCHAR(64) NOT NULL,
  action_type VARCHAR(64) NOT NULL,
  payload JSONB NOT NULL,
  status VARCHAR(32) NOT NULL, -- PENDING, COMMITTED, FAILED
  external_system_tx_id VARCHAR(128),
  executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

Use a two-phase action commit:

1. Insert the audit row as `PENDING`. If the idempotency key already exists, return the existing execution receipt instead of repeating the mutation.
2. Revalidate proposal expiry and snapshot hash against current FalkorDB `updated_at` values; reject stale proposals with `409 Conflict`.
3. Execute the authorized external mutation (for example, assign a Linear ticket) only after required user confirmation.
4. Update FalkorDB to reflect the confirmed result, using the same shared `engram-graph-core` validation/write helpers.
5. Mark the audit record `COMMITTED`; record failures as `FAILED` with safe diagnostic details.

Actions must be scoped to an allowlist, auditable, and safe to retry. Never claim an external mutation succeeded until the external system confirms it.

## 13. Evaluation plan


Create a fictional company dataset with an initial target of:

- 30–50 people.
- 5–8 teams.
- 8–12 projects.
- A few hundred linked records across documents, chats, tickets, and decisions.
- 20–30 evaluation questions with known answers and source IDs.

Include multi-hop questions, changed ownership, stale records, conflicting sources, missing evidence, and permission boundaries.

Measure:

- Entity-resolution accuracy.
- Retrieval precision/recall for relevant records.
- Citation correctness and support for each claim.
- Multi-hop relationship correctness.
- Stale-fact error rate.
- Appropriate abstention when evidence is insufficient.
- Ingestion idempotency and recovery.
- Action authorization and success reporting.
- Query latency and ingestion reliability.

Use deterministic expected answers and source IDs so results can be evaluated repeatedly. A smaller dataset with reliable evidence is better for the initial demo than a huge dataset with unknown correctness.

## 14. Implementation roadmap

### Phase 1 — Foundation
- Create repository structure and environment configuration.
- Run the pinned FalkorDB v1.0.8 locally.
- Implement per-tenant graph routing, mandatory schema bootstrap, uniqueness constraints/indexes, and the shared `engram-graph-core` library.
- Configure Redis for agent turn state and the relational metadata/audit tables.
- Prepare a small connected test dataset.
- Verify core graph queries and entity identity.

**Exit criterion:** FalkorDB contains connected entities and relationships that can be inspected and queried.

### Phase 2 — Ingestion
- Implement source normalization and adapters.
- Extract entities and relationships; reject decisions without hash-validated verbatim evidence.
- Resolve identities using exact verified email/SSO/HRIS mappings only.
- Write each record and its Evidence/relationship data atomically through `engram-graph-core`.
- Implement temporal edge transitions, idempotent writes, checkpoints, tombstones, and export-drift verification.
- Test updates, deletions, and reruns.

**Exit criterion:** re-ingesting the same dataset does not create duplicates, and source changes update graph state correctly.

### Phase 3 — Retrieval tools
- Implement the typed tools in Section 6.
- Add bounded traversal templates and source-evidence lookup.
- Enforce permissions and query limits.
- Test multi-hop retrieval independently of the LLM.

**Exit criterion:** the backend can answer the core graph questions deterministically.

### Phase 4 — Grounded agent
- Add LLM tool selection and orchestration.
- Implement claim-to-evidence mapping.
- Add conflict handling and abstention.
- Build the evaluation harness.

**Exit criterion:** questions spanning multiple source types receive grounded answers with correct citations.

### Phase 5 — UI and controlled action
- Build chat, citations, graph explorer, and project view.
- Add one allowlisted action such as assigning a ticket.
- Add proposal expiry/snapshot revalidation, confirmation, UUIDv7 idempotency keys, and append-only relational audit logging.

**Exit criterion:** an end-to-end demo shows a question, graph-backed reasoning, source evidence, and a safely executed or clearly simulated action.

### Phase 6 — Polish and reliability
- Fix evaluation failures.
- Test tenant isolation and stale data.
- Add error states, loading states, and sync visibility.
- Prepare repeatable demo scenarios.

**Exit criterion:** the demo is reproducible, source-grounded, and handles uncertainty honestly.

## 15. Suggested repository layout

```text
company-brain/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── config/
│   │   ├── graph/
│   │   │   ├── client.py
│   │   │   ├── tenant_routing.py
│   │   │   ├── schema.py
│   │   │   ├── queries.py
│   │   │   └── migrations/
│   │   ├── engram_graph_core/  # Shared library/package used by MCP + ingestion
│   │   ├── ingestion/
│   │   │   ├── adapters/
│   │   │   ├── normalize.py
│   │   │   ├── extract.py
│   │   │   ├── resolve_entities.py
│   │   │   └── sync.py
│   │   ├── agent/
│   │   │   ├── orchestrator.py
│   │   │   ├── state.py
│   │   │   ├── tools.py
│   │   │   ├── evidence.py
│   │   │   └── prompts.py
│   │   ├── mcp_server/          # Separate stateless Streamable HTTP + SSE process
│   │   ├── security/
│   │   ├── audit/
│   │   └── main.py
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   └── ...
├── data/
│   ├── fixtures/
│   └── README.md
├── evals/
│   ├── questions.jsonl
│   └── README.md
├── docker-compose.yml          # FalkorDB v1.0.8 + Redis + relational DB
├── .env.example
└── README.md
```

This is a suggested starting layout; adjust it to the team's chosen frameworks without weakening the module boundaries.

## 16. Scope boundaries and explicit non-claims for v1

The first version deliberately does **not** claim the following capabilities:

- **No unsupervised expertise extraction:** v1 identifies explicit ownership, authorship, assignment, and resolution relationships (`OWNS`, `AUTHORED`, `ASSIGNED_TO`, `RESOLVES`). It does not infer implicit employee competency or “knowledge scores” from unstructured chats.
- **No vector embeddings in the graph:** FalkorDB is a property graph for v1. Search uses exact IDs/fields and full-text keyword indexes over fields such as `id`, `name`, and `title`. Vector-based hybrid search is deferred.
- **No distributed database guarantees:** the target is one FalkorDB node and up to 50 concurrent active tenant requests. No multi-master consensus, automatic cross-region shard migration, or distributed scaling claim.
- **No LLM-only degraded mode:** if FalkorDB returns a connection error, abort the agent loop, show the graph-unavailable banner, and pause actions/queries to prevent desynchronization. The LLM must not generate a factual answer from residual model weights.
- **No fuzzy identity merging:** automated identity resolution uses verified exact keys only; ambiguous identities require administrative review.
- **No unsupported decisions:** a decision without validated verbatim evidence is rejected rather than stored as a graph fact.


Additional v1 exclusions:

- Full autonomous agent swarms.
- Every possible live source connector; start with fixture/export adapters and add integrations incrementally.
- Unrestricted generated graph queries.
- Automatic irreversible actions.
- Advanced organizational prediction or simulation.
- Premature distributed infrastructure beyond the explicitly required FastAPI, stateless MCP process, ingestion worker, Redis state store, relational metadata/audit store, and single-node FalkorDB.

## 17. Final engineering priorities

Implement in this order:

**Graph schema → ingestion → entity resolution and provenance → graph queries → evidence retrieval → grounded agent → citations → controlled action → polished UI.**

The core deliverable is not merely a chatbot or a graph visualization. It is a company knowledge system whose facts are connected in **FalkorDB**, whose answers can be traced to source evidence, and whose knowledge stays current as company data changes.