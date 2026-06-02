"""Optional MCP server over the vault (search + fetch tools).

Same VaultIndex serves both this pipeline (via the HTTP retriever in server.py) and,
later, the downstream POC-builder (via MCP). Kept thin and optional — requires `mcp`.

Run:  python -m deep_researcher.vault.mcp_server     (stdio transport; VAULT_WIKI_DIR env)
"""
from __future__ import annotations

import os
from pathlib import Path

from .index import VaultIndex


def build_server():
    from mcp.server.fastmcp import FastMCP

    wiki_dir = Path(os.environ.get("VAULT_WIKI_DIR", "vault_data/wiki"))
    index = VaultIndex(wiki_dir)
    mcp = FastMCP("deep-researcher-vault")

    @mcp.tool()
    def search(query: str, max_results: int = 5) -> list[dict]:
        """Search the wiki; returns [{url, title, score}] (no body)."""
        return [
            {"url": h["url"], "title": h["title"], "score": h["score"]}
            for h in index.search(query, k=max_results)
        ]

    @mcp.tool()
    def fetch(url: str) -> str:
        """Fetch full markdown for a vault://wiki/<name>.md url."""
        name = url.rsplit("/", 1)[-1].removesuffix(".md")
        p = index.wiki_dir / f"{name}.md"
        return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""

    return mcp


def main() -> int:
    build_server().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
