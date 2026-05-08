"""
MeetingChunk — stores transcript chunks with pgvector embeddings.

Each meeting transcript is split into semantic chunks.
Each chunk gets a 768-dim embedding stored as a pgvector column.
This enables cosine similarity search across all meetings.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.app.database import Base

try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    # Fallback: store as JSON array if pgvector not installed
    Vector = None
    PGVECTOR_AVAILABLE = False


class MeetingChunk(Base):
    __tablename__ = "meeting_chunks"
    __table_args__ = {"extend_existing": True}

    id           = Column(Integer, primary_key=True, index=True)
    meeting_id   = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    user_id      = Column(Integer, ForeignKey("users.id"), index=True)

    # The actual text chunk
    chunk_text   = Column(Text, nullable=False)
    chunk_index  = Column(Integer, default=0)       # position in transcript
    chunk_type   = Column(String(50), default="transcript")  # transcript|summary|decision

    # Metadata for hybrid search + filtering
    speaker      = Column(String(255), nullable=True)
    meeting_title = Column(String(255), nullable=True)

    # Vector embedding — 768 dims (Gemini text-embedding-004)
    # Falls back to JSON if pgvector not available
    if PGVECTOR_AVAILABLE and Vector:
        embedding = Column(Vector(768), nullable=True)
    else:
        embedding = Column(JSON, nullable=True)   # store as list fallback

    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    meeting      = relationship("Meeting", backref="chunks")


class QueryHistory(Base):
    """Stores user queries and RAG responses for history + analytics."""
    __tablename__ = "query_history"
    __table_args__ = {"extend_existing": True}

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"), index=True)
    query           = Column(Text, nullable=False)
    answer          = Column(Text, nullable=True)
    confidence      = Column(Float, default=0.0)
    sources         = Column(JSON, nullable=True)   # list of {meeting_id, title, chunk}
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
