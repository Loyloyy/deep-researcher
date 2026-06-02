"""Versioned, file-per-version artifact persistence.

Layout:  artifacts/<artifact_id>/v<NN>.json
A refinement run loads a parent (latest version), and saves version+1 under the
SAME id with parent_id pointing at the prior version's composite ref. This enables
"deepen section 3" / "incorporate these findings" without regenerating from scratch.
"""
from __future__ import annotations

import json
from pathlib import Path

from .schema import DeepResearchArtifact

ARTIFACTS_ROOT = Path("artifacts")


def _dir(artifact_id: str, root: Path) -> Path:
    return root / artifact_id


def save(artifact: DeepResearchArtifact, root: Path | str = ARTIFACTS_ROOT) -> Path:
    root = Path(root)
    d = _dir(artifact.id, root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"v{artifact.version:02d}.json"
    path.write_text(artifact.model_dump_json(indent=2))
    return path


def load(artifact_id: str, version: int | None = None, root: Path | str = ARTIFACTS_ROOT) -> DeepResearchArtifact:
    root = Path(root)
    d = _dir(artifact_id, root)
    if version is None:
        version = latest_version(artifact_id, root)
    if version is None:
        raise FileNotFoundError(f"no artifact {artifact_id} under {root}")
    return DeepResearchArtifact.model_validate_json((d / f"v{version:02d}.json").read_text())


def latest_version(artifact_id: str, root: Path | str = ARTIFACTS_ROOT) -> int | None:
    d = _dir(artifact_id, Path(root))
    if not d.exists():
        return None
    versions = [int(p.stem[1:]) for p in d.glob("v*.json") if p.stem[1:].isdigit()]
    return max(versions) if versions else None


def list_artifacts(root: Path | str = ARTIFACTS_ROOT) -> list[dict]:
    root = Path(root)
    if not root.exists():
        return []
    out = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        v = latest_version(d.name, root)
        if v is None:
            continue
        meta = json.loads((d / f"v{v:02d}.json").read_text())
        out.append({"id": d.name, "latest_version": v, "topic": meta.get("topic", "")})
    return out
