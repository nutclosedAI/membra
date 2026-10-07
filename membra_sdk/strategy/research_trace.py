"""Research trace — the transferable object passed between LLMs.

Design contract (BRO recursive research architecture):

    LLM A  ->  research  ->  TRACE  ->  PROMPT  ->  LLM B  ->  critique
        ->  TRACE 2  ->  LLM C  ->  synthesis

What moves between models is not a conclusion, it is the *observable
research procedure*: which queries ran, which sources were selected, what
evidence each yielded, which claims it supports, where it contradicts,
what stays uncertain. The trace contains no hidden chain-of-thought —
only externally checkable artifacts.

`ResearchTrace` is the serializable object. `compile_prompt` turns a
trace into the second-stage-analyst instruction package for the next
model in the chain.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Trace schema — every field is an observable artifact, not a thought.
# ---------------------------------------------------------------------------


@dataclass
class SearchQuery:
    """One query that was actually issued."""

    query: str
    purpose: str  # why this query was selected


@dataclass
class Source:
    """One source that was actually consulted."""

    ref: str  # short handle used in claim/evidence links, e.g. "S1"
    locator: str  # arxiv id, url, file path
    source_type: str  # "primary" | "secondary" | "contradictory"
    authority: str  # "paper" | "docs" | "benchmark" | "code" | ...
    date: str = ""
    note: str = ""


@dataclass
class Evidence:
    """An observable fact extracted from a source."""

    ref: str  # e.g. "E3"
    source_ref: str  # links to Source.ref
    statement: str  # what the source establishes
    artifact: str = ""  # equation, table, code path proving it


@dataclass
class Claim:
    """Something the researcher asserts, backed by evidence refs."""

    ref: str  # e.g. "C2"
    statement: str
    evidence_refs: list[str] = field(default_factory=list)
    status: str = "supported"  # "supported" | "interpretation" | "contested"


@dataclass
class ResearchTrace:
    """The full transferable state of an investigation."""

    question: str
    objective: str = ""
    search_queries: list[SearchQuery] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    hypotheses: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    conclusion: str = ""
    next_actions: list[str] = field(default_factory=list)
    stage: int = 1  # which chain stage produced this trace

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, path: Path | str) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json())
        return p

    @classmethod
    def from_dict(cls, data: dict) -> ResearchTrace:
        d = dict(data)
        d["search_queries"] = [SearchQuery(**q) for q in d.get("search_queries", [])]
        d["sources"] = [Source(**s) for s in d.get("sources", [])]
        d["evidence"] = [Evidence(**e) for e in d.get("evidence", [])]
        d["claims"] = [Claim(**c) for c in d.get("claims", [])]
        return cls(**d)

    @classmethod
    def load(cls, path: Path | str) -> ResearchTrace:
        return cls.from_dict(json.loads(Path(path).read_text()))


# ---------------------------------------------------------------------------
# TRACE -> PROMPT compiler
# ---------------------------------------------------------------------------

_SECOND_STAGE_TEMPLATE = """You are the second-stage intelligence in a multi-model research pipeline.

You are receiving a research trace produced by another LLM.
Your job is NOT to blindly accept its conclusion.
Treat the trace as a research artifact containing observations, sources,
claims, hypotheses, assumptions, contradictions, and unresolved questions.

RESEARCH QUESTION:
{question}

OBJECTIVE:
{objective}

BROWSING TRACE:
{search_queries}

SOURCES:
{sources}

EVIDENCE:
{evidence}

CLAIMS:
{claims}

CONTRADICTIONS:
{contradictions}

HYPOTHESES:
{hypotheses}

ASSUMPTIONS:
{assumptions}

UNCERTAINTIES:
{uncertainties}

DECISIONS ALREADY MADE:
{decisions}

OPEN QUESTIONS:
{open_questions}

FIRST-MODEL CONCLUSION:
{conclusion}

NOW PERFORM A SECOND-PASS ANALYSIS.

1. Reconstruct the strongest argument supported by the evidence.
2. Separate observed facts from interpretation.
3. Identify unsupported assumptions.
4. Identify contradictions or competing explanations.
5. Determine which claims require fresh verification.
6. Search for disconfirming evidence where appropriate.
7. Generate a revised hypothesis.
8. State what would falsify the revised hypothesis.
9. Identify the highest-value next research action.
10. Produce a final conclusion with explicit confidence and uncertainty.

OUTPUT FORMAT:
RESEARCH STATE
- What is established
- What is probable
- What is speculative
- What remains unknown

CRITICAL REVIEW
- Strongest evidence
- Weakest evidence
- Contradictions
- Hidden assumptions

REVISED HYPOTHESIS
...

FALSIFICATION TEST
...

NEXT BEST OBSERVATION
...

FINAL ASSESSMENT
...

CONFIDENCE
0.00-1.00

IMPORTANT:
- Do not treat the first model's reasoning as ground truth.
- Preserve uncertainty.
- Do not manufacture evidence.
- Distinguish source evidence from model inference.
- Prefer disconfirmation over confirmation when testing a strong hypothesis.
"""


def _fmt_queries(queries: list[SearchQuery]) -> str:
    if not queries:
        return "(none recorded)"
    return "\n".join(
        f'{i}. "{q.query}" — {q.purpose}' for i, q in enumerate(queries, 1)
    )


def _fmt_sources(sources: list[Source]) -> str:
    if not sources:
        return "(none recorded)"
    lines = []
    for s in sources:
        date = f", {s.date}" if s.date else ""
        note = f" — {s.note}" if s.note else ""
        lines.append(
            f"{s.ref}. [{s.authority}/{s.source_type}] {s.locator}{date}{note}"
        )
    return "\n".join(lines)


def _fmt_evidence(evidence: list[Evidence]) -> str:
    if not evidence:
        return "(none recorded)"
    lines = []
    for e in evidence:
        artifact = f" [{e.artifact}]" if e.artifact else ""
        lines.append(f"{e.ref}. ({e.source_ref}) {e.statement}{artifact}")
    return "\n".join(lines)


def _fmt_claims(claims: list[Claim]) -> str:
    if not claims:
        return "(none recorded)"
    return "\n".join(
        f"{c.ref}. [{c.status}] {c.statement} (evidence: {', '.join(c.evidence_refs) or 'none'})"
        for c in claims
    )


def _fmt_plain(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items) if items else "(none recorded)"


def compile_prompt(trace: ResearchTrace) -> str:
    """Compile a research trace into the instruction package for LLM B."""
    return _SECOND_STAGE_TEMPLATE.format(
        question=trace.question,
        objective=trace.objective or trace.question,
        search_queries=_fmt_queries(trace.search_queries),
        sources=_fmt_sources(trace.sources),
        evidence=_fmt_evidence(trace.evidence),
        claims=_fmt_claims(trace.claims),
        contradictions=_fmt_plain(trace.contradictions),
        hypotheses=_fmt_plain(trace.hypotheses),
        assumptions=_fmt_plain(trace.assumptions),
        uncertainties=_fmt_plain(trace.uncertainties),
        decisions=_fmt_plain(trace.decisions),
        open_questions=_fmt_plain(trace.open_questions),
        conclusion=trace.conclusion or "(no conclusion recorded)",
    )
