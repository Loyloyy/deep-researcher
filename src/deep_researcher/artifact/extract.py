"""Structured-artifact extraction pass.

Runs a final schema-constrained pass over the prose report + collected sources to
emit a DeepResearchArtifact. Talks OpenAI-compatible to the LiteLLM proxy, so the
model behind the `smart` alias (OpenRouter/API/vLLM) is irrelevant to this code.

Uses JSON-object mode + Pydantic validation with one repair retry. For open-weight
models that lack reliable JSON mode, prefer a vLLM/SGLang guided-JSON endpoint behind
the alias (see DECISIONS.md).
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from .schema import DeepResearchArtifact, Source
from .validate import validate_citations

_SYSTEM = """You extract a structured research artifact from a finished research report.
Return ONLY a JSON object matching the provided schema. Rules:
- Use ONLY information supported by the report and the listed sources.
- Every finding.evidence_ids entry MUST be an id from the provided sources list. Do not invent ids.
- Keep claims atomic and specific. confidence in [0,1].
- If a section has no support, return an empty list for it. Do not fabricate repos, licenses, or steps.
"""


def _schema_hint() -> str:
    # A compact, model-friendly description of the target shape.
    return json.dumps(
        {
            "findings": [{"claim": "str", "evidence_ids": ["src-id"], "confidence": 0.0}],
            "recommended_architectures": [
                {"name": "str", "summary": "str", "components": ["str"], "diagram_hint": "str|null"}
            ],
            "tech_stack": [
                {"layer": "str", "choice": "str", "rationale": "str", "alternatives": ["str"]}
            ],
            "reference_repos": [
                {"name": "str", "url": "str", "license": "str|null", "why_relevant": "str"}
            ],
            "implementation_steps": [
                {"order": 1, "action": "str", "tools": ["str"], "est_effort": "S|M|L"}
            ],
            "open_questions": ["str"],
        },
        indent=2,
    )


def _client():
    from openai import OpenAI

    return OpenAI(
        base_url=os.environ.get("OPENAI_BASE_URL", "http://localhost:4000"),
        api_key=os.environ.get("OPENAI_API_KEY", "sk-local"),
    )


def _user_prompt(topic: str, brief: str, report_md: str, sources: list[Source]) -> str:
    src_lines = "\n".join(f"- {s.id} | {s.origin} | {s.url} | {s.title or ''}" for s in sources)
    return (
        f"TOPIC:\n{topic}\n\nBRIEF:\n{brief or '(none)'}\n\n"
        f"SOURCES (use these ids for evidence_ids):\n{src_lines or '(none)'}\n\n"
        f"REPORT:\n{report_md}\n\n"
        f"Return a JSON object with exactly these keys:\n{_schema_hint()}"
    )


def _call(client, model: str, messages: list[dict]) -> dict:
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    return json.loads(resp.choices[0].message.content)


def extract_artifact(
    *,
    topic: str,
    brief: str,
    report_md: str,
    sources: list[Source],
    artifact_id: str,
    version: int = 1,
    parent_id: str | None = None,
    model: str = "smart",
    model_versions: dict | None = None,
) -> DeepResearchArtifact:
    client = _client()
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _user_prompt(topic, brief, report_md, sources)},
    ]

    raw: dict = {}
    try:
        raw = _call(client, model, messages)
    except Exception:
        # one repair retry with an explicit nudge
        messages.append({"role": "user", "content": "Return STRICT valid JSON only, no prose."})
        try:
            raw = _call(client, model, messages)
        except Exception:
            raw = {}

    artifact = DeepResearchArtifact(
        id=artifact_id,
        version=version,
        parent_id=parent_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        model_versions=model_versions or {},
        topic=topic,
        brief=brief,
        sources=sources,
        report_markdown=report_md,
        findings=_coerce_list(raw.get("findings"), "Finding"),
        recommended_architectures=_coerce_list(raw.get("recommended_architectures"), "Architecture"),
        tech_stack=_coerce_list(raw.get("tech_stack"), "TechStackItem"),
        reference_repos=_coerce_list(raw.get("reference_repos"), "ReferenceRepo"),
        implementation_steps=_coerce_list(raw.get("implementation_steps"), "ImplementationStep"),
        open_questions=list(raw.get("open_questions") or []),
    )

    # Drop hallucinated citations (evidence_ids that don't resolve to a real source).
    artifact = validate_citations(artifact)
    return artifact


def new_artifact_id() -> str:
    return f"dra-{uuid.uuid4().hex[:12]}"


def _coerce_list(items, model_name: str):
    from . import schema as _schema

    cls = getattr(_schema, model_name)
    out = []
    for it in items or []:
        try:
            out.append(cls(**it))
        except Exception:
            continue  # skip malformed rows rather than fail the whole artifact
    return out
