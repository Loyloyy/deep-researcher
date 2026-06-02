# deep-researcher — bring-up checklist & usage

**Models are declared in `.env`** — three roles (strategic / smart / fast) + a judge, each
independently an on-prem vLLM server or a frontier API. LiteLLM routes them behind one
OpenAI-compatible URL. Everything else (embeddings BGE-M3, reranker, Crawl4AI, SearXNG) runs local.

> Where to find this: repo root. Overview = `README.md`, rationale = `DECISIONS.md`, agent rules = `CLAUDE.md`.

---

## ✅ Bring-up checklist (in order)

### 0. Prereqs
- [ ] Docker + Compose.
- [ ] Your model server(s) running. Default = **vLLM**, OpenAI-compatible:
      `python -m vllm.entrypoints.openai.api_server --model <path> --port 8000` (one model per port).
- [ ] Decide the topology (see `## Model topology` below): one model for all roles (one vLLM, one port)
      or different models per role (one vLLM per port).

### 1. Declare models in `.env`
```bash
cp .env.example .env
```
Edit the per-role triples — `MODEL` (provider/id) + `API_BASE` + `API_KEY`. Example, one big model
for plan/write + a small one for the high-volume summarizer:
```
STRATEGIC_MODEL=hosted_vllm/qwen2.5-72b-instruct   STRATEGIC_API_BASE=http://host.docker.internal:8000/v1   STRATEGIC_API_KEY=dummy
SMART_MODEL=hosted_vllm/qwen2.5-72b-instruct        SMART_API_BASE=http://host.docker.internal:8000/v1       SMART_API_KEY=dummy
FAST_MODEL=hosted_vllm/qwen2.5-7b-instruct          FAST_API_BASE=http://host.docker.internal:8001/v1        FAST_API_KEY=dummy
```
- [ ] `OPENAI_API_KEY` == `LITELLM_MASTER_KEY` (app→proxy auth).
- [ ] vLLM on the host is reachable as `host.docker.internal:<port>` from the proxy container (compose `extra_hosts`).
      A frontier role instead: `MODEL=openrouter/<prov>/<model>`, `API_BASE=https://openrouter.ai/api/v1`, `API_KEY=<key>`.

### 2. Start services
```bash
cd docker && docker compose up -d && docker compose ps      # searxng + litellm
```
- [ ] `dr-searxng` + `dr-litellm` both `Up`. If litellm restarts: `docker compose logs litellm | tail -30`
      (usually a `.env` var unset, or a bad MODEL/API_BASE).

### 3. Gateway routing (proves each role reaches its model — do before any long run)
```bash
cd ..
export $(grep ^LITELLM_MASTER_KEY .env | xargs)
curl -s http://localhost:4000/health/liveliness                         # -> I'm alive!
for role in strategic smart fast; do
  echo "== $role =="
  curl -s http://localhost:4000/v1/chat/completions \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
    -d "{\"model\":\"$role\",\"messages\":[{\"role\":\"user\",\"content\":\"say ok\"}]}"
done
```
- [ ] each role returns a JSON answer. **Connection refused** → that role's vLLM isn't up / wrong
      `API_BASE` (host.docker.internal). **404 model** → `MODEL` id doesn't match what vLLM serves.

### 4. Search
```bash
curl -s 'http://localhost:8080/search?q=test&format=json' | head -c 200    # -> JSON
```

### 5. Install the app
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
python -m playwright install chromium      # Crawl4AI needs a browser
```
- [ ] First research run downloads BGE-M3 + bge-reranker (~1.5 GB, one-time).

### 6. First real run
```bash
python -m deep_researcher.cli "What is speculative decoding and when does it help?"
```
- [ ] Report has inline citations + non-empty `sources`; artifact saved at `artifacts/<id>/v01.json`;
      finishes within `wall_clock_timeout_s`.

### 7. Check the fragile seams (read logs once)
- [ ] `cross-encoder rerank enabled (...)` appears. If `rerank disabled — … drift` → run `/gptr-drift`.
- [ ] A few `crawl4ai scrape failed … skip` lines are normal. All-empty ⇒ adapter drift.
- [ ] Small models occasionally emit imperfect JSON for the artifact pass — code retries once + skips
      bad rows, so the artifact still saves (maybe fewer findings). A stronger `smart` model fixes it.

### 8. Offline sanity (anytime, no services)
```bash
PYTHONPATH=src python -m pytest tests/ -q
```

---

## Model topology (how the 3 roles map to model servers)

The pipeline uses **all three roles in every run, automatically** — strategic plans, fast summarizes
each source (many calls), smart writes the report. You bind a model to each.

- **One model, all 3 roles:** point STRATEGIC/SMART/FAST at the same vLLM (same `API_BASE` + `MODEL`).
  Simplest; one vLLM server.
- **Different model per role:** run a vLLM per model (different ports) and give each role its own
  `API_BASE`. LiteLLM routes by role to the right port — this is exactly why the proxy is here.
- **Mixed local + frontier:** e.g. SMART on OpenRouter, FAST on local vLLM — set each role's triple
  accordingly. Works because each role is independent in `.env`.

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
report_md, v2 = run_research("speculative decoding", brief="deepen the eval section",
                             parent_id=artifact.id)   # -> v02, lineage preserved
```

### UI
```bash
python -m deep_researcher.ui.gradio_app    # topic in → live progress → report + artifact (edit→refine)
```

### Change a model
Edit the role's triple in `.env`, then `cd docker && docker compose restart litellm`. No code, no
`config.yaml` edit (it's a fixed template).

### Vault ("second brain") — optional
```bash
python scripts/duplicate_vault.py                                   # read-only copy -> vault_data/wiki
VAULT_WIKI_DIR=vault_data/wiki python -m deep_researcher.vault.server   # retriever HTTP on :8090
```
Then set `vault.enabled: true` in `config/pipeline.yaml`. Web + wiki merge into one reranked pool.

### Eval
The `judge` role is already wired (set `JUDGE_*` in `.env` to a different family than the generator):
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
| `research.wall_clock_timeout_s` | 1200 | per-run circuit breaker (raise for slow local models) |
| `embedding` | `huggingface:BAAI/bge-m3` | local, in-process |
| `rerank.enabled` / `keep_top_k` | true / 10 | local cross-encoder |
| `cache.enabled` / `staleness_hours` | true / 24 | URL content cache |
| `artifact.enabled` | true | structured extraction pass |
| `vault.enabled` | false | merge the wiki retriever |

**Fastest smoke test:** point all three roles at one small vLLM model, and set `scraper: bs`,
`rerank.enabled: false`, `artifact.enabled: false`.

---

## Most likely first failure
A role's vLLM not reachable from the proxy container (`API_BASE` / host.docker.internal) or a `MODEL`
id that doesn't match what vLLM serves. After that: a GPT Researcher version drift on the fragile
seams — run `/gptr-drift` or see `DECISIONS.md`.
