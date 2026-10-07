"""latex2strategy — convert extracted LaTeX math into a strategy spec.

Stage 2 of the pipeline:

    .tex files  ->  equation/definition extraction  ->  primitive mapping
                ->  StrategySpec  ->  compilable Python skeleton
                ->  ResearchTrace evidence rows (claims + artifacts)

The converter does not try to "compile LaTeX" in general. It recognizes a
registry of strategy primitives by their LaTeX signatures (Stokes vector,
spinor state, polarization degree, Berry phase, ...), links every matched
equation to the primitive it implements, and parks everything unmatched
as `unmapped` evidence for the next LLM in the chain to resolve.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .research_trace import Claim, Evidence, ResearchTrace, Source

# Math environments we extract, in priority order.
_MATH_ENVS = [
    "equation\\*?",
    "align\\*?",
    "gather\\*?",
    "multline\\*?",
    "displaymath",
    "eqnarray\\*?",
]

_INLINE_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)


@dataclass
class ExtractedEquation:
    """One display-math block lifted out of a .tex file."""

    raw: str
    env: str
    source_file: str
    symbols: list[str] = field(default_factory=list)


@dataclass
class PrimitiveMatch:
    """An equation mapped onto a known strategy primitive."""

    primitive: str
    equation: ExtractedEquation
    signature_hit: str
    confidence: str  # "high" | "medium" | "low"


@dataclass
class StrategySpec:
    """The converted strategy: what the paper gives us, wired or not."""

    name: str
    arxiv_id: str
    title: str
    equations: list[ExtractedEquation]
    mapped: list[PrimitiveMatch]
    unmapped: list[ExtractedEquation]
    parameters: dict[str, float] = field(default_factory=dict)

    def to_trace_rows(self) -> tuple[list[Evidence], list[str]]:
        """Evidence rows + open questions for the research trace."""
        evidence = [
            Evidence(
                ref=f"E{i}",
                source_ref=self.arxiv_id,
                statement=f"Equation implements primitive '{m.primitive}'",
                artifact=f"{m.equation.env}: {m.equation.raw[:160]}",
            )
            for i, m in enumerate(self.mapped, 1)
        ]
        open_qs = [
            f"Unmapped equation in {e.source_file} ({e.env}): {e.raw[:120]}"
            for e in self.unmapped[:10]
        ]
        return evidence, open_qs


# ---------------------------------------------------------------------------
# Primitive registry — LaTeX signature -> strategy primitive
# ---------------------------------------------------------------------------

# Each entry: primitive name, regexes over (expanded) equation text, and the
# confidence a hit earns. Signatures are intentionally structural: they match
# the *form* of the math, not the prose around it.
_PRIMITIVES: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "stokes_intensity",
        [
            (r"S_?0\s*=.*\|", "high"),
            (r"S_?0\s*=.*\^2\s*\+", "high"),
        ],
    ),
    (
        "stokes_vector",
        [
            (r"S_?[123].*=.*(Re|Im|\\mathrm\{Re\}|\\text\{Re\})", "high"),
            (r"\\vec\{?S|(\\begin\{pmatrix\}.*S)", "medium"),
            (r"S_?[123]\s*=", "low"),
        ],
    ),
    (
        "polarization_degree",
        [
            (r"(\\Pi|\\mathcal\{?P\}?|P_?\{?pol)\s*=.*\\sqrt", "high"),
            (r"degree of polarization", "medium"),
        ],
    ),
    (
        "spinor_state",
        [
            (r"\\psi|spinor|\\chi.*\\binom", "medium"),
            (r"SU\(2\)|\\sigma_?[xyz123]", "medium"),
        ],
    ),
    (
        "berry_phase",
        [
            (r"\\gamma.*(\\oint|\\oint?\\s*d|Berry|geometric phase)", "high"),
            (r"Pancharatnam", "high"),
            (r"\\Omega.*solid angle", "medium"),
        ],
    ),
    (
        "hilbert_transform",
        [
            (r"Hilbert|\\mathcal\{H\}", "high"),
            (r"analytic signal", "high"),
        ],
    ),
    (
        "windowed_estimator",
        [
            (r"\\frac\{?1\}?\{?[NT]\}?\\sum", "medium"),
            (r"\\langle.*\\rangle.*=.*\\sum", "low"),
        ],
    ),
]


class LatexStrategyConverter:
    """Parse .tex sources and map their math onto strategy primitives."""

    def __init__(self, name: str = "SpinorStokes") -> None:
        self.name = name
        self._env_re = re.compile(
            r"\\begin\{(" + "|".join(_MATH_ENVS) + r")\}(.+?)\\end\{\1\}",
            re.DOTALL,
        )
        self._newcommand_re = re.compile(
            r"\\(?:re)?newcommand\*?\s*\{(\\[A-Za-z]+)\}(?:\[\d+\])?\s*\{([^}]*)\}"
        )
        self._def_re = re.compile(r"\\def\s*(\\[A-Za-z]+)\s*\{([^}]*)\}")

    # -- extraction ---------------------------------------------------------

    def _expand_macros(self, text: str) -> str:
        """Expand user macros so signatures see through \\Sone etc."""
        macros: dict[str, str] = {}
        for m in self._newcommand_re.finditer(text):
            macros[m.group(1)] = m.group(2)
        for m in self._def_re.finditer(text):
            macros[m.group(1)] = m.group(2)
        for _ in range(3):  # shallow fixpoint for nested macros
            for name, body in macros.items():
                text = text.replace(name, body)
        return text

    @staticmethod
    def _symbols(eq: str) -> list[str]:
        return sorted(set(re.findall(r"\\[a-zA-Z]+|[A-Za-z]_\{?\\?\w+\}?", eq)))

    def parse_tex(self, text: str, source_file: str = "") -> list[ExtractedEquation]:
        """Extract all display-math blocks from one .tex document."""
        expanded = self._expand_macros(text)
        out: list[ExtractedEquation] = []
        for m in self._env_re.finditer(expanded):
            env = m.group(1).rstrip("*")
            raw = " ".join(m.group(2).split())
            if raw:
                out.append(ExtractedEquation(raw, env, source_file, self._symbols(raw)))
        for m in _INLINE_RE.finditer(expanded):
            raw = " ".join(m.group(1).split())
            if raw:
                out.append(
                    ExtractedEquation(
                        raw, "displaymath", source_file, self._symbols(raw)
                    )
                )
        return out

    # -- mapping ------------------------------------------------------------

    def _match(self, eq: ExtractedEquation) -> PrimitiveMatch | None:
        for primitive, sigs in _PRIMITIVES:
            for pattern, confidence in sigs:
                if re.search(pattern, eq.raw):
                    return PrimitiveMatch(primitive, eq, pattern, confidence)
        return None

    def convert_from_text(
        self,
        text: str,
        source_file: str = "<text>",
        arxiv_id: str = "",
        title: str = "",
    ) -> StrategySpec:
        """Convert a raw LaTeX string (no files) — used by tests and in-memory callers."""
        equations = self.parse_tex(text, source_file)
        mapped: list[PrimitiveMatch] = []
        unmapped: list[ExtractedEquation] = []
        for eq in equations:
            hit = self._match(eq)
            (mapped.append(hit) if hit else unmapped.append(eq))
        return StrategySpec(
            name=self.name,
            arxiv_id=arxiv_id,
            title=title,
            equations=equations,
            mapped=mapped,
            unmapped=unmapped,
            parameters={},
        )

    def convert(
        self,
        tex_files: list[Path | str],
        arxiv_id: str = "",
        title: str = "",
    ) -> StrategySpec:
        """Extract + map every .tex file into one StrategySpec."""
        equations: list[ExtractedEquation] = []
        for f in tex_files:
            path = Path(f)
            equations.extend(self.parse_tex(path.read_text(errors="ignore"), path.name))

        mapped: list[PrimitiveMatch] = []
        unmapped: list[ExtractedEquation] = []
        for eq in equations:
            hit = self._match(eq)
            (mapped.append(hit) if hit else unmapped.append(eq))

        return StrategySpec(
            name=self.name,
            arxiv_id=arxiv_id,
            title=title,
            equations=equations,
            mapped=mapped,
            unmapped=unmapped,
            parameters={},
        )

    def to_trace(self, spec: StrategySpec, question: str) -> ResearchTrace:
        """Wrap a conversion as stage-1 research trace rows."""
        trace = ResearchTrace(question=question, stage=1)
        trace.sources.append(
            Source(
                ref=spec.arxiv_id or "S1",
                locator=spec.arxiv_id or "local corpus",
                source_type="primary",
                authority="paper",
                note=spec.title,
            )
        )
        evidence, open_qs = spec.to_trace_rows()
        trace.evidence.extend(evidence)
        trace.open_questions.extend(open_qs)
        trace.claims.extend(
            Claim(
                ref=f"C{i}",
                statement=f"Primitive '{m.primitive}' is present in source",
                evidence_refs=[e.ref],
                status="supported" if m.confidence == "high" else "interpretation",
            )
            for i, (m, e) in enumerate(zip(spec.mapped, evidence), 1)
        )
        return trace

    # -- codegen ------------------------------------------------------------

    def emit_python(self, spec: StrategySpec) -> str:
        """Emit a compilable Python skeleton wiring the mapped primitives.

        Unmapped equations are left as TODO comments — the exact surface a
        second-stage LLM should resolve instead of guessing.
        """
        mapped_names = sorted({m.primitive for m in spec.mapped})
        lines = [
            '"""Generated strategy spec — do not edit by hand."""',
            "from membra_sdk.strategy.spinor_stokes import (",
            "    SpinorStokesStrategy,",
            "    hilbert,",
            "    stokes,",
            "    stokes_mean,",
            "    spinor_lift,",
            "    pancharatnam_phase,",
            ")",
            "",
            "",
            "def build_strategy():",
            f'    """Strategy redefined from arXiv:{spec.arxiv_id or "?"} — {spec.title or "untitled"}."""',
            "    return SpinorStokesStrategy()",
            "",
            f"# mapped primitives: {', '.join(mapped_names) or 'none'}",
        ]
        for m in spec.mapped:
            lines.append(
                f"#   {m.primitive} [{m.confidence}] <- {m.equation.env}: "
                f"{m.equation.raw[:100]}"
            )
        for e in spec.unmapped[:15]:
            lines.append(f"# TODO(unmapped) {e.env}: {e.raw[:100]}")
        return "\n".join(lines) + "\n"
