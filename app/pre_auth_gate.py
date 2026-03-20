"""
Pre-Authorization Gate

Gate that must be passed before any irreversible effect.
This provides preventive enforcement for irreversible operations.

STATUS: PRODUCTION IMPLEMENTATION
UPDATED: 2026-01-08
PURPOSE: Prevent unauthorized irreversible effects
"""

import secrets
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from enum import Enum
import logging

from .effect_boundary import EffectBoundaryRegistry, get_effect_registry
from .epoch_authority import EpochAuthority, get_epoch_authority
from .physics_bridge import PhysicsGovernanceBridge, get_physics_bridge

logger = logging.getLogger(__name__)


class AuthStatus(str, Enum):
    """Authorization status states"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"
    CANCELLED = "cancelled"


@dataclass
class AuthorizationRequest:
    """Request for authorization to execute irreversible effect"""
    request_id: str
    agent_id: str
    effect_type: str
    effect_payload: Dict[str, Any]
    timestamp: datetime
    expires_at: datetime
    status: AuthStatus = AuthStatus.PENDING
    auth_token: str = ""
    physics_state: List[Any] = field(default_factory=list)
    epoch_id: Optional[str] = None
    rejection_reason: str = ""
    execution_result: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        """Check if authorization request has expired"""
        return datetime.utcnow() > self.expires_at
    
    @property
    def is_valid(self) -> bool:
        """Check if authorization request is valid"""
        return self.status == AuthStatus.APPROVED and not self.is_expired
    
    @property
    def time_remaining_ms(self) -> int:
        """Get time remaining in authorization"""
        remaining = self.expires_at - datetime.utcnow()
        return max(0, int(remaining.total_seconds() * 1000))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "request_id": self.request_id,
            "agent_id": self.agent_id,
            "effect_type": self.effect_type,
            "effect_payload": self.effect_payload,
            "timestamp": self.timestamp.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "status": self.status.value,
            "auth_token": self.auth_token,
            "epoch_id": self.epoch_id,
            "rejection_reason": self.rejection_reason,
            "is_expired": self.is_expired,
            "is_valid": self.is_valid,
            "time_remaining_ms": self.time_remaining_ms,
            "metadata": self.metadata
        }


@dataclass
class AuthorizationResponse:
    """Response to authorization request"""
    approved: bool
    reason: str
    auth_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    request_id: Optional[str] = None
    epoch_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "approved": self.approved,
            "reason": self.reason,
            "auth_token": self.auth_token,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "request_id": self.request_id,
            "epoch_id": self.epoch_id,
            "metadata": self.metadata
        }


@dataclass
class EffectResult:
    """Result of effect execution"""
    success: bool
    reason: str = ""
    result: Optional[Any] = None
    execution_time_ms: int = 0
    auth_token: Optional[str] = None
    request_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "success": self.success,
            "reason": self.reason,
            "result": self.result,
            "execution_time_ms": self.execution_time_ms,
            "auth_token": self.auth_token,
            "request_id": self.request_id,
            "metadata": self.metadata
        }


class PreAuthorizationGate:
    """Gate that must be passed before any irreversible effect"""
    
    def __init__(
        self,
        epoch_authority: EpochAuthority,
        effect_registry: EffectBoundaryRegistry,
        physics_bridge: PhysicsGovernanceBridge
    ):
        self.epoch_authority = epoch_authority
        self.effect_registry = effect_registry
        self.physics_bridge = physics_bridge
        
        # Authorization state
        self.pending_authorizations: Dict[str, AuthorizationRequest] = {}
        self.authorization_history: List[AuthorizationRequest] = []
        self.max_history_size: int = 10000
        
        # Configuration
        self.default_timeout_ms: int = 5000
        self.max_pending_requests: int = 1000
        
        logger.info("PreAuthorizationGate initialized")
    
    async def request_authorization(
        self,
        agent_id: str,
        effect_type: str,
        effect_payload: Dict[str, Any],
        timeout_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuthorizationResponse:
        """Request authorization for irreversible effect"""
        
        try:
            # Step 1: Validate effect boundary
            valid, reason = self.effect_registry.validate_effect_request(effect_type, effect_payload)
            if not valid:
                return AuthorizationResponse(
                    approved=False,
                    reason=f"Effect validation failed: {reason}"
                )
            
            # Step 2: Check if pre-authorization is required
            if not self.effect_registry.requires_pre_auth(effect_type):
                return AuthorizationResponse(
                    approved=True,
                    reason="Effect type requires no pre-authorization"
                )
            
            # Step 3: Check epoch capacity and requirements
            if self.effect_registry.requires_epoch(effect_type):
                current_epoch = self.epoch_authority.get_current_epoch()
                if not current_epoch:
                    return AuthorizationResponse(
                        approved=False,
                        reason="No active epoch for effect"
                    )
                
                can_commit, commit_reason = self.epoch_authority.can_commit_effect(effect_type)
                if not can_commit:
                    return AuthorizationResponse(
                        approved=False,
                        reason=f"Epoch check failed: {commit_reason}"
                    )
            
            # Step 4: Check pending request limit
            if len(self.pending_authorizations) >= self.max_pending_requests:
                return AuthorizationResponse(
                    approved=False,
                    reason="Too many pending authorization requests"
                )
            
            # Step 5: Physics state evaluation (if required)
            physics_actions = []
            if self.effect_registry.requires_physics_check(effect_type):
                physics_actions = await self.physics_bridge.evaluate_physics_state()
                
                # Check for blocking physics actions
                blocking_actions = [a for a in physics_actions if a.severity == "critical"]
                if blocking_actions:
                    return AuthorizationResponse(
                        approved=False,
                        reason=f"Physics state blocks action: {blocking_actions[0].reason}"
                    )
            
            # Step 6: Generate authorization token and request
            request_id = str(uuid.uuid4())
            auth_token = secrets.token_urlsafe(32)
            timeout = timeout_ms or self.effect_registry.get_timeout_ms(effect_type)
            expires_at = datetime.utcnow() + timedelta(milliseconds=timeout)
            
            # Create authorization request
            auth_request = AuthorizationRequest(
                request_id=request_id,
                agent_id=agent_id,
                effect_type=effect_type,
                effect_payload=effect_payload,
                timestamp=datetime.utcnow(),
                expires_at=expires_at,
                auth_token=auth_token,
                physics_state=physics_actions,
                epoch_id=self.epoch_authority.get_current_epoch().epoch_id if self.epoch_authority.get_current_epoch() else None,
                metadata=metadata or {}
            )
            
            # Store request
            self.pending_authorizations[auth_token] = auth_request
            
            logger.info(f"Authorization request created: {request_id} for agent {agent_id}")
            
            return AuthorizationResponse(
                approved=True,
                reason="Authorization granted",
                auth_token=auth_token,
                expires_at=expires_at,
                request_id=request_id,
                epoch_id=auth_request.epoch_id,
                metadata={
                    "timeout_ms": timeout,
                    "physics_actions": len(physics_actions),
                    "epoch_id": auth_request.epoch_id
                }
            )
            
        except Exception as e:
            logger.error(f"Authorization request failed: {e}")
            return AuthorizationResponse(
                approved=False,
                reason=f"Internal error: {str(e)}"
            )
    
    async def execute_effect(
        self,
        auth_token: str,
        effect_executor: Callable
    ) -> EffectResult:
        """Execute effect with valid authorization"""
        
        start_time = datetime.utcnow()
        
        try:
            # Step 1: Validate authorization
            auth_request = self.pending_authorizations.get(auth_token)
            if not auth_request:
                return EffectResult(
                    success=False,
                    reason="Invalid authorization token",
                    auth_token=auth_token
                )
            
            # Step 2: Check expiration
            if auth_request.is_expired:
                auth_request.status = AuthStatus.EXPIRED
                self._move_to_history(auth_request)
                return EffectResult(
                    success=False,
                    reason="Authorization expired",
                    auth_token=auth_token,
                    request_id=auth_request.request_id
                )
            
            # Step 3: Final physics check (if required)
            if self.effect_registry.requires_physics_check(auth_request.effect_type):
                physics_actions = await self.physics_bridge.evaluate_physics_state()
                blocking_actions = [a for a in physics_actions if a.severity == "critical"]
                if blocking_actions:
                    auth_request.status = AuthStatus.REJECTED
                    auth_request.rejection_reason = f"Physics state changed: {blocking_actions[0].reason}"
                    self._move_to_history(auth_request)
                    return EffectResult(
                        success=False,
                        reason=f"Physics state changed: {blocking_actions[0].reason}",
                        auth_token=auth_token,
                        request_id=auth_request.request_id
                    )
            
            # Step 4: Check epoch capacity again
            if self.effect_registry.requires_epoch(auth_request.effect_type):
                can_commit, commit_reason = self.epoch_authority.can_commit_effect(auth_request.effect_type)
                if not can_commit:
                    auth_request.status = AuthStatus.REJECTED
                    auth_request.rejection_reason = f"Epoch check failed: {commit_reason}"
                    self._move_to_history(auth_request)
                    return EffectResult(
                        success=False,
                        reason=f"Epoch check failed: {commit_reason}",
                        auth_token=auth_token,
                        request_id=auth_request.request_id
                    )
            
            # Step 5: Execute effect
            try:
                result = await effect_executor()
                
                # Step 6: Record in epoch
                if self.effect_registry.requires_epoch(auth_request.effect_type):
                    self.epoch_authority.commit_effect(auth_request.effect_type)
                
                # Step 7: Update authorization request
                auth_request.status = AuthStatus.EXECUTED
                auth_request.execution_result = result
                self._move_to_history(auth_request)
                
                execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                
                logger.info(f"Effect executed successfully: {auth_request.request_id}")
                
                return EffectResult(
                    success=True,
                    result=result,
                    execution_time_ms=execution_time,
                    auth_token=auth_token,
                    request_id=auth_request.request_id
                )
                
            except Exception as e:
                # Execution failed
                auth_request.status = AuthStatus.REJECTED
                auth_request.rejection_reason = f"Effect execution failed: {str(e)}"
                self._move_to_history(auth_request)
                
                execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                
                logger.error(f"Effect execution failed: {auth_request.request_id} - {e}")
                
                return EffectResult(
                    success=False,
                    reason=f"Effect execution failed: {str(e)}",
                    execution_time_ms=execution_time,
                    auth_token=auth_token,
                    request_id=auth_request.request_id
                )
                
        except Exception as e:
            logger.error(f"Effect execution error: {e}")
            return EffectResult(
                success=False,
                reason=f"Internal error: {str(e)}",
                auth_token=auth_token
            )
    
    async def cancel_authorization(self, auth_token: str, reason: str = "Cancelled by request") -> bool:
        """Cancel pending authorization"""
        auth_request = self.pending_authorizations.get(auth_token)
        if not auth_request:
            return False
        
        auth_request.status = AuthStatus.CANCELLED
        auth_request.rejection_reason = reason
        self._move_to_history(auth_request)
        
        logger.info(f"Authorization cancelled: {auth_request.request_id} - {reason}")
        return True
    
    def get_authorization_request(self, auth_token: str) -> Optional[AuthorizationRequest]:
        """Get authorization request by token"""
        return self.pending_authorizations.get(auth_token)
    
    def get_authorization_history(self, limit: int = 100) -> List[AuthorizationRequest]:
        """Get authorization history"""
        return self.authorization_history[-limit:]
    
    def get_pending_authorizations(self, agent_id: Optional[str] = None) -> List[AuthorizationRequest]:
        """Get pending authorizations"""
        pending = list(self.pending_authorizations.values())
        if agent_id:
            pending = [a for a in pending if a.agent_id == agent_id]
        return pending
    
    def cleanup_expired_authorizations(self) -> int:
        """Clean up expired authorizations"""
        expired_tokens = []
        for token, request in self.pending_authorizations.items():
            if request.is_expired:
                expired_tokens.append(token)
        
        for token in expired_tokens:
            request = self.pending_authorizations[token]
            request.status = AuthStatus.EXPIRED
            self._move_to_history(request)
        
        if expired_tokens:
            logger.info(f"Cleaned up {len(expired_tokens)} expired authorizations")
        
        return len(expired_tokens)
    
    def _move_to_history(self, auth_request: AuthorizationRequest):
        """Move authorization request to history"""
        # Remove from pending
        if auth_request.auth_token in self.pending_authorizations:
            del self.pending_authorizations[auth_request.auth_token]
        
        # Add to history
        self.authorization_history.append(auth_request)
        
        # Trim history if needed
        if len(self.authorization_history) > self.max_history_size:
            self.authorization_history = self.authorization_history[-self.max_history_size:]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get gate statistics"""
        total_requests = len(self.authorization_history) + len(self.pending_authorizations)
        
        status_counts = {}
        for status in AuthStatus:
            status_counts[status.value] = 0
        
        # Count pending requests
        for request in self.pending_authorizations.values():
            status_counts[request.status.value] += 1
        
        # Count history requests
        for request in self.authorization_history:
            status_counts[request.status.value] += 1
        
        # Calculate success rate
        executed_requests = [r for r in self.authorization_history if r.status == AuthStatus.EXECUTED]
        success_rate = len(executed_requests) / total_requests if total_requests > 0 else 0
        
        return {
            "total_requests": total_requests,
            "pending_requests": len(self.pending_authorizations),
            "history_size": len(self.authorization_history),
            "status_counts": status_counts,
            "success_rate": success_rate,
            "max_pending_requests": self.max_pending_requests,
            "max_history_size": self.max_history_size
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get gate status for monitoring"""
        return {
            "pending_authorizations": len(self.pending_authorizations),
            "authorization_history_size": len(self.authorization_history),
            "statistics": self.get_statistics(),
            "epoch_authority_status": self.epoch_authority.get_status(),
            "effect_registry_status": self.effect_registry.get_status(),
            "physics_bridge_status": self.physics_bridge.get_status() if self.physics_bridge else None,
            "last_cleanup": datetime.utcnow().isoformat()
        }


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

pre_auth_gate: PreAuthorizationGate = None


def get_pre_auth_gate() -> Optional[PreAuthorizationGate]:
    """Get the global pre-authorization gate instance"""
    return pre_auth_gate


def initialize_pre_auth_gate(
    epoch_authority: EpochAuthority,
    effect_registry: EffectBoundaryRegistry,
    physics_bridge: PhysicsGovernanceBridge
) -> PreAuthorizationGate:
    """Initialize the global pre-authorization gate"""
    global pre_auth_gate
    pre_auth_gate = PreAuthorizationGate(
        epoch_authority=epoch_authority,
        effect_registry=effect_registry,
        physics_bridge=physics_bridge
    )
    return pre_auth_gate
