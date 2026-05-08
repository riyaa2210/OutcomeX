-- Run this once in pgAdmin or psql to enable pgvector extension
-- and create the RAG tables

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Create meeting_chunks table with vector column
CREATE TABLE IF NOT EXISTS meeting_chunks (
    id              SERIAL PRIMARY KEY,
    meeting_id      INTEGER REFERENCES meetings(id) ON DELETE CASCADE,
    user_id         INTEGER REFERENCES users(id),
    chunk_text      TEXT NOT NULL,
    chunk_index     INTEGER DEFAULT 0,
    chunk_type      VARCHAR(50) DEFAULT 'transcript',
    speaker         VARCHAR(255),
    meeting_title   VARCHAR(255),
    embedding       vector(768),          -- Gemini text-embedding-004
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Create HNSW index for fast approximate nearest-neighbor search
CREATE INDEX IF NOT EXISTS meeting_chunks_embedding_idx
    ON meeting_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 4. Create index on user_id for fast filtering
CREATE INDEX IF NOT EXISTS meeting_chunks_user_idx ON meeting_chunks(user_id);
CREATE INDEX IF NOT EXISTS meeting_chunks_meeting_idx ON meeting_chunks(meeting_id);

-- 5. Create query_history table
CREATE TABLE IF NOT EXISTS query_history (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id),
    query       TEXT NOT NULL,
    answer      TEXT,
    confidence  FLOAT DEFAULT 0.0,
    sources     JSONB,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS query_history_user_idx ON query_history(user_id);

-- Done! pgvector RAG tables are ready.
