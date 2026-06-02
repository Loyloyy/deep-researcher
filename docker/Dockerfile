# deep-researcher app image — runs the pipeline in a container (no host venv).
# Heavy build (torch + crawl4ai + playwright chromium); first build is slow, then cached.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.hf_cache

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git curl \
    && rm -rf /var/lib/apt/lists/*

# Install deps first (better layer caching)
COPY pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip && pip install -e ".[all]"

# Chromium + its OS deps for Crawl4AI
RUN python -m playwright install --with-deps chromium

# Runtime assets
COPY config ./config
COPY eval ./eval
COPY scripts ./scripts

# Default: print CLI usage. Override the command per run.
CMD ["python", "-m", "deep_researcher.cli", "what is retrieval augmented generation"]
