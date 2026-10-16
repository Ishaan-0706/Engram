# Engram

[![Track](https://img.shields.io/badge/Track-03%20Decision%20Provenance-blue)](docs/ARCHITECTURE.md)
[![Database](https://img.shields.io/badge/Graph-FalkorDB%20v1.0.8-crimson)](https://falkordb.com)
[![State](https://img.shields.io/badge/State-Redis%20CAS%20Fencing-red)](contracts/PROTOCOL.md)
[![Tests](https://img.shields.io/badge/Tests-76%20Passed-brightgreen)](backend/tests)

> **Autonomous Decision Provenance & Grounded State Engine**  
> An auditable, temporal property graph connecting systems, people, and architectural decisions to verbatim cryptographic evidence.

---

## ⚡ Highlights

- **FalkorDB Property Graph Backbone**: Pure property graph traversals tracing full causal decision lineage (`[:AFFECTS]`, `[:SUPERSEDES]`, `[:SUPPORTED_BY]`).
- **Cryptographic Grounding**: Every synthesized claim cites an authentic evidence item verified via `sha256(excerpt + "\n" + source_uri)`. Zero hallucinated citations.
- **Optimistic Concurrency & Lua CAS Fencing**: Redis-backed state machine with monotonic epoch fences (`turn:{tid}:{sess}`). Rejects stale client writes with HTTP 410 / 409.
- **Option B MCP Split Envelope**: Clean decoupling of graph records from verbatim evidence citations.
- **Strict Multi-Tenant Isolation**: Physical graph partitioning under `tenant_{tenant_id}` ensures zero cross-tenant leakage.

---

## 🏗️ Architecture Overview

```text
┌─────────────────────────────────┐
│ Next.js Client (Frontend)       │
│  - Interactive Graph Viewer     │
│  - Dynamic Tenant Switcher      │
│  - Evidence Drawer & Drift Alert│
└────────────────┬────────────────┘
                 │ HTTP POST /api/turn
                 ▼
┌────────────────────────────────────────────────────────┐
│ FastAPI Application Gateway (Port 8000)                │
│  - JWT Tenant Scoping & Settings Injection            │
│  - Dynamic Orchestrator Pipeline (orchestrator.py)     │
└────────────┬─────────────────────────────┬─────────────┘
             │ Lua CAS Fence               │ MCP Query Dispatch
             ▼                             ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│ Redis State Engine       │  │ MCP Tool Server          │
│  - turn:{tid}:{sess}     │  │  - get_decision_history  │
│  - lock:{proposal_id}    │  │  - detect_drift          │
│  - idempotency:{key}     │  │  - get_system_ownership  │
└──────────────────────────┘  └────────────┬─────────────┘
                                           │ Cypher Traversal
                                           ▼
                              ┌──────────────────────────┐
                              │ FalkorDB Multi-Tenant    │
                              │  - tenant_acme_payments  │
                              │  - tenant_nexus_infra    │
                              └──────────────────────────┘
```

For complete technical specifications, schema definitions, and sequence diagrams, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 🚀 Quickstart Guide

### 1. Launch FalkorDB and Redis
```bash
docker run -p 6379:6379 -it --rm falkordb/falkordb:v1.0.8
```

### 2. Environment Setup
```bash
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```

### 3. Backend Dependencies
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
```

### 4. Reset & Seed Pristine Demo Graphs
```bash
python backend/scripts/reset_demo.py
```
*Seeds `tenant_acme_payments` (Financial Services) and `tenant_nexus_infra` (Platform Infrastructure) in < 0.1s.*

### 5. Start FastAPI Backend
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive OpenAPI documentation is live at [http://localhost:8000/docs](http://localhost:8000/docs).

### 6. Run Track 03 Judging Demo Runner
In a separate terminal:
```bash
python backend/scripts/demo_runner.py
```
*Executes all 3 judging scenarios with high-contrast ANSI outputs, traversal visualizations, and cryptographic verification.*

To run in step-by-step interactive mode:
```bash
python backend/scripts/demo_runner.py --interactive
```

### 7. Run Test Suite
```bash
pytest backend/tests -v
```
*Runs all 76 unit, contract, state-machine, and integration tests.*

### 8. Launch Next.js Web UI
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to view the application.

---

## 🧪 Track 03 Judging Scenarios

| Scenario | Objective | Verification Criteria |
|---|---|---|
| **Scenario 1: Decision Lineage & Grounding** | Query payment gateway authentication evolution | Traces `dec_ed25519_local` superseding `dec_oauth_introspection`; verifies SHA-256 evidence digest. |
| **Scenario 2: Documentation Drift & Atomic Mutation** | Detect stale documentation, stage proposal, execute patch | Staged proposal with snapshot hash; validates HTTP 409 CAS fence; executes atomic Cypher mutation. |
| **Scenario 3: Strict Multi-Tenant Isolation** | Probe tenant `nexus_infra` for `acme_payments` entities | Asserts zero leaked entity records, zero evidence leakage, and physical graph separation. |

---

## 📜 Key Contracts

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): Comprehensive system architecture, schema specification, and lifecycle diagrams.
- [`contracts/PROTOCOL.md`](contracts/PROTOCOL.md): Developer 1 / Developer 2 turn state and fencing protocol.
- [`shared/contracts/mcp_envelope.schema.json`](shared/contracts/mcp_envelope.schema.json): Option B MCP split envelope schema.
- [`contracts/action-confirm.schema.json`](contracts/action-confirm.schema.json): Atomic mutation confirmation and snapshot hash validation contract.

---

## ⚖️ License
MIT License.
