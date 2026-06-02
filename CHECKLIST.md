# deep-researcher — bring-up checklist & usage

**Current mode: fully LOCAL (Ollama) — no frontier APIs, no API keys.**
Everything runs on your machine: LLMs via Ollama, embeddings (BGE-M3) + reranker in-process,
Crawl4AI scraping, SearXNG search, LiteLLM proxy. Verify top-to-bottom.

> Where to find this: repo root. Overview = `README.md`, rationale = `DECISIONS.md`, agent rules = `CLAUDE.md`.

---

## ✅ Bring-up checklist (in order)

### 0. Prereqs
- [ ] Docker + Compose.
- [ ] **Ollama** installed and running (`ollama --version`, `curl -s localhost:11434/api/tags`).
- [ ] A GPU helps but isn't required (small models + BGE run on CPU, just slower).

### 1. Pull local models
```bash
ollama pull qwen2.5:7b-instruct      # strategic + smart (planner/writer)
ollama pull qwen2.5:3b-instruct      # fast (per-source summarizer)
ollama pull llama3.1:8b-instruct     # judge (eval only; different family) — optional
```
- [ ] On a 16 GB box these fit one or two at a time; Ollama loads/unloads on demand (a run that
      switches between 7b and 3b will pause to reload — fine for testing). Swap to smaller models
      (e.g. `qwen2.5:3b` everywhere, or `llama3.2:3b`) if memory is tight. Models are set in
      `docker/litellm/config.yaml`.

### 2. Config (no keys needed)
```bash
cp .env.example .env
```
- [ ] Defaults are fine. `OPENAI_API_KEY` already equals `LITELLM_MASTER_KEY` (app→proxy auth).
- [ ] `OLLAMA_BASE_URL=http://host.docker.internal:11434` (so the proxy *container* reaches host Ollama).

### 3. Start services
```bash
cd docker && docker compose up -d && docker compose ps      # searxng + litellm
```
- [ ] `dr-searxng` + `dr-litellm` both `Up`. If litellm restarts: `docker compose logs litellm | tail -30`.

### 4. Gateway routing (proves the proxy reaches Ollama — do this before any long run)
```bash
cd ..
export $(grep ^LITELLM_MASTER_KEY .env | xargs)
curl -s http://localhost:4000/health/liveliness                         # -> I'm alive!
curl -s http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"model":"strategic","messages":[{"role":"user","content":"say ok"}]}'
```
- [ ] `strategic` returns a JSON answer (first call may be slow — Ollama loads the model). Try `"fast"` too.
- [ ] **Connection error** → proxy can't reach Ollama: confirm Ollama is running and `OLLAMA_BASE_URL`
      uses `host.docker.internal`. **404 model** → run `ollama pull <model>` from step 1.

### 5. Search
```bash
curl -s 'http://localhost:8080/search?q=test&format=json' | head -c 200    # -> JSON
```

### 6. Install the app
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
python -m playwright install chromium      # Crawl4AI needs a browser
```
- [ ] First research run downloads BGE-M3 + bge-reranker (~1.5 GB, one-time).

### 7. First real run
```bash
python -m deep_researcher.cli "What is speculative decoding and when does it help?"
```
- [ ] Report has inline citations + non-empty `sources`; artifact saved at `artifacts/<id>/v01.json`;
      finishes within `wall_clock_timeout_s`.

### 8. Check the fragile seams (read logs once)
- [ ] `cross-encoder rerank enabled (...)` appears. If `rerank disabled — … drift` → run `/gptr-drift`.
- [ ] A few `crawl4ai scrape failed … skip` lines are normal (paywalls/403s). All-empty ⇒ adapter drift.
- [ ] Small local models occasionally emit imperfect JSON for the artifact pass — the code retries once
      and skips malformed rows, so the artifact still saves (may have fewer findings). Bigger model = better.

### 9. Offline sanity (anytime, no services)
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
```

### Python
```python
from deep_researcher import run_research
report_md, artifact = run_research("speculative decoding", brief="cover when it fails")
print(artifact.id, artifact.version)            # -> artifacts/<id>/v01.json
report_md, v2 = run_research("speculative decoding",
                             brief="deepen the acceptance-rate section",
                             parent_id=artifact.id)   # -> v02, lineage preserved
```

### UI
```bash
python -m deep_researcher.ui.gradio_app    # topic in → live progress → report + artifact (edit→refine)
```

### Change a model (no code change)
Edit one block in `docker/litellm/config.yaml`, then `cd docker && docker compose restart litellm`.
Roles: `strategic` = planner, `smart` = writer, `fast` = summarizer, `judge` = eval.
- bigger local model: `model: ollama_chat/qwen2.5:14b-instruct`
- local vLLM: `model: hosted_vllm/<served-name>`, `api_base: os.environ/VLLM_BASE_URL`
- frontier later: `model: openrouter/<provider>/<model>`, `api_key: os.environ/OPENROUTER_API_KEY` (+ key in `.env`)

### Vault ("second brain") — optional
```bash
python scripts/duplicate_vault.py                                   # read-only copy -> vault_data/wiki
VAULT_WIKI_DIR=vault_data/wiki python -m deep_researcher.vault.server   # retriever HTTP on :8090
```
Then set `vault.enabled: true` in `config/pipeline.yaml`. Web + wiki merge into one reranked pool.

### Eval
The `judge` alias is already in the LiteLLM config (llama3.1, different family than qwen):
```bash
JUDGE_MODEL=judge python eval/run_eval.py --limit 5     # writes eval_results.json
```

### Observability — optional
```bash
cd docker && docker compose --profile obs up -d         # langfuse on :3000
# then uncomment success_callback in docker/litellm/config.yaml and: docker compose restart litellm
```

---

## Tuning (`config/pipeline.yaml`)
| Knob | Default | Notes |
|---|---|---|
| `research.scraper` | `crawl4ai` | `bs` for a no-browser run |
| `research.max_iterations` | 3 | research loop cap |
| `research.wall_clock_timeout_s` | 1200 | per-run circuit breaker (raise it — local models are slower) |
| `embedding` | `huggingface:BAAI/bge-m3` | local, in-process |
| `rerank.enabled` / `keep_top_k` | true / 10 | local cross-encoder |
| `cache.enabled` / `staleness_hours` | true / 24 | URL content cache |
| `artifact.enabled` | true | structured extraction pass |
| `vault.enabled` | false | merge the wiki retriever |

**Fastest smoke test (skip the heavy bits):** `scraper: bs`, `rerank.enabled: false`,
`artifact.enabled: false`, and point all roles at `qwen2.5:3b-instruct`.

---

## Going proxy-less (if you really want no LiteLLM)
Possible but not recommended: set `OPENAI_BASE_URL=http://localhost:11434/v1` and `OPENAI_API_KEY=ollama`,
then change `docker/litellm/config.yaml` references — you'd have to hardcode raw model names in the
extraction (`artifact/extract.py`, model `smart`) and eval (`JUDGE_MODEL`) paths, and lose the one-line
frontier swap. Keeping the proxy pointed at Ollama costs one small container and avoids all that.

## Most likely first failure
Ollama not reachable from the container (`OLLAMA_BASE_URL` / host.docker.internal) or a model not pulled.
After that: a GPT Researcher version drift on the fragile seams — run `/gptr-drift` or see `DECISIONS.md`.
