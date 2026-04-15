"""
Vector Store (FAISS)
====================
Manages the FAISS index and chunk metadata store.

Architecture:
  - FAISS IndexFlatIP  → inner product search (works with L2-normalised vectors
                          as cosine similarity)
  - JSON metadata file → maps FAISS integer IDs → chunk dicts
  - Both files persist to disk in rag_data/

Files on disk:
  rag_data/faiss.index   — FAISS binary index
  rag_data/metadata.json — chunk metadata keyed by integer ID
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Where to persist the index and metadata
RAG_DATA_DIR = Path(__file__).resolve().parents[3] / "rag_data"
INDEX_PATH   = RAG_DATA_DIR / "faiss.index"
META_PATH    = RAG_DATA_DIR / "metadata.json"


def _ensure_dir():
    RAG_DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── In-memory state ───────────────────────────────────────────────────────────

_index    = None   # faiss.Index
_metadata: dict[int, dict] = {}   # {faiss_id: chunk_dict}


def _get_faiss():
    try:
        import faiss
        return faiss
    except ImportError:
        raise ImportError("Install FAISS: pip install faiss-cpu")


# ── Persistence ───────────────────────────────────────────────────────────────

def save_index():
    """Persist FAISS index and metadata to disk."""
    global _index, _metadata
    if _index is None:
        return
    _ensure_dir()
    faiss = _get_faiss()
    faiss.write_index(_index, str(INDEX_PATH))
    with open(META_PATH, "w", encoding="utf-8") as f:
        # JSON keys must be strings
        json.dump({str(k): v for k, v in _metadata.items()}, f, indent=2)
    logger.info(f"[VectorStore] Saved {_index.ntotal} vectors to {RAG_DATA_DIR}")


def load_index() -> bool:
    """
    Load FAISS index and metadata from disk.
    Returns True if loaded successfully, False if no saved index exists.
    """
    global _index, _metadata
    if not INDEX_PATH.exists() or not META_PATH.exists():
        return False

    faiss = _get_faiss()
    _index = faiss.read_index(str(INDEX_PATH))
    with open(META_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    _metadata = {int(k): v for k, v in raw.items()}
    logger.info(f"[VectorStore] Loaded {_index.ntotal} vectors from disk")
    return True


def _init_index(dim: int):
    """Create a new FAISS index."""
    global _index
    faiss = _get_faiss()
    # IndexFlatIP = exact inner product search (cosine with normalised vectors)
    _index = faiss.IndexFlatIP(dim)
    logger.info(f"[VectorStore] Created new FAISS index (dim={dim})")


# ── Public API ────────────────────────────────────────────────────────────────

def add_chunks(chunks: list[dict], embeddings: np.ndarray):
    """
    Add chunks and their embeddings to the vector store.

    Args:
        chunks:     List of chunk dicts (from chunker.py)
        embeddings: np.ndarray shape (len(chunks), dim)
    """
    global _index, _metadata

    if len(chunks) != len(embeddings):
        raise ValueError("chunks and embeddings must have the same length")

    dim = embeddings.shape[1]

    # Initialise or load existing index
    if _index is None:
        if not load_index():
            _init_index(dim)

    # FAISS IDs are sequential integers starting from current total
    start_id = _index.ntotal

    # Add vectors to FAISS
    _index.add(embeddings)

    # Store metadata
    for i, chunk in enumerate(chunks):
        faiss_id = start_id + i
        _metadata[faiss_id] = chunk

    logger.info(f"[VectorStore] Added {len(chunks)} chunks. Total: {_index.ntotal}")
    save_index()


def search(query_embedding: np.ndarray, top_k: int = 5) -> list[dict]:
    """
    Find the top_k most similar chunks to a query embedding.

    Args:
        query_embedding: np.ndarray shape (1, dim)
        top_k:           Number of results to return

    Returns:
        List of chunk dicts sorted by similarity (highest first),
        each with an added "score" field.
    """
    global _index, _metadata

    if _index is None:
        if not load_index():
            logger.warning("[VectorStore] No index loaded — returning empty results")
            return []

    if _index.ntotal == 0:
        return []

    k = min(top_k, _index.ntotal)
    scores, ids = _index.search(query_embedding, k)

    results = []
    for score, faiss_id in zip(scores[0], ids[0]):
        if faiss_id == -1:   # FAISS returns -1 for padding
            continue
        chunk = dict(_metadata.get(int(faiss_id), {}))
        chunk["score"] = float(score)
        results.append(chunk)

    return results


def get_stats() -> dict:
    """Return basic stats about the current index."""
    global _index, _metadata
    if _index is None:
        load_index()
    return {
        "total_vectors": _index.ntotal if _index else 0,
        "total_chunks":  len(_metadata),
        "index_path":    str(INDEX_PATH),
        "files_indexed": list({v["file_name"] for v in _metadata.values()}),
    }


def delete_by_file(file_name: str) -> int:
    """
    Remove all chunks belonging to a specific file.
    Note: FAISS IndexFlatIP doesn't support deletion — we rebuild the index.

    Returns number of chunks removed.
    """
    global _index, _metadata

    if _index is None:
        load_index()

    # Find IDs to keep
    keep_ids = [fid for fid, chunk in _metadata.items()
                if chunk.get("file_name") != file_name]
    removed  = len(_metadata) - len(keep_ids)

    if removed == 0:
        return 0

    # Rebuild index with kept vectors
    faiss = _get_faiss()
    dim   = _index.d

    # Reconstruct kept embeddings
    kept_embeddings = np.array([
        _index.reconstruct(fid) for fid in keep_ids
    ], dtype=np.float32)

    new_index = faiss.IndexFlatIP(dim)
    if len(kept_embeddings) > 0:
        new_index.add(kept_embeddings)

    new_metadata = {new_id: _metadata[old_id]
                    for new_id, old_id in enumerate(keep_ids)}

    _index    = new_index
    _metadata = new_metadata
    save_index()

    logger.info(f"[VectorStore] Removed {removed} chunks for file: {file_name}")
    return removed
