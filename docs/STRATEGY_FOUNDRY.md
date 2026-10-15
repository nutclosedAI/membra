# Strategy Foundry v1

**Research and licensing primitives, not a trading venue or an autonomous hedge fund.**
No broker credentials, custody, leverage, orders, customer allocation, production signing
service, or claimed alpha. The registry's “incumbent” is an approved **research policy**,
not evidence that money is being traded. “Temporal,” TFL and TAW are product names.
The timing rule is an existing trend/inventory heuristic, not new physics or a theorem.

## What actually runs

1. Strict TFL v1 compiler: an allowlisted policy graph, immutable SHA-256 identity,
   capital/exposure/drawdown limits, mandatory validation and shadow-first manifest.
   JSON input (also a YAML-compatible subset); no code evaluation or YAML tags.
2. Bounded deterministic inventor: twelve descendants of an inventory policy; lookback,
   rebalance interval and trend threshold vary, capital and risk mandate cannot expand.
   **No LLM calls are made.** No hallucination-free intelligence is claimed.
3. Real arXiv metadata retrieval with queries, URLs, summaries and retrieval provenance.
   No inferred novelty, fabricated citations or automatic prior-art signoff.
4. Self-financing BTC-USD spot/USD-cash tournament with fee, slippage, participation,
   market-impact proxies, terminal liquidation, three chronological evaluation folds,
   daily-block Deflated Sharpe approximation and a final untouched 25% holdout.
5. SQLite registry, lineage, full trial ledger, independent reviews, shadow admission,
   explicit risk approval, monotonic compare-and-swap epochs and rollback to cash.
6. TAW Ed25519 receipts, HMAC instance fingerprint, randomized KPI commitments, chained
   decision IDs, action/risk/market evidence, external key/checkpoint verification.
7. Authenticated catalogue, constraint-fitting and governance HTTP API.

## Reproduce a real historical experiment

From the repository root with Python 3.11+:

```sh
pip install -e ".[foundry,dev]"
mkdir -p artifacts
python -m membra_sdk.foundry fetch --hours 6000 --output artifacts/btc.json
python -m membra_sdk.foundry run --data artifacts/btc.json \
  --db artifacts/foundry.db --output artifacts/report.json --research
python -m unittest discover -s tests -p test_foundry.py -v
ruff check membra_sdk/foundry tests/test_foundry.py
black --check membra_sdk/foundry tests/test_foundry.py
python -m compileall -q membra_sdk/foundry
```

The committed `data/foundry/BTC-USD-1h.json` is real Coinbase data. The downloader
excludes history preceding the last gap, reports the exclusion and hashes the original
candles; it **never fills missing hours with invented prices**. Market loading rejects
missing hours, duplicate timestamps, nonfinite numbers, nonpositive prices and zero volume.
Network failures surface as failures, not synthetic feeds.

Use a new empty database only for a genuinely independent experiment, not to evade
holdout sealing. An identical dataset cannot be retested in the ledger. Overlapping
holdout windows are also blocked. A malicious operator can delete the database, read
public price data or modify the code; this is process enforcement, not a cryptographic
guarantee that researchers have never seen the holdout.

The experiment registers cash, inventory control and all twelve temporal variants before
benchmarking. All fourteen attempts, including losers, contribute to DSR trial count.
Selection uses three chronological folds, never the final holdout. At most one
preselected challenger and the incumbent see that holdout. If it fails, there is **no
runner-up fallback on the same holdout**. This is a fixed-grid study, not fitted ML:
“walk-forward” here means causal rolling state and sequential evaluation, not claims
about an unimplemented training procedure.

The experiment's starting incumbent is cash preservation. It cannot promote anything:
there are no fabricated independent reviews or shadow observations. Historical receipts
are explicitly marked `historical-research-only`, not proof of paying customer use.
The local issuer is ephemeral; its public key has to be pinned independently before
it has evidentiary value. Auditor openings are deliberately exported for this experiment.

## Benchmark assumptions

At open `i`, the policy sees only completed candles strictly before `i`. It selects a
long-only BTC weight, executes a participation-limited trade at the open plus cost proxies,
then marks equity at open `i+1`. Cash and BTC inventory are accounted for separately.
Temporal policies hold BTC only when lookback return exceeds the threshold; otherwise
they hedge by selling spot into cash. Inventory control targets a fixed bounded weight.
Cash interest defaults to zero. This is not a derivatives deep-hedging implementation.

Default assumptions: $2m research capital, 50% target maximum BTC exposure, 10% drawdown
budget, 10 bps fee + 5 bps slippage each direction, impact of 100 bps times participation,
1% participation measured against **previous hour's** volume. Stress doubles fees and
slippage and halves permitted participation. These are explicit conservative assumptions,
not measured customer fee tiers, actual capacity or proven liquidity.

The drawdown guard latches reduce-only at observed opens; gaps, costs, partial fills and
intrabar losses can exceed the budget. Such measured breaches block eligibility. The
post-trade exposure check allows 10 bps numerical/transaction-cost tolerance; it is not
an intrabar leverage guarantee. Terminal liquidation incurs costs but assumes sufficient
exit liquidity; this limitation matters for large accounts. No funding/borrow costs
apply because there are no derivatives or short positions. Taxes, order-book queues,
latency, exchange outages and market impact calibration are not modeled.

No net-return or Sharpe output is proof of future profits. Daily-block DSR reduces some
multiple-testing inflation; serial dependence, trial correlation and prior unpublished
search still matter. Reference: Bailey & López de Prado, *The Deflated Sharpe Ratio*
(2014), https://doi.org/10.3905/jpm.2014.40.5.094.

## Independence and continuity

The authenticated principal, not an inventor-supplied field, determines API roles.
Use different tokens and human/service identities for:

| Role | Authority |
|---|---|
| inventor | Compile, register, derive; never review or promote |
| benchmark | Run fixed engine against server-pinned data and cost assumptions |
| research | Record HTTPS sources, limitations, `existing_method`/`unresolved` novelty and honest proof status |
| adversary | Record costs/leakage/capacity/regime/selection-bias checks and limitations |
| observer | Attest external shadow artifact hash, receipt checkpoint, observation count and measured drawdown |
| governor | Bootstrap cash, admit eligible reviewed challenger to shadow, approve research replacement, roll back |
| reader | Read capability catalogue and constraint matches |

Inventors cannot self-certify. Reviewers must be distinct; the governor must not be
inventor or reviewer. Tournament eligibility alone is insufficient. Promotion requires
independent research + adversarial reviews, a current-epoch shadow admission,
an independent **operator-attested** shadow record with at least 100 observations,
and an explicit risk-approval reference. Observer attestations are signed-in operator
statements, **not verified live trading**: v1 does not ingest or certify live outcomes.
Failed immutable reviews require a new policy version and new evidence, not overwriting
history. All authority changes increment epoch, so stale decisions fail atomically.

Rollback explicitly returns to the approved cash policy, not an unverified ancestor.
It changes the research manifest only; actual cancellation, liquidation and broker
reconciliation require a separately authorized execution/risk adapter. There is no
background market monitor and no automatic live integrity-failure response in v1.

The Python API and SQLite file are trusted operator interfaces, not adversarial sandboxes.
Protect DB/filesystem access, use TLS/authentication at an approved gateway if exposing
the API, and deploy roles as separately isolated services before real use.

## TAW: identity is not performance

`fingerprint = HMAC-SHA256(server_secret, canonical(domain, policy_id, license_id))`.
This uses HMAC, not ambiguous raw secret-prefix hashing. Receipt bodies include domain,
sequence, predecessor digest, versioned policy identity, licensed instance, unique
decision ID, timestamp, exact action, risk result, market-state digest and salted KPI
commitment. Ed25519 signs the canonical body.

Verification requires an **external trusted public key** plus expected policy/license,
receipt count and head hash. Without the external checkpoint, tail truncation cannot
be detected. Unique salts prevent simple guessing of low-entropy KPI commitments.
An authorized auditor can open a commitment; everyone else can verify its signed binding.
Store keys in KMS/HSM or an equivalent protected service; do not put private keys in
strategies, receipts, browser clients or source control. Batch audit exports must protect
openings and proprietary actions appropriately.

Receipts prove a trusted issuer signed a record; they do **not** prove fills, correctness
of KPI calculations, absence of copying, TEE attestation, novelty or alpha. Market-state
hashes are integrity digests, not privacy-preserving commitments for low-entropy prices.
No behavioral perturbations, remote sabotage, hidden fee siphoning or account locks.
Revocation should stop serving new authenticated decisions safely; billing, revocation
storage, production inference and attested execution are not implemented in v1.

## Developer API

`FOUNDRY_CREDENTIALS` is a JSON object mapping high-entropy tokens to
`{"name":"unique-principal","role":"inventor"}` (and other roles above).
Generate each real token with `python -m membra_sdk.foundry token`. Keep the complete
configuration in a secret manager or session environment, never source control.
The server refuses missing/short tokens or repeated principal identities.

```sh
python -m membra_sdk.foundry serve --data data/foundry/BTC-USD-1h.json \
  --db artifacts/service.db --port 8081
curl -H "Authorization: Bearer $READER_TOKEN" http://127.0.0.1:8081/catalogue
curl -H "Authorization: Bearer $READER_TOKEN" -H "Content-Type: application/json" \
  -d '{"capital":2000000,"max_drawdown":0.1,"max_exposure":0.5}' \
  http://127.0.0.1:8081/fit
```

| Method/path | Input |
|---|---|
| GET /health | Open; research-only status, no broker |
| GET /catalogue | Public capability metadata to authenticated clients; private thresholds excluded |
| GET /authority | Research incumbent + epoch |
| GET /events | Governor only; hashed event ledger |
| GET /runs/:id | Benchmark/review/governor only; sensitive reproducibility report |
| POST /compile | Strict TFL object |
| POST /strategies | TFL object with author equal to authenticated inventor |
| POST /strategies/:id/derive | `{}`; bounded descendants |
| POST /bootstrap | `{"policy":"cash-policy-id"}` |
| POST /tournaments | `{"policies":["cash-id","inventory-id","..."]}` |
| POST /reviews/:policy | Role-specific evidence described above |
| POST /shadow | `{"run":"run-id","epoch":1}` |
| POST /promote | `{"policy":"id","epoch":1,"approval":"risk-ticket-reference"}` |
| POST /rollback | `{"epoch":2,"reason":"integrity alarm"}` |
| POST /fit | Capital, drawdown, exposure constraints |

Fitting is a filter, not portfolio optimization: exact research capital must match.
It never combines correlated strategies or allocates any of the customer's $2m.
No exchange, developer web UI, licensing terms or investment solicitation is live.

## Next integration boundary

An LLM may submit TFL hypotheses, cited research suggestions or proof obligations.
It must never have governor credentials. Formal mathematical claims remain unproven
unless an independently checked theorem-prover artifact is integrated; passing a
Python simulation is not a proof. POPPER is relevant prior art for sequential
falsification, not a trading engine: https://proceedings.mlr.press/v267/huang25n.html.
Future live shadow ingestion needs verified market/execution adapters, durable key
management, customer authorization and risk/compliance review before any live deployment.
