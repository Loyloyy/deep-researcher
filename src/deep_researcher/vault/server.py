"""Vault HTTP service — matches GPT Researcher's `custom` retriever contract.

GPTR's CustomRetriever does: GET {RETRIEVER_ENDPOINT}?query=...&<args>  and expects
a JSON array of {"url": ..., "raw_content": ...}. We serve exactly that over the
duplicated wiki. Wire with:  RETRIEVER=searx,custom  RETRIEVER_ENDPOINT=http://localhost:8090/search

Run:  python -m deep_researcher.vault.server         (reads VAULT_WIKI_DIR, PORT)
"""
from __future__ import annotations

import os
from pathlib import Path

from .index import VaultIndex

DEFAULT_WIKI = Path(os.environ.get("VAULT_WIKI_DIR", "vault_data/wiki"))


def create_app(wiki_dir: str | Path = DEFAULT_WIKI):
    from fastapi import FastAPI, Query

    app = FastAPI(title="deep-researcher vault")
    index = VaultIndex(wiki_dir)

    @app.get("/health")
    def health():
        return {"ok": True, "pages": index.size, "wiki_dir": str(index.wiki_dir)}

    @app.get("/search")
    def search(query: str = Query(...), max_results: int = 5):
        hits = index.search(query, k=max_results)
        # GPTR custom retriever needs url + raw_content; extra keys are ignored.
        return [{"url": h["url"], "raw_content": h["raw_content"]} for h in hits]

    return app


def main() -> int:
    import uvicorn

    port = int(os.environ.get("PORT", "8090"))
    uvicorn.run(create_app(), host="0.0.0.0", port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
