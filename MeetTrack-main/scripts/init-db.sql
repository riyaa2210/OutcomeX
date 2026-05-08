-- OutcomeX PostgreSQL initialization script
-- Runs once when the container is first created

-- Enable pgvector extension (required for RAG embeddings)
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable pg_trgm for fuzzy text search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Enable uuid-ossp for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Log initialization
DO $$
BEGIN
    RAISE NOTICE 'OutcomeX database initialized with extensions: vector, pg_trgm, uuid-ossp';
END $$;
