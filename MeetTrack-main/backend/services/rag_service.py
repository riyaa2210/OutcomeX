"""
RAG Service — Retrieval-Augmented Generation for Meeting Intelligence
=====================================================================

Pipeline:
  1. Embed user query (768-dim vector)
  2. Similarity search in meeting_chunks table
     - pgvector cosine similarity (primary)
     - keyword fallback (if pgvector unavailable)
  3. Metadata filtering (user_id, meeting_id, date range)
  4. Hybrid reranking (vector score + keyword overlap)
  5. Inject top-k chunks as context into Gemini prompt
  6. Return answer + source citations + confidence score

Supports queries like:
  "What tasks were assigned to Alice?"
  "Which meetings discussed JWT auth?"
  "What decisions were made last week?"
"""

import os
import re
import logging
import math
from typing import Optional
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import text, or_, and_

from backend.models.meeting_chunk import MeetingChunk, QueryHistory
from backend.services.embedding_service import embed_text

logger = logging.getLogger(__name__)

TOP_K          = 5     # number of chunks to retrieve
MIN_SIMILARITY = 0.3   # minimum cosine similarity threshold
MAX_CONTEXT    = 3000  # max chars of context to inject into prompt


# ── Index a meeting ───────────────────────────────────────────────────────────

def index_meeting(
    db: Session,
    meeting_id: int,
    user_id: int,
    transcript: str,
    title: str = "",
    summary: str = "",
    decisions: list = None,
) -> int:
    """
    Chunk a transcript, generate embeddings, and store in meeting_chunks.
    Called after every meeting is processed.
    Returns number of chunks stored.
    """
    from backend.services.embedding_service import chunk_transcript

    # Delete existing chunks for this meeting (re-index)
    db.query(MeetingChunk).filter(MeetingChunk.meeting_id == meeting_id).delete()
    db.commit()

    chunks = chunk_transcript(transcript, title)

    # Also add summary and decisions as searchable chunks
    if summary:
        chunks.append({
            "text":        summary,
            "chunk_index": len(chunks),
            "speaker":     None,
            "chunk_type":  "summary",
        })
    for i, decision in enumerate(decisions or []):
        chunks.append({
            "text":        decision,
            "chunk_index": len(chunks) + i,
            "speaker":     None,
            "chunk_type":  "decision",
        })

    stored = 0
    for chunk in chunks:
        if not chunk["text"].strip():
            continue

        embedding = embed_text(chunk["text"])

        db_chunk = MeetingChunk(
            meeting_id    = meeting_id,
            user_id       = user_id,
            chunk_text    = chunk["text"],
            chunk_index   = chunk["chunk_index"],
            chunk_type    = chunk.get("chunk_type", "transcript"),
            speaker       = chunk.get("speaker"),
            meeting_title = title,
            embedding     = embedding,
        )
        db.add(db_chunk)
        stored += 1

    db.commit()
    logger.info(f"[RAG] Indexed meeting={meeting_id} → {stored} chunks")
    return stored


# ── Similarity search ─────────────────────────────────────────────────────────

def similarity_search(
    db: Session,
    query: str,
    user_id: int,
    meeting_id: Optional[int] = None,
    chunk_type: Optional[str] = None,
    top_k: int = TOP_K,
) -> list[dict]:
    """
    Find the most semantically similar chunks to the query.
    Uses pgvector cosine similarity if available, keyword fallback otherwise.
    """
    query_embedding = embed_text(query)
    if not query_embedding:
        return _keyword_search(db, query, user_id, meeting_id, top_k)

    # Try pgvector cosine similarity
    try:
        results = _vector_search(db, query_embedding, user_id, meeting_id, chunk_type, top_k)
        if results:
            return results
    except Exception as exc:
        logger.warning(f"[RAG] pgvector search failed: {exc} — falling back to keyword")

    return _keyword_search(db, query, user_id, meeting_id, top_k)


def _vector_search(
    db, query_embedding, user_id, meeting_id, chunk_type, top_k
) -> list[dict]:
    """pgvector cosine similarity search."""
    # Build filter conditions
    filters = [MeetingChunk.user_id == user_id]
    if meeting_id:
        filters.append(MeetingChunk.meeting_id == meeting_id)
    if chunk_type:
        filters.append(MeetingChunk.chunk_type == chunk_type)

    # pgvector cosine distance operator: <=>
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    raw = db.execute(
        text("""
            SELECT
                mc.id,
                mc.meeting_id,
                mc.chunk_text,
                mc.chunk_type,
                mc.speaker,
                mc.meeting_title,
                mc.chunk_index,
                1 - (mc.embedding <=> :embedding ::vector) AS similarity
            FROM meeting_chunks mc
            WHERE mc.user_id = :user_id
              AND (:meeting_id IS NULL OR mc.meeting_id = :meeting_id)
              AND (:chunk_type IS NULL OR mc.chunk_type = :chunk_type)
              AND mc.embedding IS NOT NULL
            ORDER BY mc.embedding <=> :embedding ::vector
            LIMIT :top_k
        """),
        {
            "embedding":  embedding_str,
            "user_id":    user_id,
            "meeting_id": meeting_id,
            "chunk_type": chunk_type,
            "top_k":      top_k,
        }
    ).fetchall()

    results = []
    for row in raw:
        sim = float(row.similarity) if row.similarity else 0.0
        if sim >= MIN_SIMILARITY:
            results.append({
                "chunk_id":     row.id,
                "meeting_id":   row.meeting_id,
                "meeting_title": row.meeting_title or f"Meeting #{row.meeting_id}",
                "chunk_text":   row.chunk_text,
                "chunk_type":   row.chunk_type,
                "speaker":      row.speaker,
                "similarity":   round(sim, 4),
            })

    return results


def _keyword_search(
    db, query: str, user_id: int, meeting_id: Optional[int], top_k: int
) -> list[dict]:
    """Keyword-based fallback search using PostgreSQL ILIKE."""
    keywords = [w for w in re.findall(r'\w+', query.lower()) if len(w) > 3]
    if not keywords:
        return []

    q = db.query(MeetingChunk).filter(MeetingChunk.user_id == user_id)
    if meeting_id:
        q = q.filter(MeetingChunk.meeting_id == meeting_id)

    # Filter chunks containing any keyword
    keyword_filters = [
        MeetingChunk.chunk_text.ilike(f"%{kw}%") for kw in keywords[:5]
    ]
    q = q.filter(or_(*keyword_filters))
    chunks = q.limit(top_k * 2).all()

    # Score by keyword overlap
    scored = []
    for chunk in chunks:
        text_lower = chunk.chunk_text.lower()
        score = sum(1 for kw in keywords if kw in text_lower) / len(keywords)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "chunk_id":      c.id,
            "meeting_id":    c.meeting_id,
            "meeting_title": c.meeting_title or f"Meeting #{c.meeting_id}",
            "chunk_text":    c.chunk_text,
            "chunk_type":    c.chunk_type,
            "speaker":       c.speaker,
            "similarity":    round(score, 4),
        }
        for score, c in scored[:top_k]
    ]


# ── Hybrid reranking ──────────────────────────────────────────────────────────

def rerank_results(results: list[dict], query: str) -> list[dict]:
    """
    Rerank retrieved chunks by combining:
      - Vector similarity score (60%)
      - Keyword overlap score (40%)
    """
    keywords = set(re.findall(r'\w+', query.lower()))

    for r in results:
        text_words = set(re.findall(r'\w+', r["chunk_text"].lower()))
        overlap    = len(keywords & text_words) / max(len(keywords), 1)
        r["rerank_score"] = 0.6 * r["similarity"] + 0.4 * overlap

    results.sort(key=lambda x: x["rerank_score"], reverse=True)
    return results


# ── RAG answer generation ─────────────────────────────────────────────────────

def ask_meetings(
    db: Session,
    query: str,
    user_id: int,
    meeting_id: Optional[int] = None,
) -> dict:
    """
    Full RAG pipeline:
      1. Retrieve relevant chunks
      2. Rerank
      3. Build context
      4. Generate answer with Gemini
      5. Store query history
      6. Return answer + citations + confidence
    """
    logger.info(f"[RAG] Query: '{query[:80]}' user={user_id}")

    # Step 1 — Retrieve
    chunks = similarity_search(db, query, user_id, meeting_id, top_k=TOP_K)

    if not chunks:
        answer = "I couldn't find any relevant information in your meeting history for that query."
        _save_query(db, user_id, query, answer, 0.0, [])
        return {
            "answer":     answer,
            "sources":    [],
            "confidence": 0.0,
            "chunks_used": 0,
        }

    # Step 2 — Rerank
    chunks = rerank_results(chunks, query)[:TOP_K]

    # Step 3 — Build context
    context_parts = []
    sources       = []
    total_chars   = 0

    for chunk in chunks:
        if total_chars >= MAX_CONTEXT:
            break
        speaker_prefix = f"{chunk['speaker']}: " if chunk.get("speaker") else ""
        entry = (
            f"[{chunk['meeting_title']} — {chunk['chunk_type']}]\n"
            f"{speaker_prefix}{chunk['chunk_text']}"
        )
        context_parts.append(entry)
        total_chars += len(entry)
        sources.append({
            "meeting_id":    chunk["meeting_id"],
            "meeting_title": chunk["meeting_title"],
            "chunk_type":    chunk["chunk_type"],
            "speaker":       chunk.get("speaker"),
            "similarity":    chunk["similarity"],
            "excerpt":       chunk["chunk_text"][:150] + "...",
        })

    context = "\n\n---\n\n".join(context_parts)

    # Step 4 — Generate answer
    answer, confidence = _generate_answer(query, context)

    # Step 5 — Save history
    _save_query(db, user_id, query, answer, confidence, sources)

    return {
        "answer":      answer,
        "sources":     sources,
        "confidence":  confidence,
        "chunks_used": len(chunks),
    }


def _generate_answer(query: str, context: str) -> tuple[str, float]:
    """Call Gemini with retrieved context to generate a grounded answer."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return _fallback_answer(query, context), 0.5

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        prompt = f"""You are a professional meeting intelligence assistant for OutcomeX.
Answer the user's question using ONLY the meeting context provided below.
If the answer is not in the context, say "I don't have enough information from your meetings to answer that."
Be concise, specific, and cite which meeting the information comes from.

MEETING CONTEXT:
{context}

USER QUESTION: {query}

INSTRUCTIONS:
- Answer directly and concisely
- Cite the meeting title when referencing specific information
- If multiple meetings are relevant, mention all of them
- Do NOT make up information not present in the context
- Format action items as bullet points if listing them

ANSWER:"""

        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
        )
        answer = response.text.strip()

        # Estimate confidence based on context relevance
        confidence = min(0.95, 0.5 + len(context) / 10000)
        return answer, round(confidence, 2)

    except Exception as exc:
        logger.error(f"[RAG] Gemini answer generation failed: {exc}")
        return _fallback_answer(query, context), 0.4


def _fallback_answer(query: str, context: str) -> str:
    """Simple keyword-based answer when Gemini is unavailable."""
    lines = [l.strip() for l in context.split('\n') if l.strip()]
    keywords = set(re.findall(r'\w+', query.lower()))
    relevant = [l for l in lines if any(kw in l.lower() for kw in keywords)]
    if relevant:
        return "Based on your meetings:\n\n" + "\n".join(f"• {l}" for l in relevant[:5])
    return "I found some related meeting content but couldn't extract a specific answer."


def _save_query(db, user_id, query, answer, confidence, sources):
    """Persist query + response to query_history table."""
    try:
        record = QueryHistory(
            user_id    = user_id,
            query      = query,
            answer     = answer,
            confidence = confidence,
            sources    = sources,
        )
        db.add(record)
        db.commit()
    except Exception as exc:
        logger.error(f"[RAG] Failed to save query history: {exc}")
