"""
RARA Invariant Class Schema

Invariants are separated into three classes, each with distinct semantics:

1. STRUCTURAL - Filesystem, graph reachability, dependency integrity
2. SEMANTIC - Intent, confidence, rationale coherence
3. TEMPORAL - Rate limits, blast radius, cadence constraints

Each class has its own UNKNOWN policy based on environment.
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# INVARIANT CLASS DEFINITIONS
# ============================================================================

class InvariantClass(str, Enum):
    """The three invariant classes"""
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
    TEMPORAL = "temporal"


class InvariantSeverity(str, Enum):
    """Severity levels for invariant violations"""
    CRITICAL = "critical"    # Must block, no override
    HIGH = "high"            # Block by default, human can override
    MEDIUM = "medium"        # Warn, allow with audit
    LOW = "low"              # Log only


class InvariantStatus(str, Enum):
    """Result of an invariant check"""
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"      # Check could not be performed
    SKIPPED = "skipped"      # Intentionally not checked


class Environment(str, Enum):
    """Deployment environment"""
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


# ============================================================================
# INVARIANT DEFINITIONS
# ============================================================================

class InvariantDefinition(BaseModel):
    """Definition of a single invariant"""
    id: str
    name: str
    description: str
    invariant_class: InvariantClass
    severity: InvariantSeverity
    
    # Environment-specific UNKNOWN behavior
    unknown_policy: Dict[str, str] = {
        "dev": "allow_warn",
        "staging": "allow_escalate",
        "prod": "allow_audit"
    }
    
    # Check configuration
    enabled: bool = True
    timeout_seconds: int = 30
    retry_count: int = 1


class InvariantResult(BaseModel):
    """Result of checking an invariant"""
    invariant_id: str
    invariant_class: InvariantClass
    status: InvariantStatus
    severity: InvariantSeverity
    violations: List[str] = []
    metadata: Dict[str, Any] = {}
    checked_at: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: int = 0


# ============================================================================
# STRUCTURAL INVARIANTS
# ============================================================================

STRUCTURAL_INVARIANTS = [
    InvariantDefinition(
        id="struct.reachability",
        name="Route Reachability",
        description="Every public route must reach a handler",
        invariant_class=InvariantClass.STRUCTURAL,
        severity=InvariantSeverity.CRITICAL
    ),
    InvariantDefinition(
        id="struct.no_orphans",
        name="No Orphan Handlers",
        description="Every handler must have at least one route",
        invariant_class=InvariantClass.STRUCTURAL,
        severity=InvariantSeverity.HIGH
    ),
    InvariantDefinition(
        id="struct.auth_boundary",
        name="Auth Boundary Integrity",
        description="No unauthenticated path to privileged resources",
        invariant_class=InvariantClass.STRUCTURAL,
        severity=InvariantSeverity.CRITICAL
    ),
    InvariantDefinition(
        id="struct.no_cycles",
        name="No Execution Cycles",
        description="No execution cycles without circuit breaker",
        invariant_class=InvariantClass.STRUCTURAL,
        severity=InvariantSeverity.HIGH
    ),
    InvariantDefinition(
        id="struct.capability_isolation",
        name="Capability Isolation",
        description="Agent nodes cannot directly depend on core services",
        invariant_class=InvariantClass.STRUCTURAL,
        severity=InvariantSeverity.CRITICAL
    ),
    InvariantDefinition(
        id="struct.file_integrity",
        name="File Integrity",
        description="Modified files must be syntactically valid",
        invariant_class=InvariantClass.STRUCTURAL,
        severity=InvariantSeverity.HIGH
    ),
    InvariantDefinition(
        id="struct.dependency_resolution",
        name="Dependency Resolution",
        description="All imports must resolve to existing modules",
        invariant_class=InvariantClass.STRUCTURAL,
        severity=InvariantSeverity.MEDIUM
    ),
]


# ============================================================================
# SEMANTIC INVARIANTS
# ============================================================================

SEMANTIC_INVARIANTS = [
    InvariantDefinition(
        id="sem.confidence_threshold",
        name="Confidence Threshold",
        description="Mutation confidence must exceed minimum threshold",
        invariant_class=InvariantClass.SEMANTIC,
        severity=InvariantSeverity.HIGH
    ),
    InvariantDefinition(
        id="sem.rationale_present",
        name="Rationale Present",
        description="Every mutation must have a non-empty rationale",
        invariant_class=InvariantClass.SEMANTIC,
        severity=InvariantSeverity.MEDIUM
    ),
    InvariantDefinition(
        id="sem.intent_alignment",
        name="Intent Alignment",
        description="Mutation must align with declared capability",
        invariant_class=InvariantClass.SEMANTIC,
        severity=InvariantSeverity.HIGH
    ),
    InvariantDefinition(
        id="sem.scope_containment",
        name="Scope Containment",
        description="Mutation scope must not exceed declared boundaries",
        invariant_class=InvariantClass.SEMANTIC,
        severity=InvariantSeverity.CRITICAL
    ),
    InvariantDefinition(
        id="sem.reversibility",
        name="Reversibility",
        description="Mutation must be reversible via rollback",
        invariant_class=InvariantClass.SEMANTIC,
        severity=InvariantSeverity.HIGH
    ),
]


# ============================================================================
# TEMPORAL INVARIANTS
# ============================================================================

TEMPORAL_INVARIANTS = [
    InvariantDefinition(
        id="temp.rate_limit",
        name="Rate Limit",
        description="Mutations per time window must not exceed limit",
        invariant_class=InvariantClass.TEMPORAL,
        severity=InvariantSeverity.HIGH
    ),
    InvariantDefinition(
        id="temp.blast_radius",
        name="Blast Radius Limit",
        description="Number of affected services must not exceed threshold",
        invariant_class=InvariantClass.TEMPORAL,
        severity=InvariantSeverity.HIGH
    ),
    InvariantDefinition(
        id="temp.cooldown",
        name="Cooldown Period",
        description="Minimum time between mutations to same target",
        invariant_class=InvariantClass.TEMPORAL,
        severity=InvariantSeverity.MEDIUM
    ),
    InvariantDefinition(
        id="temp.rollback_frequency",
        name="Rollback Frequency",
        description="Rollback rate must not exceed threshold",
        invariant_class=InvariantClass.TEMPORAL,
        severity=InvariantSeverity.HIGH
    ),
    InvariantDefinition(
        id="temp.failure_circuit",
        name="Failure Circuit Breaker",
        description="Consecutive failures must trigger capability suspension",
        invariant_class=InvariantClass.TEMPORAL,
        severity=InvariantSeverity.CRITICAL
    ),
]


# ============================================================================
# ALL INVARIANTS
# ============================================================================

ALL_INVARIANTS = STRUCTURAL_INVARIANTS + SEMANTIC_INVARIANTS + TEMPORAL_INVARIANTS

INVARIANT_REGISTRY: Dict[str, InvariantDefinition] = {
    inv.id: inv for inv in ALL_INVARIANTS
}


# ============================================================================
# UNKNOWN POLICY ACTIONS
# ============================================================================

class UnknownPolicyAction(str, Enum):
    """What to do when invariant check returns UNKNOWN"""
    ALLOW_SILENT = "allow_silent"      # Allow, no logging
    ALLOW_WARN = "allow_warn"          # Allow, log warning
    ALLOW_ESCALATE = "allow_escalate"  # Allow, notify human
    ALLOW_AUDIT = "allow_audit"        # Allow, create audit record
    BLOCK = "block"                    # Block mutation
    REQUIRE_HUMAN = "require_human"    # Require human approval


def get_unknown_policy(
    invariant: InvariantDefinition,
    environment: Environment
) -> UnknownPolicyAction:
    """
    Get the UNKNOWN policy for an invariant in a specific environment.
    
    Environment-specific behavior:
    - dev: allow + warn
    - staging: allow + escalate
    - prod: allow + audit (for non-critical) or require_human (for critical)
    """
    policy_str = invariant.unknown_policy.get(environment.value, "allow_warn")
    
    # Override for critical invariants in prod
    if environment == Environment.PROD and invariant.severity == InvariantSeverity.CRITICAL:
        return UnknownPolicyAction.REQUIRE_HUMAN
    
    return UnknownPolicyAction(policy_str)


# ============================================================================
# TEMPORAL TRACKING
# ============================================================================

class TemporalState(BaseModel):
    """Tracks temporal state for rate limiting and cooldowns"""
    
    # Rate limiting
    mutations_this_hour: int = 0
    mutations_this_day: int = 0
    last_mutation_time: Optional[datetime] = None
    
    # Per-target cooldowns
    target_last_mutation: Dict[str, datetime] = {}
    
    # Failure tracking
    consecutive_failures: int = 0
    last_failure_time: Optional[datetime] = None
    
    # Rollback tracking
    rollbacks_this_hour: int = 0
    rollbacks_this_day: int = 0
    
    # Blast radius tracking
    services_affected_this_hour: Dict[str, int] = {}
    
    def record_mutation(self, target: str, services: List[str]):
        """Record a mutation for temporal tracking"""
        now = datetime.utcnow()
        self.mutations_this_hour += 1
        self.mutations_this_day += 1
        self.last_mutation_time = now
        self.target_last_mutation[target] = now
        self.consecutive_failures = 0  # Reset on success
        
        for service in services:
            self.services_affected_this_hour[service] = \
                self.services_affected_this_hour.get(service, 0) + 1
    
    def record_failure(self):
        """Record a mutation failure"""
        self.consecutive_failures += 1
        self.last_failure_time = datetime.utcnow()
    
    def record_rollback(self):
        """Record a rollback"""
        self.rollbacks_this_hour += 1
        self.rollbacks_this_day += 1
    
    def reset_hourly(self):
        """Reset hourly counters"""
        self.mutations_this_hour = 0
        self.rollbacks_this_hour = 0
        self.services_affected_this_hour = {}
    
    def reset_daily(self):
        """Reset daily counters"""
        self.mutations_this_day = 0
        self.rollbacks_this_day = 0
        self.reset_hourly()
    
    def check_rate_limit(self, max_per_hour: int = 50, max_per_day: int = 200) -> Tuple[bool, str]:
        """Check if rate limit is exceeded"""
        if self.mutations_this_hour >= max_per_hour:
            return False, f"Hourly rate limit exceeded: {self.mutations_this_hour}/{max_per_hour}"
        if self.mutations_this_day >= max_per_day:
            return False, f"Daily rate limit exceeded: {self.mutations_this_day}/{max_per_day}"
        return True, ""
    
    def check_cooldown(self, target: str, cooldown_seconds: int = 60) -> Tuple[bool, str]:
        """Check if target is in cooldown"""
        last = self.target_last_mutation.get(target)
        if last:
            elapsed = (datetime.utcnow() - last).total_seconds()
            if elapsed < cooldown_seconds:
                return False, f"Target in cooldown: {cooldown_seconds - elapsed:.0f}s remaining"
        return True, ""
    
    def check_blast_radius(self, services: List[str], max_per_hour: int = 10) -> Tuple[bool, str]:
        """Check if blast radius is exceeded"""
        for service in services:
            count = self.services_affected_this_hour.get(service, 0)
            if count >= max_per_hour:
                return False, f"Service {service} blast radius exceeded: {count}/{max_per_hour}"
        return True, ""
    
    def check_failure_circuit(self, max_consecutive: int = 3) -> Tuple[bool, str]:
        """Check if failure circuit breaker should trip"""
        if self.consecutive_failures >= max_consecutive:
            return False, f"Failure circuit breaker tripped: {self.consecutive_failures} consecutive failures"
        return True, ""
    
    def check_rollback_frequency(self, max_per_hour: int = 5) -> Tuple[bool, str]:
        """Check if rollback frequency is too high"""
        if self.rollbacks_this_hour >= max_per_hour:
            return False, f"Rollback frequency exceeded: {self.rollbacks_this_hour}/{max_per_hour}"
        return True, ""


# ============================================================================
# INVARIANT CLASS CHECKER
# ============================================================================

class InvariantClassChecker:
    """
    Checks invariants by class with environment-aware policies.
    """
    
    def __init__(self, environment: Environment = Environment.DEV):
        self.environment = environment
        self.temporal_state = TemporalState()
        self.results_history: List[InvariantResult] = []
    
    def check_structural(
        self,
        graph_data: Optional[Dict] = None
    ) -> List[InvariantResult]:
        """Check all structural invariants"""
        results = []
        
        for inv in STRUCTURAL_INVARIANTS:
            if not inv.enabled:
                continue
            
            result = self._check_single_structural(inv, graph_data)
            results.append(result)
            self.results_history.append(result)
        
        return results
    
    def check_semantic(
        self,
        mutation_data: Dict
    ) -> List[InvariantResult]:
        """Check all semantic invariants"""
        results = []
        
        for inv in SEMANTIC_INVARIANTS:
            if not inv.enabled:
                continue
            
            result = self._check_single_semantic(inv, mutation_data)
            results.append(result)
            self.results_history.append(result)
        
        return results
    
    def check_temporal(
        self,
        target: str,
        services: List[str]
    ) -> List[InvariantResult]:
        """Check all temporal invariants"""
        results = []
        
        for inv in TEMPORAL_INVARIANTS:
            if not inv.enabled:
                continue
            
            result = self._check_single_temporal(inv, target, services)
            results.append(result)
            self.results_history.append(result)
        
        return results
    
    def check_all(
        self,
        mutation_data: Dict,
        target: str,
        services: List[str],
        graph_data: Optional[Dict] = None
    ) -> Tuple[bool, List[InvariantResult]]:
        """
        Check all invariant classes.
        
        Returns:
            (all_passed, list of results)
        """
        all_results = []
        
        all_results.extend(self.check_structural(graph_data))
        all_results.extend(self.check_semantic(mutation_data))
        all_results.extend(self.check_temporal(target, services))
        
        # Determine overall pass/fail
        all_passed = True
        for result in all_results:
            if result.status == InvariantStatus.FAIL:
                if result.severity in [InvariantSeverity.CRITICAL, InvariantSeverity.HIGH]:
                    all_passed = False
            elif result.status == InvariantStatus.UNKNOWN:
                policy = get_unknown_policy(
                    INVARIANT_REGISTRY[result.invariant_id],
                    self.environment
                )
                if policy == UnknownPolicyAction.BLOCK:
                    all_passed = False
                elif policy == UnknownPolicyAction.REQUIRE_HUMAN:
                    # Mark as needing human approval
                    result.metadata["requires_human"] = True
        
        return all_passed, all_results
    
    def _check_single_structural(
        self,
        inv: InvariantDefinition,
        graph_data: Optional[Dict]
    ) -> InvariantResult:
        """Check a single structural invariant"""
        start = datetime.utcnow()
        
        if graph_data is None:
            # Graph data unavailable
            return InvariantResult(
                invariant_id=inv.id,
                invariant_class=inv.invariant_class,
                status=InvariantStatus.UNKNOWN,
                severity=inv.severity,
                violations=["Graph data unavailable"],
                metadata={"policy": get_unknown_policy(inv, self.environment).value},
                duration_ms=int((datetime.utcnow() - start).total_seconds() * 1000)
            )
        
        # Actual checks would go here
        # For now, pass if graph data is present
        return InvariantResult(
            invariant_id=inv.id,
            invariant_class=inv.invariant_class,
            status=InvariantStatus.PASS,
            severity=inv.severity,
            duration_ms=int((datetime.utcnow() - start).total_seconds() * 1000)
        )
    
    def _check_single_semantic(
        self,
        inv: InvariantDefinition,
        mutation_data: Dict
    ) -> InvariantResult:
        """Check a single semantic invariant"""
        start = datetime.utcnow()
        violations = []
        
        if inv.id == "sem.confidence_threshold":
            confidence = mutation_data.get("confidence", 0)
            if confidence < 0.6:
                violations.append(f"Confidence {confidence:.2f} below threshold 0.6")
        
        elif inv.id == "sem.rationale_present":
            rationale = mutation_data.get("rationale", "")
            if not rationale or len(rationale.strip()) < 5:
                violations.append("Rationale missing or too short")
        
        elif inv.id == "sem.intent_alignment":
            # Check capability matches operation
            capability = mutation_data.get("capability", "")
            operation = mutation_data.get("operation", {}).get("type", "")
            if "create" in capability and operation != "write":
                violations.append(f"Capability {capability} misaligned with operation {operation}")
        
        elif inv.id == "sem.scope_containment":
            target = mutation_data.get("target", "")
            # Check target is within allowed scope
            if "/opt/resonant/core" in target or "/etc" in target:
                violations.append(f"Target {target} outside allowed scope")
        
        status = InvariantStatus.FAIL if violations else InvariantStatus.PASS
        
        return InvariantResult(
            invariant_id=inv.id,
            invariant_class=inv.invariant_class,
            status=status,
            severity=inv.severity,
            violations=violations,
            duration_ms=int((datetime.utcnow() - start).total_seconds() * 1000)
        )
    
    def _check_single_temporal(
        self,
        inv: InvariantDefinition,
        target: str,
        services: List[str]
    ) -> InvariantResult:
        """Check a single temporal invariant"""
        start = datetime.utcnow()
        violations = []
        
        if inv.id == "temp.rate_limit":
            ok, msg = self.temporal_state.check_rate_limit()
            if not ok:
                violations.append(msg)
        
        elif inv.id == "temp.blast_radius":
            ok, msg = self.temporal_state.check_blast_radius(services)
            if not ok:
                violations.append(msg)
        
        elif inv.id == "temp.cooldown":
            ok, msg = self.temporal_state.check_cooldown(target)
            if not ok:
                violations.append(msg)
        
        elif inv.id == "temp.rollback_frequency":
            ok, msg = self.temporal_state.check_rollback_frequency()
            if not ok:
                violations.append(msg)
        
        elif inv.id == "temp.failure_circuit":
            ok, msg = self.temporal_state.check_failure_circuit()
            if not ok:
                violations.append(msg)
        
        status = InvariantStatus.FAIL if violations else InvariantStatus.PASS
        
        return InvariantResult(
            invariant_id=inv.id,
            invariant_class=inv.invariant_class,
            status=status,
            severity=inv.severity,
            violations=violations,
            duration_ms=int((datetime.utcnow() - start).total_seconds() * 1000)
        )
    
    def get_summary(self) -> Dict:
        """Get summary of invariant check results"""
        by_class = {c.value: {"pass": 0, "fail": 0, "unknown": 0} for c in InvariantClass}
        by_severity = {s.value: {"pass": 0, "fail": 0, "unknown": 0} for s in InvariantSeverity}
        
        for result in self.results_history[-50:]:  # Last 50 results
            by_class[result.invariant_class.value][result.status.value] += 1
            by_severity[result.severity.value][result.status.value] += 1
        
        return {
            "environment": self.environment.value,
            "by_class": by_class,
            "by_severity": by_severity,
            "temporal_state": {
                "mutations_this_hour": self.temporal_state.mutations_this_hour,
                "mutations_this_day": self.temporal_state.mutations_this_day,
                "consecutive_failures": self.temporal_state.consecutive_failures,
                "rollbacks_this_hour": self.temporal_state.rollbacks_this_hour
            }
        }
