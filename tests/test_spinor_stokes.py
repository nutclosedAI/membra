#!/usr/bin/env python3
"""Test suite for the strategy pipeline: spinor math, LaTeX conversion, traces."""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from membra_sdk.strategy.latex2strategy import LatexStrategyConverter
from membra_sdk.strategy.research_trace import ResearchTrace, compile_prompt
from membra_sdk.strategy.spinor_stokes import (
    SpinorStokesStrategy,
    hilbert,
    pancharatnam_phase,
    spinor_bloch,
    spinor_lift,
    stokes,
)


def test_stokes_linear_polarization():
    """(1,0) is pure H polarization: S1=S0, S2=S3=0, Pi=1."""
    s = stokes(1 + 0j, 0j)
    assert s.s0 == 1.0 and s.s1 == 1.0 and s.s2 == 0.0 and s.s3 == 0.0
    assert s.degree == 1.0
    print("✅ linear polarization: S1=S0, Pi=1")


def test_stokes_circular_polarization():
    """(1, i)/sqrt(2) is circular: S3=S0, Pi=1."""
    inv = 1 / math.sqrt(2)
    s = stokes(complex(inv), complex(0, inv))
    assert abs(s.s0 - 1.0) < 1e-9
    assert abs(s.s3 - 1.0) < 1e-9, f"s3={s.s3}"
    assert s.degree == 1.0
    print("✅ circular polarization: S3=S0, Pi=1")


def test_spinor_lift_roundtrip():
    """Hopf inverse then Bloch map recovers the sphere point."""
    sx, sy, sz = 0.3, 0.6, math.sqrt(1 - 0.09 - 0.36)
    psi = spinor_lift(sx, sy, sz)
    bx, by, bz = spinor_bloch(psi)
    assert abs(bx - sx) < 1e-9 and abs(by - sy) < 1e-9 and abs(bz - sz) < 1e-9
    assert abs(abs(psi[0]) ** 2 + abs(psi[1]) ** 2 - 1.0) < 1e-9
    print("✅ spinor lift round-trips: Bloch(psi) = input point")


def test_pancharatnam_same_state_zero():
    """A state against itself has zero geometric phase."""
    psi = spinor_lift(0.2, 0.5, 0.8)
    assert abs(pancharatnam_phase(psi, psi)) < 1e-9
    print("✅ Pancharatnam phase of identical states is 0")


def test_hilbert_quadrature():
    """Hilbert transform of sin(wt) is approx -cos(wt) (90 deg shift)."""
    n, w = 256, 2 * math.pi / 16
    x = [math.sin(w * t) for t in range(n)]
    a = hilbert(x)
    mid = range(32, n - 32)  # skip edges
    err = max(abs(a[t].imag - (-math.cos(w * t))) for t in mid)
    assert err < 0.05, f"quadrature error {err}"
    print("✅ Hilbert quadrature: H[sin] ~= -cos within 0.05")


def test_strategy_gates_noise():
    """Pure incoherent noise must stay mostly flat (low Pi)."""
    import random

    rng = random.Random(1)
    noise = [rng.gauss(0, 1) for _ in range(200)]
    strat = SpinorStokesStrategy(window=16, pi_enter=0.55, pi_exit=0.30)
    sigs = strat.run(noise)
    in_market = sum(1 for s in sigs if s.action != "flat")
    assert in_market / len(sigs) < 0.35, f"in-market {in_market}/{len(sigs)}"
    print(f"✅ noise regime mostly flat: {in_market}/{len(sigs)} bars in-market")


def test_strategy_reads_rotation():
    """Clean sinusoid should polarize and hold a consistent direction."""
    n, w = 200, 2 * math.pi / 18
    x = [math.sin(w * t) for t in range(n)]
    strat = SpinorStokesStrategy(window=16, pi_enter=0.55, pi_exit=0.30)
    sigs = strat.run(x)
    actions = [s.action for s in sigs if s.action != "flat"]
    assert len(actions) > len(sigs) * 0.5
    dominant = max(set(actions), key=actions.count)
    assert actions.count(dominant) / len(actions) > 0.7
    print(f"✅ sinusoid: {len(actions)} bars in-market, dominant={dominant}")


def test_converter_extracts_and_maps():
    tex = r"""
    \newcommand{\Sto}{S_0}
    \begin{equation}
      \Sto = |z_1|^2 + |z_2|^2
    \end{equation}
    \begin{align}
      S_3 &= 2\,\mathrm{Im}(z_1^* z_2) \\
      \gamma &= \oint \mathcal{A}\,d\lambda \quad \text{Berry phase}
    \end{align}
    \begin{equation}
      \int_0^\infty e^{-x} dx = 1
    \end{equation}
    """
    conv = LatexStrategyConverter()
    eqs = conv.parse_tex(tex, "main.tex")
    assert len(eqs) == 3
    spec = conv.convert_from_text(tex, "main.tex")
    prims = {m.primitive for m in spec.mapped}
    assert "stokes_intensity" in prims, prims
    assert "stokes_vector" in prims or "berry_phase" in prims, prims
    assert len(spec.unmapped) == 1  # the integral maps to nothing
    print("✅ converter maps Stokes/Berry equations, parks unmapped")


def test_emit_python_compiles():
    tex = "\\begin{equation} S_0 = |a|^2 + |b|^2 \\end{equation}"
    conv = LatexStrategyConverter()
    spec = conv.convert_from_text(tex)
    code = conv.emit_python(spec)
    compile(code, "<generated>", "exec")  # must be valid python
    print("✅ emitted skeleton compiles")


def test_trace_prompt_roundtrip():
    trace = ResearchTrace(question="q", objective="o", conclusion="c", stage=1)
    prompt = compile_prompt(trace)
    assert "SECOND-PASS ANALYSIS" in prompt and "CONFIDENCE" in prompt
    loaded = ResearchTrace.from_dict(json.loads(trace.to_json()))
    assert loaded.question == "q" and loaded.stage == 1
    print("✅ trace serializes and compiles into the LLM-B prompt")


if __name__ == "__main__":
    print("=" * 60)
    print("  SPINOR-STOKES STRATEGY PIPELINE TESTS")
    print("=" * 60)
    print()

    test_stokes_linear_polarization()
    test_stokes_circular_polarization()
    test_spinor_lift_roundtrip()
    test_pancharatnam_same_state_zero()
    test_hilbert_quadrature()
    test_strategy_gates_noise()
    test_strategy_reads_rotation()
    test_converter_extracts_and_maps()
    test_emit_python_compiles()
    test_trace_prompt_roundtrip()

    print()
    print("=" * 60)
    print("  ALL TESTS PASSED")
    print("=" * 60)
