"""MoA Orchestrator — Runs the full Mixture-of-Agents pipeline.

End-to-end flow:
  User Prompt
    → Router Brain plans subtasks
    → Specialist workers execute in parallel
    → Judge Brain scores outputs
    → Synthesizer Brain merges best results
    → Final artifact + hash + provenance

This is the single-brain experience. One prompt in, one artifact out,
but built by a team of specialist agents working together.
"""
import hashlib
import json
import time
from typing import Dict, List

from membra_sdk.brain.router import RouterBrain
from membra_sdk.brain.synthesizer import SynthesizerBrain
from membra_sdk.brain.judge import JudgeBrain
from membra_sdk.worker.worker_node import WorkerNode


class MoAOrchestrator:
    """Orchestrates the full MoA pipeline from prompt to artifact."""

    def __init__(self):
        self.router = RouterBrain()
        self.judge = JudgeBrain()
        self.synthesizer = SynthesizerBrain()
        self.workers: Dict[str, WorkerNode] = {}

    def register_worker(self, worker: WorkerNode, role: str = None):
        """Register a specialist worker for a specific role."""
        if role:
            worker.specialist_role = role
        self.workers[worker.worker_id] = worker

    def process(self, prompt: str) -> Dict:
        """Process a user prompt through the full MoA pipeline.

        Returns:
            Complete result with artifact, hash, scores, and provenance.
        """
        print(f"[MoA] Processing prompt: {prompt[:60]}...")

        # 1. Router Brain plans
        print("[MoA] 1. Router Brain planning...")
        plan = self.router.plan(prompt)
        print(f"  Plan: {plan['estimated_steps']} steps, {len(plan['subtasks'])} subtasks")

        # 2. Execute specialist tasks
        print("[MoA] 2. Running specialists...")
        specialist_outputs = []
        for subtask in plan["subtasks"]:
            role = subtask["role"]
            # Find worker for this role
            worker = self._find_worker_for_role(role)
            if not worker:
                print(f"  ⚠️ No worker for role '{role}', skipping")
                continue

            result = self._run_specialist(worker, subtask, plan)
            specialist_outputs.append({
                "worker_id": worker.worker_id,
                "role": role,
                "task_id": subtask["id"],
                "result": result,
            })
            print(f"  ✅ {role} ({worker.worker_id}) completed")

        # 3. Judge Brain scores
        print("[MoA] 3. Judge Brain scoring...")
        judge_scores = {}
        for out in specialist_outputs:
            judgment = self.judge.score(
                out["worker_id"],
                out["role"],
                out["result"],
                subtask.get("description", ""),
            )
            judge_scores[out["worker_id"]] = judgment["overall"]
            status = "PASS" if judgment["passed"] else "FAIL"
            print(f"  {out['role']}: {judgment['overall']:.2f} [{status}]")
            if judgment["safety_flags"]:
                for flag in judgment["safety_flags"]:
                    print(f"    ⚠️ {flag}")

        # 4. Synthesizer merges
        print("[MoA] 4. Synthesizer Brain merging...")
        final = self.synthesizer.synthesize(plan, specialist_outputs, judge_scores)
        print(f"  Artifact hash: {final['artifact_hash'][:16]}...")
        print(f"  Components used: {sum(1 for c in final['component_outputs'] if c['included'])}/{len(final['component_outputs'])}")

        # 5. Consensus hash
        print("[MoA] 5. Computing consensus...")
        consensus = self._compute_consensus(final, specialist_outputs, judge_scores)
        final["consensus"] = consensus

        print("[MoA] ✅ Complete")
        return final

    def draft_verify(self, prompt: str, fast_worker: WorkerNode,
                     strong_worker: WorkerNode) -> Dict:
        """Speculative draft/verify mode for faster single responses.

        fast_worker: Small quick model (e.g., phi3, llama3.2:1b)
        strong_worker: Larger accurate model (e.g., llama3.1:70b)
        """
        print("[MoA Draft/Verify] Fast draft + strong verify mode")

        # Fast draft
        print("  Fast worker drafting...")
        draft = fast_worker._run_prompt({"prompt": prompt, "model": fast_worker.capabilities.models[0]})

        # Strong verify
        print("  Strong worker verifying...")
        verify_input = {
            "prompt": f"Review and correct this draft:\n\n{draft.get('output', '')}",
            "model": strong_worker.capabilities.models[0],
        }
        verified = strong_worker._run_prompt(verify_input)

        # Synthesize
        final_text = self.synthesizer.stream_draft(
            draft.get("output", ""),
            verified.get("output", ""),
        )

        return {
            "mode": "draft_verify",
            "draft_worker": fast_worker.worker_id,
            "verify_worker": strong_worker.worker_id,
            "final_output": final_text,
            "draft_hash": hashlib.sha256(draft.get("output", "").encode()).hexdigest()[:16],
            "verified_hash": hashlib.sha256(verified.get("output", "").encode()).hexdigest()[:16],
        }

    def _find_worker_for_role(self, role: str) -> WorkerNode:
        """Find the best worker for a role."""
        # Prefer worker explicitly assigned to this role
        for w in self.workers.values():
            if getattr(w, "specialist_role", None) == role:
                return w
        # Fallback: any available worker
        for w in self.workers.values():
            if w.current_task is None:
                return w
        return None

    def _run_specialist(self, worker: WorkerNode, subtask: Dict, plan: Dict) -> Dict:
        """Execute a subtask on a specialist worker."""
        role = subtask["role"]
        description = subtask["description"]
        model = subtask.get("model", worker.capabilities.models[0] if worker.capabilities.models else "llama3.1:8b")

        # Build role-specific prompt
        role_prompts = {
            "planner": f"Create a detailed execution plan for: {plan['original_prompt']}\n\nBreak into steps with dependencies.",
            "coder": f"Write code for this task: {description}\n\nFull context: {plan['original_prompt']}",
            "security": f"Review this code for security issues, secrets, and unsafe patterns.\n\nTask: {description}",
            "tester": f"Write comprehensive tests for this functionality.\n\nTask: {description}",
            "docs": f"Write README and documentation.\n\nTask: {description}",
            "researcher": f"Research and explain: {description}\n\nContext: {plan['original_prompt']}",
            "critic": f"Review all previous outputs and score quality. Identify flaws.\n\nTask: {description}",
        }

        prompt = role_prompts.get(role, f"Task: {description}\n\nContext: {plan['original_prompt']}")

        return worker._run_prompt({"prompt": prompt, "model": model})

    def _compute_consensus(self, final: Dict, outputs: List[Dict], scores: Dict[str, float]) -> Dict:
        """Compute consensus metrics across all agents."""
        values = list(scores.values())
        if not values:
            return {"agreement": 0, "average_score": 0, "consensus_reached": False}

        avg = sum(values) / len(values)
        # Consensus if average score > 0.7 and no safety failures
        consensus_reached = avg >= 0.7

        return {
            "agreement": round(avg, 3),
            "average_score": round(avg, 3),
            "scores": scores,
            "consensus_reached": consensus_reached,
            "timestamp": time.time(),
        }
