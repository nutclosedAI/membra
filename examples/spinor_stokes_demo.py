#!/usr/bin/env python3
"""
Example: SpinorStokes — arXiv LaTeX -> research trace -> trading signal.

Two modes:

  python3 examples/spinor_stokes_demo.py
      Offline. Runs the redefined strategy on a synthetic bivariate pair
      with three regimes (channel 2 leads -> incoherent -> channel 2 lags)
      and scores the helicity convention against the true lead/lag sign.

  python3 examples/spinor_stokes_demo.py --arxiv 'all:"Stokes parameters" AND all:spinor'
      Live. Harvests arXiv e-prints, converts the first paper's .tex
      into a StrategySpec, emits the generated strategy skeleton, and
      writes the stage-1 ResearchTrace + compiled LLM-B prompt into
      the corpus directory.
"""

import argparse
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from membra_sdk.strategy.arxiv_harvest import harvest
from membra_sdk.strategy.latex2strategy import LatexStrategyConverter
from membra_sdk.strategy.research_trace import compile_prompt
from membra_sdk.strategy.spinor_stokes import SpinorStokesStrategy


def synthetic_pair(n: int = 180, seed: int = 7):
    """Two channels sharing a latent wave; channel 2 leads, decorrelates, lags.

    Regimes: t<60 ch2 leads ch1 by +3 samples (s3>0), 60-119 ch2 is
    independent noise (low Pi), t>=120 ch2 lags ch1 by -3 (s3<0).
    Returns (ch1, ch2, truth) with truth[t] in {+1, 0, -1} = the injected
    lead/lag sign a correct helicity read should recover.
    """
    rng = random.Random(seed)
    omega = 2 * math.pi / 18.0
    latent = [math.sin(omega * t) + rng.gauss(0, 0.10) for t in range(-4, n + 4)]
    ch1, ch2, truth = [], [], []
    for t in range(n):
        L = latent[t + 4]
        ch1.append(L + rng.gauss(0, 0.08))
        if t < 60:
            ch2.append(latent[t + 4 + 3] + rng.gauss(0, 0.08))
            truth.append(1)
        elif t < 120:
            ch2.append(rng.gauss(0, 1.0))
            truth.append(0)
        else:
            ch2.append(latent[t + 4 - 3] + rng.gauss(0, 0.08))
            truth.append(-1)
    return ch1, ch2, truth


def run_offline() -> None:
    print("=" * 70)
    print("  SPINOR-STOKES — redefined strategy, offline synthetic run")
    print("=" * 70)
    print()
    print("Bivariate pair: Jones = (A[ch1], A[ch2]) via Hilbert lift")
    print("Gate: Pi >= 0.55 enters, Pi <= 0.30 exits. Direction: sign(s3)")
    print("  s3 > 0 means ch2 leads ch1 (long);  s3 < 0 means ch2 lags (short)")
    print()

    ch1, ch2, truth = synthetic_pair()
    strat = SpinorStokesStrategy(window=16, pi_enter=0.55, pi_exit=0.30)
    signals = strat.run(ch1, ch2)

    # per-regime report
    print(f"{'regime':<22}{'in-market%':>11}{'mean Pi':>9}{'long%':>7}{'short%':>8}")
    for lo, hi, name in [
        (0, 60, "ch2 leads (risk-on)"),
        (60, 120, "incoherent"),
        (120, 180, "ch2 lags (risk-off)"),
    ]:
        seg = signals[lo:hi]
        inm = [s for s in seg if s.action != "flat"]
        mean_pi = sum(s.pi for s in seg) / len(seg)
        longs = sum(1 for s in inm if s.action == "long")
        shorts = sum(1 for s in inm if s.action == "short")
        print(
            f"{name:<22}{100.0 * len(inm) / len(seg):>10.0f}%"
            f"{mean_pi:>9.2f}{100.0 * longs / max(len(inm), 1):>6.0f}%"
            f"{100.0 * shorts / max(len(inm), 1):>6.0f}%"
        )

    # direction accuracy where the strategy is in-market and truth exists
    scored = [
        (s, truth[s.t]) for s in signals if s.action != "flat" and truth[s.t] != 0
    ]
    hits = sum(1 for s, d in scored if (s.action == "long") == (d > 0))
    print()
    print(
        f"Direction accuracy on scored bars: {hits}/{len(scored)}"
        f" = {100.0 * hits / max(len(scored), 1):.0f}%  (sign(s3) vs true lead/lag sign)"
    )

    print()
    print("first in-market signals:")
    shown = 0
    for s in signals:
        if s.action != "flat" and shown < 12:
            print(
                f"  t={s.t:>3}  {s.action:<5} size={s.size:+.2f}  "
                f"Pi={s.pi:.2f}  s_hat=({s.s_hat[0]:+.2f},{s.s_hat[1]:+.2f},{s.s_hat[2]:+.2f})"
                f"  turn={s.turn:.2f}  phase={s.phase:+.2f}"
            )
            shown += 1


def run_arxiv(query: str, corpus_dir: str) -> None:
    print("=" * 70)
    print("  SPINOR-STOKES — live arXiv harvest -> trace -> prompt")
    print("=" * 70)
    print(f"query: {query!r}   corpus: {corpus_dir}")
    print()

    results = harvest(query, corpus_dir, max_results=3)
    for r in results:
        tag = (
            f"{len(r.tex_files)} tex files"
            if r.tex_files
            else f"SKIP: {r.skipped_reason}"
        )
        print(f"  {r.paper.arxiv_id:<22} {r.paper.title[:52]:<52} {tag}")

    convertible = [r for r in results if r.tex_files]
    if not convertible:
        print("\nno LaTeX sources harvested — try a different query")
        return

    conv = LatexStrategyConverter(name="SpinorStokes")
    first = convertible[0]
    spec = conv.convert(
        first.tex_files, arxiv_id=first.paper.arxiv_id, title=first.paper.title
    )
    print()
    print(
        f"converted {first.paper.arxiv_id}: {len(spec.equations)} equations, "
        f"{len(spec.mapped)} mapped to primitives, {len(spec.unmapped)} unmapped"
    )
    for m in spec.mapped[:8]:
        print(f"    {m.primitive:<22} [{m.confidence}] {m.equation.raw[:60]}")

    trace = conv.to_trace(
        spec, question="Spinor/Stokes formulation of the signal state"
    )
    trace.decisions.append("helicity sign(s3) -> long/short bias (strategy convention)")
    trace.uncertainties.append("unmapped equations may carry the risk-scaling terms")
    out = Path(corpus_dir) / first.paper.arxiv_id.replace("/", "_")
    trace_path = trace.save(out / "research_trace.json")
    skeleton = conv.emit_python(spec)
    (out / "generated_strategy.py").write_text(skeleton)
    prompt_path = out / "llm_b_prompt.txt"
    prompt_path.write_text(compile_prompt(trace))
    print()
    print(f"trace -> {trace_path}")
    print(f"skeleton -> {out / 'generated_strategy.py'}")
    print(f"LLM-B prompt -> {prompt_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--arxiv", metavar="QUERY", help="live harvest with this arXiv query"
    )
    ap.add_argument("--corpus", default="corpus_arxiv", help="corpus directory")
    args = ap.parse_args()
    if args.arxiv:
        run_arxiv(args.arxiv, args.corpus)
    else:
        run_offline()


if __name__ == "__main__":
    main()
