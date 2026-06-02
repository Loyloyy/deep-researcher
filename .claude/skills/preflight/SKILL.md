---
name: preflight
description: Pre-flight the live stack (LiteLLM proxy routing + SearXNG) before a paid research run.
when_to_use: Invoke before any live/paid `run_research` or CLI pass, or to debug a 401/400 from the gateway.
disable-model-invocation: true
allowed-tools: Bash, Read
---

# Live-stack pre-flight

A live run costs money and ~20 min. This catches a broken gateway in seconds instead. It mirrors
`CHECKLIST.md` §2–§4. Run every step from the repo root; **stop and report at the first failure** —
don't proceed to a paid run until all checks pass.

## 1. Services up
```bash
cd docker && docker compose ps && cd ..
```
Expect `dr-searxng` and `dr-litellm` both `Up`. If litellm is restarting:
`cd docker && docker compose logs litellm | tail -30` — usually a missing key in `.env`.

## 2. LiteLLM liveliness
```bash
curl -s http://localhost:4000/health/liveliness
```
Expect `I'm alive!`.

## 3. Gateway routing — probe each role through the proxy
```bash
export $(grep ^LITELLM_MASTER_KEY .env | xargs)
for role in strategic smart fast; do
  echo "== $role =="
  curl -s http://localhost:4000/v1/chat/completions \
    -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
    -d "{\"model\":\"$role\",\"messages\":[{\"role\":\"user\",\"content\":\"say ok\"}]}"
  echo
done
```
Each role must return a JSON completion.

**Decode failures (this is the high-value part):**
- **401** → `OPENAI_API_KEY` ≠ `LITELLM_MASTER_KEY` in `.env`. The app→proxy auth is the *master key*, not your real provider key. Fix `.env`, `docker compose restart litellm`.
- **400 / credential error** → a bad OpenRouter model slug or key for that role. Confirm the slug at https://openrouter.ai/models and the `litellm_params` block in `docker/litellm/config.yaml`.

## 4. SearXNG returns JSON
```bash
curl -s 'http://localhost:8080/search?q=test&format=json' | head -c 200
```
Expect JSON results (not HTML). If HTML, JSON format isn't enabled in `docker/searxng/settings.yml`.

## 5. Verdict
All four green → cleared for a live run. Report which checks passed and surface any failing
response body verbatim with the decode above. Do **not** kick off a paid `run_research` pass
without the user's explicit go-ahead (hard rule in CLAUDE.md).
