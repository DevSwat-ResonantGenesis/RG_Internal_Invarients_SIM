"""
Epoch Authority

Manages global epochs with commit windows for irreversible effects.
This provides temporal boundaries for distributed operations.

STATUS: PRODUCTION IMPLEMENTATION
UPDATED: 2026-01-08
PURPOSE: Global epoch coordination and commit windows
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EpochStatus(str, Enum):
    """Epoch status states"""
    OPEN = "open"
    COMMITTING = "committing"
    CLOSED = "closed"
    EXPIRED = "expired"


@dataclass
class Epoch:
    """Global epoch with commit window"""
    epoch_id: str
    start_time: datetime
    commit_window_ms: int = 1000  # 1 second commit window
    max_effects_per_epoch: int = 100
    current_effects: List[str] = field(default_factory=list)
    status: EpochStatus = EpochStatus.OPEN
    created_by: str = "system"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        """Check if epoch has expired"""
        expiry_time = self.start_time + timedelta(milliseconds=self.commit_window_ms)
        return datetime.utcnow() > expiry_time
    
    @property
    def is_full(self) -> bool:
        """Check if epoch has reached max effects"""
        return len(self.current_effects) >= self.max_effects_per_epoch
    
    @property
    def can_commit(self) -> bool:
        """Check if epoch can be committed"""
        return self.status == EpochStatus.OPEN and not self.is_expired and not self.is_full
    
    @property
    def time_remaining_ms(self) -> int:
        """Get time remaining in epoch"""
        expiry_time = self.start_time + timedelta(milliseconds=self.commit_window_ms)
        remaining = expiry_time - datetime.utcnow()
        return max(0, int(remaining.total_seconds() * 1000))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert epoch to dictionary"""
        return {
            "epoch_id": self.epoch_id,
            "start_time": self.start_time.isoformat(),
            "commit_window_ms": self.commit_window_ms,
            "max_effects_per_epoch": self.max_effects_per_epoch,
            "current_effects": self.current_effects,
            "status": self.status.value,
            "created_by": self.created_by,
            "is_expired": self.is_expired,
            "is_full": self.is_full,
            "can_commit": self.can_commit,
            "time_remaining_ms": self.time_remaining_ms,
            "metadata": self.metadata
        }


class EpochAuthority:
    """Global epoch coordinator"""
    
    def __init__(self):
        self.current_epoch: Optional[Epoch] = None
        self.epoch_history: List[Epoch] = []
        self.epoch_counter: int = 0
        self.max_history_size: int = 1000
        self.default_commit_window_ms: int = 1000
        self.default_max_effects: int = 100
        
        logger.info("EpochAuthority initialized")
    
    def create_epoch(
        self,
        commit_window_ms: Optional[int] = None,
        max_effects: Optional[int] = None,
        created_by: str = "system",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Epoch:
        """Create new epoch"""
        
        # Close current epoch if exists and open
        if self.current_epoch and self.current_epoch.status == EpochStatus.OPEN:
            self.close_epoch(force=True)
        
        # Create new epoch
        epoch_id = f"epoch_{int(time.time() * 1000)}_{self.epoch_counter}"
        self.epoch_counter += 1
        
        epoch = Epoch(
            epoch_id=epoch_id,
            start_time=datetime.utcnow(),
            commit_window_ms=commit_window_ms or self.default_commit_window_ms,
            max_effects_per_epoch=max_effects or self.default_max_effects,
            created_by=created_by,
            metadata=metadata or {}
        )
        
        self.current_epoch = epoch
        logger.info(f"Created new epoch: {epoch_id} (window: {epoch.commit_window_ms}ms)")
        
        return epoch
    
    def can_commit_effect(self, effect_id: str) -> tuple[bool, str]:
        """Check if effect can be committed in current epoch"""
        if not self.current_epoch:
            return False, "No active epoch"
        
        if self.current_epoch.status != EpochStatus.OPEN:
            return False, f"Epoch not open (status: {self.current_epoch.status.value})"
        
        if self.current_epoch.is_expired:
            return False, "Epoch expired"
        
        if self.current_epoch.is_full:
            return False, "Epoch full"
        
        if effect_id in self.current_epoch.current_effects:
            return False, "Effect already committed in this epoch"
        
        return True, "Effect can be committed"
    
    def commit_effect(self, effect_id: str) -> tuple[bool, str]:
        """Commit effect to current epoch"""
        can_commit, reason = self.can_commit_effect(effect_id)
        if not can_commit:
            return False, reason
        
        self.current_epoch.current_effects.append(effect_id)
        logger.info(f"Committed effect {effect_id} to epoch {self.current_epoch.epoch_id}")
        
        # Check if epoch is now full
        if self.current_epoch.is_full:
            logger.info(f"Epoch {self.current_epoch.epoch_id} is now full")
        
        return True, "Effect committed successfully"
    
    def close_epoch(self, force: bool = False) -> tuple[bool, str]:
        """Close current epoch and make effects irreversible"""
        if not self.current_epoch:
            return False, "No active epoch"
        
        if self.current_epoch.status != EpochStatus.OPEN and not force:
            return False, f"Epoch not open (status: {self.current_epoch.status.value})"
        
        # Mark as closed
        self.current_epoch.status = EpochStatus.CLOSED
        
        # Add to history
        self.epoch_history.append(self.current_epoch)
        
        # Trim history if needed
        if len(self.epoch_history) > self.max_history_size:
            self.epoch_history = self.epoch_history[-self.max_history_size:]
        
        epoch_id = self.current_epoch.epoch_id
        effects_count = len(self.current_epoch.current_effects)
        
        logger.info(f"Closed epoch {epoch_id} with {effects_count} effects")
        
        # Clear current epoch
        self.current_epoch = None
        
        return True, f"Epoch {epoch_id} closed with {effects_count} effects"
    
    def expire_epoch(self) -> tuple[bool, str]:
        """Expire current epoch if time is up"""
        if not self.current_epoch:
            return False, "No active epoch"
        
        if not self.current_epoch.is_expired:
            return False, "Epoch not expired"
        
        self.current_epoch.status = EpochStatus.EXPIRED
        
        # Add to history
        self.epoch_history.append(self.current_epoch)
        
        # Trim history if needed
        if len(self.epoch_history) > self.max_history_size:
            self.epoch_history = self.epoch_history[-self.max_history_size:]
        
        epoch_id = self.current_epoch.epoch_id
        effects_count = len(self.current_epoch.current_effects)
        
        logger.info(f"Expired epoch {epoch_id} with {effects_count} effects")
        
        # Clear current epoch
        self.current_epoch = None
        
        return True, f"Epoch {epoch_id} expired with {effects_count} effects"
    
    def get_current_epoch(self) -> Optional[Epoch]:
        """Get current epoch"""
        return self.current_epoch
    
    def get_epoch(self, epoch_id: str) -> Optional[Epoch]:
        """Get epoch by ID"""
        if self.current_epoch and self.current_epoch.epoch_id == epoch_id:
            return self.current_epoch
        
        for epoch in self.epoch_history:
            if epoch.epoch_id == epoch_id:
                return epoch
        
        return None
    
    def get_epoch_history(self, limit: int = 100) -> List[Epoch]:
        """Get epoch history"""
        return self.epoch_history[-limit:]
    
    def get_active_epochs(self) -> List[Epoch]:
        """Get all active epochs (open or committing)"""
        active = []
        if self.current_epoch and self.current_epoch.status in [EpochStatus.OPEN, EpochStatus.COMMITTING]:
            active.append(self.current_epoch)
        return active
    
    def cleanup_expired_epochs(self) -> int:
        """Clean up expired epochs"""
        cleaned = 0
        
        # Check current epoch
        if self.current_epoch and self.current_epoch.is_expired:
            self.expire_epoch()
            cleaned += 1
        
        # Check history for expired epochs (shouldn't happen, but safety)
        for epoch in self.epoch_history:
            if epoch.status == EpochStatus.EXPIRED:
                epoch.status = EpochStatus.CLOSED
                cleaned += 1
        
        return cleaned
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get epoch statistics"""
        total_epochs = len(self.epoch_history) + (1 if self.current_epoch else 0)
        
        status_counts = {}
        for status in EpochStatus:
            status_counts[status.value] = 0
        
        # Count current epoch
        if self.current_epoch:
            status_counts[self.current_epoch.status.value] += 1
        
        # Count history epochs
        for epoch in self.epoch_history:
            status_counts[epoch.status.value] += 1
        
        # Calculate average effects per epoch
        total_effects = sum(len(epoch.current_effects) for epoch in self.epoch_history)
        if self.current_epoch:
            total_effects += len(self.current_epoch.current_effects)
        
        avg_effects = total_effects / total_epochs if total_epochs > 0 else 0
        
        return {
            "total_epochs": total_epochs,
            "current_epoch_id": self.current_epoch.epoch_id if self.current_epoch else None,
            "epoch_counter": self.epoch_counter,
            "status_counts": status_counts,
            "total_effects": total_effects,
            "average_effects_per_epoch": avg_effects,
            "max_history_size": self.max_history_size,
            "default_commit_window_ms": self.default_commit_window_ms,
            "default_max_effects": self.default_max_effects
        }
    
    def validate_epoch_config(self, config: Dict[str, Any]) -> tuple[bool, str]:
        """Validate epoch configuration"""
        if "commit_window_ms" in config:
            window = config["commit_window_ms"]
            if not isinstance(window, int) or window < 100 or window > 60000:
                return False, "commit_window_ms must be between 100 and 60000 ms"
        
        if "max_effects" in config:
            max_effects = config["max_effects"]
            if not isinstance(max_effects, int) or max_effects < 1 or max_effects > 10000:
                return False, "max_effects must be between 1 and 10000"
        
        return True, "Configuration is valid"
    
    def get_status(self) -> Dict[str, Any]:
        """Get authority status for monitoring"""
        current_epoch_info = None
        if self.current_epoch:
            current_epoch_info = self.current_epoch.to_dict()
        
        return {
            "current_epoch": current_epoch_info,
            "total_epochs_created": self.epoch_counter,
            "epochs_in_history": len(self.epoch_history),
            "active_epochs": len(self.get_active_epochs()),
            "statistics": self.get_statistics(),
            "last_cleanup": datetime.utcnow().isoformat()
        }


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

epoch_authority: EpochAuthority = None


def get_epoch_authority() -> Optional[EpochAuthority]:
    """Get the global epoch authority instance"""
    return epoch_authority


def initialize_epoch_authority() -> EpochAuthority:
    """Initialize the global epoch authority"""
    global epoch_authority
    epoch_authority = EpochAuthority()
    return epoch_authority
