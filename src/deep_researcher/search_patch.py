"""Force full-page scraping when using the SearXNG retriever.

GPT Researcher's `_search_relevant_source_urls` treats a result as "already fetched"
(and skips scraping) when it has body/content > 100 chars, using that text directly.
SearXNG returns short snippets as `body`, so GPTR uses the snippet and NEVER scrapes
the full page — silently bypassing our scrape -> chunk -> rerank stack and producing
shallow, snippet-only reports.

We strip `body` from each SearXNG result so every hit is routed to the real scraper
(bs / crawl4ai). Defensive: if GPTR internals drift, log and no-op.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_PATCHED = False


def force_full_scrape() -> bool:
    global _PATCHED
    if _PATCHED:
        return True
    try:
        from gpt_researcher.retrievers.searx.searx import SearxSearch
    except Exception as e:
        logger.warning("SearXNG full-scrape patch skipped (import failed): %s", e)
        return False

    original = SearxSearch.search

    def patched(self, max_results: int = 10):
        results = original(self, max_results=max_results) or []
        for r in results:
            if isinstance(r, dict):
                r.pop("body", None)  # drop snippet -> GPTR scrapes the full page
        return results

    SearxSearch.search = patched
    _PATCHED = True
    logger.info("SearXNG retriever patched: full-page scraping enabled (snippets stripped)")
    return True
