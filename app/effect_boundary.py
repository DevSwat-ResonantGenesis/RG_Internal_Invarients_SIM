"""
Effect Boundary Registry

Defines and manages all irreversible effect boundaries.
This is the foundation for formal authority over irreversibility.

STATUS: PRODUCTION IMPLEMENTATION
UPDATED: 2026-01-08
PURPOSE: Prevent unauthorized irreversible effects
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EffectType(str, Enum):
    """Types of irreversible effects"""
    EXTERNAL_API = "external_api"
    ECONOMIC_TRANSACTION = "economic"
    STATE_COMMIT = "state"
    NETWORK_COMMUNICATION = "network"
    FILE_SYSTEM_WRITE = "filesystem"
    DATABASE_WRITE = "database"
    BLOCKCHAIN_TRANSACTION = "blockchain"
    IDENTITY_ISSUANCE = "identity"


@dataclass
class IrreversibleEffect:
    """Definition of an irreversible effect boundary"""
    effect_id: str
    effect_type: EffectType
    pre_authorization_required: bool = True
    timeout_ms: int = 5000  # Max time to wait for authorization
    rollback_possible: bool = False
    quorum_required: int = 1  # For swarm, >1
    max_retries: int = 0  # No retries for irreversible effects
    requires_epoch: bool = True  # Requires active epoch
    physics_check_required: bool = True  # Requires physics state check
    description: str = ""
    risk_level: str = "medium"  # "low", "medium", "high", "critical"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "effect_id": self.effect_id,
            "effect_type": self.effect_type.value,
            "pre_authorization_required": self.pre_authorization_required,
            "timeout_ms": self.timeout_ms,
            "rollback_possible": self.rollback_possible,
            "quorum_required": self.quorum_required,
            "max_retries": self.max_retries,
            "requires_epoch": self.requires_epoch,
            "physics_check_required": self.physics_check_required,
            "description": self.description,
            "risk_level": self.risk_level
        }


class EffectBoundaryRegistry:
    """Registry of all irreversible effect types"""
    
    def __init__(self):
        self.effects: Dict[str, IrreversibleEffect] = {}
        self._register_standard_effects()
        logger.info("EffectBoundaryRegistry initialized with standard effects")
    
    def register_effect(self, effect: IrreversibleEffect) -> bool:
        """Register a new irreversible effect type"""
        if effect.effect_id in self.effects:
            logger.warning(f"Effect {effect.effect_id} already registered, updating")
        
        self.effects[effect.effect_id] = effect
        logger.info(f"Registered effect: {effect.effect_id} ({effect.effect_type.value})")
        return True
    
    def get_effect(self, effect_id: str) -> Optional[IrreversibleEffect]:
        """Get effect definition by ID"""
        return self.effects.get(effect_id)
    
    def get_effect_by_type(self, effect_type: EffectType) -> List[IrreversibleEffect]:
        """Get all effects of a specific type"""
        return [e for e in self.effects.values() if e.effect_type == effect_type]
    
    def requires_pre_auth(self, effect_id: str) -> bool:
        """Check if effect requires pre-authorization"""
        effect = self.effects.get(effect_id)
        return effect.pre_authorization_required if effect else True
    
    def requires_epoch(self, effect_id: str) -> bool:
        """Check if effect requires active epoch"""
        effect = self.effects.get(effect_id)
        return effect.requires_epoch if effect else True
    
    def requires_physics_check(self, effect_id: str) -> bool:
        """Check if effect requires physics state check"""
        effect = self.effects.get(effect_id)
        return effect.physics_check_required if effect else True
    
    def get_timeout_ms(self, effect_id: str) -> int:
        """Get timeout for effect authorization"""
        effect = self.effects.get(effect_id)
        return effect.timeout_ms if effect else 5000
    
    def is_rollback_possible(self, effect_id: str) -> bool:
        """Check if effect rollback is possible"""
        effect = self.effects.get(effect_id)
        return effect.rollback_possible if effect else False
    
    def get_quorum_required(self, effect_id: str) -> int:
        """Get quorum required for effect"""
        effect = self.effects.get(effect_id)
        return effect.quorum_required if effect else 1
    
    def list_effects(self) -> List[Dict[str, Any]]:
        """List all registered effects"""
        return [effect.to_dict() for effect in self.effects.values()]
    
    def get_effects_by_risk_level(self, risk_level: str) -> List[IrreversibleEffect]:
        """Get all effects by risk level"""
        return [e for e in self.effects.values() if e.risk_level == risk_level]
    
    def _register_standard_effects(self):
        """Register standard irreversible effect types"""
        
        # External API calls
        self.register_effect(IrreversibleEffect(
            effect_id="external_api_call",
            effect_type=EffectType.EXTERNAL_API,
            pre_authorization_required=True,
            timeout_ms=5000,
            rollback_possible=False,
            quorum_required=1,
            requires_epoch=True,
            physics_check_required=True,
            description="External API calls to third-party services",
            risk_level="high"
        ))
        
        # Economic transactions
        self.register_effect(IrreversibleEffect(
            effect_id="economic_payment",
            effect_type=EffectType.ECONOMIC_TRANSACTION,
            pre_authorization_required=True,
            timeout_ms=2000,
            rollback_possible=False,
            quorum_required=2,  # Higher quorum for economic
            requires_epoch=True,
            physics_check_required=True,
            description="Economic payments and transfers",
            risk_level="critical"
        ))
        
        # State commits
        self.register_effect(IrreversibleEffect(
            effect_id="state_commit",
            effect_type=EffectType.STATE_COMMIT,
            pre_authorization_required=True,
            timeout_ms=1000,
            rollback_possible=True,
            quorum_required=1,
            requires_epoch=True,
            physics_check_required=True,
            description="Commit state changes to persistent storage",
            risk_level="medium"
        ))
        
        # Network communications
        self.register_effect(IrreversibleEffect(
            effect_id="network_broadcast",
            effect_type=EffectType.NETWORK_COMMUNICATION,
            pre_authorization_required=True,
            timeout_ms=3000,
            rollback_possible=False,
            quorum_required=1,
            requires_epoch=True,
            physics_check_required=False,  # Network is less physics-dependent
            description="Broadcast messages to network peers",
            risk_level="medium"
        ))
        
        # File system writes
        self.register_effect(IrreversibleEffect(
            effect_id="filesystem_write",
            effect_type=EffectType.FILE_SYSTEM_WRITE,
            pre_authorization_required=True,
            timeout_ms=1000,
            rollback_possible=True,
            quorum_required=1,
            requires_epoch=True,
            physics_check_required=False,
            description="Write files to persistent storage",
            risk_level="low"
        ))
        
        # Database writes
        self.register_effect(IrreversibleEffect(
            effect_id="database_write",
            effect_type=EffectType.DATABASE_WRITE,
            pre_authorization_required=True,
            timeout_ms=2000,
            rollback_possible=True,
            quorum_required=1,
            requires_epoch=True,
            physics_check_required=False,
            description="Write data to database",
            risk_level="medium"
        ))
        
        # Blockchain transactions
        self.register_effect(IrreversibleEffect(
            effect_id="blockchain_transaction",
            effect_type=EffectType.BLOCKCHAIN_TRANSACTION,
            pre_authorization_required=True,
            timeout_ms=10000,  # Longer timeout for blockchain
            rollback_possible=False,
            quorum_required=3,  # High quorum for blockchain
            requires_epoch=True,
            physics_check_required=True,
            description="Submit transactions to blockchain",
            risk_level="critical"
        ))
        
        # Identity issuance
        self.register_effect(IrreversibleEffect(
            effect_id="identity_issuance",
            effect_type=EffectType.IDENTITY_ISSUANCE,
            pre_authorization_required=True,
            timeout_ms=3000,
            rollback_possible=False,
            quorum_required=2,
            requires_epoch=True,
            physics_check_required=True,
            description="Issue new identities or credentials",
            risk_level="critical"
        ))
        
        logger.info(f"Registered {len(self.effects)} standard irreversible effects")
    
    def validate_effect_request(self, effect_id: str, payload: Dict[str, Any]) -> tuple[bool, str]:
        """Validate effect request against boundary rules"""
        effect = self.get_effect(effect_id)
        if not effect:
            return False, f"Unknown effect type: {effect_id}"
        
        # Check required fields in payload
        if effect.effect_type == EffectType.EXTERNAL_API:
            required_fields = ["url", "method"]
            for field in required_fields:
                if field not in payload:
                    return False, f"Missing required field for external API: {field}"
        
        elif effect.effect_type == EffectType.ECONOMIC_TRANSACTION:
            required_fields = ["amount", "recipient"]
            for field in required_fields:
                if field not in payload:
                    return False, f"Missing required field for economic transaction: {field}"
        
        elif effect.effect_type == EffectType.STATE_COMMIT:
            required_fields = ["state_key", "state_value"]
            for field in required_fields:
                if field not in payload:
                    return False, f"Missing required field for state commit: {field}"
        
        return True, "Effect request is valid"
    
    def get_status(self) -> Dict[str, Any]:
        """Get registry status for monitoring"""
        effects_by_type = {}
        for effect_type in EffectType:
            effects_by_type[effect_type.value] = len(self.get_effect_by_type(effect_type))
        
        effects_by_risk = {}
        for risk_level in ["low", "medium", "high", "critical"]:
            effects_by_risk[risk_level] = len(self.get_effects_by_risk_level(risk_level))
        
        return {
            "total_effects": len(self.effects),
            "effects_by_type": effects_by_type,
            "effects_by_risk": effects_by_risk,
            "pre_auth_required": len([e for e in self.effects.values() if e.pre_authorization_required]),
            "rollback_possible": len([e for e in self.effects.values() if e.rollback_possible]),
            "quorum_required": len([e for e in self.effects.values() if e.quorum_required > 1])
        }


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

effect_registry: EffectBoundaryRegistry = None


def get_effect_registry() -> Optional[EffectBoundaryRegistry]:
    """Get the global effect registry instance"""
    return effect_registry


def initialize_effect_registry() -> EffectBoundaryRegistry:
    """Initialize the global effect registry"""
    global effect_registry
    effect_registry = EffectBoundaryRegistry()
    return effect_registry
