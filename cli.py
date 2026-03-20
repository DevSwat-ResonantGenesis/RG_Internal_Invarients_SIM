#!/usr/bin/env python3
"""
RARA CLI - Command-line interface for local development and testing
"""

import argparse
import json
import sys
import base64
from pathlib import Path

try:
    import httpx
except ImportError:
    print("httpx not installed. Run: pip install httpx")
    sys.exit(1)


RARA_URL = "http://localhost:8093"


def status(args):
    """Get RARA status"""
    response = httpx.get(f"{RARA_URL}/status", timeout=10)
    print(json.dumps(response.json(), indent=2))


def health(args):
    """Check RARA health"""
    response = httpx.get(f"{RARA_URL}/health", timeout=10)
    print(json.dumps(response.json(), indent=2))


def freeze(args):
    """Freeze system - enter observe-only mode"""
    response = httpx.post(f"{RARA_URL}/control/freeze", timeout=10)
    print(json.dumps(response.json(), indent=2))


def unfreeze(args):
    """Unfreeze system - enable mutations"""
    response = httpx.post(f"{RARA_URL}/control/unfreeze", timeout=10)
    print(json.dumps(response.json(), indent=2))


def list_snapshots(args):
    """List recent snapshots"""
    response = httpx.get(f"{RARA_URL}/snapshots", params={"limit": args.limit}, timeout=10)
    snapshots = response.json()
    
    print(f"{'ID':<12} {'Timestamp':<24} {'Health':<8} {'Files':<8} {'Trigger'}")
    print("-" * 80)
    for snap in snapshots:
        print(f"{snap['id']:<12} {snap['timestamp'][:23]:<24} {snap['health']:<8} {snap['files_count']:<8} {snap['trigger']}")


def create_snapshot(args):
    """Create a manual snapshot"""
    response = httpx.post(
        f"{RARA_URL}/snapshots/create",
        params={"trigger": args.trigger or "manual"},
        timeout=30
    )
    print(json.dumps(response.json(), indent=2))


def restore_snapshot(args):
    """Restore to a specific snapshot"""
    response = httpx.post(
        f"{RARA_URL}/snapshots/{args.snapshot_id}/restore",
        params={"reason": args.reason or "manual restore"},
        timeout=30
    )
    print(json.dumps(response.json(), indent=2))


def register_agent(args):
    """Register a new agent"""
    response = httpx.post(
        f"{RARA_URL}/agents/register",
        json={
            "agent_id": args.agent_id,
            "role": args.role,
            "dsid": args.dsid or f"dsid-a-{args.agent_id}",
            "public_key": args.public_key or "placeholder-key"
        },
        timeout=10
    )
    print(json.dumps(response.json(), indent=2))


def agent_capabilities(args):
    """Get agent capabilities"""
    response = httpx.get(f"{RARA_URL}/agents/{args.agent_id}/capabilities", timeout=10)
    data = response.json()
    
    print(f"Agent: {data['agent_id']}")
    print(f"{'Capability':<35} {'Trust':<8} {'Status':<15} {'Success':<8} {'Fail'}")
    print("-" * 80)
    
    for cap, info in data['capabilities'].items():
        status = "REVOKED" if info['is_revoked'] else "DISABLED" if info['is_disabled'] else "APPROVAL" if info['requires_approval'] else "ACTIVE"
        print(f"{cap:<35} {info['trust']:.2f}    {status:<15} {info['successes']:<8} {info['failures']}")


def agent_stats(args):
    """Get agent statistics"""
    response = httpx.get(f"{RARA_URL}/agents/{args.agent_id}/stats", timeout=10)
    print(json.dumps(response.json(), indent=2))


def mutate_file(args):
    """Execute a file mutation"""
    # Read file content
    content = Path(args.source).read_bytes() if args.source else b""
    content_b64 = base64.b64encode(content).decode()
    
    mutation = {
        "actor": "human",
        "capability": f"filesystem.{args.operation}_file",
        "target": args.target,
        "operation": {
            "type": "write" if args.operation in ["create", "update"] else args.operation,
            "content": content_b64,
            "mode": args.mode or "0644"
        },
        "rationale": args.rationale or f"CLI mutation: {args.operation} {args.target}",
        "confidence": 1.0
    }
    
    response = httpx.post(
        f"{RARA_URL}/mutations/execute",
        params={"agent_id": args.agent_id},
        json=mutation,
        timeout=60
    )
    print(json.dumps(response.json(), indent=2))


def pending_mutations(args):
    """List pending mutations awaiting approval"""
    response = httpx.get(f"{RARA_URL}/mutations/pending", timeout=10)
    mutations = response.json()
    
    if not mutations:
        print("No pending mutations")
        return
    
    print(f"{'Mutation ID':<40} {'Capability':<25} {'Target'}")
    print("-" * 100)
    for m in mutations:
        print(f"{m['mutation_id']:<40} {m['capability']:<25} {m['target']}")


def approve_mutation(args):
    """Approve a pending mutation"""
    response = httpx.post(
        f"{RARA_URL}/mutations/approve",
        json={
            "mutation_id": args.mutation_id,
            "approval_token": args.token or "human-approved"
        },
        timeout=10
    )
    print(json.dumps(response.json(), indent=2))


def reject_mutation(args):
    """Reject a pending mutation"""
    response = httpx.post(
        f"{RARA_URL}/mutations/reject",
        json={
            "mutation_id": args.mutation_id,
            "reason": args.reason or "Rejected by human"
        },
        timeout=10
    )
    print(json.dumps(response.json(), indent=2))


def check_invariants(args):
    """Run invariant checks"""
    response = httpx.post(f"{RARA_URL}/invariants/check", timeout=60)
    data = response.json()
    
    print(f"All Passed: {data['all_passed']}")
    print()
    
    for result in data['results']:
        status = "✅" if result['passed'] else "❌"
        print(f"{status} {result['invariant']}")
        if result['violations']:
            for v in result['violations']:
                print(f"   - {v}")


def coordination_stats(args):
    """Get coordination statistics"""
    response = httpx.get(f"{RARA_URL}/coordination/stats", timeout=10)
    print(json.dumps(response.json(), indent=2))


def mutation_log(args):
    """Get mutation log"""
    response = httpx.get(f"{RARA_URL}/mutations/log", params={"limit": args.limit}, timeout=10)
    log = response.json()
    
    print(f"{'Timestamp':<24} {'Decision':<12} {'Reason'}")
    print("-" * 80)
    for entry in log:
        print(f"{entry['timestamp'][:23]:<24} {entry['decision']:<12} {entry['reason'][:40]}")


def main():
    global RARA_URL
    parser = argparse.ArgumentParser(
        description="RARA CLI - Resident Autonomous Runtime Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  rara status                          # Get system status
  rara freeze                          # Enter observe-only mode
  rara unfreeze                        # Enable mutations
  rara snapshots                       # List snapshots
  rara snapshot create                 # Create manual snapshot
  rara snapshot restore snap-0001      # Restore to snapshot
  rara agent register my-agent planner # Register agent
  rara agent caps my-agent             # Show agent capabilities
  rara invariants check                # Run invariant checks
  rara mutations pending               # List pending approvals
  rara mutations approve <id>          # Approve mutation
        """
    )
    
    parser.add_argument("--url", default=RARA_URL, help="RARA service URL")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Status
    subparsers.add_parser("status", help="Get RARA status")
    subparsers.add_parser("health", help="Check RARA health")
    
    # Control
    subparsers.add_parser("freeze", help="Freeze system")
    subparsers.add_parser("unfreeze", help="Unfreeze system")
    
    # Snapshots
    snap_parser = subparsers.add_parser("snapshots", help="List snapshots")
    snap_parser.add_argument("--limit", type=int, default=20, help="Number of snapshots")
    
    snap_sub = subparsers.add_parser("snapshot", help="Snapshot operations")
    snap_sub_parsers = snap_sub.add_subparsers(dest="snap_command")
    
    snap_create = snap_sub_parsers.add_parser("create", help="Create snapshot")
    snap_create.add_argument("--trigger", help="Trigger description")
    
    snap_restore = snap_sub_parsers.add_parser("restore", help="Restore snapshot")
    snap_restore.add_argument("snapshot_id", help="Snapshot ID to restore")
    snap_restore.add_argument("--reason", help="Reason for restore")
    
    # Agents
    agent_parser = subparsers.add_parser("agent", help="Agent operations")
    agent_sub = agent_parser.add_subparsers(dest="agent_command")
    
    agent_reg = agent_sub.add_parser("register", help="Register agent")
    agent_reg.add_argument("agent_id", help="Agent ID")
    agent_reg.add_argument("role", choices=["planner", "executor", "verifier", "auditor"])
    agent_reg.add_argument("--dsid", help="Agent DSID")
    agent_reg.add_argument("--public-key", help="Agent public key")
    
    agent_caps = agent_sub.add_parser("caps", help="Show capabilities")
    agent_caps.add_argument("agent_id", help="Agent ID")
    
    agent_stats = agent_sub.add_parser("stats", help="Show statistics")
    agent_stats.add_argument("agent_id", help="Agent ID")
    
    # Mutations
    mut_parser = subparsers.add_parser("mutations", help="Mutation operations")
    mut_sub = mut_parser.add_subparsers(dest="mut_command")
    
    mut_sub.add_parser("pending", help="List pending mutations")
    
    mut_approve = mut_sub.add_parser("approve", help="Approve mutation")
    mut_approve.add_argument("mutation_id", help="Mutation ID")
    mut_approve.add_argument("--token", help="Approval token")
    
    mut_reject = mut_sub.add_parser("reject", help="Reject mutation")
    mut_reject.add_argument("mutation_id", help="Mutation ID")
    mut_reject.add_argument("--reason", help="Rejection reason")
    
    mut_log = mut_sub.add_parser("log", help="Show mutation log")
    mut_log.add_argument("--limit", type=int, default=50, help="Number of entries")
    
    # Mutate file
    mutate_parser = subparsers.add_parser("mutate", help="Execute file mutation")
    mutate_parser.add_argument("operation", choices=["create", "update", "delete"])
    mutate_parser.add_argument("target", help="Target file path")
    mutate_parser.add_argument("--source", help="Source file for content")
    mutate_parser.add_argument("--agent-id", default="cli-agent", help="Agent ID")
    mutate_parser.add_argument("--mode", help="File mode (e.g., 0644)")
    mutate_parser.add_argument("--rationale", help="Reason for mutation")
    
    # Invariants
    inv_parser = subparsers.add_parser("invariants", help="Invariant operations")
    inv_sub = inv_parser.add_subparsers(dest="inv_command")
    inv_sub.add_parser("check", help="Run invariant checks")
    
    # Coordination
    subparsers.add_parser("coordination", help="Coordination statistics")
    
    args = parser.parse_args()
    
    if args.url:
        RARA_URL = args.url
    
    try:
        if args.command == "status":
            status(args)
        elif args.command == "health":
            health(args)
        elif args.command == "freeze":
            freeze(args)
        elif args.command == "unfreeze":
            unfreeze(args)
        elif args.command == "snapshots":
            list_snapshots(args)
        elif args.command == "snapshot":
            if args.snap_command == "create":
                create_snapshot(args)
            elif args.snap_command == "restore":
                restore_snapshot(args)
        elif args.command == "agent":
            if args.agent_command == "register":
                register_agent(args)
            elif args.agent_command == "caps":
                agent_capabilities(args)
            elif args.agent_command == "stats":
                agent_stats(args)
        elif args.command == "mutations":
            if args.mut_command == "pending":
                pending_mutations(args)
            elif args.mut_command == "approve":
                approve_mutation(args)
            elif args.mut_command == "reject":
                reject_mutation(args)
            elif args.mut_command == "log":
                mutation_log(args)
        elif args.command == "mutate":
            mutate_file(args)
        elif args.command == "invariants":
            if args.inv_command == "check":
                check_invariants(args)
        elif args.command == "coordination":
            coordination_stats(args)
        else:
            parser.print_help()
    except httpx.ConnectError:
        print(f"Error: Cannot connect to RARA at {RARA_URL}")
        print("Make sure the RARA service is running.")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"Error: {e.response.status_code} - {e.response.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()
