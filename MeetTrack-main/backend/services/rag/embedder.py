"""
Embedder
========
Converts text into dense vector embeddings using sentence-transformers.

Model: all-MiniLM-L6-v2
  - 384-dimensional embeddings
  - Fast, lightweight, runs locally — no API key needed
  - Good quality for semantic search

The model is downloaded once and cached in ~/.cache/huggingface/
"""

import logging
import numpy as np
from typing import Union

logger = logging.getLogger(__name__)

# Module-level model cache — loaded once, reused across requests
_model = None
MODEL_NAME = "all-MiniLM-L6-v2"


def _get_model():
    """Lazy-load the embedding model (downloads on first call)."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "Install sentence-transformers: pip install sentence-transformers"
            )
        logger.info(f"[Embedder] Loading model: {MODEL_NAME}")
        _model = SentenceTransformer(MODEL_NAME)
        logger.info(f"[Embedder] Model loaded. Embedding dim: {_model.get_sentence_embedding_dimension()}")
    return _model


def embed_texts(texts: list[str], batch_size: int = 32) -> np.ndarray:
    """
    Embed a list of strings into a 2D numpy array.

    Args:
        texts:      List of strings to embed.
        batch_size: Number of texts to process at once (tune for memory).

    Returns:
        np.ndarray of shape (len(texts), 384), dtype float32.
    """
    if not texts:
        return np.array([], dtype=np.float32)

    model = _get_model()
    logger.info(f"[Embedder] Embedding {len(texts)} texts in batches of {batch_size}")

    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,   # L2-normalise → cosine similarity = dot product
    )

    logger.info(f"[Embedder] Done. Shape: {embeddings.shape}")
    return embeddings.astype(np.float32)


def embed_query(query: str) -> np.ndarray:
    """
    Embed a single query string.

    Returns:
        np.ndarray of shape (1, 384), dtype float32.
    """
    return embed_texts([query])


def get_embedding_dim() -> int:
    """Return the embedding dimension of the loaded model."""
    return _get_model().get_sentence_embedding_dimension()
