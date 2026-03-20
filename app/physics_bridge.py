"""
Physics → Governance Bridge

Translates measured physical state into governance decisions.
This is the missing deterministic bridge between State Physics and RARA governance.

STATUS: PRODUCTION IMPLEMENTATION
UPDATED: 2025-01-08
PURPOSE: Close the physics → enforcement loop
"""

import os
import httpx
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .models import GovernanceDecision, ComplianceProfile
from .kill_switch import KillSwitch, KillSwitchState, KillSwitchTrigger
from .capability_engine import CapabilityEngine

logger = logging.getLogger(__name__)


# ============================================================================
# PHYSICS STATE MODELS
# ============================================================================

@dataclass
class PhysicsState:
    """Physics state from State Physics service"""
    entropy: float
    collapse_risk: float
    invariant_violations: int
    agent_values: Dict[str, float]
    agent_trust: Dict[str, float]
    total_mass: float
    total_energy: float
    node_count: int
    timestamp: datetime


@dataclass
class GovernanceAction:
    """Governance action to be executed"""
    action_type: str
    target: Optional[str] = None  # agent_id if applicable
    severity: str = "medium"
    reason: str = ""
    physics_trigger: str = ""
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


# ============================================================================
# DETERMINISTIC RULE TABLE
# ============================================================================

class PhysicsRule(str, Enum):
    """Deterministic physics → governance rules"""
    
    # CRITICAL RULES
    COLLAPSE_RISK_HIGH = "collapse_risk_high"
    INVARIANT_VIOLATION = "invariant_violation"
    
    # WARNING RULES
    ENTROPY_HIGH = "entropy_high"
    AGENT_VALUE_ZERO = "agent_value_zero"
    AGENT_TRUST_LOW = "agent_trust_low"
    
    # MONITORING RULES
    MASS_IMBALANCE = "mass_imbalance"
    ENERGY_SPIKE = "energy_spike"


class PhysicsGovernanceBridge:
    """
    Deterministic bridge from physics state to governance actions.
    
    Rules:
    - No modes, no learning, no autonomy
    - Static thresholds only
    - Physics cannot act directly
    - RARA retains all authority
    """
    
    # === STATIC THRESHOLDS (CONSTANTS, NOT CONFIG) ===
    THRESHOLD_COLLAPSE_RISK_CRITICAL = 0.8
    THRESHOLD_ENTROPY_WARNING = 0.65
    THRESHOLD_AGENT_VALUE_CRITICAL = 0.0
    THRESHOLD_AGENT_TRUST_WARNING = 0.3
    THRESHOLD_MASS_IMBALANCE = 10.0  # ratio
    THRESHOLD_ENERGY_SPIKE = 1000.0
    
    def __init__(
        self,
        physics_service_url: str = None,
        rara_governance_url: str = None,
        capability_engine: CapabilityEngine = None,
        kill_switch: KillSwitch = None
    ):
        # Service URLs
        self.physics_service_url = physics_service_url or os.getenv(
            "PHYSICS_SERVICE_URL", "http://state_physics_service:8091"
        )
        self.rara_governance_url = rara_governance_url or os.getenv(
            "RARA_GOVERNANCE_URL", "http://rara_service:8093"
        )
        
        # RARA components
        self.capability_engine = capability_engine
        self.kill_switch = kill_switch
        
        # State tracking
        self.last_evaluation: Optional[datetime] = None
        self.action_history: List[GovernanceAction] = []
        
        logger.info("PhysicsGovernanceBridge initialized")
    
    async def evaluate_physics_state(self) -> List[GovernanceAction]:
        """
        Main evaluation method:
        1. Fetch current physics state
        2. Apply deterministic rules
        3. Generate governance actions
        4. Return actions for execution
        """
        try:
            # Step 1: Get physics state
            physics_state = await self._fetch_physics_state()
            if not physics_state:
                logger.warning("Failed to fetch physics state")
                return []
            
            # Step 2: Apply deterministic rules
            actions = self._apply_deterministic_rules(physics_state)
            
            # Step 3: Log evaluation
            self.last_evaluation = datetime.utcnow()
            logger.info(f"Physics evaluation complete: {len(actions)} actions generated")
            
            return actions
            
        except Exception as e:
            logger.error(f"Physics evaluation failed: {e}")
            return []
    
    async def _fetch_physics_state(self) -> Optional[PhysicsState]:
        """Fetch current state from State Physics service"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.physics_service_url}/api/state")
                response.raise_for_status()
                data = response.json()
                
                # Extract metrics
                metrics = data.get("metrics", {})
                nodes = data.get("nodes", [])
                
                # Build agent data
                agent_values = {}
                agent_trust = {}
                for node in nodes:
                    if node.get("type") == "agent":
                        agent_id = node.get("id", "unknown")
                        agent_values[agent_id] = node.get("value", 0.0)
                        agent_trust[agent_id] = node.get("trust_score", 0.5)
                
                # Calculate collapse risk (from instabilities)
                instabilities = data.get("instabilities", [])
                collapse_risk = 0.0
                for instability in instabilities:
                    if instability.get("type") == "collapse_risk":
                        if instability.get("severity") == "critical":
                            collapse_risk = max(collapse_risk, 0.9)
                        elif instability.get("severity") == "high":
                            collapse_risk = max(collapse_risk, 0.7)
                
                return PhysicsState(
                    entropy=metrics.get("entropy", 0.0),
                    collapse_risk=collapse_risk,
                    invariant_violations=metrics.get("invariant_violations", 0),
                    agent_values=agent_values,
                    agent_trust=agent_trust,
                    total_mass=metrics.get("total_mass", 0.0),
                    total_energy=metrics.get("total_energy", 0.0),
                    node_count=len(nodes),
                    timestamp=datetime.utcnow()
                )
                
        except Exception as e:
            logger.error(f"Failed to fetch physics state: {e}")
            return None
    
    def _apply_deterministic_rules(self, state: PhysicsState) -> List[GovernanceAction]:
        """
        Apply deterministic rule table.
        No learning, no adaptation, no autonomy.
        """
        actions = []
        
        # === CRITICAL RULES ===
        
        # Rule: Collapse risk ≥ 0.8 → Emergency stop
        if state.collapse_risk >= self.THRESHOLD_COLLAPSE_RISK_CRITICAL:
            actions.append(GovernanceAction(
                action_type="emergency_stop",
                severity="critical",
                reason=f"Critical collapse risk: {state.collapse_risk:.2f}",
                physics_trigger=PhysicsRule.COLLAPSE_RISK_HIGH.value
            ))
        
        # Rule: Invariant violations > 0 → Emergency stop
        if state.invariant_violations > 0:
            actions.append(GovernanceAction(
                action_type="emergency_stop",
                severity="critical",
                reason=f"Invariant violations detected: {state.invariant_violations}",
                physics_trigger=PhysicsRule.INVARIANT_VIOLATION.value
            ))
        
        # === WARNING RULES ===
        
        # Rule: Entropy ≥ 0.65 → Freeze capabilities
        if state.entropy >= self.THRESHOLD_ENTROPY_WARNING:
            actions.append(GovernanceAction(
                action_type="freeze_capabilities",
                severity="high",
                reason=f"High entropy: {state.entropy:.2f}",
                physics_trigger=PhysicsRule.ENTROPY_HIGH.value
            ))
        
        # Rule: Agent value ≤ 0 → Revoke agent
        for agent_id, value in state.agent_values.items():
            if value <= self.THRESHOLD_AGENT_VALUE_CRITICAL:
                actions.append(GovernanceAction(
                    action_type="revoke_agent",
                    target=agent_id,
                    severity="critical",
                    reason=f"Agent value depleted: {value:.2f}",
                    physics_trigger=PhysicsRule.AGENT_VALUE_ZERO.value
                ))
        
        # Rule: Agent trust < 0.3 → Downgrade role
        for agent_id, trust in state.agent_trust.items():
            if trust < self.THRESHOLD_AGENT_TRUST_WARNING:
                actions.append(GovernanceAction(
                    action_type="downgrade_role",
                    target=agent_id,
                    severity="medium",
                    reason=f"Low agent trust: {trust:.2f}",
                    physics_trigger=PhysicsRule.AGENT_TRUST_LOW.value
                ))
        
        # === MONITORING RULES ===
        
        # Rule: Mass imbalance → Log warning
        if state.node_count > 0:
            avg_mass = state.total_mass / state.node_count
            if avg_mass > self.THRESHOLD_MASS_IMBALANCE:
                actions.append(GovernanceAction(
                    action_type="log_warning",
                    severity="low",
                    reason=f"Mass imbalance detected: avg_mass={avg_mass:.2f}",
                    physics_trigger=PhysicsRule.MASS_IMBALANCE.value
                ))
        
        # Rule: Energy spike → Log warning
        if state.total_energy > self.THRESHOLD_ENERGY_SPIKE:
            actions.append(GovernanceAction(
                action_type="log_warning",
                severity="low",
                reason=f"Energy spike detected: {state.total_energy:.2f}",
                physics_trigger=PhysicsRule.ENERGY_SPIKE.value
            ))
        
        return actions
    
    async def execute_actions(self, actions: List[GovernanceAction]) -> bool:
        """
        Execute governance actions through RARA.
        Physics never acts directly - always through RARA.
        """
        success = True
        
        for action in actions:
            try:
                action_success = await self._execute_single_action(action)
                if not action_success:
                    success = False
                    logger.error(f"Failed to execute action: {action.action_type}")
                else:
                    logger.info(f"Executed action: {action.action_type}")
                
                # Record action
                self.action_history.append(action)
                
            except Exception as e:
                success = False
                logger.error(f"Action execution error: {e}")
        
        return success
    
    async def _execute_single_action(self, action: GovernanceAction) -> bool:
        """Execute a single governance action through RARA"""
        
        # === CRITICAL ACTIONS ===
        
        if action.action_type == "emergency_stop":
            if self.kill_switch:
                return await self._trigger_emergency_stop(action)
            return False
        
        # === CAPABILITY ACTIONS ===
        
        elif action.action_type == "freeze_capabilities":
            if self.kill_switch:
                return await self._freeze_capabilities(action)
            return False
        
        elif action.action_type == "revoke_agent":
            if self.capability_engine and action.target:
                return await self._revoke_agent(action)
            return False
        
        elif action.action_type == "downgrade_role":
            if self.capability_engine and action.target:
                return await self._downgrade_agent_role(action)
            return False
        
        # === MONITORING ACTIONS ===
        
        elif action.action_type == "log_warning":
            logger.warning(f"Physics warning: {action.reason}")
            return True
        
        else:
            logger.warning(f"Unknown action type: {action.action_type}")
            return False
    
    async def _trigger_emergency_stop(self, action: GovernanceAction) -> bool:
        """Trigger emergency stop via kill switch"""
        try:
            # Use kill switch to stop all mutations
            self.kill_switch.trigger_emergency_stop(
                trigger=KillSwitchTrigger.INVARIANT,
                reason=f"Physics emergency stop: {action.reason}",
                metadata={"physics_trigger": action.physics_trigger}
            )
            logger.critical(f"Emergency stop triggered: {action.reason}")
            return True
        except Exception as e:
            logger.error(f"Emergency stop failed: {e}")
            return False
    
    async def _freeze_capabilities(self, action: GovernanceAction) -> bool:
        """Freeze all capabilities via kill switch"""
        try:
            self.kill_switch.freeze(
                trigger=KillSwitchTrigger.INVARIANT,
                reason=f"Physics capability freeze: {action.reason}",
                metadata={"physics_trigger": action.physics_trigger}
            )
            logger.warning(f"Capabilities frozen: {action.reason}")
            return True
        except Exception as e:
            logger.error(f"Capability freeze failed: {e}")
            return False
    
    async def _revoke_agent(self, action: GovernanceAction) -> bool:
        """Revoke agent capabilities"""
        try:
            # Set all capabilities to revoked state
            if action.target in self.capability_engine.manifests:
                manifest = self.capability_engine.manifests[action.target]
                for capability in manifest.capabilities.values():
                    capability.trust = 0.0  # Complete revocation
                
                self.capability_engine._save_state()
                logger.warning(f"Agent {action.target} revoked: {action.reason}")
                return True
            return False
        except Exception as e:
            logger.error(f"Agent revocation failed: {e}")
            return False
    
    async def _downgrade_agent_role(self, action: GovernanceAction) -> bool:
        """Downgrade agent role based on trust"""
        try:
            if action.target in self.capability_engine.manifests:
                manifest = self.capability_engine.manifests[action.target]
                
                # Reduce trust for all capabilities
                for capability in manifest.capabilities.values():
                    capability.update_failure()  # Apply trust decay
                
                self.capability_engine._save_state()
                logger.warning(f"Agent {action.target} downgraded: {action.reason}")
                return True
            return False
        except Exception as e:
            logger.error(f"Agent downgrade failed: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get bridge status for monitoring"""
        return {
            "last_evaluation": self.last_evaluation.isoformat() if self.last_evaluation else None,
            "actions_generated": len(self.action_history),
            "recent_actions": [
                {
                    "type": a.action_type,
                    "target": a.target,
                    "severity": a.severity,
                    "reason": a.reason,
                    "timestamp": a.timestamp.isoformat()
                }
                for a in self.action_history[-10:]  # Last 10 actions
            ],
            "thresholds": {
                "collapse_risk_critical": self.THRESHOLD_COLLAPSE_RISK_CRITICAL,
                "entropy_warning": self.THRESHOLD_ENTROPY_WARNING,
                "agent_value_critical": self.THRESHOLD_AGENT_VALUE_CRITICAL,
                "agent_trust_warning": self.THRESHOLD_AGENT_TRUST_WARNING
            }
        }


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

physics_bridge: PhysicsGovernanceBridge = None


def get_physics_bridge() -> Optional[PhysicsGovernanceBridge]:
    """Get the global physics bridge instance"""
    return physics_bridge


def initialize_physics_bridge(
    capability_engine: CapabilityEngine = None,
    kill_switch: KillSwitch = None
) -> PhysicsGovernanceBridge:
    """Initialize the global physics bridge"""
    global physics_bridge
    physics_bridge = PhysicsGovernanceBridge(
        capability_engine=capability_engine,
        kill_switch=kill_switch
    )
    return physics_bridge
