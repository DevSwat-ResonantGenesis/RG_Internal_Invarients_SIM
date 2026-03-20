"""
Irreversibility Authority

Complete authority over irreversible effects.
This integrates all components to provide formal authority over irreversibility.

STATUS: PRODUCTION IMPLEMENTATION
UPDATED: 2026-01-08
PURPOSE: Complete flow for irreversible effect execution
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
import logging

from .effect_boundary import EffectBoundaryRegistry, get_effect_registry
from .epoch_authority import EpochAuthority, get_epoch_authority
from .pre_auth_gate import PreAuthorizationGate, get_pre_auth_gate, AuthorizationResponse, EffectResult
from .quorum_authority import QuorumAuthority, get_quorum_authority, ProposalResponse, VoteResult

logger = logging.getLogger(__name__)


@dataclass
class IrreversibilityConfig:
    """Configuration for irreversibility authority"""
    enable_epochs: bool = True
    enable_quorum: bool = True
    enable_physics_checks: bool = True
    default_epoch_timeout_ms: int = 1000
    default_quorum_size: int = 3
    default_veto_threshold: float = 0.3
    cleanup_interval_ms: int = 10000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "enable_epochs": self.enable_epochs,
            "enable_quorum": self.enable_quorum,
            "enable_physics_checks": self.enable_physics_checks,
            "default_epoch_timeout_ms": self.default_epoch_timeout_ms,
            "default_quorum_size": self.default_quorum_size,
            "default_veto_threshold": self.default_veto_threshold,
            "cleanup_interval_ms": self.cleanup_interval_ms
        }


class IrreversibilityAuthority:
    """Complete authority over irreversible effects"""
    
    def __init__(
        self,
        effect_registry: EffectBoundaryRegistry,
        epoch_authority: EpochAuthority,
        pre_auth_gate: PreAuthorizationGate,
        quorum_authority: Optional[QuorumAuthority] = None,
        config: Optional[IrreversibilityConfig] = None
    ):
        self.effect_registry = effect_registry
        self.epoch_authority = epoch_authority
        self.pre_auth_gate = pre_auth_gate
        self.quorum_authority = quorum_authority
        self.config = config or IrreversibilityConfig()
        
        # Statistics
        self.total_requests: int = 0
        self.successful_executions: int = 0
        self.failed_executions: int = 0
        
        logger.info("IrreversibilityAuthority initialized")
    
    async def execute_irreversible_effect(
        self,
        agent_id: str,
        effect_type: str,
        effect_payload: Dict[str, Any],
        effect_executor: Callable,
        timeout_ms: Optional[int] = None,
        require_quorum: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> EffectResult:
        """Complete flow for irreversible effect execution"""
        
        self.total_requests += 1
        start_time = datetime.utcnow()
        
        try:
            # Step 1: Validate effect request
            valid, reason = self.effect_registry.validate_effect_request(effect_type, effect_payload)
            if not valid:
                self.failed_executions += 1
                return EffectResult(
                    success=False,
                    reason=f"Effect validation failed: {reason}"
                )
            
            # Step 2: Check if quorum is required
            should_require_quorum = require_quorum or (
                self.config.enable_quorum and 
                self.effect_registry.get_quorum_required(effect_type) > 1
            )
            
            if should_require_quorum and self.quorum_authority:
                # Step 2a: Create proposal for quorum approval
                proposal_response = await self.quorum_authority.propose_effect(
                    proposer_id=agent_id,
                    effect_type=effect_type,
                    effect_payload=effect_payload,
                    description=f"Quorum approval for {effect_type}",
                    votes_required=self.effect_registry.get_quorum_required(effect_type)
                )
                
                if proposal_response.status != "pending":
                    self.failed_executions += 1
                    return EffectResult(
                        success=False,
                        reason=f"Quorum proposal failed: {proposal_response.message}"
                    )
                
                # Step 2b: Wait for quorum decision (simplified - in production would use async waiting)
                proposal = self.quorum_authority.get_proposal(proposal_response.proposal_id)
                if not proposal or not proposal.is_approved:
                    self.failed_executions += 1
                    return EffectResult(
                        success=False,
                        reason="Quorum approval not obtained"
                    )
            
            # Step 3: Request pre-authorization
            auth_response = await self.pre_auth_gate.request_authorization(
                agent_id=agent_id,
                effect_type=effect_type,
                effect_payload=effect_payload,
                timeout_ms=timeout_ms,
                metadata=metadata
            )
            
            if not auth_response.approved:
                self.failed_executions += 1
                return EffectResult(
                    success=False,
                    reason=f"Authorization failed: {auth_response.reason}"
                )
            
            # Step 4: Execute effect with authorization
            result = await self.pre_auth_gate.execute_effect(
                auth_response.auth_token,
                effect_executor
            )
            
            if result.success:
                self.successful_executions += 1
                logger.info(f"Irreversible effect executed successfully: {effect_type} by {agent_id}")
            else:
                self.failed_executions += 1
                logger.warning(f"Irreversible effect execution failed: {effect_type} by {agent_id} - {result.reason}")
            
            return result
            
        except Exception as e:
            self.failed_executions += 1
            logger.error(f"Irreversible effect execution error: {e}")
            return EffectResult(
                success=False,
                reason=f"Internal error: {str(e)}"
            )
    
    async def request_effect_authorization(
        self,
        agent_id: str,
        effect_type: str,
        effect_payload: Dict[str, Any],
        timeout_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuthorizationResponse:
        """Request authorization for irreversible effect (without execution)"""
        
        try:
            # Validate effect request
            valid, reason = self.effect_registry.validate_effect_request(effect_type, effect_payload)
            if not valid:
                return AuthorizationResponse(
                    approved=False,
                    reason=f"Effect validation failed: {reason}"
                )
            
            # Request pre-authorization
            return await self.pre_auth_gate.request_authorization(
                agent_id=agent_id,
                effect_type=effect_type,
                effect_payload=effect_payload,
                timeout_ms=timeout_ms,
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Authorization request error: {e}")
            return AuthorizationResponse(
                approved=False,
                reason=f"Internal error: {str(e)}"
            )
    
    async def execute_with_authorization(
        self,
        auth_token: str,
        effect_executor: Callable
    ) -> EffectResult:
        """Execute effect with existing authorization"""
        
        try:
            return await self.pre_auth_gate.execute_effect(auth_token, effect_executor)
        except Exception as e:
            logger.error(f"Effect execution error: {e}")
            return EffectResult(
                success=False,
                reason=f"Internal error: {str(e)}"
            )
    
    async def propose_quorum_effect(
        self,
        agent_id: str,
        effect_type: str,
        effect_payload: Dict[str, Any],
        description: str = "",
        votes_required: Optional[int] = None
    ) -> ProposalResponse:
        """Propose effect for quorum approval"""
        
        if not self.quorum_authority:
            return ProposalResponse(
                proposal_id="",
                status="unavailable",
                votes_required=0,
                veto_threshold=0.0,
                expires_at=datetime.utcnow(),
                message="Quorum authority not available"
            )
        
        try:
            return await self.quorum_authority.propose_effect(
                proposer_id=agent_id,
                effect_type=effect_type,
                effect_payload=effect_payload,
                description=description,
                votes_required=votes_required
            )
        except Exception as e:
            logger.error(f"Quorum proposal error: {e}")
            return ProposalResponse(
                proposal_id="",
                status="error",
                votes_required=0,
                veto_threshold=0.0,
                expires_at=datetime.utcnow(),
                message=f"Internal error: {str(e)}"
            )
    
    async def vote_on_quorum_proposal(
        self,
        proposal_id: str,
        voter_id: str,
        vote_type: str,
        reason: str = ""
    ) -> VoteResult:
        """Vote on quorum proposal"""
        
        if not self.quorum_authority:
            return VoteResult(
                success=False,
                result="unavailable",
                proposal_status=None,
                vote_counts={},
                message="Quorum authority not available"
            )
        
        try:
            return await self.quorum_authority.vote_on_proposal(
                proposal_id=proposal_id,
                voter_id=voter_id,
                vote_type=vote_type,
                reason=reason
            )
        except Exception as e:
            logger.error(f"Quorum voting error: {e}")
            return VoteResult(
                success=False,
                result="error",
                proposal_status=None,
                vote_counts={},
                message=f"Internal error: {str(e)}"
            )
    
    def create_epoch(
        self,
        commit_window_ms: Optional[int] = None,
        max_effects: Optional[int] = None,
        created_by: str = "system"
    ) -> Optional[str]:
        """Create new epoch"""
        
        if not self.config.enable_epochs:
            return None
        
        try:
            epoch = self.epoch_authority.create_epoch(
                commit_window_ms=commit_window_ms,
                max_effects=max_effects,
                created_by=created_by
            )
            return epoch.epoch_id
        except Exception as e:
            logger.error(f"Epoch creation error: {e}")
            return None
    
    def close_epoch(self, force: bool = False) -> bool:
        """Close current epoch"""
        
        if not self.config.enable_epochs:
            return False
        
        try:
            success, reason = self.epoch_authority.close_epoch(force)
            return success
        except Exception as e:
            logger.error(f"Epoch closing error: {e}")
            return False
    
    def add_authorized_voter(self, voter_id: str, weight: float = 1.0) -> bool:
        """Add authorized voter for quorum"""
        
        if not self.quorum_authority:
            return False
        
        try:
            return self.quorum_authority.add_authorized_voter(voter_id, weight)
        except Exception as e:
            logger.error(f"Voter addition error: {e}")
            return False
    
    def remove_authorized_voter(self, voter_id: str) -> bool:
        """Remove authorized voter"""
        
        if not self.quorum_authority:
            return False
        
        try:
            return self.quorum_authority.remove_authorized_voter(voter_id)
        except Exception as e:
            logger.error(f"Voter removal error: {e}")
            return False
    
    def cleanup_expired_resources(self) -> Dict[str, int]:
        """Clean up expired resources"""
        
        cleanup_results = {}
        
        try:
            # Clean up expired authorizations
            expired_auths = self.pre_auth_gate.cleanup_expired_authorizations()
            cleanup_results["expired_authorizations"] = expired_auths
            
            # Clean up expired epochs
            expired_epochs = self.epoch_authority.cleanup_expired_epochs()
            cleanup_results["expired_epochs"] = expired_epochs
            
            # Clean up expired proposals
            expired_proposals = 0
            if self.quorum_authority:
                expired_proposals = self.quorum_authority.cleanup_expired_proposals()
            cleanup_results["expired_proposals"] = expired_proposals
            
            total_cleaned = sum(cleanup_results.values())
            if total_cleaned > 0:
                logger.info(f"Cleaned up expired resources: {cleanup_results}")
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            cleanup_results["error"] = 1
        
        return cleanup_results
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        
        stats = {
            "total_requests": self.total_requests,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "success_rate": self.successful_executions / self.total_requests if self.total_requests > 0 else 0.0,
            "config": self.config.to_dict()
        }
        
        # Add component statistics
        try:
            stats["effect_registry"] = self.effect_registry.get_status()
            stats["epoch_authority"] = self.epoch_authority.get_status()
            stats["pre_auth_gate"] = self.pre_auth_gate.get_status()
            if self.quorum_authority:
                stats["quorum_authority"] = self.quorum_authority.get_status()
        except Exception as e:
            logger.error(f"Statistics collection error: {e}")
            stats["collection_error"] = str(e)
        
        return stats
    
    def get_status(self) -> Dict[str, Any]:
        """Get authority status for monitoring"""
        
        return {
            "total_requests": self.total_requests,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "success_rate": self.successful_executions / self.total_requests if self.total_requests > 0 else 0.0,
            "config": self.config.to_dict(),
            "components": {
                "effect_registry": self.effect_registry.get_status(),
                "epoch_authority": self.epoch_authority.get_status(),
                "pre_auth_gate": self.pre_auth_gate.get_status(),
                "quorum_authority": self.quorum_authority.get_status() if self.quorum_authority else None
            },
            "last_cleanup": datetime.utcnow().isoformat()
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Health check for all components"""
        
        health = {
            "overall": "healthy",
            "components": {},
            "issues": []
        }
        
        # Check effect registry
        try:
            effects = self.effect_registry.list_effects()
            health["components"]["effect_registry"] = "healthy" if effects else "no_effects"
        except Exception as e:
            health["components"]["effect_registry"] = "error"
            health["issues"].append(f"Effect registry error: {e}")
        
        # Check epoch authority
        try:
            current_epoch = self.epoch_authority.get_current_epoch()
            health["components"]["epoch_authority"] = "healthy"
        except Exception as e:
            health["components"]["epoch_authority"] = "error"
            health["issues"].append(f"Epoch authority error: {e}")
        
        # Check pre-auth gate
        try:
            pending = self.pre_auth_gate.get_pending_authorizations()
            health["components"]["pre_auth_gate"] = "healthy"
        except Exception as e:
            health["components"]["pre_auth_gate"] = "error"
            health["issues"].append(f"Pre-auth gate error: {e}")
        
        # Check quorum authority
        if self.quorum_authority:
            try:
                proposals = self.quorum_authority.get_active_proposals()
                health["components"]["quorum_authority"] = "healthy"
            except Exception as e:
                health["components"]["quorum_authority"] = "error"
                health["issues"].append(f"Quorum authority error: {e}")
        
        # Determine overall health
        if health["issues"]:
            health["overall"] = "degraded" if len(health["issues"]) < 3 else "unhealthy"
        
        return health


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

irreversibility_authority: IrreversibilityAuthority = None


def get_irreversibility_authority() -> Optional[IrreversibilityAuthority]:
    """Get the global irreversibility authority instance"""
    return irreversibility_authority


def initialize_irreversibility_authority(
    effect_registry: EffectBoundaryRegistry,
    epoch_authority: EpochAuthority,
    pre_auth_gate: PreAuthorizationGate,
    quorum_authority: Optional[QuorumAuthority] = None,
    config: Optional[IrreversibilityConfig] = None
) -> IrreversibilityAuthority:
    """Initialize the global irreversibility authority"""
    global irreversibility_authority
    irreversibility_authority = IrreversibilityAuthority(
        effect_registry=effect_registry,
        epoch_authority=epoch_authority,
        pre_auth_gate=pre_auth_gate,
        quorum_authority=quorum_authority,
        config=config
    )
    return irreversibility_authority
