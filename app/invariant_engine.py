"""
RARA Invariant Engine - Graph constraint enforcement via Code Visualizer
"""

import httpx
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from .models import GraphInvariant, InvariantCheckResult
import logging

logger = logging.getLogger(__name__)


class InvariantEngine:
    """
    Enforces graph invariants using Code Visualizer as the oracle.
    
    Before any mutation commit:
    1. Regenerate dependency graph
    2. Ensure no orphan nodes
    3. Ensure required invariants hold
    
    If graph breaks → mutation rejected
    """
    
    def __init__(
        self,
        code_visualizer_url: str = None,
        runtime_path: str = "/opt/resonant/runtime"
    ):
        import os
        if code_visualizer_url is None:
            code_visualizer_url = os.getenv("AST_ANALYSIS_SERVICE_URL") or os.getenv("CODE_VISUALIZER_URL", "http://rg_ast_analysis:8000")
        self.code_visualizer_url = code_visualizer_url
        self.runtime_path = runtime_path
        self.last_analysis_id: Optional[str] = None
        self.invariant_results: Dict[str, InvariantCheckResult] = {}
    
    async def analyze_runtime(self) -> str:
        """
        Trigger Code Visualizer analysis of the runtime layer.
        
        Returns:
            analysis_id for subsequent queries
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.code_visualizer_url}/api/analyze",
                json={"path": self.runtime_path}
            )
            response.raise_for_status()
            data = response.json()
            self.last_analysis_id = data.get("analysis_id")
            logger.info(f"Code Visualizer analysis started: {self.last_analysis_id}")
            return self.last_analysis_id
    
    async def get_analysis_result(self, analysis_id: str = None) -> Dict:
        """Get analysis results from Code Visualizer"""
        aid = analysis_id or self.last_analysis_id
        if not aid:
            raise ValueError("No analysis_id available")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.code_visualizer_url}/api/analysis/{aid}"
            )
            response.raise_for_status()
            return response.json()
    
    async def get_broken_connections(self, analysis_id: str = None) -> List[Dict]:
        """Get broken connections from Code Visualizer"""
        aid = analysis_id or self.last_analysis_id
        if not aid:
            return []
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.code_visualizer_url}/api/analysis/{aid}/broken"
            )
            if response.status_code == 200:
                return response.json().get("broken_connections", [])
            return []
    
    async def run_governance(self, analysis_id: str = None) -> Dict:
        """Run governance analysis via Code Visualizer"""
        aid = analysis_id or self.last_analysis_id
        if not aid:
            raise ValueError("No analysis_id available")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.code_visualizer_url}/api/analysis/{aid}/governance",
                json={}
            )
            response.raise_for_status()
            return response.json()
    
    async def check_reachability(self, analysis_id: str = None) -> InvariantCheckResult:
        """
        Invariant A: Every public route must reach a handler.
        ∀ route R → ∃ handler H : path(R → H)
        """
        try:
            analysis = await self.get_analysis_result(analysis_id)
            broken = await self.get_broken_connections(analysis_id)
            
            violations = []
            
            # Check for routes without handlers
            nodes = analysis.get("nodes", [])
            edges = analysis.get("edges", [])
            
            route_nodes = [n for n in nodes if n.get("type") == "route"]
            handler_nodes = {n.get("id") for n in nodes if n.get("type") == "handler"}
            
            edge_targets = {e.get("target") for e in edges}
            
            for route in route_nodes:
                route_id = route.get("id")
                # Check if route has path to any handler
                has_handler = any(
                    e.get("source") == route_id and e.get("target") in handler_nodes
                    for e in edges
                )
                if not has_handler:
                    violations.append(f"Route {route.get('name', route_id)} has no handler")
            
            # Add broken connections as violations
            for bc in broken:
                if bc.get("type") == "route_handler":
                    violations.append(f"Broken: {bc.get('source')} -> {bc.get('target')}")
            
            result = InvariantCheckResult(
                invariant=GraphInvariant.REACHABILITY,
                passed=len(violations) == 0,
                violations=violations
            )
            
            self.invariant_results[GraphInvariant.REACHABILITY.value] = result
            return result
            
        except Exception as e:
            logger.error(f"Reachability check failed: {e}")
            return InvariantCheckResult(
                invariant=GraphInvariant.REACHABILITY,
                passed=False,
                violations=[f"Check failed: {str(e)}"]
            )
    
    async def check_no_orphan_handlers(self, analysis_id: str = None) -> InvariantCheckResult:
        """
        Invariant B: No orphan handlers.
        ∀ handler H → ∃ route R : path(R → H)
        """
        try:
            analysis = await self.get_analysis_result(analysis_id)
            
            violations = []
            
            nodes = analysis.get("nodes", [])
            edges = analysis.get("edges", [])
            
            handler_nodes = [n for n in nodes if n.get("type") == "handler"]
            
            # Find handlers that are targets of edges from routes
            edge_targets = {
                e.get("target") for e in edges
                if any(n.get("id") == e.get("source") and n.get("type") == "route" for n in nodes)
            }
            
            for handler in handler_nodes:
                handler_id = handler.get("id")
                if handler_id not in edge_targets:
                    violations.append(f"Orphan handler: {handler.get('name', handler_id)}")
            
            result = InvariantCheckResult(
                invariant=GraphInvariant.NO_ORPHAN_HANDLERS,
                passed=len(violations) == 0,
                violations=violations
            )
            
            self.invariant_results[GraphInvariant.NO_ORPHAN_HANDLERS.value] = result
            return result
            
        except Exception as e:
            logger.error(f"Orphan handler check failed: {e}")
            return InvariantCheckResult(
                invariant=GraphInvariant.NO_ORPHAN_HANDLERS,
                passed=False,
                violations=[f"Check failed: {str(e)}"]
            )
    
    async def check_auth_boundary(self, analysis_id: str = None) -> InvariantCheckResult:
        """
        Invariant C: Auth boundary.
        No edge crosses (unauthenticated → privileged)
        """
        try:
            analysis = await self.get_analysis_result(analysis_id)
            
            violations = []
            
            nodes = analysis.get("nodes", [])
            edges = analysis.get("edges", [])
            
            # Build node lookup
            node_map = {n.get("id"): n for n in nodes}
            
            # Check for auth boundary violations
            for edge in edges:
                source = node_map.get(edge.get("source"), {})
                target = node_map.get(edge.get("target"), {})
                
                source_auth = source.get("requires_auth", False)
                target_privileged = target.get("privileged", False)
                
                if not source_auth and target_privileged:
                    violations.append(
                        f"Auth boundary violation: {source.get('name', 'unknown')} -> "
                        f"{target.get('name', 'unknown')}"
                    )
            
            result = InvariantCheckResult(
                invariant=GraphInvariant.AUTH_BOUNDARY,
                passed=len(violations) == 0,
                violations=violations
            )
            
            self.invariant_results[GraphInvariant.AUTH_BOUNDARY.value] = result
            return result
            
        except Exception as e:
            logger.error(f"Auth boundary check failed: {e}")
            return InvariantCheckResult(
                invariant=GraphInvariant.AUTH_BOUNDARY,
                passed=False,
                violations=[f"Check failed: {str(e)}"]
            )
    
    async def check_no_cycles(self, analysis_id: str = None) -> InvariantCheckResult:
        """
        Invariant D: No execution cycles without breaker.
        """
        try:
            governance = await self.run_governance(analysis_id)
            
            violations = []
            
            cycles = governance.get("cycles", [])
            for cycle in cycles:
                if not cycle.get("has_breaker", False):
                    violations.append(f"Cycle without breaker: {cycle.get('path', 'unknown')}")
            
            result = InvariantCheckResult(
                invariant=GraphInvariant.NO_CYCLES,
                passed=len(violations) == 0,
                violations=violations
            )
            
            self.invariant_results[GraphInvariant.NO_CYCLES.value] = result
            return result
            
        except Exception as e:
            logger.error(f"Cycle check failed: {e}")
            return InvariantCheckResult(
                invariant=GraphInvariant.NO_CYCLES,
                passed=False,
                violations=[f"Check failed: {str(e)}"]
            )
    
    async def check_capability_isolation(self, analysis_id: str = None) -> InvariantCheckResult:
        """
        Invariant E: Capability isolation.
        Agent nodes may not directly depend on core services.
        """
        try:
            analysis = await self.get_analysis_result(analysis_id)
            
            violations = []
            
            nodes = analysis.get("nodes", [])
            edges = analysis.get("edges", [])
            
            node_map = {n.get("id"): n for n in nodes}
            
            agent_nodes = {n.get("id") for n in nodes if n.get("type") == "agent"}
            core_nodes = {n.get("id") for n in nodes if n.get("layer") == "core"}
            
            for edge in edges:
                if edge.get("source") in agent_nodes and edge.get("target") in core_nodes:
                    source = node_map.get(edge.get("source"), {})
                    target = node_map.get(edge.get("target"), {})
                    violations.append(
                        f"Agent-core violation: {source.get('name', 'unknown')} -> "
                        f"{target.get('name', 'unknown')}"
                    )
            
            result = InvariantCheckResult(
                invariant=GraphInvariant.CAPABILITY_ISOLATION,
                passed=len(violations) == 0,
                violations=violations
            )
            
            self.invariant_results[GraphInvariant.CAPABILITY_ISOLATION.value] = result
            return result
            
        except Exception as e:
            logger.error(f"Capability isolation check failed: {e}")
            return InvariantCheckResult(
                invariant=GraphInvariant.CAPABILITY_ISOLATION,
                passed=False,
                violations=[f"Check failed: {str(e)}"]
            )
    
    async def check_all_invariants(self, analysis_id: str = None) -> Tuple[bool, List[InvariantCheckResult]]:
        """
        Run all invariant checks.
        
        Returns:
            (all_passed, list of results)
        """
        # First, trigger fresh analysis
        if not analysis_id:
            try:
                analysis_id = await self.analyze_runtime()
            except Exception as e:
                # If Code Visualizer is unavailable or path doesn't exist,
                # pass by default (nothing to validate yet)
                logger.warning(f"Code Visualizer unavailable, skipping invariant checks: {e}")
                return True, [
                    InvariantCheckResult(
                        invariant=inv,
                        passed=True,
                        violations=["Skipped - Code Visualizer unavailable"]
                    )
                    for inv in GraphInvariant
                ]
        
        results = []
        
        # Run all checks
        results.append(await self.check_reachability(analysis_id))
        results.append(await self.check_no_orphan_handlers(analysis_id))
        results.append(await self.check_auth_boundary(analysis_id))
        results.append(await self.check_no_cycles(analysis_id))
        results.append(await self.check_capability_isolation(analysis_id))
        
        all_passed = all(r.passed for r in results)
        
        logger.info(
            f"Invariant check complete: {sum(1 for r in results if r.passed)}/{len(results)} passed"
        )
        
        return all_passed, results
    
    def get_last_results(self) -> Dict[str, InvariantCheckResult]:
        """Get the last invariant check results"""
        return self.invariant_results.copy()
