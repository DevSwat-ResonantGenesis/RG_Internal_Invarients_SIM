"""
RARA Data Models - Mutation Schema, Capability Grammar, Snapshot Metadata
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum
import uuid


# ============================================================================
# CAPABILITY GRAMMAR
# ============================================================================

class CapabilityType(str, Enum):
    # Filesystem
    CREATE_FILE = "filesystem.create_file"
    UPDATE_FILE = "filesystem.update_file"
    DELETE_FILE = "filesystem.delete_file"
    MOVE_FILE = "filesystem.move_file"
    
    # Services
    RESTART_SERVICE = "services.restart_service"
    RELOAD_CONFIG = "services.reload_config"
    
    # Routing
    ADD_ROUTE = "routing.add_route"
    UPDATE_ROUTE = "routing.update_route"
    REMOVE_ROUTE = "routing.remove_route"
    
    # Workflows
    REGISTER_WORKFLOW = "workflows.register_workflow"
    UPDATE_WORKFLOW = "workflows.update_workflow"
    DISABLE_WORKFLOW = "workflows.disable_workflow"


class CapabilityScore(BaseModel):
    """Trust score for a capability - decays on failure, never auto-expands"""
    capability: CapabilityType
    trust: float = Field(default=1.0, ge=0.0, le=1.0)
    successes: int = 0
    failures: int = 0
    rollbacks: int = 0
    last_used: Optional[datetime] = None
    
    def update_success(self):
        """Trust increases slightly on success (capped at 1.0)"""
        self.trust = min(1.0, self.trust + 0.01)
        self.successes += 1
        self.last_used = datetime.utcnow()
    
    def update_failure(self):
        """Trust decreases on failure"""
        self.trust = max(0.0, self.trust - 0.10)
        self.failures += 1
        self.last_used = datetime.utcnow()
    
    def update_rollback(self):
        """Trust decreases more on rollback"""
        self.trust = max(0.0, self.trust - 0.10)
        self.rollbacks += 1
        self.last_used = datetime.utcnow()
    
    def update_human_reject(self):
        """Trust decreases significantly on human rejection"""
        self.trust = max(0.0, self.trust - 0.25)
        self.last_used = datetime.utcnow()
    
    @property
    def requires_approval(self) -> bool:
        return self.trust < 0.7
    
    @property
    def is_disabled(self) -> bool:
        return self.trust < 0.5
    
    @property
    def is_revoked(self) -> bool:
        return self.trust < 0.3


class CapabilityManifest(BaseModel):
    """Full capability manifest for an agent"""
    agent_id: str
    capabilities: Dict[str, CapabilityScore] = {}
    custom_capabilities: Dict[str, Dict[str, Any]] = {}  # Custom user-defined capabilities
    forbidden_paths: List[str] = [
        "/opt/resonant/core",
        "/opt/resonant/agent",
        "/etc",
        "/usr",
        "/bin"
    ]
    max_files_per_mutation: int = 25
    max_bytes_per_mutation: int = 5 * 1024 * 1024  # 5MB


# ============================================================================
# MUTATION SCHEMA
# ============================================================================

class OperationType(str, Enum):
    WRITE = "write"
    DELETE = "delete"
    MOVE = "move"
    RESTART = "restart"
    RELOAD = "reload"


class MutationOperation(BaseModel):
    """The actual operation to perform"""
    type: OperationType
    content: Optional[str] = None  # base64 encoded for writes
    mode: Optional[str] = "0644"
    source: Optional[str] = None  # for move operations
    destination: Optional[str] = None  # for move operations


class Precondition(BaseModel):
    """Condition that must be true before mutation"""
    type: str  # path_exists, service_stopped, file_hash, etc.
    target: str
    expected: Optional[Any] = None


class Postcondition(BaseModel):
    """Condition that must be true after mutation"""
    type: str  # file_hash_changed, service_healthy, route_reachable, etc.
    target: str
    expected: Optional[Any] = None


class MutationRequest(BaseModel):
    """Formal mutation request - the only way to change the system"""
    mutation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    actor: Literal["agent", "human"]
    capability: CapabilityType
    target: str  # file path or service name
    operation: MutationOperation
    preconditions: List[Precondition] = []
    postconditions: List[Postcondition] = []
    rationale: str = ""  # Why this mutation
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    requires_human: bool = False
    approval_token: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MutationResult(BaseModel):
    """Result of a mutation attempt"""
    mutation_id: str
    status: Literal["success", "failed", "rolled_back", "rejected", "pending_approval"]
    snapshot_id: Optional[str] = None
    error: Optional[str] = None
    rollback_id: Optional[str] = None
    executed_at: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: int = 0


# ============================================================================
# SNAPSHOT SCHEMA
# ============================================================================

class SnapshotMeta(BaseModel):
    """Metadata for a runtime snapshot"""
    id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    trigger: str  # mutation_id or "manual"
    hash: str  # SHA256 of snapshot contents
    previous: Optional[str] = None
    health: Literal["PASS", "FAIL", "UNKNOWN"] = "UNKNOWN"
    files_count: int = 0
    size_bytes: int = 0


class RollbackRequest(BaseModel):
    """Request to rollback to a specific snapshot"""
    snapshot_id: str
    reason: str
    actor: Literal["agent", "human", "system"]


# ============================================================================
# ECONOMIC THROTTLING
# ============================================================================

class MutationCost(BaseModel):
    """Cost model for a mutation"""
    cpu_cost: float = 0.0
    disk_cost: float = 0.0
    blast_radius: float = 0.0
    risk_score: float = 0.0
    
    @property
    def total_cost(self) -> float:
        return self.cpu_cost + self.disk_cost + self.blast_radius + self.risk_score


class AgentBudget(BaseModel):
    """Daily mutation budget for an agent"""
    agent_id: str
    daily_budget: float = 10.0
    spent_today: float = 0.0
    last_reset: datetime = Field(default_factory=datetime.utcnow)
    
    @property
    def remaining(self) -> float:
        return max(0.0, self.daily_budget - self.spent_today)
    
    @property
    def is_over_budget(self) -> bool:
        return self.spent_today >= self.daily_budget
    
    def spend(self, cost: float):
        self.spent_today += cost
    
    def reset(self):
        self.spent_today = 0.0
        self.last_reset = datetime.utcnow()


# ============================================================================
# MULTI-AGENT COORDINATION
# ============================================================================

class AgentRole(str, Enum):
    PLANNER = "planner"      # Propose mutations
    EXECUTOR = "executor"    # Execute approved mutations
    VERIFIER = "verifier"    # Run probes & invariants
    AUDITOR = "auditor"      # Log & score behavior


class AgentRegistration(BaseModel):
    """Registration for a coordinated agent"""
    agent_id: str
    role: AgentRole
    dsid: str
    public_key: str
    capabilities: List[CapabilityType] = []
    registered_at: datetime = Field(default_factory=datetime.utcnow)


class MutationProposal(BaseModel):
    """Proposal from planner to be verified and executed"""
    proposal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    planner_id: str
    mutation: MutationRequest
    risk_score: float = 0.0
    alternatives_considered: int = 0
    verification_status: Literal["pending", "approved", "rejected"] = "pending"
    verifier_id: Optional[str] = None
    executor_id: Optional[str] = None


# ============================================================================
# COMPLIANCE & GOVERNANCE
# ============================================================================

class ComplianceProfile(str, Enum):
    EU_AI_ACT = "eu_ai_act"
    SOC2 = "soc2"
    MINIMAL = "minimal"


class ExplainabilityArtifact(BaseModel):
    """Required explanation for every mutation (EU AI Act compliance)"""
    mutation_id: str
    why: str
    what: str
    risk: Literal["Low", "Medium", "High", "Critical"]
    impact: List[str]  # affected services
    alternatives_considered: int
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class GovernanceDecision(BaseModel):
    """Hash Sphere governance decision"""
    state_key: str
    current_hash: str
    proposed_hash: str
    mutation_type: str
    actor: str
    confidence: float
    blast_radius: List[str]
    decision: Literal["approved", "rejected", "pending_human"]
    reason: str


# ============================================================================
# GRAPH INVARIANTS
# ============================================================================

class GraphInvariant(str, Enum):
    REACHABILITY = "reachability"          # Every route reaches a handler
    NO_ORPHAN_HANDLERS = "no_orphan_handlers"  # Every handler has a route
    AUTH_BOUNDARY = "auth_boundary"        # No unauth->privileged edges
    NO_CYCLES = "no_cycles"                # No execution cycles without breaker
    CAPABILITY_ISOLATION = "capability_isolation"  # Agent nodes isolated from core


class InvariantCheckResult(BaseModel):
    """Result of checking a graph invariant"""
    invariant: GraphInvariant
    passed: bool
    violations: List[str] = []
    checked_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# SYSTEM STATE
# ============================================================================

class SystemState(str, Enum):
    RUNNING = "running"
    FROZEN = "frozen"      # Observe-only mode
    STOPPED = "stopped"
    RECOVERING = "recovering"


class RARAStatus(BaseModel):
    """Current status of the RARA system"""
    state: SystemState = SystemState.RUNNING
    active_mutation: Optional[str] = None
    last_snapshot: Optional[str] = None
    agents_registered: int = 0
    mutations_today: int = 0
    rollbacks_today: int = 0
    invariant_violations: int = 0
    uptime_seconds: int = 0
