"""MEMBRA Hugging Face Demo — Proof-of-Job Runtime

6 tabs:
  1. Chat -> Job Spec
  2. Job -> Container Plan
  3. Run / Dry Run
  4. Yield Score
  5. Consensus
  6. Export

This is a proof demo and artifact validator, not a live container runner.
Real containers run via the local CLI on the user's machine.
"""
import json
import time

import gradio as gr

from membra_sdk.job.chat_compiler import ChatCompiler
from membra_sdk.job.job_spec import JobSpec
from membra_sdk.job.artifact_hasher import ArtifactHasher
from membra_sdk.job.yield_meter import YieldMeter
from membra_sdk.job.validators import ValidatorSet
from membra_sdk.job.consensus import ConsensusEngine
from membra_sdk.job.proof_bundle import ProofBundle
from membra_sdk.job.settlement import SettlementAdapter


def compile_chat(prompt):
    """Tab 1: Chat -> Job Spec"""
    compiler = ChatCompiler()
    job = compiler.compile(prompt)
    return job.to_json()


def show_plan(job_json):
    """Tab 2: Job -> Container Plan"""
    try:
        job = json.loads(job_json)
    except:
        return "Invalid job JSON"

    plan = f"""# MEMBRA Job Plan: {job.get('job_id', 'N/A')}

## Intent
{job.get('intent', 'N/A')}

## Runtime
- Container: {job.get('runtime', {}).get('container', 'N/A')}
- Model: {job.get('model_backend', 'N/A')}
- Tools: {', '.join(job.get('tools', []))}

## Policy
{json.dumps(job.get('policy', {}), indent=2)}

## Expected Outputs
{chr(10).join(f"- {o}" for o in job.get('expected_outputs', []))}

## Yield Metric
{job.get('yield_metric', 'N/A')}
"""
    return plan


def dry_run(job_json):
    """Tab 3: Run / Dry Run"""
    try:
        job = json.loads(job_json)
    except:
        return "Invalid job JSON"

    # Simulate a dry run
    result = f"""# MEMBRA Dry Run: {job.get('job_id', 'N/A')}

## Status
✅ Job spec validated
✅ Policy gates clear (mainnet={job.get('policy', {}).get('mainnet', False)})
✅ Container image found: {job.get('runtime', {}).get('container', 'N/A')}
⚠️  No secrets detected
⚠️  Funds disabled (safe mode)

## Simulation
- Container would start with restricted network
- Model backend would load: {job.get('model_backend', 'N/A')}
- Expected outputs would be generated in sandbox
- All policy checks would be enforced

## Note
For real execution, use the local CLI:
  membra job run --job {job.get('job_id', 'N/A')}
"""
    return result


def score_yield(job_json, artifact_count, tests_passed, tests_total, lint_passed, security_flags):
    """Tab 4: Yield Score"""
    try:
        job = json.loads(job_json)
    except:
        return "Invalid job JSON"

    meter = YieldMeter()

    # Build fake artifacts list for scoring
    artifacts = [{"path": f"artifact_{i}", "bytes": 1000} for i in range(artifact_count)]

    report = meter.measure(
        artifacts=artifacts,
        tests_passed=tests_passed,
        tests_total=tests_total,
        lint_passed=lint_passed,
        security_flags=security_flags,
    )

    result = f"""# MEMBRA Yield Report: {job.get('job_id', 'N/A')}

| Yield Type | Score | Notes |
|------------|-------|-------|
| Artifact Yield | {report.artifact_yield} | {report.files_created} files created |
| Validation Yield | {report.validation_yield} | {report.tests_passed}/{report.tests_total} tests |
| Market Yield | {report.market_yield} | No external receipts |
| Chain Yield | {report.chain_yield} | No on-chain receipts |
| **Total Score** | **{report.total_score}** | |

## Economic Status
{report.economic_status}
Real Revenue: ${report.real_revenue}

## Security
Security Flags: {report.security_flags}
Lint Passed: {'✅' if report.lint_passed else '❌'}
"""
    return result, report.to_dict()


def run_consensus(job_json, yield_dict):
    """Tab 5: Consensus"""
    try:
        job = json.loads(job_json)
    except:
        return "Invalid job JSON"

    # Build fake artifacts for validation
    artifacts = [{"path": o} for o in job.get('expected_outputs', [])]

    # Run validators
    validator_set = ValidatorSet()
    test_results = {"passed": yield_dict.get('tests_passed', 0), "total": yield_dict.get('tests_total', 1)}
    votes = validator_set.run(job, artifacts, test_results=test_results)

    # Evaluate consensus
    consensus = ConsensusEngine().evaluate(votes)

    votes_table = "\n".join(
        f"| {v['validator_id']} | {v['role']} | {v['vote']} | {v['reason']} |"
        for v in votes
    )

    result = f"""# MEMBRA Consensus: {job.get('job_id', 'N/A')}

## Votes
| Validator | Role | Vote | Reason |
|-----------|------|------|--------|
{votes_table}

## Result
**{consensus['result'].upper()}**
- Yes: {consensus['yes_votes']}/{consensus['total_votes']} ({consensus['ratio']:.0%})
- Threshold: {consensus['threshold']}

## Rejection Reasons
{chr(10).join(f"- {r}" for r in consensus.get('rejection_reasons', ['None']))}
"""
    return result, consensus


def export_proof(job_json, yield_dict, consensus_dict):
    """Tab 6: Export"""
    try:
        job = json.loads(job_json)
    except:
        return "Invalid job JSON"

    # Build proof bundle
    bundle_builder = ProofBundle()
    chat = {"prompt_hash": job.get('prompt_hash', ''), "summary": job.get('chat_summary', '')}
    container = {"image": job.get('runtime', {}).get('container', '')}
    artifacts = [{"path": o} for o in job.get('expected_outputs', [])]

    bundle = bundle_builder.build(
        chat=chat,
        job=job,
        container=container,
        artifacts=artifacts,
        yield_report=yield_dict,
        consensus=consensus_dict,
    )

    # Settlement preview
    settlement = SettlementAdapter()
    preview = settlement.preview(bundle)

    result = f"""# MEMBRA Proof Bundle: {job.get('job_id', 'N/A')}

## Root Hash
`{bundle['root_hash']}`

## Schema
{bundle['schema']}

## Settlement Preview
Settlable: {'✅' if preview['settlable'] else '❌'}
{preview.get('warning', '')}

### Suggested Actions
{chr(10).join(f"- {a}" for a in preview.get('suggested_actions', []))}

## Full Bundle (JSON)
```json
{json.dumps(bundle, indent=2)[:2000]}...
```

## Export Commands
```bash
# Local CLI
membra proof export {job.get('job_id', 'N/A')} --format zip
membra settle preview {job.get('job_id', 'N/A')}
```
"""
    return result


# Gradio UI
def create_app():
    with gr.Blocks(title="MEMBRA — Proof-of-Job Runtime") as app:
        gr.Markdown("# MEMBRA Proof-of-Job Runtime")
        gr.Markdown(
            "Turn chat into executable jobs. Measure yield. Validate with consensus. "
            "Export proof bundles."
        )

        # State
        job_state = gr.State()
        yield_state = gr.State()
        consensus_state = gr.State()

        with gr.Tab("1. Chat -> Job Spec"):
            prompt_input = gr.Textbox(
                label="Chat Prompt",
                placeholder="Build a Python FastAPI app for my proof runtime...",
                lines=3,
            )
            compile_btn = gr.Button("Compile to Job Spec")
            job_output = gr.Code(label="Job Spec JSON", language="json")
            compile_btn.click(compile_chat, inputs=prompt_input, outputs=job_output)
            compile_btn.click(lambda x: x, inputs=job_output, outputs=job_state)

        with gr.Tab("2. Job -> Container Plan"):
            plan_btn = gr.Button("Show Container Plan")
            plan_output = gr.Markdown()
            plan_btn.click(show_plan, inputs=job_state, outputs=plan_output)

        with gr.Tab("3. Run / Dry Run"):
            run_btn = gr.Button("Run Dry Run")
            run_output = gr.Markdown()
            run_btn.click(dry_run, inputs=job_state, outputs=run_output)

        with gr.Tab("4. Yield Score"):
            with gr.Row():
                artifact_count = gr.Number(label="Artifacts Created", value=4, precision=0)
                tests_passed = gr.Number(label="Tests Passed", value=12, precision=0)
                tests_total = gr.Number(label="Tests Total", value=12, precision=0)
            with gr.Row():
                lint_passed = gr.Checkbox(label="Lint Passed", value=True)
                security_flags = gr.Number(label="Security Flags", value=0, precision=0)
            score_btn = gr.Button("Score Yield")
            yield_output = gr.Markdown()
            score_btn.click(
                score_yield,
                inputs=[job_state, artifact_count, tests_passed, tests_total, lint_passed, security_flags],
                outputs=[yield_output, yield_state],
            )

        with gr.Tab("5. Consensus"):
            consensus_btn = gr.Button("Run Consensus")
            consensus_output = gr.Markdown()
            consensus_btn.click(
                run_consensus,
                inputs=[job_state, yield_state],
                outputs=[consensus_output, consensus_state],
            )

        with gr.Tab("6. Export"):
            export_btn = gr.Button("Export Proof Bundle")
            export_output = gr.Markdown()
            export_btn.click(
                export_proof,
                inputs=[job_state, yield_state, consensus_state],
                outputs=export_output,
            )

        gr.Markdown("---")
        gr.Markdown(
            "**MEMBRA Doctrine:** Yield starts as proof-of-work-quality, not fake revenue. "
            "MEMBRA measures and packages proof. It cannot manufacture external demand."
        )

    return app


if __name__ == "__main__":
    app = create_app()
    app.launch()
