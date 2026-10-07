# BRO — temporal observation and reorganization machine

BRO is not primarily a predictor. It is a **temporal
observation-and-reorganization** machine:

```
O_t -> Φ_t -> H(Φ_t) -> historical recurrence -> hypothesis -> test -> Y_{t+τ} -> G_{t+1}
```

`O_t` raw observations · `Φ_t` temporal fingerprint · `H` historical
search · `Y_{t+τ}` subsequent outcome · `G_{t+1}` reorganized knowledge.

This module builds the first controlled experiment of that loop: **can a
hidden algorithm be identified from the temporal fingerprint of its
observable order flow alone?** The market-microstructure grounding is
real — order flow has persistent temporal structure (arXiv:0809.0822),
execution algorithms leave behavioral signatures like child-order
slicing and liquidity replenishment (BIS mktc13), and markets contain
feedback loops (BIS wp122).

## The benchmark

```
KNOWN ALGORITHM -> GENERATED BEHAVIOR -> HIDDEN FROM BRO
  -> TEMPORAL FINGERPRINT -> ALGORITHM CLASSIFICATION
  -> OUT-OF-SAMPLE TEST -> ADVERSARIAL ADAPTATION -> RE-FINGERPRINT
```

`membra_sdk/bro/`:

```
agents.py       shared price path + the zoo of KNOWN algorithms
fingerprint.py  Φ: stream -> scalar features (cadence/size/mix/flow/
                lead-lag + Stokes s3 via strategy.spinor_stokes)
recurrence.py   H: labeled fingerprint bank + z-scored kNN
experiment.py   the three stages
```

## The zoo (known algorithms)

| Agent | Observable signature it should leave |
|---|---|
| `twap` | fixed-interval uniform slices → IAT CV ≈ 0, entropy ≈ 0 |
| `vwap` | U-shaped intraday profile → size varies, cadence dense |
| `momentum` | positive feedback → `corr(flow_t, move_{t-1})` ≈ +1, consistent s3 |
| `market_maker` | cancel/replace churn → high `cancel_per_trade`, symmetric sides |
| `gradient_descent` | `-η·∇C` steps → geometric size decay, high skew & max/median |
| `noise` | the null algorithm |

`gradient_descent` is the canary for the bigger claim — whether an
*optimization* algorithm is legible in the flow — tested synthetically
first, exactly because real-market claims must wait for a passing
synthetic benchmark.

## Stages and current results

1. **Base** — bank on 12 seeds/agent, classify 12 held-out seeds:
   **1.00 accuracy**, diagonal confusion matrix.
2. **Adversarial** — jittered cadence/slices (`twap_jittered`,
   `vwap_jittered`), faded reactions (`momentum_faded`), variable
   quoting (`market_maker_jittered`, `gradient_descent_jittered`), and a
   `twap_mimic` tilting slices with momentum — **0.81**. The failure is
   specific: jittered TWAP loses its entropy edge and leaks into `noise`;
   the mimic leans toward `momentum`/`gradient_descent`.
3. **Re-organization** — fold observed adversarial runs back into `H`
   (labeled by base algorithm), then classify *held-out* adversarial
   seeds: **1.00** (+0.21 over the un-augmented bank on the same seeds).

The honest lesson is in stage 3's design: the recovery came from
updating the *bank* (newly observed behavior folded into history) — the
`G_{t+1}` move — not from shrinking the feature set. A robust-features
variant exists (`fingerprint(ep, robust=True)`) and `ROBUST_NAMES`
documents which statistics are scale-free.

## Boundaries

- Synthetic agents only. Claiming BRO can identify real-world algorithms
  is premature until this benchmark transfers: the progression is
  synthetic → realistic microstructure sim → anonymized real flow.
- The classifier is deliberately dumb (kNN in z-scored feature space) —
  the experiment tests whether the *fingerprint* carries the
  information, not whether a model can squeeze it out.
- `prev_move` handed to agents is the shared observable (the tape);
  agents never see each other.

## Run it

```bash
python examples/bro_fingerprint_demo.py   # three stages + confusion matrices
python tests/test_bro.py                  # 7 checks
```
