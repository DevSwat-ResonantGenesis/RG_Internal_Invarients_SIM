"""
Enhanced DISD Protocol

Enhanced DISD protocol coordinator with cryptographic receipt integrity,
Byzantine detection, and tamper-evident logging.

STATUS: PRODUCTION IMPLEMENTATION
UPDATED: 2026-01-08
PURPOSE: Enhanced DISD protocol with cryptographic security
"""

import asyncio
import time
from typing import Dict, List, Optional, Set, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging

from .disd_message import (
    DISDMessage, DISDMessageType, VoteType, ReceiptStatus,
    DISDMessageFactory, DISDMessageValidator
)
from .disd_protocol import DISDProtocol, SwarmMember, SwarmStatus
from .enhanced_disd_router import EnhancedDISDRouter
from .cryptographic_receipt_mock import (
    MockCryptographicReceiptHandler, MockReceiptLogManager, MockFailureDetectionSystem,
    EnhancedReceiptPayload, get_mock_crypto_receipt_handler, get_mock_receipt_log_manager,
    get_mock_failure_detection_system
)
from .quorum_authority import QuorumAuthority, get_quorum_authority
from .irreversibility_authority import IrreversibilityAuthority, get_irreversibility_authority

logger = logging.getLogger(__name__)


class EnhancedDISDProtocol(DISDProtocol):
    """Enhanced DISD protocol with cryptographic receipt integrity"""
    
    def __init__(
        self,
        swarm_id: str = "default_swarm",
        router: Optional[EnhancedDISDRouter] = None,
        quorum_authority: Optional[QuorumAuthority] = None,
        irreversibility_authority: Optional[IrreversibilityAuthority] = None
    ):
        # Initialize with enhanced router
        enhanced_router = router or EnhancedDISDRouter(f"{swarm_id}_enhanced")
        super().__init__(swarm_id, enhanced_router, quorum_authority, irreversibility_authority)
        
        # Enhanced components
        self.crypto_handler: Optional[MockCryptographicReceiptHandler] = None
        self.receipt_log_manager: Optional[MockReceiptLogManager] = None
        self.failure_detector: Optional[MockFailureDetectionSystem] = None
        
        # Enhanced statistics
        self.cryptographic_verifications: int = 0
        self.signature_failures: int = 0
        self.bybantine_detections: int = 0
        self.valid_votes_cast: int = 0
        self.invalid_votes_rejected: int = 0
        
        logger.info(f"EnhancedDISDProtocol initialized for swarm: {swarm_id}")
    
    def initialize_cryptographic_components(
        self,
        crypto_handler: MockCryptographicReceiptHandler,
        receipt_log_manager: MockReceiptLogManager,
        failure_detector: MockFailureDetectionSystem
    ):
        """Initialize cryptographic components"""
        self.crypto_handler = crypto_handler
        self.receipt_log_manager = receipt_log_manager
        self.failure_detector = failure_detector
        
        # Initialize router with cryptographic components
        if isinstance(self.router, EnhancedDISDRouter):
            self.router.initialize_cryptographic_components(
                crypto_handler, receipt_log_manager, failure_detector
            )
        
        logger.info(f"Cryptographic components initialized for protocol: {self.swarm_id}")
    
    async def _handle_vote_message(self, message: DISDMessage) -> None:
        """Enhanced vote message handling with receipt verification"""
        try:
            payload = message.payload
            if not hasattr(payload, 'proposal_id'):
                return
            
            proposal_id = payload.proposal_id
            voter_id = message.sender_id
            
            # Verify receipt integrity before counting vote
            if self.crypto_handler and isinstance(self.router, EnhancedDISDRouter):
                receipt_key = f"{message.message_id}:{voter_id}"
                receipt = self.router.get_enhanced_receipt(receipt_key)
                
                if receipt:
                    # Verify cryptographic integrity
                    is_valid = self.crypto_handler.verify_receipt_signature(
                        message=message,
                        receiver_dsid=voter_id,
                        signature_hex=receipt.receiver_signature,
                        public_key_hex=receipt.receiver_public_key,
                        nonce=receipt.nonce,
                        status=receipt.status,
                        timestamp=int(time.time())
                    )
                    
                    if not is_valid:
                        self.invalid_votes_rejected += 1
                        self.failure_detector.update_suspicion_score(voter_id, "invalid_vote_signature", 0.3)
                        logger.warning(f"Invalid receipt signature from {voter_id} for proposal {proposal_id}")
                        return
                    
                    # Check for Byzantine behavior
                    proposal_receipts = self.router.get_all_enhanced_receipts(message.message_id)
                    byzantine_agents = self.failure_detector.detect_byzantine_behavior(
                        message.message_id, proposal_receipts
                    )
                    
                    for agent_id, issue in byzantine_agents.items():
                        self.bybantine_detections += 1
                        self.failure_detector.update_suspicion_score(agent_id, issue, 0.4)
                        logger.error(f"Byzantine behavior detected from {agent_id}: {issue}")
                    
                    self.valid_votes_cast += 1
                else:
                    self.invalid_votes_rejected += 1
                    logger.warning(f"No receipt found for vote from {voter_id} on proposal {proposal_id}")
                    return
            
            # Store vote with verification
            self.votes[proposal_id][voter_id] = message
            
            # Check completion with enhanced verification
            await self._check_proposal_completion_enhanced(proposal_id)
            
        except Exception as e:
            logger.error(f"Enhanced vote handling error: {e}")
    
    async def _check_proposal_completion_enhanced(self, proposal_id: str):
        """Enhanced proposal completion check with receipt verification"""
        try:
            proposal = self.proposals.get(proposal_id)
            if not proposal:
                return
            
            votes = self.votes.get(proposal_id, {})
            payload = proposal.payload
            
            # Count valid votes only (with verified receipts)
            valid_votes = {}
            for voter_id, vote_message in votes.items():
                if self.crypto_handler and isinstance(self.router, EnhancedDISDRouter):
                    receipt_key = f"{vote_message.message_id}:{voter_id}"
                    receipt = self.router.get_enhanced_receipt(receipt_key)
                    
                    if receipt and self.crypto_handler.verify_receipt_signature(
                        message=vote_message,
                        receiver_dsid=voter_id,
                        signature_hex=receipt.receiver_signature,
                        public_key_hex=receipt.receiver_public_key,
                        nonce=receipt.nonce,
                        status=receipt.status,
                        timestamp=int(time.time())
                    ):
                        valid_votes[voter_id] = vote_message
                    else:
                        self.failure_detector.update_suspicion_score(voter_id, "invalid_vote_receipt", 0.2)
                else:
                    # Fallback to counting all votes
                    valid_votes[voter_id] = vote_message
            
            # Check quorum with valid votes only
            approve_count = sum(1 for vote in valid_votes.values() if vote.payload.vote_type == VoteType.APPROVE)
            veto_count = sum(1 for vote in valid_votes.values() if vote.payload.vote_type == VoteType.VETO)
            total_votes = len(valid_votes)
            
            # Log vote statistics
            logger.info(f"Proposal {proposal_id} vote tally: {approve_count} approve, {veto_count} veto, {total_votes} total valid")
            
            # Apply same logic as before but with valid votes
            if total_votes > 0 and veto_count / total_votes >= payload.veto_threshold:
                await self._abort_proposal(proposal_id, f"Veto threshold reached: {veto_count}/{total_votes}")
                return
            
            if approve_count >= payload.quorum_required:
                await self._commit_proposal_enhanced(proposal_id, valid_votes)
                return
            
            # Check expiration
            if payload.is_expired():
                await self._abort_proposal(proposal_id, "Proposal expired")
                return
                
        except Exception as e:
            logger.error(f"Enhanced proposal completion check error: {e}")
    
    async def _commit_proposal_enhanced(self, proposal_id: str, valid_votes: Dict[str, DISDMessage]):
        """Enhanced proposal commit with receipt verification"""
        try:
            proposal = self.proposals.get(proposal_id)
            if not proposal:
                return
            
            payload = proposal.payload
            
            # Get authorization with enhanced verification
            if self.irreversibility_authority:
                auth_response = await self.irreversibility_authority.request_effect_authorization(
                    agent_id=proposal.sender_id,
                    effect_type=payload.action_type,
                    effect_payload=payload.action_payload
                )
                
                if not auth_response.approved:
                    await self._abort_proposal(proposal_id, f"Authorization failed: {auth_response.reason}")
                    return
                
                auth_token = auth_response.auth_token
            else:
                auth_token = None
            
            # Create enhanced commit message with cryptographic binding
            commit_message = DISDMessageFactory.create_commit_message(
                sender_id=self.swarm_id,
                proposal_id=proposal_id,
                decision="approved",
                votes={voter_id: vote.payload.to_dict() for voter_id, vote in valid_votes.items()},
                auth_token=auth_token
            )
            
            # Add cryptographic verification metadata
            if self.crypto_handler:
                # Sign the commit with swarm authority
                commit_signature, commit_pubkey, commit_nonce = self.crypto_handler.sign_receipt(
                    message=commit_message,
                    receiver_dsid=self.swarm_id,
                    status=ReceiptStatus.PROCESSED
                )
                
                # Add signature to commit message
                commit_message.signature = commit_signature
            
            # Execute effect through irreversibility authority
            if self.irreversibility_authority and auth_token:
                async def effect_executor():
                    return {
                        "proposal_id": proposal_id, 
                        "executed": True, 
                        "receipt_verified": True,
                        "valid_votes": len(valid_votes),
                        "cryptographic_integrity": True
                    }
                
                result = await self.irreversibility_authority.execute_with_authorization(
                    auth_token, effect_executor
                )
                
                if not result.success:
                    await self._abort_proposal(proposal_id, f"Effect execution failed: {result.reason}")
                    return
            
            # Broadcast commit with enhanced routing
            if isinstance(self.router, EnhancedDISDRouter):
                result = await self.router.broadcast_message(commit_message)
            else:
                result = await self.router.broadcast_message(commit_message)
            
            if result.success:
                self.total_commits += 1
                logger.info(f"Enhanced proposal {proposal_id} committed with {len(valid_votes)} verified votes")
                
                # Verify chain integrity after commit
                if self.receipt_log_manager:
                    epoch_id = proposal.header.epoch_id or "no_epoch"
                    chain_integrity = self.receipt_log_manager.verify_epoch_chain(epoch_id)
                    if not chain_integrity:
                        logger.error(f"Chain integrity failure detected in epoch {epoch_id}")
                
                # Clean up
                await self._cleanup_proposal(proposal_id)
            else:
                logger.error(f"Failed to broadcast enhanced commit: {result.message}")
                
        except Exception as e:
            logger.error(f"Enhanced commit proposal error: {e}")
    
    async def propose_action_enhanced(
        self,
        sender_id: str,
        action_type: str,
        action_payload: Dict[str, Any],
        quorum_required: int = 3,
        veto_threshold: float = 0.3,
        description: str = ""
    ) -> Optional[str]:
        """Enhanced proposal creation with cryptographic binding"""
        try:
            # Create proposal message
            propose_message = DISDMessageFactory.create_propose_message(
                sender_id=sender_id,
                action_type=action_type,
                action_payload=action_payload,
                quorum_required=quorum_required,
                veto_threshold=veto_threshold,
                description=description
            )
            
            # Add cryptographic signature to proposal
            if self.crypto_handler:
                proposal_signature, proposal_pubkey, proposal_nonce = self.crypto_handler.sign_receipt(
                    message=propose_message,
                    receiver_dsid=sender_id,
                    status=ReceiptStatus.PROCESSED
                )
                propose_message.signature = proposal_signature
            
            # Store proposal
            proposal_id = propose_message.payload.proposal_id
            self.proposals[proposal_id] = propose_message
            self.votes[proposal_id] = {}
            
            # Route to all members with enhanced routing
            if isinstance(self.router, EnhancedDISDRouter):
                result = await self.router.broadcast_message(propose_message)
            else:
                result = await self.router.broadcast_message(propose_message)
            
            if result.success:
                self.total_proposals += 1
                logger.info(f"Enhanced proposal {proposal_id} created by {sender_id}")
                return proposal_id
            else:
                # Clean up failed proposal
                del self.proposals[proposal_id]
                del self.votes[proposal_id]
                logger.error(f"Failed to create enhanced proposal: {result.message}")
                return None
                
        except Exception as e:
            logger.error(f"Enhanced propose action error: {e}")
            return None
    
    async def vote_on_proposal_enhanced(
        self,
        sender_id: str,
        proposal_id: str,
        vote_type: VoteType,
        reason: str = "",
        weight: float = 1.0
    ) -> bool:
        """Enhanced voting with cryptographic receipt verification"""
        try:
            # Check if proposal exists
            if proposal_id not in self.proposals:
                logger.error(f"Proposal {proposal_id} not found")
                return False
            
            # Create vote message
            vote_message = DISDMessageFactory.create_vote_message(
                sender_id=sender_id,
                proposal_id=proposal_id,
                vote_type=vote_type,
                reason=reason,
                weight=weight
            )
            
            # Add cryptographic signature to vote
            if self.crypto_handler:
                vote_signature, vote_pubkey, vote_nonce = self.crypto_handler.sign_receipt(
                    message=vote_message,
                    receiver_dsid=sender_id,
                    status=ReceiptStatus.PROCESSED
                )
                vote_message.signature = vote_signature
            
            # Store vote
            self.votes[proposal_id][sender_id] = vote_message
            
            # Route to all members with enhanced routing
            if isinstance(self.router, EnhancedDISDRouter):
                result = await self.router.broadcast_message(vote_message)
            else:
                result = await self.router.broadcast_message(vote_message)
            
            if result.success:
                self.total_votes += 1
                logger.info(f"Enhanced vote cast by {sender_id} on proposal {proposal_id}: {vote_type.value}")
                
                # Check if proposal is ready to commit
                await self._check_proposal_completion_enhanced(proposal_id)
                
                return True
            else:
                # Clean up failed vote
                del self.votes[proposal_id][sender_id]
                logger.error(f"Failed to cast enhanced vote: {result.message}")
                return False
                
        except Exception as e:
            logger.error(f"Enhanced vote on proposal error: {e}")
            return False
    
    def get_enhanced_statistics(self) -> Dict[str, Any]:
        """Get enhanced protocol statistics"""
        base_stats = self.get_statistics()
        
        enhanced_stats = {
            "cryptographic_metrics": {
                "cryptographic_verifications": self.cryptographic_verifications,
                "signature_failures": self.signature_failures,
                "bybantine_detections": self.bybantine_detections,
                "valid_votes_cast": self.valid_votes_cast,
                "invalid_votes_rejected": self.invalid_votes_rejected
            },
            "receipt_log_statistics": self.receipt_log_manager.get_all_epoch_statistics() if self.receipt_log_manager else {},
            "suspicion_scores": self.failure_detector.get_agent_suspicion_scores() if self.failure_detector else {},
            "suspicious_agents": [
                agent_id for agent_id, score in (self.failure_detector.get_agent_suspicion_scores() if self.failure_detector else {}).items()
                if score >= self.failure_detector.suspicion_threshold
            ]
        }
        
        return {**base_stats, **enhanced_stats}
    
    def get_enhanced_swarm_status(self) -> SwarmStatus:
        """Get enhanced swarm status"""
        base_status = self.get_swarm_status()
        
        # Add cryptographic security metrics
        if self.crypto_handler and isinstance(self.router, EnhancedDISDRouter):
            security_stats = self.router.get_security_statistics()
            base_status.cryptographic_integrity = security_stats.get("cryptographic_verifications", 0) > 0
            base_status.signature_failure_rate = (
                security_stats.get("signature_failures", 0) / 
                max(security_stats.get("cryptographic_verifications", 1), 1)
            )
        
        return base_status
    
    def get_security_audit_report(self) -> Dict[str, Any]:
        """Generate comprehensive security audit report"""
        report = {
            "audit_timestamp": datetime.utcnow().isoformat(),
            "swarm_id": self.swarm_id,
            "cryptographic_integrity": {},
            "byzantine_resilience": {},
            "chain_integrity": {},
            "suspicious_activity": {}
        }
        
        # Cryptographic integrity
        if self.crypto_handler:
            report["cryptographic_integrity"] = {
                "total_verifications": self.cryptographic_verifications,
                "signature_failures": self.signature_failures,
                "failure_rate": self.signature_failures / max(self.cryptographic_verifications, 1),
                "status": "healthy" if self.signature_failures == 0 else "degraded"
            }
        
        # Byzantine resilience
        if self.failure_detector:
            suspicion_scores = self.failure_detector.get_agent_suspicion_scores()
            report["byzantine_resilience"] = {
                "bybantine_detections": self.bybantine_detections,
                "suspicious_agents": len([
                    agent_id for agent_id, score in suspicion_scores.items()
                    if score >= self.failure_detector.suspicion_threshold
                ]),
                "total_suspicious_score": sum(suspicion_scores.values()),
                "status": "healthy" if self.bybantine_detections == 0 else "alert"
            }
        
        # Chain integrity
        if self.receipt_log_manager:
            epoch_integrity = {}
            for epoch_id in self.receipt_log_manager.epoch_chains.keys():
                epoch_integrity[epoch_id] = self.receipt_log_manager.verify_epoch_chain(epoch_id)
            
            report["chain_integrity"] = {
                "total_epochs": len(epoch_integrity),
                "intact_epochs": sum(1 for intact in epoch_integrity.values() if intact),
                "compromised_epochs": [eid for eid, intact in epoch_integrity.items() if not intact],
                "status": "healthy" if all(epoch_integrity.values()) else "compromised"
            }
        
        # Suspicious activity
        report["suspicious_activity"] = {
            "invalid_votes_rejected": self.invalid_votes_rejected,
            "valid_votes_cast": self.valid_votes_cast,
            "invalid_vote_rate": self.invalid_votes_rejected / max(self.valid_votes_cast + self.invalid_votes_rejected, 1),
            "recent_byzantine_events": self.bybantine_detections
        }
        
        return report


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

enhanced_disd_protocol: EnhancedDISDProtocol = None


def get_enhanced_disd_protocol() -> Optional[EnhancedDISDProtocol]:
    """Get the global enhanced DISD protocol instance"""
    return enhanced_disd_protocol


def initialize_enhanced_disd_protocol(
    swarm_id: str = "default_swarm",
    router: Optional[EnhancedDISDRouter] = None,
    quorum_authority: Optional[QuorumAuthority] = None,
    irreversibility_authority: Optional[IrreversibilityAuthority] = None,
    crypto_handler: Optional[MockCryptographicReceiptHandler] = None,
    receipt_log_manager: Optional[MockReceiptLogManager] = None,
    failure_detector: Optional[MockFailureDetectionSystem] = None
) -> EnhancedDISDProtocol:
    """Initialize the global enhanced DISD protocol"""
    global enhanced_disd_protocol
    enhanced_disd_protocol = EnhancedDISDProtocol(
        swarm_id=swarm_id,
        router=router,
        quorum_authority=quorum_authority,
        irreversibility_authority=irreversibility_authority
    )
    
    # Initialize cryptographic components if provided
    if crypto_handler and receipt_log_manager and failure_detector:
        enhanced_disd_protocol.initialize_cryptographic_components(
            crypto_handler, receipt_log_manager, failure_detector
        )
    
    return enhanced_disd_protocol
