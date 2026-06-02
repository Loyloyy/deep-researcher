# DEV_NOTES

Running log of mistakes/bugs spotted during build + on-server testing, and how we mitigated each.
Newest at the bottom of each section. "⏳ pending verify" = fix committed but not yet re-run on the server.

---

## GPT Researcher integration

### Scraping silently skipped — reports built from snippets, not pages  ⭐ biggest one
- **Symptom:** every run logged `🌐 Scraping content from 0 URLs → 📄 Scraped 0 pages`, yet the report
  had real sources and coherent (but shallow, generic) content. Egress (200) and SearXNG both worked.
- **Cause:** GPTR's `_search_relevant_source_urls` treats a search result as *already fetched* when it
  has `body`/`raw_content` > 100 chars, and uses that text directly instead of scraping. The SearXNG
  retriever returns each hit as `{"href", "body"}` where `body` is the **search snippet** (>100 chars).
  So GPTR used snippets and never scraped full pages — silently bypassing the whole scrape→chunk→rerank
  stack. Not hallucinated (real URLs/snippets), but shallow and under-grounded.
- **Fix:** `src/deep_researcher/search_patch.py::force_full_scrape()` monkeypatches `SearxSearch.search`
  to drop `body`, so every hit is routed to the real scraper. Wired in `gptr_runner` when retriever
  includes `searx`.  ⏳ pending verify.

### Reranker disabled at startup
- **Symptom:** `rerank disabled — could not import GPTR/LangChain internals: No module named 'langchain.retrievers'`.
- **Cause:** only `langchain-core`/`langchain-community` were installed; the umbrella `langchain`
  package (which holds `langchain.retrievers`, `CrossEncoderReranker`, etc.) was not.
- **Fix:** added `langchain` to the `quality`/`all` extras in `pyproject.toml`. Also hardened
  `rerank/patch.py` so any runtime error in the reranking pipeline degrades to GPTR's default retriever
  instead of breaking the run.  ⏳ pending verify (rebuild required).

### `MCPRetriever` import warning — benign
- `Failed to import MCPRetriever: No module named 'langchain_mcp_adapters'` is a GPTR optional feature
  we don't use (the vault goes through GPTR's HTTP `custom` retriever, not MCP). Left as-is.

### Embedding model string needs the `huggingface:` prefix
- A bare path (`/mnt/.../bge-m3`) breaks GPTR's `provider:model` parsing. Use
  `huggingface:/mnt/.../bge-m3`. The **reranker** model is consumed by our own code, so a bare path
  is fine there.

### Cost number is meaningless for local models
- GPTR's `💸 Total Research Costs` is `tokens × a price table`; self-hosted models have no price entry,
  so it's a junk estimate. **Fix:** stopped recording it in the artifact (`model_versions.costs = None`).
  Use Langfuse for real token/latency accounting.

---

## Model wiring (vLLM behind LiteLLM)

### vLLM served id has a LEADING SLASH
- `/v1/models` returned `"/nfs/llm_models/nvidia/GLM-5-NVFP4"` (leading `/`). In `.env` the LiteLLM
  value is therefore `hosted_vllm//nfs/llm_models/...` (**double slash**). A single slash →
  `The model ... does not exist (404)`.

### Container networking
- Inside the compose network, reach services by name — `http://litellm:4000`, `http://searxng:8080` —
  not `localhost`. Set via the `app` service `environment:` overrides; `.env`'s `localhost` values are
  only for host-run usage.

### `.env`-only model selection
- LiteLLM resolves `model/api_base/api_key: os.environ/VAR`, so the 3 roles (+ judge) are declared
  entirely in `.env`; `docker/litellm/config.yaml` is a fixed template (never edited).

---

## Deployment / Docker

### LiteLLM image tag
- `main-v1.83.0` and `main-v1.83.0-stable` → `manifest unknown`. **Fix:** `main-stable` (rolling,
  well past the Mar-2026 compromised 1.82.7/1.82.8). TODO: re-pin to a verified `vX.Y.Z-stable`.

### docker-compose v1.29.2 (old standalone binary)
- Rejects the top-level `name:` key → replaced with `version: "3.8"`.
- `KeyError: 'ContainerConfig'` on recreate of modern OCI images (a known v1.29.2 bug). **Workaround:**
  `docker-compose down && docker-compose up -d` (fresh create) instead of `up --force-recreate`.

### NFS bind-mount permission denied
- Daemon couldn't `mkdir` `artifacts/` on NFS (container root → squashed to `nobody`). **Fix:**
  pre-create the dirs as the user and `chmod 777` so the squashed user can write.

### Playwright/Chromium blocked at build
- `cdn.playwright.dev` unreachable (`ECONNRESET`) → image build aborted. **Fix:** made
  `playwright install` non-fatal (`|| echo WARN`) and defaulted `scraper: bs` (no browser).
  Crawl4AI (better extractor) stays optional until the CDN is reachable, or use a prebuilt
  Playwright base image that ships Chromium.

---

## Config hygiene / git workflow

### Server-local edits clobbered on `git pull`
- Private model paths and host mounts kept getting overwritten on pull. **Fix:** all machine-specific
  config now lives in **gitignored** files:
  - `.env` — `DR_EMBEDDING` / `DR_RERANK_MODEL` override `config/pipeline.yaml` without editing it.
  - `docker/docker-compose.override.yml` — host mounts (e.g. the model NFS dir), auto-merged by compose.
  Tracked files stay generic, so pulls never conflict.
