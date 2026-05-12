# ClosedAI + MEMBRA Product Architecture

## One-Sentence Definition

**ClosedAI** is a private AI operating system where every user runs a **MEMBRA personal blockchain**: a consent-based ledger of prompts, files, builds, proofs, notary attestations, and settlement receipts that turns human digital activity into verifiable economic infrastructure.

## The Product Stack

```
┌─────────────────────────────────────────────────────────────┐
│  CLOSED AI — Private AI Interface                           │
│  Chat, upload, build, speak                                  │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────────┐
│  MEMBRA PERSONAL CHAIN — User's Proof Ledger                 │
│  Chronological ledger of consented proof events             │
└────────────────────┬────────────────────────────────────────┘
                     │
    ┌────────────────┼────────────────┐
    │                │                │
┌───┴───┐     ┌────┴────┐     ┌─────┴─────┐
│ MEMBRA│     │ Artifact│     │  Consent  │
│ Node  │     │ Engine  │     │  Manager  │
│(local)│     │(hash)   │     │(privacy)  │
└───┬───┘     └────┬────┘     └─────┬─────┘
    │              │                │
    └──────────────┼────────────────┘
                   │
┌──────────────────┴────────────────────────────────────────┐
│  MEMBRA KYI — Identity & Notary Layer                     │
│  Know Your Identity attestation, flagged value review     │
└──────────────────┬────────────────────────────────────────┘
                   │
┌──────────────────┴────────────────────────────────────────┐
│  STRIPE LAYER — Fiat Payments & Payouts                    │
│  Buyer deposits, escrow, settlement, receipt verification │
└──────────────────┬────────────────────────────────────────┘
                   │
┌──────────────────┴────────────────────────────────────────┐
│  SOLANA / PUBLIC CHAIN — Hash Anchoring                   │
│  Only hashes and consented metadata go public             │
│  Raw files, private chats, KYC stay private               │
└──────────────────┬────────────────────────────────────────┘
                   │
┌──────────────────┴────────────────────────────────────────┐
│  MEMBRA PROOF MARKET — Monetization Layer                 │
│  Bounties, licensing, support, subscriptions, paid access │
└─────────────────────────────────────────────────────────────┘
```

## What Each User Owns

### They Own:
- **Personal chain namespace** — Their unique event ledger
- **Artifact history** — All generated builds, files, outputs
- **Proof hashes** — Cryptographic proofs of their work
- **Public wallet address** — For settlements and anchors
- **Private file corpus** — Unhashed, unshared original files
- **Monetization settings** — What they choose to sell and how
- **Consent policy** — What gets captured, when, and at what privacy level
- **Exportable archive** — Full chain export, user-controlled

### They Do NOT Automatically Own:
- Money just because something was hashed
- Revenue without a buyer, settlement, or verified receipt
- Public reputation without explicit consent

## The Consent Doctrine

```
Private by default.
Consent before capture.
Hash before public proof.
Notary before disputed value.
Stripe before fiat money.
Solana before public anchor.
Settlement before yield.
```

### Privacy Labels

| Label | Meaning | Public? |
|-------|---------|---------|
| **PRIVATE** | Never leaves local machine | ❌ |
| **PROTECTED** | Encrypted, shared only with explicit consent | ❌ |
| **PUBLIC** | Hash and metadata may be published | ✅ |
| **ANONYMOUS** | Metadata public, identity stripped | ✅ |

### Event Flow

```
Human prompt
    → LLM response
    → File artifact
    → Hash computed
    → Timestamp recorded
    → Appraisal/estimate
    → Privacy label applied
    → Optional: Notary/KYI review
    → Optional: Stripe receipt linked
    → Optional: Solana anchor
```

## Naming

| Component | Name | Role |
|-----------|------|------|
| Private AI interface | **ClosedAI** | Chat, upload, build, speak |
| Personal proof ledger | **MEMBRA Personal Chain** | User's chronological event ledger |
| Local compute validator | **MEMBRA Node** | Scans approved folders, hashes artifacts |
| Identity/notary layer | **MEMBRA KYI** | Identity attestation, flagged value review |
| Monetization layer | **MEMBRA Proof Market** | Bounties, licensing, subscriptions |
| Public hash anchor | **MEMBRA Anchor** | Solana devnet/public chain anchoring |

## What Each Layer Does

### ClosedAI
- Private ChatGPT-like interface
- Local or hosted LLM workspace
- User types, uploads, builds, speaks
- All data stays under user control

### MEMBRA Node
- Runs on user's Mac or cloud instance
- Scans ONLY approved folders
- Watches approved prompts
- Hashes artifacts
- Creates local proof events

### Artifact Engine
- Converts content into structured proof objects
- Computes hashes
- Generates metadata
- Links to parent events

### Personal Blockchain
- Records every approved event in user-owned order
- Chain integrity via previous_hash linking
- Privacy labels on every event
- Consent tokens prove user authorization
- Exportable by user at any time

### KYI / Notary Layer
- Verifies identity without storing full PII
- Reviews flagged high-value events
- Attests to legitimacy before monetization
- Prevents fraud in marketplace

### Stripe Layer
- Handles fiat payments and payouts
- Escrow for build bounties
- Settlement receipt verification
- Integrated with consensus

### Solana / Public Chain
- Anchors proof hashes only
- Never exposes raw files or private chats
- Provides public timestamping
- Optional: marketplace reputation

### Marketplace Layer
- Build bounties
- Artifact licensing
- Support subscriptions
- Paid API access
- Compute job marketplace

## The Strong Doctrine

| Rule | Meaning |
|------|---------|
| **Private by default** | Nothing is captured without explicit user action |
| **Consent before capture** | User must approve each capture type |
| **Hash before public proof** | Only hashes go public, never raw data |
| **Notary before disputed value** | High-value events reviewed before monetization |
| **Stripe before fiat money** | Real payment settlement required for yield |
| **Solana before public anchor** | Public proof only after user allows it |
| **Settlement before yield** | Money distributed only after funds clear |

## Revenue Model

Money begins only when there is:
- **Buyer payment** — Someone pays for a build or license
- **Stripe settlement** — Funds clear to escrow
- **Grant** — External funding for development
- **Sponsor** — Sponsored bounties or compute jobs
- **Bounty** — Posted tasks with escrowed payment
- **License** — Artifact reuse rights purchased
- **Subscription** — Recurring API or proof service payments
- **Escrow release** — Funds released after validator consensus
- **Verified protocol receipt** — On-chain or off-chain payment confirmed

## User Control

At any time, the user can:
- **Export** their full chain archive
- **Revoke** all consents (emergency privacy reset)
- **Change** privacy labels on past events
- **Delete** local events (removes from chain, not from anchors)
- **Pause** monetization
- **Switch** between local-only and public-anchor modes

## Comparison

| Feature | Traditional Blockchain | MEMBRA Personal Chain |
|---------|------------------------|----------------------|
| Data ownership | Network owns ledger | User owns ledger |
| Privacy | All public by default | Private by default |
| Consent | Implied by participation | Explicit per event type |
| Identity | Pseudonymous | KYI-attested, user-controlled |
| Monetization | Speculation | Verified work + settlement |
| Storage | Distributed, immutable | Local, user-exportable |
| Public proof | Full transaction data | Hash + metadata only |

## Next Steps

1. Deploy ClosedAI chat interface
2. Integrate MEMBRA Node with local file watching
3. Build Artifact Engine with automatic hash computation
4. Launch Personal Chain with consent-first UX
5. Integrate KYI notary for marketplace verification
6. Connect Stripe Connect for real payment processing
7. Anchor first production hash to Solana mainnet
8. Open MEMBRA Proof Market with build bounties

## Read More

- `docs/PROOF_OF_YIELD.md` — What yield means in MEMBRA
- `docs/PROFIT_LOOP.md` — Five revenue sources and distribution policy
- `docs/BENCHMARKS.md` — How throughput is measured
- `docs/SECURITY.md` — Key handling and policy gates
