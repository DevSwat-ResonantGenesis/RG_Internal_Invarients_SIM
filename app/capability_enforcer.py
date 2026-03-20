"""
Capability Enforcer - Enforces capability grammar for mutations.

STATUS: PRODUCTION
CREATED: 2025-12-21
GOVERNANCE: Enforces capability grammar rules before allowing mutations.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

GRAMMAR_PATH = os.getenv(
    "CAPABILITY_GRAMMAR_PATH",
    "/opt/resonant/governance/capability_grammar.yaml"
)


class RiskLevel(Enum):
    """Risk levels for capabilities."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CapabilityCheck:
    """Result of a capability check."""
    allowed: bool
    capability: str
    reason: str
    risk_level: RiskLevel
    requirements_met: List[str]
    requirements_missing: List[str]


class CapabilityEnforcer:
    """
    Enforces capability grammar for mutations.
    
    Loads capability definitions from YAML and validates
    mutation requests against defined rules.
    """
    
    def __init__(self, grammar_path: Optional[str] = None):
        self.grammar_path = grammar_path or GRAMMAR_PATH
        self.grammar: Dict[str, Any] = {}
        self.capabilities: Dict[str, Any] = {}
        self.environment = os.getenv("RARA_ENVIRONMENT", "dev")
        self._load_grammar()
        
    def _load_grammar(self) -> None:
        """Load capability grammar from YAML file."""
        path = Path(self.grammar_path)
        if not path.exists():
            logger.warning(f"Capability grammar not found at {self.grammar_path}, using defaults")
            self._set_defaults()
            return
            
        try:
            with open(path) as f:
                self.grammar = yaml.safe_load(f)
            self.capabilities = self.grammar.get("capabilities", {})
            logger.info(f"Loaded {len(self.capabilities)} capabilities from grammar")
        except Exception as e:
            logger.error(f"Failed to load capability grammar: {e}")
            self._set_defaults()
            
    def _set_defaults(self) -> None:
        """Set default restrictive grammar."""
        self.grammar = {
            "version": "1.0.0",
            "global": {
                "require_snapshot_before_mutation": True,
                "require_invariant_pass": True,
                "confidence": {"minimum": 0.7}
            }
        }
        self.capabilities = {}
        
    def check_capability(
        self,
        capability_name: str,
        context: Dict[str, Any]
    ) -> CapabilityCheck:
        """
        Check if a capability is allowed given the context.
        
        Args:
            capability_name: The capability to check (e.g., "filesystem.write")
            context: Context including confidence, snapshot status, etc.
            
        Returns:
            CapabilityCheck with result and details
        """
        # Check if capability exists
        if capability_name not in self.capabilities:
            return CapabilityCheck(
                allowed=False,
                capability=capability_name,
                reason=f"Unknown capability: {capability_name}",
                risk_level=RiskLevel.CRITICAL,
                requirements_met=[],
                requirements_missing=["capability_defined"]
            )
            
        cap_def = self.capabilities[capability_name]
        risk_level = RiskLevel(cap_def.get("risk_level", "high"))
        requirements = cap_def.get("requires", [])
        
        met = []
        missing = []
        
        # Check each requirement
        for req in requirements:
            if self._check_requirement(req, context, cap_def):
                met.append(req)
            else:
                missing.append(req)
                
        # Check path restrictions
        if "allowed_paths" in cap_def:
            path = context.get("path", "")
            if not self._path_allowed(path, cap_def):
                missing.append(f"path_allowed:{path}")
                
        # Check denied paths
        if "denied_paths" in cap_def:
            path = context.get("path", "")
            if self._path_denied(path, cap_def):
                missing.append(f"path_not_denied:{path}")
                
        allowed = len(missing) == 0
        
        if allowed:
            reason = f"Capability {capability_name} allowed"
        else:
            reason = f"Missing requirements: {', '.join(missing)}"
            
        return CapabilityCheck(
            allowed=allowed,
            capability=capability_name,
            reason=reason,
            risk_level=risk_level,
            requirements_met=met,
            requirements_missing=missing
        )
        
    def _check_requirement(
        self,
        requirement: str,
        context: Dict[str, Any],
        cap_def: Dict[str, Any]
    ) -> bool:
        """Check if a single requirement is met."""
        if requirement == "snapshot":
            return context.get("has_snapshot", False)
            
        if requirement == "invariant_pass":
            return context.get("invariant_passed", False)
            
        if requirement == "governance_approval":
            return context.get("governance_approved", False)
            
        if requirement == "human_confirmation":
            return context.get("human_confirmed", False)
            
        if requirement == "code_visualizer_analysis":
            return context.get("visualizer_analyzed", False)
            
        if requirement == "rate_limit_check":
            return context.get("rate_limit_ok", True)
            
        if requirement.startswith("confidence"):
            # Parse "confidence >= 0.7"
            parts = requirement.split()
            if len(parts) >= 3:
                threshold = float(parts[2])
                return context.get("confidence", 0) >= threshold
            # Use global minimum
            min_conf = self.grammar.get("global", {}).get("confidence", {}).get("minimum", 0.7)
            return context.get("confidence", 0) >= min_conf
            
        # Unknown requirement - fail safe
        logger.warning(f"Unknown requirement: {requirement}")
        return False
        
    def _path_allowed(self, path: str, cap_def: Dict[str, Any]) -> bool:
        """Check if path is in allowed paths."""
        allowed_paths = cap_def.get("allowed_paths", [])
        if not allowed_paths:
            return True
            
        for pattern in allowed_paths:
            if self._path_matches(path, pattern):
                return True
        return False
        
    def _path_denied(self, path: str, cap_def: Dict[str, Any]) -> bool:
        """Check if path is in denied paths."""
        denied_paths = cap_def.get("denied_paths", [])
        
        for pattern in denied_paths:
            if self._path_matches(path, pattern):
                return True
        return False
        
    def _path_matches(self, path: str, pattern: str) -> bool:
        """Check if path matches a glob pattern."""
        import fnmatch
        return fnmatch.fnmatch(path, pattern)
        
    def get_environment_overrides(self) -> Dict[str, Any]:
        """Get environment-specific overrides."""
        envs = self.grammar.get("environments", {})
        return envs.get(self.environment, {})
        
    def is_graceful_skip_allowed(self) -> bool:
        """Check if graceful skip is allowed in current environment."""
        overrides = self.get_environment_overrides()
        return overrides.get("graceful_skip_allowed", False)
        
    def get_stats(self) -> Dict[str, Any]:
        """Get enforcer statistics."""
        return {
            "grammar_version": self.grammar.get("version", "unknown"),
            "capabilities_defined": len(self.capabilities),
            "environment": self.environment,
            "graceful_skip_allowed": self.is_graceful_skip_allowed()
        }


# Global instance
_enforcer: Optional[CapabilityEnforcer] = None


def get_capability_enforcer() -> CapabilityEnforcer:
    """Get or create the global capability enforcer."""
    global _enforcer
    if _enforcer is None:
        _enforcer = CapabilityEnforcer()
    return _enforcer


def check_capability(capability: str, context: Dict[str, Any]) -> CapabilityCheck:
    """Convenience function to check a capability."""
    return get_capability_enforcer().check_capability(capability, context)
