# RG Internal Invariants SIM (RARA)

> **Part of the [ResonantGenesis](https://dev-swat.com) platform** — internal platform governance service (Resident Autonomous Runtime Agent).

[![Status: Production](https://img.shields.io/badge/Status-Production-brightgreen.svg)]()
[![Docker: rg_internal_invarients_sim](https://img.shields.io/badge/Docker-rg__internal__invarients__sim-blue.svg)]()
[![Port: 8093](https://img.shields.io/badge/Port-8093-orange.svg)]()
[![License: RG Source Available](https://img.shields.io/badge/License-RG%20Source%20Available-blue.svg)](LICENSE.txt)

Internal platform governance service — the **Resident Autonomous Runtime Agent (RARA)** for Genesis2026. Enforces structural, semantic, and temporal invariants across the platform. Admin-only access. Deployed as standalone Docker container `rg_internal_invarients_sim`.

## Architecture

```
Admin → Nginx → Gateway → rg_internal_invarients_sim (this service, port 8093)
                               ├── rg_ast_analysis (AST-based invariant enforcement)
                               ├── rg_users_invarients_sim (Hash Sphere state)
                               ├── Redis (state locks, caching)
                               └── Filesystem (/opt/resonant/runtime, core, snapshots)
```

## Features

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

## Quick Start

```bash
# Clone
git clone git@github-devswat:DevSwat-ResonantGenesis/RG_Internal_Invarients_SIM.git
cd RG_Internal_Invarients_SIM

# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn app.main:app --host 0.0.0.0 --port 8093 --reload
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
| `AST_ANALYSIS_SERVICE_URL` | `http://rg_ast_analysis:8000` | AST Analysis service for invariant checks |
| `HASH_SPHERE_URL` | `http://rg_users_invarients_sim:8091` | Users Invariants SIM (Hash Sphere state) |
| `RARA_RUNTIME_PATH` | `/opt/resonant/runtime` | Runtime layer path |
| `RARA_CORE_PATH` | `/opt/resonant/core` | Core layer path |
| `RARA_SNAPSHOTS_PATH` | `/opt/resonant/snapshots` | Snapshots directory |
| `RARA_STATE_PATH` | `/opt/resonant/state` | State directory |
| `RARA_COMPLIANCE` | `minimal` | Compliance profile (`minimal`, `standard`, `strict`) |
| `RARA_ENVIRONMENT` | `dev` | Environment (`dev`/`staging`/`prod`) |

## API Endpoints (admin-only)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/status` | System status |
| `GET` | `/agents` | List registered agents |
| `POST` | `/agents/register` | Register agent |
| `POST` | `/mutations/execute` | Execute mutation with rollback |
| `POST` | `/mutations/approve` | Approve pending mutation |
| `POST` | `/invariants/check` | Run invariant checks |
| `GET` | `/invariants/results` | Get invariant check results |
| `POST` | `/control/freeze` | Freeze system |
| `POST` | `/control/emergency-stop` | Emergency stop |
| `GET` | `/snapshots` | List system snapshots |
| `POST` | `/snapshots/create` | Create snapshot |
| `GET` | `/compliance/report` | Compliance report |
| `GET` | `/governance/state` | Governance engine state |

## Gateway Integration

The gateway proxies RARA requests to this standalone service:
```
/rara/*          → http://rg_internal_invarients_sim:8093/*
/api/v1/rara/*   → http://rg_internal_invarients_sim:8093/*
```

## Related Modules

| Module | Repo | Relationship |
|--------|------|-------------|
| AST Analysis | [`RG_AST_analysis`](https://github.com/DevSwat-ResonantGenesis/RG_AST_analysis) | Provides AST data for invariant enforcement |
| Users Invariants SIM | [`RG_Users_Invarients_SIM`](https://github.com/DevSwat-ResonantGenesis/RG_Users_Invarients_SIM) | Hash Sphere state used for governance decisions |
| Registered Users Agentic Chat | [`RG_Registered_Users_Agentic_Chat`](https://github.com/DevSwat-ResonantGenesis/RG_Registered_Users_Agentic_Chat) | Agent engine calls RARA for governance checks |
| Unified LLM Client | [`RG_UnifiedLLMClient`](https://github.com/DevSwat-ResonantGenesis/RG_UnifiedLLMClient) | Not used by this service |

## Deployment Status

- **Status**: ✅ **Production** — deployed as standalone Docker container `rg_internal_invarients_sim`
- **Extracted from**: `genesis2026_production_backend/rara_service` (entire directory deleted from monolith)
- **Server path**: `/home/deploy/RG_Internal_Invarients_SIM` (cloned from DevSwat GitHub)
- **Docker service**: `rg_internal_invarients_sim` in `docker-compose.unified.yml`
- **Port**: 8093 (internal Docker network)

---

**Organization**: [DevSwat-ResonantGenesis](https://github.com/DevSwat-ResonantGenesis)
**Platform**: [dev-swat.com](https://dev-swat.com)
