"""
Embedding Service
Generates vector embeddings for BOM text using Azure OpenAI (text-embedding-3-large).
Falls back to a deterministic mock when credentials are not configured so the rest
of the pipeline can be exercised locally without Azure access.
"""
import hashlib
import logging
import math
import os
from typing import List

logger = logging.getLogger(__name__)

# Embedding dimension for text-embedding-3-large
EMBEDDING_DIM = 3072


# ── Mock embedding (deterministic hash-based) ─────────────────────────────────

def _mock_embedding(text: str) -> List[float]:
    """
    Produce a deterministic unit-normalised vector from a SHA-256 hash.
    Useful for local dev / testing without an Azure key.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    # Repeat digest bytes to fill EMBEDDING_DIM floats
    raw: List[float] = []
    while len(raw) < EMBEDDING_DIM:
        for b in digest:
            raw.append((b - 127.5) / 127.5)  # normalise to [-1, 1]
            if len(raw) == EMBEDDING_DIM:
                break
    # L2 normalise
    norm = math.sqrt(sum(v * v for v in raw)) or 1.0
    return [v / norm for v in raw]


# ── Azure OpenAI embedding client ─────────────────────────────────────────────

_embedding_client = None


def _get_embedding_client():
    global _embedding_client
    if _embedding_client is not None:
        return _embedding_client

    try:
        from openai import AzureOpenAI
        from config import get_settings
        s = get_settings()
        endpoint = s.azure_openai_endpoint
        key = s.azure_openai_api_key
        version = s.azure_openai_api_version

        if not endpoint or "dummy" in endpoint or not key or "dummy" in key:
            logger.info("EmbeddingService: no Azure OpenAI credentials — using mock embeddings")
            return None

        _embedding_client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=key,
            api_version=version,
            max_retries=2,
            timeout=30.0,
        )
        logger.info("EmbeddingService: Azure OpenAI client ready")
        return _embedding_client
    except Exception as exc:
        logger.warning("EmbeddingService: client init failed (%s) — using mock", exc)
        return None


def embed_text(text: str) -> List[float]:
    """
    Embed a single text string.
    Returns a float list of length EMBEDDING_DIM.
    """
    text = text.strip()
    if not text:
        return _mock_embedding("")

    client = _get_embedding_client()
    if client is None:
        return _mock_embedding(text)

    try:
        from config import get_settings
        deployment = get_settings().azure_openai_embedding_deployment
        resp = client.embeddings.create(input=[text], model=deployment)
        return resp.data[0].embedding
    except Exception as exc:
        logger.warning("embed_text failed (%s) — falling back to mock", exc)
        return _mock_embedding(text)


def embed_batch(texts: List[str], batch_size: int = 16) -> List[List[float]]:
    """
    Embed a list of texts efficiently in batches.
    Returns embeddings in the same order as input.
    """
    results: List[List[float]] = []
    client = _get_embedding_client()

    if client is None:
        for t in texts:
            results.append(_mock_embedding(t.strip()))
        return results

    try:
        from config import get_settings
        deployment = get_settings().azure_openai_embedding_deployment
        for i in range(0, len(texts), batch_size):
            batch = [t.strip() for t in texts[i: i + batch_size]]
            resp = client.embeddings.create(input=batch, model=deployment)
            # API returns results sorted by index
            sorted_data = sorted(resp.data, key=lambda d: d.index)
            results.extend(d.embedding for d in sorted_data)
    except Exception as exc:
        logger.warning("embed_batch failed (%s) — falling back to mock for remaining", exc)
        # Fill the rest with mock
        while len(results) < len(texts):
            results.append(_mock_embedding(texts[len(results)].strip()))

    return results
