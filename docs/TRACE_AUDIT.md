# TRACE repository audit

Scope: the reachable `nutclosedAI/membra` checkout, branch
`feat/strategy-foundry`, inspected 2026-10-15. The Mac-only `subquantum-rl`
files shown in editor context were **not** accessible or audited. No row
counts, performance claims, or module descriptions in supplied prose are
assumed true.

## Verified implementation before TRACE

| Location | Observed implementation | Integrity gap |
| --- | --- | --- |
| `personal_chain/chain.py` | SHA-256 predecessor links, JSON files, public/private export | No signatures or trusted final checkpoint. `full_hash` excludes metadata, preview and anchor fields. Loader silently skips malformed files. No atomic multi-record transaction. |
| `core/ledger.py` | Bounded in-memory deque, batch draining | Buffer, not durable audit evidence; a full deque discards oldest entries. |
| `consensus/poy.py` | In-process vote records, inference/yield hashes, local timestamps | No independently signed votes/time receipts; no-key and error fallbacks do not constitute independent validation. |
| `kyi/notary.py` | In-memory requests and manually changed verification status | Status change, not a cryptographic notarial signature or independent identity proof. |
| `strategy/research_trace.py` | Serializable research artifact and prompt compiler | Useful research transfer object, **not** cryptographic TRACE. |
| `bro/*`, `economy/*` | Agent experiments, feature fingerprints, outcome calculations, capability/state transitions | No externally timestamped forecast commitment protocol found in these modules. Feature “signatures” are not cryptographic signatures. |
| `foundry/receipts.py` | Ed25519 receipts, HMAC instance fingerprint, salted KPI commitments, sequence/previous digest; verifier takes trusted key, expected head and count | No external time, persistent key lifecycle, exported trust contract or standalone verifier. Identity does not prove KPI correctness, execution or alpha. |
| `foundry/registry.py` | SQLite transactions, local hash-linked events, epoch CAS, distinct reviewers/governor, rollback | Local timestamps only; audit events not signed/time-witnessed; authorization is not a portable evidence contract. |

Paths in this table are relative to `membra_sdk/`.

### Behavior probes actually run

On a temporary **test** personal chain, `verify_chain_integrity()` returned
`True` for the original chain, after changing event metadata, after changing
the sole terminal event's `data_hash`, and after deleting all events. These
are scope limitations of a predecessor-only verifier without a trusted
terminal commitment, not claims that the existing function provides TRACE.

The foundry suite passed 30 unit tests before TRACE changes. Its existing
tests cover signed receipt mutations and governance transitions, not all six
TRACE acceptance criteria. Neither that run nor the audit is an independent
security certification.

## Baseline against the requested acceptance criteria

1. **Tamper evidence: partial.** TAW can verify against a separately supplied
   head/count; the personal chain alone cannot detect terminal truncation.
2. **Independent time: absent.** No verified external checkpoint receipt.
3. **Prequential integrity: absent.** Chronological backtesting is not
   prospective forecast commitment evidence.
4. **Portable verification: absent.** Some JSON exports exist, but no
   offline verifier with an explicit independent trust contract.
5. **Governance integrity: partial.** Foundry separation and epoch CAS
   exist; portable contemporaneous evidence linkage does not.
6. **Recovery: partial.** Foundry SQLite transactions exist; external-witness
   retry, corruption quarantine and key rotation are undefined.

No criterion is marked completely satisfied by the pre-TRACE repository.

## Implementation boundary

Add a focused `membra_sdk.trace` evidence protocol rather than rename the
research prompt object or silently change the personal-chain format.
Preserve existing foundry safety gates. Do not add broker execution or
capital allocation.

The verifier must take trusted actors/roles, chain identity and terminal
checkpoint from the verifier, not from the exported bundle alone. Otherwise
an attacker can replace the entire bundle, key set or terminal checkpoint.
A pinned TSA root is also verifier input; including a self-signed root in a
bundle does not make it trusted.

Use RFC 3161 requests with nonces, SHA-256 checkpoint imprints, and offline
OpenSSL signature/chain verification. Preserve original request and response
bytes. Track TSA uncertainty/accuracy; local observation and append times
are not independent clock evidence. An upper-bound TSA timestamp alone does
not prove that a market outcome was unavailable earlier. Scored outcomes
therefore require an independently trusted oracle's signed release-time
assertion; a locally declared market timestamp is insufficient.

Research principals must not mint oracle evidence, authorize decisions, or
execute authorized actions. Signed governance must bind exact decisions,
policy, epoch, evidence checkpoint and expiry, with single-use authorizations.
Rotation must preserve principal roles and verify both old- and new-key
possession. Corruption must fail closed, never be silently skipped.

## External protocol documentation consulted

- [FreeTSA protocol and current certificate fingerprints](https://freetsa.org/index_en.php)
- [OpenSSL 3.2 `ts`: query, response and verification](https://docs.openssl.org/3.2/man1/openssl-ts/)

FreeTSA's published examples disable nonces; TRACE intentionally retains
them. The public TSA sees only a checkpoint hash, not strategy parameters.
TSA trust remains an explicit auditor choice, not a universal trust claim.
