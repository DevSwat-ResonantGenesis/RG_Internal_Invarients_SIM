"""
RG Internal Invariants SIM - Resident Autonomous Runtime Agent (RARA)
Standalone internal platform governance service for Genesis2026
"""

import os
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .models import (
    MutationRequest, MutationResult, CapabilityType, AgentRole,
    SystemState, RARAStatus, ComplianceProfile, SnapshotMeta,
    ExplainabilityArtifact, GovernanceDecision, InvariantCheckResult
)
from .snapshot_engine import SnapshotEngine
from .capability_engine import CapabilityEngine
from .invariant_engine import InvariantEngine
from .governance_engine import GovernanceEngine
from .mutation_executor import MutationExecutor
from .agent_coordinator import AgentCoordinator
from .kill_switch import KillSwitch, KillSwitchTrigger, KillSwitchState
from .invariant_classes import (
    InvariantClass, InvariantClassChecker, Environment,
    STRUCTURAL_INVARIANTS, SEMANTIC_INVARIANTS, TEMPORAL_INVARIANTS
)
from .compliance import (
    ComplianceFramework, ComplianceVerifier, CompliancePolicy,
    get_policy, COMPLIANCE_POLICIES, EU_AI_ACT_REQUIREMENTS, SOC2_CONTROLS
)
from .physics_bridge import initialize_physics_bridge, get_physics_bridge
from .effect_boundary import initialize_effect_registry, get_effect_registry
from .epoch_authority import initialize_epoch_authority, get_epoch_authority
from .pre_auth_gate import initialize_pre_auth_gate, get_pre_auth_gate
from .quorum_authority import initialize_quorum_authority, get_quorum_authority
from .irreversibility_authority import initialize_irreversibility_authority, get_irreversibility_authority
from .disd_message import DISDMessage, DISDMessageType, DISDMessageFactory
from .disd_router import initialize_disd_router, get_disd_router
from .disd_protocol import initialize_disd_protocol, get_disd_protocol
from .disd_transport import initialize_transport_manager, get_transport_manager
# Try production cryptographic receipt, fallback to mock if cryptography not available
try:
    from .cryptographic_receipt import (
        initialize_cryptographic_receipt_system, get_crypto_receipt_handler,
        get_receipt_log_manager, get_failure_detection_system
    )
    USE_MOCK_CRYPTO = False
except ImportError:
    from .cryptographic_receipt_mock import (
        initialize_mock_cryptographic_receipt_system as initialize_cryptographic_receipt_system,
        get_mock_crypto_receipt_handler as get_crypto_receipt_handler,
        get_mock_receipt_log_manager as get_receipt_log_manager,
        get_mock_failure_detection_system as get_failure_detection_system
    )
    USE_MOCK_CRYPTO = True
    logger.warning("cryptography library not available, using mock receipt handlers")
from .enhanced_disd_router import initialize_enhanced_disd_router, get_enhanced_disd_router
from .enhanced_disd_protocol import initialize_enhanced_disd_protocol, get_enhanced_disd_protocol
from .adversarial_tests import run_adversarial_test_suite

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

RUNTIME_PATH = os.getenv("RARA_RUNTIME_PATH", "/opt/resonant/runtime")
CORE_PATH = os.getenv("RARA_CORE_PATH", "/opt/resonant/core")
SNAPSHOTS_PATH = os.getenv("RARA_SNAPSHOTS_PATH", "/opt/resonant/snapshots")
STATE_PATH = os.getenv("RARA_STATE_PATH", "/opt/resonant/state")
CODE_VISUALIZER_URL = os.getenv("AST_ANALYSIS_SERVICE_URL") or os.getenv("CODE_VISUALIZER_URL", "http://rg_ast_analysis:8000")
HASH_SPHERE_URL = os.getenv("HASH_SPHERE_URL") or os.getenv("STATE_PHYSICS_URL", "http://rg_users_invarients_sim:8091")
COMPLIANCE_PROFILE = os.getenv("RARA_COMPLIANCE", "minimal")


# ============================================================================
# GLOBAL INSTANCES
# ============================================================================

snapshot_engine: SnapshotEngine = None
capability_engine: CapabilityEngine = None
invariant_engine: InvariantEngine = None
governance_engine: GovernanceEngine = None
mutation_executor: MutationExecutor = None
agent_coordinator: AgentCoordinator = None
kill_switch: KillSwitch = None
invariant_checker: InvariantClassChecker = None
compliance_verifier: ComplianceVerifier = None

start_time: datetime = None
ENVIRONMENT = os.getenv("RARA_ENVIRONMENT", "dev")


# ============================================================================
# LIFESPAN
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global snapshot_engine, capability_engine, invariant_engine
    global governance_engine, mutation_executor, agent_coordinator
    global kill_switch, invariant_checker, compliance_verifier
    global start_time
    
    logger.info("RARA starting up...")
    
    # Initialize engines
    snapshot_engine = SnapshotEngine(
        runtime_path=RUNTIME_PATH,
        snapshots_path=SNAPSHOTS_PATH
    )
    
    capability_engine = CapabilityEngine(
        state_dir=STATE_PATH
    )
    
    invariant_engine = InvariantEngine(
        code_visualizer_url=CODE_VISUALIZER_URL,
        runtime_path=RUNTIME_PATH
    )
    
    governance_engine = GovernanceEngine(
        hash_sphere_url=HASH_SPHERE_URL,
        compliance_profile=ComplianceProfile(COMPLIANCE_PROFILE)
    )
    
    mutation_executor = MutationExecutor(
        runtime_path=RUNTIME_PATH,
        snapshot_engine=snapshot_engine,
        capability_engine=capability_engine,
        invariant_engine=invariant_engine,
        governance_engine=governance_engine
    )
    
    agent_coordinator = AgentCoordinator()
    
    # Initialize kill switch
    kill_switch = KillSwitch(state_dir=STATE_PATH)
    
    # Initialize invariant class checker with environment
    env = Environment(ENVIRONMENT) if ENVIRONMENT in [e.value for e in Environment] else Environment.DEV
    invariant_checker = InvariantClassChecker(environment=env)
    
    # Initialize compliance verifier
    policy = get_policy(ENVIRONMENT)
    compliance_verifier = ComplianceVerifier(framework=policy.framework)
    
    # Initialize physics bridge (MISSING COMPONENT NOW IMPLEMENTED)
    physics_bridge = initialize_physics_bridge(
        capability_engine=capability_engine,
        kill_switch=kill_switch
    )
    
    # Initialize irreversibility authority components
    effect_registry = initialize_effect_registry()
    epoch_authority = initialize_epoch_authority()
    pre_auth_gate = initialize_pre_auth_gate(
        epoch_authority=epoch_authority,
        effect_registry=effect_registry,
        physics_bridge=physics_bridge
    )
    quorum_authority = initialize_quorum_authority(
        min_quorum=3,
        veto_threshold=0.3,
        proposal_timeout_ms=30000
    )
    irreversibility_authority = initialize_irreversibility_authority(
        effect_registry=effect_registry,
        epoch_authority=epoch_authority,
        pre_auth_gate=pre_auth_gate,
        quorum_authority=quorum_authority
    )
    
    # Add some authorized voters for quorum
    quorum_authority.add_authorized_voter("rara_system", weight=2.0)
    quorum_authority.add_authorized_voter("human_operator", weight=3.0)
    
    # Initialize cryptographic receipt system (production or mock)
    crypto_handler, receipt_log_manager, failure_detector = initialize_cryptographic_receipt_system(
        system_salt=b"DISD_SYSTEM_SALT_V1" if not USE_MOCK_CRYPTO else b"MOCK_SYSTEM_SALT",
        log_path="/opt/resonant/logs/receipts.wal" if not USE_MOCK_CRYPTO else "/tmp/mock_receipts.wal"
    )
    if USE_MOCK_CRYPTO:
        logger.warning("Using MOCK cryptographic receipt handlers - NOT FOR PRODUCTION")
    else:
        logger.info("Using PRODUCTION cryptographic receipt handlers")
    
    # Initialize enhanced DISD protocol components
    enhanced_disd_router = initialize_enhanced_disd_router(
        router_id="rara_enhanced_disd_router",
        crypto_handler=crypto_handler,
        receipt_log_manager=receipt_log_manager,
        failure_detector=failure_detector
    )
    
    # Initialize basic DISD protocol for backward compatibility
    disd_router = initialize_disd_router("rara_disd_router")
    transport_manager = initialize_transport_manager()
    
    # Initialize enhanced DISD protocol
    enhanced_disd_protocol = initialize_enhanced_disd_protocol(
        swarm_id="rara_enhanced_swarm",
        router=enhanced_disd_router,
        quorum_authority=quorum_authority,
        irreversibility_authority=irreversibility_authority,
        crypto_handler=crypto_handler,
        receipt_log_manager=receipt_log_manager,
        failure_detector=failure_detector
    )
    
    # Initialize basic DISD protocol for compatibility
    disd_protocol = initialize_disd_protocol(
        swarm_id="rara_swarm",
        router=disd_router,
        quorum_authority=quorum_authority,
        irreversibility_authority=irreversibility_authority
    )
    
    # Start DISD protocols
    await disd_protocol.start()
    await enhanced_disd_protocol.start()
    
    start_time = datetime.utcnow()
    
    logger.info(f"RARA initialized: env={ENVIRONMENT}, compliance={policy.framework.value}")
    
    yield
    
    # Stop DISD protocols
    if disd_protocol:
        await disd_protocol.stop()
    if enhanced_disd_protocol:
        await enhanced_disd_protocol.stop()
    
    logger.info("RARA shutting down...")


# ============================================================================
# APP
# ============================================================================

app = FastAPI(
    title="RG Internal Invariants SIM (RARA)",
    description="Internal platform governance: atomic mutations, invariant enforcement, compliance, and rollback",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# REQUEST MODELS
# ============================================================================

class RegisterAgentRequest(BaseModel):
    agent_id: str
    role: AgentRole
    dsid: str
    public_key: str
    capabilities: Optional[List[CapabilityType]] = None


class SubmitProposalRequest(BaseModel):
    planner_id: str
    mutation: MutationRequest
    risk_score: float = 0.0
    alternatives_considered: int = 0


class VerifyProposalRequest(BaseModel):
    verifier_id: str
    proposal_id: str
    approved: bool
    reason: str = ""


class ExecuteProposalRequest(BaseModel):
    executor_id: str
    proposal_id: str


class ApprovalRequest(BaseModel):
    mutation_id: str
    approval_token: str


class RejectionRequest(BaseModel):
    mutation_id: str
    reason: str


# ============================================================================
# HEALTH & STATUS
# ============================================================================

@app.get("/health")
async def health():
    return {"status": "ok", "service": "rara"}


@app.get("/status", response_model=RARAStatus)
async def status():
    uptime = int((datetime.utcnow() - start_time).total_seconds()) if start_time else 0
    
    return RARAStatus(
        state=mutation_executor.current_state if mutation_executor else SystemState.STOPPED,
        active_mutation=mutation_executor.active_mutation if mutation_executor else None,
        last_snapshot=snapshot_engine.get_current_snapshot() if snapshot_engine else None,
        agents_registered=len(agent_coordinator.agents) if agent_coordinator else 0,
        mutations_today=len(governance_engine.mutation_log) if governance_engine else 0,
        rollbacks_today=0,  # Would track from mutation results
        invariant_violations=0,  # Would track from invariant checks
        uptime_seconds=uptime
    )


# ============================================================================
# MUTATION ENDPOINTS
# ============================================================================

@app.post("/mutations/execute", response_model=MutationResult)
async def execute_mutation(agent_id: str, mutation: MutationRequest):
    """Execute a mutation directly (for simple cases)"""
    if not mutation_executor:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    result = await mutation_executor.execute(agent_id, mutation)
    return result


@app.get("/mutations/pending")
async def get_pending_mutations():
    """Get mutations pending human approval"""
    if not governance_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    return governance_engine.get_pending_approvals()


@app.post("/mutations/approve")
async def approve_mutation(request: ApprovalRequest):
    """Human approval for a pending mutation"""
    if not governance_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    success = governance_engine.approve_pending(request.mutation_id, request.approval_token)
    if not success:
        raise HTTPException(status_code=404, detail="Mutation not found or not pending")
    
    return {"status": "approved", "mutation_id": request.mutation_id}


@app.post("/mutations/reject")
async def reject_mutation(request: RejectionRequest):
    """Human rejection for a pending mutation"""
    if not governance_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    success = governance_engine.reject_pending(request.mutation_id, request.reason)
    if not success:
        raise HTTPException(status_code=404, detail="Mutation not found or not pending")
    
    return {"status": "rejected", "mutation_id": request.mutation_id}


@app.get("/mutations/log")
async def get_mutation_log(limit: int = 50):
    """Get mutation log"""
    if not governance_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    return governance_engine.get_mutation_log(limit)


# ============================================================================
# SNAPSHOT ENDPOINTS
# ============================================================================

@app.get("/snapshots")
async def list_snapshots(limit: int = 20):
    """List recent snapshots"""
    if not snapshot_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    return [s.model_dump() for s in snapshot_engine.list_snapshots(limit)]


@app.get("/snapshots/{snapshot_id}")
async def get_snapshot(snapshot_id: str):
    """Get snapshot details"""
    if not snapshot_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    snapshot = snapshot_engine.get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    return snapshot.model_dump()


@app.post("/snapshots/create")
async def create_snapshot(trigger: str = "manual"):
    """Create a manual snapshot"""
    if not snapshot_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    snapshot = snapshot_engine.create_snapshot(trigger)
    return snapshot.model_dump()


@app.post("/snapshots/{snapshot_id}/restore")
async def restore_snapshot(snapshot_id: str, reason: str = "manual restore"):
    """Restore to a specific snapshot"""
    if not snapshot_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    try:
        snapshot_engine.restore_snapshot(snapshot_id)
        return {"status": "restored", "snapshot_id": snapshot_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CAPABILITY ENDPOINTS
# ============================================================================

@app.post("/agents/register")
async def register_agent(request: RegisterAgentRequest):
    """Register a new agent"""
    if not capability_engine or not agent_coordinator:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    # Register in capability engine
    manifest = capability_engine.register_agent(
        request.agent_id,
        request.capabilities
    )
    
    # Register in coordinator
    registration = agent_coordinator.register_agent(
        request.agent_id,
        request.role,
        request.dsid,
        request.public_key,
        request.capabilities
    )
    
    return {
        "agent_id": request.agent_id,
        "role": request.role.value,
        "capabilities": len(manifest.capabilities)
    }


@app.get("/agents")
async def list_agents():
    """List all registered agents with their status"""
    if not agent_coordinator or not capability_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    agents_list = []
    for agent_id, registration in agent_coordinator.agents.items():
        manifest = capability_engine.get_manifest(agent_id)
        stats = capability_engine.get_agent_stats(agent_id) or {}
        
        agents_list.append({
            "id": agent_id,
            "name": getattr(registration, "name", agent_id),
            "type": getattr(registration, "role", "general"),
            "status": "active" if getattr(registration, "active", True) else "idle",
            "tasks_completed": stats.get("total_mutations", 0),
            "uptime": "99.9%",
            "cpu_usage": 0,
            "memory_usage": 0,
            "last_task": stats.get("last_mutation", "Waiting..."),
            "capabilities": len(manifest.capabilities) if manifest else 0,
            "trust_score": stats.get("avg_trust", 0.5),
        })
    
    return {"agents": agents_list, "total": len(agents_list)}


@app.get("/agents/{agent_id}/capabilities")
async def get_agent_capabilities(agent_id: str):
    """Get agent capabilities and trust scores"""
    if not capability_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    manifest = capability_engine.get_manifest(agent_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return {
        "agent_id": agent_id,
        "custom_capabilities": getattr(manifest, "custom_capabilities", {}) or {},
        "capabilities": {
            k: {
                "trust": v.trust,
                "requires_approval": v.requires_approval,
                "is_disabled": v.is_disabled,
                "is_revoked": v.is_revoked,
                "successes": v.successes,
                "failures": v.failures
            }
            for k, v in manifest.capabilities.items()
        }
    }


@app.get("/agents/{agent_id}/stats")
async def get_agent_stats(agent_id: str):
    """Get agent statistics"""
    if not capability_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    stats = capability_engine.get_agent_stats(agent_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return stats


# ============================================================================
# PHYSICS BRIDGE ENDPOINTS
# ============================================================================

@app.get("/physics/bridge/status")
async def get_physics_bridge_status():
    """Get physics bridge status and recent actions"""
    bridge = get_physics_bridge()
    if not bridge:
        raise HTTPException(status_code=503, detail="Physics bridge not initialized")
    
    return bridge.get_status()


@app.post("/physics/bridge/evaluate")
async def evaluate_physics_state():
    """Manually trigger physics evaluation"""
    bridge = get_physics_bridge()
    if not bridge:
        raise HTTPException(status_code=503, detail="Physics bridge not initialized")
    
    actions = await bridge.evaluate_physics_state()
    success = await bridge.execute_actions(actions)
    
    return {
        "evaluation_timestamp": datetime.utcnow().isoformat(),
        "actions_generated": len(actions),
        "actions_executed": success,
        "actions": [
            {
                "type": a.action_type,
                "target": a.target,
                "severity": a.severity,
                "reason": a.reason,
                "physics_trigger": a.physics_trigger
            }
            for a in actions
        ]
    }



# ============================================================================
# GOVERNANCE-AS-A-SERVICE API (Phase 3.1)
# ============================================================================

class GovernanceEvaluateRequest(BaseModel):
    """Request to evaluate an agent action against governance rules."""
    agent_id: str
    action_type: str  # e.g. "http_request", "file_write", "code_execute", "memory_write"
    action_details: Dict[str, Any]  # Action-specific parameters
    context: Optional[Dict[str, Any]] = None  # Optional context (user info, session info)

class GovernanceEvaluateResponse(BaseModel):
    """Governance evaluation result."""
    allowed: bool
    risk_level: str  # low, medium, high, critical
    explanation: str
    rules_checked: int
    violations: List[Dict[str, Any]]  # List of rule violations found
    recommendations: List[str]  # Suggestions for making the action compliant
    evaluation_ms: int

@app.post("/governance/evaluate", response_model=GovernanceEvaluateResponse)
async def governance_evaluate(request: GovernanceEvaluateRequest):
    """Evaluate an agent action against governance rules WITHOUT executing it.
    
    This is the public Governance-as-a-Service API. External platforms can use
    this to check if an action would be allowed before taking it.
    
    Example:
        POST /governance/evaluate
        {
            "agent_id": "abc-123",
            "action_type": "http_request",
            "action_details": {"url": "https://api.stripe.com/charges", "method": "POST"},
            "context": {"user_id": "user-456"}
        }
    
    Returns whether the action is allowed, risk level, and any violations.
    """
    import time
    start = time.time()
    
    violations = []
    recommendations = []
    rules_checked = 0
    risk_level = "low"
    allowed = True
    
    action_type = request.action_type
    details = request.action_details or {}
    ctx = request.context or {}
    
    # ── Rule 1: Kill switch check ──
    rules_checked += 1
    if kill_switch and kill_switch.is_killed:
        allowed = False
        risk_level = "critical"
        violations.append({
            "rule": "kill_switch",
            "message": "Platform kill switch is active. All mutations are blocked.",
        })
    
    # ── Rule 2: Agent registration check ──
    rules_checked += 1
    if governance_engine:
        known = governance_engine.registered_agents.get(request.agent_id)
        if not known:
            violations.append({
                "rule": "agent_registration",
                "message": f"Agent '{request.agent_id}' is not registered with RARA governance.",
            })
            recommendations.append("Register the agent via POST /agents/register before executing actions.")
    
    # ── Rule 3: Capability check ──
    rules_checked += 1
    if capability_enforcer:
        try:
            cap_result = capability_enforcer.check_capability(
                request.agent_id, action_type, details
            )
            if not cap_result.get("allowed", True):
                allowed = False
                risk_level = max(risk_level, "high", key=lambda x: ["low","medium","high","critical"].index(x))
                violations.append({
                    "rule": "capability_enforcement",
                    "message": cap_result.get("reason", "Action exceeds agent capabilities"),
                })
        except Exception:
            pass  # If enforcer not configured for this agent, skip
    
    # ── Rule 4: Blast radius estimation ──
    rules_checked += 1
    blast_radius = "low"
    if action_type in ("file_write", "file_delete", "code_execute", "database_write"):
        blast_radius = "medium"
        if details.get("path", "").startswith("/") or details.get("sudo"):
            blast_radius = "high"
    if action_type in ("http_request",) and details.get("method", "GET").upper() in ("POST", "PUT", "DELETE", "PATCH"):
        blast_radius = "medium"
    
    if blast_radius in ("high", "critical"):
        risk_level = max(risk_level, blast_radius, key=lambda x: ["low","medium","high","critical"].index(x))
        if blast_radius == "high":
            recommendations.append("This action has high blast radius. Consider requiring human approval.")
    
    # ── Rule 5: Rate limit check ──
    rules_checked += 1
    # Simple check - in production this would query actual rate state
    
    # ── Rule 6: Invariant checks ──
    rules_checked += 1
    if invariant_engine:
        try:
            inv_result = invariant_engine.check_pre_conditions(
                request.agent_id, action_type, details
            )
            if inv_result and not inv_result.get("passed", True):
                allowed = False
                for v in inv_result.get("violations", []):
                    violations.append({
                        "rule": "invariant",
                        "message": str(v),
                    })
        except Exception:
            pass
    
    # Determine final risk
    if violations and allowed:
        # Soft violations (warnings, not blockers)
        risk_level = max(risk_level, "medium", key=lambda x: ["low","medium","high","critical"].index(x))
    if not allowed:
        risk_level = max(risk_level, "high", key=lambda x: ["low","medium","high","critical"].index(x))
    
    duration_ms = int((time.time() - start) * 1000)
    
    explanation = "Action is allowed." if allowed else f"Action blocked: {'; '.join(v['message'] for v in violations[:3])}"
    
    return GovernanceEvaluateResponse(
        allowed=allowed,
        risk_level=risk_level,
        explanation=explanation,
        rules_checked=rules_checked,
        violations=violations,
        recommendations=recommendations,
        evaluation_ms=duration_ms,
    )


@app.get("/governance/rules")
async def list_governance_rules():
    """List all active governance rules and their descriptions.
    
    Useful for external platforms to understand what rules are enforced.
    """
    rules = [
        {"id": "kill_switch", "name": "Kill Switch", "description": "Global emergency stop for all agent mutations", "active": bool(kill_switch)},
        {"id": "capability_enforcement", "name": "Capability Enforcement", "description": "Agents can only use capabilities they are registered for", "active": bool(capability_enforcer)},
        {"id": "blast_radius", "name": "Blast Radius Analysis", "description": "Estimates impact scope of destructive actions", "active": True},
        {"id": "rate_limiting", "name": "Rate Limiting", "description": "Per-agent action rate limits", "active": True},
        {"id": "invariant_checks", "name": "Invariant Checks", "description": "Pre/post condition verification for state mutations", "active": bool(invariant_engine)},
        {"id": "human_approval", "name": "Human Approval Gate", "description": "High-risk actions require human approval", "active": bool(governance_engine)},
    ]
    return {"rules": rules, "total": len(rules)}


# ============================================================================
# IRREVERSIBILITY AUTHORITY ENDPOINTS
# ============================================================================

@app.get("/irreversibility/status")
async def get_irreversibility_status():
    """Get irreversibility authority status"""
    authority = get_irreversibility_authority()
    if not authority:
        raise HTTPException(status_code=503, detail="Irreversibility authority not initialized")
    
    return authority.get_status()


@app.get("/irreversibility/health")
async def irreversibility_health_check():
    """Health check for irreversibility authority"""
    authority = get_irreversibility_authority()
    if not authority:
        raise HTTPException(status_code=503, detail="Irreversibility authority not initialized")
    
    return authority.health_check()


@app.post("/irreversibility/request-auth")
async def request_authorization(
    agent_id: str,
    effect_type: str,
    effect_payload: Dict[str, Any],
    timeout_ms: Optional[int] = None
):
    """Request authorization for irreversible effect"""
    authority = get_irreversibility_authority()
    if not authority:
        raise HTTPException(status_code=503, detail="Irreversibility authority not initialized")
    
    response = await authority.request_effect_authorization(
        agent_id=agent_id,
        effect_type=effect_type,
        effect_payload=effect_payload,
        timeout_ms=timeout_ms
    )
    
    return response.to_dict()


@app.post("/irreversibility/execute-effect")
async def execute_irreversible_effect(
    agent_id: str,
    effect_type: str,
    effect_payload: Dict[str, Any],
    timeout_ms: Optional[int] = None,
    require_quorum: Optional[bool] = None
):
    """Execute irreversible effect with full authorization flow"""
    authority = get_irreversibility_authority()
    if not authority:
        raise HTTPException(status_code=503, detail="Irreversibility authority not initialized")
    
    # Mock effect executor for demonstration
    async def mock_effect_executor():
        return {"result": f"Effect {effect_type} executed successfully"}
    
    result = await authority.execute_irreversible_effect(
        agent_id=agent_id,
        effect_type=effect_type,
        effect_payload=effect_payload,
        effect_executor=mock_effect_executor,
        timeout_ms=timeout_ms,
        require_quorum=require_quorum
    )
    
    return result.to_dict()


@app.post("/irreversibility/create-epoch")
async def create_epoch(
    commit_window_ms: Optional[int] = None,
    max_effects: Optional[int] = None,
    created_by: str = "api"
):
    """Create new epoch"""
    authority = get_irreversibility_authority()
    if not authority:
        raise HTTPException(status_code=503, detail="Irreversibility authority not initialized")
    
    epoch_id = authority.create_epoch(
        commit_window_ms=commit_window_ms,
        max_effects=max_effects,
        created_by=created_by
    )
    
    if not epoch_id:
        raise HTTPException(status_code=500, detail="Failed to create epoch")
    
    return {"epoch_id": epoch_id, "created_by": created_by}


@app.post("/irreversibility/commit-epoch")
async def commit_epoch(force: bool = False):
    """Commit current epoch"""
    authority = get_irreversibility_authority()
    if not authority:
        raise HTTPException(status_code=503, detail="Irreversibility authority not initialized")
    
    success = authority.close_epoch(force=force)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to commit epoch")
    
    return {"success": True, "message": "Epoch committed successfully"}


@app.post("/irreversibility/propose-effect")
async def propose_irreversible_effect(
    agent_id: str,
    effect_type: str,
    effect_payload: Dict[str, Any],
    description: str = "",
    votes_required: Optional[int] = None
):
    """Propose effect for quorum approval"""
    authority = get_irreversibility_authority()
    if not authority:
        raise HTTPException(status_code=503, detail="Irreversibility authority not initialized")
    
    response = await authority.propose_quorum_effect(
        agent_id=agent_id,
        effect_type=effect_type,
        effect_payload=effect_payload,
        description=description,
        votes_required=votes_required
    )
    
    return response.to_dict()


@app.post("/irreversibility/vote-on-proposal")
async def vote_on_proposal(
    proposal_id: str,
    voter_id: str,
    vote_type: str,
    reason: str = ""
):
    """Vote on quorum proposal"""
    authority = get_irreversibility_authority()
    if not authority:
        raise HTTPException(status_code=503, detail="Irreversibility authority not initialized")
    
    result = await authority.vote_on_quorum_proposal(
        proposal_id=proposal_id,
        voter_id=voter_id,
        vote_type=vote_type,
        reason=reason
    )
    
    return result.to_dict()


@app.get("/irreversibility/effects")
async def list_effects():
    """List all registered irreversible effects"""
    registry = get_effect_registry()
    if not registry:
        raise HTTPException(status_code=503, detail="Effect registry not initialized")
    
    return {"effects": registry.list_effects()}


@app.get("/irreversibility/epochs")
async def list_epochs(limit: int = 100):
    """List epoch history"""
    epoch_auth = get_epoch_authority()
    if not epoch_auth:
        raise HTTPException(status_code=503, detail="Epoch authority not initialized")
    
    current_epoch = epoch_auth.get_current_epoch()
    history = epoch_auth.get_epoch_history(limit)
    
    return {
        "current_epoch": current_epoch.to_dict() if current_epoch else None,
        "history": [epoch.to_dict() for epoch in history]
    }


@app.get("/irreversibility/proposals")
async def list_proposals(limit: int = 100):
    """List quorum proposals"""
    quorum_auth = get_quorum_authority()
    if not quorum_auth:
        raise HTTPException(status_code=503, detail="Quorum authority not initialized")
    
    active = quorum_auth.get_active_proposals()
    history = quorum_auth.get_proposal_history(limit)
    
    return {
        "active_proposals": [prop.to_dict() for prop in active],
        "history": [prop.to_dict() for prop in history]
    }


@app.post("/irreversibility/cleanup")
async def cleanup_expired_resources():
    """Clean up expired resources"""
    authority = get_irreversibility_authority()
    if not authority:
        raise HTTPException(status_code=503, detail="Irreversibility authority not initialized")
    
    results = authority.cleanup_expired_resources()
    
    return {
        "cleanup_results": results,
        "total_cleaned": sum(results.values()),
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================================
# DISD PROTOCOL ENDPOINTS
# ============================================================================

@app.get("/disd/status")
async def get_disd_status():
    """Get DISD protocol status"""
    protocol = get_disd_protocol()
    if not protocol:
        raise HTTPException(status_code=503, detail="DISD protocol not initialized")
    
    return {
        "swarm_status": protocol.get_swarm_status().to_dict(),
        "statistics": protocol.get_statistics(),
        "router_status": protocol.router.get_status() if protocol.router else None,
        "transport_status": get_transport_manager().get_status() if get_transport_manager() else None
    }


@app.get("/disd/members")
async def get_swarm_members():
    """Get swarm members"""
    protocol = get_disd_protocol()
    if not protocol:
        raise HTTPException(status_code=503, detail="DISD protocol not initialized")
    
    members = protocol.get_members()
    return {
        "members": [member.to_dict() for member in members],
        "total_count": len(members)
    }


@app.get("/disd/proposals")
async def get_swarm_proposals():
    """Get swarm proposals"""
    protocol = get_disd_protocol()
    if not protocol:
        raise HTTPException(status_code=503, detail="DISD protocol not initialized")
    
    proposals = protocol.get_proposals()
    return {
        "proposals": proposals,
        "total_count": len(proposals)
    }


@app.post("/disd/join")
async def join_swarm(
    agent_id: str,
    agent_type: str = "general",
    capabilities: List[str] = [],
    endpoint: str = "",
    metadata: Dict[str, Any] = {}
):
    """Join swarm"""
    protocol = get_disd_protocol()
    if not protocol:
        raise HTTPException(status_code=503, detail="DISD protocol not initialized")
    
    success = await protocol.join_swarm(
        agent_id=agent_id,
        agent_type=agent_type,
        capabilities=capabilities,
        endpoint=endpoint,
        metadata=metadata
    )
    
    if success:
        return {"success": True, "message": f"Agent {agent_id} joined swarm"}
    else:
        raise HTTPException(status_code=500, detail="Failed to join swarm")


@app.post("/disd/leave")
async def leave_swarm(
    agent_id: str,
    reason: str = "",
    graceful: bool = True
):
    """Leave swarm"""
    protocol = get_disd_protocol()
    if not protocol:
        raise HTTPException(status_code=503, detail="DISD protocol not initialized")
    
    success = await protocol.leave_swarm(
        agent_id=agent_id,
        reason=reason,
        graceful=graceful
    )
    
    if success:
        return {"success": True, "message": f"Agent {agent_id} left swarm"}
    else:
        raise HTTPException(status_code=500, detail="Failed to leave swarm")


@app.post("/disd/propose")
async def propose_action(
    sender_id: str,
    action_type: str,
    action_payload: Dict[str, Any],
    quorum_required: int = 3,
    veto_threshold: float = 0.3,
    description: str = ""
):
    """Propose action to swarm"""
    protocol = get_disd_protocol()
    if not protocol:
        raise HTTPException(status_code=503, detail="DISD protocol not initialized")
    
    proposal_id = await protocol.propose_action(
        sender_id=sender_id,
        action_type=action_type,
        action_payload=action_payload,
        quorum_required=quorum_required,
        veto_threshold=veto_threshold,
        description=description
    )
    
    if proposal_id:
        return {
            "success": True,
            "proposal_id": proposal_id,
            "message": f"Proposal {proposal_id} created"
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to create proposal")


@app.post("/disd/vote")
async def vote_on_proposal(
    sender_id: str,
    proposal_id: str,
    vote_type: str,
    reason: str = "",
    weight: float = 1.0
):
    """Vote on proposal"""
    from .disd_message import VoteType
    
    protocol = get_disd_protocol()
    if not protocol:
        raise HTTPException(status_code=503, detail="DISD protocol not initialized")
    
    try:
        vote_enum = VoteType(vote_type.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid vote type: {vote_type}")
    
    success = await protocol.vote_on_proposal(
        sender_id=sender_id,
        proposal_id=proposal_id,
        vote_type=vote_enum,
        reason=reason,
        weight=weight
    )
    
    if success:
        return {"success": True, "message": f"Vote cast on proposal {proposal_id}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to cast vote")


@app.post("/disd/send-message")
async def send_disd_message(
    sender_id: str,
    message_type: str,
    target_agent: str,
    payload: Dict[str, Any]
):
    """Send DISD message to specific agent"""
    from .disd_message import DISDMessageType
    
    protocol = get_disd_protocol()
    if not protocol:
        raise HTTPException(status_code=503, detail="DISD protocol not initialized")
    
    try:
        msg_type = DISDMessageType(message_type.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid message type: {message_type}")
    
    # Create message based on type
    if msg_type == DISDMessageType.HEARTBEAT:
        message = DISDMessageFactory.create_heartbeat_message(
            sender_id=sender_id,
            agent_id=payload.get("agent_id", sender_id),
            status=payload.get("status", "active"),
            load=payload.get("load", 0.0),
            capabilities=payload.get("capabilities", [])
        )
    else:
        raise HTTPException(status_code=400, detail=f"Message type {message_type} not supported for direct sending")
    
    result = await protocol.router.send_to_agent(message, target_agent)
    
    return {
        "success": result.success,
        "message": result.message,
        "delivered_count": result.delivered_count,
        "failed_count": result.failed_count
    }


@app.post("/disd/broadcast-message")
async def broadcast_disd_message(
    sender_id: str,
    message_type: str,
    payload: Dict[str, Any]
):
    """Broadcast DISD message to all agents"""
    from .disd_message import DISDMessageType
    
    protocol = get_disd_protocol()
    if not protocol:
        raise HTTPException(status_code=503, detail="DISD protocol not initialized")
    
    try:
        msg_type = DISDMessageType(message_type.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid message type: {message_type}")
    
    # Create message based on type
    if msg_type == DISDMessageType.HEARTBEAT:
        message = DISDMessageFactory.create_heartbeat_message(
            sender_id=sender_id,
            agent_id=payload.get("agent_id", sender_id),
            status=payload.get("status", "active"),
            load=payload.get("load", 0.0),
            capabilities=payload.get("capabilities", [])
        )
    else:
        raise HTTPException(status_code=400, detail=f"Message type {message_type} not supported for broadcasting")
    
    result = await protocol.router.broadcast_message(message)
    
    return {
        "success": result.success,
        "message": result.message,
        "delivered_count": result.delivered_count,
        "failed_count": result.failed_count
    }


class AddCapabilityRequest(BaseModel):
    """Request to add a custom capability to an agent"""
    name: str
    description: str
    category: str = "custom"
    enabled: bool = True
    required_permissions: List[str] = []


class UpdateCapabilityRequest(BaseModel):
    """Request to update a capability"""
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    required_permissions: Optional[List[str]] = None


@app.post("/agents/{agent_id}/capabilities")
async def add_agent_capability(
    agent_id: str,
    capability: AddCapabilityRequest
):
    """Add a custom capability to an agent"""
    if not capability_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    manifest = capability_engine.get_manifest(agent_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Create capability ID from name
    cap_id = f"custom.{capability.name.lower().replace(' ', '_')}"
    
    # Check if capability already exists
    if cap_id in manifest.capabilities:
        raise HTTPException(status_code=409, detail="Capability already exists")
    
    # Add capability to manifest
    from .models import CapabilityScore, CapabilityType
    
    # For custom capabilities, we'll store them as a dict in the manifest
    # Since CapabilityType is an enum, we need to handle custom capabilities differently
    if not hasattr(manifest, 'custom_capabilities'):
        manifest.custom_capabilities = {}
    
    manifest.custom_capabilities[cap_id] = {
        "name": capability.name,
        "description": capability.description,
        "category": capability.category,
        "enabled": capability.enabled,
        "required_permissions": capability.required_permissions,
        "created_at": datetime.utcnow().isoformat()
    }
    
    # Save state
    capability_engine._save_state()
    
    logger.info(f"Added custom capability {cap_id} to agent {agent_id}")
    
    return {
        "id": cap_id,
        "agent_id": agent_id,
        "capability": manifest.custom_capabilities[cap_id]
    }


@app.put("/agents/{agent_id}/capabilities/{capability_id}")
async def update_agent_capability(
    agent_id: str,
    capability_id: str,
    capability: UpdateCapabilityRequest
):
    """Update an agent capability"""
    if not capability_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    manifest = capability_engine.get_manifest(agent_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if not hasattr(manifest, 'custom_capabilities') or capability_id not in manifest.custom_capabilities:
        raise HTTPException(status_code=404, detail="Capability not found")
    
    # Update capability fields
    cap = manifest.custom_capabilities[capability_id]
    if capability.name is not None:
        cap["name"] = capability.name
    if capability.description is not None:
        cap["description"] = capability.description
    if capability.enabled is not None:
        cap["enabled"] = capability.enabled
    if capability.required_permissions is not None:
        cap["required_permissions"] = capability.required_permissions
    
    cap["updated_at"] = datetime.utcnow().isoformat()
    
    # Save state
    capability_engine._save_state()
    
    logger.info(f"Updated capability {capability_id} for agent {agent_id}")
    
    return {
        "id": capability_id,
        "agent_id": agent_id,
        "capability": cap
    }


@app.delete("/agents/{agent_id}/capabilities/{capability_id}")
async def delete_agent_capability(
    agent_id: str,
    capability_id: str
):
    """Delete a custom capability from an agent"""
    if not capability_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    manifest = capability_engine.get_manifest(agent_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if not hasattr(manifest, 'custom_capabilities') or capability_id not in manifest.custom_capabilities:
        raise HTTPException(status_code=404, detail="Capability not found")
    
    # Delete capability
    del manifest.custom_capabilities[capability_id]
    
    # Save state
    capability_engine._save_state()
    
    logger.info(f"Deleted capability {capability_id} from agent {agent_id}")
    
    return {"message": "Capability deleted successfully"}


# ============================================================================
# COORDINATION ENDPOINTS
# ============================================================================

@app.post("/proposals/submit")
async def submit_proposal(request: SubmitProposalRequest):
    """Submit a mutation proposal (planner only)"""
    if not agent_coordinator:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    try:
        proposal = await agent_coordinator.submit_proposal(
            request.planner_id,
            request.mutation,
            request.risk_score,
            request.alternatives_considered
        )
        return {"proposal_id": proposal.proposal_id, "status": "submitted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/proposals/verify")
async def verify_proposal(request: VerifyProposalRequest):
    """Verify a proposal (verifier only)"""
    if not agent_coordinator:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    try:
        proposal = await agent_coordinator.verify_proposal(
            request.verifier_id,
            request.proposal_id,
            request.approved,
            request.reason
        )
        return {"proposal_id": proposal.proposal_id, "status": proposal.verification_status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# ENHANCED DISD PROTOCOL ENDPOINTS
# ============================================================================

@app.get("/enhanced-disd/status")
async def get_enhanced_disd_status():
    """Get enhanced DISD protocol status with cryptographic metrics"""
    protocol = get_enhanced_disd_protocol()
    if not protocol:
        raise HTTPException(status_code=503, detail="Enhanced DISD protocol not initialized")
    
    return {
        "swarm_status": protocol.get_enhanced_swarm_status().to_dict(),
        "statistics": protocol.get_enhanced_statistics(),
        "router_status": protocol.router.get_enhanced_status() if protocol.router else None,
        "security_audit": protocol.get_security_audit_report()
    }


@app.get("/enhanced-disd/security-report")
async def get_security_audit_report():
    """Get comprehensive security audit report"""
    protocol = get_enhanced_disd_protocol()
    if not protocol:
        raise HTTPException(status_code=503, detail="Enhanced DISD protocol not initialized")
    
    return protocol.get_security_audit_report()


@app.post("/enhanced-disd/join")
async def join_enhanced_swarm(
    agent_id: str,
    agent_type: str = "general",
    capabilities: List[str] = [],
    endpoint: str = "",
    metadata: Dict[str, Any] = {}
):
    """Join enhanced swarm with cryptographic verification"""
    protocol = get_enhanced_disd_protocol()
    if not protocol:
        raise HTTPException(status_code=503, detail="Enhanced DISD protocol not initialized")
    
    success = await protocol.join_swarm(
        agent_id=agent_id,
        agent_type=agent_type,
        capabilities=capabilities,
        endpoint=endpoint,
        metadata=metadata
    )
    
    if success:
        return {"success": True, "message": f"Agent {agent_id} joined enhanced swarm"}
    else:
        raise HTTPException(status_code=500, detail="Failed to join enhanced swarm")


@app.post("/enhanced-disd/propose")
async def propose_enhanced_action(
    sender_id: str,
    action_type: str,
    action_payload: Dict[str, Any],
    quorum_required: int = 3,
    veto_threshold: float = 0.3,
    description: str = ""
):
    """Propose enhanced action with cryptographic binding"""
    protocol = get_enhanced_disd_protocol()
    if not protocol:
        raise HTTPException(status_code=503, detail="Enhanced DISD protocol not initialized")
    
    proposal_id = await protocol.propose_action_enhanced(
        sender_id=sender_id,
        action_type=action_type,
        action_payload=action_payload,
        quorum_required=quorum_required,
        veto_threshold=veto_threshold,
        description=description
    )
    
    if proposal_id:
        return {
            "success": True,
            "proposal_id": proposal_id,
            "message": f"Enhanced proposal {proposal_id} created"
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to create enhanced proposal")


@app.post("/enhanced-disd/vote")
async def vote_on_enhanced_proposal(
    sender_id: str,
    proposal_id: str,
    vote_type: str,
    reason: str = "",
    weight: float = 1.0
):
    """Vote on enhanced proposal with cryptographic receipt verification"""
    from .disd_message import VoteType
    
    protocol = get_enhanced_disd_protocol()
    if not protocol:
        raise HTTPException(status_code=503, detail="Enhanced DISD protocol not initialized")
    
    try:
        vote_enum = VoteType(vote_type.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid vote type: {vote_type}")
    
    success = await protocol.vote_on_proposal_enhanced(
        sender_id=sender_id,
        proposal_id=proposal_id,
        vote_type=vote_enum,
        reason=reason,
        weight=weight
    )
    
    if success:
        return {"success": True, "message": f"Enhanced vote cast on proposal {proposal_id}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to cast enhanced vote")


@app.get("/enhanced-disd/receipt-verification")
async def verify_message_receipts(message_id: str):
    """Verify all receipts for a specific message"""
    router = get_enhanced_disd_router()
    if not router:
        raise HTTPException(status_code=503, detail="Enhanced DISD router not initialized")
    
    verification_results = router.verify_message_receipts(message_id)
    
    return {
        "message_id": message_id,
        "verification_results": verification_results,
        "total_receipts": len(verification_results),
        "verified_receipts": sum(1 for verified in verification_results.values() if verified),
        "verification_rate": sum(1 for verified in verification_results.values() if verified) / max(len(verification_results), 1)
    }


@app.get("/enhanced-disd/chain-integrity")
async def check_chain_integrity(epoch_id: str = None):
    """Check receipt chain integrity"""
    log_manager = get_receipt_log_manager()
    if not log_manager:
        raise HTTPException(status_code=503, detail="Receipt log manager not initialized")
    
    if epoch_id:
        # Check specific epoch
        integrity = log_manager.verify_epoch_chain(epoch_id)
        stats = log_manager.get_epoch_statistics(epoch_id)
        return {
            "epoch_id": epoch_id,
            "chain_integrity": integrity,
            "statistics": stats
        }
    else:
        # Check all epochs
        return log_manager.get_all_epoch_statistics()


@app.get("/enhanced-disd/suspicion-scores")
async def get_suspicion_scores():
    """Get agent suspicion scores"""
    failure_detector = get_failure_detection_system()
    if not failure_detector:
        raise HTTPException(status_code=503, detail="Failure detection system not initialized")
    
    scores = failure_detector.get_agent_suspicion_scores()
    suspicious_agents = [
        agent_id for agent_id, score in scores.items()
        if score >= failure_detector.suspicion_threshold
    ]
    
    return {
        "suspicion_scores": scores,
        "suspicious_agents": suspicious_agents,
        "suspicion_threshold": failure_detector.suspicion_threshold,
        "total_agents": len(scores),
        "suspicious_count": len(suspicious_agents)
    }


@app.post("/enhanced-disd/reset-suspicion")
async def reset_agent_suspicion(agent_id: str):
    """Reset suspicion score for an agent"""
    failure_detector = get_failure_detection_system()
    if not failure_detector:
        raise HTTPException(status_code=503, detail="Failure detection system not initialized")
    
    failure_detector.reset_suspicion_score(agent_id)
    
    return {"success": True, "message": f"Suspicion score reset for agent {agent_id}"}


@app.post("/enhanced-disd/adversarial-tests")
async def run_adversarial_tests():
    """Run comprehensive adversarial test suite"""
    try:
        results = await run_adversarial_test_suite()
        
        return {
            "success": True,
            "test_results": results,
            "summary": results["test_summary"],
            "security_assessment": results["security_assessment"],
            "recommendations": results["recommendations"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Adversarial test suite failed: {str(e)}")


@app.post("/proposals/execute")
async def execute_proposal(request: ExecuteProposalRequest):
    """Execute an approved proposal (executor only)"""
    if not agent_coordinator or not mutation_executor:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    try:
        result = await agent_coordinator.execute_proposal(
            request.executor_id,
            request.proposal_id,
            mutation_executor.execute
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/proposals/pending")
async def get_pending_proposals():
    """Get pending proposals"""
    if not agent_coordinator:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    return [
        {
            "proposal_id": p.proposal_id,
            "planner_id": p.planner_id,
            "capability": p.mutation.capability.value,
            "target": p.mutation.target,
            "risk_score": p.risk_score
        }
        for p in agent_coordinator.get_pending_proposals()
    ]


@app.get("/coordination/stats")
async def get_coordination_stats():
    """Get coordination statistics"""
    if not agent_coordinator:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    return agent_coordinator.get_stats()


# ============================================================================
# INVARIANT ENDPOINTS
# ============================================================================

@app.post("/invariants/check")
async def check_invariants():
    """Run all invariant checks"""
    if not invariant_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    try:
        all_passed, results = await invariant_engine.check_all_invariants()
        return {
            "all_passed": all_passed,
            "results": [r.model_dump() for r in results]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/invariants/results")
async def get_invariant_results():
    """Get last invariant check results"""
    if not invariant_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    return {
        k: v.model_dump()
        for k, v in invariant_engine.get_last_results().items()
    }


# ============================================================================
# GOVERNANCE ENDPOINTS
# ============================================================================

@app.get("/governance/state")
async def get_governance_state():
    """Get current governance state from Hash Sphere"""
    if not governance_engine:
        return {"status": "not_initialized", "governance": "offline", "kill_switch": "unknown"}
    try:
        state = await governance_engine.get_current_state()
        return state
    except Exception as e:
        ks_status = "unknown"
        if kill_switch:
            ks_status = "frozen" if kill_switch.is_frozen else "active"
        return {
            "status": "degraded",
            "governance": "active",
            "kill_switch": ks_status,
            "state_physics": "unreachable",
            "error": str(e),
            "agents": len(getattr(agent_coordinator, "agents", {})) if agent_coordinator else 0,
        }
async def get_governance_state():
    """Get current governance state from Hash Sphere"""
    if not governance_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    try:
        return await governance_engine.get_current_state()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/governance/explain")
async def generate_explanation(mutation: MutationRequest):
    """Generate explainability artifact for a mutation"""
    if not governance_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    artifact = governance_engine.generate_explainability(mutation)
    return artifact.model_dump()


# ============================================================================
# CONTROL ENDPOINTS
# ============================================================================

@app.post("/control/freeze")
async def freeze_system(actor: str = "api", reason: str = "Manual freeze"):
    """Freeze system - enter observe-only mode"""
    if not kill_switch:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    kill_switch.freeze(trigger=KillSwitchTrigger.API, actor=actor, reason=reason)
    mutation_executor.freeze()
    return {"status": "frozen", "message": "System in observe-only mode"}


@app.post("/control/unfreeze")
async def unfreeze_system(actor: str = "api", reason: str = "Manual unfreeze"):
    """Unfreeze system - enable mutations"""
    if not kill_switch:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    kill_switch.unfreeze(trigger=KillSwitchTrigger.API, actor=actor, reason=reason)
    mutation_executor.unfreeze()
    return {"status": "running", "message": "Mutations enabled"}


@app.post("/control/emergency-stop")
async def emergency_stop(actor: str = "api", reason: str = "Emergency stop"):
    """Emergency stop - full system halt. Only human can reset."""
    if not kill_switch:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    kill_switch.emergency_stop(trigger=KillSwitchTrigger.API, actor=actor, reason=reason)
    mutation_executor.freeze()
    return {"status": "emergency_stop", "message": "EMERGENCY STOP - only human can reset"}


class EmergencyResetRequest(BaseModel):
    actor: str
    reason: str
    confirmation_token: str


@app.post("/control/emergency-reset")
async def emergency_reset(request: EmergencyResetRequest):
    """Reset from emergency stop. Requires confirmation token."""
    if not kill_switch:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    success = kill_switch.reset_emergency(
        actor=request.actor,
        reason=request.reason,
        confirmation_token=request.confirmation_token
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Emergency reset failed - invalid token or not in emergency state")
    
    return {"status": "frozen", "message": "Emergency reset complete - system frozen, manual unfreeze required"}


@app.post("/control/reset-budgets")
async def reset_budgets():
    """Reset daily budgets for all agents"""
    if not capability_engine:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    capability_engine.reset_daily_budgets()
    return {"status": "reset", "message": "All agent budgets reset"}


@app.get("/control/kill-switch/status")
async def get_kill_switch_status():
    """Get kill switch status"""
    if not kill_switch:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    return kill_switch.get_status()


@app.get("/control/kill-switch/events")
async def get_kill_switch_events(limit: int = 50):
    """Get kill switch event history"""
    if not kill_switch:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    return kill_switch.get_events(limit)


# ============================================================================
# INVARIANT CLASS ENDPOINTS
# ============================================================================

@app.post("/invariants/check-by-class")
async def check_invariants_by_class(
    mutation_data: dict,
    target: str,
    services: List[str] = None
):
    """Run invariant checks by class (structural, semantic, temporal)"""
    if not invariant_checker:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    all_passed, results = invariant_checker.check_all(
        mutation_data=mutation_data,
        target=target,
        services=services or [],
        graph_data=None  # Would come from Code Visualizer
    )
    
    return {
        "all_passed": all_passed,
        "environment": invariant_checker.environment.value,
        "results": [r.model_dump() for r in results]
    }


@app.get("/invariants/definitions")
async def get_invariant_definitions():
    """Get all invariant definitions by class"""
    return {
        "structural": [inv.model_dump() for inv in STRUCTURAL_INVARIANTS],
        "semantic": [inv.model_dump() for inv in SEMANTIC_INVARIANTS],
        "temporal": [inv.model_dump() for inv in TEMPORAL_INVARIANTS]
    }


@app.get("/invariants/summary")
async def get_invariant_summary():
    """Get invariant check summary"""
    if not invariant_checker:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    return invariant_checker.get_summary()


# ============================================================================
# COMPLIANCE ENDPOINTS
# ============================================================================

@app.get("/compliance/policy")
async def get_compliance_policy():
    """Get current compliance policy"""
    policy = get_policy(ENVIRONMENT)
    return policy.model_dump()


@app.get("/compliance/policies")
async def get_all_policies():
    """Get all available compliance policies"""
    return {k: v.model_dump() for k, v in COMPLIANCE_POLICIES.items()}


@app.get("/compliance/requirements/eu-ai-act")
async def get_eu_ai_act_requirements():
    """Get EU AI Act requirement mappings"""
    return [req.model_dump() for req in EU_AI_ACT_REQUIREMENTS]


@app.get("/compliance/requirements/soc2")
async def get_soc2_controls():
    """Get SOC2 control mappings"""
    return [ctrl.model_dump() for ctrl in SOC2_CONTROLS]


@app.get("/compliance/report")
async def get_compliance_report():
    """Get compliance report"""
    if not compliance_verifier:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    return compliance_verifier.get_compliance_report()


@app.get("/compliance/audit-trail")
async def get_audit_trail():
    """Get audit trail for compliance"""
    if not compliance_verifier:
        raise HTTPException(status_code=503, detail="RARA not initialized")
    
    return compliance_verifier.export_for_audit()


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8093)
