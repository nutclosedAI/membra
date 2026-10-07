"""arXiv harvester — pull papers and their LaTeX sources into a local corpus.

The harvester is the first stage of the LaTeX -> strategy pipeline:

    arXiv API query  ->  ArxivPaper metadata
    e-print download ->  .tex sources (tar.gz / gzipped single file / raw .tex)
    corpus layout    ->  corpus_dir/<arxiv_id>/{meta.json, src/*.tex}

Everything runs on stdlib + httpx (already a membra-sdk dependency).
"""

from __future__ import annotations

import gzip
import json
import re
import tarfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import httpx

ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_EPRINT = "https://export.arxiv.org/e-print"

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"


@dataclass
class ArxivPaper:
    """One arXiv record."""

    arxiv_id: str
    title: str
    summary: str
    published: str
    authors: list[str]
    categories: list[str]
    pdf_url: str
    eprint_url: str

    def to_json(self) -> dict:
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "summary": self.summary,
            "published": self.published,
            "authors": self.authors,
            "categories": self.categories,
            "pdf_url": self.pdf_url,
            "eprint_url": self.eprint_url,
        }


@dataclass
class HarvestResult:
    """What a harvest run produced for one paper."""

    paper: ArxivPaper
    paper_dir: Path
    tex_files: list[Path] = field(default_factory=list)
    skipped_reason: str | None = None


def query_arxiv(
    search_query: str,
    max_results: int = 8,
    sort_by: str = "relevance",
    timeout: float = 30.0,
) -> list[ArxivPaper]:
    """Query the arXiv Atom API and return parsed records.

    `search_query` uses arXiv's own syntax, e.g.
    ``all:"Stokes parameters" AND all:spinor``.
    """
    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": max_results,
        "sortBy": sort_by,
    }
    resp = httpx.get(ARXIV_API, params=params, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return _parse_atom(resp.text)


def _parse_atom(xml_text: str) -> list[ArxivPaper]:
    root = ET.fromstring(xml_text)
    papers: list[ArxivPaper] = []
    for entry in root.findall(f"{_ATOM}entry"):
        raw_id = (entry.findtext(f"{_ATOM}id") or "").strip()
        arxiv_id = raw_id.rsplit("/", 1)[-1]
        links = {
            a.get("title"): a.get("href", "") for a in entry.findall(f"{_ATOM}link")
        }
        papers.append(
            ArxivPaper(
                arxiv_id=arxiv_id,
                title=" ".join((entry.findtext(f"{_ATOM}title") or "").split()),
                summary=(entry.findtext(f"{_ATOM}summary") or "").strip(),
                published=(entry.findtext(f"{_ATOM}published") or "")[:10],
                authors=[
                    a.findtext(f"{_ATOM}name") or ""
                    for a in entry.findall(f"{_ATOM}author")
                ],
                categories=[
                    c.get("term", "")
                    for c in entry.findall(f"{_ARXIV}primary_category")
                ]
                + [c.get("term", "") for c in entry.findall(f"{_ATOM}category")],
                pdf_url=links.get("pdf", f"https://arxiv.org/pdf/{arxiv_id}"),
                eprint_url=f"{ARXIV_EPRINT}/{arxiv_id}",
            )
        )
    return papers


def fetch_eprint(
    arxiv_id: str,
    dest_dir: Path | str,
    timeout: float = 60.0,
    politeness_sleep: float = 3.0,
) -> Path:
    """Download the e-print (LaTeX source bundle) for one paper.

    arXiv asks automated clients to sleep ~3s between requests;
    `politeness_sleep` keeps batch harvests friendly.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"{arxiv_id.replace('/', '_')}.eprint"
    time.sleep(politeness_sleep)
    with httpx.stream(
        "GET", f"{ARXIV_EPRINT}/{arxiv_id}", timeout=timeout, follow_redirects=True
    ) as resp:
        resp.raise_for_status()
        with open(out, "wb") as fh:
            fh.writelines(resp.iter_bytes(1 << 16))
    return out


def extract_tex_sources(eprint_path: Path | str, dest_dir: Path | str) -> list[Path]:
    """Unpack an e-print into .tex files.

    Handles the three shapes arXiv serves:
      * tar.gz bundle (most common)
      * gzip-compressed single .tex
      * uncompressed single .tex
    Returns the extracted .tex paths (empty when the bundle holds no LaTeX).
    """
    eprint = Path(eprint_path)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    blob = eprint.read_bytes()
    tex_out: list[Path] = []

    if _is_tar(blob):
        with tarfile.open(eprint) as tf:
            tf.extractall(dest, filter="data")
        tex_out = sorted(dest.rglob("*.tex"))
    elif _is_gzip(blob):
        raw = gzip.decompress(blob)
        if _looks_like_tex(raw):
            tex_out = [dest / f"{eprint.stem}.tex"]
            tex_out[0].write_bytes(raw)
    elif _looks_like_tex(blob):
        tex_out = [dest / f"{eprint.stem}.tex"]
        tex_out[0].write_bytes(blob)

    return tex_out


def harvest(
    search_query: str,
    corpus_dir: Path | str,
    max_results: int = 4,
    timeout: float = 60.0,
) -> list[HarvestResult]:
    """End-to-end harvest: query -> eprint -> .tex files per paper.

    Papers whose e-print is PDF-only (no LaTeX source) are returned with
    `skipped_reason` set instead of tex_files.
    """
    corpus = Path(corpus_dir)
    corpus.mkdir(parents=True, exist_ok=True)
    results: list[HarvestResult] = []

    for paper in query_arxiv(search_query, max_results=max_results, timeout=timeout):
        paper_dir = corpus / paper.arxiv_id.replace("/", "_")
        src_dir = paper_dir / "src"
        (paper_dir / "meta.json").parent.mkdir(parents=True, exist_ok=True)
        (paper_dir / "meta.json").write_text(json.dumps(paper.to_json(), indent=2))

        result = HarvestResult(paper=paper, paper_dir=paper_dir)
        try:
            eprint = fetch_eprint(paper.arxiv_id, paper_dir)
            result.tex_files = extract_tex_sources(eprint, src_dir)
            if not result.tex_files:
                result.skipped_reason = "no LaTeX source in e-print (PDF-only?)"
        except (httpx.HTTPError, OSError, tarfile.TarError, gzip.BadGzipFile) as exc:
            # network or unpack failure -> skip this paper, keep going
            result.skipped_reason = f"eprint fetch/extract failed: {exc}"
        results.append(result)

    return results


def _is_tar(blob: bytes) -> bool:
    # tar magic: "ustar" at offset 257 (or plain tar without magic for old tars —
    # tarfile.open would still raise, so magic check is the cheap gate)
    return len(blob) > 262 and blob[257:262] == b"ustar"


def _is_gzip(blob: bytes) -> bool:
    return blob[:2] == b"\x1f\x8b"


def _looks_like_tex(blob: bytes) -> bool:
    head = blob[:4096].decode("utf-8", errors="ignore")
    return bool(
        re.search(r"\\(documentclass|begin\{document\}|section|usepackage)", head)
    )
