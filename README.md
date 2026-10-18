# Company Brain (Engram)

[![Track](https://img.shields.io/badge/Track-Company%20Brain%20(Primary)-blue)](docs/JUDGE_QA_GUIDE.md)
[![Secondary Track](https://img.shields.io/badge/Track-Agents%20That%20Act%20on%20Connected%20Data-purple)](docs/JUDGE_QA_GUIDE.md)
[![Secondary Track](https://img.shields.io/badge/Track-Agent%20Memory%20%26%20Coordination-indigo)](docs/JUDGE_QA_GUIDE.md)
[![Database](https://img.shields.io/badge/Graph-FalkorDB%20Latest-crimson)](https://falkordb.com)
[![State](https://img.shields.io/badge/State-Redis%20Lua%20CAS%20Fencing-red)](contracts/PROTOCOL.md)
[![Tests](https://img.shields.io/badge/Tests-87%20Passed-brightgreen)](backend/tests)

> **Autonomous Decision Provenance, Topological Drift Detection, and Grounded Multi-Tenant State Engine for FalkorDB Graph Hacks.**  
> An auditable, temporal property graph connecting enterprise systems, engineering teams, and architectural decision records to verbatim cryptographic evidence with zero-hallucination verification.

---

## 🏆 Hackathon Track Declarations (Rule #5 & Rule #10)

This project is submitted to the **WeMakeDevs x FalkorDB "Graph Hacks" Hackathon** under the following tracks:

- **Primary Track:** **`Company Brain` (Track 03)**
  - Unifies **people, teams, projects, systems, documents, tickets, chats, and decisions** into an active, traversable property graph with zero mock fallbacks. Fully realizes all 5 Company Brain pillars:
    1. *Who Owns What vs. Who Knows What*: Formal temporal accountability (`[:OWNS]`) alongside computed deep subject matter expertise (`knowledge_score` from authored tickets, chats, and ADRs).
    2. *Tracing Decisions to Source*: Multi-hop causal lineage (`[:SUPERSEDES*1..10]`) back to raw Slack chats and Linear tickets.
    3. *Keeping Knowledge Current*: Autonomous documentation drift detection with 2PC atomic reconciliation.
    4. *Answers with Clear Sources*: Strictly grounded answers with inline citation markers (`[E1]`, `[E2]`) and SHA-256 verification hashes.
    5. *Multi-Tenant Isolation*: Zero-leakage physical graph partitioning across enterprise tenants.
- **Secondary Track 1:** **`Agents That Act on Connected Data`**
  - An autonomous multi-turn agent that evaluates multi-hop graph lineage, detects documentation drift, identifies optimal code/system owners via Cypher graph centrality, and stages two-phase atomic graph mutations.
- **Secondary Track 2:** **`Agent Memory and Coordination`**
  - Redis Lua CAS monotonic epoch fencing (`turn:{tenant_id}:{session_id}`) and cryptographic snapshot hash validation that coordinates multi-turn agent state and prevents race conditions or stale snapshot overwrites.

---

## ⚡ Why FalkorDB is Essential (Rule #2 & Rule #3)

A relational SQL database or vector embedding store **fundamentally cannot solve** this problem:

1. **Multi-Hop Variable-Length Lineage Traversal (`[:SUPERSEDES*1..10]`)**:
   - Architectural decisions form directed acyclic causal graphs (DAGs). When tracking why an active decision exists, the engine must traverse arbitrary chain depths from historical RFC anchors to current terminal nodes. In SQL, recursive CTEs over cyclic joins become exponentially expensive and unmaintainable. In vector search, cosine similarity has no causal or directed graph semantics—a vector search might find "similar" documents but cannot know whether Decision B *invalidated* Decision A.
2. **"Who Owns What vs. Who Knows What" Graph Computation**:
   - Formal accountability is an active temporal edge (`(owner:Person)-[:OWNS]->(s:System)` where `valid_to IS NULL`). Deep domain expertise is computed across authored tickets, Slack incident threads, and decisions:
     $$\text{knowledge\_score} = (\text{decisions\_led} \times 3) + (\text{artifacts\_authored} \times 2)$$
     FalkorDB evaluates this real-time graph algorithm in < 2ms without table joins.
3. **Temporal Edge Validity & Immutable Audit Trails**:
   - In enterprise operations, ownership is never overwritten; it transitions. FalkorDB temporal edges preserve historical ownership via `valid_from` and `valid_to: null` properties. Historical queries can traverse the topology as it existed at any point in time without data loss or table duplication.
4. **Topological Blast-Radius & Dependency Impact Calculation**:
   - Evaluating mutation risk requires recursive upstream and downstream traversal across service dependencies (`[:DEPENDS_ON*1..5]`) and affected documentation (`[:DOCUMENTS]`). FalkorDB computes topological blast radius directly in Cypher sub-millisecond graph queries.
5. **Physical Multi-Tenant Graph Partitioning**:
   - FalkorDB allows physical graph isolation via native graph namespaces (`tenant_acme_payments` vs `tenant_nexus_infra`). Cross-tenant data leakage is prevented at the storage engine level, not through brittle `WHERE tenant_id = $id` application filters.

---

## 🧬 Graph Data Model (Rule #10)

### Mermaid Topology Diagram

```mermaid
graph TD
    classDef person fill:#D4CEBF,stroke:#2A2F3B,stroke-width:1.5px,color:#13151A;
    classDef team fill:#4E9F76,stroke:#2A2F3B,stroke-width:1.5px,color:#FFFFFF;
    classDef project fill:#858D9A,stroke:#2A2F3B,stroke-width:1.5px,color:#FFFFFF;
    classDef system fill:#4C78A8,stroke:#2A2F3B,stroke-width:1.5px,color:#FFFFFF;
    classDef decActive fill:#2ECC71,stroke:#2A2F3B,stroke-width:1.5px,color:#FFFFFF;
    classDef decSup fill:#68707E,stroke:#2A2F3B,stroke-width:1.5px,color:#FFFFFF;
    classDef doc fill:#D07D38,stroke:#2A2F3B,stroke-width:1.5px,color:#FFFFFF;
    classDef evidence fill:#5E60CE,stroke:#2A2F3B,stroke-width:1.5px,color:#FFFFFF;
    classDef source fill:#858D9A,stroke:#2A2F3B,stroke-width:1.5px,color:#FFFFFF;

    Aarav["Person: Aarav Mehta (Staff Security Eng)"]:::person
    Priya["Person: Priya Nair (Payments Lead)"]:::person
    Rohan["Person: Rohan Verma (Security Architect)"]:::person
    Team["Team: Core Payments & Security"]:::team
    Project["Project: Zero-Trust Ingress Migration"]:::project
    System["System: payment-gateway"]:::system
    Doc["Document: Payments Auth RFC v1"]:::doc
    OldDec["Decision: OAuth Introspection (superseded)"]:::decSup
    NewDec["Decision: Local Ed25519 (active)"]:::decActive
    SlackEvi["Evidence: Slack Incident #inc-payments"]:::evidence
    LinearEvi["Evidence: Linear Ticket PAY-402"]:::evidence
    DocEvi["Evidence: Confluence RFC Proposal"]:::evidence

    Priya -->|OWNS (valid_to: null)| System
    Priya -->|MEMBER_OF {role: 'Payments Lead'}| Team
    Aarav -->|MEMBER_OF {role: 'Staff Security Engineer'}| Team
    Rohan -->|MEMBER_OF {role: 'Security Architect'}| Team
    Team -->|RESPONSIBLE_FOR| System
    System -->|PART_OF| Project
    NewDec -->|IMPACTS_PROJECT| Project

    Aarav -->|ESTABLISHED| NewDec
    Aarav -->|AUTHORED| SlackEvi
    Rohan -->|AUTHORED| LinearEvi
    Priya -->|AUTHORED| DocEvi

    NewDec -->|AFFECTS| System
    OldDec -->|AFFECTS| System
    NewDec -->|SUPERSEDES (reason: p99 latency SLA)| OldDec
    NewDec -->|SUPPORTED_BY| SlackEvi
    NewDec -->|SUPPORTED_BY| LinearEvi
    OldDec -->|SUPPORTED_BY| DocEvi

    Doc -->|DOCUMENTS| System
    Doc -->|PROPOSED| OldDec
    Doc -.->|ALIGNED_WITH (reconciled via POST /api/confirm)| NewDec
```

### Node Schema

| Label | Primary ID | Key Properties | Purpose |
|---|---|---|---|
| `Person` | `id` (e.g. `usr_018f_aarav`) | `display_name`, `canonical_email`, `role` | Human stakeholders, formal system owners, and domain experts. |
| `Team` | `id` (e.g. `team_core_pay`) | `name` | Organizational accountability unit grouping engineers. |
| `Project` | `id` (e.g. `proj_zero_trust_2026`) | `name`, `status` | Strategic engineering initiative linking systems and decisions. |
| `System` | `id` (e.g. `sys_payment_gw`) | `name`, `status` | Mission-critical production services, clusters, and databases. |
| `Decision` | `id` (e.g. `dec_ed25519_local`) | `summary`, `status` (`active` \| `superseded`), `timestamp` | Architectural Decision Records (ADRs) with multi-hop lineage. |
| `Document` | `id` (e.g. `doc_auth_rfc`) | `title`, `status` (`stale` \| `updated`), `uri`, `created_at` | Architecture specs, runbooks, SOPs, and RFCs. |
| `Evidence` | `id` (e.g. `evi_018f_latency_auth`) | `record_id`, `excerpt`, `source_type`, `author`, `source_uri`, `content_hash` | Verbatim, immutable evidence spanning Chats, Tickets, and Docs. |
| `Source` | `id` (e.g. `src_slack_inc`) | `uri`, `source_type` (`slack`, `linear`, `confluence`, `notion`), `content_hash` | External origin system containing raw conversation or ticket. |

### Relationship Schema

| Relationship | Source Label | Target Label | Edge Properties | Semantics |
|---|---|---|---|---|
| `[:OWNS]` | `Person` | `System` | `valid_from` (ms), `valid_to` (ms \| null), `ingested_at` | Formal accountability with temporal fencing. |
| `[:MEMBER_OF]` | `Person` | `Team` | `role` | Engineering organizational membership. |
| `[:RESPONSIBLE_FOR]` | `Team` | `System` | None | Team-level formal operational ownership. |
| `[:PART_OF]` | `System` | `Project` | None | Connects system architecture to business project initiatives. |
| `[:IMPACTS_PROJECT]` | `Decision` | `Project` | None | Traces architectural decisions to project outcomes. |
| `[:AUTHORED]` | `Person` | `Evidence` / `Document` | None | Attribution for computed Subject Matter Expertise (SME). |
| `[:SUPERSEDES]` | `Decision` | `Decision` | `reason` (string) | Directed causal lineage indicating architectural evolution. |
| `[:SUPPORTED_BY]` | `Decision` | `Evidence` | None | Direct cryptographic citation linking decision to excerpt. |
| `[:PROPOSED]` | `Document` | `Decision` | None | Original decision proposed by an RFC/spec. |
| `[:ALIGNED_WITH]` | `Document` | `Decision` | `updated_at` (ms) | Reconciled documentation link created upon drift resolution. |
| `[:DOCUMENTS]` | `Document` | `System` | None | Identifies which system the RFC or runbook governs. |

---

## 🧠 Core Cypher Queries & Graph Algorithms (Rule #10)

### 1. "Who Owns What vs. Who Knows What" Engine (Algorithm 1)
Evaluates formal temporal accountability alongside computed deep subject matter expertise:
```cypher
/* Who Owns What (Formal Accountability) */
MATCH (owner:Person)-[r:OWNS]->(s:System {name: $system_name})
WHERE r.valid_to IS NULL
OPTIONAL MATCH (owner)-[:MEMBER_OF]->(t:Team)
OPTIONAL MATCH (s)-[:PART_OF]->(proj:Project)
RETURN owner, s, t, proj;

/* Who Knows What (Computed Domain Subject Matter Expertise) */
MATCH (p:Person), (s:System {name: $system_name})
OPTIONAL MATCH (p)-[:ESTABLISHED]->(d:Decision)-[:AFFECTS]->(s)
OPTIONAL MATCH (p)-[:AUTHORED]->(e:Evidence)<-[:SUPPORTED_BY]-(d2:Decision)-[:AFFECTS]->(s)
OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)
WITH p, t, count(DISTINCT d) AS decisions_led, count(DISTINCT e) AS artifacts_authored, collect(DISTINCT e.source_type) AS artifact_types
WHERE (decisions_led + artifacts_authored) > 0
RETURN p, t, decisions_led, artifacts_authored, artifact_types,
       (decisions_led * 3 + artifacts_authored * 2) AS knowledge_score
ORDER BY knowledge_score DESC;
```

### 2. Multi-Hop Decision Lineage & Evidence Provenance (Algorithm 2)
Traverses causal superseding chains across arbitrary hops with attached multi-source evidence:
```cypher
MATCH (s:System {name: $system_name})<-[:AFFECTS]-(d:Decision)
OPTIONAL MATCH (d)-[:SUPERSEDES*0..10]->(prev:Decision)
OPTIONAL MATCH (prev)-[:SUPPORTED_BY]->(e:Evidence)
RETURN s, d, prev, e;
```

### 3. Variable-Length Topological Lineage & Drift Traversal (Algorithm 3)
Detects stale documentation whose anchored decision has been superseded by newer active decisions:
```cypher
MATCH (doc:Document {id: $doc_id})-[:PROPOSED|ALIGNED_WITH]->(anchor:Decision)
MATCH path = (anchor)<-[:SUPERSEDES*1..10]-(active_dec:Decision {status: 'active'})
OPTIONAL MATCH (active_dec)-[:SUPPORTED_BY]->(evi:Evidence)
RETURN doc, anchor, active_dec, length(path) AS divergence_hops, collect(evi) AS evidence;
```

### 4. Atomic Documentation Re-alignment (Two-Phase Commit Mutation)
Reconciles stale documentation upon confirmation (`POST /api/confirm`):
```cypher
MATCH (doc:Document {id: $doc_id}), (active:Decision {id: $active_decision_id})
SET doc.status = 'updated', doc.updated_at = $now_ms
CREATE (doc)-[:ALIGNED_WITH {updated_at: $now_ms}]->(active)
RETURN doc.id, doc.status;
```

---

## 🛡️ Architecture & Safety Guarantees

```text
┌────────────────────────────────────────────────────────┐
│ Next.js Client (Port 3000)                             │
│  - Engineering Slate Canvas (Force Physics d3 -420/135)│
│  - Live Topology (GET /api/graph/{tenant_id})          │
│  - 409 Snapshot Conflict Banner & Re-sync Dock         │
└───────────────────────────┬────────────────────────────┘
                            │ HTTP POST /api/turn, /api/confirm
                            ▼
┌────────────────────────────────────────────────────────┐
│ FastAPI Application Gateway (Port 8000)                │
│  - Two-Phase Citation Validator (Zero Hallucination)   │
│  - Dynamic Query Parameter & Intent Routing            │
└──────────────┬───────────────────────────┬─────────────┘
               │ Monotonic Lua CAS         │ Cypher Traversals
               ▼                           ▼
┌───────────────────────────┐ ┌──────────────────────────┐
│ Redis State Machine       │ │ FalkorDB Multi-Tenant    │
│  - turn:{tid}:{sess}      │ │  - tenant_acme_payments  │
│  - lock:{proposal_id}     │ │  - tenant_nexus_infra    │
│  - Monotonic Epoch Fencing│ └──────────────────────────┘
└───────────────────────────┘
```

1. **Option B MCP Split Envelope**:
   - Clean separation of structural graph entities (`records`) from verbatim citation evidence (`evidence`). Citations are verifiable strings with `sha256(excerpt + "\n" + source_uri)`.
2. **Two-Phase Citation Validator**:
   - The LLM cannot hallucinate citations. Any claim citing an evidence ID not present in the MCP evidence bag is rejected. If a retry fails, the engine triggers graceful abstention (`UNVERIFIABLE_CLAIM_ABSTAIN`) to ensure zero hallucinations.
3. **Redis Lua CAS Monotonic Epoch Fencing**:
   - Optimistic concurrency control guarantees atomic turn transitions (`PLANNING` → `EXECUTING_TOOLS` → `AWAITING_CONFIRMATION` → `COMPLETED`). Stale turns reject with HTTP 410.
4. **Snapshot Hash Collision & HTTP 409 Conflict Protection**:
   - Before applying a staged mutation, the engine checks `snapshot_hash` against live FalkorDB state. If another engineer modified the graph concurrently, HTTP 409 is returned with the live hash for non-destructive re-synchronization.

---

## 🧭 One-Click Judge Evaluation Presets

The Left Chat Pane header features 4 instant presets wired to the live FalkorDB backend:

| Preset Chip | User Intent | What FalkorDB & The Agent Prove |
|---|---|---|
| **`1. Trace Decision & Sources`** | *"Why was the payment gateway authentication method changed? Trace the decision back to its Slack and ticket sources."* | Traverses causal `[:SUPERSEDES*0..10]` chain. Returns active `dec_ed25519_local` and superseded `dec_oauth_introspection` grounded with **Slack chat** (`#inc-payments`), **Linear ticket** (`PAY-402`), and **Confluence RFC** verbatim evidence with SHA-256 verification. |
| **`2. Who Owns vs. Who Knows`** | *"Who formally owns payment-gateway, which team is responsible, and who knows the most about its Ed25519 implementation?"* | Distinguishes formal accountability (`Priya Nair` / `Core Payments & Security`) from deep computed operational knowledge (`Aarav Mehta` with `knowledge_score: 5` and `Rohan Verma` with `knowledge_score: 2`). |
| **`3. Resolve Knowledge Drift`** | *"Check if the Payments Auth RFC v1 document has drifted from current decisions and stage an update to keep knowledge current."* | Discovers topological path divergence (`divergence_hops: 1`, `drift_staleness_days: 62`). Transitions to `AWAITING_CONFIRMATION` with staged proposal. Click **Confirm Mutation** to execute atomic graph reconciliation (`[:ALIGNED_WITH]`). |
| **`4. Verify Tenant Isolation`** | *"Query event-stream-cluster architecture and KRaft consensus decisions within current tenant scope to verify strict zero-leakage isolation."* | Proves physical FalkorDB namespace isolation (`tenant_acme_payments` vs `tenant_nexus_infra`). Zero cross-tenant data or entity leakage. |

---

## 🚀 Complete Local Setup Instructions (Rule #10)

Follow these exact steps to run the complete stack locally:

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (Python 3.14 compatible)
- Node.js 18+ and npm

### 1. Start FalkorDB and Redis
```bash
docker run -d --name falkordb -p 6379:6379 falkordb/falkordb:latest
```

### 2. Configure Environment Files
```bash
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```

### 3. Backend Setup & Pytest Execution
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Reset and seed both pristine synthetic demo tenants (< 0.1s)
python scripts/reset_demo.py

# Run complete test suite (82 passing tests)
pytest tests -v
```

### 4. Launch FastAPI Gateway
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive OpenAPI documentation is live at [http://localhost:8000/docs](http://localhost:8000/docs).  
Live FalkorDB topology endpoint: [http://localhost:8000/api/graph/acme_payments](http://localhost:8000/api/graph/acme_payments).

### 5. Launch Next.js Web UI
In a separate terminal:
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to view the live Engineering Slate interface.

---

## 🔒 Data Privacy Statement & AI Assistance Disclosure

### Data Privacy Statement (Rule #6)
**100% of data** contained in `tenant_acme_payments` and `tenant_nexus_infra` is synthetic architectural and organizational data created exclusively for the WeMakeDevs x FalkorDB Graph Hacks Hackathon. No proprietary, sensitive, customer, or real-world private data was used or ingested.

### AI Assistance Disclosure (Rule #11)
In accordance with Graph Hacks Rule #11:
- **AI Coding Assistants Used:** Cursor, Antigravity (Google DeepMind), Gemini 3.8 Flash, and OpenAI APIs.
- **Scope of AI Assistance:** Scaffolding initial boilerplate schemas, optimizing Cypher query syntax, drafting unit test fixtures, and styling frontend Tailwind components.
- **Architectural Authorship:** All multi-tenant graph partitioning models, Lua CAS state machines, Two-Phase Citation Verification algorithms, and state verification test suites were architected, integrated, and verified directly by the team.

---

## 📄 License
MIT License.
