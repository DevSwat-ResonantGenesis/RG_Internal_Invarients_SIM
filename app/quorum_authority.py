"""
Quorum Authority

Quorum-based decision making for swarm operations.
This provides collective agreement semantics for distributed autonomy.

STATUS: PRODUCTION IMPLEMENTATION
UPDATED: 2026-01-08
PURPOSE: Quorum-based decision making for swarm operations
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class VoteType(str, Enum):
    """Types of votes"""
    APPROVE = "approve"
    VETO = "veto"
    ABSTAIN = "abstain"


class ProposalStatus(str, Enum):
    """Proposal status states"""
    PENDING = "pending"
    APPROVED = "approved"
    VETOED = "vetoed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class Vote:
    """Individual vote on a proposal"""
    voter_id: str
    vote_type: VoteType
    reason: str
    timestamp: datetime
    weight: float = 1.0  # Voter weight (for weighted voting)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "voter_id": self.voter_id,
            "vote_type": self.vote_type.value,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
            "weight": self.weight
        }


@dataclass
class Proposal:
    """Proposal for quorum approval"""
    proposal_id: str
    proposer_id: str
    effect_type: str
    effect_payload: Dict[str, Any]
    created_at: datetime
    expires_at: datetime
    status: ProposalStatus = ProposalStatus.PENDING
    votes_required: int = 3
    veto_threshold: float = 0.3  # 30% veto threshold
    votes: Dict[str, Vote] = field(default_factory=dict)
    veto_count: int = 0
    approve_count: int = 0
    abstain_count: int = 0
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        """Check if proposal has expired"""
        return datetime.utcnow() > self.expires_at
    
    @property
    def total_votes(self) -> int:
        """Get total number of votes"""
        return len(self.votes)
    
    @property
    def is_approved(self) -> bool:
        """Check if proposal is approved"""
        return self.status == ProposalStatus.APPROVED
    
    @property
    def is_vetoed(self) -> bool:
        """Check if proposal is vetoed"""
        return self.status == ProposalStatus.VETOED
    
    @property
    def can_vote(self) -> bool:
        """Check if proposal is still open for voting"""
        return self.status == ProposalStatus.PENDING and not self.is_expired
    
    @property
    def veto_ratio(self) -> float:
        """Get veto ratio"""
        total = self.total_votes
        return self.veto_count / total if total > 0 else 0.0
    
    @property
    def approve_ratio(self) -> float:
        """Get approve ratio"""
        total = self.total_votes
        return self.approve_count / total if total > 0 else 0.0
    
    @property
    def time_remaining_ms(self) -> int:
        """Get time remaining for voting"""
        remaining = self.expires_at - datetime.utcnow()
        return max(0, int(remaining.total_seconds() * 1000))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "proposal_id": self.proposal_id,
            "proposer_id": self.proposer_id,
            "effect_type": self.effect_type,
            "effect_payload": self.effect_payload,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "status": self.status.value,
            "votes_required": self.votes_required,
            "veto_threshold": self.veto_threshold,
            "total_votes": self.total_votes,
            "veto_count": self.veto_count,
            "approve_count": self.approve_count,
            "abstain_count": self.abstain_count,
            "veto_ratio": self.veto_ratio,
            "approve_ratio": self.approve_ratio,
            "is_expired": self.is_expired,
            "is_approved": self.is_approved,
            "is_vetoed": self.is_vetoed,
            "can_vote": self.can_vote,
            "time_remaining_ms": self.time_remaining_ms,
            "description": self.description,
            "metadata": self.metadata
        }


@dataclass
class ProposalResponse:
    """Response to proposal creation"""
    proposal_id: str
    status: str
    votes_required: int
    veto_threshold: float
    expires_at: datetime
    message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "proposal_id": self.proposal_id,
            "status": self.status,
            "votes_required": self.votes_required,
            "veto_threshold": self.veto_threshold,
            "expires_at": self.expires_at.isoformat(),
            "message": self.message
        }


@dataclass
class VoteResult:
    """Result of voting on proposal"""
    success: bool
    result: str
    proposal_status: ProposalStatus
    vote_counts: Dict[str, int]
    message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "success": self.success,
            "result": self.result,
            "proposal_status": self.proposal_status.value,
            "vote_counts": self.vote_counts,
            "message": self.message
        }


class QuorumAuthority:
    """Quorum-based decision making for swarm operations"""
    
    def __init__(
        self,
        min_quorum: int = 3,
        veto_threshold: float = 0.3,
        proposal_timeout_ms: int = 30000,
        max_proposals: int = 1000
    ):
        self.min_quorum = min_quorum
        self.veto_threshold = veto_threshold
        self.proposal_timeout_ms = proposal_timeout_ms
        self.max_proposals = max_proposals
        
        # Proposal state
        self.active_proposals: Dict[str, Proposal] = {}
        self.proposal_history: List[Proposal] = []
        self.proposal_counter: int = 0
        
        # Voter management
        self.authorized_voters: Set[str] = set()
        self.voter_weights: Dict[str, float] = {}
        
        logger.info(f"QuorumAuthority initialized (quorum={min_quorum}, veto_threshold={veto_threshold})")
    
    def add_authorized_voter(self, voter_id: str, weight: float = 1.0) -> bool:
        """Add authorized voter"""
        self.authorized_voters.add(voter_id)
        self.voter_weights[voter_id] = weight
        logger.info(f"Added authorized voter: {voter_id} (weight: {weight})")
        return True
    
    def remove_authorized_voter(self, voter_id: str) -> bool:
        """Remove authorized voter"""
        self.authorized_voters.discard(voter_id)
        self.voter_weights.pop(voter_id, None)
        logger.info(f"Removed authorized voter: {voter_id}")
        return True
    
    def is_authorized_voter(self, voter_id: str) -> bool:
        """Check if voter is authorized"""
        return voter_id in self.authorized_voters
    
    async def propose_effect(
        self,
        proposer_id: str,
        effect_type: str,
        effect_payload: Dict[str, Any],
        description: str = "",
        votes_required: Optional[int] = None,
        veto_threshold: Optional[float] = None,
        timeout_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ProposalResponse:
        """Propose effect for quorum approval"""
        
        try:
            # Check if proposer is authorized
            if not self.is_authorized_voter(proposer_id):
                return ProposalResponse(
                    proposal_id="",
                    status="rejected",
                    votes_required=0,
                    veto_threshold=0.0,
                    expires_at=datetime.utcnow(),
                    message="Proposer not authorized to make proposals"
                )
            
            # Check proposal limit
            if len(self.active_proposals) >= self.max_proposals:
                return ProposalResponse(
                    proposal_id="",
                    status="rejected",
                    votes_required=0,
                    veto_threshold=0.0,
                    expires_at=datetime.utcnow(),
                    message="Too many active proposals"
                )
            
            # Create proposal
            proposal_id = f"prop_{int(time.time() * 1000)}_{self.proposal_counter}"
            self.proposal_counter += 1
            
            expires_at = datetime.utcnow() + timedelta(milliseconds=timeout_ms or self.proposal_timeout_ms)
            
            proposal = Proposal(
                proposal_id=proposal_id,
                proposer_id=proposer_id,
                effect_type=effect_type,
                effect_payload=effect_payload,
                created_at=datetime.utcnow(),
                expires_at=expires_at,
                votes_required=votes_required or self.min_quorum,
                veto_threshold=veto_threshold or self.veto_threshold,
                description=description,
                metadata=metadata or {}
            )
            
            self.active_proposals[proposal_id] = proposal
            
            logger.info(f"Created proposal: {proposal_id} by {proposer_id}")
            
            return ProposalResponse(
                proposal_id=proposal_id,
                status="pending",
                votes_required=proposal.votes_required,
                veto_threshold=proposal.veto_threshold,
                expires_at=expires_at,
                message="Proposal created successfully"
            )
            
        except Exception as e:
            logger.error(f"Proposal creation failed: {e}")
            return ProposalResponse(
                proposal_id="",
                status="error",
                votes_required=0,
                veto_threshold=0.0,
                expires_at=datetime.utcnow(),
                message=f"Internal error: {str(e)}"
            )
    
    async def vote_on_proposal(
        self,
        proposal_id: str,
        voter_id: str,
        vote_type: str,
        reason: str = ""
    ) -> VoteResult:
        """Vote on active proposal"""
        
        try:
            # Validate vote type
            try:
                vote_enum = VoteType(vote_type.lower())
            except ValueError:
                return VoteResult(
                    success=False,
                    result="invalid_vote",
                    proposal_status=ProposalStatus.PENDING,
                    vote_counts={},
                    message=f"Invalid vote type: {vote_type}"
                )
            
            # Check if voter is authorized
            if not self.is_authorized_voter(voter_id):
                return VoteResult(
                    success=False,
                    result="unauthorized",
                    proposal_status=ProposalStatus.PENDING,
                    vote_counts={},
                    message="Voter not authorized"
                )
            
            # Get proposal
            proposal = self.active_proposals.get(proposal_id)
            if not proposal:
                return VoteResult(
                    success=False,
                    result="not_found",
                    proposal_status=ProposalStatus.PENDING,
                    vote_counts={},
                    message="Proposal not found"
                )
            
            # Check if proposal is still open for voting
            if not proposal.can_vote:
                return VoteResult(
                    success=False,
                    result="not_open",
                    proposal_status=proposal.status,
                    vote_counts={
                        "approve": proposal.approve_count,
                        "veto": proposal.veto_count,
                        "abstain": proposal.abstain_count
                    },
                    message=f"Proposal not open for voting (status: {proposal.status.value})"
                )
            
            # Check if voter already voted
            if voter_id in proposal.votes:
                return VoteResult(
                    success=False,
                    result="already_voted",
                    proposal_status=proposal.status,
                    vote_counts={
                        "approve": proposal.approve_count,
                        "veto": proposal.veto_count,
                        "abstain": proposal.abstain_count
                    },
                    message="Voter has already voted on this proposal"
                )
            
            # Record vote
            vote = Vote(
                voter_id=voter_id,
                vote_type=vote_enum,
                reason=reason,
                timestamp=datetime.utcnow(),
                weight=self.voter_weights.get(voter_id, 1.0)
            )
            
            proposal.votes[voter_id] = vote
            
            # Update counts
            if vote_enum == VoteType.APPROVE:
                proposal.approve_count += 1
            elif vote_enum == VoteType.VETO:
                proposal.veto_count += 1
            elif vote_enum == VoteType.ABSTAIN:
                proposal.abstain_count += 1
            
            # Check for veto threshold
            if proposal.veto_ratio >= proposal.veto_threshold:
                proposal.status = ProposalStatus.VETOED
                self._move_to_history(proposal)
                
                logger.info(f"Proposal {proposal_id} vetoed (veto ratio: {proposal.veto_ratio:.2f})")
                
                return VoteResult(
                    success=True,
                    result="vetoed",
                    proposal_status=ProposalStatus.VETOED,
                    vote_counts={
                        "approve": proposal.approve_count,
                        "veto": proposal.veto_count,
                        "abstain": proposal.abstain_count
                    },
                    message=f"Proposal vetoed: {proposal.veto_count}/{proposal.total_votes} votes"
                )
            
            # Check for approval
            if proposal.approve_count >= proposal.votes_required:
                proposal.status = ProposalStatus.APPROVED
                self._move_to_history(proposal)
                
                logger.info(f"Proposal {proposal_id} approved ({proposal.approve_count}/{proposal.votes_required} votes)")
                
                return VoteResult(
                    success=True,
                    result="approved",
                    proposal_status=ProposalStatus.APPROVED,
                    vote_counts={
                        "approve": proposal.approve_count,
                        "veto": proposal.veto_count,
                        "abstain": proposal.abstain_count
                    },
                    message=f"Proposal approved: {proposal.approve_count}/{proposal.votes_required} votes"
                )
            
            # Vote recorded, but decision pending
            return VoteResult(
                success=True,
                result="recorded",
                proposal_status=ProposalStatus.PENDING,
                vote_counts={
                    "approve": proposal.approve_count,
                    "veto": proposal.veto_count,
                    "abstain": proposal.abstain_count
                },
                message="Vote recorded, awaiting more votes"
            )
            
        except Exception as e:
            logger.error(f"Voting failed: {e}")
            return VoteResult(
                success=False,
                result="error",
                proposal_status=ProposalStatus.PENDING,
                vote_counts={},
                message=f"Internal error: {str(e)}"
            )
    
    async def cancel_proposal(self, proposal_id: str, reason: str = "Cancelled by proposer") -> bool:
        """Cancel active proposal"""
        proposal = self.active_proposals.get(proposal_id)
        if not proposal:
            return False
        
        proposal.status = ProposalStatus.CANCELLED
        self._move_to_history(proposal)
        
        logger.info(f"Proposal cancelled: {proposal_id} - {reason}")
        return True
    
    def get_proposal(self, proposal_id: str) -> Optional[Proposal]:
        """Get proposal by ID"""
        return self.active_proposals.get(proposal_id)
    
    def get_proposal_history(self, limit: int = 100) -> List[Proposal]:
        """Get proposal history"""
        return self.proposal_history[-limit:]
    
    def get_active_proposals(self) -> List[Proposal]:
        """Get all active proposals"""
        return list(self.active_proposals.values())
    
    def get_proposals_by_voter(self, voter_id: str) -> List[Proposal]:
        """Get proposals that voter has voted on"""
        voted_proposals = []
        for proposal in list(self.active_proposals.values()) + self.proposal_history:
            if voter_id in proposal.votes:
                voted_proposals.append(proposal)
        return voted_proposals
    
    def cleanup_expired_proposals(self) -> int:
        """Clean up expired proposals"""
        expired_count = 0
        
        expired_proposals = []
        for proposal_id, proposal in self.active_proposals.items():
            if proposal.is_expired:
                expired_proposals.append(proposal_id)
        
        for proposal_id in expired_proposals:
            proposal = self.active_proposals[proposal_id]
            proposal.status = ProposalStatus.EXPIRED
            self._move_to_history(proposal)
            expired_count += 1
        
        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired proposals")
        
        return expired_count
    
    def _move_to_history(self, proposal: Proposal):
        """Move proposal to history"""
        # Remove from active
        if proposal.proposal_id in self.active_proposals:
            del self.active_proposals[proposal.proposal_id]
        
        # Add to history
        self.proposal_history.append(proposal)
        
        # Trim history if needed
        if len(self.proposal_history) > self.max_proposals:
            self.proposal_history = self.proposal_history[-self.max_proposals:]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get quorum statistics"""
        total_proposals = len(self.proposal_history) + len(self.active_proposals)
        
        status_counts = {}
        for status in ProposalStatus:
            status_counts[status.value] = 0
        
        # Count active proposals
        for proposal in self.active_proposals.values():
            status_counts[proposal.status.value] += 1
        
        # Count history proposals
        for proposal in self.proposal_history:
            status_counts[proposal.status.value] += 1
        
        # Calculate approval rate
        approved_proposals = [p for p in self.proposal_history if p.status == ProposalStatus.APPROVED]
        approval_rate = len(approved_proposals) / total_proposals if total_proposals > 0 else 0
        
        # Calculate veto rate
        vetoed_proposals = [p for p in self.proposal_history if p.status == ProposalStatus.VETOED]
        veto_rate = len(vetoed_proposals) / total_proposals if total_proposals > 0 else 0
        
        return {
            "total_proposals": total_proposals,
            "active_proposals": len(self.active_proposals),
            "authorized_voters": len(self.authorized_voters),
            "status_counts": status_counts,
            "approval_rate": approval_rate,
            "veto_rate": veto_rate,
            "min_quorum": self.min_quorum,
            "veto_threshold": self.veto_threshold,
            "proposal_timeout_ms": self.proposal_timeout_ms
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get authority status for monitoring"""
        return {
            "active_proposals": len(self.active_proposals),
            "proposal_history_size": len(self.proposal_history),
            "authorized_voters": list(self.authorized_voters),
            "statistics": self.get_statistics(),
            "last_cleanup": datetime.utcnow().isoformat()
        }


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

quorum_authority: QuorumAuthority = None


def get_quorum_authority() -> Optional[QuorumAuthority]:
    """Get the global quorum authority instance"""
    return quorum_authority


def initialize_quorum_authority(
    min_quorum: int = 3,
    veto_threshold: float = 0.3,
    proposal_timeout_ms: int = 30000
) -> QuorumAuthority:
    """Initialize the global quorum authority"""
    global quorum_authority
    quorum_authority = QuorumAuthority(
        min_quorum=min_quorum,
        veto_threshold=veto_threshold,
        proposal_timeout_ms=proposal_timeout_ms
    )
    return quorum_authority
