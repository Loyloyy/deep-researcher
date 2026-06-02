"""DeepResearchArtifact — the versioned, machine-readable contract.

Consumed (later) by the downstream POC-builder. Kept flat (<=3-4 levels) for
cross-model reliability. Phase 3 fills this via a schema-constrained extraction
pass and validates that every evidence_id resolves to a real Source.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Source(BaseModel):
    id: str
    url: str
    title: str | None = None
    origin: str = "web"  # "web" | "vault"


class Finding(BaseModel):
    claim: str
    evidence_ids: list[str] = Field(default_factory=list)  # -> Source.id, must resolve
    confidence: float = 0.5  # 0..1


class TechStackItem(BaseModel):
    layer: str  # "orchestration" | "inference" | "vector_store" | ...
    choice: str
    rationale: str
    alternatives: list[str] = Field(default_factory=list)


class Architecture(BaseModel):
    name: str
    summary: str
    components: list[str] = Field(default_factory=list)
    diagram_hint: str | None = None


class ReferenceRepo(BaseModel):
    name: str
    url: str
    license: str | None = None
    why_relevant: str


class ImplementationStep(BaseModel):
    order: int
    action: str
    tools: list[str] = Field(default_factory=list)
    est_effort: str | None = None  # "S" | "M" | "L" or hours


class DeepResearchArtifact(BaseModel):
    # ---- versioning / lineage ----
    id: str
    version: int = 1
    parent_id: str | None = None
    generated_at: str
    model_versions: dict = Field(default_factory=dict)

    # ---- request ----
    topic: str
    brief: str = ""

    # ---- content ----
    findings: list[Finding] = Field(default_factory=list)
    recommended_architectures: list[Architecture] = Field(default_factory=list)
    tech_stack: list[TechStackItem] = Field(default_factory=list)
    reference_repos: list[ReferenceRepo] = Field(default_factory=list)
    implementation_steps: list[ImplementationStep] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    report_markdown: str = ""
