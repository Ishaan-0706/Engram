Company Brain — Engineering Plan
Core requirement: FalkorDB is mandatory and is the central graph database for the Company Brain. Do not replace it with Neo4j, a relational database, or a vector database as the primary knowledge graph.

1. Product goal
Build an agent that understands how a company works by connecting people, teams, projects, documents, tickets, conversations, and decisions in one graph. The agent must answer questions and help users get work done across these sources.
The implementation must clearly satisfy all five required focus areas:
1. Knowledge from documents, tickets, and chats in one graph.
2. Who owns what, and who knows what.
3. Decisions traceable to their original sources.
4. Knowledge kept current as source data changes.
5. Answers supported by clear, inspectable citations.
2. Engineering principles
- FalkorDB is the graph backbone. Company entities, relationships, decision links, provenance links, and graph traversals live in FalkorDB.
- Sources remain the evidence. Preserve source IDs, URLs, timestamps, versions, and relevant excerpts. Do not make generated summaries the sole evidence.
- Build a modular monolith first. Keep ingestion, graph access, agent orchestration, and API code in clear modules; do not introduce microservices prematurely.
- Ground every answer. The LLM interprets the question and chooses tools; retrieved graph records and source evidence provide the facts.
- Prefer deterministic tools. Use validated query templates and bounded traversals for common queries rather than allowing unrestricted model-generated Cypher.
- Actions require authorization. Start with read-only queries, then add one controlled action with confirmation and an audit trail.
- Keep data access scoped. Every read, write, search, and action must enforce user/tenant permissions.
- Keep the model provider replaceable. The graph and core retrieval path must not depend on a single LLM vendor.
3. Proposed architecture
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
Suggested stack
Component	Initial choice	Notes
Graph database	FalkorDB — required	Primary graph store and graph query engine
Backend	Python + FastAPI	Fast iteration and data-processing ecosystem
Graph client	Official FalkorDB client compatible with the deployed version	Confirm current client APIs and supported Cypher features
Frontend	Next.js + TypeScript	Chat, citations, graph exploration
Agent tools	MCP-compatible tools	Standardized interface for graph search and approved actions
LLM	Configurable tool-calling model	Entity extraction, query interpretation, answer synthesis
Embeddings	Optional compatible embedding model	Add semantic retrieval only when useful
Source storage	Local files initially; object storage later if needed	Preserve original documents and excerpts
Tests	Pytest plus deterministic fixture dataset	Validate ingestion, queries, citations, permissions, and updates


Do not add a separate vector database, Redis, message broker, or workflow engine unless measurements or requirements justify it. If semantic retrieval is needed, evaluate FalkorDB's supported vector capabilities for the chosen version first.
4. Graph schema
Use stable IDs from source systems whenever possible. A person referenced in a chat, ticket, and document should resolve to one canonical Person node.
Node labels
Label	Suggested properties
Person	id, name, email, role, tenant_id
Team	id, name, tenant_id
Project	id, name, status, updated_at, tenant_id
Document	id, title, source_uri, updated_at, tenant_id
Ticket	id, title, status, priority, source_uri, tenant_id
Message	id, channel, timestamp, source_uri, tenant_id
Decision	id, summary, timestamp, status, tenant_id
Source	id, system, external_id, version, last_synced_at, tenant_id
Evidence (optional)	id, excerpt, source_uri, start_offset, end_offset, tenant_id


Relationship types
- (:Person)-[:MEMBER_OF]->(:Team)
- (:Person)-[:OWNS]->(:Project) or (:Person)-[:ASSIGNED_TO]->(:Ticket)
- (:Team)-[:RESPONSIBLE_FOR]->(:Project)
- (:Person)-[:AUTHORED]->(:Document)
- (:Person)-[:CREATED]->(:Ticket)
- (:Project)-[:HAS_TICKET]->(:Ticket)
- (:Project)-[:DEPENDS_ON]->(:Project)
- (:Project)-[:HAS_DECISION]->(:Decision)
- (:Decision)-[:RECORDED_IN]->(:Message)
- (:Decision)-[:SUPPORTED_BY]->(:Document) or (:Evidence)
- (:Message)-[:ABOUT]->(:Project)
- (:Ticket)-[:MENTIONED_IN]->(:Message)
- (:Document)-[:FROM_SOURCE]->(:Source)
- (:Evidence)-[:DERIVED_FROM]->(:Message|:Document|:Ticket)
FalkorDB relationship/property constraints and syntax must be verified against the exact deployed version. Keep schema migrations and index creation in version-controlled setup scripts.
Provenance and time
Every extracted fact or relationship that materially affects an answer should carry, directly or through an evidence node:
- Source ID and original URI.
- Source system and external record ID.
- Source timestamp and ingestion timestamp.
- Version or content hash.
- Extractor/model version where applicable.
- Confidence or evidence status when extraction is probabilistic.
- Validity interval for facts that change over time.
For changing ownership or status, preserve history. Close or supersede old relationships rather than leaving contradictory active relationships. Distinguish when a fact was true from when the system learned it.
5. Ingestion pipeline
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
Implement the pipeline in this order:
1. Source adapters: initially support JSON, Markdown, and CSV exports. Add live integrations after the end-to-end workflow works.
2. Normalization: convert inputs into a common record format with stable IDs, timestamps, source URI, and version/hash.
3. Extraction: identify people, teams, projects, tickets, decisions, blockers, dependencies, and ownership.
4. Entity resolution: use stable IDs and conservative matching. Avoid merging people based only on similar names.
5. Validation: validate labels, properties, relationship types, tenant scope, and evidence references.
6. Graph writes: use idempotent upserts so re-ingestion does not create duplicate nodes or edges.
7. Change handling: update changed records, close stale relationships, and process deletions/archival.
8. Reconciliation: periodically compare source records with graph state and report missing or stale records.
9. Observability: log source counts, extracted entities, rejected records, errors, and sync checkpoints.
Preserve original records outside the graph or in a suitable source store. Store concise searchable text or chunks in the graph only when useful, and link every chunk back to its source and exact location.
6. Agent and graph tools
Start with a small set of typed, testable tools exposed through an MCP-compatible interface where appropriate.
Tool	Responsibility
search_entities	Find people, teams, projects, tickets, documents, and decisions
get_entity_details	Return validated properties and adjacent relationships
traverse_relationships	Perform bounded traversal over an allowlist of relationship types
search_source_evidence	Retrieve source excerpts and exact source references
get_decision_history	Return decisions, dates, and supporting evidence
get_project_status	Assemble owners, blockers, dependencies, and latest verified updates
propose_action	Prepare a ticket assignment or status update without executing it
execute_action	Execute a supported action only after authorization and confirmation


Tool requirements:
- Validate all inputs and outputs with schemas.
- Restrict traversals by depth, result count, labels, and relationship types.
- Use parameterized queries or safe query construction.
- Do not give the model unrestricted write access to FalkorDB.
- Keep read tools read-only.
- Apply tenant and user authorization on every tool call.
- Return structured results with IDs, timestamps, and provenance.
- Log tool calls and errors without leaking sensitive source content.
7. Query and answer flow
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
“Why is the payments migration delayed, and who needs to act?”

Expected process: find the project; retrieve its owner and status; follow its ticket and dependency relationships; inspect recent source messages and decisions; verify the latest evidence; return the blocker, responsible person/team, next step, and citations.
8. Citations and answer contract
Do not ask the LLM to invent citations after drafting an answer. The backend must build citations from retrieved records and source metadata.
Example evidence object:
{
  "claim": "Compatibility tests are blocking the migration",
  "source_id": "ticket_482",
  "source_type": "ticket",
  "source_title": "Payments API migration",
  "source_uri": "https://example.test/tickets/482",
  "excerpt": "Compatibility tests are failing on the new endpoint.",
  "source_timestamp": "2026-10-15T14:30:00Z"
}
This is illustrative test data, not a real company record.
The UI should show source title, excerpt, timestamp, and a link to the original source when available. Each material claim should be traceable. If sources conflict, show the conflict and dates; do not silently pick a preferred answer. Check permissions before returning excerpts or links.
9. Keeping the graph current
Implement:
- Stable source IDs and content hashes/version numbers.
- created_at, updated_at, ingested_at, and last_synced_at as applicable.
- Idempotent upserts.
- Incremental ingestion and periodic reconciliation.
- Explicit deletion, archival, and access-revocation handling.
- Validity intervals for changing ownership, status, and commitments.
- Source freshness indicators in the UI.
- Retry handling and resumable checkpoints for ingestion failures.
Do not assume that a source change has propagated until the graph update succeeds. Surface sync errors and stale status. If asynchronous indexing is introduced, track indexing state so retrieval can handle lag.
10. Security and tenant isolation
Tenant isolation is a core requirement, not a later optimization.
- Associate every source record, node, relationship, query, and action with an authorized tenant/scope.
- Enforce access control in the backend and storage/query layer, not only in prompts.
- Do not trust IDs supplied by a client without checking authorization.
- Ensure graph traversals cannot cross into another tenant's data.
- Keep credentials in environment/secrets management, never in source control.
- Audit reads of sensitive information and all write actions.
- Support deletion and retention policies for source records and derived memories.
- Treat ingested documents and messages as untrusted data; do not follow instructions embedded in them.
Before using shared-tenant graphs in production, test isolation with adversarial queries and relationship traversals.
11. Frontend scope
Build three views:
A. Ask Company Brain
- Chat input and streaming/normal response display.
- Answer with source citations and evidence excerpts.
- Related people, teams, projects, and decisions.
- Suggested follow-up questions.
- Clear “insufficient evidence” and “sources conflict” states.
B. Graph explorer
- Interactive nodes and edges for people, teams, projects, documents, tickets, and decisions.
- Click a node to inspect properties, connected entities, and provenance.
- Show relationship direction and relevant timestamps.
- Avoid rendering the entire graph at once; explore a bounded neighborhood around a selected entity.
C. Company activity and actions
- Project owners, status, blockers, dependencies, and recent changes.
- Last-synced status for source systems.
- Proposed action, confirmation, execution result, and audit history.
Prioritize the chat-and-evidence experience first. The graph explorer should help users verify the reasoning rather than become a decorative visualization.
12. Evaluation plan
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
13. Implementation roadmap
Phase 1 — Foundation
- Create repository structure and environment configuration.
- Run FalkorDB locally.
- Implement schema/index setup and a version-controlled graph client module.
- Prepare a small connected test dataset.
- Verify core graph queries and entity identity.
Exit criterion: FalkorDB contains connected entities and relationships that can be inspected and queried.
Phase 2 — Ingestion
- Implement source normalization and adapters.
- Extract entities and relationships.
- Resolve entities and attach provenance.
- Implement idempotent upserts and sync checkpoints.
- Test updates, deletions, and reruns.
Exit criterion: re-ingesting the same dataset does not create duplicates, and source changes update graph state correctly.
Phase 3 — Retrieval tools
- Implement the typed tools in Section 6.
- Add bounded traversal templates and source-evidence lookup.
- Enforce permissions and query limits.
- Test multi-hop retrieval independently of the LLM.
Exit criterion: the backend can answer the core graph questions deterministically.
Phase 4 — Grounded agent
- Add LLM tool selection and orchestration.
- Implement claim-to-evidence mapping.
- Add conflict handling and abstention.
- Build the evaluation harness.
Exit criterion: questions spanning multiple source types receive grounded answers with correct citations.
Phase 5 — UI and controlled action
- Build chat, citations, graph explorer, and project view.
- Add one sandboxed action such as proposing or assigning a ticket.
- Add confirmation, idempotency, and audit logging.
Exit criterion: an end-to-end demo shows a question, graph-backed reasoning, source evidence, and a safely executed or clearly simulated action.
Phase 6 — Polish and reliability
- Fix evaluation failures.
- Test tenant isolation and stale data.
- Add error states, loading states, and sync visibility.
- Prepare repeatable demo scenarios.
Exit criterion: the demo is reproducible, source-grounded, and handles uncertainty honestly.
14. Suggested repository layout
company-brain/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── config/
│   │   ├── graph/
│   │   │   ├── client.py
│   │   │   ├── schema.py
│   │   │   ├── queries.py
│   │   │   └── migrations/
│   │   ├── ingestion/
│   │   │   ├── adapters/
│   │   │   ├── normalize.py
│   │   │   ├── extract.py
│   │   │   ├── resolve_entities.py
│   │   │   └── sync.py
│   │   ├── agent/
│   │   │   ├── orchestrator.py
│   │   │   ├── tools.py
│   │   │   ├── evidence.py
│   │   │   └── prompts.py
│   │   ├── security/
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
├── docker-compose.yml
├── .env.example
└── README.md
This is a suggested starting layout; adjust it to the team's chosen frameworks without weakening the module boundaries.
15. Out of scope for the first version
- Full autonomous agent swarms.
- Every possible live source connector.
- Multiple graph databases.
- A separate vector database before benchmarking FalkorDB's capabilities.
- Unrestricted generated graph queries.
- Automatic irreversible actions.
- Advanced organizational prediction or simulation.
- Premature microservices and complex distributed infrastructure.
16. Final engineering priorities
Implement in this order:
Graph schema → ingestion → entity resolution and provenance → graph queries → evidence retrieval → grounded agent → citations → controlled action → polished UI.
The core deliverable is not merely a chatbot or a graph visualization. It is a company knowledge system whose facts are connected in FalkorDB, whose answers can be traced to source evidence, and whose knowledge stays current as company data changes.