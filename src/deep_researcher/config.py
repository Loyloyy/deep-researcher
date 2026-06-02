"""Pipeline configuration: loads .env + config/pipeline.yaml into a RunConfig."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

# repo root = .../deep-researcher (two levels up from this file's package dir)
ROOT = Path(__file__).resolve().parents[2]


@dataclass
class RerankConfig:
    enabled: bool = True
    model: str = "BAAI/bge-reranker-v2-m3"
    retrieve_top_n: int = 50
    keep_top_k: int = 10


@dataclass
class CacheConfig:
    enabled: bool = True
    staleness_hours: int = 24


@dataclass
class ArtifactConfig:
    enabled: bool = True
    model: str = "smart"


@dataclass
class VaultConfig:
    enabled: bool = False
    endpoint: str = "http://localhost:8090/search"


@dataclass
class RunConfig:
    report_type: str = "research_report"
    retriever: str = "searx"
    scraper: str = "crawl4ai"
    max_iterations: int = 3
    max_search_results_per_query: int = 5
    wall_clock_timeout_s: int = 1200
    embedding: str = "huggingface:BAAI/bge-m3"
    rerank: RerankConfig = field(default_factory=RerankConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    artifact: ArtifactConfig = field(default_factory=ArtifactConfig)
    vault: VaultConfig = field(default_factory=VaultConfig)


def load_config(path: str | Path | None = None) -> RunConfig:
    """Load .env (secrets/endpoints) and pipeline.yaml (knobs) into a RunConfig."""
    load_dotenv(ROOT / ".env")
    p = Path(path) if path else ROOT / "config" / "pipeline.yaml"
    data = yaml.safe_load(p.read_text()) if p.exists() else {}
    data = data or {}
    r = data.get("research", {}) or {}
    rk = data.get("rerank", {}) or {}
    ca = data.get("cache", {}) or {}
    ar = data.get("artifact", {}) or {}
    va = data.get("vault", {}) or {}
    return RunConfig(
        report_type=r.get("report_type", "research_report"),
        retriever=r.get("retriever", "searx"),
        scraper=r.get("scraper", "crawl4ai"),
        max_iterations=int(r.get("max_iterations", 3)),
        max_search_results_per_query=int(r.get("max_search_results_per_query", 5)),
        wall_clock_timeout_s=int(r.get("wall_clock_timeout_s", 1200)),
        # Env overrides (DR_EMBEDDING / DR_RERANK_MODEL) win over pipeline.yaml, so machine-specific
        # private model paths live in .env (gitignored) and never get clobbered by git pulls.
        embedding=os.environ.get("DR_EMBEDDING") or data.get("embedding", "huggingface:BAAI/bge-m3"),
        rerank=RerankConfig(
            enabled=bool(rk.get("enabled", True)),
            model=os.environ.get("DR_RERANK_MODEL") or rk.get("model", "BAAI/bge-reranker-v2-m3"),
            retrieve_top_n=int(rk.get("retrieve_top_n", 50)),
            keep_top_k=int(rk.get("keep_top_k", 10)),
        ),
        cache=CacheConfig(
            enabled=bool(ca.get("enabled", True)),
            staleness_hours=int(ca.get("staleness_hours", 24)),
        ),
        artifact=ArtifactConfig(
            enabled=bool(ar.get("enabled", True)),
            model=ar.get("model", "smart"),
        ),
        vault=VaultConfig(
            enabled=bool(va.get("enabled", False)),
            endpoint=va.get("endpoint", "http://localhost:8090/search"),
        ),
    )
