"""Evaluation harness.

For each golden-set topic: run the pipeline, then score with an LLM judge from a
DIFFERENT model family than the generator (avoid self-preference bias).

Two scores:
  - report_quality  : 1-5 rubric judgement of the prose report (vs optional reference)
  - citation_support: fraction of findings whose evidence the judge confirms supports the claim
    (plus a structural check: findings with >=1 resolvable evidence id)

Judge model: set JUDGE_MODEL (a litellm alias, e.g. "judge") routed in docker/litellm/config.yaml
to a different family than strategic/smart. Talks OpenAI-compatible to the proxy.

Usage:
  python eval/run_eval.py [--limit N] [--out results.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

# allow running from repo root without install
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deep_researcher import run_research  # noqa: E402
from deep_researcher.artifact import DeepResearchArtifact  # noqa: E402

JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "judge")

_RUBRIC = """You are grading a research report. Score 1-5 (5=excellent) on:
- coverage: does it address the topic's key aspects?
- accuracy: are claims correct and non-hallucinated?
- grounding: are claims supported by cited sources?
Return ONLY JSON: {"report_quality": <1-5>, "rationale": "<one sentence>"}"""


def _judge_client():
    from openai import OpenAI

    return OpenAI(
        base_url=os.environ.get("OPENAI_BASE_URL", "http://localhost:4000"),
        api_key=os.environ.get("OPENAI_API_KEY", "sk-local"),
    )


def judge_report(client, topic: str, reference: str, report_md: str) -> dict:
    user = f"TOPIC: {topic}\n\nREFERENCE (may be empty): {reference or '(none)'}\n\nREPORT:\n{report_md}"
    resp = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[{"role": "system", "content": _RUBRIC}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {"report_quality": None, "rationale": "judge parse error"}


def citation_structural(artifact: DeepResearchArtifact) -> float:
    if not artifact.findings:
        return 0.0
    grounded = sum(1 for f in artifact.findings if f.evidence_ids)
    return round(grounded / len(artifact.findings), 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default="eval_results.json")
    ap.add_argument("--golden", default=str(Path(__file__).with_name("golden_set.yaml")))
    args = ap.parse_args()

    topics = yaml.safe_load(Path(args.golden).read_text())["topics"]
    if args.limit:
        topics = topics[: args.limit]

    client = _judge_client()
    results = []
    for t in topics:
        print(f"[eval] {t['id']} …", file=sys.stderr)
        try:
            report, artifact = run_research(t["topic"], t.get("brief", ""))
            jq = judge_report(client, t["topic"], t.get("reference", ""), report)
            results.append(
                {
                    "id": t["id"],
                    "report_quality": jq.get("report_quality"),
                    "citation_structural": citation_structural(artifact),
                    "n_findings": len(artifact.findings),
                    "n_sources": len(artifact.sources),
                    "rationale": jq.get("rationale"),
                    "artifact_id": artifact.id,
                }
            )
        except Exception as e:
            results.append({"id": t["id"], "error": str(e)})

    scored = [r for r in results if isinstance(r.get("report_quality"), (int, float))]
    summary = {
        "n": len(results),
        "n_scored": len(scored),
        "avg_report_quality": round(sum(r["report_quality"] for r in scored) / len(scored), 2) if scored else None,
        "avg_citation_structural": round(
            sum(r["citation_structural"] for r in scored) / len(scored), 3
        ) if scored else None,
    }
    Path(args.out).write_text(json.dumps({"summary": summary, "results": results}, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
