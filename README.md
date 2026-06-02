# deep-researcher

Generic, model-agnostic **deep research pipeline**: give it a topic (+ optional brief), it plans,
searches the web, scrapes/extracts sources, reranks, iterates, and returns a **cited report** plus a
**versioned, machine-readable artifact**. Headless core first; thin Gradio UI on top. The upstream
trigger and downstream POC-builder call `run_research(...)`. See `DECISIONS.md` for every choice + rationale.

## Architecture

```
run_research(topic, brief)                ┌──────────── docker compose ────────────┐
        │                                 │  SearXNG (:8080)   LiteLLM (:4000)      │
        ▼                                 │  vault svc (:8090) Langfuse (:3000,opt) │
  GPT Researcher                          └─────────────────────────────────────────┘
   ├─ RETRIEVER=searx[,custom] ──► SearXNG  (+ vault HTTP service, merged into one pool)
   ├─ SCRAPER=crawl4ai         ──► Crawl4AI (clean markdown; PDFs→PyMuPDF) → URL cache
   ├─ context compression      ──► BGE-M3 embed → CrossEncoder rerank (bge-reranker-v2-m3)
   └─ all LLM calls            ──► LiteLLM proxy ──► OpenRouter / direct API / vLLM
                                     (single switch-point: docker/litellm/config.yaml)
        ▼
  report.md  +  DeepResearchArtifact (versioned, citation-validated, persisted)
```

## Quickstart (server build — full stack)

```bash
# 1. configure
cp .env.example .env          # set LITELLM_MASTER_KEY, OPENAI_API_KEY(=master), OPENROUTER_API_KEY

# 2. confirm OpenRouter model slugs in docker/litellm/config.yaml (strategic/smart/fast)

# 3. services
cd docker && docker compose up -d         # searxng + litellm   (add --profile obs for langfuse)
cd ..

# 4. install (server has the GPU for BGE-M3 + reranker)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"                   # crawl4ai needs: python -m playwright install chromium

# 5. run
python -m deep_researcher.cli "What is speculative decoding and when does it help?"
```

```python
from deep_researcher import run_research
report_md, artifact = run_research("your topic", brief="optional focus")
# refine an existing artifact lineage:
report_md, v2 = run_research("your topic", brief="deepen the eval section", parent_id=artifact.id)
```

## Lightweight local slice (no local models)
Flip in `config/pipeline.yaml`: `scraper: bs`, `embedding: openai:embedding`, `rerank.enabled: false`,
`artifact.enabled: false` — and point an alias at any chat model. Verifies the loop without a GPU.

## Switching models
Edit `docker/litellm/config.yaml` — one block per role (`strategic`/`smart`/`fast`). Point at OpenRouter,
a direct API, or a local vLLM/SGLang server; `docker compose restart litellm`. No app code changes.

## Vault ("second brain") — optional
```bash
python scripts/duplicate_vault.py          # copy ai-engineer-wiki/wiki -> vault_data/wiki (read-only)
VAULT_WIKI_DIR=vault_data/wiki python -m deep_researcher.vault.server   # GPTR custom-retriever HTTP (:8090)
```
Then set `vault.enabled: true` in `config/pipeline.yaml`. Web+vault hits merge into one reranked pool.
An optional MCP server (`python -m deep_researcher.vault.mcp_server`, needs `mcp`) exposes search/fetch
for the downstream POC-builder.

## UI
```bash
python -m deep_researcher.ui.gradio_app    # topic in → live progress → report + artifact (edit→refine)
```

## Eval
Add a `judge` alias (different family than the generator) to `docker/litellm/config.yaml`, then:
```bash
JUDGE_MODEL=judge python eval/run_eval.py --limit 5
```

## Tests
```bash
PYTHONPATH=src python -m pytest tests/ -q   # offline: schema, validation, store, cache, vault BM25
```

## Layout
```
src/deep_researcher/
  core.py  gptr_runner.py  config.py  cli.py
  scrapers/crawl4ai_scraper.py   rerank/patch.py   cache/store.py
  artifact/{schema,extract,validate,store}.py
  vault/{index,server,mcp_server}.py   ui/gradio_app.py
docker/{docker-compose.yml, searxng/settings.yml, litellm/config.yaml}
config/pipeline.yaml   eval/{golden_set.yaml, run_eval.py}   scripts/duplicate_vault.py   tests/
```

## Status
Phases 1–6 implemented. Offline logic (schema/validation/store/cache/vault BM25) verified. Live
model/embedding/scrape calls are validated on the server build. The most version-coupled seam is the
rerank monkeypatch (`rerank/patch.py`) — it degrades gracefully if GPTR internals drift. See `DECISIONS.md`.
