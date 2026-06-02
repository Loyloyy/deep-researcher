# deep-researcher — server checklist & usage

A practical runbook for bringing the pipeline up on the server (where the models live)
and using it. Verify top-to-bottom; each layer builds on the previous one.

---

## ✅ Bring-up checklist (in order)

### 1. Config
- [ ] `.env` exists (`cp .env.example .env`).
- [ ] `OPENAI_API_KEY` **==** `LITELLM_MASTER_KEY` — this is the app→proxy auth, **not** your real key.
- [ ] `OPENROUTER_API_KEY` set.
- [ ] `docker/litellm/config.yaml`: the 3 OpenRouter slugs (`strategic`/`smart`/`fast`) are real — confirm at https://openrouter.ai/models.

### 2. Services up
```bash
cd docker && docker compose up -d && docker compose ps   # add --profile obs for langfuse
```
- [ ] `dr-searxng` and `dr-litellm` both show `Up`.
- [ ] If litellm restarts: `docker compose logs litellm | tail -30` (usually a missing key in `.env`).

### 3. Gateway routing (catch model problems before a 5-min run)
```bash
export $(grep ^LITELLM_MASTER_KEY .env | xargs)
curl -s http://localhost:4000/health/liveliness                         # -> I'm alive!
curl -s http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"model":"strategic","messages":[{"role":"user","content":"say ok"}]}'
```
- [ ] `strategic` returns a JSON answer. Repeat with `"model":"fast"` (and `"smart"`).
- [ ] **401** = `OPENAI_API_KEY` ≠ master key. **400 / credential** = bad OpenRouter slug or key.

### 4. Search
```bash
curl -s 'http://localhost:8080/search?q=test&format=json' | head -c 200    # -> JSON
```
- [ ] SearXNG returns JSON results.

### 5. Install
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
python -m playwright install chromium      # Crawl4AI needs a browser
```
- [ ] First research run downloads BGE-M3 + bge-reranker (~1.5 GB) — expected, one-time.

### 6. First real run
```bash
python -m deep_researcher.cli "What is speculative decoding and when does it help?"
```
- [ ] Report has **inline citations** and a non-empty `sources` list.
- [ ] Artifact saved at `artifacts/<id>/v01.json`.
- [ ] Run finishes within `wall_clock_timeout_s` (default 1200s) and stops at `max_iterations`.

### 7. Check the fragile seams (read the logs once)
- [ ] Log shows `cross-encoder rerank enabled (...)`. If instead `rerank disabled — … drift`, GPTR
      internals moved — paste it, it's a quick patch. (Pipeline still runs without rerank.)
- [ ] A few `crawl4ai scrape failed … skip` lines are normal (paywalls/403s). **All** sources empty
      ⇒ adapter/field drift — check `crawl4ai_scraper.py`.

### 8. Offline sanity (anytime, no services/keys)
```bash
PYTHONPATH=src python -m pytest tests/ -q
```

---

## How to use

### CLI
```bash
python -m deep_researcher.cli "your topic"
python -m deep_researcher.cli "your topic" "optional brief / focus"
python -m deep_researcher.cli "your topic" --refine dra-abc123   # extend an existing artifact
python -m deep_researcher.cli "your topic" --no-artifact-print   # report only
```

### Python
```python
from deep_researcher import run_research

report_md, artifact = run_research("speculative decoding", brief="cover when it fails")
print(artifact.id, artifact.version)          # -> artifacts/<id>/v01.json

# Refine: take a prior artifact as input, deepen/extend it (lineage preserved)
report_md, v2 = run_research(
    "speculative decoding",
    brief="deepen the acceptance-rate section",
    parent_id=artifact.id,                    # -> v02 under the same id
)
```

### UI
```bash
python -m deep_researcher.ui.gradio_app
```
Topic in → live progress → **Report** tab → **Artifact** tab (edit the JSON, hit **Refine** for the next version).

### Switch a model (no code change)
Edit one block in `docker/litellm/config.yaml` (e.g. point `fast` at a local vLLM:
`model: hosted_vllm/<served-name>`, `api_base: os.environ/VLLM_BASE_URL`), then:
```bash
cd docker && docker compose restart litellm
```
Roles: `strategic` = planner, `smart` = report writer, `fast` = high-volume per-source summarizer.

### Vault ("second brain") — optional
```bash
python scripts/duplicate_vault.py                                   # read-only copy -> vault_data/wiki
VAULT_WIKI_DIR=vault_data/wiki python -m deep_researcher.vault.server   # HTTP retriever on :8090
```
Then set `vault.enabled: true` in `config/pipeline.yaml`. Web + wiki hits merge into one reranked pool.
Optional MCP server for the downstream POC-builder: `python -m deep_researcher.vault.mcp_server` (needs `pip install mcp`).

### Eval
Add a `judge` alias (a **different** model family than the generator) to `docker/litellm/config.yaml`, then:
```bash
JUDGE_MODEL=judge python eval/run_eval.py --limit 5      # drop --limit for the full 18-topic set
```
Writes `eval_results.json` (avg report_quality 1–5 + citation_structural).

### Observability — optional
```bash
cd docker && docker compose --profile obs up -d          # langfuse on :3000
# then uncomment `success_callback: ["langfuse"]` in docker/litellm/config.yaml and:
docker compose restart litellm
```

---

## Tuning (`config/pipeline.yaml`)
| Knob | Default | Notes |
|---|---|---|
| `research.scraper` | `crawl4ai` | `bs` for a no-browser run |
| `research.max_iterations` | 3 | research loop cap (cost) |
| `research.wall_clock_timeout_s` | 1200 | per-run circuit breaker |
| `embedding` | `huggingface:BAAI/bge-m3` | `openai:embedding` to route via proxy |
| `rerank.enabled` / `keep_top_k` | true / 10 | cross-encoder rerank stage |
| `cache.enabled` / `staleness_hours` | true / 24 | URL content cache |
| `artifact.enabled` | true | structured extraction pass |
| `vault.enabled` | false | merge the wiki retriever |

**No-GPU local slice:** `scraper: bs`, `embedding: openai:embedding`, `rerank.enabled: false`,
`artifact.enabled: false` — verifies the loop without local models.

---

## Most likely first failure
A GPT Researcher version drift on a method/field name (e.g. `get_research_sources`, the
`SCRAPER_CLASSES` registry, or the `ContextCompressor` internals the rerank patch targets). All are
wrapped to degrade rather than crash — paste the traceback or the `rerank disabled` log line and it's a
small patch. See `DECISIONS.md` for where each seam attaches.
