"""Router Brain — Decides which specialist agent handles each part of a task.

The router analyzes the prompt and produces a plan:
  1. Decompose the task into subtasks
  2. Assign each subtask to the best specialist worker
  3. Define dependencies between subtasks
  4. Set quality thresholds for synthesis
"""
import json
import time
from typing import Dict, List


class RouterBrain:
    """Routes user prompts to specialist workers based on task decomposition."""

    # Specialist roles and their capabilities
    ROLES = {
        "planner": "Decomposes tasks, creates execution plans, defines dependencies",
        "coder": "Writes code, builds applications, creates scripts and modules",
        "security": "Reviews code for secrets, vulnerabilities, unsafe patterns",
        "tester": "Writes tests, runs test suites, reports coverage and failures",
        "docs": "Writes README, API docs, comments, usage examples",
        "researcher": "Searches knowledge, summarizes, fact-checks, finds examples",
        "critic": "Reviews outputs, scores quality, identifies flaws",
    }

    # Model-to-role mapping (can be customized per deployment)
    DEFAULT_MODELS = {
        "planner": "llama3.1:8b",
        "coder": "qwen2.5-coder",
        "security": "deepseek-coder:1.3b",
        "tester": "llama3.1:8b",
        "docs": "phi3:mini",
        "researcher": "llama3.1:8b",
        "critic": "deepseek-r1:latest",
    }

    def __init__(self, role_models: Dict[str, str] = None):
        self.role_models = role_models or self.DEFAULT_MODELS.copy()

    def plan(self, prompt: str) -> Dict:
        """Decompose prompt into a plan with specialist assignments."""
        # Deterministic plan based on prompt keywords
        plan = self._analyze_prompt(prompt)

        return {
            "plan_id": f"plan-{int(time.time())}",
            "original_prompt": prompt,
            "subtasks": plan["subtasks"],
            "worker_assignments": plan["assignments"],
            "dependencies": plan["dependencies"],
            "quality_threshold": plan.get("quality_threshold", 0.75),
            "estimated_steps": len(plan["subtasks"]),
            "created_at": time.time(),
        }

    def _analyze_prompt(self, prompt: str) -> Dict:
        """Analyze prompt and decompose into subtasks.

        In production this would use an LLM. For now, use keyword-based routing.
        """
        prompt_lower = prompt.lower()
        subtasks = []
        assignments = {}
        dependencies = {}

        # Detect task types from keywords
        needs_code = any(k in prompt_lower for k in [
            "code", "build", "app", "bot", "script", "function",
            "program", "deploy", "api", "smart contract",
        ])
        needs_tests = any(k in prompt_lower for k in [
            "test", "pytest", "unit test", "integration",
        ])
        needs_security = any(k in prompt_lower for k in [
            "secure", "audit", "vulnerability", "secret", "key",
            "password", "token", "webhook",
        ])
        needs_docs = any(k in prompt_lower for k in [
            "readme", "documentation", "docstring", "comment",
            "explain", "tutorial",
        ])
        needs_research = any(k in prompt_lower for k in [
            "research", "find", "search", "compare", "analyze",
            "what is", "how does", "explain",
        ])

        # Step 1: Always start with planning
        subtasks.append({
            "id": "plan",
            "description": "Create execution plan for the task",
            "role": "planner",
            "model": self.role_models["planner"],
        })
        assignments["plan"] = "planner"

        step = 1

        # Step 2: Research if needed
        if needs_research:
            subtasks.append({
                "id": f"step-{step}",
                "description": "Research topic and find relevant information",
                "role": "researcher",
                "model": self.role_models["researcher"],
            })
            assignments[f"step-{step}"] = "researcher"
            dependencies[f"step-{step}"] = ["plan"]
            step += 1

        # Step 3: Code if needed
        if needs_code:
            subtasks.append({
                "id": f"step-{step}",
                "description": "Write the main code/artifact",
                "role": "coder",
                "model": self.role_models["coder"],
            })
            assignments[f"step-{step}"] = "coder"
            dependencies[f"step-{step}"] = ["plan"] + ([f"step-{step-1}"] if needs_research else [])
            code_step = step
            step += 1

            # Step 4: Security review
            if needs_security:
                subtasks.append({
                    "id": f"step-{step}",
                    "description": "Review code for security issues",
                    "role": "security",
                    "model": self.role_models["security"],
                })
                assignments[f"step-{step}"] = "security"
                dependencies[f"step-{step}"] = [f"step-{code_step}"]
                step += 1

            # Step 5: Tests
            if needs_tests:
                subtasks.append({
                    "id": f"step-{step}",
                    "description": "Write and run tests",
                    "role": "tester",
                    "model": self.role_models["tester"],
                })
                assignments[f"step-{step}"] = "tester"
                dependencies[f"step-{step}"] = [f"step-{code_step}"]
                step += 1

            # Step 6: Documentation
            if needs_docs:
                subtasks.append({
                    "id": f"step-{step}",
                    "description": "Write documentation and README",
                    "role": "docs",
                    "model": self.role_models["docs"],
                })
                assignments[f"step-{step}"] = "docs"
                dependencies[f"step-{step}"] = [f"step-{code_step}"]
                step += 1

        # If no specific type detected, just do a general answer
        if not subtasks or len(subtasks) == 1:
            subtasks.append({
                "id": f"step-{step}",
                "description": "Generate comprehensive answer",
                "role": "researcher",
                "model": self.role_models["researcher"],
            })
            assignments[f"step-{step}"] = "researcher"
            dependencies[f"step-{step}"] = ["plan"]

        # Final step: Critic review
        final_step = len(subtasks)
        subtasks.append({
            "id": f"step-{final_step}",
            "description": "Review all outputs and score quality",
            "role": "critic",
            "model": self.role_models["critic"],
        })
        assignments[f"step-{final_step}"] = "critic"
        dependencies[f"step-{final_step}"] = [s["id"] for s in subtasks[:-1]]

        return {
            "subtasks": subtasks,
            "assignments": assignments,
            "dependencies": dependencies,
            "quality_threshold": 0.75,
        }

    def get_worker_roles(self) -> Dict[str, str]:
        """Return available roles and their models."""
        return self.role_models
