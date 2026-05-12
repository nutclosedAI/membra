/**
 * MEMBRA Core End-to-End Test Flow
 * Demonstrates: create job → submit manifest → vote → finalize → yield → settle
 */
import { Connection, Keypair, PublicKey, clusterApiUrl } from "@solana/web3.js";
import { Wallet, AnchorProvider } from "@coral-xyz/anchor";
import { MembraSolanaClient, hashToBuffer } from "../clients/typescript/src/membra_core";
import fs from "fs";
import path from "path";

const CLUSTER = "devnet";

async function main() {
  console.log(`=== MEMBRA E2E Test Flow on ${CLUSTER} ===\n`);

  const keypairPath = path.join(process.env.HOME || "", ".config", "solana", "id.json");
  const secretKey = JSON.parse(fs.readFileSync(keypairPath, "utf-8"));
  const creator = Keypair.fromSecretKey(Uint8Array.from(secretKey));
  const wallet = new Wallet(creator);
  const connection = new Connection(clusterApiUrl(CLUSTER as any), "confirmed");

  const client = new MembraSolanaClient(connection, wallet);

  // 1. Create Job
  const jobIdHash = hashToBuffer("job_001");
  const chatHash = hashToBuffer("chat:Build a Solana dApp");
  const jobSpecHash = hashToBuffer(JSON.stringify({ intent: "Build dApp", runtime: "anchor" }));

  console.log("1. Creating job...");
  await client.createJob(creator, jobIdHash, chatHash, jobSpecHash);
  const [jobPda] = client.jobPda(creator.publicKey, jobIdHash);
  console.log(`   Job PDA: ${jobPda.toBase58()}`);

  // 2. Submit Artifact Manifest
  const manifestHash = hashToBuffer("manifest_v1");
  const artifactRoot = hashToBuffer("merkle_root_abc123");
  const metadataUriHash = hashToBuffer("ipfs://Qm...");

  console.log("2. Submitting artifact manifest...");
  await client.submitArtifactManifest(
    creator, jobPda, manifestHash, artifactRoot, metadataUriHash, 5
  );
  console.log(`   Manifest root: ${artifactRoot.toString("hex").slice(0, 16)}...`);

  // 3. Register & Vote (3 validators)
  for (let i = 0; i < 3; i++) {
    const validator = Keypair.generate();
    console.log(`3.${i + 1}. Registering validator ${i + 1}...`);
    await client.registerValidator(creator, validator);

    const [validatorPda] = client.validatorPda(validator.publicKey);
    const reasonHash = hashToBuffer(`reason_${i}`);
    const vote = i < 2 ? 1 : 0; // 2 accept, 1 reject

    console.log(`   Validator voting ${vote === 1 ? "ACCEPT" : "REJECT"}...`);
    await client.submitValidatorVote(
      creator, validator, jobPda, validatorPda, vote, 85, reasonHash
    );
  }

  // 4. Finalize Consensus
  console.log("4. Finalizing consensus...");
  await client.finalizeConsensus(creator, jobPda, 2, 1);
  console.log(`   Expected: ACCEPTED (2/3 >= 66.67%)`);

  // 5. Record Yield
  console.log("5. Recording yield...");
  await client.recordYield(creator, jobPda, 78, 91, 0, 0, 845);
  console.log(`   Total score: 84.5`);

  // 6. Record Settlement
  console.log("6. Recording settlement...");
  const receiptHash = hashToBuffer("stripe_receipt_pi_123");
  await client.recordSettlement(
    creator, jobPda, creator.publicKey, creator.publicKey, 1000000, 3, receiptHash
  );
  console.log(`   Settlement type: Stripe (3)`);

  // 7. Close Job
  console.log("7. Closing job...");
  await client.closeJob(creator, jobPda);
  console.log(`   Job closed.`);

  // Verify
  console.log("\n=== Verification ===");
  const jobData = await client.fetchJob(jobPda);
  console.log(`Job status: ${jobData?.status} (7 = Closed)`);

  const consensus = await client.fetchConsensus(jobPda);
  console.log(`Consensus: ${consensus?.result === 1 ? "ACCEPTED" : "REJECTED"}`);

  const yieldData = await client.fetchYield(jobPda);
  console.log(`Yield score: ${yieldData?.totalScore}`);

  console.log("\n=== E2E Flow Complete ===");
}

main().catch((err) => {
  console.error("Test flow failed:", err);
  process.exit(1);
});
