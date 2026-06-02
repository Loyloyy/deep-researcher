"""Thin wrapper around GPT Researcher.

Maps RunConfig onto GPTR's env-var config surface, registers our custom scraper,
enables the cross-encoder rerank stage, configures caching, merges the vault
retriever, runs the research + report under a wall-clock circuit breaker, and
returns the report plus detailed sources for the artifact pass.

Provider switching (OpenRouter/API/vLLM) is handled entirely by the LiteLLM proxy
via the strategic/smart/fast aliases — this module never names a concrete model.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

from .cache.store import configure_default_cache
from .config import RunConfig

logger = logging.getLogger(__name__)


def _apply_env(cfg: RunConfig) -> None:
    retriever = cfg.retriever
    if cfg.vault.enabled and "custom" not in retriever.split(","):
        retriever = f"{retriever},custom"
        os.environ["RETRIEVER_ENDPOINT"] = cfg.vault.endpoint
    os.environ["RETRIEVER"] = retriever
    os.environ["SCRAPER"] = cfg.scraper
    os.environ["STRATEGIC_LLM"] = "openai:strategic"
    os.environ["SMART_LLM"] = "openai:smart"
    os.environ["FAST_LLM"] = "openai:fast"
    os.environ["EMBEDDING"] = cfg.embedding
    os.environ["MAX_ITERATIONS"] = str(cfg.max_iterations)
    os.environ["MAX_SEARCH_RESULTS_PER_QUERY"] = str(cfg.max_search_results_per_query)


def _wire_extensions(cfg: RunConfig) -> None:
    configure_default_cache(enabled=cfg.cache.enabled, ttl_hours=cfg.cache.staleness_hours)
    if cfg.scraper == "crawl4ai":
        from .scrapers import register_crawl4ai

        register_crawl4ai()
    if cfg.rerank.enabled:
        from .rerank import enable_reranker

        enable_reranker(cfg.rerank.model, cfg.rerank.retrieve_top_n, cfg.rerank.keep_top_k)


def _build_query(topic: str, brief: str) -> str:
    return topic if not brief else f"{topic}\n\nResearch brief / focus:\n{brief}"


async def run_gptr(topic: str, brief: str, cfg: RunConfig) -> dict:
    from gpt_researcher import GPTResearcher  # lazy: surface config errors first

    _apply_env(cfg)
    _wire_extensions(cfg)

    researcher = GPTResearcher(query=_build_query(topic, brief), report_type=cfg.report_type)

    t0 = time.time()
    await asyncio.wait_for(researcher.conduct_research(), timeout=cfg.wall_clock_timeout_s)
    report = await researcher.write_report()
    elapsed = round(time.time() - t0, 1)

    return {
        "report_markdown": report,
        "sources_detailed": _collect_sources(researcher),
        "costs": _safe(researcher, "get_costs"),
        "elapsed_s": elapsed,
    }


def _safe(obj, method):
    fn = getattr(obj, method, None)
    try:
        return fn() if callable(fn) else None
    except Exception:
        return None


def _collect_sources(researcher) -> list[dict]:
    """Normalize GPTR's source records to {url, title} dicts (best-effort across versions)."""
    detailed = _safe(researcher, "get_research_sources")
    out: list[dict] = []
    if isinstance(detailed, list):
        for s in detailed:
            if isinstance(s, dict):
                url = s.get("url") or s.get("href") or ""
                if url:
                    out.append({"url": url, "title": s.get("title") or ""})
    if not out:
        for url in _safe(researcher, "get_source_urls") or []:
            out.append({"url": url, "title": ""})
    # dedup by url, preserve order
    seen, deduped = set(), []
    for s in out:
        if s["url"] not in seen:
            seen.add(s["url"])
            deduped.append(s)
    return deduped
