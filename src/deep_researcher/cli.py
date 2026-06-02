"""CLI: python -m deep_researcher.cli "<topic>" ["<brief>"] [--refine <artifact_id>]"""
from __future__ import annotations

import argparse
import sys

from .core import run_research


def main() -> int:
    ap = argparse.ArgumentParser(prog="deep-researcher")
    ap.add_argument("topic", help="research topic")
    ap.add_argument("brief", nargs="?", default="", help="optional research brief / focus")
    ap.add_argument("--refine", default=None, help="artifact_id to refine (loads latest version)")
    ap.add_argument("--no-artifact-print", action="store_true", help="print report only")
    args = ap.parse_args()

    report, artifact = run_research(args.topic, args.brief, parent_id=args.refine)
    print(report)
    if not args.no_artifact_print:
        print("\n\n---\nARTIFACT:\n" + artifact.model_dump_json(indent=2))
    print(f"\n[saved artifact {artifact.id} v{artifact.version}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
