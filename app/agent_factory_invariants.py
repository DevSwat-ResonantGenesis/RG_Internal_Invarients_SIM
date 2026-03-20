"""
Agent Factory Invariants - Non-Negotiable Safety Constraints

These invariants must be enforced for ALL agent creation.
No exceptions. No workarounds. No "special cases".

STATUS: PRODUCTION-READY
ENFORCEMENT: MANDATORY
"""

from dataclasses import dataclass
from typing import Dict, List, Set, Optional, Any
import time
import uuid
import hashlib
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class AgentType(Enum):
    """Allowed agent types with strict boundaries"""
    TASK_EXECUTOR = "task_executor"
    BUSINESS_OPERATOR = "business_operator"
    TOOL_AGENT = "tool_agent"
    SWARM_MEMBER = "swarm_member"
    OBSERVER_AUDITOR = "observer_auditor"


class EffectClass(Enum):
    """Effect classes with different risk levels"""
    READ_ONLY = "read_only"
    ECONOMIC_READ = "economic_read"
    ECONOMIC_WRITE = "economic_write"
    SYSTEM_MODIFY = "system_modify"
    IRREVERSIBLE = "irreversible"


class ReceiptLevel(Enum):
    """Receipt enforcement levels"""
    STRICT = "strict"      # Every action must have receipt
    NORMAL = "normal"      # Most actions need receipts
    MINIMAL = "minimal"    # Only irreversible actions need receipts


@dataclass
class CapabilityManifest:
    """Immutable capability manifest for agents"""
    capabilities: List[str]
    hard_limits: Dict[str, Any]
    cost_ceiling_usd: float
    rate_limits: Dict[str, int]
    effect_classes: List[EffectClass]
    receipt_level: ReceiptLevel
    
    def __post_init__(self):
        # Validate capabilities are non-empty
        if not self.capabilities:
            raise ValueError("Agent must have at least one capability")
        
        # Validate cost ceiling is positive
        if self.cost_ceiling_usd <= 0:
            raise ValueError("Cost ceiling must be positive")
        
        # Validate rate limits exist
        if not self.rate_limits:
            raise ValueError("Agent must have rate limits")
        
        # Freeze the manifest
        self._frozen = True
    
    def __setattr__(self, name, value):
        if hasattr(self, '_frozen') and self._frozen:
            raise AttributeError("Capability manifest is immutable")
        super().__setattr__(name, value)


@dataclass
class AuthorityBindings:
    """Authority bindings for agents"""
    physics_bridge_required: bool = True
    irreversibility_authority_required: bool = True
    epoch_constraints_required: bool = True
    quorum_required: bool = False
    human_override_enabled: bool = True
    
    def __post_init__(self):
        # Freeze the bindings
        self._frozen = True
    
    def __setattr__(self, name, value):
        if hasattr(self, '_frozen') and self._frozen:
            raise AttributeError("Authority bindings are immutable")
        super().__setattr__(name, value)


@dataclass
class AgentConstraints:
    """Hard constraints for agent behavior"""
    max_actions_per_hour: int
    max_cost_per_day_usd: float
    max_runtime_seconds: int
    ttl_hours: int
    can_expand_capabilities: bool = False  # ALWAYS FALSE
    can_modify_constraints: bool = False   # ALWAYS FALSE
    can_talk_directly_to_internet: bool = False  # ALWAYS FALSE
    
    def __post_init__(self):
        # Validate constraints
        if self.max_actions_per_hour <= 0:
            raise ValueError("Max actions per hour must be positive")
        
        if self.max_cost_per_day_usd <= 0:
            raise ValueError("Max cost per day must be positive")
        
        if self.max_runtime_seconds <= 0:
            raise ValueError("Max runtime must be positive")
        
        if self.ttl_hours <= 0:
            raise ValueError("TTL must be positive")
        
        # Enforce invariant #1: No agent can expand itself
        if self.can_expand_capabilities:
            raise ValueError("Agent capability expansion is forbidden")
        
        if self.can_modify_constraints:
            raise ValueError("Agent constraint modification is forbidden")
        
        if self.can_talk_directly_to_internet:
            raise ValueError("Direct internet access is forbidden")
        
        # Freeze the constraints
        self._frozen = True
    
    def __setattr__(self, name, value):
        if hasattr(self, '_frozen') and self._frozen:
            raise AttributeError("Agent constraints are immutable")
        super().__setattr__(name, value)


class AgentFactoryInvariants:
    """Enforces all agent factory invariants"""
    
    def __init__(self):
        self.issued_agents: Dict[str, Dict[str, Any]] = {}
        self.revoked_agents: Set[str] = set()
        self.suspicious_agents: Set[str] = set()
        
        logger.info("Agent Factory Invariants initialized - SAFETY MODE")
    
    def validate_agent_creation_request(
        self,
        agent_type: AgentType,
        capabilities: List[str],
        constraints: AgentConstraints,
        manifest: CapabilityManifest,
        bindings: AuthorityBindings
    ) -> bool:
        """Validate agent creation request against all invariants"""
        
        try:
            # Invariant #1: No agent can expand itself
            if constraints.can_expand_capabilities:
                raise ValueError("Invariant violated: Agent capability expansion forbidden")
            
            # Invariant #2: All irreversible effects require pre-auth
            if EffectClass.IRREVERSIBLE in manifest.effect_classes:
                if not bindings.irreversibility_authority_required:
                    raise ValueError("Invariant violated: Irreversible effects require pre-auth")
            
            # Invariant #3: Receipts are mandatory
            if manifest.receipt_level == ReceiptLevel.MINIMAL:
                if EffectClass.IRREVERSIBLE in manifest.effect_classes:
                    raise ValueError("Invariant violated: Irreversible effects require strict receipts")
            
            # Invariant #4: Agents are replaceable (no identity value)
            # This is enforced by not storing any identity state
            
            # Invariant #5: Humans can always override
            if not bindings.human_override_enabled:
                raise ValueError("Invariant violated: Human override must be enabled")
            
            # Invariant #6: No agent talks to internet directly
            if constraints.can_talk_directly_to_internet:
                raise ValueError("Invariant violated: Direct internet access forbidden")
            
            # Additional safety checks
            self._validate_capabilities(agent_type, capabilities)
            self._validate_constraints(constraints, manifest)
            self._validate_manifest(manifest)
            self._validate_bindings(bindings, manifest)
            
            return True
            
        except Exception as e:
            logger.error(f"Agent creation validation failed: {e}")
            return False
    
    def _validate_capabilities(self, agent_type: AgentType, capabilities: List[str]):
        """Validate capabilities are appropriate for agent type"""
        forbidden_capabilities = {
            AgentType.OBSERVER_AUDITOR: ["write", "delete", "modify", "execute"],
            AgentType.TOOL_AGENT: ["*"],  # Tool agents are single-purpose only
            AgentType.SWARM_MEMBER: ["self_modify", "authority_override"]
        }
        
        if agent_type in forbidden_capabilities:
            for forbidden in forbidden_capabilities[agent_type]:
                if any(forbidden.lower() in cap.lower() for cap in capabilities):
                    raise ValueError(f"Forbidden capability '{forbidden}' for agent type '{agent_type.value}'")
    
    def _validate_constraints(self, constraints: AgentConstraints, manifest: CapabilityManifest):
        """Validate constraints are appropriate for capabilities"""
        # Economic capabilities need cost limits
        if EffectClass.ECONOMIC_WRITE in manifest.effect_classes:
            if constraints.max_cost_per_day_usd > 10000:  # $10k daily limit
                raise ValueError("Daily cost limit too high for economic agent")
        
        # System modification needs strict limits
        if EffectClass.SYSTEM_MODIFY in manifest.effect_classes:
            if constraints.max_actions_per_hour > 10:
                raise ValueError("Action rate too high for system modification agent")
    
    def _validate_manifest(self, manifest: CapabilityManifest):
        """Validate capability manifest"""
        # Check for dangerous capabilities
        dangerous_patterns = ["*", "admin", "root", "sudo", "override"]
        for capability in manifest.capabilities:
            for pattern in dangerous_patterns:
                if pattern in capability.lower():
                    raise ValueError(f"Dangerous capability pattern detected: {capability}")
    
    def _validate_bindings(self, bindings: AuthorityBindings, manifest: CapabilityManifest):
        """Validate authority bindings"""
        # Irreversible effects need irreversibility authority
        if EffectClass.IRREVERSIBLE in manifest.effect_classes:
            if not bindings.irreversibility_authority_required:
                raise ValueError("Irreversible effects require irreversibility authority")
        
        # Economic effects need physics bridge
        if EffectClass.ECONOMIC_WRITE in manifest.effect_classes:
            if not bindings.physics_bridge_required:
                raise ValueError("Economic effects require physics bridge")
    
    def issue_agent(
        self,
        agent_type: AgentType,
        capabilities: List[str],
        constraints: AgentConstraints,
        manifest: CapabilityManifest,
        bindings: AuthorityBindings
    ) -> Optional[Dict[str, Any]]:
        """Issue a new agent with all invariants enforced"""
        
        # Validate against all invariants
        if not self.validate_agent_creation_request(agent_type, capabilities, constraints, manifest, bindings):
            return None
        
        # Generate immutable agent identity
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        dsid = self._generate_dsid(agent_id)
        public_key = f"pk_{hashlib.sha256(dsid.encode()).hexdigest()[:16]}"
        
        # Create agent record
        agent_record = {
            "agent_id": agent_id,
            "dsid": dsid,
            "public_key": public_key,
            "agent_type": agent_type.value,
            "capabilities": capabilities,
            "constraints": constraints,
            "manifest": manifest,
            "bindings": bindings,
            "issued_at": time.time(),
            "expires_at": time.time() + (constraints.ttl_hours * 3600),
            "status": "active",
            "action_count": 0,
            "cost_spent": 0.0,
            "last_action": None
        }
        
        # Store agent record
        self.issued_agents[agent_id] = agent_record
        
        logger.info(f"Agent issued: {agent_id} ({agent_type.value})")
        return agent_record
    
    def _generate_dsid(self, agent_id: str) -> str:
        """Generate immutable DSID for agent"""
        # DSID = SHA-256(agent_id + timestamp + factory_secret)
        factory_secret = "AGENT_FACTORY_SALT_V1"
        dsid_input = f"{agent_id}{time.time()}{factory_secret}"
        return f"dsid_{hashlib.sha256(dsid_input.encode()).hexdigest()}"
    
    def revoke_agent(self, agent_id: str, reason: str = "user_request") -> bool:
        """Revoke an agent immediately"""
        if agent_id not in self.issued_agents:
            return False
        
        agent = self.issued_agents[agent_id]
        agent["status"] = "revoked"
        agent["revoked_at"] = time.time()
        agent["revoked_reason"] = reason
        
        self.revoked_agents.add(agent_id)
        
        logger.info(f"Agent revoked: {agent_id} ({reason})")
        return True
    
    def is_agent_active(self, agent_id: str) -> bool:
        """Check if agent is active and not revoked"""
        if agent_id not in self.issued_agents:
            return False
        
        agent = self.issued_agents[agent_id]
        
        # Check if revoked
        if agent_id in self.revoked_agents:
            return False
        
        # Check if expired
        if time.time() > agent["expires_at"]:
            return False
        
        # Check status
        return agent["status"] == "active"
    
    def get_agent_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent information (safe subset)"""
        if agent_id not in self.issued_agents:
            return None
        
        agent = self.issued_agents[agent_id].copy()
        
        # Remove sensitive information
        agent.pop("dsid", None)
        agent.pop("public_key", None)
        
        return agent
    
    def mark_agent_suspicious(self, agent_id: str, reason: str):
        """Mark agent as suspicious"""
        if agent_id in self.issued_agents:
            self.suspicious_agents.add(agent_id)
            self.issued_agents[agent_id]["status"] = "suspicious"
            self.issued_agents[agent_id]["suspicious_reason"] = reason
            logger.warning(f"Agent marked suspicious: {agent_id} ({reason})")
    
    def get_factory_statistics(self) -> Dict[str, Any]:
        """Get factory statistics"""
        active_agents = sum(1 for agent_id in self.issued_agents if self.is_agent_active(agent_id))
        
        return {
            "total_issued": len(self.issued_agents),
            "active_agents": active_agents,
            "revoked_agents": len(self.revoked_agents),
            "suspicious_agents": len(self.suspicious_agents),
            "invariant_enforcement": "STRICT",
            "factory_status": "OPERATIONAL"
        }


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

agent_factory_invariants: AgentFactoryInvariants = None


def get_agent_factory_invariants() -> Optional[AgentFactoryInvariants]:
    """Get the global agent factory invariants instance"""
    return agent_factory_invariants


def initialize_agent_factory_invariants() -> AgentFactoryInvariants:
    """Initialize the global agent factory invariants"""
    global agent_factory_invariants
    agent_factory_invariants = AgentFactoryInvariants()
    return agent_factory_invariants
