"""Cross-encoder rerank stage for GPT Researcher's context compression.

GPTR's ContextCompressor builds a DocumentCompressorPipeline of
[splitter, EmbeddingsFilter]. We rebuild it as
[splitter, EmbeddingsFilter(wide), CrossEncoderReranker(keep_top_k)] so each
scraped source is wide-retrieved by embeddings then reranked by a cross-encoder
before summarization — the single highest-impact relevance fix.

The target method is name-mangled (``__get_contextual_retriever``), so we monkeypatch
``_ContextCompressor__get_contextual_retriever`` rather than subclass. Everything is
wrapped defensively: if GPTR's internals have drifted, we log and leave the default
pipeline intact instead of breaking the run.
"""
from __future__ import annotations

import functools
import logging

logger = logging.getLogger(__name__)

_PATCHED = False
_RERANKER_CACHE: dict[str, object] = {}


def _get_reranker(model_name: str, top_k: int):
    """Lazily build (and cache) a LangChain CrossEncoderReranker."""
    key = f"{model_name}:{top_k}"
    if key in _RERANKER_CACHE:
        return _RERANKER_CACHE[key]
    from langchain.retrievers.document_compressors import CrossEncoderReranker
    from langchain_community.cross_encoders import HuggingFaceCrossEncoder

    encoder = HuggingFaceCrossEncoder(model_name=model_name)
    reranker = CrossEncoderReranker(model=encoder, top_n=top_k)
    _RERANKER_CACHE[key] = reranker
    return reranker


def enable_reranker(model_name: str, retrieve_top_n: int = 50, keep_top_k: int = 10) -> bool:
    """Monkeypatch ContextCompressor to add a cross-encoder rerank stage. Idempotent."""
    global _PATCHED
    if _PATCHED:
        return True
    try:
        from gpt_researcher.context.compression import ContextCompressor
        from langchain.retrievers import ContextualCompressionRetriever
        from langchain.retrievers.document_compressors import (
            DocumentCompressorPipeline,
            EmbeddingsFilter,
        )
        from langchain_community.document_transformers import EmbeddingsRedundantFilter
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except Exception as e:
        logger.warning("rerank disabled — could not import GPTR/LangChain internals: %s", e)
        return False

    def patched_get_contextual_retriever(self):
        # Fail-safe: any error here degrades to GPTR's default (unreranked) retriever
        # rather than breaking the whole research run.
        try:
            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
            redundant = EmbeddingsRedundantFilter(embeddings=self.embeddings)  # dedup near-identical chunks
            threshold = getattr(self, "similarity_threshold", 0.42)
            relevance = EmbeddingsFilter(
                embeddings=self.embeddings, similarity_threshold=threshold, k=retrieve_top_n
            )
            reranker = _get_reranker(model_name, keep_top_k)
            pipeline = DocumentCompressorPipeline(
                transformers=[splitter, redundant, relevance, reranker]
            )
            # Reuse GPTR's original builder for a correctly-wired base retriever over
            # self.documents, then swap in our reranking compressor pipeline.
            original_retriever = _ORIGINAL(self)
            original_retriever.base_compressor = pipeline
            return original_retriever
        except Exception as e:
            logger.warning("rerank step failed at runtime; using default retriever: %s", e)
            return _ORIGINAL(self)

    # capture the original mangled method
    global _ORIGINAL
    _ORIGINAL = getattr(ContextCompressor, "_ContextCompressor__get_contextual_retriever", None)
    if _ORIGINAL is None:
        logger.warning("rerank disabled — ContextCompressor.__get_contextual_retriever not found (drift?)")
        return False

    ContextCompressor._ContextCompressor__get_contextual_retriever = functools.wraps(_ORIGINAL)(
        patched_get_contextual_retriever
    )
    _PATCHED = True
    logger.info("cross-encoder rerank enabled (%s, top_k=%d)", model_name, keep_top_k)
    return True


_ORIGINAL = None
