/**
 * MEMBRA Core Protocol Initialization Script
 * Creates the ProtocolConfig account after deployment.
 */
import { Connection, Keypair, PublicKey, clusterApiUrl } from "@solana/web3.js";
import { Wallet, AnchorProvider } from "@coral-xyz/anchor";
import { MembraSolanaClient } from "../clients/typescript/src/membra_core";
import fs from "fs";
import path from "path";

const CLUSTER = process.argv.includes("--cluster")
  ? process.argv[process.argv.indexOf("--cluster") + 1]
  : "devnet";

async function main() {
  console.log(`Initializing MEMBRA Protocol on ${CLUSTER}...`);

  const keypairPath = path.join(
    process.env.HOME || "",
    ".config",
    "solana",
    "id.json"
  );
  const secretKey = JSON.parse(fs.readFileSync(keypairPath, "utf-8"));
  const wallet = new Wallet(Keypair.fromSecretKey(Uint8Array.from(secretKey)));
  const connection = new Connection(clusterApiUrl(CLUSTER as any), "confirmed");

  const client = new MembraSolanaClient(connection, wallet);

  console.log(`Authority: ${wallet.publicKey.toBase58()}`);

  try {
    const tx = await client.initialize(wallet.publicKey);
    console.log(`Protocol initialized. TX: ${tx}`);
    console.log(`Config PDA: ${client.protocolConfigPda()[0].toBase58()}`);
  } catch (err: any) {
    if (err.toString().includes("already in use")) {
      console.log("Protocol already initialized.");
    } else {
      throw err;
    }
  }
}

main().catch((err) => {
  console.error("Initialization failed:", err);
  process.exit(1);
});
