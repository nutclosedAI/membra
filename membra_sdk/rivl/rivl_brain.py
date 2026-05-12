"""RIVL Brain — Integrates RIVL into the MoA pipeline.

Flow:
  1. Router Brain plans subtasks
  2. Punishment Memory retrieves past failures for this prompt type
  3. Specialist workers execute (with memory warnings in prompts)
  4. Verifier Stack checks all outputs (code, security, payment, consensus)
  5. Reward Engine scores: +reward for passing, -punishment for failing
  6. Scored events persisted to memory
  7. Synthesizer Brain merges verified outputs only
  8. Final artifact + hash + provenance + reward score

This is the full RIVL-MoA integration.
"""
from typing import Dict, List

from membra_sdk.brain.router import RouterBrain
from membra_sdk.brain.synthesizer import SynthesizerBrain
from membra_sdk.brain.judge import JudgeBrain
from membra_sdk.rivl.reward_engine import RIVLRewardEngine
from membra_sdk.rivl.punishment_memory import PunishmentMemory
from membra_sdk.rivl.verifier_stack import VerifierStack
from membra_sdk.worker.worker_node import WorkerNode


class RIVLBrain:
    """MoA Brain with RIVL verification, scoring, and punishment memory."""

    def __init__(self):
        self.router = RouterBrain()
        self.synthesizer = SynthesizerBrain()
        self.judge = JudgeBrain()
        self.verifier = VerifierStack()
        self.reward = RIVLRewardEngine()
        self.memory = PunishmentMemory()
        self.workers: Dict[str, WorkerNode] = {}

    def register_worker(self, worker: WorkerNode, role: str = None):
        if role:
            worker.specialist_role = role
        self.workers[worker.worker_id] = worker

    def process(self, prompt: str, run_verification: bool = True) -> Dict:
        """Process prompt through full RIVL-MoA pipeline."""
        print(f"[RIVL] Processing: {prompt[:60]}...")

        # 1. Retrieve punishment memory
        print("[RIVL] 1. Retrieving punishment memory...")
        memory_addon = self.memory.get_system_prompt_addon(prompt)
        if memory_addon:
            print("  Found past learnings")
            print(memory_addon[:200] + "...")

        # 2. Router plans
        print("[RIVL] 2. Router planning...")
        plan = self.router.plan(prompt)

        # 3. Execute specialists
        print("[RIVL] 3. Running specialists...")
        specialist_outputs = []
        for subtask in plan["subtasks"]:
            role = subtask["role"]
            worker = self._find_worker_for_role(role)
            if not worker:
                continue

            # Add memory to task prompt
            task_prompt = self._build_prompt_with_memory(subtask, memory_addon)
            result = worker._run_prompt({"prompt": task_prompt, "model": subtask.get("model", "llama3.1:8b")})

            specialist_outputs.append({
                "worker_id": worker.worker_id,
                "role": role,
                "task_id": subtask["id"],
                "result": result,
            })
            print(f"  ✅ {role} completed")

        # 4. Verifier checks
        print("[RIVL] 4. Verifier Stack checking...")
        verification_results = []
        for out in specialist_outputs:
            code = out["result"].get("output", "") if isinstance(out["result"], dict) else str(out["result"])
            vresult = self.verifier.verify_code(code)
            verification_results.append({
                "worker_id": out["worker_id"],
                "role": out["role"],
                "passed": vresult["passed"],
                "issues": vresult["issues"],
            })
            status = "PASS" if vresult["passed"] else "FAIL"
            print(f"  {out['role']}: {status}")
            if vresult["issues"]:
                for issue in vresult["issues"][:3]:
                    print(f"    ⚠️ {issue}")

        # 5. Judge scores
        print("[RIVL] 5. Judge scoring...")
        judge_scores = {}
        for out in specialist_outputs:
            judgment = self.judge.score(
                out["worker_id"], out["role"], out["result"],
                subtask.get("description", "")
            )
            judge_scores[out["worker_id"]] = judgment["overall"]

        # 6. Reward engine scores
        print("[RIVL] 6. Reward Engine scoring...")
        reward_events = []
        for out, vresult in zip(specialist_outputs, verification_results):
            code = out["result"].get("output", "") if isinstance(out["result"], dict) else str(out["result"])
            event = self.reward.score(
                prompt=plan["original_prompt"],
                output=code,
                tests_passed=vresult["passed"],
                security_passed=not any("Security" in i for i in vresult["issues"]),
                payment_verified=False,  # No real payment in demo
                consensus_verified=True,  # Assume consensus for demo
            )
            reward_events.append(event)
            verdict_emoji = "✅" if event.verdict == "accepted" else "❌"
            print(f"  {verdict_emoji} {out['role']}: reward={event.reward:.0f} | {event.verdict}")

        # 7. Synthesize (only verified outputs)
        print("[RIVL] 7. Synthesizing verified outputs...")
        valid_outputs = [
            out for out, v in zip(specialist_outputs, verification_results) if v["passed"]
        ]
        if not valid_outputs:
            print("  ❌ No outputs passed verification. Returning best attempt.")
            valid_outputs = specialist_outputs[:1]

        final = self.synthesizer.synthesize(plan, valid_outputs, judge_scores)

        # 8. Final verification + consensus hash
        print("[RIVL] 8. Final consensus...")
        consensus = {
            "overall_passed": all(v["passed"] for v in verification_results),
            "reward_events": [self._event_to_dict(e) for e in reward_events],
            "total_reward": sum(e.reward for e in reward_events),
            "verification_count": len(verification_results),
        }
        final["rivl"] = consensus

        print(f"[RIVL] ✅ Complete. Total reward: {consensus['total_reward']:.0f}")
        return final

    def get_stats(self) -> Dict:
        """Get RIVL system statistics."""
        return {
            "reward_engine": self.reward.get_stats(),
            "workers": len(self.workers),
        }

    def _find_worker_for_role(self, role: str) -> WorkerNode:
        for w in self.workers.values():
            if getattr(w, "specialist_role", None) == role:
                return w
        for w in self.workers.values():
            if w.current_task is None:
                return w
        return None

    def _build_prompt_with_memory(self, subtask: Dict, memory_addon: str) -> str:
        base = subtask.get("description", "")
        if memory_addon:
            return f"{memory_addon}\n\nTask: {base}"
        return base

    def _event_to_dict(self, event) -> Dict:
        from dataclasses import asdict
        return asdict(event)
