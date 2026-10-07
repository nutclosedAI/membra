# SpinorStokes — the redefined strategy

Pipeline: **arXiv LaTeX → research trace → strategy spec → signal.**

```
arxiv_harvest      query arXiv, download e-prints, extract .tex
        │
latex2strategy     extract display math, map equations → primitives
        │
research_trace     stage-1 trace object (sources/evidence/claims/gaps)
        │
compile_prompt     TRACE → PROMPT for the next LLM in the chain
        │
spinor_stokes      the redefined strategy the spec points at
```

## The redefinition

A bivariate time series z(t) = (z₁, z₂) is a **Jones vector**. Its Stokes
parameters

```
S0 = |z1|² + |z2|²          total intensity
S1 = |z1|² − |z2|²          linear polarization   (H vs V)
S2 = 2 Re(z1* z2)           linear polarization   (+45° vs −45°)
S3 = 2 Im(z1* z2)           circular polarization (helicity)
```

measure channel coherence. Normalized, `s = (S1,S2,S3)/S0` lives on the
Poincaré sphere; its length `Π = |s|` is the degree of polarization.

The normalized Jones vector ψ = (z₁,z₂)/√S0 **is the spinor**: its Bloch
coordinates ψ†σψ are exactly (S2,S3,S1)/S0. Spinor and Stokes are one
object seen from S³ and S² — that Hopf-fibration identity is the
redefinition the strategy trades on.

## Decision rule

| Quantity | Reads | Trade meaning |
|---|---|---|
| Π | channel coherence | regime gate: enter ≥ 0.55, exit ≤ 0.30 (hysteresis) |
| sign(s3) | helicity = lead/lag direction | >0 long (ch2 leads), <0 short (ch2 lags) |
| Π | also position size | size = ±Π, halved when the state turns fast |
| `sphere_turn`, `pancharatnam_phase` | geodesic + geometric phase drift | instability → shrink exposure |

For a univariate series, `run()` delay-embeds x as (x_t, x_{t−τ}) — the
naive (x, H[x]) pair is degenerate (always fully circular). With delay
embedding Π still gates coherence, but s3's *sign* is structural; only a
genuine second channel gives s3 a tradable direction.

## LaTeX → strategy conversion

`LatexStrategyConverter` does not try to compile arbitrary LaTeX. It
extracts `equation/align/gather/…` blocks, expands `\newcommand` /
`\def` macros, and matches each equation against a registry of strategy
primitives by structural signature:

```
S_0 = |·|² + |·|²            → stokes_intensity
S_3 = 2 Im(z1* z2)           → stokes_vector
Π = √(...)/S₀                → polarization_degree
ψ, σ_i, SU(2)                → spinor_state
γ = ∮ A·dλ, Berry phase      → berry_phase
H, analytic signal           → hilbert_transform
(1/N)Σ, ⟨·⟩ estimators       → windowed_estimator
```

Mapped equations wire into `StrategySpec.mapped` (with confidence);
unmapped equations are parked verbatim — they are the exact surface the
next LLM in the chain should resolve, not silently dropped. `emit_python`
generates a compilable strategy skeleton with unmapped equations as
`# TODO(unmapped)` comments.

## The research trace

Every conversion produces a stage-1 `ResearchTrace` — the observable
procedure, not a conclusion: which paper, which equations mapped, which
claims that supports, which equations stayed unmapped (→ open questions),
and the strategy's own assumptions. `compile_prompt(trace)` emits the
second-stage analyst package for LLM B:

> Reconstruct the strongest argument. Separate observed facts from
> interpretation. Identify unsupported assumptions. Prefer
> disconfirmation. Produce RESEARCH STATE / CRITICAL REVIEW / REVISED
> HYPOTHESIS / FALSIFICATION TEST / NEXT BEST OBSERVATION / CONFIDENCE.

The chain is recursive: LLM B's critique is itself a trace — what it
observed, inferred, could not verify, and would test next — passed to
the next stage.

## Layout

```
membra_sdk/strategy/
    arxiv_harvest.py     ArxivPaper, query_arxiv, fetch_eprint, harvest
    latex2strategy.py    LatexStrategyConverter, StrategySpec
    research_trace.py    ResearchTrace, compile_prompt
    spinor_stokes.py     SpinorStokesStrategy, Stokes, hilbert, spinor_lift
examples/spinor_stokes_demo.py
tests/test_spinor_stokes.py
```

## Run it

```bash
# offline: synthetic lead/lag regimes
python examples/spinor_stokes_demo.py

# live: harvest -> convert -> trace + LLM-B prompt + skeleton
python examples/spinor_stokes_demo.py \
    --arxiv 'all:"Stokes parameters" AND all:spinor'

python tests/test_spinor_stokes.py
```

## Caveats

- sign(s3) → long/short is a **convention**: it says which channel leads,
  not which direction price moves. Alpha requires a lead/lag pair where
  leadership predicts drift (e.g. correlated instruments, not noise).
- The estimator is a 16-sample window: Π of incoherent noise has wide
  variance — hysteresis exists precisely because gating is noisy.
- Univariate delay embedding is a regime/coherence read, not a direction
  read.
- Everything is stdlib Python (no numpy) — research-grade reference, not
  a production execution path.
