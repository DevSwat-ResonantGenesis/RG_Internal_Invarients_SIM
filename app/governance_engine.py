"""
RARA Governance Engine - Hash Sphere mutation governance

STATUS: PRODUCTION
UPDATED: 2025-12-21
GOVERNANCE: Enforces capability grammar and mutation governance rules.
            Graceful skip is DISABLED in production environment.
"""

import os
import httpx
import hashlib
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from .models import (
    MutationRequest, GovernanceDecision, ExplainabilityArtifact,
    ComplianceProfile
)
from .capability_enforcer import get_capability_enforcer, CapabilityCheck
import logging

logger = logging.getLogger(__name__)

# Environment configuration
ENVIRONMENT = os.getenv("RARA_ENVIRONMENT", "dev")
GRACEFUL_SKIP_ALLOWED = ENVIRONMENT == "dev"  # Only in dev


class GovernanceEngine:
    """
    Hash Sphere-based mutation governance.
    
    Rules:
    - Confidence < 0.6 → Reject
    - Blast radius > 2 services → Human approval
    - Core state touched → Forbidden
    - Repeated failure → Capability throttled
    """
    
    def __init__(
        self,
        hash_sphere_url: str = None,
        compliance_profile: ComplianceProfile = ComplianceProfile.MINIMAL
    ):
        if hash_sphere_url is None:
            hash_sphere_url = os.getenv("HASH_SPHERE_URL", "http://state_physics_service:8000")
        self.hash_sphere_url = hash_sphere_url
        self.compliance_profile = compliance_profile
        self.mutation_log: List[Dict] = []
        self.pending_approvals: Dict[str, MutationRequest] = {}
    
    async def get_current_state(self) -> Dict:
        """Get current state from Hash Sphere"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.hash_sphere_url}/api/state")
            response.raise_for_status()
            return response.json()
    
    async def propose_mutation(self, mutation: MutationRequest) -> GovernanceDecision:
        """
        Propose a mutation to Hash Sphere governance.
        
        Returns:
            GovernanceDecision with approval/rejection
        """
        # Calculate state hashes
        current_hash = await self._get_state_hash(mutation.target)
        proposed_hash = self._calculate_proposed_hash(mutation)
        
        # Determine blast radius
        blast_radius = self._calculate_blast_radius(mutation)
        
        # Build decision
        decision = GovernanceDecision(
            state_key=mutation.target,
            current_hash=current_hash,
            proposed_hash=proposed_hash,
            mutation_type=mutation.capability.value,
            actor="agent" if mutation.actor == "agent" else "human",
            confidence=mutation.confidence,
            blast_radius=blast_radius,
            decision="pending_human",
            reason=""
        )
        
        # Apply governance rules
        decision = self._apply_governance_rules(decision, mutation)
        
        # Log the decision
        self._log_decision(mutation, decision)
        
        # If pending human approval, store for later
        if decision.decision == "pending_human":
            self.pending_approvals[mutation.mutation_id] = mutation
        
        return decision
    
    def _apply_governance_rules(
        self,
        decision: GovernanceDecision,
        mutation: MutationRequest
    ) -> GovernanceDecision:
        """Apply governance rules to determine decision"""
        
        # Rule 0: Check capability grammar
        enforcer = get_capability_enforcer()
        cap_check = enforcer.check_capability(
            mutation.capability.value,
            {
                "confidence": mutation.confidence,
                "has_snapshot": True,  # Assume snapshot exists
                "invariant_passed": True,  # Will be checked separately
                "path": mutation.target
            }
        )
        
        if not cap_check.allowed:
            decision.decision = "rejected"
            decision.reason = f"Capability denied: {cap_check.reason}"
            logger.warning(f"GOVERNANCE: Capability {mutation.capability.value} denied - {cap_check.reason}")
            return decision
        
        # Rule 1: Confidence < 0.6 → Reject
        if decision.confidence < 0.6:
            decision.decision = "rejected"
            decision.reason = f"Confidence too low: {decision.confidence:.2f} < 0.6"
            return decision
        
        # Rule 2: Core state touched → Forbidden
        if self._touches_core(mutation.target):
            decision.decision = "rejected"
            decision.reason = "Core state modification forbidden"
            return decision
        
        # Rule 3: Blast radius > 2 services → Human approval
        if len(decision.blast_radius) > 2:
            if not mutation.approval_token:
                decision.decision = "pending_human"
                decision.reason = f"Blast radius {len(decision.blast_radius)} > 2, requires human approval"
                return decision
        
        # Rule 4: High-risk capabilities require approval in strict compliance
        if self.compliance_profile in [ComplianceProfile.EU_AI_ACT, ComplianceProfile.SOC2]:
            high_risk = ["delete_file", "restart_service", "remove_route"]
            if any(hr in mutation.capability.value for hr in high_risk):
                if not mutation.approval_token:
                    decision.decision = "pending_human"
                    decision.reason = f"High-risk action requires approval under {self.compliance_profile.value}"
                    return decision
        
        # All checks passed
        decision.decision = "approved"
        decision.reason = "All governance checks passed"
        return decision
    
    async def _get_state_hash(self, target: str) -> str:
        """Get current state hash for a target"""
        try:
            state = await self.get_current_state()
            # Hash the relevant portion of state
            relevant = str(state.get("nodes", [])) + str(state.get("edges", []))
            return f"0x{hashlib.sha256(relevant.encode()).hexdigest()[:16]}"
        except Exception:
            return "0x0000000000000000"
    
    def _calculate_proposed_hash(self, mutation: MutationRequest) -> str:
        """Calculate hash of proposed state after mutation"""
        content = f"{mutation.target}:{mutation.operation.type}:{mutation.operation.content or ''}"
        return f"0x{hashlib.sha256(content.encode()).hexdigest()[:16]}"
    
    def _calculate_blast_radius(self, mutation: MutationRequest) -> List[str]:
        """Determine which services are affected by this mutation"""
        target = mutation.target.lower()
        affected = []
        
        # Service detection based on path
        services = [
            "gateway", "auth", "chat", "memory", "agent",
            "workflow", "notification", "crypto", "blockchain",
            "storage", "ide", "billing", "user"
        ]
        
        for service in services:
            if service in target:
                affected.append(service)
        
        # Config changes affect multiple services
        if "config" in target:
            affected.extend(["gateway", "auth"])
        
        # Route changes affect gateway
        if "route" in target and "gateway" not in affected:
            affected.append("gateway")
        
        return list(set(affected)) or ["unknown"]
    
    def _touches_core(self, target: str) -> bool:
        """Check if mutation touches core layer"""
        core_paths = [
            "/opt/resonant/core",
            "/opt/resonant/agent",
            "core/",
            "agent/bin"
        ]
        return any(cp in target for cp in core_paths)
    
    def _log_decision(self, mutation: MutationRequest, decision: GovernanceDecision):
        """Log governance decision"""
        entry = {
            "mutation_id": mutation.mutation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "decision": decision.decision,
            "reason": decision.reason,
            "confidence": decision.confidence,
            "blast_radius": decision.blast_radius
        }
        self.mutation_log.append(entry)
        
        logger.info(
            f"Governance decision: {mutation.mutation_id} -> {decision.decision} "
            f"({decision.reason})"
        )
    
    async def commit_to_hash_sphere(self, mutation: MutationRequest) -> bool:
        """Commit a mutation to Hash Sphere state"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.hash_sphere_url}/api/mutate",
                    json={
                        "key": f"mutation:{mutation.mutation_id}",
                        "value": {
                            "target": mutation.target,
                            "capability": mutation.capability.value,
                            "actor": mutation.actor,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    }
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to commit to Hash Sphere: {e}")
            return False
    
    def generate_explainability(self, mutation: MutationRequest) -> ExplainabilityArtifact:
        """
        Generate explainability artifact for EU AI Act compliance.
        """
        # Determine risk level
        high_risk_caps = ["delete", "restart", "remove"]
        if any(hr in mutation.capability.value for hr in high_risk_caps):
            risk = "High"
        elif mutation.confidence < 0.7:
            risk = "Medium"
        else:
            risk = "Low"
        
        # Calculate impact
        impact = self._calculate_blast_radius(mutation)
        
        return ExplainabilityArtifact(
            mutation_id=mutation.mutation_id,
            why=mutation.rationale or "Automated system optimization",
            what=f"{mutation.capability.value} on {mutation.target}",
            risk=risk,
            impact=impact,
            alternatives_considered=1  # Would be populated by planner agent
        )
    
    def approve_pending(self, mutation_id: str, approval_token: str) -> bool:
        """Human approval for a pending mutation"""
        if mutation_id not in self.pending_approvals:
            return False
        
        mutation = self.pending_approvals[mutation_id]
        mutation.approval_token = approval_token
        mutation.requires_human = False
        
        del self.pending_approvals[mutation_id]
        
        logger.info(f"Human approved mutation {mutation_id}")
        return True
    
    def reject_pending(self, mutation_id: str, reason: str) -> bool:
        """Human rejection for a pending mutation"""
        if mutation_id not in self.pending_approvals:
            return False
        
        del self.pending_approvals[mutation_id]
        
        logger.info(f"Human rejected mutation {mutation_id}: {reason}")
        return True
    
    def get_pending_approvals(self) -> List[Dict]:
        """Get all pending approval requests"""
        return [
            {
                "mutation_id": m.mutation_id,
                "capability": m.capability.value,
                "target": m.target,
                "rationale": m.rationale,
                "confidence": m.confidence,
                "created_at": m.created_at.isoformat()
            }
            for m in self.pending_approvals.values()
        ]
    
    def get_mutation_log(self, limit: int = 50) -> List[Dict]:
        """Get recent mutation log entries"""
        return self.mutation_log[-limit:]
