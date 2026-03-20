"""
DISD Message Types and Serialization

Defines the DISD wire protocol message formats, serialization,
and core message types for swarm coordination.

STATUS: PRODUCTION IMPLEMENTATION
UPDATED: 2026-01-08
PURPOSE: DISD wire protocol message handling
"""

import json
import uuid
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class DISDMessageType(str, Enum):
    """DISD message types"""
    # Control messages
    JOIN = "DISD_JOIN"
    LEAVE = "DISD_LEAVE"
    HEARTBEAT = "DISD_HEARTBEAT"
    DISCOVER = "DISD_DISCOVER"
    
    # Coordination messages
    PROPOSE = "DISD_PROPOSE"
    VOTE = "DISD_VOTE"
    COMMIT = "DISD_COMMIT"
    ABORT = "DISD_ABORT"
    
    # State messages
    SYNC = "DISD_SYNC"
    SNAPSHOT = "DISD_SNAPSHOT"
    RESTORE = "DISD_RESTORE"
    
    # Receipt messages
    RECEIPT = "DISD_RECEIPT"
    ERROR = "DISD_ERROR"


class ReceiptStatus(str, Enum):
    """Receipt status types"""
    ACKNOWLEDGED = "acknowledged"
    REJECTED = "rejected"
    PROCESSED = "processed"
    FAILED = "failed"


class VoteType(str, Enum):
    """Vote types for proposals"""
    APPROVE = "approve"
    VETO = "veto"
    ABSTAIN = "abstain"


@dataclass
class DISDMessageHeader:
    """DISD message header"""
    version: str = "1.0"
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    message_type: DISDMessageType = DISDMessageType.HEARTBEAT
    sender_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    epoch_id: Optional[str] = None
    sequence: int = 0
    ttl_ms: int = 5000
    priority: int = 0  # 0 = highest priority
    
    def is_expired(self) -> bool:
        """Check if message has expired"""
        expiry_time = self.timestamp + timedelta(milliseconds=self.ttl_ms)
        return datetime.utcnow() > expiry_time
    
    def time_remaining_ms(self) -> int:
        """Get time remaining in milliseconds"""
        expiry_time = self.timestamp + timedelta(milliseconds=self.ttl_ms)
        remaining = expiry_time - datetime.utcnow()
        return max(0, int(remaining.total_seconds() * 1000))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert header to dictionary"""
        return {
            "version": self.version,
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "sender_id": self.sender_id,
            "timestamp": self.timestamp.isoformat(),
            "epoch_id": self.epoch_id,
            "sequence": self.sequence,
            "ttl_ms": self.ttl_ms,
            "priority": self.priority
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DISDMessageHeader":
        """Create header from dictionary"""
        return cls(
            version=data.get("version", "1.0"),
            message_id=data.get("message_id", str(uuid.uuid4())),
            message_type=DISDMessageType(data.get("message_type", "DISD_HEARTBEAT")),
            sender_id=data.get("sender_id", ""),
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat())),
            epoch_id=data.get("epoch_id"),
            sequence=data.get("sequence", 0),
            ttl_ms=data.get("ttl_ms", 5000),
            priority=data.get("priority", 0)
        )


@dataclass
class DISDMessagePayload:
    """DISD message payload base class"""
    payload_type: str = "base"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert payload to dictionary"""
        return {"payload_type": self.payload_type}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DISDMessagePayload":
        """Create payload from dictionary"""
        return cls()


@dataclass
class JoinPayload(DISDMessagePayload):
    """Join swarm payload"""
    agent_id: str = ""
    agent_type: str = "general"
    capabilities: List[str] = field(default_factory=list)
    endpoint: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        self.payload_type = "join"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "payload_type": self.payload_type,
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "capabilities": self.capabilities,
            "endpoint": self.endpoint,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JoinPayload":
        return cls(
            agent_id=data.get("agent_id", ""),
            agent_type=data.get("agent_type", "general"),
            capabilities=data.get("capabilities", []),
            endpoint=data.get("endpoint", ""),
            metadata=data.get("metadata", {})
        )


@dataclass
class LeavePayload(DISDMessagePayload):
    """Leave swarm payload"""
    agent_id: str = ""
    reason: str = ""
    graceful: bool = True
    
    def __post_init__(self):
        self.payload_type = "leave"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "payload_type": self.payload_type,
            "agent_id": self.agent_id,
            "reason": self.reason,
            "graceful": self.graceful
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LeavePayload":
        return cls(
            agent_id=data.get("agent_id", ""),
            reason=data.get("reason", ""),
            graceful=data.get("graceful", True)
        )


@dataclass
class HeartbeatPayload(DISDMessagePayload):
    """Heartbeat payload"""
    agent_id: str = ""
    status: str = "active"
    load: float = 0.0
    capabilities: List[str] = field(default_factory=list)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        self.payload_type = "heartbeat"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "payload_type": self.payload_type,
            "agent_id": self.agent_id,
            "status": self.status,
            "load": self.load,
            "capabilities": self.capabilities,
            "last_seen": self.last_seen.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HeartbeatPayload":
        return cls(
            agent_id=data.get("agent_id", ""),
            status=data.get("status", "active"),
            load=data.get("load", 0.0),
            capabilities=data.get("capabilities", []),
            last_seen=datetime.fromisoformat(data.get("last_seen", datetime.utcnow().isoformat()))
        )


@dataclass
class ProposePayload(DISDMessagePayload):
    """Proposal payload"""
    proposal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action_type: str = ""
    action_payload: Dict[str, Any] = field(default_factory=dict)
    quorum_required: int = 3
    veto_threshold: float = 0.3
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(minutes=5))
    description: str = ""
    
    def __post_init__(self):
        self.payload_type = "propose"
    
    def is_expired(self) -> bool:
        """Check if proposal has expired"""
        return datetime.utcnow() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "payload_type": self.payload_type,
            "proposal_id": self.proposal_id,
            "action_type": self.action_type,
            "action_payload": self.action_payload,
            "quorum_required": self.quorum_required,
            "veto_threshold": self.veto_threshold,
            "expires_at": self.expires_at.isoformat(),
            "description": self.description
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProposePayload":
        return cls(
            proposal_id=data.get("proposal_id", str(uuid.uuid4())),
            action_type=data.get("action_type", ""),
            action_payload=data.get("action_payload", {}),
            quorum_required=data.get("quorum_required", 3),
            veto_threshold=data.get("veto_threshold", 0.3),
            expires_at=datetime.fromisoformat(data.get("expires_at", (datetime.utcnow() + timedelta(minutes=5)).isoformat())),
            description=data.get("description", "")
        )


@dataclass
class VotePayload(DISDMessagePayload):
    """Vote payload"""
    proposal_id: str = ""
    vote_type: VoteType = VoteType.ABSTAIN
    reason: str = ""
    weight: float = 1.0
    
    def __post_init__(self):
        self.payload_type = "vote"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "payload_type": self.payload_type,
            "proposal_id": self.proposal_id,
            "vote_type": self.vote_type.value,
            "reason": self.reason,
            "weight": self.weight
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VotePayload":
        return cls(
            proposal_id=data.get("proposal_id", ""),
            vote_type=VoteType(data.get("vote_type", "abstain")),
            reason=data.get("reason", ""),
            weight=data.get("weight", 1.0)
        )


@dataclass
class CommitPayload(DISDMessagePayload):
    """Commit payload"""
    proposal_id: str = ""
    decision: str = "approved"
    votes: Dict[str, Any] = field(default_factory=dict)
    auth_token: Optional[str] = None
    
    def __post_init__(self):
        self.payload_type = "commit"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "payload_type": self.payload_type,
            "proposal_id": self.proposal_id,
            "decision": self.decision,
            "votes": self.votes,
            "auth_token": self.auth_token
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommitPayload":
        return cls(
            proposal_id=data.get("proposal_id", ""),
            decision=data.get("decision", "approved"),
            votes=data.get("votes", {}),
            auth_token=data.get("auth_token")
        )


@dataclass
class ReceiptPayload(DISDMessagePayload):
    """Receipt payload"""
    original_message_id: str = ""
    receiver_id: str = ""
    status: ReceiptStatus = ReceiptStatus.ACKNOWLEDGED
    processing_time_ms: int = 0
    error_message: str = ""
    
    def __post_init__(self):
        self.payload_type = "receipt"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "payload_type": self.payload_type,
            "original_message_id": self.original_message_id,
            "receiver_id": self.receiver_id,
            "status": self.status.value,
            "processing_time_ms": self.processing_time_ms,
            "error_message": self.error_message
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReceiptPayload":
        return cls(
            original_message_id=data.get("original_message_id", ""),
            receiver_id=data.get("receiver_id", ""),
            status=ReceiptStatus(data.get("status", "acknowledged")),
            processing_time_ms=data.get("processing_time_ms", 0),
            error_message=data.get("error_message", "")
        )


@dataclass
class DISDMessage:
    """Complete DISD message"""
    header: DISDMessageHeader
    payload: DISDMessagePayload
    signature: Optional[str] = None
    
    def __post_init__(self):
        # Set message type in header based on payload
        if isinstance(self.payload, JoinPayload):
            self.header.message_type = DISDMessageType.JOIN
        elif isinstance(self.payload, LeavePayload):
            self.header.message_type = DISDMessageType.LEAVE
        elif isinstance(self.payload, HeartbeatPayload):
            self.header.message_type = DISDMessageType.HEARTBEAT
        elif isinstance(self.payload, ProposePayload):
            self.header.message_type = DISDMessageType.PROPOSE
        elif isinstance(self.payload, VotePayload):
            self.header.message_type = DISDMessageType.VOTE
        elif isinstance(self.payload, CommitPayload):
            self.header.message_type = DISDMessageType.COMMIT
        elif isinstance(self.payload, ReceiptPayload):
            self.header.message_type = DISDMessageType.RECEIPT
    
    @property
    def message_id(self) -> str:
        """Get message ID"""
        return self.header.message_id
    
    @property
    def message_type(self) -> DISDMessageType:
        """Get message type"""
        return self.header.message_type
    
    @property
    def sender_id(self) -> str:
        """Get sender ID"""
        return self.header.sender_id
    
    @property
    def is_expired(self) -> bool:
        """Check if message is expired"""
        return self.header.is_expired()
    
    @property
    def time_remaining_ms(self) -> int:
        """Get time remaining"""
        return self.header.time_remaining_ms()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return {
            "header": self.header.to_dict(),
            "payload": self.payload.to_dict(),
            "signature": self.signature
        }
    
    def to_json(self) -> str:
        """Convert message to JSON string"""
        return json.dumps(self.to_dict(), default=str)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DISDMessage":
        """Create message from dictionary"""
        header_data = data.get("header", {})
        payload_data = data.get("payload", {})
        
        header = DISDMessageHeader.from_dict(header_data)
        
        # Create payload based on type
        payload_type = payload_data.get("payload_type", "base")
        if payload_type == "join":
            payload = JoinPayload.from_dict(payload_data)
        elif payload_type == "leave":
            payload = LeavePayload.from_dict(payload_data)
        elif payload_type == "heartbeat":
            payload = HeartbeatPayload.from_dict(payload_data)
        elif payload_type == "propose":
            payload = ProposePayload.from_dict(payload_data)
        elif payload_type == "vote":
            payload = VotePayload.from_dict(payload_data)
        elif payload_type == "commit":
            payload = CommitPayload.from_dict(payload_data)
        elif payload_type == "receipt":
            payload = ReceiptPayload.from_dict(payload_data)
        else:
            payload = DISDMessagePayload.from_dict(payload_data)
        
        return cls(
            header=header,
            payload=payload,
            signature=data.get("signature")
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "DISDMessage":
        """Create message from JSON string"""
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def create_receipt(self, receiver_id: str, status: ReceiptStatus, processing_time_ms: int = 0, error_message: str = "") -> "DISDMessage":
        """Create receipt for this message"""
        receipt_payload = ReceiptPayload(
            original_message_id=self.message_id,
            receiver_id=receiver_id,
            status=status,
            processing_time_ms=processing_time_ms,
            error_message=error_message
        )
        
        receipt_header = DISDMessageHeader(
            message_type=DISDMessageType.RECEIPT,
            sender_id=receiver_id,
            timestamp=datetime.utcnow()
        )
        
        return DISDMessage(header=receipt_header, payload=receipt_payload)


# ============================================================================
# MESSAGE FACTORY
# ============================================================================

class DISDMessageFactory:
    """Factory for creating DISD messages"""
    
    @staticmethod
    def create_join_message(
        sender_id: str,
        agent_id: str,
        agent_type: str = "general",
        capabilities: List[str] = None,
        endpoint: str = "",
        metadata: Dict[str, Any] = None
    ) -> DISDMessage:
        """Create join message"""
        header = DISDMessageHeader(
            message_type=DISDMessageType.JOIN,
            sender_id=sender_id
        )
        
        payload = JoinPayload(
            agent_id=agent_id,
            agent_type=agent_type,
            capabilities=capabilities or [],
            endpoint=endpoint,
            metadata=metadata or {}
        )
        
        return DISDMessage(header=header, payload=payload)
    
    @staticmethod
    def create_leave_message(
        sender_id: str,
        agent_id: str,
        reason: str = "",
        graceful: bool = True
    ) -> DISDMessage:
        """Create leave message"""
        header = DISDMessageHeader(
            message_type=DISDMessageType.LEAVE,
            sender_id=sender_id
        )
        
        payload = LeavePayload(
            agent_id=agent_id,
            reason=reason,
            graceful=graceful
        )
        
        return DISDMessage(header=header, payload=payload)
    
    @staticmethod
    def create_heartbeat_message(
        sender_id: str,
        agent_id: str,
        status: str = "active",
        load: float = 0.0,
        capabilities: List[str] = None
    ) -> DISDMessage:
        """Create heartbeat message"""
        header = DISDMessageHeader(
            message_type=DISDMessageType.HEARTBEAT,
            sender_id=sender_id
        )
        
        payload = HeartbeatPayload(
            agent_id=agent_id,
            status=status,
            load=load,
            capabilities=capabilities or []
        )
        
        return DISDMessage(header=header, payload=payload)
    
    @staticmethod
    def create_propose_message(
        sender_id: str,
        action_type: str,
        action_payload: Dict[str, Any],
        quorum_required: int = 3,
        veto_threshold: float = 0.3,
        description: str = "",
        expires_at: Optional[datetime] = None
    ) -> DISDMessage:
        """Create proposal message"""
        header = DISDMessageHeader(
            message_type=DISDMessageType.PROPOSE,
            sender_id=sender_id
        )
        
        payload = ProposePayload(
            action_type=action_type,
            action_payload=action_payload,
            quorum_required=quorum_required,
            veto_threshold=veto_threshold,
            description=description,
            expires_at=expires_at or (datetime.utcnow() + timedelta(minutes=5))
        )
        
        return DISDMessage(header=header, payload=payload)
    
    @staticmethod
    def create_vote_message(
        sender_id: str,
        proposal_id: str,
        vote_type: VoteType,
        reason: str = "",
        weight: float = 1.0
    ) -> DISDMessage:
        """Create vote message"""
        header = DISDMessageHeader(
            message_type=DISDMessageType.VOTE,
            sender_id=sender_id
        )
        
        payload = VotePayload(
            proposal_id=proposal_id,
            vote_type=vote_type,
            reason=reason,
            weight=weight
        )
        
        return DISDMessage(header=header, payload=payload)
    
    @staticmethod
    def create_commit_message(
        sender_id: str,
        proposal_id: str,
        decision: str,
        votes: Dict[str, Any],
        auth_token: Optional[str] = None
    ) -> DISDMessage:
        """Create commit message"""
        header = DISDMessageHeader(
            message_type=DISDMessageType.COMMIT,
            sender_id=sender_id
        )
        
        payload = CommitPayload(
            proposal_id=proposal_id,
            decision=decision,
            votes=votes,
            auth_token=auth_token
        )
        
        return DISDMessage(header=header, payload=payload)


# ============================================================================
# MESSAGE VALIDATION
# ============================================================================

class DISDMessageValidator:
    """Validator for DISD messages"""
    
    @staticmethod
    def validate_message(message: DISDMessage) -> tuple[bool, str]:
        """Validate DISD message"""
        try:
            # Check header
            if not message.header.message_id:
                return False, "Missing message ID"
            
            if not message.header.sender_id:
                return False, "Missing sender ID"
            
            if message.is_expired:
                return False, "Message expired"
            
            # Check payload based on type
            if message.message_type == DISDMessageType.JOIN:
                return DISDMessageValidator._validate_join_message(message)
            elif message.message_type == DISDMessageType.PROPOSE:
                return DISDMessageValidator._validate_propose_message(message)
            elif message.message_type == DISDMessageType.VOTE:
                return DISDMessageValidator._validate_vote_message(message)
            
            return True, "Message valid"
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    @staticmethod
    def _validate_join_message(message: DISDMessage) -> tuple[bool, str]:
        """Validate join message"""
        payload = message.payload
        if not isinstance(payload, JoinPayload):
            return False, "Invalid payload type for JOIN message"
        
        if not payload.agent_id:
            return False, "Missing agent ID in JOIN payload"
        
        return True, "JOIN message valid"
    
    @staticmethod
    def _validate_propose_message(message: DISDMessage) -> tuple[bool, str]:
        """Validate propose message"""
        payload = message.payload
        if not isinstance(payload, ProposePayload):
            return False, "Invalid payload type for PROPOSE message"
        
        if not payload.proposal_id:
            return False, "Missing proposal ID"
        
        if not payload.action_type:
            return False, "Missing action type"
        
        if payload.is_expired:
            return False, "Proposal expired"
        
        return True, "PROPOSE message valid"
    
    @staticmethod
    def _validate_vote_message(message: DISDMessage) -> tuple[bool, str]:
        """Validate vote message"""
        payload = message.payload
        if not isinstance(payload, VotePayload):
            return False, "Invalid payload type for VOTE message"
        
        if not payload.proposal_id:
            return False, "Missing proposal ID"
        
        if payload.vote_type not in VoteType:
            return False, "Invalid vote type"
        
        return True, "VOTE message valid"
