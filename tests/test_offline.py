"""Offline unit tests — exercise everything that does NOT need live models/services.

Run:  PYTHONPATH=src python -m pytest tests/ -q
(or)  PYTHONPATH=src python tests/test_offline.py
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deep_researcher.artifact import (  # noqa: E402
    DeepResearchArtifact,
    Finding,
    Source,
    save,
    load,
    latest_version,
    validate_citations,
)
from deep_researcher.cache.store import ContentCache  # noqa: E402
from deep_researcher.config import load_config  # noqa: E402


def _artifact(**kw) -> DeepResearchArtifact:
    base = dict(id="dra-test", version=1, generated_at="2026-06-01T00:00:00Z", topic="t")
    base.update(kw)
    return DeepResearchArtifact(**base)


def test_config_loads():
    cfg = load_config()
    assert cfg.rerank.keep_top_k > 0
    assert cfg.scraper in {"crawl4ai", "bs", "browser"}


def test_citation_validation_drops_hallucinated():
    a = _artifact(
        sources=[Source(id="src-001", url="http://a")],
        findings=[Finding(claim="x", evidence_ids=["src-001", "src-999"], confidence=0.7)],
    )
    a = validate_citations(a)
    assert a.findings[0].evidence_ids == ["src-001"]


def test_store_roundtrip_and_versioning():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        a1 = _artifact(version=1)
        save(a1, root)
        a2 = _artifact(version=2, parent_id="dra-test@v1")
        save(a2, root)
        assert latest_version("dra-test", root) == 2
        loaded = load("dra-test", root=root)
        assert loaded.version == 2 and loaded.parent_id == "dra-test@v1"


def test_cache_set_get_and_staleness():
    with tempfile.TemporaryDirectory() as d:
        c = ContentCache(root=d, ttl_hours=24, enabled=True)
        c.set("http://x", "hello", "Title", ["img"])
        got = c.get("http://x")
        assert got and got["content"] == "hello" and got["title"] == "Title"
        # force staleness
        c.ttl_s = 0
        time.sleep(0.01)
        assert c.get("http://x") is None
        # disabled cache returns nothing
        assert ContentCache(root=d, enabled=False).get("http://x") is None


def test_vault_index_against_real_wiki_if_present():
    from deep_researcher.vault.index import VaultIndex

    wiki = Path("/mnt/d/aloy/personal/ai-engineer-wiki/wiki")
    if not wiki.exists():
        return  # skip when the wiki isn't available
    idx = VaultIndex(wiki)
    assert idx.size > 50
    hits = idx.search("context engineering agents", k=5)
    assert hits and "raw_content" in hits[0] and hits[0]["url"].startswith("vault://")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all offline tests passed")
