# BRO Economic State Graph — specification

**Outcome Transition Infrastructure.**

Clearing asks: *should this obligation be allowed to settle?*
BRO asks the harder next question: *what does the settled economic act
mean after the world continues changing?*

The neighborhood is being named and formalized elsewhere — agentic
clearing (RAILS: Obligation Object / Evidence Envelope / Verification
Mesh / Clearing Passport), settlement-time finality (IETF
draft-das-payment-execution-finality: sink binding, replay protection,
protected state). BRO does not compete there. It operates **one layer
above**: the record of an economic act stays alive after settlement,
and verified outcomes generate the next economic state.

```
INTENT -> OBLIGATION -> EVIDENCE -> CLEARING -> AUTHORIZATION
    -> SETTLEMENT -> OUTCOME OBSERVATION -> OUTCOME EVALUATION
    -> STATE TRANSITION -> NEW ECONOMIC CONSEQUENCE -> (repeat)
```

## Core law

`S_t != FINAL`. Settlement is one state, not a terminal node:

    $50 -> SETTLED -> FULFILLMENT OBSERVED -> OUTCOME EVALUATED
        -> PARTIAL -> $12 COMPENSATION ENTITLEMENT
        -> NEW PAYMENT -> NEW OUTCOME

The transition function:

    X_{t+1} = F(X_t, E_t, O_t, P_t)

`X` economic state · `E` new evidence · `O` evaluated outcome ·
`P` governing policy. Money becomes a stateful process.

## Objects (`membra_sdk/economy/`)

### EconomicStateObject (state.py)

The canonical record — every field is a section of the living act:

```
economic_act_id:  EA_xxxxxxxx
parent_act_id:    EA_xxxxxxxx | null        # set when spawned by consequence
promise:          { type, conditions[], deadline, terms }
authorization:    { max_value, currency, capability_id, authorized_by }
settlement:       { amount, status, settled_at }
observation:      { values{}, observed_at, source }
outcome:          { state, confidence, vector }
consequence:      { type, amount, currency, reason, next_act_id }
causal_log:       [ { stage, at, ... } ]    # append-only, every mutation
```

Settlement statuses: `PENDING AUTHORIZED HELD SETTLED RELEASED RETURNED DISPUTED`.
Outcome states: `UNKNOWN FULFILLED PARTIALLY_FULFILLED FAILED`.
Consequence types: `NONE COMPENSATION PARTIAL_RELEASE REFUND DISPUTE PENALTY`.

### OutcomeVector (outcome.py)

Outcomes are multidimensional, `O = (Q, T, C, R, D, U)`:

| dim | meaning |
|---|---|
| Q quality       | how good the delivered thing was |
| T timeliness    | 1.0 on time; decays with observed lateness |
| C completeness  | fraction of promise conditions met |
| R reliability   | consistency of counterparty / evidence source |
| D deviation     | magnitude of the promise-vs-reality gap |
| U uncertainty   | 1 − confidence in the evaluation |

`evaluate_outcome(eso)` scores conditions against `observation.values`,
and confidence scales with evidence coverage × source reliability.
Payment logic becomes `f(Q,T,C,R)` instead of `f(completed)`.

### Policy + transition (transitions.py)

`transition(eso, policy)` classifies the outcome and applies rules —
each is a policy knob, not hardcoded law:

- `FULFILLED` → consequence `NONE`; `HELD` funds `RELEASED` in full
- `PARTIALLY_FULFILLED` →
  `SETTLED`: `COMPENSATION = amount × deviation × compensation_rate`
  (default rate 0.25), spawning a child act
  `HELD`: `PARTIAL_RELEASE` of `amount × completeness`, rest `RETURNED`
- `FAILED` → `HELD`: `RETURNED`; `SETTLED`: `DISPUTED` + spawned dispute act
- `UNKNOWN` or `confidence < min_confidence` → deferred (act stays open)

### Capability (capability.py)

Constrained economic agency — the agent isn't given purchasing power,
it's given a governed mandate:

```
budget, max_exposure, permitted_acts[], currency,
success_rule, evidence_required, outcome_check_required,
compensation_permitted, expires_at, revoked
```

`authorize(act_type, amount)` gates every intended obligation against
exposure, budget, type permission, expiry, and revocation;
`release(amount)` frees budget on conclusion; `revoke()` kills it.

### EconomicGraph (graph.py)

Registry of acts + consequence edges. `causal_chain(act_id)` returns
the stage list (`INTENT POLICY AUTHORITY SETTLEMENT OBSERVED OUTCOME
OUTCOME CLASSIFICATION CONSEQUENCE CURRENT STATE`) plus the parent
chain explaining why the act exists. `outcome_dataset()` exports
`D = {(P_i, E_i, O_i, C_i)}` — the promise-vs-reality substrate.

## Economic recursion

```
A -> B -> O -> C -> A_{t+1}
```

act → settlement → observed outcome → consequence → next act.
`Consequence.next_act_id` links the spawned act; `parent_act_id`
links back. `EconomicGraph` makes the recursion queryable.

## API surface (names map to module calls)

```
POST /promises            EconomicStateObject(promise=...)
POST /obligations         Capability.authorize / Authorization
POST /evidence            eso.observe / eso.record("EVIDENCE")
POST /observations        eso.observe
POST /outcomes/evaluate   evaluate_outcome
POST /state-transitions   transition
POST /consequences        eso.apply_consequence

GET  /acts/:id            eso.to_dict()
GET  /acts/:id/state      settlement.status + outcome.state
GET  /acts/:id/outcome    outcome vector + state + confidence
GET  /acts/:id/evidence   observation.values + causal_log
GET  /acts/:id/causal-chain   graph.causal_chain(act_id)
```

## What the graph learns at scale

Once thousands of state objects exist, `D` supports:

- which evidence sources are reliable (R calibration)
- which promises are unrealistic (systematic deviation)
- which agents overstate confidence (confidence vs realized outcomes)
- which merchants miss SLAs (per-source outcome vectors)
- which contracts produce predictable compensation (D × consequence)
- recurring temporal structure → economic archetypes, feeding
  `P(O_{t+τ} | EA_t, Φ_t, S_t)` — measured probabilistic outcome
  prediction that feeds back into authorization/risk/pricing.
  The `membra_sdk.bro` fingerprint machinery is the Φ extractor for it.

## Boundaries

- This is **not** a payment protocol, clearing layer, or
  conditional-payment system — it presumes those exist downstream
  (RAILS/IETF territory) and consumes their outputs as evidence.
- Consequence sizing is policy-governed and conservative by default;
  a damages schedule is a policy artifact, not a claim about law.
- Confidence gating (`min_confidence`) is deliberate: thin evidence
  defers transitions rather than manufacturing consequences.

## Run it

```bash
python examples/economy_demo.py   # the $100/6pm-delivery recursion
python tests/test_economy.py      # 7 checks
```
