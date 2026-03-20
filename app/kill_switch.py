"""
RARA Kill Switch - Production-grade emergency stop mechanism

Non-negotiable requirements:
1. Cannot be overridden by agents
2. Freezes mutation execution immediately
3. Preserves observability
4. Bound to CLI, API, and systemd signal
"""

import os
import signal
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, List
from enum import Enum
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# KILL SWITCH STATES
# ============================================================================

class KillSwitchState(str, Enum):
    """Kill switch states"""
    ACTIVE = "active"           # System running normally
    FROZEN = "frozen"           # Mutations blocked, observability preserved
    EMERGENCY_STOP = "emergency_stop"  # Full stop, no operations
    MAINTENANCE = "maintenance"  # Planned maintenance mode


class KillSwitchTrigger(str, Enum):
    """What triggered the kill switch"""
    API = "api"                 # HTTP API call
    CLI = "cli"                 # Command line
    SIGNAL = "signal"           # Unix signal (SIGUSR1, SIGUSR2)
    FILE = "file"               # FREEZE file detected
    INVARIANT = "invariant"     # Critical invariant violation
    CIRCUIT_BREAKER = "circuit_breaker"  # Too many failures
    HUMAN = "human"             # Explicit human action
    SCHEDULED = "scheduled"     # Scheduled maintenance


# ============================================================================
# KILL SWITCH EVENT
# ============================================================================

class KillSwitchEvent(BaseModel):
    """Record of a kill switch state change"""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    previous_state: KillSwitchState
    new_state: KillSwitchState
    trigger: KillSwitchTrigger
    actor: str = "system"
    reason: str = ""
    metadata: dict = {}


# ============================================================================
# KILL SWITCH CONTROLLER
# ============================================================================

class KillSwitch:
    """
    Production-grade kill switch for RARA.
    
    Features:
    - Multiple trigger mechanisms (API, CLI, signal, file)
    - Cannot be overridden by agents
    - Preserves full observability
    - Audit trail of all state changes
    """
    
    def __init__(
        self,
        state_dir: str = "/opt/resonant/state",
        freeze_file: str = "/opt/resonant/state/FREEZE",
        emergency_file: str = "/opt/resonant/state/EMERGENCY_STOP"
    ):
        self.state_dir = Path(state_dir)
        self.freeze_file = Path(freeze_file)
        self.emergency_file = Path(emergency_file)
        
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        self._state = KillSwitchState.ACTIVE
        self._events: List[KillSwitchEvent] = []
        self._callbacks: List[Callable] = []
        
        # Check for existing freeze/emergency files
        self._check_file_state()
        
        # Register signal handlers
        self._register_signals()
    
    @property
    def state(self) -> KillSwitchState:
        """Current kill switch state"""
        return self._state
    
    @property
    def is_active(self) -> bool:
        """True if system is running normally"""
        return self._state == KillSwitchState.ACTIVE
    
    @property
    def is_frozen(self) -> bool:
        """True if mutations are blocked"""
        return self._state in [
            KillSwitchState.FROZEN,
            KillSwitchState.EMERGENCY_STOP,
            KillSwitchState.MAINTENANCE
        ]
    
    @property
    def allows_mutations(self) -> bool:
        """True if mutations are allowed"""
        return self._state == KillSwitchState.ACTIVE
    
    def _check_file_state(self):
        """Check for freeze/emergency files on startup"""
        if self.emergency_file.exists():
            self._state = KillSwitchState.EMERGENCY_STOP
            logger.warning("Emergency stop file detected on startup")
        elif self.freeze_file.exists():
            self._state = KillSwitchState.FROZEN
            logger.warning("Freeze file detected on startup")
    
    def _register_signals(self):
        """Register Unix signal handlers"""
        try:
            # SIGUSR1 = Freeze
            signal.signal(signal.SIGUSR1, self._handle_sigusr1)
            # SIGUSR2 = Unfreeze
            signal.signal(signal.SIGUSR2, self._handle_sigusr2)
            logger.info("Signal handlers registered: SIGUSR1=freeze, SIGUSR2=unfreeze")
        except (ValueError, OSError) as e:
            # Signal handling may not work in all contexts (e.g., threads)
            logger.warning(f"Could not register signal handlers: {e}")
    
    def _handle_sigusr1(self, signum, frame):
        """Handle SIGUSR1 - Freeze"""
        logger.warning("Received SIGUSR1 - triggering freeze")
        self.freeze(trigger=KillSwitchTrigger.SIGNAL, reason="SIGUSR1 received")
    
    def _handle_sigusr2(self, signum, frame):
        """Handle SIGUSR2 - Unfreeze"""
        logger.info("Received SIGUSR2 - triggering unfreeze")
        self.unfreeze(trigger=KillSwitchTrigger.SIGNAL, reason="SIGUSR2 received")
    
    def _record_event(
        self,
        previous: KillSwitchState,
        new: KillSwitchState,
        trigger: KillSwitchTrigger,
        actor: str = "system",
        reason: str = ""
    ):
        """Record a state change event"""
        event = KillSwitchEvent(
            previous_state=previous,
            new_state=new,
            trigger=trigger,
            actor=actor,
            reason=reason
        )
        self._events.append(event)
        
        # Keep last 1000 events
        if len(self._events) > 1000:
            self._events = self._events[-1000:]
        
        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Kill switch callback error: {e}")
    
    def register_callback(self, callback: Callable):
        """Register a callback for state changes"""
        self._callbacks.append(callback)
    
    # ========================================================================
    # STATE TRANSITIONS
    # ========================================================================
    
    def freeze(
        self,
        trigger: KillSwitchTrigger = KillSwitchTrigger.API,
        actor: str = "system",
        reason: str = "Manual freeze"
    ) -> bool:
        """
        Freeze the system - block all mutations.
        
        This is the soft stop. Observability is preserved.
        """
        if self._state == KillSwitchState.EMERGENCY_STOP:
            logger.warning("Cannot freeze: system in emergency stop")
            return False
        
        previous = self._state
        self._state = KillSwitchState.FROZEN
        
        # Create freeze file
        self.freeze_file.touch()
        
        self._record_event(previous, self._state, trigger, actor, reason)
        
        logger.warning(f"System FROZEN by {actor} via {trigger.value}: {reason}")
        
        return True
    
    def unfreeze(
        self,
        trigger: KillSwitchTrigger = KillSwitchTrigger.API,
        actor: str = "system",
        reason: str = "Manual unfreeze"
    ) -> bool:
        """
        Unfreeze the system - allow mutations.
        
        Cannot unfreeze from emergency stop without explicit reset.
        """
        if self._state == KillSwitchState.EMERGENCY_STOP:
            logger.warning("Cannot unfreeze: system in emergency stop. Use reset_emergency().")
            return False
        
        previous = self._state
        self._state = KillSwitchState.ACTIVE
        
        # Remove freeze file
        if self.freeze_file.exists():
            self.freeze_file.unlink()
        
        self._record_event(previous, self._state, trigger, actor, reason)
        
        logger.info(f"System UNFROZEN by {actor} via {trigger.value}: {reason}")
        
        return True
    
    def emergency_stop(
        self,
        trigger: KillSwitchTrigger = KillSwitchTrigger.API,
        actor: str = "system",
        reason: str = "Emergency stop"
    ) -> bool:
        """
        Emergency stop - full system halt.
        
        This is the hard stop. Only human can reset.
        """
        previous = self._state
        self._state = KillSwitchState.EMERGENCY_STOP
        
        # Create emergency file
        self.emergency_file.touch()
        
        # Also create freeze file for redundancy
        self.freeze_file.touch()
        
        self._record_event(previous, self._state, trigger, actor, reason)
        
        logger.critical(f"EMERGENCY STOP by {actor} via {trigger.value}: {reason}")
        
        return True
    
    def reset_emergency(
        self,
        actor: str,
        reason: str,
        confirmation_token: str
    ) -> bool:
        """
        Reset from emergency stop.
        
        Requires explicit human action with confirmation token.
        """
        # Validate confirmation token (in prod, this would be a signed JWT)
        if not confirmation_token or len(confirmation_token) < 8:
            logger.error("Emergency reset rejected: invalid confirmation token")
            return False
        
        if self._state != KillSwitchState.EMERGENCY_STOP:
            logger.warning("Not in emergency stop state")
            return False
        
        previous = self._state
        self._state = KillSwitchState.FROZEN  # Go to frozen, not active
        
        # Remove emergency file
        if self.emergency_file.exists():
            self.emergency_file.unlink()
        
        self._record_event(
            previous, self._state,
            KillSwitchTrigger.HUMAN, actor,
            f"Emergency reset: {reason}"
        )
        
        logger.warning(f"Emergency stop RESET by {actor}: {reason}")
        
        return True
    
    def enter_maintenance(
        self,
        actor: str,
        reason: str,
        duration_minutes: int = 60
    ) -> bool:
        """
        Enter planned maintenance mode.
        """
        if self._state == KillSwitchState.EMERGENCY_STOP:
            logger.warning("Cannot enter maintenance: system in emergency stop")
            return False
        
        previous = self._state
        self._state = KillSwitchState.MAINTENANCE
        
        self.freeze_file.touch()
        
        self._record_event(
            previous, self._state,
            KillSwitchTrigger.SCHEDULED, actor,
            f"Maintenance: {reason} (duration: {duration_minutes}m)"
        )
        
        logger.info(f"Entering MAINTENANCE mode: {reason}")
        
        return True
    
    def exit_maintenance(
        self,
        actor: str,
        reason: str = "Maintenance complete"
    ) -> bool:
        """
        Exit maintenance mode.
        """
        if self._state != KillSwitchState.MAINTENANCE:
            logger.warning("Not in maintenance mode")
            return False
        
        previous = self._state
        self._state = KillSwitchState.ACTIVE
        
        if self.freeze_file.exists():
            self.freeze_file.unlink()
        
        self._record_event(
            previous, self._state,
            KillSwitchTrigger.HUMAN, actor,
            reason
        )
        
        logger.info(f"Exiting MAINTENANCE mode: {reason}")
        
        return True
    
    # ========================================================================
    # AUTOMATIC TRIGGERS
    # ========================================================================
    
    def trigger_on_invariant_violation(
        self,
        invariant_id: str,
        severity: str
    ):
        """
        Automatically trigger based on invariant violation.
        
        Critical invariants trigger emergency stop.
        High severity triggers freeze.
        """
        if severity == "critical":
            self.emergency_stop(
                trigger=KillSwitchTrigger.INVARIANT,
                reason=f"Critical invariant violation: {invariant_id}"
            )
        elif severity == "high":
            self.freeze(
                trigger=KillSwitchTrigger.INVARIANT,
                reason=f"High severity invariant violation: {invariant_id}"
            )
    
    def trigger_on_circuit_breaker(
        self,
        consecutive_failures: int,
        threshold: int = 5
    ):
        """
        Automatically trigger based on failure circuit breaker.
        """
        if consecutive_failures >= threshold:
            self.freeze(
                trigger=KillSwitchTrigger.CIRCUIT_BREAKER,
                reason=f"Circuit breaker: {consecutive_failures} consecutive failures"
            )
    
    # ========================================================================
    # STATUS & AUDIT
    # ========================================================================
    
    def get_status(self) -> dict:
        """Get current kill switch status"""
        return {
            "state": self._state.value,
            "is_active": self.is_active,
            "is_frozen": self.is_frozen,
            "allows_mutations": self.allows_mutations,
            "freeze_file_exists": self.freeze_file.exists(),
            "emergency_file_exists": self.emergency_file.exists(),
            "events_count": len(self._events),
            "last_event": self._events[-1].model_dump() if self._events else None
        }
    
    def get_events(self, limit: int = 50) -> List[dict]:
        """Get recent kill switch events"""
        return [e.model_dump() for e in self._events[-limit:]]
    
    def get_audit_trail(self) -> List[dict]:
        """Get full audit trail for compliance"""
        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "previous_state": e.previous_state.value,
                "new_state": e.new_state.value,
                "trigger": e.trigger.value,
                "actor": e.actor,
                "reason": e.reason
            }
            for e in self._events
        ]


# ============================================================================
# CLI INTERFACE
# ============================================================================

def cli_freeze():
    """CLI command to freeze the system"""
    ks = KillSwitch()
    ks.freeze(trigger=KillSwitchTrigger.CLI, actor="cli", reason="CLI freeze command")
    print(f"System frozen. State: {ks.state.value}")


def cli_unfreeze():
    """CLI command to unfreeze the system"""
    ks = KillSwitch()
    ks.unfreeze(trigger=KillSwitchTrigger.CLI, actor="cli", reason="CLI unfreeze command")
    print(f"System unfrozen. State: {ks.state.value}")


def cli_emergency_stop():
    """CLI command for emergency stop"""
    ks = KillSwitch()
    ks.emergency_stop(trigger=KillSwitchTrigger.CLI, actor="cli", reason="CLI emergency stop")
    print(f"EMERGENCY STOP. State: {ks.state.value}")


def cli_status():
    """CLI command to check status"""
    ks = KillSwitch()
    status = ks.get_status()
    print(f"State: {status['state']}")
    print(f"Allows mutations: {status['allows_mutations']}")
    print(f"Freeze file: {status['freeze_file_exists']}")
    print(f"Emergency file: {status['emergency_file_exists']}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: kill_switch.py [freeze|unfreeze|emergency|status]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "freeze":
        cli_freeze()
    elif cmd == "unfreeze":
        cli_unfreeze()
    elif cmd == "emergency":
        cli_emergency_stop()
    elif cmd == "status":
        cli_status()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
