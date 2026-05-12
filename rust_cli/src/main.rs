use clap::{Parser, Subcommand};
use membra_cli::ledger::InternalLedger;
use membra_cli::consensus::{ConsensusEngine, ProofOfYield};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tracing::{info, warn};

#[derive(Parser)]
#[command(name = "membra")]
#[command(about = "Membra CLI — Proof-of-Yield Validator for M5 Pro")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Start validator node
    Start {
        #[arg(short, long)]
        node_id: Option<String>,
        #[arg(short, long)]
        autonomous: bool,
    },
    /// Benchmark internal ledger throughput
    Bench {
        #[arg(short, long, default_value = "1000000")]
        ops: u64,
    },
    /// Run 3-agent consensus demo
    Consensus,
    /// Show node status
    Status,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();

    let cli = Cli::parse();

    match cli.command {
        Commands::Start { node_id, autonomous } => {
            start_node(node_id, autonomous).await;
        }
        Commands::Bench { ops } => {
            benchmark_ledger(ops);
        }
        Commands::Consensus => {
            demo_consensus();
        }
        Commands::Status => {
            show_status();
        }
    }
}

async fn start_node(node_id: Option<String>, autonomous: bool) {
    let id = node_id.unwrap_or_else(|| "m5-pro-001".to_string());
    info!("╔══════════════════════════════════════════════════════════════╗");
    info!("║  MEMBRA CLI — Proof-of-Yield Validator                     ║");
    info!("║  M5 Pro Mac | High-Throughput Ledger | LLM Consensus       ║");
    info!("╚══════════════════════════════════════════════════════════════╝");
    info!("Node ID: {}", id);
    info!("Autonomous: {}", autonomous);
    info!("Press Ctrl+C to stop...");

    let ledger = Arc::new(InternalLedger::new());
    let consensus = Arc::new(ConsensusEngine::new(&id));

    // Spawn processing loops
    let ledger_clone = ledger.clone();
    let consensus_clone = consensus.clone();
    tokio::spawn(async move {
        processing_loop(ledger_clone, consensus_clone).await;
    });

    tokio::signal::ctrl_c().await.ok();
    warn!("Shutting down Membra node...");
}

async fn processing_loop(ledger: Arc<InternalLedger>, consensus: Arc<ConsensusEngine>) {
    let mut interval = tokio::time::interval(Duration::from_millis(100));

    loop {
        interval.tick().await;

        let batch = ledger.drain_batch(1000);
        if !batch.is_empty() {
            let _root = consensus.form_batch_root(&batch);
            // In production: submit to P2P, wait for votes, finalize
            info!("Processed batch of {} ops", batch.len());
        }
    }
}

fn benchmark_ledger(target_ops: u64) {
    println!("╔══════════════════════════════════════════════════════════════╗");
    println!("║  MEMBRA LEDGER BENCHMARK                                    ║");
    println!("╚══════════════════════════════════════════════════════════════╝");
    println!("Target: {} operations", target_ops);

    let ledger = InternalLedger::new();
    let start = Instant::now();

    // Submit ops
    for i in 0..target_ops {
        let op = format!("op-{}", i);
        ledger.submit_string(&op);
    }
    let submit_time = start.elapsed();

    // Drain all
    let drain_start = Instant::now();
    let mut total_drained = 0usize;
    loop {
        let batch = ledger.drain_batch(10000);
        if batch.is_empty() {
            break;
        }
        total_drained += batch.len();
    }
    let drain_time = drain_start.elapsed();
    let total_time = start.elapsed();

    let submit_tps = target_ops as f64 / submit_time.as_secs_f64();
    let drain_tps = total_drained as f64 / drain_time.as_secs_f64();
    let total_tps = target_ops as f64 / total_time.as_secs_f64();

    println!("\nResults:");
    println!("  Submit time:  {:?}", submit_time);
    println!("  Drain time:   {:?}", drain_time);
    println!("  Total time:   {:?}", total_time);
    println!("  Submit TPS:   {:.0}", submit_tps);
    println!("  Drain TPS:    {:.0}", drain_tps);
    println!("  Total TPS:    {:.0}", total_tps);
    println!("  Ops processed: {}", total_drained);
}

fn demo_consensus() {
    println!("╔══════════════════════════════════════════════════════════════╗");
    println!("║  3-AGENT PROOF-OF-YIELD CONSENSUS DEMO                      ║");
    println!("╚══════════════════════════════════════════════════════════════╝");

    let mut engine = ConsensusEngine::new("demo");

    // Simulate 3 agents voting on same batch
    let batch_root = "0xabc123def456";

    // Agent 1 and 2 agree (same yield + inference)
    engine.submit_vote(batch_root, "hash-alpha", "yield-hash-1", 0.95);
    engine.submit_vote(batch_root, "hash-alpha", "yield-hash-1", 0.95);
    // Agent 3 disagrees
    engine.submit_vote(batch_root, "hash-beta", "yield-hash-2", 0.30);

    let finalized = engine.check_consensus(batch_root);

    println!("Votes submitted: 3");
    println!("Consensus reached: {}", if finalized { "YES ✅" } else { "NO ❌" });

    if finalized {
        println!("Batch finalized with 2/3 agreement on BOTH inference and yield.");
    }
}

fn show_status() {
    println!("Membra CLI v0.1.0");
    println!("Run 'membra start' to launch a validator node.");
}
