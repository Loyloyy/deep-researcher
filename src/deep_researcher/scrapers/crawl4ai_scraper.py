"""Crawl4AI scraper adapter for GPT Researcher.

GPTR scrapers are constructed as ``Scraper(link, session)`` and must expose
``scrape_async()`` (preferred) or ``scrape()`` returning ``(content, image_urls, title)``.
They receive only the URL (no query), so we do query-agnostic clean extraction via
Crawl4AI's PruningContentFilter -> fit_markdown. Query-aware relevance filtering /
reranking happens downstream where the query is available (see rerank/).

Registered into GPTR's SCRAPER_CLASSES by name "crawl4ai" via register_crawl4ai().
PDFs/arxiv URLs are still routed by GPTR to its PyMuPDF/Arxiv scrapers automatically.
"""
from __future__ import annotations

import asyncio
import logging

from ..cache.store import default_cache

logger = logging.getLogger(__name__)


class Crawl4AIScraper:
    def __init__(self, link: str, session=None):
        self.link = link
        self.session = session

    async def scrape_async(self) -> tuple[str, list[str], str]:
        cached = default_cache.get(self.link)
        if cached is not None:
            return cached["content"], cached.get("image_urls", []), cached.get("title", "")

        content, images, title = await self._fetch()
        if content:
            default_cache.set(self.link, content, title, images)
        return content, images, title

    async def _fetch(self) -> tuple[str, list[str], str]:
        try:
            from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
            from crawl4ai.content_filter_strategy import PruningContentFilter
            from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
        except Exception as e:  # crawl4ai not installed
            logger.warning("crawl4ai unavailable (%s); returning empty for %s", e, self.link)
            return "", [], ""

        try:
            md_gen = DefaultMarkdownGenerator(
                content_filter=PruningContentFilter(threshold=0.45, threshold_type="dynamic")
            )
            run_cfg = CrawlerRunConfig(markdown_generator=md_gen, page_timeout=30000)
            async with AsyncWebCrawler() as crawler:
                result = await crawler.arun(url=self.link, config=run_cfg)

            if not getattr(result, "success", False):
                logger.info("crawl4ai non-success for %s: %s", self.link, getattr(result, "error_message", ""))
                return "", [], ""

            md = getattr(result, "markdown", None)
            content = ""
            if md is not None:
                content = getattr(md, "fit_markdown", None) or getattr(md, "raw_markdown", "") or str(md)
            meta = getattr(result, "metadata", None) or {}
            title = meta.get("title", "") if isinstance(meta, dict) else ""
            media = getattr(result, "media", None) or {}
            images = [
                img.get("src")
                for img in (media.get("images", []) if isinstance(media, dict) else [])
                if isinstance(img, dict) and img.get("src")
            ]
            return content, images, title
        except Exception as e:
            # politeness/robustness: skip paywalls/403s/timeouts instead of crashing the run
            logger.warning("crawl4ai scrape failed for %s: %s", self.link, e)
            return "", [], ""

    def scrape(self) -> tuple[str, list[str], str]:
        return asyncio.run(self.scrape_async())


def register_crawl4ai() -> bool:
    """Inject the adapter into GPTR's scraper registry. Returns True on success."""
    try:
        from gpt_researcher.scraper import scraper as gptr_scraper_mod

        registry = getattr(gptr_scraper_mod, "SCRAPER_CLASSES", None)
        if isinstance(registry, dict):
            registry["crawl4ai"] = Crawl4AIScraper
            return True
        logger.warning("SCRAPER_CLASSES not found; cannot register crawl4ai (GPTR version drift?)")
    except Exception as e:
        logger.warning("could not register crawl4ai scraper: %s", e)
    return False
