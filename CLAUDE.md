# CLAUDE.md

Operational context for Claude Code working in this repo. Read before editing.

## What this is

A generic, model-agnostic **deep research pipeline**: `(topic, brief) -> (cited report,
versioned DeepResearchArtifact)`. It is the **middle stage** of an eventual 3-part system —
(1) an upstream YouTube/AI-Engineer momentum trigger [NOT built], (2) THIS pipeline,
(3) a downstream POC-builder that consumes the artifact [NOT built]. Keep the core
**headless and decoupled**; the only contract to the outside is `run_research(...)` in and a
persisted `DeepResearchArtifact` out. Do not build stages 1 or 3.

Full rationale for every choice is in `DECISIONS.md`; setup/usage in `README.md`; bugs hit and how
they were mitigated in `DEV_NOTES.md`. This file is the rules + gotchas a coding agent needs.

## Commands

- **Offline tests (run after every edit — no services/keys/GPU):** `PYTHONPATH=src python -m pytest tests/ -q`
- **Run the pipeline:** `python -m deep_researcher.cli "topic" ["brief"]`
- **Before any live / paid run:** `/preflight` — probes the LiteLLM proxy + SearXNG stack.
- **After a `gpt-researcher` bump:** `/gptr-drift` — re-checks the three fragile seams below, then offline tests.

## Architecture (one line per layer)

- **Core:** GPT Researcher, driven via env vars set in `src/deep_researcher/gptr_runner.py`.
- **Search:** SearXNG (`RETRIEVER=searx`); vault adds `,custom` → merged into one pool.
- **Extract:** Crawl4AI adapter (`scrapers/crawl4ai_scraper.py`), registered into GPTR's `SCRAPER_CLASSES`.
- **Rerank:** cross-encoder (`rerank/patch.py`) monkeypatched into GPTR's context compression.
- **Models:** all calls go through the **LiteLLM proxy** via roles `strategic`/`smart`/`fast` (+ `judge`
  for eval). Each role's model id + endpoint + key is declared **in `.env`** (`STRATEGIC_*`, `SMART_*`,
  `FAST_*`, `JUDGE_*`); `docker/litellm/config.yaml` is a **fixed env-driven template** (do not edit it).
  The proxy lets each role be an independent on-prem vLLM endpoint or a frontier API.
- **Artifact:** `artifact/` — schema, extraction pass, citation validation, versioned store.
- **Vault / UI / eval:** `vault/`, `ui/gradio_app.py`, `eval/`.

## Hard rules

1. **Never name a concrete model in app code.** Roles map to proxy aliases only; real models live in
   `.env` (per-role `*_MODEL`/`*_API_BASE`/`*_API_KEY`), wired by the fixed `docker/litellm/config.yaml`
   template. Switching models/providers must stay `.env`-only.
2. **Never put pipeline logic in the UI.** `ui/` is presentation over `run_research` — nothing else.
3. **Keep the core generic.** No AI/LLM-domain assumptions baked into the pipeline; the AI-Engineer use
   case is just the first consumer.
4. **Decouple search and extraction.** They are independently swappable layers — don't fuse them.
5. **LiteLLM is pinned (`1.83.0`)** in `pyproject.toml` AND the docker image tag, due to the Mar 2026
   supply-chain incident (malicious 1.82.7/1.82.8). Bump only after changelog review + `pip-audit`.
   A `PreToolUse` hook (`.claude/hooks/litellm-pin-guard.sh`) asks for confirmation on any edit that
   changes the pin — that prompt is expected, not a glitch.
6. **Vault is read-only.** Operate on the duplicated copy (`vault_data/`), never write to the user's
   `ai-engineer-wiki` repo. The `## Notes` sections in that wiki are user-owned.
7. **Keep heavy deps lazy-imported** (torch, crawl4ai, gradio, fastapi, rank_bm25) so the package
   imports and offline tests run without a GPU or the full extra set.
8. **Never put machine-specific or sensitive values in tracked files.** Server IPs, NFS/filesystem paths,
   internal/partner model names or ids, hostnames, and any keys live ONLY in gitignored `.env` /
   `docker/docker-compose.override.yml`. Committed files (code, `.env.example`, docs, helper scripts) use
   **generic placeholders** (`/path/to/models`, `<served-model-id>`, `<host>:<port>`). Don't hardcode a
   real endpoint/model into a one-off script either. This repo pushes to a GitHub remote — assume anything
   committed is public.
9. **Log every non-trivial decision in `DECISIONS.md`.**

## Fragile seams (these couple to GPT Researcher internals — verify after any GPTR upgrade)

- `scrapers/crawl4ai_scraper.py::register_crawl4ai` → injects into `gpt_researcher.scraper.scraper.SCRAPER_CLASSES`.
- `rerank/patch.py` → monkeypatches the name-mangled `ContextCompressor._ContextCompressor__get_contextual_retriever`.
- `gptr_runner.py::_collect_sources` → reads `get_research_sources` / `get_source_urls`.
All three are wrapped to **degrade, not crash** if internals drift; a drift shows up as a logged warning
(e.g. `rerank disabled — … drift`) or empty results, not an exception.

## Testing

- Offline (no services/keys/GPU): `PYTHONPATH=src python -m pytest tests/ -q` — covers schema, citation
  validation, artifact store/versioning, cache TTL, and a real BM25 vault search. **Run this after edits.**
- Live (server only): the model/embedding/scrape path — see `README.md` quickstart. Don't run paid
  research passes without the user's go-ahead.

## Conventions

- Package import name is `deep_researcher` (folder `deep-researcher`); src layout under `src/`.
- Config: `config/pipeline.yaml` for non-model knobs; `.env` declares the 3 models (+ judge) and secrets;
  `docker/litellm/config.yaml` is a fixed env-driven template (not edited). `RunConfig` (in `config.py`)
  is the single typed config object.
- Persisted artifacts: `artifacts/<id>/vNN.json`. Refinement bumps version under the same id via `parent_id`.

## Status (2026-06-03)

**Deployed and validated on the H200 server, fully containerized** (`docker-compose run app`):
a local vLLM model via LiteLLM, local BGE-M3 embeddings + bge-reranker-v2-m3, full-page scraping, cross-encoder
rerank, and artifact extraction/persistence all work end-to-end → grounded, cited reports.

**Known constraint (environmental, not code):** the server has a hard egress allowlist with no proxy —
only search engines + a few vendor domains are reachable; most content sites are TLS-reset by the
firewall. Web-research depth is network-limited on this box.

**Next:** (1) wire the vault (Phase 4) — local wiki as a no-internet source, the best fit here;
(2) Crawl4AI/Chromium only on an open-egress box (prebuilt Playwright image); (3) egress via IT
allowlist/proxy or an open-internet host. Full bug log + roadmap in `DEV_NOTES.md`; see also the
`deep-researcher-project` memory and `DECISIONS.md`.
