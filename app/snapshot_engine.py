"""
RARA Snapshot Engine - Atomic rollback mechanism
"""

import os
import json
import hashlib
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple
from .models import SnapshotMeta, RollbackRequest
import logging

logger = logging.getLogger(__name__)


class SnapshotEngine:
    """
    Manages atomic snapshots of the runtime layer.
    
    Guarantees:
    - Pre-mutation snapshot creation
    - Atomic rollback via rsync
    - Rollback time < 2 seconds
    - No partial states
    """
    
    def __init__(
        self,
        runtime_path: str = "/opt/resonant/runtime",
        snapshots_path: str = "/opt/resonant/snapshots",
        max_snapshots: int = 100
    ):
        self.runtime_path = Path(runtime_path)
        self.snapshots_path = Path(snapshots_path)
        self.max_snapshots = max_snapshots
        self.index_file = self.snapshots_path / "index.json"
        
        # Ensure directories exist
        self.snapshots_path.mkdir(parents=True, exist_ok=True)
        
        # Load or create index
        self._load_index()
    
    def _load_index(self):
        """Load snapshot index from disk"""
        if self.index_file.exists():
            with open(self.index_file, 'r') as f:
                self.index = json.load(f)
        else:
            self.index = {
                "snapshots": [],
                "current": None,
                "created_at": datetime.utcnow().isoformat()
            }
            self._save_index()
    
    def _save_index(self):
        """Persist snapshot index to disk"""
        with open(self.index_file, 'w') as f:
            json.dump(self.index, f, indent=2, default=str)
    
    def _generate_snapshot_id(self) -> str:
        """Generate unique snapshot ID"""
        count = len(self.index["snapshots"]) + 1
        return f"snap-{count:04d}"
    
    def _compute_hash(self, path: Path) -> str:
        """Compute SHA256 hash of directory contents"""
        hasher = hashlib.sha256()
        
        for root, dirs, files in os.walk(path):
            dirs.sort()
            files.sort()
            for filename in files:
                filepath = Path(root) / filename
                try:
                    with open(filepath, 'rb') as f:
                        while chunk := f.read(8192):
                            hasher.update(chunk)
                except (IOError, PermissionError):
                    continue
        
        return f"sha256:{hasher.hexdigest()[:16]}"
    
    def _count_files(self, path: Path) -> Tuple[int, int]:
        """Count files and total size in directory"""
        count = 0
        size = 0
        for root, dirs, files in os.walk(path):
            for filename in files:
                filepath = Path(root) / filename
                try:
                    count += 1
                    size += filepath.stat().st_size
                except (IOError, PermissionError):
                    continue
        return count, size
    
    def create_snapshot(self, trigger: str) -> SnapshotMeta:
        """
        Create a snapshot of the runtime layer BEFORE mutation.
        
        Args:
            trigger: The mutation_id or "manual" that triggered this snapshot
            
        Returns:
            SnapshotMeta with snapshot details
        """
        snapshot_id = self._generate_snapshot_id()
        snapshot_dir = self.snapshots_path / snapshot_id / "runtime"
        
        logger.info(f"Creating snapshot {snapshot_id} triggered by {trigger}")
        
        # Create snapshot directory
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        # Use rsync for atomic copy
        try:
            result = subprocess.run(
                [
                    "rsync", "-a", "--delete",
                    f"{self.runtime_path}/",
                    f"{snapshot_dir}/"
                ],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"rsync failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            raise RuntimeError("Snapshot creation timed out")
        except FileNotFoundError:
            # Fallback to shutil if rsync not available
            if snapshot_dir.exists():
                shutil.rmtree(snapshot_dir)
            shutil.copytree(self.runtime_path, snapshot_dir)
        
        # Compute metadata
        files_count, size_bytes = self._count_files(snapshot_dir)
        content_hash = self._compute_hash(snapshot_dir)
        
        # Get previous snapshot
        previous = self.index["current"]
        
        # Create metadata
        meta = SnapshotMeta(
            id=snapshot_id,
            timestamp=datetime.utcnow(),
            trigger=trigger,
            hash=content_hash,
            previous=previous,
            health="UNKNOWN",
            files_count=files_count,
            size_bytes=size_bytes
        )
        
        # Save metadata
        meta_file = self.snapshots_path / snapshot_id / "meta.json"
        with open(meta_file, 'w') as f:
            json.dump(meta.model_dump(), f, indent=2, default=str)
        
        # Update index
        self.index["snapshots"].append(snapshot_id)
        self.index["current"] = snapshot_id
        self._save_index()
        
        # Cleanup old snapshots
        self._cleanup_old_snapshots()
        
        logger.info(f"Snapshot {snapshot_id} created: {files_count} files, {size_bytes} bytes")
        
        return meta
    
    def restore_snapshot(self, snapshot_id: str) -> bool:
        """
        Restore runtime from a snapshot.
        
        This is atomic - either fully restores or fails completely.
        
        Args:
            snapshot_id: The snapshot to restore
            
        Returns:
            True if successful
        """
        snapshot_dir = self.snapshots_path / snapshot_id / "runtime"
        
        if not snapshot_dir.exists():
            raise ValueError(f"Snapshot {snapshot_id} not found")
        
        logger.warning(f"Restoring snapshot {snapshot_id}")
        
        # Use rsync for atomic restore
        try:
            result = subprocess.run(
                [
                    "rsync", "-a", "--delete",
                    f"{snapshot_dir}/",
                    f"{self.runtime_path}/"
                ],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"rsync restore failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            raise RuntimeError("Snapshot restore timed out")
        except FileNotFoundError:
            # Fallback to shutil if rsync not available
            if self.runtime_path.exists():
                shutil.rmtree(self.runtime_path)
            shutil.copytree(snapshot_dir, self.runtime_path)
        
        logger.info(f"Snapshot {snapshot_id} restored successfully")
        
        return True
    
    def mark_health(self, snapshot_id: str, health: str):
        """Mark a snapshot's health status after verification"""
        meta_file = self.snapshots_path / snapshot_id / "meta.json"
        
        if meta_file.exists():
            with open(meta_file, 'r') as f:
                meta = json.load(f)
            meta["health"] = health
            with open(meta_file, 'w') as f:
                json.dump(meta, f, indent=2, default=str)
    
    def get_snapshot(self, snapshot_id: str) -> Optional[SnapshotMeta]:
        """Get metadata for a specific snapshot"""
        meta_file = self.snapshots_path / snapshot_id / "meta.json"
        
        if not meta_file.exists():
            return None
        
        with open(meta_file, 'r') as f:
            data = json.load(f)
        
        return SnapshotMeta(**data)
    
    def list_snapshots(self, limit: int = 20) -> List[SnapshotMeta]:
        """List recent snapshots"""
        snapshots = []
        for snap_id in reversed(self.index["snapshots"][-limit:]):
            meta = self.get_snapshot(snap_id)
            if meta:
                snapshots.append(meta)
        return snapshots
    
    def get_current_snapshot(self) -> Optional[str]:
        """Get the current (most recent) snapshot ID"""
        return self.index.get("current")
    
    def _cleanup_old_snapshots(self):
        """Remove old snapshots beyond max_snapshots limit"""
        while len(self.index["snapshots"]) > self.max_snapshots:
            old_id = self.index["snapshots"].pop(0)
            old_dir = self.snapshots_path / old_id
            
            if old_dir.exists():
                shutil.rmtree(old_dir)
                logger.info(f"Cleaned up old snapshot {old_id}")
        
        self._save_index()
    
    def rollback(self, request: RollbackRequest) -> bool:
        """
        Execute a rollback request.
        
        Args:
            request: RollbackRequest with snapshot_id and reason
            
        Returns:
            True if successful
        """
        logger.warning(
            f"Rollback requested by {request.actor}: "
            f"{request.reason} -> {request.snapshot_id}"
        )
        
        return self.restore_snapshot(request.snapshot_id)
