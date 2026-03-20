"""
RARA Agent Coordinator - Multi-agent coordination with role separation
"""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from .models import (
    AgentRole, AgentRegistration, MutationProposal,
    MutationRequest, CapabilityType
)
import logging

logger = logging.getLogger(__name__)


class AgentCoordinator:
    """
    Coordinates multiple agents with strict role separation.
    
    Roles:
    - Planner: Propose mutations
    - Executor: Execute approved mutations
    - Verifier: Run probes & invariants
    - Auditor: Log & score behavior
    
    No agent can:
    - Propose and execute
    - Execute and verify
    - Verify and approve
    """
    
    def __init__(self):
        self.agents: Dict[str, AgentRegistration] = {}
        self.proposals: Dict[str, MutationProposal] = {}
        self.proposal_queue: asyncio.Queue = asyncio.Queue()
        self.execution_lock = asyncio.Lock()
    
    def register_agent(
        self,
        agent_id: str,
        role: AgentRole,
        dsid: str,
        public_key: str,
        capabilities: List[CapabilityType] = None
    ) -> AgentRegistration:
        """Register an agent with a specific role"""
        
        # Validate role-capability alignment
        allowed_caps = self._get_allowed_capabilities(role)
        if capabilities:
            invalid = [c for c in capabilities if c not in allowed_caps]
            if invalid:
                raise ValueError(f"Capabilities {invalid} not allowed for role {role}")
        
        registration = AgentRegistration(
            agent_id=agent_id,
            role=role,
            dsid=dsid,
            public_key=public_key,
            capabilities=capabilities or allowed_caps
        )
        
        self.agents[agent_id] = registration
        logger.info(f"Registered agent {agent_id} as {role.value}")
        
        return registration
    
    def _get_allowed_capabilities(self, role: AgentRole) -> List[CapabilityType]:
        """Get capabilities allowed for a role"""
        if role == AgentRole.PLANNER:
            # Planners can only propose, not execute
            return []
        
        elif role == AgentRole.EXECUTOR:
            # Executors can perform all mutations
            return list(CapabilityType)
        
        elif role == AgentRole.VERIFIER:
            # Verifiers can only read
            return []
        
        elif role == AgentRole.AUDITOR:
            # Auditors can only observe
            return []
        
        return []
    
    def get_agent(self, agent_id: str) -> Optional[AgentRegistration]:
        """Get agent registration"""
        return self.agents.get(agent_id)
    
    def get_agents_by_role(self, role: AgentRole) -> List[AgentRegistration]:
        """Get all agents with a specific role"""
        return [a for a in self.agents.values() if a.role == role]
    
    async def submit_proposal(
        self,
        planner_id: str,
        mutation: MutationRequest,
        risk_score: float = 0.0,
        alternatives_considered: int = 0
    ) -> MutationProposal:
        """
        Submit a mutation proposal from a planner.
        
        Only planners can submit proposals.
        """
        agent = self.agents.get(planner_id)
        if not agent:
            raise ValueError(f"Agent {planner_id} not registered")
        
        if agent.role != AgentRole.PLANNER:
            raise ValueError(f"Agent {planner_id} is not a planner (role={agent.role})")
        
        proposal = MutationProposal(
            planner_id=planner_id,
            mutation=mutation,
            risk_score=risk_score,
            alternatives_considered=alternatives_considered
        )
        
        self.proposals[proposal.proposal_id] = proposal
        await self.proposal_queue.put(proposal.proposal_id)
        
        logger.info(f"Proposal {proposal.proposal_id} submitted by {planner_id}")
        
        return proposal
    
    async def verify_proposal(
        self,
        verifier_id: str,
        proposal_id: str,
        approved: bool,
        reason: str = ""
    ) -> MutationProposal:
        """
        Verify a proposal.
        
        Only verifiers can verify proposals.
        """
        agent = self.agents.get(verifier_id)
        if not agent:
            raise ValueError(f"Agent {verifier_id} not registered")
        
        if agent.role != AgentRole.VERIFIER:
            raise ValueError(f"Agent {verifier_id} is not a verifier (role={agent.role})")
        
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        # Verifier cannot be the same as planner
        if verifier_id == proposal.planner_id:
            raise ValueError("Verifier cannot be the same as planner")
        
        proposal.verification_status = "approved" if approved else "rejected"
        proposal.verifier_id = verifier_id
        
        logger.info(
            f"Proposal {proposal_id} {'approved' if approved else 'rejected'} "
            f"by verifier {verifier_id}: {reason}"
        )
        
        return proposal
    
    async def execute_proposal(
        self,
        executor_id: str,
        proposal_id: str,
        executor_func
    ) -> Dict:
        """
        Execute an approved proposal.
        
        Only executors can execute proposals.
        Proposal must be verified first.
        """
        agent = self.agents.get(executor_id)
        if not agent:
            raise ValueError(f"Agent {executor_id} not registered")
        
        if agent.role != AgentRole.EXECUTOR:
            raise ValueError(f"Agent {executor_id} is not an executor (role={agent.role})")
        
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        if proposal.verification_status != "approved":
            raise ValueError(f"Proposal {proposal_id} not approved (status={proposal.verification_status})")
        
        # Executor cannot be planner or verifier
        if executor_id in [proposal.planner_id, proposal.verifier_id]:
            raise ValueError("Executor cannot be planner or verifier")
        
        # Only one execution at a time
        async with self.execution_lock:
            proposal.executor_id = executor_id
            
            logger.info(f"Executing proposal {proposal_id} by {executor_id}")
            
            # Execute via provided function
            result = await executor_func(executor_id, proposal.mutation)
            
            return {
                "proposal_id": proposal_id,
                "executor_id": executor_id,
                "result": result
            }
    
    async def audit_action(
        self,
        auditor_id: str,
        proposal_id: str,
        score: float,
        notes: str = ""
    ) -> Dict:
        """
        Audit a completed action.
        
        Only auditors can audit.
        """
        agent = self.agents.get(auditor_id)
        if not agent:
            raise ValueError(f"Agent {auditor_id} not registered")
        
        if agent.role != AgentRole.AUDITOR:
            raise ValueError(f"Agent {auditor_id} is not an auditor (role={agent.role})")
        
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        audit_entry = {
            "proposal_id": proposal_id,
            "auditor_id": auditor_id,
            "score": score,
            "notes": notes,
            "timestamp": datetime.utcnow().isoformat(),
            "planner": proposal.planner_id,
            "verifier": proposal.verifier_id,
            "executor": proposal.executor_id
        }
        
        logger.info(f"Audit for {proposal_id}: score={score}")
        
        return audit_entry
    
    async def get_next_proposal(self, timeout: float = 5.0) -> Optional[str]:
        """Get next proposal from queue"""
        try:
            proposal_id = await asyncio.wait_for(
                self.proposal_queue.get(),
                timeout=timeout
            )
            return proposal_id
        except asyncio.TimeoutError:
            return None
    
    def get_pending_proposals(self) -> List[MutationProposal]:
        """Get all pending proposals"""
        return [
            p for p in self.proposals.values()
            if p.verification_status == "pending"
        ]
    
    def get_approved_proposals(self) -> List[MutationProposal]:
        """Get all approved but not executed proposals"""
        return [
            p for p in self.proposals.values()
            if p.verification_status == "approved" and not p.executor_id
        ]
    
    def get_stats(self) -> Dict:
        """Get coordinator statistics"""
        return {
            "total_agents": len(self.agents),
            "agents_by_role": {
                role.value: len(self.get_agents_by_role(role))
                for role in AgentRole
            },
            "total_proposals": len(self.proposals),
            "pending_proposals": len(self.get_pending_proposals()),
            "approved_proposals": len(self.get_approved_proposals()),
            "queue_size": self.proposal_queue.qsize()
        }
