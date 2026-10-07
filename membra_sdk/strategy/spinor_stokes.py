"""SpinorStokes — the redefined strategy.

Signal model (redefinition, in one breath):

    A bivariate time series z(t) = (z1(t), z2(t)) is a Jones vector.
    Its instantaneous Stokes parameters

        S0 = |z1|^2 + |z2|^2        total intensity
        S1 = |z1|^2 - |z2|^2        linear polarization  (H vs V)
        S2 = 2 Re(conj(z1) z2)      linear polarization  (+45 vs -45)
        S3 = 2 Im(conj(z1) z2)      circular polarization (helicity)

    measure how coherent the two channels are. Normalized,
    s = (S1,S2,S3)/S0 sits on the Poincare sphere; its magnitude
    Pi = |s| is the degree of polarization in [0,1].

    The normalized Jones vector psi = (z1,z2)/sqrt(S0) IS the spinor:
    Bloch coordinates of psi are exactly (S2, S3, S1)/S0 under the Pauli
    map s_i = psi^dagger sigma_i psi. So "spinor" and "Stokes" are the
    same object seen from S^3 and S^2 — that Hopf-fibration identity is
    the redefinition this strategy trades on.

Decision rule (redefined):
    Pi  -> regime coherence: only trade when the state is polarized.
    s3  -> helicity sign: >0 long, <0 short (this strategy's convention).
           For a true bivariate pair, s3's sign IS the lead/lag direction
           between channels — the tradable intermarket read. For the
           univariate delay embedding the sign is structural (the delay
           trajectory circulates one way); there s3's *magnitude* is the
           signal and direction must come from elsewhere.
    turning of s on the sphere -> state instability -> shrink size.

Embeddings. The Jones pair needs two *complex* channels, so each real
channel is first lifted to its analytic signal via the Hilbert transform:

    bivariate input (x1, x2)   ->  Jones = (A[x1], A[x2])
    univariate input x         ->  Jones = (A[x], A[x shifted by lag])

The naive univariate pair (x, H[x]) is degenerate: A[H[x]] = -i*A[x], so
the cross term is purely imaginary with fixed sign — always fully
circular, carrying no information. Delay embedding is the standard fix:
the lag sets a phase reference and the helicity sign then reads whether
the (x_t, x_{t-tau}) trajectory circulates forward or backward — i.e.
rotation direction, which is what s3 actually measures.

Pure stdlib — no numpy dependency.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Hilbert transform (pure-python radix-2 FFT; O(n log n), fine for windows)
# ---------------------------------------------------------------------------


def _fft(x: list[complex], inverse: bool = False) -> list[complex]:
    n = len(x)
    if n == 1:
        return x[:]
    if n % 2:
        raise ValueError("fft requires power-of-two length")
    even = _fft(x[0::2], inverse)
    odd = _fft(x[1::2], inverse)
    sign = 1 if inverse else -1
    out = [0j] * n
    for k in range(n // 2):
        t = cmath.exp(sign * 2j * math.pi * k / n) * odd[k]
        out[k] = even[k] + t
        out[k + n // 2] = even[k] - t
    if inverse:
        return [v / 2 for v in out]  # 1/2 per level => 1/n overall
    return out


def _next_pow2(n: int) -> int:
    p = 1
    while p < n:
        p <<= 1
    return p


def hilbert(x: list[float]) -> list[complex]:
    """Analytic signal a(t) = x(t) + i*H[x](t) via FFT."""
    n = len(x)
    m = _next_pow2(max(n, 2))
    spec = _fft([complex(v, 0.0) for v in x] + [0j] * (m - n))
    h = [0.0] * m
    h[0] = 1.0
    if m % 2 == 0:
        h[m // 2] = 1.0
        for i in range(1, m // 2):
            h[i] = 2.0
    else:
        for i in range(1, (m + 1) // 2):
            h[i] = 2.0
    analytic = _fft([spec[i] * h[i] for i in range(m)], inverse=True)
    return analytic[:n]


# ---------------------------------------------------------------------------
# Stokes parameters of a complex pair
# ---------------------------------------------------------------------------


@dataclass
class Stokes:
    """The four Stokes parameters of one (z1, z2) sample or window mean."""

    s0: float
    s1: float
    s2: float
    s3: float

    @property
    def degree(self) -> float:
        """Degree of polarization Pi = |s| / S0 in [0,1]."""
        if self.s0 <= 0:
            return 0.0
        return min(1.0, math.sqrt(self.s1**2 + self.s2**2 + self.s3**2) / self.s0)

    @property
    def normalized(self) -> tuple[float, float, float]:
        """Point on the Poincare sphere (s1,s2,s3)/S0 — length = Pi."""
        if self.s0 <= 0:
            return (0.0, 0.0, 0.0)
        return (self.s1 / self.s0, self.s2 / self.s0, self.s3 / self.s0)


def stokes(z1: complex, z2: complex) -> Stokes:
    """Instantaneous Stokes parameters of a Jones pair (z1, z2)."""
    i1 = (z1.conjugate() * z1).real
    i2 = (z2.conjugate() * z2).real
    cross = z1.conjugate() * z2
    return Stokes(
        s0=i1 + i2,
        s1=i1 - i2,
        s2=2.0 * cross.real,
        s3=2.0 * cross.imag,
    )


def stokes_mean(samples: list[tuple[complex, complex]]) -> Stokes:
    """Windowed Stokes = element-wise mean of instantaneous parameters."""
    n = len(samples)
    if n == 0:
        return Stokes(0.0, 0.0, 0.0, 0.0)
    acc = Stokes(0.0, 0.0, 0.0, 0.0)
    for z1, z2 in samples:
        s = stokes(z1, z2)
        acc = Stokes(acc.s0 + s.s0, acc.s1 + s.s1, acc.s2 + s.s2, acc.s3 + s.s3)
    return Stokes(acc.s0 / n, acc.s1 / n, acc.s2 / n, acc.s3 / n)


# ---------------------------------------------------------------------------
# Spinor lift — S^3 (spinor) <-> S^2 (Poincare sphere)
# ---------------------------------------------------------------------------


def jones_to_spinor(z1: complex, z2: complex) -> tuple[complex, complex]:
    """Normalized Jones vector = the spinor (mod global phase)."""
    norm = math.sqrt(abs(z1) ** 2 + abs(z2) ** 2)
    if norm == 0:
        return (0j, 0j)
    return (z1 / norm, z2 / norm)


def spinor_bloch(psi: tuple[complex, complex]) -> tuple[float, float, float]:
    """Bloch vector psi^dagger sigma psi = (S2, S3, S1)/S0 on the sphere."""
    a, b = psi
    x = 2.0 * (a.conjugate() * b).real
    y = 2.0 * (a.conjugate() * b).imag
    z = abs(a) ** 2 - abs(b) ** 2
    return (x, y, z)


def spinor_lift(sx: float, sy: float, sz: float) -> tuple[complex, complex]:
    """Inverse Hopf map: point on the Bloch/Poincare sphere -> spinor in C^2.

    psi = (sqrt((1+sz)/2), (sx + i*sy) / sqrt(2(1+sz)))
    Undefined at the south pole (sz=-1); caller clamps degenerate states.
    """
    if sz <= -0.999999:
        return (0j, 1 + 0j)
    a = math.sqrt((1.0 + sz) / 2.0)
    denom = math.sqrt(2.0 * (1.0 + sz))
    b = complex(sx, sy) / denom
    return (complex(a, 0.0), b)


def pancharatnam_phase(
    psi_a: tuple[complex, complex], psi_b: tuple[complex, complex]
) -> float:
    """Geometric phase arg(<psi_a | psi_b>) between two spinor states."""
    inner = psi_a[0].conjugate() * psi_b[0] + psi_a[1].conjugate() * psi_b[1]
    return cmath.phase(inner) if abs(inner) > 0 else 0.0


def sphere_turn(
    s_a: tuple[float, float, float], s_b: tuple[float, float, float]
) -> float:
    """Geodesic angle between two normalized Stokes points."""
    dot = sum(a * b for a, b in zip(s_a, s_b))
    na = math.sqrt(sum(v * v for v in s_a))
    nb = math.sqrt(sum(v * v for v in s_b))
    if na == 0 or nb == 0:
        return math.pi / 2  # depolarized: treat as maximal instability
    return math.acos(max(-1.0, min(1.0, dot / (na * nb))))


# ---------------------------------------------------------------------------
# The strategy
# ---------------------------------------------------------------------------


@dataclass
class Signal:
    """One bar's decision."""

    t: int
    action: str  # "long" | "short" | "flat"
    size: float  # signed fraction in [-1, 1]
    pi: float  # polarization degree
    s_hat: tuple[float, float, float]  # normalized Stokes on the sphere
    turn: float  # geodesic turn since previous state (radians)
    phase: float  # Pancharatnam phase drift since previous state


class SpinorStokesStrategy:
    """Trade the polarization state of a bivariate series.

    Parameters
    ----------
    window : int
        Rolling window over which Stokes parameters are averaged.
    pi_enter : float
        Minimum degree of polarization to hold a position.
    pi_exit : float
        Drop below this and the position flattens (hysteresis band).
    max_turn : float
        If the state turns faster than this per bar, halve the size.
    """

    def __init__(
        self,
        window: int = 16,
        pi_enter: float = 0.55,
        pi_exit: float = 0.30,
        max_turn: float = 0.5,
    ) -> None:
        if pi_exit >= pi_enter:
            raise ValueError("pi_exit must be < pi_enter (hysteresis band)")
        self.window = window
        self.pi_enter = pi_enter
        self.pi_exit = pi_exit
        self.max_turn = max_turn
        self._buf: list[tuple[complex, complex]] = []
        self._in_market = False
        self._prev_hat: tuple[float, float, float] | None = None
        self._prev_psi: tuple[complex, complex] | None = None

    def feed(self, z1: complex, z2: complex) -> Signal:
        """Ingest one (z1, z2) sample; emit the current bar's signal."""
        self._buf.append((z1, z2))
        t = len(self._buf) - 1
        if len(self._buf) < self.window:
            return Signal(t, "flat", 0.0, 0.0, (0.0, 0.0, 0.0), 0.0, 0.0)

        s = stokes_mean(self._buf[-self.window :])
        pi = s.degree
        hat = s.normalized
        # Bloch coords for the spinor lift are a permutation of Stokes:
        # (sx,sy,sz) = (S2,S3,S1)/S0 — see module docstring.
        psi = (
            spinor_lift(s.s2 / s.s0, s.s3 / s.s0, s.s1 / s.s0)
            if s.s0 > 0
            else (1 + 0j, 0j)
        )

        turn = sphere_turn(self._prev_hat, hat) if self._prev_hat else 0.0
        phase = pancharatnam_phase(self._prev_psi, psi) if self._prev_psi else 0.0
        self._prev_hat, self._prev_psi = hat, psi

        # hysteresis on Pi
        if not self._in_market and pi >= self.pi_enter:
            self._in_market = True
        elif self._in_market and pi <= self.pi_exit:
            self._in_market = False

        if not self._in_market:
            return Signal(t, "flat", 0.0, pi, hat, turn, phase)

        # redefined direction: helicity s3 sets long/short bias
        action = "long" if s.s3 >= 0 else "short"
        size = math.copysign(pi, 1.0 if s.s3 >= 0 else -1.0)
        if turn > self.max_turn:
            size *= 0.5  # state is spinning — halve exposure
        return Signal(t, action, size, pi, hat, turn, phase)

    def run(
        self,
        series1: list[float],
        series2: list[float] | None = None,
        lag: int | None = None,
    ) -> list[Signal]:
        """Run over real channel(s); Hilbert-lift each to its analytic signal.

        Pass `series2` for a true bivariate signal. Omit it for a
        univariate series, embedded as the delay pair (x_t, x_{t-lag});
        lag defaults to a quarter window.
        """
        x1 = [float(complex(v).real) for v in series1]
        if series2 is None:
            lag = lag or max(2, self.window // 4)
            pad = [x1[0]] * lag  # hold first value before the delay starts
            x2 = pad + x1[:-lag] if lag < len(x1) else pad + [x1[0]] * (len(x1) - lag)
        else:
            x2 = [float(complex(v).real) for v in series2]
        a1, a2 = hilbert(x1), hilbert(x2)
        return [self.feed(z1, z2) for z1, z2 in zip(a1, a2)]
