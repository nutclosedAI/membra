"""Membra Node — Main orchestrator for M5 Pro validator."""
import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import psutil

from membra_sdk.core.ledger import InternalLedger
from membra_sdk.core.yield_engine import YieldEngine
from membra_sdk.consensus.poy import ProofOfYieldConsensus


class MembraNode:
    """A single Membra validator node running on M5 Pro Mac.

    Architecture:
    1. File corpus scanner mines local files for yield potential
    2. YieldEngine estimates value from file content
    3. LLM validates batches and produces inference hashes
    4. ProofOfYieldConsensus requires 2/3 agreement on yield + inference
    5. InternalLedger records ops at 1M+ ops/sec (lock-free)
    6. Batched settlement to Solana devnet for public anchoring
    """

    def __init__(self, node_id: str = None, config_path: str = None):
        self.node_id = node_id or self._generate_node_id()
        self.config_path = config_path or os.path.expanduser("~/.membra/config.yaml")
        self.ledger = InternalLedger()
        self.yield_engine = YieldEngine()
        self.consensus = ProofOfYieldConsensus(agent_id=self.node_id)
        self.running = False
        self.stats = {
            "ops_processed": 0,
            "batches_finalized": 0,
            "yield_estimated": 0.0,
            "files_scanned": 0,
        }

    def _generate_node_id(self) -> str:
        machine = f"{os.uname().nodename}-{psutil.cpu_count()}-{psutil.virtual_memory().total}"
        return hashlib.sha256(machine.encode()).hexdigest()[:12]

    async def start(self):
        """Start all subsystems."""
        self.running = True
        print("=" * 70)
        print("  MEMBRA NODE — Proof-of-Yield Validator")
        print(f"  Node: {self.node_id}")
        print(f"  Machine: M5 Pro Mac | Cores: {psutil.cpu_count()}")
        print("=" * 70)

        await asyncio.gather(
            self._file_mining_loop(),
            self._consensus_loop(),
            self._settlement_loop(),
            self._status_loop(),
        )

    async def _file_mining_loop(self):
        """Scan files, estimate yield, queue operations."""
        scan_paths = [
            os.path.expanduser("~/Documents"),
            os.path.expanduser("~/Downloads"),
            os.path.expanduser("~/Projects"),
        ]

        while self.running:
            try:
                for path in scan_paths:
                    if not os.path.exists(path):
                        continue
                    for root, _, files in os.walk(path):
                        for fname in files[:10]:  # Rate limit
                            if fname.endswith((".rs", ".sol", ".go", ".py", ".js", ".ts")):
                                fpath = os.path.join(root, fname)
                                try:
                                    with open(fpath, "r", errors="ignore") as f:
                                        content = f.read()[:2000]

                                    # Estimate yield from file
                                    yield_est = self.yield_engine.estimate(fpath, content)

                                    # Create operation
                                    op = {
                                        "type": "file_yield",
                                        "file": fname,
                                        "path": fpath,
                                        "size": len(content),
                                        "yield_estimate": yield_est,
                                        "timestamp": time.time(),
                                    }
                                    self.ledger.submit(op)
                                    self.stats["ops_processed"] += 1
                                    self.stats["files_scanned"] += 1
                                    self.stats["yield_estimated"] += yield_est

                                except Exception:
                                    pass
                await asyncio.sleep(5)
            except Exception as e:
                print(f"[MINING] Error: {e}")
                await asyncio.sleep(10)

    async def _consensus_loop(self):
        """Form batches, run proof-of-yield consensus."""
        while self.running:
            try:
                batch = self.ledger.drain_batch(100)
                if len(batch) >= 10:
                    # Form state root from batch
                    root = hashlib.sha256(
                        json.dumps(batch, sort_keys=True).encode()
                    ).hexdigest()

                    # Calculate total yield in batch
                    total_yield = sum(op.get("yield_estimate", 0) for op in batch)

                    # Run proof-of-yield consensus
                    result = await self.consensus.run_poy_round(
                        state_root=root,
                        batch=batch,
                        total_yield=total_yield,
                    )

                    if result.finalized:
                        self.stats["batches_finalized"] += 1
                        print(f"[CONSENSUS] Batch finalized — yield: {total_yield:.4f} — root: {root[:16]}...")

                await asyncio.sleep(3)
            except Exception as e:
                print(f"[CONSENSUS] Error: {e}")
                await asyncio.sleep(5)

    async def _settlement_loop(self, interval: int = 30):
        """Anchor finalized batches to Solana devnet."""
        while self.running:
            await asyncio.sleep(interval)
            # In production: send memo tx with finalized root
            # For now, log the intent
            if self.stats["batches_finalized"] > 0:
                print(f"[SETTLE] Would anchor {self.stats['batches_finalized']} batches to Solana")

    async def _status_loop(self):
        """Print periodic status."""
        while self.running:
            await asyncio.sleep(10)
            print(
                f"[STATUS] Ops: {self.stats['ops_processed']} | "
                f"Finalized: {self.stats['batches_finalized']} | "
                f"Yield: {self.stats['yield_estimated']:.4f} | "
                f"Files: {self.stats['files_scanned']}"
            )

    def get_status(self) -> Dict:
        return {
            "node_id": self.node_id,
            "running": self.running,
            **self.stats,
            "ledger_pending": self.ledger.pending_count(),
            "consensus": self.consensus.get_stats(),
        }
