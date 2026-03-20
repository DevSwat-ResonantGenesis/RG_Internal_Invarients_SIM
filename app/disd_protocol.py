"""
DISD Protocol Implementation

Main DISD protocol coordinator that integrates message routing,
quorum authority, and irreversibility authority for swarm coordination.

STATUS: PRODUCTION IMPLEMENTATION
UPDATED: 2026-01-08
PURPOSE: DISD protocol coordination and swarm management
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
from .disd_router import DISDMessageRouter, get_disd_router
from .quorum_authority import QuorumAuthority, get_quorum_authority
from .irreversibility_authority import IrreversibilityAuthority, get_irreversibility_authority

logger = logging.getLogger(__name__)


@dataclass
class SwarmMember:
    """Swarm member information"""
    agent_id: str
    agent_type: str
    endpoint: str
    capabilities: List[str]
    status: str = "active"
    joined_at: datetime = None
    last_heartbeat: datetime = None
    load: float = 0.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.joined_at is None:
            self.joined_at = datetime.utcnow()
        if self.last_heartbeat is None:
            self.last_heartbeat = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}
    
    def is_active(self) -> bool:
        """Check if member is active"""
        return (self.status == "active" and 
                datetime.utcnow() - self.last_heartbeat < timedelta(seconds=30))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "endpoint": self.endpoint,
            "capabilities": self.capabilities,
            "status": self.status,
            "joined_at": self.joined_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "load": self.load,
            "is_active": self.is_active(),
            "metadata": self.metadata
        }


@dataclass
class SwarmStatus:
    """Swarm status information"""
    swarm_id: str
    member_count: int
    active_members: int
    total_messages: int
    pending_proposals: int
    last_activity: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "swarm_id": self.swarm_id,
            "member_count": self.member_count,
            "active_members": self.active_members,
            "total_messages": self.total_messages,
            "pending_proposals": self.pending_proposals,
            "last_activity": self.last_activity.isoformat()
        }


class DISDProtocol:
    """DISD protocol coordinator for swarm management"""
    
    def __init__(
        self,
        swarm_id: str = "default_swarm",
        router: Optional[DISDMessageRouter] = None,
        quorum_authority: Optional[QuorumAuthority] = None,
        irreversibility_authority: Optional[IrreversibilityAuthority] = None
    ):
        self.swarm_id = swarm_id
        
        # Components
        self.router = router or get_disd_router()
        self.quorum_authority = quorum_authority or get_quorum_authority()
        self.irreversibility_authority = irreversibility_authority or get_irreversibility_authority()
        
        # Swarm state
        self.members: Dict[str, SwarmMember] = {}
        self.proposals: Dict[str, DISDMessage] = {}  # proposal_id -> propose message
        self.votes: Dict[str, Dict[str, DISDMessage]] = {}  # proposal_id -> voter_id -> vote message
        
        # Configuration
        self.heartbeat_interval_ms: int = 10000
        self.member_timeout_ms: int = 30000
        self.proposal_timeout_ms: int = 300000  # 5 minutes
        self.enable_auto_cleanup: bool = True
        
        # Statistics
        self.total_messages: int = 0
        self.total_proposals: int = 0
        self.total_votes: int = 0
        self.total_commits: int = 0
        
        # Background tasks
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
        
        # Register message handlers
        self._register_message_handlers()
        
        logger.info(f"DISDProtocol initialized for swarm: {swarm_id}")
    
    def _register_message_handlers(self):
        """Register message handlers with router"""
        if self.router:
            # Control messages
            self.router.register_handler(DISDMessageType.JOIN, self._handle_join_message, priority=10)
            self.router.register_handler(DISDMessageType.LEAVE, self._handle_leave_message, priority=10)
            self.router.register_handler(DISDMessageType.HEARTBEAT, self._handle_heartbeat_message, priority=5)
            
            # Coordination messages
            self.router.register_handler(DISDMessageType.PROPOSE, self._handle_propose_message, priority=10)
            self.router.register_handler(DISDMessageType.VOTE, self._handle_vote_message, priority=10)
            self.router.register_handler(DISDMessageType.COMMIT, self._handle_commit_message, priority=10)
            self.router.register_handler(DISDMessageType.ABORT, self._handle_abort_message, priority=10)
    
    async def start(self):
        """Start DISD protocol background tasks"""
        if self.heartbeat_task is None:
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info(f"DISDProtocol started for swarm: {self.swarm_id}")
    
    async def stop(self):
        """Stop DISD protocol background tasks"""
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            self.heartbeat_task = None
        
        if self.cleanup_task:
            self.cleanup_task.cancel()
            self.cleanup_task = None
        
        logger.info(f"DISDProtocol stopped for swarm: {self.swarm_id}")
    
    async def join_swarm(
        self,
        agent_id: str,
        agent_type: str = "general",
        capabilities: List[str] = None,
        endpoint: str = "",
        metadata: Dict[str, Any] = None
    ) -> bool:
        """Join swarm"""
        try:
            # Create join message
            join_message = DISDMessageFactory.create_join_message(
                sender_id=agent_id,
                agent_id=agent_id,
                agent_type=agent_type,
                capabilities=capabilities or [],
                endpoint=endpoint,
                metadata=metadata or {}
            )
            
            # Route to all members
            result = await self.router.broadcast_message(join_message)
            
            if result.success:
                # Add to local members
                member = SwarmMember(
                    agent_id=agent_id,
                    agent_type=agent_type,
                    endpoint=endpoint,
                    capabilities=capabilities or [],
                    metadata=metadata or {}
                )
                self.members[agent_id] = member
                
                # Register with router
                if endpoint and self.router:
                    self.router.register_agent(agent_id, endpoint)
                
                logger.info(f"Agent {agent_id} joined swarm {self.swarm_id}")
                return True
            else:
                logger.error(f"Failed to join swarm: {result.message}")
                return False
                
        except Exception as e:
            logger.error(f"Join swarm error: {e}")
            return False
    
    async def leave_swarm(self, agent_id: str, reason: str = "", graceful: bool = True) -> bool:
        """Leave swarm"""
        try:
            # Create leave message
            leave_message = DISDMessageFactory.create_leave_message(
                sender_id=agent_id,
                agent_id=agent_id,
                reason=reason,
                graceful=graceful
            )
            
            # Route to all members
            result = await self.router.broadcast_message(leave_message)
            
            # Remove from local members
            if agent_id in self.members:
                del self.members[agent_id]
                
                # Unregister from router
                if self.router:
                    self.router.unregister_agent(agent_id)
                
                logger.info(f"Agent {agent_id} left swarm {self.swarm_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Leave swarm error: {e}")
            return False
    
    async def propose_action(
        self,
        sender_id: str,
        action_type: str,
        action_payload: Dict[str, Any],
        quorum_required: int = 3,
        veto_threshold: float = 0.3,
        description: str = ""
    ) -> Optional[str]:
        """Propose action to swarm"""
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
            
            # Store proposal
            proposal_id = propose_message.payload.proposal_id
            self.proposals[proposal_id] = propose_message
            self.votes[proposal_id] = {}
            
            # Route to all members
            result = await self.router.broadcast_message(propose_message)
            
            if result.success:
                self.total_proposals += 1
                logger.info(f"Proposal {proposal_id} created by {sender_id}")
                return proposal_id
            else:
                # Clean up failed proposal
                del self.proposals[proposal_id]
                del self.votes[proposal_id]
                logger.error(f"Failed to create proposal: {result.message}")
                return None
                
        except Exception as e:
            logger.error(f"Propose action error: {e}")
            return None
    
    async def vote_on_proposal(
        self,
        sender_id: str,
        proposal_id: str,
        vote_type: VoteType,
        reason: str = "",
        weight: float = 1.0
    ) -> bool:
        """Vote on proposal"""
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
            
            # Store vote
            self.votes[proposal_id][sender_id] = vote_message
            
            # Route to all members
            result = await self.router.broadcast_message(vote_message)
            
            if result.success:
                self.total_votes += 1
                logger.info(f"Vote cast by {sender_id} on proposal {proposal_id}: {vote_type.value}")
                
                # Check if proposal is ready to commit
                await self._check_proposal_completion(proposal_id)
                
                return True
            else:
                # Clean up failed vote
                del self.votes[proposal_id][sender_id]
                logger.error(f"Failed to cast vote: {result.message}")
                return False
                
        except Exception as e:
            logger.error(f"Vote on proposal error: {e}")
            return False
    
    async def _check_proposal_completion(self, proposal_id: str):
        """Check if proposal is ready to commit"""
        try:
            proposal = self.proposals.get(proposal_id)
            if not proposal:
                return
            
            votes = self.votes.get(proposal_id, {})
            payload = proposal.payload
            
            # Count votes
            approve_count = sum(1 for vote in votes.values() if vote.payload.vote_type == VoteType.APPROVE)
            veto_count = sum(1 for vote in votes.values() if vote.payload.vote_type == VoteType.VETO)
            total_votes = len(votes)
            
            # Check veto threshold
            if total_votes > 0 and veto_count / total_votes >= payload.veto_threshold:
                await self._abort_proposal(proposal_id, f"Veto threshold reached: {veto_count}/{total_votes}")
                return
            
            # Check quorum
            if approve_count >= payload.quorum_required:
                await self._commit_proposal(proposal_id)
                return
            
            # Check expiration
            if payload.is_expired():
                await self._abort_proposal(proposal_id, "Proposal expired")
                return
                
        except Exception as e:
            logger.error(f"Check proposal completion error: {e}")
    
    async def _commit_proposal(self, proposal_id: str):
        """Commit proposal"""
        try:
            proposal = self.proposals.get(proposal_id)
            if not proposal:
                return
            
            votes = self.votes.get(proposal_id, {})
            payload = proposal.payload
            
            # Get authorization from irreversibility authority
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
            
            # Create commit message
            commit_message = DISDMessageFactory.create_commit_message(
                sender_id=self.swarm_id,  # Swarm commits on behalf of members
                proposal_id=proposal_id,
                decision="approved",
                votes={voter_id: vote.payload.to_dict() for voter_id, vote in votes.items()},
                auth_token=auth_token
            )
            
            # Execute effect through irreversibility authority
            if self.irreversibility_authority and auth_token:
                async def effect_executor():
                    return {"proposal_id": proposal_id, "executed": True}
                
                result = await self.irreversibility_authority.execute_with_authorization(
                    auth_token, effect_executor
                )
                
                if not result.success:
                    await self._abort_proposal(proposal_id, f"Effect execution failed: {result.reason}")
                    return
            
            # Broadcast commit
            result = await self.router.broadcast_message(commit_message)
            
            if result.success:
                self.total_commits += 1
                logger.info(f"Proposal {proposal_id} committed")
                
                # Clean up
                await self._cleanup_proposal(proposal_id)
            else:
                logger.error(f"Failed to broadcast commit: {result.message}")
                
        except Exception as e:
            logger.error(f"Commit proposal error: {e}")
    
    async def _abort_proposal(self, proposal_id: str, reason: str):
        """Abort proposal"""
        try:
            proposal = self.proposals.get(proposal_id)
            if not proposal:
                return
            
            # Create abort message
            abort_message = DISDMessage(
                header=DISDMessageHeader(
                    message_type=DISDMessageType.ABORT,
                    sender_id=self.swarm_id
                ),
                payload=type('AbortPayload', (), {
                    'proposal_id': proposal_id,
                    'reason': reason,
                    'to_dict': lambda: {'proposal_id': proposal_id, 'reason': reason}
                })()
            )
            
            # Broadcast abort
            await self.router.broadcast_message(abort_message)
            
            logger.info(f"Proposal {proposal_id} aborted: {reason}")
            
            # Clean up
            await self._cleanup_proposal(proposal_id)
            
        except Exception as e:
            logger.error(f"Abort proposal error: {e}")
    
    async def _cleanup_proposal(self, proposal_id: str):
        """Clean up proposal data"""
        if proposal_id in self.proposals:
            del self.proposals[proposal_id]
        if proposal_id in self.votes:
            del self.votes[proposal_id]
    
    # Message handlers
    async def _handle_join_message(self, message: DISDMessage) -> None:
        """Handle join message"""
        try:
            payload = message.payload
            if not hasattr(payload, 'agent_id'):
                return
            
            agent_id = payload.agent_id
            
            # Add member if not exists
            if agent_id not in self.members:
                member = SwarmMember(
                    agent_id=agent_id,
                    agent_type=getattr(payload, 'agent_type', 'general'),
                    endpoint=getattr(payload, 'endpoint', ''),
                    capabilities=getattr(payload, 'capabilities', []),
                    metadata=getattr(payload, 'metadata', {})
                )
                self.members[agent_id] = member
                
                # Register with router
                if member.endpoint and self.router:
                    self.router.register_agent(agent_id, member.endpoint)
                
                logger.info(f"Agent {agent_id} joined via message")
                
        except Exception as e:
            logger.error(f"Handle join message error: {e}")
    
    async def _handle_leave_message(self, message: DISDMessage) -> None:
        """Handle leave message"""
        try:
            payload = message.payload
            if not hasattr(payload, 'agent_id'):
                return
            
            agent_id = payload.agent_id
            
            # Remove member
            if agent_id in self.members:
                del self.members[agent_id]
                
                # Unregister from router
                if self.router:
                    self.router.unregister_agent(agent_id)
                
                logger.info(f"Agent {agent_id} left via message")
                
        except Exception as e:
            logger.error(f"Handle leave message error: {e}")
    
    async def _handle_heartbeat_message(self, message: DISDMessage) -> None:
        """Handle heartbeat message"""
        try:
            payload = message.payload
            if not hasattr(payload, 'agent_id'):
                return
            
            agent_id = payload.agent_id
            
            # Update member heartbeat
            if agent_id in self.members:
                member = self.members[agent_id]
                member.last_heartbeat = datetime.utcnow()
                member.status = getattr(payload, 'status', 'active')
                member.load = getattr(payload, 'load', 0.0)
                
        except Exception as e:
            logger.error(f"Handle heartbeat message error: {e}")
    
    async def _handle_propose_message(self, message: DISDMessage) -> None:
        """Handle propose message"""
        try:
            payload = message.payload
            if not hasattr(payload, 'proposal_id'):
                return
            
            proposal_id = payload.proposal_id
            
            # Store proposal if not exists
            if proposal_id not in self.proposals:
                self.proposals[proposal_id] = message
                self.votes[proposal_id] = {}
                
        except Exception as e:
            logger.error(f"Handle propose message error: {e}")
    
    async def _handle_vote_message(self, message: DISDMessage) -> None:
        """Handle vote message"""
        try:
            payload = message.payload
            if not hasattr(payload, 'proposal_id'):
                return
            
            proposal_id = payload.proposal_id
            voter_id = message.sender_id
            
            # Store vote
            if proposal_id in self.votes:
                self.votes[proposal_id][voter_id] = message
                
                # Check completion
                await self._check_proposal_completion(proposal_id)
                
        except Exception as e:
            logger.error(f"Handle vote message error: {e}")
    
    async def _handle_commit_message(self, message: DISDMessage) -> None:
        """Handle commit message"""
        try:
            payload = message.payload
            if hasattr(payload, 'proposal_id'):
                proposal_id = payload.proposal_id
                await self._cleanup_proposal(proposal_id)
                
        except Exception as e:
            logger.error(f"Handle commit message error: {e}")
    
    async def _handle_abort_message(self, message: DISDMessage) -> None:
        """Handle abort message"""
        try:
            payload = message.payload
            if hasattr(payload, 'proposal_id'):
                proposal_id = payload.proposal_id
                await self._cleanup_proposal(proposal_id)
                
        except Exception as e:
            logger.error(f"Handle abort message error: {e}")
    
    # Background tasks
    async def _heartbeat_loop(self):
        """Background heartbeat loop"""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval_ms / 1000)
                
                # Send heartbeats for all local agents
                for member in self.members.values():
                    if member.endpoint:  # Only send for local agents
                        heartbeat_message = DISDMessageFactory.create_heartbeat_message(
                            sender_id=member.agent_id,
                            agent_id=member.agent_id,
                            status=member.status,
                            load=member.load,
                            capabilities=member.capabilities
                        )
                        
                        await self.router.broadcast_message(heartbeat_message)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
    
    async def _cleanup_loop(self):
        """Background cleanup loop"""
        while True:
            try:
                await asyncio.sleep(60000)  # 1 minute
                
                if self.enable_auto_cleanup:
                    # Clean up inactive members
                    inactive_members = []
                    for agent_id, member in self.members.items():
                        if not member.is_active():
                            inactive_members.append(agent_id)
                    
                    for agent_id in inactive_members:
                        await self.leave_swarm(agent_id, "inactive timeout")
                    
                    # Clean up expired proposals
                    expired_proposals = []
                    for proposal_id, proposal in self.proposals.items():
                        if proposal.payload.is_expired():
                            expired_proposals.append(proposal_id)
                    
                    for proposal_id in expired_proposals:
                        await self._abort_proposal(proposal_id, "expired")
                    
                    # Clean up router
                    if self.router:
                        self.router.cleanup_expired_messages()
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
    
    def get_swarm_status(self) -> SwarmStatus:
        """Get swarm status"""
        active_members = sum(1 for member in self.members.values() if member.is_active())
        
        return SwarmStatus(
            swarm_id=self.swarm_id,
            member_count=len(self.members),
            active_members=active_members,
            total_messages=self.total_messages,
            pending_proposals=len(self.proposals),
            last_activity=datetime.utcnow()
        )
    
    def get_members(self) -> List[SwarmMember]:
        """Get all swarm members"""
        return list(self.members.values())
    
    def get_proposals(self) -> Dict[str, Dict[str, Any]]:
        """Get all proposals with votes"""
        proposals_data = {}
        
        for proposal_id, proposal in self.proposals.items():
            votes_data = {}
            for voter_id, vote in self.votes.get(proposal_id, {}).items():
                votes_data[voter_id] = vote.payload.to_dict()
            
            proposals_data[proposal_id] = {
                "proposal": proposal.payload.to_dict(),
                "votes": votes_data,
                "vote_count": len(votes_data),
                "created_at": proposal.header.timestamp.isoformat()
            }
        
        return proposals_data
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get protocol statistics"""
        return {
            "swarm_id": self.swarm_id,
            "total_messages": self.total_messages,
            "total_proposals": self.total_proposals,
            "total_votes": self.total_votes,
            "total_commits": self.total_commits,
            "member_count": len(self.members),
            "active_members": sum(1 for member in self.members.values() if member.is_active()),
            "pending_proposals": len(self.proposals),
            "configuration": {
                "heartbeat_interval_ms": self.heartbeat_interval_ms,
                "member_timeout_ms": self.member_timeout_ms,
                "proposal_timeout_ms": self.proposal_timeout_ms,
                "enable_auto_cleanup": self.enable_auto_cleanup
            }
        }


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

disd_protocol: DISDProtocol = None


def get_disd_protocol() -> Optional[DISDProtocol]:
    """Get the global DISD protocol instance"""
    return disd_protocol


def initialize_disd_protocol(
    swarm_id: str = "default_swarm",
    router: Optional[DISDMessageRouter] = None,
    quorum_authority: Optional[QuorumAuthority] = None,
    irreversibility_authority: Optional[IrreversibilityAuthority] = None
) -> DISDProtocol:
    """Initialize the global DISD protocol"""
    global disd_protocol
    disd_protocol = DISDProtocol(
        swarm_id=swarm_id,
        router=router,
        quorum_authority=quorum_authority,
        irreversibility_authority=irreversibility_authority
    )
    return disd_protocol
