/**
 * MEMBRA Solana TypeScript Client SDK
 * Interact with the membra_core Anchor program.
 */
import { Connection, PublicKey, Keypair } from "@solana/web3.js";
import * as anchor from "@coral-xyz/anchor";
import { MembraCore } from "./membra_core_idl";

// ============================================================================
// Constants
// ============================================================================

export const PROGRAM_ID = new PublicKey("Membr1Core1111111111111111111111111111111111");

// ============================================================================
// Types
// ============================================================================

export interface JobData {
  creator: PublicKey;
  jobIdHash: string;
  chatHash: string;
  jobSpecHash: string;
  status: number;
  createdAt: number;
  closedAt: number;
}

export interface ArtifactManifestData {
  job: PublicKey;
  manifestHash: string;
  artifactRoot: string;
  metadataUriHash: string;
  artifactCount: number;
  createdAt: number;
}

export interface ValidatorData {
  authority: PublicKey;
  reputationScore: number;
  totalVotes: number;
  acceptedVotes: number;
  slashedVotes: number;
  active: boolean;
  createdAt: number;
}

export interface VoteData {
  job: PublicKey;
  validator: PublicKey;
  vote: number; // 1 = accept, 0 = reject
  score: number;
  reasonHash: string;
  createdAt: number;
}

export interface ConsensusData {
  job: PublicKey;
  yesVotes: number;
  noVotes: number;
  thresholdBps: number;
  result: number; // 1 = accepted, 0 = rejected
  finalizedAt: number;
}

export interface YieldData {
  job: PublicKey;
  artifactYield: number;
  validationYield: number;
  marketYield: number;
  chainYield: number;
  totalScore: number;
  createdAt: number;
}

export interface SettlementData {
  job: PublicKey;
  payer: PublicKey;
  recipient: PublicKey;
  amountLamports: number;
  settlementType: number;
  receiptHash: string;
  settledAt: number;
}

export enum JobStatus {
  Created = 0,
  ArtifactsSubmitted = 1,
  VotingOpen = 2,
  ConsensusAccepted = 3,
  ConsensusRejected = 4,
  YieldRecorded = 5,
  Settled = 6,
  Closed = 7,
}

export enum SettlementType {
  Bounty = 0,
  Grant = 1,
  Invoice = 2,
  Stripe = 3,
  Nft = 4,
}

// ============================================================================
// Client
// ============================================================================

export class MembraSolanaClient {
  program: anchor.Program<MembraCore>;
  provider: anchor.AnchorProvider;

  constructor(connection: Connection, wallet: anchor.Wallet, programId?: PublicKey) {
    this.provider = new anchor.AnchorProvider(connection, wallet, {
      commitment: "confirmed",
    });
    anchor.setProvider(this.provider);

    // In a real setup, load IDL from file. Here we use a placeholder.
    const idl = require("./membra_core_idl.json");
    this.program = new anchor.Program(idl, programId || PROGRAM_ID, this.provider);
  }

  // ==========================================================================
  // PDA Helpers
  // ==========================================================================

  protocolConfigPda(): [PublicKey, number] {
    return PublicKey.findProgramAddressSync([Buffer.from("protocol_config")], this.program.programId);
  }

  jobPda(creator: PublicKey, jobIdHash: Buffer): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [Buffer.from("job"), creator.toBuffer(), jobIdHash],
      this.program.programId
    );
  }

  artifactManifestPda(job: PublicKey): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [Buffer.from("artifact_manifest"), job.toBuffer()],
      this.program.programId
    );
  }

  validatorPda(authority: PublicKey): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [Buffer.from("validator"), authority.toBuffer()],
      this.program.programId
    );
  }

  votePda(job: PublicKey, validator: PublicKey): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [Buffer.from("vote"), job.toBuffer(), validator.toBuffer()],
      this.program.programId
    );
  }

  consensusPda(job: PublicKey): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [Buffer.from("consensus"), job.toBuffer()],
      this.program.programId
    );
  }

  yieldPda(job: PublicKey): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [Buffer.from("yield"), job.toBuffer()],
      this.program.programId
    );
  }

  settlementPda(job: PublicKey): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [Buffer.from("settlement"), job.toBuffer()],
      this.program.programId
    );
  }

  // ==========================================================================
  // Instructions
  // ==========================================================================

  async initialize(authority: PublicKey) {
    const [configPda] = this.protocolConfigPda();
    return this.program.methods
      .initialize(authority)
      .accounts({
        payer: this.provider.wallet.publicKey,
        protocolConfig: configPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      } as any)
      .rpc();
  }

  async createJob(
    creator: Keypair,
    jobIdHash: Buffer,
    chatHash: Buffer,
    jobSpecHash: Buffer
  ) {
    const [jobPda] = this.jobPda(creator.publicKey, jobIdHash);
    const [configPda] = this.protocolConfigPda();
    return this.program.methods
      .createJob(Array.from(jobIdHash), Array.from(chatHash), Array.from(jobSpecHash))
      .accounts({
        creator: creator.publicKey,
        jobAccount: jobPda,
        protocolConfig: configPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      } as any)
      .signers([creator])
      .rpc();
  }

  async submitArtifactManifest(
    signer: Keypair,
    jobPda: PublicKey,
    manifestHash: Buffer,
    artifactRoot: Buffer,
    metadataUriHash: Buffer,
    artifactCount: number
  ) {
    const [manifestPda] = this.artifactManifestPda(jobPda);
    return this.program.methods
      .submitArtifactManifest(
        Array.from(manifestHash),
        Array.from(artifactRoot),
        Array.from(metadataUriHash),
        artifactCount
      )
      .accounts({
        signer: signer.publicKey,
        jobAccount: jobPda,
        artifactManifest: manifestPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      } as any)
      .signers([signer])
      .rpc();
  }

  async submitValidatorVote(
    signer: Keypair,
    validatorKeypair: Keypair,
    jobPda: PublicKey,
    validatorPda: PublicKey,
    vote: number,
    score: number,
    reasonHash: Buffer
  ) {
    const [votePda] = this.votePda(jobPda, validatorPda);
    return this.program.methods
      .submitValidatorVote(vote, score, Array.from(reasonHash))
      .accounts({
        signer: signer.publicKey,
        jobAccount: jobPda,
        validatorAccount: validatorPda,
        voteAccount: votePda,
        authority: validatorKeypair.publicKey,
        systemProgram: anchor.web3.SystemProgram.programId,
      } as any)
      .signers([signer, validatorKeypair])
      .rpc();
  }

  async finalizeConsensus(
    signer: Keypair,
    jobPda: PublicKey,
    yesVotes: number,
    noVotes: number
  ) {
    const [consensusPda] = this.consensusPda(jobPda);
    const [configPda] = this.protocolConfigPda();
    return this.program.methods
      .finalizeConsensus(yesVotes, noVotes)
      .accounts({
        signer: signer.publicKey,
        jobAccount: jobPda,
        protocolConfig: configPda,
        consensusAccount: consensusPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      } as any)
      .signers([signer])
      .rpc();
  }

  async recordYield(
    signer: Keypair,
    jobPda: PublicKey,
    artifactYield: number,
    validationYield: number,
    marketYield: number,
    chainYield: number,
    totalScore: number
  ) {
    const [yieldPda] = this.yieldPda(jobPda);
    return this.program.methods
      .recordYield(artifactYield, validationYield, marketYield, chainYield, totalScore)
      .accounts({
        signer: signer.publicKey,
        jobAccount: jobPda,
        yieldAccount: yieldPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      } as any)
      .signers([signer])
      .rpc();
  }

  async recordSettlement(
    signer: Keypair,
    jobPda: PublicKey,
    payer: PublicKey,
    recipient: PublicKey,
    amountLamports: number,
    settlementType: number,
    receiptHash: Buffer
  ) {
    const [settlementPda] = this.settlementPda(jobPda);
    return this.program.methods
      .recordSettlement(payer, recipient, amountLamports, settlementType, Array.from(receiptHash))
      .accounts({
        signer: signer.publicKey,
        jobAccount: jobPda,
        settlementAccount: settlementPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      } as any)
      .signers([signer])
      .rpc();
  }

  async closeJob(signer: Keypair, jobPda: PublicKey) {
    return this.program.methods
      .closeJob()
      .accounts({
        signer: signer.publicKey,
        jobAccount: jobPda,
      } as any)
      .signers([signer])
      .rpc();
  }

  async registerValidator(payer: Keypair, authority: Keypair) {
    const [validatorPda] = this.validatorPda(authority.publicKey);
    return this.program.methods
      .registerValidator(authority.publicKey)
      .accounts({
        payer: payer.publicKey,
        authority: authority.publicKey,
        validatorAccount: validatorPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      } as any)
      .signers([payer])
      .rpc();
  }

  // ==========================================================================
  // Fetchers
  // ==========================================================================

  async fetchJob(jobPda: PublicKey): Promise<JobData | null> {
    try {
      const account = await this.program.account.jobAccount.fetch(jobPda);
      return {
        creator: account.creator,
        jobIdHash: Buffer.from(account.jobIdHash).toString("hex"),
        chatHash: Buffer.from(account.chatHash).toString("hex"),
        jobSpecHash: Buffer.from(account.jobSpecHash).toString("hex"),
        status: account.status,
        createdAt: account.createdAt.toNumber(),
        closedAt: account.closedAt.toNumber(),
      };
    } catch {
      return null;
    }
  }

  async fetchConsensus(jobPda: PublicKey): Promise<ConsensusData | null> {
    try {
      const [consensusPda] = this.consensusPda(jobPda);
      const account = await this.program.account.consensusAccount.fetch(consensusPda);
      return {
        job: account.job,
        yesVotes: account.yesVotes,
        noVotes: account.noVotes,
        thresholdBps: account.thresholdBps,
        result: account.result,
        finalizedAt: account.finalizedAt.toNumber(),
      };
    } catch {
      return null;
    }
  }

  async fetchYield(jobPda: PublicKey): Promise<YieldData | null> {
    try {
      const [yieldPda] = this.yieldPda(jobPda);
      const account = await this.program.account.yieldAccount.fetch(yieldPda);
      return {
        job: account.job,
        artifactYield: account.artifactYield,
        validationYield: account.validationYield,
        marketYield: account.marketYield.toNumber(),
        chainYield: account.chainYield.toNumber(),
        totalScore: account.totalScore,
        createdAt: account.createdAt.toNumber(),
      };
    } catch {
      return null;
    }
  }
}

// ============================================================================
// Helper: Hash a string to 32-byte buffer for on-chain use
// ============================================================================

export function hashToBuffer(data: string): Buffer {
  const { createHash } = require("crypto");
  return createHash("sha256").update(data).digest();
}
