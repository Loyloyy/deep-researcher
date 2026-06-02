"""Headless entrypoint.

    run_research(topic, brief, config, parent_id) -> (report_markdown, DeepResearchArtifact)

This is the stable interface the upstream trigger and downstream POC-builder call.
Always returns a DeepResearchArtifact (content-light if extraction is disabled) so the
return type is stable. Pass `parent_id` to refine an existing artifact lineage.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .artifact import (
    DeepResearchArtifact,
    Source,
    extract_artifact,
    new_artifact_id,
)
from .artifact import load as load_artifact
from .artifact import save as save_artifact
from .config import RunConfig, load_config


def run_research(
    topic: str,
    brief: str = "",
    config: RunConfig | None = None,
    parent_id: str | None = None,
) -> tuple[str, DeepResearchArtifact]:
    cfg = config or load_config()
    return asyncio.run(_arun(topic, brief, cfg, parent_id))


def _build_sources(detailed: list[dict]) -> list[Source]:
    sources: list[Source] = []
    for i, s in enumerate(detailed, start=1):
        sources.append(
            Source(id=f"src-{i:03d}", url=s.get("url", ""), title=s.get("title") or None, origin="web")
        )
    return sources


async def _arun(topic: str, brief: str, cfg: RunConfig, parent_id: str | None) -> tuple[str, DeepResearchArtifact]:
    from .gptr_runner import run_gptr

    # Refinement lineage
    parent = load_artifact(parent_id) if parent_id else None
    if parent is not None:
        artifact_id = parent.id
        version = parent.version + 1
        lineage_parent = f"{parent.id}@v{parent.version}"
        # feed prior findings into the brief so the run extends rather than restarts
        prior = "\n".join(f"- {f.claim}" for f in parent.findings[:20])
        if prior:
            brief = (brief + "\n\nBuild on these prior findings; deepen/extend, don't repeat:\n" + prior).strip()
    else:
        artifact_id = new_artifact_id()
        version = 1
        lineage_parent = None

    result = await run_gptr(topic, brief, cfg)
    report = result["report_markdown"]
    sources = _build_sources(result["sources_detailed"])
    model_versions = {
        "aliases": {"strategic": "openai:strategic", "smart": "openai:smart", "fast": "openai:fast"},
        "embedding": cfg.embedding,
        "costs": result.get("costs"),
        "elapsed_s": result.get("elapsed_s"),
    }

    if cfg.artifact.enabled:
        artifact = extract_artifact(
            topic=topic,
            brief=brief,
            report_md=report,
            sources=sources,
            artifact_id=artifact_id,
            version=version,
            parent_id=lineage_parent,
            model=cfg.artifact.model,
            model_versions=model_versions,
        )
    else:
        artifact = DeepResearchArtifact(
            id=artifact_id,
            version=version,
            parent_id=lineage_parent,
            generated_at=datetime.now(timezone.utc).isoformat(),
            model_versions=model_versions,
            topic=topic,
            brief=brief,
            sources=sources,
            report_markdown=report,
        )

    save_artifact(artifact)
    return report, artifact
