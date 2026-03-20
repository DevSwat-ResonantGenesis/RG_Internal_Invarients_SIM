"""
Mock Cryptographic Receipt Handler

Temporary mock implementation for demonstration purposes.
Will be replaced with real cryptographic implementation once dependency issues are resolved.

STATUS: MOCK IMPLEMENTATION
UPDATED: 2026-01-08
PURPOSE: Temporary placeholder for cryptographic receipt integrity
"""

from dataclasses import dataclass
import json
import time
import secrets
import uuid
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import logging

from .disd_message import DISDMessage, ReceiptStatus

logger = logging.getLogger(__name__)


@dataclass
class ReceiptLogEntry:
    """Mock write-ahead log entry for receipts"""
    entry_id: str
    epoch_id: str
    receipt_hash: str
    previous_hash: str
    chain_hash: str
    receipt_data: Optional['EnhancedReceiptPayload']
    timestamp: datetime
    checksum: str
    
    def calculate_checksum(self) -> str:
        """Calculate entry checksum"""
        receipt_data_json = json.dumps(self.receipt_data.to_dict(), sort_keys=True) if self.receipt_data else ""
        entry_data = f"{self.entry_id}{self.epoch_id}{self.receipt_hash}{self.previous_hash}{self.chain_hash}{self.timestamp.isoformat()}{receipt_data_json}"
        return hashlib.sha256(entry_data.encode()).hexdigest()[:8]
    
    def verify_integrity(self) -> bool:
        """Verify entry integrity"""
        return self.checksum == self.calculate_checksum()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "entry_id": self.entry_id,
            "epoch_id": self.epoch_id,
            "receipt_hash": self.receipt_hash,
            "previous_hash": self.previous_hash,
            "chain_hash": self.chain_hash,
            "receipt_data": self.receipt_data.to_dict() if self.receipt_data else None,
            "timestamp": self.timestamp.isoformat(),
            "checksum": self.checksum
        }


@dataclass
class EnhancedReceiptPayload:
    """Mock enhanced receipt with cryptographic binding"""
    original_message_id: str = ""
    receiver_id: str = ""
    status: ReceiptStatus = ReceiptStatus.ACKNOWLEDGED
    processing_time_ms: int = 0
    message_hash: str = ""
    receiver_signature: str = ""
    receiver_public_key: str = ""
    dsid_binding: str = ""
    epoch_binding: str = ""
    nonce: str = ""
    error_message: str = ""
    
    def __post_init__(self):
        self.payload_type = "enhanced_receipt"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "payload_type": self.payload_type,
            "original_message_id": self.original_message_id,
            "receiver_id": self.receiver_id,
            "status": self.status.value,
            "processing_time_ms": self.processing_time_ms,
            "message_hash": self.message_hash,
            "receiver_signature": self.receiver_signature,
            "receiver_public_key": self.receiver_public_key,
            "dsid_binding": self.dsid_binding,
            "epoch_binding": self.epoch_binding,
            "nonce": self.nonce,
            "error_message": self.error_message
        }


class MockCryptographicReceiptHandler:
    """Mock cryptographic receipt handler for demonstration"""
    
    def __init__(self, system_salt: bytes = b"MOCK_SYSTEM_SALT"):
        self.system_salt = system_salt
        logger.warning("Using MOCK cryptographic receipt handler - NOT FOR PRODUCTION")
        
    def derive_keypair_from_dsid(self, dsid: str) -> Tuple[str, str]:
        """Mock keypair derivation"""
        private_key = f"mock_private_key_{dsid}_{self.system_salt.decode()}"
        public_key = f"mock_public_key_{dsid}_{self.system_salt.decode()}"
        return private_key, public_key
    
    def calculate_message_hash(self, message: DISDMessage) -> str:
        """Calculate SHA-256 hash of message"""
        message_data = json.dumps(message.to_dict(), sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(message_data.encode('utf-8')).hexdigest()
    
    def create_receipt_signature_input(
        self,
        message_hash: str,
        epoch_id: str,
        receiver_dsid: str,
        nonce: str,
        timestamp: int,
        status_code: int
    ) -> bytes:
        """Create input for receipt signature"""
        input_data = (
            message_hash.encode('utf-8') +
            epoch_id.encode('utf-8') +
            receiver_dsid.encode('utf-8') +
            nonce.encode('utf-8') +
            timestamp.to_bytes(8, 'big') +
            status_code.to_bytes(1, 'big')
        )
        return hashlib.sha256(input_data).digest()
    
    def sign_receipt(
        self,
        message: DISDMessage,
        receiver_dsid: str,
        status: ReceiptStatus,
        processing_time_ms: int = 0
    ) -> Tuple[str, str, str]:
        """Create mock signed receipt"""
        # Mock keypair
        private_key, public_key = self.derive_keypair_from_dsid(receiver_dsid)
        
        # Calculate components
        message_hash = self.calculate_message_hash(message)
        epoch_id = message.header.epoch_id or "no_epoch"
        nonce = secrets.token_urlsafe(32)
        timestamp = int(time.time())
        status_code = {
            ReceiptStatus.ACKNOWLEDGED: 1,
            ReceiptStatus.REJECTED: 2,
            ReceiptStatus.PROCESSED: 3,
            ReceiptStatus.FAILED: 4
        }[status]
        
        # Create mock signature
        sig_input = self.create_receipt_signature_input(
            message_hash, epoch_id, receiver_dsid, nonce, timestamp, status_code
        )
        signature = f"mock_signature_{hashlib.sha256(sig_input).hexdigest()}"
        
        return signature, public_key, nonce
    
    def verify_receipt_signature(
        self,
        message: DISDMessage,
        receiver_dsid: str,
        signature_hex: str,
        public_key_hex: str,
        nonce: str,
        status: ReceiptStatus,
        timestamp: int
    ) -> bool:
        """Mock signature verification"""
        # In mock implementation, we just check if signature starts with "mock_signature_"
        if not signature_hex.startswith("mock_signature_"):
            return False
        
        # Verify public key matches DSID
        _, expected_public_key = self.derive_keypair_from_dsid(receiver_dsid)
        if public_key_hex != expected_public_key:
            return False
        
        # Mock verification always passes for valid mock signatures
        return True


class MockReceiptLogManager:
    """Mock receipt log manager for demonstration"""
    
    def __init__(self, log_path: str = "/tmp/mock_receipts.wal"):
        self.log_path = log_path
        self.epoch_chains: Dict[str, List[ReceiptLogEntry]] = {}
        self.current_epoch: Optional[str] = None
        self.crypto_handler = MockCryptographicReceiptHandler()
        
        logger.warning("Using MOCK receipt log manager - NOT FOR PRODUCTION")
        logger.info(f"MockReceiptLogManager initialized with log path: {log_path}")
    
    def append_receipt(self, receipt: EnhancedReceiptPayload, message: DISDMessage) -> str:
        """Append receipt to mock write-ahead log"""
        # Ensure epoch chain exists
        epoch_id = message.header.epoch_id or "no_epoch"
        if epoch_id not in self.epoch_chains:
            self._initialize_epoch_chain(epoch_id)
        
        # Calculate previous hash
        chain = self.epoch_chains[epoch_id]
        previous_hash = chain[-1].receipt_hash if chain else self._get_genesis_hash(epoch_id)
        
        # Calculate receipt hash
        receipt_hash = self._calculate_receipt_hash(receipt, previous_hash)
        
        # Create log entry
        entry = ReceiptLogEntry(
            entry_id=str(uuid.uuid4()),
            epoch_id=epoch_id,
            receipt_hash=receipt_hash,
            previous_hash=previous_hash,
            chain_hash=self._calculate_chain_hash(chain + [receipt_hash]),
            receipt_data=receipt,
            timestamp=datetime.utcnow(),
            checksum=""
        )
        
        # Calculate and verify checksum
        entry.checksum = entry.calculate_checksum()
        if not entry.verify_integrity():
            raise ValueError("Log entry integrity check failed")
        
        # Append to chain
        chain.append(entry)
        
        logger.debug(f"Mock receipt appended to log: {receipt.original_message_id} → {receipt.receiver_id}")
        return receipt_hash
    
    def _initialize_epoch_chain(self, epoch_id: str):
        """Initialize new epoch chain"""
        genesis_hash = self._get_genesis_hash(epoch_id)
        self.epoch_chains[epoch_id] = []
        
        # Write epoch marker
        marker_entry = ReceiptLogEntry(
            entry_id=f"epoch_marker_{epoch_id}",
            epoch_id=epoch_id,
            receipt_hash=genesis_hash,
            previous_hash="",
            chain_hash=genesis_hash,
            receipt_data=None,
            timestamp=datetime.utcnow(),
            checksum=""
        )
        marker_entry.checksum = marker_entry.calculate_checksum()
        
        logger.info(f"Initialized mock epoch chain: {epoch_id}")
    
    def _get_genesis_hash(self, epoch_id: str) -> str:
        """Calculate genesis hash for epoch"""
        return hashlib.sha256(f"epoch_{epoch_id}".encode()).hexdigest()
    
    def _calculate_receipt_hash(self, receipt: EnhancedReceiptPayload, previous_hash: str) -> str:
        """Calculate hash for receipt"""
        receipt_data = json.dumps(receipt.to_dict(), sort_keys=True, separators=(',', ':'))
        hash_input = (
            receipt.original_message_id.encode() +
            receipt.receiver_id.encode() +
            receipt.receiver_signature.encode() +
            receipt.nonce.encode() +
            str(receipt.status.value).encode() +
            previous_hash.encode() +
            receipt_data.encode()
        )
        return hashlib.sha256(hash_input).hexdigest()
    
    def _calculate_chain_hash(self, receipt_hashes: List[str]) -> str:
        """Calculate hash for entire chain"""
        if not receipt_hashes:
            return ""
        
        chain_input = b"".join(hash.encode() for hash in receipt_hashes)
        return hashlib.sha256(chain_input).hexdigest()
    
    def verify_epoch_chain(self, epoch_id: str) -> bool:
        """Verify entire epoch chain integrity"""
        chain = self.epoch_chains.get(epoch_id, [])
        if not chain:
            return True
        
        # Verify genesis
        expected_genesis = self._get_genesis_hash(epoch_id)
        if chain[0].receipt_hash != expected_genesis:
            logger.error(f"Genesis hash mismatch for epoch {epoch_id}")
            return False
        
        # Verify chain links
        for i in range(1, len(chain)):
            if chain[i].previous_hash != chain[i-1].receipt_hash:
                logger.error(f"Chain link broken at index {i} for epoch {epoch_id}")
                return False
            if not chain[i].verify_integrity():
                logger.error(f"Entry integrity failed at index {i} for epoch {epoch_id}")
                return False
        
        # Verify final chain hash
        receipt_hashes = [entry.receipt_hash for entry in chain]
        expected_chain_hash = self._calculate_chain_hash(receipt_hashes)
        if chain[-1].chain_hash != expected_chain_hash:
            logger.error(f"Chain hash mismatch for epoch {epoch_id}")
            return False
        
        return True
    
    def get_epoch_statistics(self, epoch_id: str) -> Dict[str, Any]:
        """Get statistics for epoch"""
        chain = self.epoch_chains.get(epoch_id, [])
        
        return {
            "epoch_id": epoch_id,
            "total_entries": len(chain),
            "receipt_entries": len([e for e in chain if e.receipt_data is not None]),
            "genesis_hash": self._get_genesis_hash(epoch_id),
            "final_chain_hash": chain[-1].chain_hash if chain else "",
            "chain_integrity": self.verify_epoch_chain(epoch_id),
            "last_entry_time": chain[-1].timestamp.isoformat() if chain else None
        }
    
    def get_all_epoch_statistics(self) -> Dict[str, Any]:
        """Get statistics for all epochs"""
        return {
            "total_epochs": len(self.epoch_chains),
            "epochs": {
                epoch_id: self.get_epoch_statistics(epoch_id)
                for epoch_id in self.epoch_chains.keys()
            }
        }


class MockFailureDetectionSystem:
    """Mock failure detection system for demonstration"""
    
    def __init__(self):
        self.suspicion_threshold = 0.7
        self.missing_receipt_timeout_ms = 10000
        self.max_delay_tolerance_ms = 5000
        self.suspicion_scores: Dict[str, float] = {}
        self.agent_nonces: Dict[str, set] = {}
        
        logger.warning("Using MOCK failure detection system - NOT FOR PRODUCTION")
    
    def detect_missing_receipts(self, message_id: str, target_agents: List[str]) -> Dict[str, str]:
        """Mock detection of missing receipts"""
        missing = {}
        
        # Simulate some missing receipts for demo
        for agent_id in target_agents:
            if agent_id.endswith("_missing"):
                missing[agent_id] = "no_receipt"
            elif agent_id.endswith("_delayed"):
                missing[agent_id] = "receipt_delayed"
        
        return missing
    
    def detect_byzantine_behavior(
        self, 
        message_id: str, 
        received_receipts: Dict[str, EnhancedReceiptPayload]
    ) -> Dict[str, str]:
        """Mock detection of Byzantine receipt behavior"""
        byzantine_agents = {}
        
        # Check for nonce reuse
        for agent_id, receipt in received_receipts.items():
            if agent_id not in self.agent_nonces:
                self.agent_nonces[agent_id] = set()
            
            if receipt.nonce in self.agent_nonces[agent_id]:
                byzantine_agents[agent_id] = "nonce_reuse"
            else:
                self.agent_nonces[agent_id].add(receipt.nonce)
        
        # Check for conflicting statuses on same message
        status_groups = {}
        for agent_id, receipt in received_receipts.items():
            if receipt.original_message_id == message_id:
                status = receipt.status
                if status not in status_groups:
                    status_groups[status] = []
                status_groups[status].append(agent_id)
        
        # If more than one status exists for same message, flag all
        if len(status_groups) > 1:
            for status, agents in status_groups.items():
                for agent_id in agents:
                    byzantine_agents[agent_id] = f"conflicting_status_{status.value}"
        
        return byzantine_agents
    
    def update_suspicion_score(self, agent_id: str, issue_type: str, severity: float = 0.1):
        """Update agent suspicion score"""
        current_score = self.suspicion_scores.get(agent_id, 0.0)
        new_score = min(1.0, current_score + severity)
        self.suspicion_scores[agent_id] = new_score
        
        if new_score >= self.suspicion_threshold:
            logger.warning(f"Agent {agent_id} suspicion score: {new_score:.2f} ({issue_type})")
    
    def is_agent_suspicious(self, agent_id: str) -> bool:
        """Check if agent is suspicious"""
        return self.suspicion_scores.get(agent_id, 0.0) >= self.suspicion_threshold
    
    def get_agent_suspicion_scores(self) -> Dict[str, float]:
        """Get all agent suspicion scores"""
        return self.suspicion_scores.copy()
    
    def reset_suspicion_score(self, agent_id: str):
        """Reset agent suspicion score"""
        self.suspicion_scores[agent_id] = 0.0
        logger.info(f"Reset suspicion score for agent {agent_id}")


# ============================================================================
# GLOBAL INSTANCES
# ============================================================================

mock_crypto_receipt_handler: MockCryptographicReceiptHandler = None
mock_receipt_log_manager: MockReceiptLogManager = None
mock_failure_detection_system: MockFailureDetectionSystem = None


def get_mock_crypto_receipt_handler() -> Optional[MockCryptographicReceiptHandler]:
    """Get the global mock cryptographic receipt handler"""
    return mock_crypto_receipt_handler


def get_mock_receipt_log_manager() -> Optional[MockReceiptLogManager]:
    """Get the global mock receipt log manager"""
    return mock_receipt_log_manager


def get_mock_failure_detection_system() -> Optional[MockFailureDetectionSystem]:
    """Get the global mock failure detection system"""
    return mock_failure_detection_system


def initialize_mock_cryptographic_receipt_system(
    system_salt: bytes = b"MOCK_SYSTEM_SALT",
    log_path: str = "/tmp/mock_receipts.wal"
) -> Tuple[MockCryptographicReceiptHandler, MockReceiptLogManager, MockFailureDetectionSystem]:
    """Initialize the global mock cryptographic receipt system"""
    global mock_crypto_receipt_handler, mock_receipt_log_manager, mock_failure_detection_system
    
    mock_crypto_receipt_handler = MockCryptographicReceiptHandler(system_salt)
    mock_receipt_log_manager = MockReceiptLogManager(log_path)
    mock_failure_detection_system = MockFailureDetectionSystem()
    
    logger.info("Mock cryptographic receipt system initialized")
    return mock_crypto_receipt_handler, mock_receipt_log_manager, mock_failure_detection_system
