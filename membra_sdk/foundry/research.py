"""Actual prior-art metadata retrieval; retrieval is not novelty or proof certification."""

from __future__ import annotations

import datetime as dt
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .tfl import digest


def prior_art(query: str = 'all:"deep hedging"', limit: int = 5) -> dict:
    if not isinstance(query, str) or not 1 <= len(query) <= 300 or not 1 <= limit <= 10:
        raise ValueError("bounded arXiv query required")
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": query, "max_results": limit, "sortBy": "relevance"}
    )
    req = urllib.request.Request(
        url, headers={"User-Agent": "membra-foundry-research/1"}
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("research response too large")
    root = ET.fromstring(raw)
    atom = "{http://www.w3.org/2005/Atom}"
    sources = [
        {
            "url": entry.findtext(atom + "id", "").replace("http://", "https://", 1),
            "title": " ".join(entry.findtext(atom + "title", "").split()),
            "summary": entry.findtext(atom + "summary", "").strip(),
            "published": entry.findtext(atom + "published", ""),
        }
        for entry in root.findall(atom + "entry")
    ]
    return {
        "query": query,
        "endpoint": url,
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sources": sources,
        "content_sha256": digest(sources),
        "novelty": "unresolved",
        "proof_status": "unproven",
        "certified": False,
        "limitations": "arXiv metadata only; requires independent full-text and prior-art review",
    }
