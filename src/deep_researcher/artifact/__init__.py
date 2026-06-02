"""Structured, versioned research artifact + extraction/validation/persistence."""
from .extract import extract_artifact, new_artifact_id
from .schema import (
    Architecture,
    DeepResearchArtifact,
    Finding,
    ImplementationStep,
    ReferenceRepo,
    Source,
    TechStackItem,
)
from .store import latest_version, list_artifacts, load, save
from .validate import validate_citations

__all__ = [
    "Source",
    "Finding",
    "TechStackItem",
    "Architecture",
    "ReferenceRepo",
    "ImplementationStep",
    "DeepResearchArtifact",
    "extract_artifact",
    "new_artifact_id",
    "validate_citations",
    "save",
    "load",
    "latest_version",
    "list_artifacts",
]
