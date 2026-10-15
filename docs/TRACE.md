# TRACE v1: independently time-witnessed, portable research evidence

Read [the repository audit](TRACE_AUDIT.md) first. TRACE is a separate
evidence protocol, **not** a rename of the research-prompt `ResearchTrace`
and not a replacement for the foundry's current risk gates. The protocol
records research events and *recorded* authorizations, not broker fills.
There is no configured independent market oracle or live trading deployment.

## Verification contract

```text
event body -> Ed25519 signature -> SHA-256 predecessor chain
           -> signed checkpoint (count + head)
           -> RFC 3161 request (SHA-256 of signed checkpoint + nonce)
           -> external TSA response and certificate chain
```

An offline verifier requires **three separately authenticated inputs**:

1. `trust.json`: chain ID, initial principal public keys/roles, initial
   approved policy and governance epoch, risk-limits digest, maximum
   evidence age, TSA CA fingerprint and allowed timing uncertainty. A
   self-published trust file is **not** independent identity proof.
2. The expected **terminal signed checkpoint digest**, obtained outside
   the exported bundle. An attacker who controls only the bundle cannot
   silently truncate it, replace its key set, or rewrite its final head.
3. A TSA root certificate (PEM) whose **entire file** hashes to the
   `tsa_ca_sha256` trust pin. Do not trust the certificate just because it
   was packaged with the bundle. Verify the fingerprint with the
   provider or your own independent trust decision.

Keep the original Ed25519 private keys in separate protected services.
`Signer.generate` exists for examples/tests, not for persistent production
key management. Each trust entry maps exactly one actor to one immutable
role. Signing with an inventor key does not grant oracle, evaluator,
governor, executor or recorder authority; organizational independence
also requires **different key custodians**, which software cannot prove.

The JSON wire format is versioned, ASCII-escaped and key-sorted. Numbers
are integers only (including nanosecond epoch times and ppm probabilities);
decimal trading values must be strings. Duplicate keys, unknown event
types, unsupported event fields, nonfinite values, forged signatures,
sequence gaps and predecessor mismatches fail verification. Each event
body includes an ID, chain, sequence, predecessor, principal/key, kind,
payload, local observation time and local append time. Neither local
clock field is independently verified. Checkpoints bind **count and
head**; timestamp receipts bind checkpoint digests and a 128-bit nonce.

The TSA request and response are preserved as DER hex; the verifier
checks the request imprint and nonce against the response, the response's
CMS signature and TSA certificate chain against the pinned root, the TSA
signer's certificate fingerprint, and the certificate's validity at the
signed generation time. The returned interval is
`[generated_ns - uncertainty, generated_ns + uncertainty]`, where
uncertainty is **at least** the configured bound and the TSA token's
reported accuracy. A local chain alone cannot provide this interval.

The `provider` URL in an anchor is **transport metadata**, not proof
of provider identity; the cryptographic identity is the verified
certificate and its explicitly trusted root. Verification is offline:
no certificate URLs, origin server or TLS network calls are needed.
The verifier does **not** fetch historical OCSP/CRLs; if revocation
assurance matters, archive independent, time-appropriate revocation
evidence and add an explicit verification gate before relying on
old tokens. Do not represent offline chain verification as a
revocation-status guarantee.

## Prospective forecasting

1. A researcher signs an `observation` containing source/version and
   data commitment, then commits to a `forecast` tied to that observation,
   a policy digest, a future `target_ns`, a `deadline_ns` and the
   `brier-ppm-v1` scoring rule. The committed preimage is
   `{observation, policy, target_ns, prediction}`, salted with 32
   random bytes.
2. A recorder signs a checkpoint **containing the forecast**, and a
   TSA signs it *before* the target: the TSA interval's latest
   possible time must be strictly earlier than `target_ns`.
3. An independently provisioned `oracle` key signs `outcome` (binary
   value, source and asserted release time) or `missing` (explicit
   reason and release time after deadline). The oracle must not hold
   the forecast author's key. A future local timestamp alone cannot
   make a historical forecast prospective.
4. The oracle's resolution must also be covered by an independent TSA
   checkpoint *after* the asserted release. A researcher may reveal
   the salt and prediction later; the reveal must match the original
   commitment.
5. A separate `evaluator` signs `score`, referencing the forecast,
   reveal, outcome, independently witnessed **outcome checkpoint**
   and original TSA receipt digest. This unguessable token dependency
   forces the score record to follow the outcome witness. The
   score is the integer squared error
   `(probability_ppm - outcome * 1_000_000) ** 2`.
   Late/missing resolutions cannot be scored; duplicate resolutions
   or scores fail. An unreconciled forecast is reported as `pending` or
   `overdue_without_resolution`, never quietly treated as a win.

Oracle assertions depend on an **externally provisioned, independent and
truthful** oracle. A TSA proves a record existed by a time; it cannot
prove a price was not known or a feed was not manipulated. Until a
real independently operated price/fill oracle is integrated, do not
claim a live prequential trading result. Unit tests use an explicitly
ephemeral local test TSA/oracle with real cryptographic signatures; they
are protocol fixtures, not external market evidence.

## Governance / continuity boundary

The trusted initial policy/risk digest/epoch are external. An evaluator
signs a `decision` with policy, epoch, exact action and evidence IDs. A
governor (distinct from the evaluator) signs `authorization` for that
decision and a **named executor** only after a timestamped evidence
checkpoint covering the decision; it binds the exact TSA response
digest, policy, epoch, unchanged risk digest and a validity interval.
The timestamp dependency proves the authorization record could not
have been signed before receiving that evidence receipt.

An executor signs `authorized_action` referring to the authorization,
an independently anchored checkpoint covering the authorization and its
receipt digest. Its own terminal checkpoint must be independently
anchored no later than expiry; the evidence must not exceed the
externally supplied maximum age at that upper-bound time. The executor
cannot be the evidence author. Every authorization is single-use;
`revoke` stops future uses. A governor's signed `epoch` transition
invalidates previous grants even when a later epoch returns to the
same policy digest. A research principal cannot change the pinned
risk limits. These rules authorize **recorded actions only**; no
broker is connected, and no signed record establishes that an order
was actually submitted, filled or profitable.

Do **not** treat an imported old foundry event or historical Coinbase
candle as a prospective TRACE forecast. To couple foundry promotion to
TRACE in a later increment, provision independent actor keys and an
oracle, then make promotion require a separately distributed trust
file, checkpoint and verified result. Existing foundry registry
promotion must not be labeled TRACE-attested until that gate is wired.

## Standalone offline CLI

Requirements: Python 3.11+, `cryptography`, `asn1crypto==1.5.1`, and
OpenSSL 3.x in `PATH`. Install with `pip install -e ".[trace]"`.

```shell
python -m membra_sdk.trace inspect bundle.json
python -m membra_sdk.trace verify bundle.json \
  --trust trusted-from-auditor.json \
  --checkpoint 64-character-checkpoint-digest \
  --tsa-ca root-from-independent-source.pem
```

`inspect` explicitly reports **unverified**; `verify` exits nonzero
and identifies invalid event/checkpoint locations. A bundle is
ordinary JSON with `format`, `chain`, signed `events`, signed
`checkpoints`, and `anchors` indexed by checkpoint digest. Private
signing keys and confidential unsalted predictions are **not**
exported by TRACE; operators must review their own observation/action
payloads for sensitive data before export. Offline verification
works without the originating SQLite database.

The ledger's programmatic API is `Ledger(path, trust, ca)`,
`append(signer, kind, payload, id)`, `checkpoint(recorder)`,
`anchor(checkpoint, "https://…")` and `export(path, checkpoint)`.
`anchor` is an **explicit network operation** that publishes only the
checkpoint hash to the selected TSA:

```shell
python -m membra_sdk.trace anchor evidence.db \
  --trust trusted.json --tsa-ca root.pem --checkpoint DIGEST \
  --provider https://freetsa.org/tsr
python -m membra_sdk.trace export evidence.db bundle.json \
  --trust trusted.json --tsa-ca root.pem --checkpoint DIGEST
```

Read the TSA's protocol documentation and choose/pin the root
independently before submission. For the audited October 2026
experiment, FreeTSA published its CA PEM SHA-256 as
`2151b61137ffa86bf664691ba67e7da0b19f98c758e3d228d5d8ebf27e044438`;
this can change and is **not** a universal pinned root for all users.
FreeTSA's examples omit a nonce; TRACE requires one.

## Recovery semantics

| Event | Safe behavior |
| --- | --- |
| Process crash during append | SQLite `BEGIN IMMEDIATE` / `FULL`-synchronous WAL rolls back the incomplete transaction; reopen re-verifies existing chain and SQLite integrity. |
| Exact duplicate event ID | Return original signed event only for identical actor, signing key, kind and payload. Divergent content fails. |
| Corrupt committed event, checkpoint or prepared request | Reject on startup/next access. Preserve evidence for investigation; do not skip a bad row or auto-rewrite history. |
| Network timeout / partial TSA submission | Persist the original nonce-bearing query **before** submission. Retry the same query; accept only a verified matching response. An already completed checkpoint returns its first validated response. Multiple external tokens for one query are harmless; only the first accepted token is recorded. |
| Corrupt TSA response | Reject and leave the request pending; retry or investigate the provider. Do not mark it anchored. |
| Out-of-order event arrival | Reject references to future events and sequence/predecessor gaps; retry in order. |
| Key rotation | Old-key-signed `key_rotate` includes proof of possession of the new key; new key is used only from the next event onward. Historical verification retains old-key validity for prior events. Roles cannot change through rotation. |
| Key compromise / revocation | Governor-signed `key_revoke` permanently disables the principal for future events in the chain. Re-provision with a **new externally approved trust identity**; do not quietly restore the old key. An already compromised key's earlier statements require manual review; old external checkpoints constrain retrospective rewrites, not correctness. |
| Failed bundle export | Write/fsync to a sibling temporary file, then atomic replace; preserve the previous bundle if interrupted. Distribute its final checkpoint digest through an independent channel. |
| Missing/late outcome | Explicit `missing`/`late` status; do not score or impute performance. A pending forecast can become overdue when a later external checkpoint proves the deadline passed. |

Limits: a power loss may need filesystem-specific directory fsync
after rename; this implementation guarantees SQLite transaction
rollback and atomic rename, not every storage controller's durability.
SQLite lives on one trusted host. Cross-host key custody, malicious
operator controls, independently authenticated feed data, broker/fill
attestation, and production compliance review remain deployment
requirements.

Run the acceptance suite with
`python -m unittest discover -s tests -p test_trace.py -v`.
The tests exercise all six protocol criteria with local signed
cryptographic fixtures, while a **separate real FreeTSA receipt**
demonstrates external timestamp verification for a historical
dataset checkpoint only.
