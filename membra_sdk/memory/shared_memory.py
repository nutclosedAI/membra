"""Shared Memory Layer — All MoA agents read/write to the same memory.

Instead of shared tensors (impossible over WiFi), we use shared memory:
  - SQLite database for structured data
  - JSON artifact store for files
  - Vector search for embeddings
  - Task history for provenance
  - Worker reputation scores
  - User preferences

Every worker reads/writes to the same memory layer.
Worker A learns something → stores memory → Worker B can use it.
"""
import hashlib
import json
import os
import sqlite3
import time
from typing import Dict, List, Optional


class SharedMemory:
    """SQLite-based shared memory for all MoA agents."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.expanduser("~/.membra/shared_memory.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize SQLite tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    job_id TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_hash TEXT,
                    timestamp REAL NOT NULL,
                    job_id TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS worker_reputation (
                    worker_id TEXT PRIMARY KEY,
                    total_tasks INTEGER DEFAULT 0,
                    successful_tasks INTEGER DEFAULT 0,
                    avg_score REAL DEFAULT 0.0,
                    safety_violations INTEGER DEFAULT 0,
                    last_active REAL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_agent ON agent_memory(agent_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_type ON agent_memory(memory_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_job ON task_history(job_id)
            """)
            conn.commit()

    def store(self, agent_id: str, memory_type: str, key: str,
              value: any, job_id: str = None):
        """Store a memory entry."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO agent_memory (agent_id, memory_type, key, value, timestamp, job_id) VALUES (?, ?, ?, ?, ?, ?)",
                (agent_id, memory_type, key, json.dumps(value), time.time(), job_id),
            )
            conn.commit()

    def retrieve(self, agent_id: str = None, memory_type: str = None,
                   key: str = None, limit: int = 100) -> List[Dict]:
        """Retrieve memory entries with filters."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM agent_memory WHERE 1=1"
            params = []
            if agent_id:
                query += " AND agent_id = ?"
                params.append(agent_id)
            if memory_type:
                query += " AND memory_type = ?"
                params.append(memory_type)
            if key:
                query += " AND key = ?"
                params.append(key)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [
                {
                    "id": r["id"],
                    "agent_id": r["agent_id"],
                    "memory_type": r["memory_type"],
                    "key": r["key"],
                    "value": json.loads(r["value"]),
                    "timestamp": r["timestamp"],
                    "job_id": r["job_id"],
                }
                for r in rows
            ]

    def log_task(self, task_id: str, agent_id: str, role: str,
                 status: str, result_hash: str = None, job_id: str = None):
        """Log a task execution."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO task_history (task_id, agent_id, role, status, result_hash, timestamp, job_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (task_id, agent_id, role, status, result_hash, time.time(), job_id),
            )
            conn.commit()

    def update_reputation(self, worker_id: str, score: float, success: bool,
                          safety_violation: bool = False):
        """Update worker reputation."""
        with sqlite3.connect(self.db_path) as conn:
            # Try update first
            conn.execute(
                """UPDATE worker_reputation SET
                    total_tasks = total_tasks + 1,
                    successful_tasks = successful_tasks + ?,
                    avg_score = (avg_score * total_tasks + ?) / (total_tasks + 1),
                    safety_violations = safety_violations + ?,
                    last_active = ?
                WHERE worker_id = ?""",
                (1 if success else 0, score, 1 if safety_violation else 0, time.time(), worker_id),
            )
            # If no rows affected, insert
            if conn.total_changes == 0:
                conn.execute(
                    "INSERT INTO worker_reputation (worker_id, total_tasks, successful_tasks, avg_score, safety_violations, last_active) VALUES (?, 1, ?, ?, ?, ?)",
                    (worker_id, 1 if success else 0, score, 1 if safety_violation else 0, time.time()),
                )
            conn.commit()

    def get_reputation(self, worker_id: str) -> Optional[Dict]:
        """Get worker reputation."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM worker_reputation WHERE worker_id = ?",
                (worker_id,),
            ).fetchone()
            if row:
                return dict(row)
            return None

    def get_stats(self) -> Dict:
        """Memory layer statistics."""
        with sqlite3.connect(self.db_path) as conn:
            total_memories = conn.execute("SELECT COUNT(*) FROM agent_memory").fetchone()[0]
            total_tasks = conn.execute("SELECT COUNT(*) FROM task_history").fetchone()[0]
            total_workers = conn.execute("SELECT COUNT(*) FROM worker_reputation").fetchone()[0]
            avg_score = conn.execute("SELECT AVG(avg_score) FROM worker_reputation").fetchone()[0]

            return {
                "total_memories": total_memories,
                "total_tasks_logged": total_tasks,
                "total_workers": total_workers,
                "average_reputation": round(avg_score or 0, 3),
            }


class ArtifactStore:
    """File-based artifact store with hash verification."""

    def __init__(self, storage_path: str = None):
        self.storage_path = storage_path or os.path.expanduser("~/.membra/artifacts")
        os.makedirs(self.storage_path, exist_ok=True)

    def store(self, job_id: str, filename: str, content: str) -> str:
        """Store an artifact and return its hash."""
        job_dir = os.path.join(self.storage_path, job_id)
        os.makedirs(job_dir, exist_ok=True)

        path = os.path.join(job_dir, filename)
        with open(path, "w") as f:
            f.write(content)

        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Write hash manifest
        manifest = os.path.join(job_dir, "manifest.json")
        manifest_data = {}
        if os.path.exists(manifest):
            with open(manifest) as f:
                manifest_data = json.load(f)
        manifest_data[filename] = content_hash

        with open(manifest, "w") as f:
            json.dump(manifest_data, f, indent=2)

        return content_hash

    def retrieve(self, job_id: str, filename: str) -> Optional[str]:
        """Retrieve an artifact."""
        path = os.path.join(self.storage_path, job_id, filename)
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return f.read()

    def verify(self, job_id: str, filename: str) -> bool:
        """Verify artifact hash matches manifest."""
        path = os.path.join(self.storage_path, job_id, filename)
        manifest = os.path.join(self.storage_path, job_id, "manifest.json")

        if not os.path.exists(path) or not os.path.exists(manifest):
            return False

        with open(manifest) as f:
            manifest_data = json.load(f)

        expected_hash = manifest_data.get(filename, "")
        with open(path, "rb") as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest()

        return expected_hash == actual_hash
