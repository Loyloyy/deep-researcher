---
name: gptr-drift
description: After a gpt-researcher upgrade, verify the three fragile seams against current GPTR internals, then run offline tests.
when_to_use: Invoke after bumping the `gpt-researcher` dependency, or when a run logs "rerank disabled — … drift", empty sources, or a scraper/registry error.
allowed-tools: Bash, Read, Grep
---

# GPT-Researcher drift check

The pipeline couples to three GPT Researcher internals (see CLAUDE.md "Fragile seams"). All three
are wrapped to **degrade, not crash**, so drift surfaces as a logged warning or empty results — not
an exception. This skill confirms each seam still attaches after a GPTR version bump. Work through
all three, then the tests. Report each seam as OK / DRIFTED with the evidence.

## Seam 1 — scraper registry (`scrapers/crawl4ai_scraper.py::register_crawl4ai`)
Injects Crawl4AI into `gpt_researcher.scraper.scraper.SCRAPER_CLASSES`. Confirm the registry still exists:
```bash
PYTHONPATH=src python -c "from gpt_researcher.scraper.scraper import SCRAPER_CLASSES; print(type(SCRAPER_CLASSES), list(SCRAPER_CLASSES)[:8])"
```
DRIFTED if the import path or the `SCRAPER_CLASSES` dict is gone/renamed.

## Seam 2 — rerank monkeypatch (`rerank/patch.py`)
Monkeypatches the name-mangled `ContextCompressor._ContextCompressor__get_contextual_retriever`.
Confirm the target method still exists:
```bash
PYTHONPATH=src python -c "from gpt_researcher.context.compression import ContextCompressor as C; print(hasattr(C, '_ContextCompressor__get_contextual_retriever'))"
```
Must print `True`. `False` (or an import error) → the compression internals moved; update `rerank/patch.py`
and expect the `rerank disabled — … drift` log until fixed. Cross-check the patch's own import path against the error.

## Seam 3 — source collection (`gptr_runner.py::_collect_sources`)
Reads `get_research_sources` / `get_source_urls` off the researcher object:
```bash
PYTHONPATH=src python -c "from gpt_researcher import GPTResearcher; print([m for m in dir(GPTResearcher) if 'source' in m.lower()])"
```
DRIFTED if neither `get_research_sources` nor `get_source_urls` appears.

## Offline tests
```bash
PYTHONPATH=src python -m pytest tests/ -q
```
Must stay green — these cover schema/validation/store/cache and don't touch GPTR internals, so a
failure here means something else regressed.

## Before bumping LiteLLM (separate, security-gated)
Do **not** fold a LiteLLM bump into a GPTR upgrade. LiteLLM is pinned `1.83.0` after the Mar 2026
supply-chain incident (malicious 1.82.7/1.82.8). Bump only after changelog review + `pip-audit`,
and only in both `pyproject.toml` and the docker image tag. The `litellm-pin-guard` hook will prompt
on any such edit.

## Wrap up
If any seam drifted, the fix is small and local to that file — patch it, re-run this skill, and log
the GPTR version + what moved in `DECISIONS.md`.
