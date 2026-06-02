# DECISIONS

Running log of non-trivial choices and rationale. Newest phases appended over time.

## Phase 0 — Validation & foundation (2026-06-01)

### Environment (verified on dev box)
- Docker 28 + Compose v2.34 present → self-host SearXNG/LiteLLM/Langfuse locally.
- GPU: **RTX 5000 Ada Laptop, 16 GB** = the "limited GPU" profile. Runs BGE-M3 + reranker
  comfortably, but cannot host an 8B embedder *and* a local generation model simultaneously.
  The multi-H200 server is the "quality" profile; frontier APIs the third.
- Python 3.10.12, no `gh` CLI (use `git`/web), Node 20.

### Core framework — **GPT Researcher** (confirmed default, §5.1)
- Validated: SearXNG is a built-in retriever (`searx`); role LLMs are `STRATEGIC/SMART/FAST_LLM`
  in `provider:model` form; the `openai:` provider honors `OPENAI_BASE_URL` → can point at LiteLLM.
- Considered `open_deep_research` (LangGraph-native, more rewireable — cleaner home for the
  custom rerank + vault-merge nodes) and DeerFlow 2.0 (heavyweight superagent runtime, overkill).
- **Decision:** GPT Researcher, per the brief's default. The one friction noted: the cross-encoder
  rerank and vault↔web merge sit *inside* GPTR's retrieve→compress loop, which is semi-closed —
  we'll inject them via a custom context-compressor / custom retriever rather than graph nodes.
  Accepted in exchange for fastest time-to-first-report and 1:1 fit with the brief's config surface.

### Search — **SearXNG** self-hosted, `RETRIEVER=searx` (§5.2, LOCKED)
- `SEARX_URL` env, JSON format enabled in `settings.yml`. Fallbacks (serper/brave) stay config-swappable.
- **AgentSearch (`brcrusoe72/agent-search`) — REJECTED as a dependency.** It's an all-in-one that
  fuses search+extraction+cache+MCP (~25 stars), which violates our decoupling principle and adds
  low-maturity risk. Will mine it for two ideas only: prompt-injection scrubbing + paywall/403 detection.

### Extraction — **Crawl4AI**, but as a CUSTOM SCRAPER ADAPTER (§5.3)
- **Correction to brief:** Crawl4AI is *not* a built-in GPTR scraper. Built-ins are `bs` / `browser`
  / `tavily_extract` / `firecrawl`. So Crawl4AI = a thin custom adapter (lands Phase 2).
- **Phase 1 uses the built-in `bs` scraper** to get the happy path working with zero custom code.
  Self-hosted Firecrawl remains the zero-custom fallback if the adapter proves fiddly.

### Model gateway — **LiteLLM Proxy**, pinned (§5.4, LOCKED + security)
- **Pinned to `1.83.0`** (rebuilt, verified-clean release after the Mar 24 2026 supply-chain
  incident; malicious `1.82.7`/`1.82.8`). Pinned in both `pyproject.toml` and the docker image tag.
  Bump only after changelog review + `pip-audit`.
- **The proxy is the single switch-point.** GPTR always calls aliases `strategic/smart/fast/embedding`;
  swapping Claude↔OpenAI↔vLLM for any role = editing one `litellm_params` block. Satisfies the
  user's "easily change between frontier models / vLLM" requirement with no app/code changes.

### Roles & Phase-1 default models (§5.5)
- Planner (`strategic`) = Claude Opus; Writer (`smart`) = Claude Opus; Summarizer (`fast`, high-volume)
  = Claude Haiku. Embeddings (Phase 1) = OpenAI `text-embedding-3-small` via the proxy.
- Caps: `max_iterations=3`, `max_search_results_per_query=5`, `wall_clock_timeout_s=900`.
  (Phase 1 has wall-clock + iteration caps; a mid-run token/cost circuit breaker comes with the
  quality layer.)

### Embeddings — **BGE-M3** default (§5.7)
- Default to BGE-M3 (+ `bge-reranker-v2-m3`) — fits 16 GB easily, CPU-capable, hybrid-in-one,
  already in the user's prod stack. Qwen3-Embedding-4B/8B + Qwen3-reranker = opt-in "h200 quality".
- **Phase 1 deviation:** to avoid pulling torch into the first slice, embeddings route through the
  proxy to OpenAI. Phase 2 swaps `EMBEDDING` to local BGE-M3.

### Reranker — **bge-reranker-v2-m3**, custom node (§5.8, LOCKED) — Phase 2.

### Vault / second brain — **MCP `search`/`fetch` server** (§5.6)
- Inspected the real vault: `ai-engineer-wiki/` (367 md). Flat `wiki/*.md` entity pages (H1 +
  one-sentence def + inline `[Page-Name](Page-Name.md)` links + `## Practical application` /
  `## Opinions` / `## Notes`), a curated `index.md` catalog with per-page descriptions, gitignored
  raw `transcripts/`. Near-ideal for MCP search/fetch (index descriptions + crosslink graph = signal).
- **Decision:** MCP server over a **duplicated, read-only** copy (never write back to the user's repo).
  Same server serves this pipeline now and the downstream POC-builder later. Ranking: merge vault+web
  into one candidate pool reranked on one scale; dedup vault↔web. Phase 4. Stubbed behind `vault.enabled`.

### Observability — **Langfuse** (§5.10, LOCKED)
- Self-hosted, opt-in via the `obs` docker profile. Wired at the gateway: enabling
  `success_callback: ["langfuse"]` in the LiteLLM config emits per-call token/cost/latency traces
  with zero app code. Stage-level spans come later.

### Output — **DeepResearchArtifact** pydantic schema seeded now (§7) — extraction pass is Phase 3.

### Deployment — headless core first (`run_research`), Gradio later (§5.11). UI never holds pipeline logic.

## Phase 0b — OpenRouter + build-out decision (2026-06-01)

- **Frontier via OpenRouter** (user preference). Config-only: `strategic/smart/fast` aliases →
  `openrouter/<provider>/<model>`, `api_key: os.environ/OPENROUTER_API_KEY`. **No app code changed.**
- **OpenRouter has no embeddings endpoint** → embedding default moved to **local BGE-M3 in-process**
  (`EMBEDDING=huggingface:BAAI/bge-m3`), brought forward from Phase 2. The OpenAI `embedding` alias
  remains as a commented alternative. Net effect: the frontier path is 100% OpenRouter, no stray OpenAI dep.
- **Build strategy:** user will validate on the H200 server (where the models live), so we build
  Phases 2–6 fully here first, keep heavy deps behind lazy imports, and mark the few "verify on server"
  seams. Pipeline defaults in `config/pipeline.yaml` now assume the FULL stack; flip to the lightweight
  combo (scraper=bs, embedding=openai:embedding, rerank/artifact off) for a no-local-models run.

## Phases 2–6 — implementation choices (2026-06-01)

### P2 Extraction — Crawl4AI adapter
- GPTR scrapers get only the URL (no query) and must return `(content, image_urls, title)` via
  `scrape_async`. Adapter uses `PruningContentFilter -> fit_markdown` (query-agnostic clean extraction);
  registered by injecting into `SCRAPER_CLASSES["crawl4ai"]`. PDFs/arxiv still auto-route to PyMuPDF/Arxiv.
  Failures (paywall/403/timeout) return empty + log, never crash the run. **Verify on server:** exact
  Crawl4AI result fields across the installed version.

### P2 Rerank — monkeypatch, not subclass
- `ContextCompressor.__get_contextual_retriever` is name-mangled → subclassing can't override it. We patch
  `_ContextCompressor__get_contextual_retriever` to rebuild the pipeline as
  `[splitter, EmbeddingsRedundantFilter, EmbeddingsFilter(k=retrieve_top_n), CrossEncoderReranker(top_n=keep_top_k)]`
  using LangChain components GPTR already ships. Wrapped in try/except: on internal drift it logs and
  leaves GPTR's default behavior intact. **Verify on server** — this is the most version-coupled piece.

### P2 Cache — dependency-free URL-keyed JSON store with TTL; consulted inside the Crawl4AI adapter.

### P3 Artifact — extraction pass via OpenAI-compatible client → LiteLLM `smart` alias, JSON-object mode +
  Pydantic validation + one repair retry; malformed rows skipped. Citation validation drops evidence_ids
  that don't resolve to a real Source. Versioned file-per-version store (`artifacts/<id>/vNN.json`);
  refinement loads a parent, bumps version, feeds prior findings into the brief. `run_research` now always
  returns `(report_md, DeepResearchArtifact)`. **Verify on server:** open-weight JSON-mode reliability —
  prefer vLLM/SGLang guided-JSON behind the alias if needed.

### P4 Vault — BM25 (`rank_bm25`) over the duplicated flat `wiki/*.md`. Served two ways from one index:
  an HTTP service matching GPTR's `custom` retriever contract (`GET /search?query=` → `[{url, raw_content}]`,
  wired via `RETRIEVER=searx,custom`) for THIS pipeline, and an optional MCP server (search/fetch) for the
  downstream POC-builder. Merge happens natively in the multi-retriever pool; web+vault chunks then rerank
  on one scale. `scripts/duplicate_vault.py` copies the wiki read-only (never writes back). Tested offline
  against the real 367-page wiki. (Upgrade path: swap BM25 → BGE-M3 dense/hybrid if recall needs it.)

### P5 UI — Gradio over the core: topic/brief in, live progress via a queue log-handler streamed to a
  textbox, report tab, artifact tab (editable JSON) + Refine button (parent_id). No pipeline logic in the UI.

### P6 Eval — 18-topic golden set (10 AI-eng + 8 general, to keep it honestly generic). LLM judge via a
  `judge` alias that must route to a DIFFERENT family than the generator. Scores report_quality (1–5 rubric)
  + citation_structural (fraction of findings with resolvable evidence). Add a `judge` model to the LiteLLM
  config before running.

## Local-first deployment (2026-06-01)

- **Default deployment is now fully LOCAL via Ollama** — no frontier APIs, no keys. Everything in the
  stack was already local (BGE-M3 embeddings in-process, bge-reranker in-process, Crawl4AI, SearXNG);
  only the LLM calls were remote. Switching them to local = repointing the LiteLLM aliases at Ollama.
- **"Is LiteLLM needed?" — kept, pointed at local.** It's not strictly required (GPTR could hit Ollama's
  OpenAI endpoint directly), but keeping it means the artifact-extraction pass and eval judge (which call
  the `smart`/`judge` aliases) work unchanged, model names stay out of app code (rule #1), and the
  one-line frontier swap is preserved. Cost: one small container. Going proxy-less is documented in
  CHECKLIST as a non-recommended option.
- **Changes (config-only, zero app code):** `docker/litellm/config.yaml` → `ollama_chat/<model>` for
  strategic(qwen2.5:7b)/smart(qwen2.5:7b)/fast(qwen2.5:3b)/judge(llama3.1:8b, different family);
  docker-compose litellm gets `extra_hosts: host.docker.internal:host-gateway` so the container reaches
  host Ollama; `.env.example` drops required keys, adds `OLLAMA_BASE_URL`. Embeddings stay local BGE-M3.
- Frontier remains a one-line swap per role (openrouter/anthropic/vllm) — the model-agnostic goal holds.

### Verified offline this session
- Config load, citation validation, artifact store round-trip + versioning, cache set/get + staleness,
  and a real BM25 vault search over the 367-page wiki — all pass. The only unverified parts are the live
  model/embedding/scrape calls, which are the server's job.
