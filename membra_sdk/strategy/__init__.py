"""Strategy pipeline: arXiv LaTeX -> research trace -> SpinorStokes strategy.

arxiv_harvest   pull papers + .tex sources into a local corpus
latex2strategy  map extracted equations onto strategy primitives
research_trace  the transferable object between LLM chain stages
spinor_stokes   the redefined strategy: Stokes params + spinor lift
"""

from .arxiv_harvest import ArxivPaper, HarvestResult, harvest, query_arxiv
from .latex2strategy import LatexStrategyConverter, StrategySpec
from .research_trace import ResearchTrace, compile_prompt
from .spinor_stokes import Signal, SpinorStokesStrategy, Stokes

__all__ = [
    "ArxivPaper",
    "HarvestResult",
    "LatexStrategyConverter",
    "ResearchTrace",
    "Signal",
    "SpinorStokesStrategy",
    "Stokes",
    "StrategySpec",
    "compile_prompt",
    "harvest",
    "query_arxiv",
]
