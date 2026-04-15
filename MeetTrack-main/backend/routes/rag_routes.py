"""
RAG API Routes
==============

POST /rag/upload          — ingest a document (PDF/DOCX/TXT)
POST /rag/query           — ask a question against uploaded documents
POST /rag/meeting-summary — extract intelligence from a transcript
GET  /rag/stats           — index stats (files, chunk count)
DELETE /rag/document      — remove a document from the index
"""

import logging
import os
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.auth import get_current_user
from backend.app.database import SessionLocal
from backend.services.rag.chunker import chunk_pages
from backend.services.rag.document_processor import extract_text
from backend.services.rag.embedder import embed_texts
from backend.services.rag.rag_pipeline import analyse_meeting, query_rag
from backend.services.rag.vector_store import add_chunks, delete_by_file, get_stats
from backend.services.n8n_service import trigger_n8n_workflow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rag", tags=["RAG"])

RAG_UPLOAD_DIR = Path("rag_uploads")
RAG_UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# POST /rag/upload
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    """
    Ingest a document into the RAG vector store.

    Steps:
      1. Save file to disk
      2. Extract text (PDF/DOCX/TXT)
      3. Split into overlapping chunks
      4. Embed chunks with sentence-transformers
      5. Store in FAISS index

    Returns chunk count and processing time.
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: PDF, DOCX, TXT"
        )

    # Save uploaded file
    save_path = RAG_UPLOAD_DIR / file.filename
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    t0 = time.time()

    try:
        # Extract text
        logger.info(f"[RAG Upload] Extracting: {file.filename}")
        pages = extract_text(str(save_path))

        if not pages:
            raise HTTPException(status_code=422, detail="No text could be extracted from the file.")

        # Chunk
        chunks = chunk_pages(pages, file_name=file.filename)

        if not chunks:
            raise HTTPException(status_code=422, detail="Document produced no chunks after processing.")

        # Embed
        texts = [c["text"] for c in chunks]
        embeddings = embed_texts(texts)

        # Store
        add_chunks(chunks, embeddings)

        elapsed = round(time.time() - t0, 2)
        logger.info(f"[RAG Upload] Done: {file.filename} → {len(chunks)} chunks in {elapsed}s")

        return {
            "status":       "success",
            "file_name":    file.filename,
            "pages":        len(pages),
            "chunks":       len(chunks),
            "elapsed_sec":  elapsed,
            "message":      f"Document indexed successfully. {len(chunks)} chunks ready for querying.",
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[RAG Upload] Failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(exc)}")


# ─────────────────────────────────────────────────────────────────────────────
# POST /rag/query
# ─────────────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    top_k: int = 5   # number of chunks to retrieve


@router.post("/query")
async def query_documents(
    request: QueryRequest,
    current_user=Depends(get_current_user),
):
    """
    Ask a question against all indexed documents.

    Returns:
      - answer:      LLM-generated answer grounded in retrieved chunks
      - sources:     Which document chunks were used
      - chunks_used: How many chunks contributed to the answer
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    if request.top_k < 1 or request.top_k > 20:
        raise HTTPException(status_code=400, detail="top_k must be between 1 and 20.")

    t0 = time.time()

    try:
        result = query_rag(request.question, top_k=request.top_k)
        result["elapsed_sec"] = round(time.time() - t0, 2)
        return result

    except Exception as exc:
        logger.error(f"[RAG Query] Failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(exc)}")


# ─────────────────────────────────────────────────────────────────────────────
# POST /rag/meeting-summary
# ─────────────────────────────────────────────────────────────────────────────

class MeetingRequest(BaseModel):
    transcript: str
    send_to_n8n: bool = False   # optionally trigger n8n webhook


@router.post("/meeting-summary")
async def meeting_summary(
    request: MeetingRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Extract structured intelligence from a meeting transcript.

    Returns:
      - summary
      - key_points
      - decisions
      - action_items (with assignee + deadline)

    Optionally triggers n8n webhook for email/notification.
    """
    if not request.transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript cannot be empty.")

    if len(request.transcript) < 50:
        raise HTTPException(status_code=400, detail="Transcript too short to analyse.")

    t0 = time.time()

    try:
        result = analyse_meeting(request.transcript)
        result["elapsed_sec"] = round(time.time() - t0, 2)

        # Optionally fire n8n webhook
        if request.send_to_n8n:
            try:
                trigger_n8n_workflow(
                    db=db,
                    meeting_id=0,
                    transcript=request.transcript,
                    structured=result,
                    event_type="rag_meeting_summary",
                )
                result["n8n_triggered"] = True
            except Exception as n8n_exc:
                logger.warning(f"[RAG Meeting] n8n trigger failed: {n8n_exc}")
                result["n8n_triggered"] = False

        return result

    except Exception as exc:
        logger.error(f"[RAG Meeting] Failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Meeting analysis failed: {str(exc)}")


# ─────────────────────────────────────────────────────────────────────────────
# GET /rag/stats
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def rag_stats(current_user=Depends(get_current_user)):
    """Return current index statistics."""
    try:
        return get_stats()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /rag/document
# ─────────────────────────────────────────────────────────────────────────────

class DeleteRequest(BaseModel):
    file_name: str


@router.delete("/document")
async def delete_document(
    request: DeleteRequest,
    current_user=Depends(get_current_user),
):
    """Remove all chunks for a specific document from the index."""
    removed = delete_by_file(request.file_name)
    if removed == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No chunks found for file: {request.file_name}"
        )
    return {
        "status":   "success",
        "removed":  removed,
        "file_name": request.file_name,
    }
