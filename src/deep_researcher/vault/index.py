"""BM25 index over a flat wiki/ directory of markdown entity pages.

Designed for the user's ai-engineer-wiki layout: flat `*.md` pages (H1 + one-sentence
definition + body + ## sections). Returns full-page markdown as `raw_content` so the
pipeline treats vault hits as already-scraped sources (no web fetch). Web+vault hits are
later merged into one pool and reranked on one scale.

Read-only: operates on a DUPLICATED copy (see scripts/duplicate.py) — never the user's repo.
"""
from __future__ import annotations

import re
from pathlib import Path

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class VaultIndex:
    def __init__(self, wiki_dir: str | Path):
        self.wiki_dir = Path(wiki_dir)
        self.names: list[str] = []
        self.paths: list[Path] = []
        self.texts: list[str] = []
        self._bm25 = None
        self._load()

    def _load(self) -> None:
        if not self.wiki_dir.exists():
            return
        for p in sorted(self.wiki_dir.glob("*.md")):
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            self.paths.append(p)
            self.names.append(p.stem)
            self.texts.append(txt)
        if self.texts:
            from rank_bm25 import BM25Okapi

            self._bm25 = BM25Okapi([_tokenize(t) for t in self.texts])

    @property
    def size(self) -> int:
        return len(self.texts)

    def search(self, query: str, k: int = 5) -> list[dict]:
        if not self._bm25 or not self.texts:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        results = []
        for i in ranked[:k]:
            if scores[i] <= 0:
                continue
            results.append(
                {
                    "url": f"vault://wiki/{self.names[i]}.md",
                    "title": self.names[i].replace("-", " "),
                    "raw_content": self.texts[i],
                    "score": float(scores[i]),
                }
            )
        return results
