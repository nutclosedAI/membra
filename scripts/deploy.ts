/**
 * MEMBRA Core Solana Deployment Script
 *
 * Usage:
 *   npx tsx scripts/deploy.ts --cluster devnet
 *   npx tsx scripts/deploy.ts --cluster mainnet
 */
import { Connection, Keypair, PublicKey, clusterApiUrl } from "@solana/web3.js";
import { Wallet, AnchorProvider, Program } from "@coral-xyz/anchor";
import fs from "fs";
import path from "path";

const CLUSTER = process.argv.includes("--cluster")
  ? process.argv[process.argv.indexOf("--cluster") + 1]
  : "devnet";

async function main() {
  console.log(`Deploying MEMBRA Core to ${CLUSTER}...`);

  // Load wallet from ~/.config/solana/id.json
  const keypairPath = path.join(
    process.env.HOME || "",
    ".config",
    "solana",
    "id.json"
  );
  const secretKey = JSON.parse(fs.readFileSync(keypairPath, "utf-8"));
  const wallet = new Wallet(Keypair.fromSecretKey(Uint8Array.from(secretKey)));

  const connection = new Connection(clusterApiUrl(CLUSTER as any), "confirmed");
  const provider = new AnchorProvider(connection, wallet, {
    commitment: "confirmed",
  });

  console.log(`Deployer: ${wallet.publicKey.toBase58()}`);
  console.log(`Balance: ${await connection.getBalance(wallet.publicKey)} lamports`);

  // Load IDL
  const idlPath = path.join(__dirname, "..", "target", "idl", "membra_core.json");
  if (!fs.existsSync(idlPath)) {
    console.error(`IDL not found at ${idlPath}. Run 'anchor build' first.`);
    process.exit(1);
  }
  const idl = JSON.parse(fs.readFileSync(idlPath, "utf-8"));

  // Deploy (in real usage, use anchor deploy)
  // For now, just log the program ID
  const programId = new PublicKey(idl.address || "Membr1Core1111111111111111111111111111111111");
  console.log(`Program ID: ${programId.toBase58()}`);

  // Initialize protocol config
  const [configPda, configBump] = PublicKey.findProgramAddressSync(
    [Buffer.from("protocol_config")],
    programId
  );

  console.log(`Protocol Config PDA: ${configPda.toBase58()} (bump=${configBump})`);

  console.log("\nNext steps:");
  console.log(`  1. Run: anchor deploy --provider.cluster ${CLUSTER}`);
  console.log(`  2. Update PROGRAM_ID in clients/typescript/src/membra_core.ts`);
  console.log(`  3. Run: npx tsx scripts/initialize.ts`);
}

main().catch((err) => {
  console.error("Deployment failed:", err);
  process.exit(1);
});
