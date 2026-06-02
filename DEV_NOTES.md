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
- **Symptom:** `rerank disabled — … No module named 'langchain.retrievers'`, even with `langchain` installed.
- **Cause:** the installed stack is **langchain 1.3.3** (the 1.x restructure). `langchain.retrievers` and
  `…document_compressors` (`CrossEncoderReranker`, `DocumentCompressorPipeline`, `EmbeddingsFilter`) were
  relocated to the **`langchain-classic`** package. Our patch imported the old `langchain.retrievers` paths.
- **Fix:** `rerank/patch.py` now imports from `langchain_classic.retrievers…` with a fallback to the old
  `langchain.retrievers…` (0.x); added `langchain-classic` to the extras. Also hardened so any runtime
  error in the reranking pipeline degrades to GPTR's default retriever instead of breaking the run.
  ⏳ pending verify (rebuild required).

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
- A vLLM served id can be an absolute path with a **leading slash** (check `/v1/models` → `data[0].id`).
  When it starts with `/`, the LiteLLM `.env` value needs a **double slash**: `hosted_vllm//<served/id>`.
  A single slash → `The model ... does not exist (404)`.

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
- **Update:** even with Chromium, this server's egress is filtered (see *Restricted network egress*),
  so the real browser scraper (Crawl4AI) only helps on an **open-egress** deployment. Revisit there via
  a prebuilt Playwright base image (Chromium baked in, no CDN download). On this box, `scraper: bs` stays.

### Restricted network egress — the real scraping limiter ⭐ current blocker for web depth
- **Symptom:** most sites failed scraping with `Connection reset by peer`; only IBM/NVIDIA/Microsoft
  came through. Raw `curl` from the container to `aws.amazon.com` → `curl: (35) … Connection reset by
  peer` (reset at the TLS layer), and `env | grep -i proxy` returns nothing.
- **Cause:** the server enforces a hard **egress allowlist** (likely SNI-based) — search engines + a few
  vendor domains permitted, most content sites blocked, no HTTP proxy. **Not fixable in code** (a browser
  scraper hits the same wall). SearXNG still returns results because the search engines are allowlisted.
- **Direction:** (a) use the **vault** (local wiki) as a no-internet source; (b) IT allowlist/proxy;
  (c) run the portable container on an open-egress box pointed at the server's vLLM.

---

## Config hygiene / git workflow

### Server-local edits clobbered on `git pull`
- Private model paths and host mounts kept getting overwritten on pull. **Fix:** all machine-specific
  config now lives in **gitignored** files:
  - `.env` — `DR_EMBEDDING` / `DR_RERANK_MODEL` override `config/pipeline.yaml` without editing it.
  - `docker/docker-compose.override.yml` — host mounts (e.g. the model NFS dir), auto-merged by compose.
  Tracked files stay generic, so pulls never conflict.

---

## Status (2026-06-03)

**Working end-to-end on the H200 server**, fully containerized (`docker-compose run app`):
a local vLLM model via LiteLLM (all 4 roles), local BGE-M3 embeddings + bge-reranker-v2-m3 (via
`DR_EMBEDDING`/`DR_RERANK_MODEL` + the NFS mount), full-page scraping (`search_patch`), cross-encoder
rerank (langchain-classic), and artifact extraction/persistence. Runs produce grounded, cited reports.

**The one open blocker is environmental, not code:** restricted egress (above) caps web-research depth.

## Next / open items
- **Vault wiring (Phase 4)** — duplicate the wiki into `vault_data/`, add a `vault` compose service,
  set `vault.enabled: true` + `RETRIEVER=searx,custom` (or `custom`-only on this locked-down box).
  No internet needed → best fit here and the strongest on-prem demo story.
- **Crawl4AI/Chromium** — only worthwhile on an open-egress deployment; use a prebuilt Playwright base
  image there. Deferred on this server.
- **Egress** — IT allowlist/proxy for broad web research, or run the portable container on an open box
  pointed at the server's vLLM.
- **Dev convenience** — mount `../src:/app/src` in `docker-compose.override.yml` so code changes take
  effect without an image rebuild (only dependency changes then need `docker-compose build app`).
- **Housekeeping** — re-pin the LiteLLM image to a verified `vX.Y.Z-stable`; optionally add
  `langchain-mcp-adapters` to silence the benign `MCPRetriever` import warning.
