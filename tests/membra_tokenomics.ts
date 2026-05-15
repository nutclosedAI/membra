/**
 * MEMBRA Tokenomics Anchor Test Suite
 * Run with: anchor test --skip-build
 */
import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { MembraTokenomics } from "../target/types/membra_tokenomics";
import { expect } from "chai";

const program = anchor.workspace.MembraTokenomics as Program<MembraTokenomics>;

describe("membra_tokenomics", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);

  const authority = anchor.web3.Keypair.generate();
  let treasury: anchor.web3.Keypair;
  let protocolWallet: anchor.web3.Keypair;
  let validatorPool: anchor.web3.Keypair;

  const SALE_ID = 1;
  let salePda: anchor.web3.PublicKey;
  let poolPda: anchor.web3.PublicKey;

  before(async () => {
    treasury = anchor.web3.Keypair.generate();
    protocolWallet = anchor.web3.Keypair.generate();
    validatorPool = anchor.web3.Keypair.generate();

    // Airdrop SOL for tests
    const airdrops = await Promise.all([
      provider.connection.requestAirdrop(
        authority.publicKey,
        5 * anchor.web3.LAMPORTS_PER_SOL
      ),
      provider.connection.requestAirdrop(
        treasury.publicKey,
        1 * anchor.web3.LAMPORTS_PER_SOL
      ),
      provider.connection.requestAirdrop(
        protocolWallet.publicKey,
        1 * anchor.web3.LAMPORTS_PER_SOL
      ),
      provider.connection.requestAirdrop(
        validatorPool.publicKey,
        1 * anchor.web3.LAMPORTS_PER_SOL
      ),
    ]);
    for (const sig of airdrops) {
      await provider.connection.confirmTransaction(sig);
    }

    // Derive PDAs
    const idBytes = Buffer.alloc(8);
    idBytes.writeBigUInt64LE(BigInt(SALE_ID), 0);
    [salePda] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("token_sale"), idBytes],
      program.programId
    );
    [poolPda] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("early_reward_pool"), salePda.toBuffer()],
      program.programId
    );
  });

  it("Initialize token sale", async () => {
    const tx = await program.methods
      .initializeSale(
        new anchor.BN(SALE_ID),
        new anchor.BN(100_000), // base_price = 0.0001 SOL
        new anchor.BN(100), // slope_bps
        2000, // max_bonus_bps = 20%
        new anchor.BN(3600), // 1 hour duration
        new anchor.BN(10 * anchor.web3.LAMPORTS_PER_SOL), // cap 10 SOL
        new anchor.BN(1 * anchor.web3.LAMPORTS_PER_SOL), // max rebate 1 SOL
        500 // rebate_rate_bps = 5%
      )
      .accounts({
        authority: authority.publicKey,
        tokenSale: salePda,
        treasury: treasury.publicKey,
        protocolWallet: protocolWallet.publicKey,
        validatorPool: validatorPool.publicKey,
        earlyRewardPool: poolPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      } as any)
      .signers([authority])
      .rpc();

    const sale = await program.account.tokenSale.fetch(salePda);
    expect(sale.authority.toString()).to.equal(authority.publicKey.toString());
    expect(sale.status).to.equal(0); // Draft
    expect(sale.basePriceLamports.toNumber()).to.equal(100_000);
    expect(sale.maxBonusBps).to.equal(2000);
    expect(sale.earlyRewardCapLamports.toNumber()).to.equal(
      10 * anchor.web3.LAMPORTS_PER_SOL
    );
  });

  it("Activate sale", async () => {
    await program.methods
      .activateSale()
      .accounts({
        authority: authority.publicKey,
        tokenSale: salePda,
      } as any)
      .signers([authority])
      .rpc();

    const sale = await program.account.tokenSale.fetch(salePda);
    expect(sale.status).to.equal(1); // Active
    expect(sale.startTime.toNumber()).to.be.greaterThan(0);
    expect(sale.endTime.toNumber()).to.be.greaterThan(sale.startTime.toNumber());
  });

  it("Buyer contributes and receives token allocation", async () => {
    const buyer = anchor.web3.Keypair.generate();
    await provider.connection.confirmTransaction(
      await provider.connection.requestAirdrop(
        buyer.publicKey,
        2 * anchor.web3.LAMPORTS_PER_SOL
      )
    );

    const [receiptPda] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("buyer_receipt"), salePda.toBuffer(), buyer.publicKey.toBuffer()],
      program.programId
    );
    const [contribPda] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("contribution"), salePda.toBuffer(), buyer.publicKey.toBuffer(), Buffer.from([1, 0, 0, 0, 0, 0, 0, 0])],
      program.programId
    );

    const treasuryBefore = await provider.connection.getBalance(treasury.publicKey);
    const protocolBefore = await provider.connection.getBalance(protocolWallet.publicKey);
    const validatorBefore = await provider.connection.getBalance(validatorPool.publicKey);

    const amount = 1 * anchor.web3.LAMPORTS_PER_SOL;
    await program.methods
      .contribute(new anchor.BN(amount))
      .accounts({
        buyer: buyer.publicKey,
        tokenSale: salePda,
        treasury: treasury.publicKey,
        protocolWallet: protocolWallet.publicKey,
        validatorPool: validatorPool.publicKey,
        earlyRewardPool: poolPda,
        contribution: contribPda,
        buyerReceipt: receiptPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      } as any)
      .signers([buyer])
      .rpc();

    const sale = await program.account.tokenSale.fetch(salePda);
    expect(sale.totalRaisedLamports.toNumber()).to.equal(amount);
    expect(sale.contributionCount.toNumber()).to.equal(1);

    // Verify splits (80/10/5/5)
    const treasuryAfter = await provider.connection.getBalance(treasury.publicKey);
    const protocolAfter = await provider.connection.getBalance(protocolWallet.publicKey);
    const validatorAfter = await provider.connection.getBalance(validatorPool.publicKey);

    expect(treasuryAfter - treasuryBefore).to.equal(Math.floor(amount * 0.8));
    expect(protocolAfter - protocolBefore).to.equal(Math.floor(amount * 0.1));
    expect(validatorAfter - validatorBefore).to.equal(Math.floor(amount * 0.05));

    // Verify receipt
    const receipt = await program.account.buyerReceipt.fetch(receiptPda);
    expect(receipt.buyer.toString()).to.equal(buyer.publicKey.toString());
    expect(receipt.totalContributedLamports.toNumber()).to.equal(amount);
    expect(receipt.totalTokensAllocated.toNumber()).to.be.greaterThan(0);
    expect(receipt.rebateClaimStatus).to.equal(1); // Eligible
  });

  it("Cannot claim rebate before finalization", async () => {
    const buyer = anchor.web3.Keypair.generate();
    await provider.connection.confirmTransaction(
      await provider.connection.requestAirdrop(
        buyer.publicKey,
        2 * anchor.web3.LAMPORTS_PER_SOL
      )
    );

    const [receiptPda] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("buyer_receipt"), salePda.toBuffer(), buyer.publicKey.toBuffer()],
      program.programId
    );
    const [contribPda] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("contribution"), salePda.toBuffer(), buyer.publicKey.toBuffer(), Buffer.from([2, 0, 0, 0, 0, 0, 0, 0])],
      program.programId
    );

    await program.methods
      .contribute(new anchor.BN(anchor.web3.LAMPORTS_PER_SOL))
      .accounts({
        buyer: buyer.publicKey,
        tokenSale: salePda,
        treasury: treasury.publicKey,
        protocolWallet: protocolWallet.publicKey,
        validatorPool: validatorPool.publicKey,
        earlyRewardPool: poolPda,
        contribution: contribPda,
        buyerReceipt: receiptPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      } as any)
      .signers([buyer])
      .rpc();

    try {
      await program.methods
        .claimRebate()
        .accounts({
          buyer: buyer.publicKey,
          tokenSale: salePda,
          earlyRewardPool: poolPda,
          buyerReceipt: receiptPda,
          systemProgram: anchor.web3.SystemProgram.programId,
        } as any)
        .signers([buyer])
        .rpc();
      expect.fail("Should have thrown ClaimsNotEnabled");
    } catch (e: any) {
      expect(e.toString()).to.include("ClaimsNotEnabled");
    }
  });

  it("Finalize sale and claim rebate", async () => {
    const buyer = anchor.web3.Keypair.generate();
    await provider.connection.confirmTransaction(
      await provider.connection.requestAirdrop(
        buyer.publicKey,
        2 * anchor.web3.LAMPORTS_PER_SOL
      )
    );

    const [receiptPda] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("buyer_receipt"), salePda.toBuffer(), buyer.publicKey.toBuffer()],
      program.programId
    );
    const [contribPda] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("contribution"), salePda.toBuffer(), buyer.publicKey.toBuffer(), Buffer.from([3, 0, 0, 0, 0, 0, 0, 0])],
      program.programId
    );

    // Contribute
    const amount = anchor.web3.LAMPORTS_PER_SOL;
    await program.methods
      .contribute(new anchor.BN(amount))
      .accounts({
        buyer: buyer.publicKey,
        tokenSale: salePda,
        treasury: treasury.publicKey,
        protocolWallet: protocolWallet.publicKey,
        validatorPool: validatorPool.publicKey,
        earlyRewardPool: poolPda,
        contribution: contribPda,
        buyerReceipt: receiptPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      } as any)
      .signers([buyer])
      .rpc();

    // Finalize
    await program.methods
      .finalizeSale()
      .accounts({
        authority: authority.publicKey,
        tokenSale: salePda,
      } as any)
      .signers([authority])
      .rpc();

    const saleAfterFinalize = await program.account.tokenSale.fetch(salePda);
    expect(saleAfterFinalize.status).to.equal(3); // Finalized

    // Claim rebate
    const buyerBefore = await provider.connection.getBalance(buyer.publicKey);
    await program.methods
      .claimRebate()
      .accounts({
        buyer: buyer.publicKey,
        tokenSale: salePda,
        earlyRewardPool: poolPda,
        buyerReceipt: receiptPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      } as any)
      .signers([buyer])
      .rpc();

    const receipt = await program.account.buyerReceipt.fetch(receiptPda);
    expect(receipt.rebateClaimStatus).to.equal(2); // Claimed
    expect(receipt.rebateClaimedLamports.toNumber()).to.be.greaterThan(0);

    const buyerAfter = await provider.connection.getBalance(buyer.publicKey);
    // Buyer received rebate (net gain after tx fees)
    expect(buyerAfter).to.be.greaterThan(buyerBefore);
  });

  it("Migrate liquidity", async () => {
    await program.methods
      .migrateLiquidity()
      .accounts({
        authority: authority.publicKey,
        tokenSale: salePda,
      } as any)
      .signers([authority])
      .rpc();

    const sale = await program.account.tokenSale.fetch(salePda);
    expect(sale.status).to.equal(5); // LiquidityMigrated
  });

  it("Cannot claim twice", async () => {
    // Use a fresh buyer
    const buyer = anchor.web3.Keypair.generate();
    await provider.connection.confirmTransaction(
      await provider.connection.requestAirdrop(
        buyer.publicKey,
        3 * anchor.web3.LAMPORTS_PER_SOL
      )
    );

    const [receiptPda] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("buyer_receipt"), salePda.toBuffer(), buyer.publicKey.toBuffer()],
      program.programId
    );
    const [contribPda] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from("contribution"), salePda.toBuffer(), buyer.publicKey.toBuffer(), Buffer.from([4, 0, 0, 0, 0, 0, 0, 0])],
      program.programId
    );

    await program.methods
      .contribute(new anchor.BN(anchor.web3.LAMPORTS_PER_SOL))
      .accounts({
        buyer: buyer.publicKey,
        tokenSale: salePda,
        treasury: treasury.publicKey,
        protocolWallet: protocolWallet.publicKey,
        validatorPool: validatorPool.publicKey,
        earlyRewardPool: poolPda,
        contribution: contribPda,
        buyerReceipt: receiptPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      } as any)
      .signers([buyer])
      .rpc();

    // Finalize (needed since previous test already migrated; we need a new sale ideally, but let's test with existing)
    // For this test, the sale is already migrated so claims should work.
    await program.methods
      .claimRebate()
      .accounts({
        buyer: buyer.publicKey,
        tokenSale: salePda,
        earlyRewardPool: poolPda,
        buyerReceipt: receiptPda,
        systemProgram: anchor.web3.SystemProgram.programId,
      } as any)
      .signers([buyer])
      .rpc();

    try {
      await program.methods
        .claimRebate()
        .accounts({
          buyer: buyer.publicKey,
          tokenSale: salePda,
          earlyRewardPool: poolPda,
          buyerReceipt: receiptPda,
          systemProgram: anchor.web3.SystemProgram.programId,
        } as any)
        .signers([buyer])
        .rpc();
      expect.fail("Should have thrown AlreadyClaimed");
    } catch (e: any) {
      expect(e.toString()).to.include("AlreadyClaimed");
    }
  });
});
