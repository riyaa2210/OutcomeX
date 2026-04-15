"""
RAG Pipeline
============
Orchestrates the full Retrieval-Augmented Generation flow:

  1. Embed user query
  2. Retrieve top-k similar chunks from FAISS
  3. Build structured prompt (system + context + question)
  4. Call Gemini LLM
  5. Return answer + source chunks

Also handles meeting intelligence (transcript → key points / actions / decisions).
"""

import json
import logging
import os
from typing import Optional

from dotenv import load_dotenv

from backend.services.rag.embedder    import embed_query
from backend.services.rag.vector_store import search

load_dotenv()
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
RAG_MODEL      = "gemini-1.5-flash"   # fast + cheap
TOP_K          = 5                     # chunks to retrieve


# ── Gemini client ─────────────────────────────────────────────────────────────

def _call_gemini(prompt: str, temperature: float = 0.2) -> str:
    """
    Call Gemini with a prompt and return the text response.
    temperature=0.2 keeps answers factual and consistent.
    """
    if not GEMINI_API_KEY:
        raise EnvironmentError("GEMINI_API_KEY not set in .env")

    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=RAG_MODEL,
            contents=prompt,
        )
        return response.text.strip()
    except Exception as exc:
        logger.error(f"[RAG] Gemini call failed: {exc}")
        raise


# ── Prompt templates ──────────────────────────────────────────────────────────

def _build_rag_prompt(question: str, chunks: list[dict]) -> str:
    """
    Build the RAG prompt.

    Structure:
      SYSTEM instruction → CONTEXT (retrieved chunks) → USER question

    The system instruction explicitly tells the model to answer ONLY from
    the provided context, preventing hallucination.
    """
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source = f"{chunk.get('file_name', 'unknown')} (page {chunk.get('page', '?')})"
        context_parts.append(f"[Source {i}: {source}]\n{chunk['text']}")

    context_block = "\n\n---\n\n".join(context_parts)

    return f"""SYSTEM:
You are an intelligent document assistant for MeetTrack.
Answer the user's question using ONLY the context provided below.
If the answer is not in the context, respond with: "I don't have enough information in the provided documents to answer that."
Be concise, accurate, and cite the source number when referencing specific information.

CONTEXT:
{context_block}

USER QUESTION:
{question}

ANSWER:"""


def _build_meeting_prompt(transcript: str) -> str:
    """
    Prompt for meeting intelligence extraction.
    Returns structured JSON with key_points, decisions, action_items.
    """
    return f"""You are a professional meeting analyst.
Analyse the meeting transcript below and extract structured information.

RULES:
1. Extract ONLY information explicitly stated in the transcript.
2. Do NOT invent names, tasks, or decisions.
3. Return ONLY valid JSON — no markdown, no code fences.
4. action_items must include: task, assignee (or "Unassigned"), deadline (or null).

OUTPUT SCHEMA:
{{
  "key_points": ["string", ...],
  "decisions":  ["string", ...],
  "action_items": [
    {{"task": "string", "assignee": "string", "deadline": "string or null"}}
  ],
  "summary": "2-3 sentence summary of the meeting"
}}

TRANSCRIPT:
{transcript[:4000]}

Return ONLY the JSON:"""


# ── Public API ────────────────────────────────────────────────────────────────

def query_rag(question: str, top_k: int = TOP_K) -> dict:
    """
    Full RAG pipeline: query → retrieve → generate.

    Args:
        question: User's natural language question.
        top_k:    Number of chunks to retrieve.

    Returns:
        {
          "answer":  str,
          "sources": [{"file_name", "page", "score", "text_preview"}, ...],
          "chunks_used": int,
        }
    """
    logger.info(f"[RAG] Query: {question[:80]}…")

    # Step 1 — embed query
    q_embedding = embed_query(question)

    # Step 2 — retrieve chunks
    chunks = search(q_embedding, top_k=top_k)

    if not chunks:
        return {
            "answer":      "No documents have been uploaded yet. Please upload a document first.",
            "sources":     [],
            "chunks_used": 0,
        }

    # Step 3 — build prompt
    prompt = _build_rag_prompt(question, chunks)

    # Step 4 — call LLM
    answer = _call_gemini(prompt, temperature=0.2)

    # Step 5 — format sources
    sources = [
        {
            "file_name":    c.get("file_name", ""),
            "page":         c.get("page", 1),
            "score":        round(c.get("score", 0), 4),
            "text_preview": c.get("text", "")[:200] + "…",
        }
        for c in chunks
    ]

    logger.info(f"[RAG] Answer generated using {len(chunks)} chunks")
    return {
        "answer":      answer,
        "sources":     sources,
        "chunks_used": len(chunks),
    }


def analyse_meeting(transcript: str) -> dict:
    """
    Extract structured intelligence from a meeting transcript.

    Returns:
        {
          "summary":      str,
          "key_points":   [str, ...],
          "decisions":    [str, ...],
          "action_items": [{"task", "assignee", "deadline"}, ...],
        }
    """
    logger.info(f"[RAG] Analysing meeting transcript ({len(transcript)} chars)")

    prompt = _build_meeting_prompt(transcript)

    try:
        raw = _call_gemini(prompt, temperature=0.1)

        # Strip markdown fences if present
        import re
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw).strip()

        result = json.loads(raw)

        # Validate and fill defaults
        return {
            "summary":      result.get("summary", ""),
            "key_points":   result.get("key_points", []),
            "decisions":    result.get("decisions", []),
            "action_items": result.get("action_items", []),
        }

    except json.JSONDecodeError as exc:
        logger.error(f"[RAG] Meeting analysis JSON parse failed: {exc}")
        # Fallback — return raw text as summary
        return {
            "summary":      raw if "raw" in dir() else "Analysis failed.",
            "key_points":   [],
            "decisions":    [],
            "action_items": [],
        }
    except Exception as exc:
        logger.error(f"[RAG] Meeting analysis failed: {exc}")
        raise
