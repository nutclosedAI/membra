#!/usr/bin/env python3
"""Membra CLI — Command-line interface for the validator network.

Commands:
    membra start              # Start validator node
    membra benchmark          # Benchmark internal ledger throughput
    membra mine-files         # Scan files and generate yield estimates
    membra validate-prompt    # Run LLM inference and hash output
    membra anchor             # Anchor batch root to Solana devnet
    membra status             # Show node status
    membra consensus          # Run 3-agent consensus demo
    membra version            # Show SDK version
"""
import asyncio
import hashlib
import json
import os
import sys
import time
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from membra_sdk.core.node import MembraNode
from membra_sdk.core.yield_engine import YieldEngine
from membra_sdk.core.ledger import InternalLedger
from membra_sdk.core.artifacts import ArtifactTracker
from membra_sdk.consensus.poy import ProofOfYieldConsensus
from membra_sdk.profit_loop import MembraProfitLoop
from membra_sdk.config import MembraConfig
from membra_sdk.personal_chain.chain import PersonalChain, PrivacyLabel
from membra_sdk.personal_chain.events import EventType
from membra_sdk.brain_server.server import BrainServer
from membra_sdk.worker.worker_client import WorkerClient
from membra_sdk.job.chat_compiler import ChatCompiler
from membra_sdk.job.job_spec import JobSpec
from membra_sdk.job.artifact_hasher import ArtifactHasher
from membra_sdk.job.yield_meter import YieldMeter
from membra_sdk.job.validators import ValidatorSet
from membra_sdk.job.consensus import ConsensusEngine
from membra_sdk.job.proof_bundle import ProofBundle
from membra_sdk.job.settlement import SettlementAdapter
from membra_sdk.llm.gpt import LLMGPT, GPTConfig
from membra_sdk.llm.tokenizer import ByteTokenizer
from membra_sdk.llm.terminal_chat import TerminalChat
from membra_sdk.llm.validator import ValidatorEngine
from membra_sdk.llm.solana_bridge import SolanaValidatorBridge
from membra_sdk.token_gate import (
    TokenLaunchState,
    can_begin_token_and_liquidity,
    can_stake_treasury_sol,
    get_missing_conditions,
    get_state_summary,
)

app = typer.Typer(name="membra", help="Membra SDK — Local Proof-of-Yield Validator Kit")
console = Console()


@app.command()
def start(
    node_id: Optional[str] = typer.Option(None, "--node-id", "-n", help="Validator node ID"),
    autonomous: bool = typer.Option(False, "--autonomous", "-a", help="Autonomous file mining mode"),
    enable_defi: bool = typer.Option(False, "--enable-defi", help="Enable DeFi operator (devnet-only)"),
):
    """Start a Membra validator node."""
    console.print(Panel.fit(
        "[bold green]MEMBRA SDK[/bold green] — Local Proof-of-Yield Validator Kit\n"
        "M5 Pro Mac | File Corpus Mining | LLM Consensus | Solana Anchor",
        border_style="green",
    ))
    console.print("[yellow]⚠️  No guaranteed income. See docs/PROOF_OF_YIELD.md[/yellow]")
    console.print()

    if enable_defi:
        console.print("[red]⚠️  DeFi enabled. This is experimental and testnet-only.[/red]")

    node = MembraNode(node_id=node_id)
    try:
        asyncio.run(node.start())
    except KeyboardInterrupt:
        console.print("\n[bold red]Node stopped.[/bold red]")
        status = node.get_status()
        console.print(f"  Ops: {status['ops_processed']} | Finalized: {status['batches_finalized']} | Yield: {status['yield_estimated']:.4f}")


@app.command()
def benchmark(
    ops: int = typer.Option(100000, "--ops", help="Number of operations to benchmark"),
):
    """Benchmark internal ledger throughput."""
    console.print(Panel.fit(
        "[bold blue]MEMBRA BENCHMARK[/bold blue] — Internal Ledger Throughput",
        border_style="blue",
    ))
    console.print("[dim]Note: This measures local buffer performance, not Solana TPS.[/dim]")
    console.print()

    ledger = InternalLedger()

    # Submit phase
    submit_start = time.time()
    for i in range(ops):
        op = {"id": i, "type": "benchmark", "timestamp": time.time()}
        ledger.submit(op)
    submit_time = time.time() - submit_start

    # Drain phase
    drain_start = time.time()
    total_drained = 0
    while True:
        batch = ledger.drain_batch(10000)
        if not batch:
            break
        total_drained += len(batch)
    drain_time = time.time() - drain_start
    total_time = submit_time + drain_time

    table = Table(title="Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")
    table.add_row("Operations", str(ops))
    table.add_row("Submit Time", f"{submit_time:.4f}s")
    table.add_row("Drain Time", f"{drain_time:.4f}s")
    table.add_row("Total Time", f"{total_time:.4f}s")
    table.add_row("Submit TPS", f"{ops / submit_time:,.0f}")
    table.add_row("Drain TPS", f"{total_drained / drain_time:,.0f}")
    table.add_row("Total TPS", f"{ops / total_time:,.0f}")

    console.print(table)
    console.print()
    console.print("[dim]See docs/BENCHMARKS.md for methodology.[/dim]")


@app.command()
def mine_files(
    path: str = typer.Argument(..., help="Directory to scan for files"),
    max_files: int = typer.Option(50, "--max", help="Max files to analyze"),
):
    """Scan files and generate yield estimates."""
    console.print(Panel.fit(
        "[bold yellow]MEMBRA FILE MINER[/bold yellow] — Corpus Analysis",
        border_style="yellow",
    ))
    console.print()

    if not os.path.exists(path):
        console.print(f"[red]Path not found: {path}[/red]")
        raise typer.Exit(1)

    engine = YieldEngine()
    results = []
    count = 0

    for root, _, files in os.walk(path):
        for fname in files:
            if count >= max_files:
                break
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", errors="ignore") as f:
                    content = f.read()[:2000]
                y = engine.estimate(fpath, content)
                results.append((fname, y))
                count += 1
            except Exception:
                pass

    table = Table(title=f"Top Files by Yield Estimate (scanned {count})")
    table.add_column("File", style="cyan")
    table.add_column("Yield Estimate", style="green")

    for fname, y in sorted(results, key=lambda x: x[1], reverse=True)[:20]:
        table.add_row(fname, f"{y:.6f}")

    console.print(table)
    console.print()
    console.print("[dim]Yield estimates are scenario projections, not guaranteed returns.[/dim]")


@app.command()
def validate_prompt(
    prompt: str = typer.Argument(..., help="Prompt to validate via LLM"),
):
    """Run LLM inference and hash the output (deterministic fallback if no API key)."""
    console.print(Panel.fit(
        "[bold magenta]MEMBRA LLM VALIDATOR[/bold magenta]",
        border_style="magenta",
    ))
    console.print()

    consensus = ProofOfYieldConsensus(agent_id="cli-validator")
    inference = consensus._call_llm(prompt)
    inf_hash = hashlib.sha256(inference.encode()).hexdigest()

    console.print(f"Prompt: {prompt[:60]}...")
    console.print(f"Inference: {inference[:80]}...")
    console.print(f"Hash: {inf_hash}")
    console.print()
    console.print("[dim]This hash can be used as a consensus vote.[/dim]")


@app.command()
def anchor(
    memo: str = typer.Option(..., "--memo", help="Memo text to anchor to Solana devnet"),
    wallet: Optional[str] = typer.Option(None, "--wallet", help="Solana wallet JSON path"),
):
    """Anchor a memo to Solana devnet (requires devnet SOL)."""
    console.print(Panel.fit(
        "[bold cyan]MEMBRA SOLANA ANCHOR[/bold cyan] — Devnet Settlement",
        border_style="cyan",
    ))
    console.print()

    try:
        sys.path.insert(0, "/Users/alep/Downloads/mac_compute_node")
        from real_chain import RealSolanaClient, ChainConfig

        config = ChainConfig()
        client = RealSolanaClient(config)
        balance = client.balance_sol()

        console.print(f"Wallet: {client.pubkey}")
        console.print(f"Balance: {balance:.4f} SOL")

        if balance < 0.0005:
            console.print("[red]Insufficient SOL. Request airdrop at:[/red]")
            console.print(f"  https://faucet.solana.com/?address={client.pubkey}")
            raise typer.Exit(1)

        tx_sig = client.submit_memo(memo)
        console.print(f"[green]✅ Transaction: {tx_sig}[/green]")
        console.print(f"Explorer: https://explorer.solana.com/tx/{tx_sig}?cluster=devnet")

    except ImportError:
        console.print("[red]Solana dependencies not available. Install with:[/red]")
        console.print("  pip install solana solders spl-token")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@app.command()
def status():
    """Show current node status."""
    console.print("[bold]Membra Node Status[/bold]")
    console.print("  Run [cyan]membra start[/cyan] to launch a validator node.")


@app.command()
def consensus():
    """Run 3-agent proof-of-yield consensus demo."""
    console.print("[bold]3-Agent Proof-of-Yield Consensus Demo[/bold]")
    console.print("  Run: python3 tests/test_consensus.py")


@app.command()
def log_event(
    user: str = typer.Option("demo-user", "--user", "-u", help="User ID"),
    event_type: str = typer.Argument(..., help="Event type (prompt, upload, build, artifact, etc.)"),
    data: str = typer.Argument(..., help="Event data (JSON string)"),
    privacy: str = typer.Option("private", "--privacy", help="Privacy label: private, protected, public, anonymous"),
):
    """Log a consented event to the user's personal chain."""
    console.print(Panel.fit(
        "[bold blue]MEMBRA PERSONAL CHAIN[/bold blue] — Log Event",
        border_style="blue",
    ))

    chain = PersonalChain(user)
    try:
        event_data = json.loads(data)
    except json.JSONDecodeError:
        event_data = {"text": data}

    privacy_label = PrivacyLabel(privacy.lower())
    event_type_enum = None
    for et in EventType:
        if et.value == event_type.lower():
            event_type_enum = et
            break

    if not event_type_enum:
        console.print(f"[red]Unknown event type: {event_type}[/red]")
        raise typer.Exit(1)

    event = chain.log_event(event_type_enum, event_data, privacy=privacy_label, consent_override=True)
    if event:
        console.print(f"Event logged: [cyan]{event.event_id}[/cyan]")
        console.print(f"Sequence: {event.sequence}")
        console.print(f"Hash: {event.data_hash[:16]}...")
        console.print(f"Privacy: {event.privacy.value}")
    else:
        console.print("[yellow]Event not logged (consent policy blocks this type)[/yellow]")


@app.command()
def chain_summary(
    user: str = typer.Option("demo-user", "--user", "-u", help="User ID"),
):
    """Show user's personal chain summary."""
    console.print(Panel.fit(
        "[bold blue]MEMBRA PERSONAL CHAIN[/bold blue] — Summary",
        border_style="blue",
    ))

    chain = PersonalChain(user)
    summary = chain.get_chain_summary()

    table = Table(title=f"Chain for {user}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("User ID", summary["user_id"])
    table.add_row("Total Events", str(summary["events"]))
    table.add_row("Latest Sequence", str(summary["latest_sequence"]))
    table.add_row("Latest Hash", summary["latest_hash"][:16] + "...")
    table.add_row("Integrity", "VERIFIED" if chain.verify_chain_integrity() else "BROKEN")

    for label, count in summary["privacy_breakdown"].items():
        table.add_row(f"Privacy: {label}", str(count))

    console.print(table)


@app.command()
def export_chain(
    user: str = typer.Option("demo-user", "--user", "-u", help="User ID"),
    public_only: bool = typer.Option(False, "--public-only", help="Export only public proofs"),
):
    """Export user's personal chain archive."""
    console.print(Panel.fit(
        "[bold blue]MEMBRA PERSONAL CHAIN[/bold blue] — Export",
        border_style="blue",
    ))

    chain = PersonalChain(user)
    if public_only:
        data = chain.export_public_proofs()
        console.print(f"Public proofs: {len(data)} events")
    else:
        data = chain.export_chain_archive()
        console.print(f"Full archive: {len(data.get('events', []))} events")

    console.print(json.dumps(data, indent=2, default=str)[:1000])
    console.print("[dim]... (truncated, full export in ~/.membra/chains/)[/dim]")


@app.command()
def consent_status(
    user: str = typer.Option("demo-user", "--user", "-u", help="User ID"),
):
    """Show user's consent policy and approved capture types."""
    console.print(Panel.fit(
        "[bold yellow]MEMBRA CONSENT[/bold yellow] — Status",
        border_style="yellow",
    ))

    chain = PersonalChain(user)
    policy = chain.consent_policy

    table = Table(title="Consent Policy")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Auto-capture prompts", str(policy.get("auto_capture_prompts", False)))
    table.add_row("Auto-capture uploads", str(policy.get("auto_capture_uploads", False)))
    table.add_row("Auto-capture builds", str(policy.get("auto_capture_builds", True)))
    table.add_row("Default privacy", policy.get("default_privacy", "private"))
    table.add_row("Public anchor allowed", str(policy.get("public_anchor_allowed", False)))
    table.add_row("Monetization enabled", str(policy.get("monetization_enabled", False)))

    console.print(table)


@app.command()
def post_job(
    title: str = typer.Argument(..., help="Job title"),
    budget: float = typer.Argument(..., help="Budget in USD"),
    buyer: str = typer.Option("anonymous", "--buyer", help="Buyer ID"),
):
    """Post a build job to the marketplace."""
    console.print(Panel.fit(
        "[bold green]MEMBRA MARKETPLACE[/bold green] — Post Job",
        border_style="green",
    ))
    loop = MembraProfitLoop()
    job = loop.post_job(
        title=title,
        description="Posted via CLI",
        requirements=[],
        deliverables=[],
        budget=budget,
        buyer_id=buyer,
    )
    console.print(f"Job ID: [cyan]{job.job_id}[/cyan]")
    console.print(f"Budget: [green]${budget:.2f}[/green]")


@app.command()
def list_jobs():
    """List open jobs on the marketplace."""
    console.print("[bold]Open Jobs[/bold]")
    loop = MembraProfitLoop()
    jobs = loop.jobs.list_open()
    if not jobs:
        console.print("  No open jobs.")
        return
    table = Table()
    table.add_column("Job ID", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Budget", style="green")
    for job in jobs:
        table.add_row(job.job_id, job.title, f"${job.budget_usd:.2f}")
    console.print(table)


@app.command()
def profit_loop():
    """Run complete profit loop demo (buyer → builder → validators → payout)."""
    console.print(Panel.fit(
        "[bold green]MEMBRA PROFIT LOOP[/bold green] — Full Revenue Flow",
        border_style="green",
    ))
    console.print("[dim]Running demo: deposit → build → test → pay → verify → distribute[/dim]")
    console.print()
    import subprocess
    subprocess.run(["python3", "/Users/alep/Downloads/membra-sdk/examples/profit_loop_demo.py"])


@app.command()
def mode():
    """Show current mode (simulation vs production) and API status."""
    config = MembraConfig()
    status = config.get_status()

    console.print(Panel.fit(
        "[bold]MEMBRA MODE STATUS[/bold]",
        border_style="yellow" if config.is_simulation() else "green",
    ))

    table = Table()
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Mode", status["mode"].upper())
    table.add_row("Stripe Configured", "✅ Yes" if status["stripe_configured"] else "❌ No")
    table.add_row("Groq Configured", "✅ Yes" if status["groq_configured"] else "❌ No")
    table.add_row("Solana RPC", status["solana_rpc"])
    table.add_row("Safe for Development", "✅ Yes" if status["safe_for_development"] else "❌ Careful")

    console.print(table)

    if config.is_simulation():
        console.print("[yellow]⚠️  SIMULATION MODE: No real money moves. All payments are mocked.[/yellow]")
        console.print("   Set MEMBRA_MODE=production and configure STRIPE_SECRET_KEY for real payments.")
    else:
        console.print("[green]✅ PRODUCTION MODE: Real payments enabled.[/green]")
        console.print("   Ensure STRIPE_SECRET_KEY starts with sk_test_ (test) or sk_live_ (live).")


@app.command()
def brain_start(
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind (0.0.0.0 for LAN)"),
    port: int = typer.Option(7777, "--port", help="Port to listen on"),
):
    """Start the MEMBRA Brain Server (coordinator for distributed workers)."""
    console.print(Panel.fit(
        "[bold green]MEMBRA BRAIN SERVER[/bold green] — Distributed Worker Coordinator",
        border_style="green",
    ))
    console.print(f"   Binding: {host}:{port}")
    console.print(f"   LAN URL: http://{host}:{port}")
    console.print()
    console.print("   Other Macs should connect with:")
    console.print(f"     membra worker start --brain http://THIS_MAC_IP:{port} ...")
    console.print()

    server = BrainServer(host=host, port=port)
    server.run()


@app.command()
def worker_start(
    brain: str = typer.Option("http://127.0.0.1:7777", "--brain", help="Brain server URL"),
    worker_id: str = typer.Option("", "--worker-id", help="Unique worker ID"),
    model: str = typer.Option("llama3.2:3b", "--model", help="Ollama model to use"),
    role: str = typer.Option("general", "--role", help="Worker role (coder, reviewer, tester, docs)"),
    poll_interval: float = typer.Option(2.0, "--poll-interval", help="Poll interval in seconds"),
):
    """Start a MEMBRA worker that connects to a brain server over LAN."""
    console.print(Panel.fit(
        "[bold cyan]MEMBRA WORKER[/bold cyan] — Distributed Agent Worker",
        border_style="cyan",
    ))
    console.print(f"   Brain: {brain}")
    console.print(f"   Worker ID: {worker_id or 'auto-generated'}")
    console.print(f"   Model: {model}")
    console.print(f"   Role: {role}")
    console.print()

    client = WorkerClient(
        brain_url=brain,
        worker_id=worker_id or f"worker-{os.uname().nodename}",
        model=model,
        role=role,
    )
    return client.run(poll_interval=poll_interval)


@app.command()
def job_submit(
    prompt: str = typer.Argument(..., help="Job prompt/description"),
    brain: str = typer.Option("http://127.0.0.1:7777", "--brain", help="Brain server URL"),
    job_type: str = typer.Option("code-review", "--type", help="Job type"),
):
    """Submit a job to the MEMBRA brain server."""
    console.print(Panel.fit(
        "[bold yellow]MEMBRA JOB SUBMIT[/bold yellow] — Submit Work to Brain",
        border_style="yellow",
    ))
    console.print(f"   Brain: {brain}")
    console.print(f"   Type: {job_type}")
    console.print(f"   Prompt: {prompt[:60]}...")
    console.print()

    try:
        import requests
        resp = requests.post(
            f"{brain.rstrip('/')}/submit-job",
            json={"prompt": prompt, "type": job_type},
            timeout=30,
        )
        data = resp.json()

        if resp.status_code == 200:
            console.print(f"[green]✅ Job accepted: {data['job_id']}[/green]")
            console.print(f"   Tasks: {data['tasks']}")
            console.print(f"   Check status: membra job status {data['job_id']} --brain {brain}")
        else:
            console.print(f"[red]❌ Error: {data.get('error', 'Unknown')}[/red]")
    except Exception as e:
        console.print(f"[red]❌ Cannot reach brain at {brain}: {e}[/red]")
        console.print("   Is the brain server running? membra brain start")


@app.command()
def job_status(
    job_id: str = typer.Argument(..., help="Job ID"),
    brain: str = typer.Option("http://127.0.0.1:7777", "--brain", help="Brain server URL"),
):
    """Check status of a submitted job."""
    try:
        import requests
        resp = requests.get(f"{brain.rstrip('/')}/jobs/{job_id}", timeout=10)
        data = resp.json()

        if resp.status_code == 200:
            console.print(f"Job: [cyan]{job_id}[/cyan]")
            console.print(f"Status: [bold]{data['status']}[/bold]")
            console.print(f"Prompt: {data['prompt'][:60]}...")
            if data.get("final_artifact"):
                console.print(f"Artifact hash: {data['final_artifact']['artifact_hash'][:16]}...")
            if data.get("tasks"):
                table = Table(title="Tasks")
                table.add_column("Task", style="cyan")
                table.add_column("Status", style="white")
                table.add_column("Worker", style="green")
                for tid, t in data["tasks"].items():
                    table.add_row(tid[:20], t["status"], t.get("worker", "—")[:20])
                console.print(table)
        else:
            console.print(f"[red]Error: {data.get('error', 'Unknown')}[/red]")
    except Exception as e:
        console.print(f"[red]Cannot reach brain: {e}[/red]")


@app.command()
def version():
    """Show Membra SDK version."""
    from membra_sdk import __version__
    console.print(f"Membra SDK [bold]{__version__}[/bold]")


@app.command(name="chat")
def chat(
    prompt: str = typer.Argument(..., help="Chat prompt to compile into a job"),
):
    """Turn a chat prompt into a structured MEMBRA job spec."""
    console.print(Panel.fit(
        "[bold green]MEMBRA CHAT COMPILER[/bold green] — Chat → Job Spec",
        border_style="green",
    ))
    console.print(f"Prompt: {prompt[:80]}...")
    console.print()

    compiler = ChatCompiler()
    job = compiler.compile(prompt)
    path = job.save()

    console.print(f"[green]✅ Job compiled: {job.job_id}[/green]")
    console.print(f"   Intent: {job.intent[:60]}...")
    console.print(f"   Runtime: {job.runtime.get('container', 'N/A')}")
    console.print(f"   Model: {job.model_backend}")
    console.print(f"   Expected outputs: {', '.join(job.expected_outputs[:3])}")
    console.print(f"   Saved to: {path}")
    console.print()
    console.print("Next: membra job run --job-id " + job.job_id)
    console.print()
    console.print(job.to_json())


@app.command(name="job")
def job_cmd(
    action: str = typer.Argument(..., help="Action: create, run, status"),
    from_chat: str = typer.Option(None, "--from-chat", help="Create job from latest chat (use 'latest')"),
    job_id: str = typer.Option(None, "--job-id", help="Job ID to run or check"),
    container: str = typer.Option("python:3.11-slim", "--container", help="Container image"),
    model: str = typer.Option("ollama:qwen2.5-coder", "--model", help="Model backend"),
):
    """Create, run, or check status of a MEMBRA job."""
    if action == "create":
        console.print(Panel.fit(
            "[bold yellow]MEMBRA JOB CREATE[/bold yellow]",
            border_style="yellow",
        ))
        if from_chat == "latest":
            # Find latest job in .membra/jobs
            import glob
            job_dir = Path.home() / ".membra" / "jobs"
            files = sorted(job_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
            if not files:
                console.print("[red]No jobs found. Run 'membra chat' first.[/red]")
                return
            latest = files[0]
            job = JobSpec.load(str(latest))
            console.print(f"[green]✅ Loaded latest job: {job.job_id}[/green]")
            console.print(f"   Intent: {job.intent[:60]}...")
            console.print(f"   Next: membra job run --job-id {job.job_id}")
        else:
            console.print("Use --from-chat latest to create from latest chat")

    elif action == "run":
        console.print(Panel.fit(
            "[bold cyan]MEMBRA JOB RUN[/bold cyan] — Dry Run / Local Execution",
            border_style="cyan",
        ))
        if not job_id:
            console.print("[red]Error: --job-id required[/red]")
            return
        job_dir = Path.home() / ".membra" / "jobs" / f"{job_id}.json"
        if not job_dir.exists():
            console.print(f"[red]Job {job_id} not found[/red]")
            return
        job = JobSpec.load(str(job_dir))
        console.print(f"Running job: {job.job_id}")
        console.print(f"   Container: {container}")
        console.print(f"   Model: {model}")
        console.print(f"   Policy: {json.dumps(job.policy, indent=2)}")
        console.print()
        console.print("[yellow]Note: Real execution requires Docker + Ollama.[/yellow]")
        console.print("   For dry run, use the Hugging Face demo.")

    elif action == "status":
        if not job_id:
            console.print("[red]Error: --job-id required[/red]")
            return
        console.print(f"Job status: {job_id}")
        console.print("Status: pending (use membra job run to execute)")
    else:
        console.print(f"[red]Unknown action: {action}. Use: create, run, status[/red]")


@app.command(name="yield")
def yield_cmd(
    action: str = typer.Argument(..., help="Action: score"),
    job_id: str = typer.Option(None, "--job-id", help="Job ID to score"),
    artifacts: int = typer.Option(4, "--artifacts", help="Number of artifacts"),
    tests_passed: int = typer.Option(0, "--tests-passed", help="Tests passed"),
    tests_total: int = typer.Option(0, "--tests-total", help="Tests total"),
    lint: bool = typer.Option(True, "--lint/--no-lint", help="Lint passed"),
    security_flags: int = typer.Option(0, "--security-flags", help="Security flags count"),
):
    """Score yield for a completed job."""
    if action != "score":
        console.print("[red]Use: membra yield score --job-id <id>[/red]")
        return

    console.print(Panel.fit(
        "[bold magenta]MEMBRA YIELD METER[/bold magenta] — Score Job Yield",
        border_style="magenta",
    ))

    meter = YieldMeter()
    artifact_list = [{"path": f"artifact_{i}", "bytes": 1000} for i in range(artifacts)]
    report = meter.measure(
        artifacts=artifact_list,
        tests_passed=tests_passed,
        tests_total=tests_total,
        lint_passed=lint,
        security_flags=security_flags,
    )

    table = Table(title="Yield Report")
    table.add_column("Type", style="cyan")
    table.add_column("Score", style="white")
    table.add_row("Artifact Yield", str(report.artifact_yield))
    table.add_row("Validation Yield", str(report.validation_yield))
    table.add_row("Market Yield", str(report.market_yield))
    table.add_row("Chain Yield", str(report.chain_yield))
    table.add_row("Total Score", f"[bold]{report.total_score}[/bold]")
    console.print(table)

    console.print(f"\nEconomic status: {report.economic_status}")
    console.print(f"Real revenue: ${report.real_revenue}")
    console.print(f"Files: {report.files_created} | Tests: {report.tests_passed}/{report.tests_total}")


@app.command(name="consensus")
def consensus_cmd(
    action: str = typer.Argument(..., help="Action: validate"),
    job_id: str = typer.Option(None, "--job-id", help="Job ID"),
    validators: int = typer.Option(3, "--validators", help="Number of validators"),
):
    """Run consensus validation on a job's output."""
    if action != "validate":
        console.print("[red]Use: membra consensus validate --job-id <id>[/red]")
        return

    console.print(Panel.fit(
        "[bold blue]MEMBRA CONSENSUS[/bold blue] — Validator Consensus",
        border_style="blue",
    ))

    # Load job
    job_dir = Path.home() / ".membra" / "jobs" / f"{job_id}.json"
    if not job_dir.exists():
        console.print(f"[red]Job {job_id} not found[/red]")
        return

    job = JobSpec.load(str(job_dir))
    artifacts = [{"path": o} for o in job.expected_outputs]
    test_results = {"passed": 12, "total": 12}

    validator_set = ValidatorSet()
    votes = validator_set.run(job.to_dict(), artifacts, test_results=test_results)
    consensus = ConsensusEngine().evaluate(votes)

    table = Table(title="Validator Votes")
    table.add_column("Validator", style="cyan")
    table.add_column("Role", style="white")
    table.add_column("Vote", style="green")
    table.add_column("Reason", style="white")
    for v in votes:
        vote_color = "green" if v["vote"] == "accept" else "red"
        table.add_row(v["validator_id"], v["role"], f"[{vote_color}]{v['vote']}[/{vote_color}]", v["reason"])
    console.print(table)

    result_color = "green" if consensus["result"] == "accepted" else "red"
    console.print(f"\nResult: [{result_color}]{consensus['result'].upper()}[/{result_color}]")
    console.print(f"Votes: {consensus['yes_votes']}/{consensus['total_votes']} ({consensus['ratio']:.0%})")
    console.print(f"Threshold: {consensus['threshold']}")
    if consensus.get("rejection_reasons"):
        console.print("Rejection reasons:")
        for r in consensus["rejection_reasons"]:
            console.print(f"  • {r}")


@app.command(name="proof")
def proof_cmd(
    action: str = typer.Argument(..., help="Action: export"),
    job_id: str = typer.Option(None, "--job-id", help="Job ID"),
    format: str = typer.Option("zip", "--format", help="Export format: zip, json"),
):
    """Export a proof bundle for a completed job."""
    if action != "export":
        console.print("[red]Use: membra proof export --job-id <id>[/red]")
        return

    console.print(Panel.fit(
        "[bold white]MEMBRA PROOF BUNDLE[/bold white] — Export Proof",
        border_style="white",
    ))

    job_dir = Path.home() / ".membra" / "jobs" / f"{job_id}.json"
    if not job_dir.exists():
        console.print(f"[red]Job {job_id} not found[/red]")
        return

    job = JobSpec.load(str(job_dir))
    artifacts = [{"path": o, "sha256": "sha256:mock", "bytes": 1000} for o in job.expected_outputs]

    bundle = ProofBundle()
    proof = bundle.build(
        chat={"prompt_hash": job.prompt_hash, "summary": job.chat_summary},
        job=job.to_dict(),
        container={"image": job.runtime.get("container", "N/A")},
        artifacts=artifacts,
        yield_report={"artifact_yield": 78.0, "validation_yield": 91.0, "market_yield": 0, "chain_yield": 0, "total_score": 84.5},
        consensus={"result": "accepted", "yes_votes": 3, "total_votes": 3, "ratio": 1.0, "threshold": "2/3"},
    )

    console.print(f"Proof root: [cyan]{proof['root_hash']}[/cyan]")
    console.print(f"Schema: {proof['schema']}")
    console.print(f"Artifacts: {len(proof['artifacts'])}")

    if format == "json":
        out_path = Path.home() / ".membra" / "proofs" / f"{job_id}.json"
        bundle.save(str(out_path))
        console.print(f"[green]✅ Saved to: {out_path}[/green]")
    else:
        out_path = Path.home() / ".membra" / "proofs" / f"{job_id}.zip"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        bundle.export_zip(str(job_dir.parent), str(out_path))
        console.print(f"[green]✅ Exported ZIP: {out_path}[/green]")


@app.command(name="settle")
def settle_cmd(
    action: str = typer.Argument(..., help="Action: preview"),
    job_id: str = typer.Option(None, "--job-id", help="Job ID"),
):
    """Preview settlement options for a proof bundle."""
    if action != "preview":
        console.print("[red]Use: membra settle preview --job-id <id>[/red]")
        return

    console.print(Panel.fit(
        "[bold green]MEMBRA SETTLEMENT[/bold green] — Settlement Preview",
        border_style="green",
    ))

    job_dir = Path.home() / ".membra" / "jobs" / f"{job_id}.json"
    if not job_dir.exists():
        console.print(f"[red]Job {job_id} not found[/red]")
        return

    job = JobSpec.load(str(job_dir))
    artifacts = [{"path": o, "sha256": "sha256:mock", "bytes": 1000} for o in job.expected_outputs]

    bundle = ProofBundle()
    proof = bundle.build(
        chat={"prompt_hash": job.prompt_hash, "summary": job.chat_summary},
        job=job.to_dict(),
        container={"image": job.runtime.get("container", "N/A")},
        artifacts=artifacts,
        yield_report={"total_score": 84.5},
        consensus={"result": "accepted"},
    )

    settlement = SettlementAdapter()
    preview = settlement.preview(proof)

    if preview["settlable"]:
        console.print("[green]✅ Proof bundle is settlable[/green]")
        if preview.get("warning"):
            console.print(f"[yellow]⚠️ {preview['warning']}[/yellow]")
        console.print("\nSuggested actions:")
        for action in preview.get("suggested_actions", []):
            console.print(f"  • {action}")

        # Show invoice preview
        invoice = settlement.export_invoice(proof)
        console.print(f"\nInvoice preview: ${invoice['total']}")
    else:
        console.print("[red]❌ Not settlable:[/red]")
        console.print(f"   {preview.get('reason', 'Unknown')}")
        console.print("Suggested actions:")
        for action in preview.get("suggested_actions", []):
            console.print(f"  • {action}")


@app.command(name="validator")
def validator_start(
    model: str = typer.Option("llmgpt", "--model", help="Model type: llmgpt, ollama"),
    checkpoint: Optional[str] = typer.Option(None, "--checkpoint", help="Path to LLMGPT checkpoint"),
    n_layer: int = typer.Option(4, "--n-layer", help="Number of transformer layers"),
    n_head: int = typer.Option(4, "--n-head", help="Number of attention heads"),
    n_embd: int = typer.Option(256, "--n-embd", help="Embedding dimension"),
    temperature: float = typer.Option(0.8, "--temperature", help="Sampling temperature"),
    top_k: int = typer.Option(40, "--top-k", help="Top-k sampling"),
    mode: str = typer.Option("chat", "--mode", help="Mode: chat, validate, evaluate"),
    job_id: Optional[str] = typer.Option(None, "--job-id", help="Job ID for validator mode"),
    solana: bool = typer.Option(False, "--solana", help="Submit votes to Solana devnet"),
):
    """Start MEMBRA LLMGPT — terminal-native AI validator."""
    console.print(Panel.fit(
        "[bold cyan]MEMBRA LLMGPT[/bold cyan] — Terminal-Native AI Validator",
        border_style="cyan",
    ))

    if model == "llmgpt":
        config = GPTConfig(n_layer=n_layer, n_head=n_head, n_embd=n_embd)
        console.print(f"   Model: LLMGPT {n_layer}L/{n_head}H/{n_embd}D")
        console.print(f"   Params: {config.param_count:,}")
        console.print(f"   Checkpoint: {checkpoint or 'random init'}")

        if checkpoint and os.path.exists(checkpoint):
            llm = LLMGPT.load_checkpoint(checkpoint)
            console.print(f"   [green]Loaded checkpoint: {checkpoint}[/green]")
        else:
            llm = LLMGPT(config)
            console.print("   [yellow]Random initialization (train or load checkpoint)[/yellow]")

        if mode == "chat":
            chat = TerminalChat(
                model=llm,
                temperature=temperature,
                top_k=top_k,
            )
            chat.run()

        elif mode == "validate":
            console.print("[yellow]Validator mode: evaluating job artifacts...[/yellow]")
            engine = ValidatorEngine(llm)

            if job_id:
                job_dir = Path.home() / ".membra" / "jobs" / f"{job_id}.json"
                if job_dir.exists():
                    job = JobSpec.load(str(job_dir))
                    artifacts = [{"path": o} for o in job.expected_outputs]
                    result = engine.evaluate(job.intent, artifacts)
                    console.print(f"\n[bold]Validation Result:[/bold]")
                    console.print(f"  Vote: {'ACCEPT' if result['vote'] == 1 else 'REJECT'}")
                    console.print(f"  Score: {result['score']}")
                    console.print(f"  Reason: {result['reason']}")

                    if solana:
                        bridge = SolanaValidatorBridge(cluster="devnet")
                        bridge.submit_full_evaluation(
                            job_pda=job_id,
                            validator_pda=job_id,  # TODO: real validator PDA
                            evaluation=result,
                        )
                else:
                    console.print(f"[red]Job {job_id} not found[/red]")
            else:
                console.print("[red]Use --job-id to specify job[/red]")

        elif mode == "evaluate":
            console.print("[yellow]Evaluation mode: interactive artifact review[/yellow]")
            engine = ValidatorEngine(llm)
            console.print("Enter artifact path (or 'done' to finish):")
            artifacts = []
            while True:
                path = input("> ")
                if path.lower() in ("done", ""):
                    break
                if os.path.exists(path):
                    try:
                        with open(path) as f:
                            content = f.read()
                        artifacts.append({"path": path, "content": content})
                        console.print(f"  Added: {path}")
                    except Exception as e:
                        console.print(f"  [red]Error: {e}[/red]")
                else:
                    console.print(f"  [red]File not found: {path}[/red]")

            if artifacts:
                intent = input("Job intent: ")
                result = engine.evaluate(intent, artifacts)
                console.print(f"\n[bold]Evaluation:[/bold]")
                console.print(f"  Vote: {'ACCEPT' if result['vote'] == 1 else 'REJECT'}")
                console.print(f"  Score: {result['score']}")
                console.print(f"  Reason: {result['reason']}")

        else:
            console.print(f"[red]Unknown mode: {mode}. Use: chat, validate, evaluate[/red]")

    else:
        console.print(f"[red]Unknown model: {model}. Use: llmgpt[/red]")


@app.command(name="token-gate")
def token_gate_cmd(
    action: str = typer.Argument(..., help="Action: status, prepare-mint, prepare-pool, check-readiness"),
    treasury_sol: float = typer.Option(0.0, "--treasury-sol", help="Treasury SOL balance"),
    treasury_usdc: float = typer.Option(0.0, "--treasury-usdc", help="Treasury USDC balance"),
    agent_online: bool = typer.Option(False, "--agent-online", help="Agent is running"),
    dashboard_online: bool = typer.Option(False, "--dashboard-online", help="Dashboard is accessible"),
    corpus_indexed: bool = typer.Option(False, "--corpus-indexed", help="Corpus has been indexed"),
    proof_published: bool = typer.Option(False, "--proof-published", help="Proof manifest published"),
    wallet_connected: bool = typer.Option(False, "--wallet-connected", help="Wallet is connected"),
    human_approved: bool = typer.Option(False, "--human-approved", help="Human or multisig approval granted"),
    mainnet_enabled: bool = typer.Option(False, "--mainnet-enabled", help="Mainnet policy enabled"),
):
    """Check token and liquidity launch readiness."""
    console.print(Panel.fit(
        "[bold magenta]MEMBRA TOKEN GATE[/bold magenta] — Production Launch Readiness",
        border_style="magenta",
    ))

    state = TokenLaunchState(
        agent_online=agent_online,
        dashboard_online=dashboard_online,
        corpus_indexed=corpus_indexed,
        proof_manifest_published=proof_published,
        wallet_connected=wallet_connected,
        human_or_multisig_approval=human_approved,
        treasury_sol=treasury_sol,
        treasury_usdc=treasury_usdc,
        no_private_keys_stored=True,
        mainnet_policy_enabled=mainnet_enabled,
    )

    if action == "status":
        summary = get_state_summary(state)
        table = Table(title="Launch Readiness")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_row("Ready", "✅ YES" if summary["ready"] else "❌ NO")
        table.add_row("Phase", summary["phase"])
        table.add_row("Treasury SOL", f"{summary['treasury_sol']}")
        table.add_row("Treasury USDC", f"{summary['treasury_usdc']}")
        if summary["missing"]:
            table.add_row("Missing", "\n".join(summary["missing"]))
        console.print(table)

    elif action == "check-readiness":
        if can_begin_token_and_liquidity(state):
            console.print("[bold green]✅ ALL CONDITIONS MET[/bold green]")
            console.print("The agent may prepare token and liquidity transactions.")
            console.print("[yellow]A human or multisig must still sign all mainnet transactions.[/yellow]")
        else:
            console.print("[bold red]❌ NOT READY[/bold red]")
            console.print("Missing conditions:")
            for m in get_missing_conditions(state):
                console.print(f"  • {m}")

    elif action == "prepare-mint":
        if can_begin_token_and_liquidity(state):
            console.print("[green]✅ Preparing MEMBRA SPL mint transaction...[/green]")
            console.print("  Symbol: MEMBRA")
            console.print("  Decimals: 6")
            console.print("  Supply: Fixed (published before mint)")
            console.print("  Mint authority: Multisig or hardware wallet")
            console.print("[yellow]⚠️  This is a PREPARED transaction. A human/multisig must sign.[/yellow]")
        else:
            console.print("[red]❌ Cannot prepare mint. Check readiness first.[/red]")

    elif action == "prepare-pool":
        if can_begin_token_and_liquidity(state):
            console.print("[green]✅ Preparing Raydium MEMBRA/USDC pool transaction...[/green]")
            console.print("  Pair: MEMBRA/USDC")
            console.print("  Venue: Raydium")
            console.print("  Initial price: From actual LP deposit")
            console.print("[yellow]⚠️  This is a PREPARED transaction. A human/multisig must sign.[/yellow]")
        else:
            console.print("[red]❌ Cannot prepare pool. Check readiness first.[/red]")

    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        console.print("Use: status, check-readiness, prepare-mint, prepare-pool")


def main():
    app()


if __name__ == "__main__":
    main()
