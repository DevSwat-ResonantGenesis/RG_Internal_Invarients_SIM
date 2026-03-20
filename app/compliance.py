"""
RARA Compliance Module - EU AI Act / SOC2 Mapping

This module provides:
1. Formal compliance profile definitions
2. Mapping to regulatory language
3. Audit artifact generation
4. Compliance verification
"""

from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pydantic import BaseModel, Field
import json
import hashlib
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# COMPLIANCE FRAMEWORKS
# ============================================================================

class ComplianceFramework(str, Enum):
    """Supported compliance frameworks"""
    EU_AI_ACT = "eu_ai_act"
    SOC2 = "soc2"
    ISO27001 = "iso27001"
    GDPR = "gdpr"
    INTERNAL = "internal"


class RiskLevel(str, Enum):
    """EU AI Act risk classification"""
    UNACCEPTABLE = "unacceptable"  # Banned
    HIGH = "high"                   # Strict requirements
    LIMITED = "limited"             # Transparency requirements
    MINIMAL = "minimal"             # No specific requirements


# ============================================================================
# EU AI ACT MAPPING
# ============================================================================

class EUAIActRequirement(BaseModel):
    """EU AI Act requirement mapping"""
    article: str
    title: str
    description: str
    rara_implementation: str
    verification_method: str
    status: str = "implemented"


EU_AI_ACT_REQUIREMENTS = [
    EUAIActRequirement(
        article="Article 9",
        title="Risk Management System",
        description="High-risk AI systems shall have a risk management system",
        rara_implementation="Invariant class system with STRUCTURAL, SEMANTIC, TEMPORAL checks",
        verification_method="InvariantClassChecker.check_all() returns results for all risk categories"
    ),
    EUAIActRequirement(
        article="Article 10",
        title="Data and Data Governance",
        description="Training, validation and testing data sets shall be subject to appropriate data governance",
        rara_implementation="Capability trust scoring tracks all mutation outcomes",
        verification_method="CapabilityEngine maintains success/failure/rollback counts"
    ),
    EUAIActRequirement(
        article="Article 11",
        title="Technical Documentation",
        description="Technical documentation shall be drawn up before placing on market",
        rara_implementation="ExplainabilityArtifact generated for every mutation",
        verification_method="GovernanceEngine.generate_explainability() produces required fields"
    ),
    EUAIActRequirement(
        article="Article 12",
        title="Record-keeping",
        description="High-risk AI systems shall technically allow for automatic recording of events",
        rara_implementation="Hash Sphere mutation log with immutable audit trail",
        verification_method="All mutations logged with timestamp, actor, rationale, outcome"
    ),
    EUAIActRequirement(
        article="Article 13",
        title="Transparency",
        description="High-risk AI systems shall be designed to ensure transparency",
        rara_implementation="Every mutation requires rationale, confidence score, and blast radius",
        verification_method="MutationRequest schema enforces required fields"
    ),
    EUAIActRequirement(
        article="Article 14",
        title="Human Oversight",
        description="High-risk AI systems shall be designed to be effectively overseen by natural persons",
        rara_implementation="Kill switch with freeze/emergency stop, human approval gates",
        verification_method="KillSwitch.freeze() immediately blocks all mutations"
    ),
    EUAIActRequirement(
        article="Article 15",
        title="Accuracy, Robustness and Cybersecurity",
        description="High-risk AI systems shall be designed to achieve appropriate levels of accuracy",
        rara_implementation="Confidence threshold (0.6), capability decay on failure",
        verification_method="Mutations with confidence < 0.6 are rejected"
    ),
]


# ============================================================================
# SOC2 MAPPING
# ============================================================================

class SOC2Control(BaseModel):
    """SOC2 Trust Services Criteria mapping"""
    criteria: str
    category: str
    description: str
    rara_implementation: str
    verification_method: str
    status: str = "implemented"


SOC2_CONTROLS = [
    # Security
    SOC2Control(
        criteria="CC6.1",
        category="Logical and Physical Access Controls",
        description="The entity implements logical access security software",
        rara_implementation="Capability-based access control with trust scoring",
        verification_method="CapabilityEngine enforces per-agent permissions"
    ),
    SOC2Control(
        criteria="CC6.2",
        category="Logical and Physical Access Controls",
        description="Prior to issuing system credentials, the entity registers and authorizes new users",
        rara_implementation="Agent registration with role assignment",
        verification_method="AgentCoordinator.register_agent() requires role and DSID"
    ),
    SOC2Control(
        criteria="CC6.3",
        category="Logical and Physical Access Controls",
        description="The entity authorizes, modifies, or removes access based on roles",
        rara_implementation="Role-based capability assignment (planner/executor/verifier/auditor)",
        verification_method="Agents cannot execute outside their role permissions"
    ),
    
    # Availability
    SOC2Control(
        criteria="A1.1",
        category="Availability",
        description="The entity maintains, monitors, and evaluates current processing capacity",
        rara_implementation="Temporal invariants track rate limits and blast radius",
        verification_method="TemporalState enforces mutations_per_hour limits"
    ),
    SOC2Control(
        criteria="A1.2",
        category="Availability",
        description="The entity authorizes, designs, develops or acquires, implements, operates, approves, maintains, and monitors environmental protections",
        rara_implementation="Snapshot-based rollback with atomic restore",
        verification_method="SnapshotEngine.restore_snapshot() completes in < 2 seconds"
    ),
    
    # Processing Integrity
    SOC2Control(
        criteria="PI1.1",
        category="Processing Integrity",
        description="The entity obtains or generates, uses, and communicates relevant, quality information",
        rara_implementation="Mutation validation with preconditions and postconditions",
        verification_method="MutationExecutor validates all conditions before commit"
    ),
    SOC2Control(
        criteria="PI1.2",
        category="Processing Integrity",
        description="The entity implements policies and procedures over system inputs",
        rara_implementation="Capability grammar enforces mutation schema",
        verification_method="Invalid mutations rejected at schema validation"
    ),
    
    # Confidentiality
    SOC2Control(
        criteria="C1.1",
        category="Confidentiality",
        description="The entity identifies and maintains confidential information",
        rara_implementation="Forbidden paths prevent access to sensitive directories",
        verification_method="Mutations to /opt/resonant/core are rejected"
    ),
    
    # Change Management
    SOC2Control(
        criteria="CC8.1",
        category="Change Management",
        description="The entity authorizes, designs, develops or acquires, configures, documents, tests, approves, and implements changes",
        rara_implementation="Multi-agent coordination with proposal/verify/execute flow",
        verification_method="Planner cannot execute, executor cannot verify"
    ),
]


# ============================================================================
# COMPLIANCE ARTIFACT
# ============================================================================

class ComplianceArtifact(BaseModel):
    """Audit artifact for compliance verification"""
    artifact_id: str = Field(default_factory=lambda: hashlib.sha256(
        datetime.utcnow().isoformat().encode()
    ).hexdigest()[:16])
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    framework: ComplianceFramework
    
    # Mutation details
    mutation_id: str
    actor: str
    capability: str
    target: str
    
    # Risk assessment
    risk_level: RiskLevel
    confidence: float
    blast_radius: List[str]
    
    # Human oversight
    human_approval_required: bool
    human_approval_received: bool = False
    approver: Optional[str] = None
    
    # Explainability
    rationale: str
    alternatives_considered: int = 0
    
    # Outcome
    outcome: str  # success, failed, rolled_back, rejected
    rollback_id: Optional[str] = None
    
    # Invariant results
    invariants_checked: int = 0
    invariants_passed: int = 0
    invariant_violations: List[str] = []
    
    # Hash chain for immutability
    previous_artifact_hash: Optional[str] = None
    artifact_hash: Optional[str] = None
    
    def compute_hash(self) -> str:
        """Compute hash of this artifact for chain integrity"""
        data = self.model_dump(exclude={"artifact_hash"})
        content = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()
    
    def finalize(self, previous_hash: Optional[str] = None):
        """Finalize artifact with hash chain"""
        self.previous_artifact_hash = previous_hash
        self.artifact_hash = self.compute_hash()


# ============================================================================
# COMPLIANCE VERIFIER
# ============================================================================

class ComplianceVerifier:
    """
    Verifies compliance with regulatory frameworks.
    """
    
    def __init__(self, framework: ComplianceFramework = ComplianceFramework.INTERNAL):
        self.framework = framework
        self.artifacts: List[ComplianceArtifact] = []
        self.last_artifact_hash: Optional[str] = None
    
    def classify_risk(
        self,
        capability: str,
        confidence: float,
        blast_radius: List[str]
    ) -> RiskLevel:
        """
        Classify risk level based on EU AI Act criteria.
        """
        # High-risk indicators
        high_risk_capabilities = [
            "services.restart_service",
            "routing.remove_route",
            "filesystem.delete_file",
            "workflows.disable_workflow"
        ]
        
        if capability in high_risk_capabilities:
            return RiskLevel.HIGH
        
        if len(blast_radius) > 2:
            return RiskLevel.HIGH
        
        if confidence < 0.7:
            return RiskLevel.LIMITED
        
        return RiskLevel.MINIMAL
    
    def requires_human_approval(
        self,
        risk_level: RiskLevel,
        capability: str
    ) -> bool:
        """
        Determine if human approval is required.
        """
        if self.framework == ComplianceFramework.EU_AI_ACT:
            # EU AI Act: High-risk requires human oversight
            return risk_level == RiskLevel.HIGH
        
        elif self.framework == ComplianceFramework.SOC2:
            # SOC2: Change management for critical changes
            critical_capabilities = [
                "services.restart_service",
                "routing.remove_route"
            ]
            return capability in critical_capabilities
        
        return False
    
    def create_artifact(
        self,
        mutation_id: str,
        actor: str,
        capability: str,
        target: str,
        confidence: float,
        blast_radius: List[str],
        rationale: str,
        outcome: str,
        invariants_checked: int = 0,
        invariants_passed: int = 0,
        invariant_violations: List[str] = None,
        rollback_id: Optional[str] = None,
        human_approved: bool = False,
        approver: Optional[str] = None
    ) -> ComplianceArtifact:
        """
        Create a compliance artifact for a mutation.
        """
        risk_level = self.classify_risk(capability, confidence, blast_radius)
        requires_human = self.requires_human_approval(risk_level, capability)
        
        artifact = ComplianceArtifact(
            framework=self.framework,
            mutation_id=mutation_id,
            actor=actor,
            capability=capability,
            target=target,
            risk_level=risk_level,
            confidence=confidence,
            blast_radius=blast_radius,
            human_approval_required=requires_human,
            human_approval_received=human_approved,
            approver=approver,
            rationale=rationale,
            outcome=outcome,
            rollback_id=rollback_id,
            invariants_checked=invariants_checked,
            invariants_passed=invariants_passed,
            invariant_violations=invariant_violations or []
        )
        
        # Finalize with hash chain
        artifact.finalize(self.last_artifact_hash)
        self.last_artifact_hash = artifact.artifact_hash
        
        self.artifacts.append(artifact)
        
        return artifact
    
    def verify_chain_integrity(self) -> Tuple[bool, List[str]]:
        """
        Verify the integrity of the artifact chain.
        """
        errors = []
        
        for i, artifact in enumerate(self.artifacts):
            # Verify hash
            computed = artifact.compute_hash()
            if computed != artifact.artifact_hash:
                errors.append(f"Artifact {artifact.artifact_id}: hash mismatch")
            
            # Verify chain
            if i > 0:
                expected_prev = self.artifacts[i-1].artifact_hash
                if artifact.previous_artifact_hash != expected_prev:
                    errors.append(f"Artifact {artifact.artifact_id}: chain break")
        
        return len(errors) == 0, errors
    
    def get_compliance_report(self) -> Dict:
        """
        Generate a compliance report.
        """
        if self.framework == ComplianceFramework.EU_AI_ACT:
            requirements = EU_AI_ACT_REQUIREMENTS
        elif self.framework == ComplianceFramework.SOC2:
            requirements = SOC2_CONTROLS
        else:
            requirements = []
        
        # Analyze artifacts
        total = len(self.artifacts)
        by_risk = {r.value: 0 for r in RiskLevel}
        by_outcome = {"success": 0, "failed": 0, "rolled_back": 0, "rejected": 0}
        human_required = 0
        human_received = 0
        
        for artifact in self.artifacts:
            by_risk[artifact.risk_level.value] += 1
            by_outcome[artifact.outcome] = by_outcome.get(artifact.outcome, 0) + 1
            if artifact.human_approval_required:
                human_required += 1
                if artifact.human_approval_received:
                    human_received += 1
        
        # Chain integrity
        chain_valid, chain_errors = self.verify_chain_integrity()
        
        return {
            "framework": self.framework.value,
            "generated_at": datetime.utcnow().isoformat(),
            "requirements_count": len(requirements),
            "requirements_implemented": sum(1 for r in requirements if r.status == "implemented"),
            "artifacts_count": total,
            "by_risk_level": by_risk,
            "by_outcome": by_outcome,
            "human_oversight": {
                "required": human_required,
                "received": human_received,
                "compliance_rate": human_received / human_required if human_required > 0 else 1.0
            },
            "chain_integrity": {
                "valid": chain_valid,
                "errors": chain_errors
            }
        }
    
    def export_for_audit(self) -> List[Dict]:
        """
        Export artifacts in audit-ready format.
        """
        return [
            {
                "artifact_id": a.artifact_id,
                "timestamp": a.timestamp.isoformat(),
                "framework": a.framework.value,
                "mutation_id": a.mutation_id,
                "actor": a.actor,
                "capability": a.capability,
                "target": a.target,
                "risk_level": a.risk_level.value,
                "confidence": a.confidence,
                "blast_radius": a.blast_radius,
                "human_approval_required": a.human_approval_required,
                "human_approval_received": a.human_approval_received,
                "approver": a.approver,
                "rationale": a.rationale,
                "outcome": a.outcome,
                "invariants_checked": a.invariants_checked,
                "invariants_passed": a.invariants_passed,
                "invariant_violations": a.invariant_violations,
                "artifact_hash": a.artifact_hash,
                "previous_artifact_hash": a.previous_artifact_hash
            }
            for a in self.artifacts
        ]


# ============================================================================
# COMPLIANCE POLICY
# ============================================================================

class CompliancePolicy(BaseModel):
    """
    Environment-specific compliance policy.
    """
    environment: str
    framework: ComplianceFramework
    
    # Thresholds
    confidence_threshold: float = 0.6
    max_blast_radius: int = 2
    max_mutations_per_hour: int = 50
    max_rollbacks_per_hour: int = 5
    
    # Human oversight
    require_human_for_high_risk: bool = True
    require_human_for_delete: bool = True
    require_human_for_restart: bool = True
    
    # Audit
    audit_all_mutations: bool = True
    retain_artifacts_days: int = 90
    
    # Kill switch
    auto_freeze_on_critical: bool = True
    auto_freeze_on_consecutive_failures: int = 3


# Pre-defined policies
COMPLIANCE_POLICIES = {
    "dev": CompliancePolicy(
        environment="dev",
        framework=ComplianceFramework.INTERNAL,
        confidence_threshold=0.5,
        max_blast_radius=5,
        require_human_for_high_risk=False,
        require_human_for_delete=False,
        require_human_for_restart=False,
        audit_all_mutations=False,
        auto_freeze_on_critical=False
    ),
    "staging": CompliancePolicy(
        environment="staging",
        framework=ComplianceFramework.SOC2,
        confidence_threshold=0.6,
        max_blast_radius=3,
        require_human_for_high_risk=True,
        require_human_for_delete=False,
        require_human_for_restart=True,
        audit_all_mutations=True,
        auto_freeze_on_critical=True
    ),
    "prod": CompliancePolicy(
        environment="prod",
        framework=ComplianceFramework.EU_AI_ACT,
        confidence_threshold=0.7,
        max_blast_radius=2,
        require_human_for_high_risk=True,
        require_human_for_delete=True,
        require_human_for_restart=True,
        audit_all_mutations=True,
        retain_artifacts_days=365,
        auto_freeze_on_critical=True,
        auto_freeze_on_consecutive_failures=2
    )
}


def get_policy(environment: str) -> CompliancePolicy:
    """Get compliance policy for environment"""
    return COMPLIANCE_POLICIES.get(environment, COMPLIANCE_POLICIES["dev"])
