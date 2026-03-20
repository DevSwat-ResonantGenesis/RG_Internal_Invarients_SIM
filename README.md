# RG Internal Invariants SIM (RARA)

Internal platform governance service — Resident Autonomous Runtime Agent for Genesis2026.

## Overview

This is a standalone microservice extracted from the monolithic `rara_service`. It provides:

- **Invariant Engine** — Graph constraint enforcement via AST Analysis
- **Invariant Classes** — Structural, Semantic, Temporal invariant checking
- **Kill Switch** — Emergency freeze/stop/reset
- **Mutation Executor** — Atomic mutations with rollback
- **Governance Engine** — Decision explainability and audit trail
- **Capability Engine** — Agent capability enforcement
- **Compliance** — EU AI Act, SOC2, policy enforcement
- **DISD Protocol** — Decentralized Secure Identity messaging
- **Cryptographic Receipts** — Tamper-proof mutation receipts
- **Quorum Authority** — Multi-agent consensus
- **Epoch Authority** — Time-based governance
- **Snapshot Engine** — System state snapshots and restore

## Running Locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8093
```

## Docker

```bash
docker build -t rg_internal_invarients_sim .
docker run -p 8093:8093 rg_internal_invarients_sim
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://shared_redis:6379/0` | Redis connection |
| `AST_ANALYSIS_SERVICE_URL` | `http://rg_ast_analysis:8000` | AST Analysis service |
| `HASH_SPHERE_URL` | `http://rg_users_invarients_sim:8091` | Users Invariants SIM |
| `RARA_RUNTIME_PATH` | `/opt/resonant/runtime` | Runtime layer path |
| `RARA_CORE_PATH` | `/opt/resonant/core` | Core layer path |
| `RARA_SNAPSHOTS_PATH` | `/opt/resonant/snapshots` | Snapshots directory |
| `RARA_STATE_PATH` | `/opt/resonant/state` | State directory |
| `RARA_COMPLIANCE` | `minimal` | Compliance profile |
| `RARA_ENVIRONMENT` | `dev` | Environment (dev/staging/prod) |

## API Endpoints (admin-only)

- `GET /health` — Health check
- `GET /status` — System status
- `GET /agents` — List agents
- `POST /agents/register` — Register agent
- `POST /mutations/execute` — Execute mutation
- `POST /mutations/approve` — Approve mutation
- `POST /invariants/check` — Run invariant checks
- `GET /invariants/results` — Get results
- `POST /control/freeze` — Freeze system
- `POST /control/emergency-stop` — Emergency stop
- `GET /snapshots` — List snapshots
- `POST /snapshots/create` — Create snapshot
- `GET /compliance/report` — Compliance report
- `GET /governance/state` — Governance state

## Port

**8093**
