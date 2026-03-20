"""
RARA Capability Engine - Enforces capability grammar and trust scoring
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from .models import (
    CapabilityType, CapabilityScore, CapabilityManifest,
    MutationRequest, MutationCost, AgentBudget
)
import logging

logger = logging.getLogger(__name__)


class CapabilityEngine:
    """
    Enforces capability grammar and manages trust scores.
    
    Principles:
    - Capabilities can only decay, never expand autonomously
    - No agent may grant itself new authority
    - All mutations must pass capability check
    """
    
    def __init__(
        self,
        capabilities_file: str = "/opt/resonant/agent/capabilities.yaml",
        state_dir: str = "/opt/resonant/state"
    ):
        self.capabilities_file = Path(capabilities_file)
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        # Agent manifests
        self.manifests: Dict[str, CapabilityManifest] = {}
        
        # Agent budgets
        self.budgets: Dict[str, AgentBudget] = {}
        
        # Default forbidden paths
        self.forbidden_paths = [
            "/opt/resonant/core",
            "/opt/resonant/agent",
            "/etc",
            "/usr",
            "/bin",
            "/sbin",
            "/var/log",
            "/root"
        ]
        
        # Load persisted state
        self._load_state()
    
    def _load_state(self):
        """Load capability state from disk"""
        state_file = self.state_dir / "capabilities.json"
        if state_file.exists():
            with open(state_file, 'r') as f:
                data = json.load(f)
                for agent_id, manifest_data in data.get("manifests", {}).items():
                    self.manifests[agent_id] = CapabilityManifest(**manifest_data)
                for agent_id, budget_data in data.get("budgets", {}).items():
                    self.budgets[agent_id] = AgentBudget(**budget_data)
    
    def _save_state(self):
        """Persist capability state to disk"""
        state_file = self.state_dir / "capabilities.json"
        data = {
            "manifests": {k: v.model_dump() for k, v in self.manifests.items()},
            "budgets": {k: v.model_dump() for k, v in self.budgets.items()},
            "updated_at": datetime.utcnow().isoformat()
        }
        with open(state_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def register_agent(self, agent_id: str, capabilities: List[CapabilityType] = None) -> CapabilityManifest:
        """Register a new agent with initial capabilities"""
        if agent_id in self.manifests:
            return self.manifests[agent_id]
        
        manifest = CapabilityManifest(
            agent_id=agent_id,
            capabilities={
                cap.value: CapabilityScore(capability=cap)
                for cap in (capabilities or list(CapabilityType))
            },
            forbidden_paths=self.forbidden_paths.copy()
        )
        
        self.manifests[agent_id] = manifest
        self.budgets[agent_id] = AgentBudget(agent_id=agent_id)
        self._save_state()
        
        logger.info(f"Registered agent {agent_id} with {len(manifest.capabilities)} capabilities")
        
        return manifest
    
    def get_manifest(self, agent_id: str) -> Optional[CapabilityManifest]:
        """Get capability manifest for an agent"""
        return self.manifests.get(agent_id)
    
    def check_capability(
        self,
        agent_id: str,
        mutation: MutationRequest
    ) -> Tuple[bool, str]:
        """
        Check if an agent has capability to perform a mutation.
        
        Returns:
            (allowed, reason)
        """
        manifest = self.manifests.get(agent_id)
        if not manifest:
            return False, f"Agent {agent_id} not registered"
        
        # Check capability exists
        cap_key = mutation.capability.value
        if cap_key not in manifest.capabilities:
            return False, f"Capability {cap_key} not in manifest"
        
        cap_score = manifest.capabilities[cap_key]
        
        # Check if revoked
        if cap_score.is_revoked:
            return False, f"Capability {cap_key} permanently revoked (trust={cap_score.trust:.2f})"
        
        # Check if disabled
        if cap_score.is_disabled:
            return False, f"Capability {cap_key} disabled (trust={cap_score.trust:.2f})"
        
        # Check if requires approval
        if cap_score.requires_approval and not mutation.approval_token:
            return False, f"Capability {cap_key} requires human approval (trust={cap_score.trust:.2f})"
        
        # Check path authorization
        if mutation.target:
            path_allowed, path_reason = self._check_path(mutation.target, manifest)
            if not path_allowed:
                return False, path_reason
        
        # Check budget
        budget = self.budgets.get(agent_id)
        if budget and budget.is_over_budget:
            return False, f"Agent {agent_id} over daily budget ({budget.spent_today:.1f}/{budget.daily_budget:.1f})"
        
        return True, "Capability check passed"
    
    def _check_path(self, target: str, manifest: CapabilityManifest) -> Tuple[bool, str]:
        """Check if a path is allowed for mutation"""
        target_path = Path(target).resolve()
        
        # Check forbidden paths
        for forbidden in manifest.forbidden_paths:
            forbidden_path = Path(forbidden).resolve()
            try:
                target_path.relative_to(forbidden_path)
                return False, f"Path {target} is in forbidden zone {forbidden}"
            except ValueError:
                continue
        
        # Must be in runtime
        runtime_path = Path("/opt/resonant/runtime").resolve()
        try:
            target_path.relative_to(runtime_path)
        except ValueError:
            return False, f"Path {target} is outside runtime layer"
        
        return True, "Path allowed"
    
    def calculate_cost(self, mutation: MutationRequest) -> MutationCost:
        """Calculate the cost of a mutation"""
        cost = MutationCost()
        
        # CPU cost based on operation type
        if mutation.operation.type.value in ["write", "move"]:
            cost.cpu_cost = 0.2
        elif mutation.operation.type.value == "restart":
            cost.cpu_cost = 0.5
        else:
            cost.cpu_cost = 0.1
        
        # Disk cost based on content size
        if mutation.operation.content:
            size_kb = len(mutation.operation.content) / 1024
            cost.disk_cost = min(1.0, size_kb / 100)  # Cap at 1.0
        
        # Blast radius based on target
        target = mutation.target.lower()
        if "gateway" in target:
            cost.blast_radius = 0.8
        elif "auth" in target:
            cost.blast_radius = 0.9
        elif "config" in target:
            cost.blast_radius = 0.5
        else:
            cost.blast_radius = 0.2
        
        # Risk score based on capability
        high_risk_caps = [
            CapabilityType.DELETE_FILE,
            CapabilityType.RESTART_SERVICE,
            CapabilityType.REMOVE_ROUTE
        ]
        if mutation.capability in high_risk_caps:
            cost.risk_score = 0.6
        else:
            cost.risk_score = 0.2
        
        return cost
    
    def record_success(self, agent_id: str, mutation: MutationRequest, cost: MutationCost):
        """Record a successful mutation"""
        manifest = self.manifests.get(agent_id)
        if manifest:
            cap_key = mutation.capability.value
            if cap_key in manifest.capabilities:
                manifest.capabilities[cap_key].update_success()
        
        budget = self.budgets.get(agent_id)
        if budget:
            budget.spend(cost.total_cost)
        
        self._save_state()
    
    def record_failure(self, agent_id: str, mutation: MutationRequest):
        """Record a failed mutation"""
        manifest = self.manifests.get(agent_id)
        if manifest:
            cap_key = mutation.capability.value
            if cap_key in manifest.capabilities:
                manifest.capabilities[cap_key].update_failure()
        
        self._save_state()
    
    def record_rollback(self, agent_id: str, mutation: MutationRequest):
        """Record a rollback"""
        manifest = self.manifests.get(agent_id)
        if manifest:
            cap_key = mutation.capability.value
            if cap_key in manifest.capabilities:
                manifest.capabilities[cap_key].update_rollback()
        
        self._save_state()
    
    def record_human_reject(self, agent_id: str, mutation: MutationRequest):
        """Record a human rejection"""
        manifest = self.manifests.get(agent_id)
        if manifest:
            cap_key = mutation.capability.value
            if cap_key in manifest.capabilities:
                manifest.capabilities[cap_key].update_human_reject()
        
        self._save_state()
    
    def reset_daily_budgets(self):
        """Reset all agent budgets (called daily)"""
        for budget in self.budgets.values():
            budget.reset()
        self._save_state()
        logger.info("Daily budgets reset for all agents")
    
    def get_agent_stats(self, agent_id: str) -> Dict:
        """Get statistics for an agent"""
        manifest = self.manifests.get(agent_id)
        budget = self.budgets.get(agent_id)
        
        if not manifest:
            return {}
        
        return {
            "agent_id": agent_id,
            "total_capabilities": len(manifest.capabilities),
            "active_capabilities": sum(
                1 for c in manifest.capabilities.values()
                if not c.is_disabled
            ),
            "revoked_capabilities": sum(
                1 for c in manifest.capabilities.values()
                if c.is_revoked
            ),
            "budget_remaining": budget.remaining if budget else 0,
            "budget_spent": budget.spent_today if budget else 0
        }
