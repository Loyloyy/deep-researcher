"""Duplicate the user's LLM Wiki into a read-only working copy for the pipeline.

Never writes back to the source repo. Copies only `wiki/*.md` (the entity pages);
ignores transcripts/.git/etc.

Usage:
  python scripts/duplicate_vault.py [SOURCE_WIKI_DIR] [DEST_DIR]
  # defaults: SOURCE=/mnt/d/aloy/personal/ai-engineer-wiki/wiki  DEST=vault_data/wiki
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

DEFAULT_SOURCE = Path("/mnt/d/aloy/personal/ai-engineer-wiki/wiki")
DEFAULT_DEST = Path("vault_data/wiki")


def main(argv: list[str]) -> int:
    source = Path(argv[1]) if len(argv) > 1 else DEFAULT_SOURCE
    dest = Path(argv[2]) if len(argv) > 2 else DEFAULT_DEST
    if not source.exists():
        print(f"source not found: {source}", file=sys.stderr)
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in source.glob("*.md"):
        shutil.copy2(p, dest / p.name)
        n += 1
    print(f"copied {n} wiki pages -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
