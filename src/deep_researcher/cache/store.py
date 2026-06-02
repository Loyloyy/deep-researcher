"""URL-keyed content cache (dependency-free, JSON-on-disk).

Saves repeated scrapes across iterative/re-runs. Honors a staleness window so
fast-moving topics re-fetch. Search/summary caches can layer on the same store later.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

_DEFAULT_DIR = Path(os.environ.get("DR_CACHE_DIR", Path.cwd() / ".dr_cache"))


class ContentCache:
    def __init__(self, root: str | Path | None = None, ttl_hours: int = 24, enabled: bool = True):
        self.root = Path(root) if root else _DEFAULT_DIR
        self.ttl_s = ttl_hours * 3600
        self.enabled = enabled
        if self.enabled:
            self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, url: str) -> Path:
        return self.root / (hashlib.sha256(url.encode()).hexdigest() + ".json")

    def get(self, url: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        p = self._path(url)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        if time.time() - data.get("ts", 0) > self.ttl_s:
            return None
        return data

    def set(self, url: str, content: str, title: str = "", image_urls: list[str] | None = None) -> None:
        if not self.enabled:
            return
        payload = {
            "url": url,
            "content": content,
            "title": title,
            "image_urls": image_urls or [],
            "ts": time.time(),
        }
        try:
            self._path(url).write_text(json.dumps(payload))
        except OSError:
            pass


# Module-level singleton; reconfigured by gptr_runner from RunConfig before a run.
default_cache = ContentCache(enabled=False)


def configure_default_cache(enabled: bool, ttl_hours: int, root: str | Path | None = None) -> ContentCache:
    global default_cache
    default_cache = ContentCache(root=root, ttl_hours=ttl_hours, enabled=enabled)
    return default_cache
