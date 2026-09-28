# MeetTrack — Interview Drilling Document

> Use this to practice answering questions out loud. Every answer is written the way you'd actually say it in an interview — confident, specific, using the real names/numbers from the project. Cover this document 3 times before any interview.

---

## HOW TO USE THIS

1. Read the question out loud
2. Close your eyes and say the answer without reading
3. Open and compare — fill the gaps
4. Repeat any section you stumble on

---

## SECTION 1 — "Tell me about this project"

### Q: Walk me through your project in 2 minutes.

"I built MeetTrack — an AI-powered meeting outcome tracker. The idea is simple: you upload a meeting recording or paste a transcript, and the system automatically extracts a structured summary, key decisions, and action items with assignees and deadlines — all powered by Gemini 2.0 Flash.

The stack is FastAPI on the backend with PostgreSQL and Redis, a React 19 frontend with Vite, and Celery for background task processing. For transcription I built a dual-mode system — either runs Whisper locally on CPU using faster-whisper, or sends audio to an external Colab-hosted Whisper server.

Beyond the core pipeline, I built a full RAG system where users can ask natural language questions like 'What tasks were assigned to Alice last week?' and get grounded answers with citations — using pgvector for semantic search and Gemini embeddings. I also added real-time live meeting support via WebSockets, analytics dashboards, integrations with Google Calendar, Zoom, Teams, Trello, Notion and Jira, and an enterprise security layer with RBAC, JWT refresh token rotation, rate limiting, and anomaly detection."

---

### Q: What problem does this solve?

"After every meeting, someone manually reads through notes or the recording to figure out what was decided and who needs to do what. That process is slow, inconsistent, and things get missed. MeetTrack automates all of that — you get a structured intelligence report in under a minute, automatically pushed to your task management tools."

---

### Q: What was your role?

"I built the entire project — backend architecture, frontend, database design, the AI pipeline, the RAG system, security layer, deployment config. Full-stack end to end."

---

## SECTION 2 — Backend & Architecture

### Q: Why FastAPI over Django or Flask?

"Three reasons. First, FastAPI generates OpenAPI docs automatically — I get Swagger UI at `/docs` for free, which helped a lot during development. Second, it's async-native, which matters for the WebSocket live meeting feature and the long-running AI calls. Third, Pydantic validation is built in — I define a schema once and get request validation, serialization, and docs from the same class. Flask would need a lot of extra setup for all of that."

---

### Q: How is your app structured?

"It's organized by feature domain. The `backend/app/` directory has the FastAPI app entry point, auth, database connection, CRUD operations, Pydantic schemas, and settings. Then I have separate directories for `models/` (SQLAlchemy ORM), `routes/` (one file per feature — upload, meetings, RAG, analytics, etc.), `services/` (business logic — AI extraction, transcription, embeddings, LLM routing), `worker/` (Celery tasks), and `security/` (RBAC, rate limiting, anomaly detection, audit logging). The frontend is a standard Vite/React structure with pages, components, context, services, and hooks."

---

### Q: How does your app start up? What happens when uvicorn starts?

"The very first thing — before any imports — is loading the `.env` file from the project root using `python-dotenv`. This is critical because other modules read env vars at import time.

Then SQLAlchemy creates the database engine. It auto-detects environment: if 'localhost' is in the DATABASE_URL it creates a plain connection, otherwise it adds `sslmode=require` for Render/cloud.

Next, every SQLAlchemy model class is imported — this is required because `create_all` only knows about tables whose Python classes have been imported. Then `Base.metadata.create_all(bind=engine, checkfirst=True)` creates any missing tables.

After that, the FastAPI app is created, two middleware layers are applied — CORS first, then security headers — and all 15 routers are mounted. The app is ready."

---

### Q: How do you handle database connections?

"I use SQLAlchemy's `sessionmaker` with `autocommit=False` and `autoflush=False`. Every endpoint gets a DB session via a `get_db()` generator dependency — it yields the session and closes it in a `finally` block regardless of success or failure. This ensures connections are always returned to the pool.

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

For production I use the PostgreSQL connection with SSL required. For local dev it's plain TCP."

---

### Q: What middleware do you use and why?

"Two layers. First is `CORSMiddleware` from FastAPI/Starlette — it reads allowed origins from the `CORS_ORIGINS` environment variable (comma-separated), so I can change allowed domains without code changes. If the value is `*` it allows everything and disables credentials (CORS spec requires this).

Second is a custom `SecurityHeadersMiddleware` I wrote. Every response gets OWASP-recommended headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection`, `Referrer-Policy`, `Permissions-Policy`, `Content-Security-Policy`. It also removes the `Server` header to prevent fingerprinting, and hooks into the anomaly detector to record every 404 per IP."

---

### Q: How do you handle errors?

"For expected errors I use `HTTPException` with appropriate status codes — 400 for bad input, 401 for auth failures, 403 for permission denied, 404 for not found. For unexpected errors in the processing pipeline, I catch the exception, log the full traceback with Python's `logging` module, and return HTTP 500 with a descriptive message. Pydantic handles request validation errors automatically and returns 422 with field-level detail."

---

## SECTION 3 — Authentication Deep Dive

### Q: How does your login work, step by step?

"The frontend sends a `POST /login` request with `application/x-www-form-urlencoded` content — fields `username` (the email) and `password`. That format is required by FastAPI's `OAuth2PasswordRequestForm`.

The backend looks up the user by email, then calls `verify_password(plain, stored_hash)` which does a bcrypt comparison via passlib. If credentials are wrong, it raises HTTP 401.

If correct, it creates two tokens. The access token is a JWT HS256 with a `user_id`, `exp` set to 15 minutes from now, `type: 'access'`, and a UUID `jti` (JWT ID). The refresh token has `exp` set to 7 days and `type: 'refresh'` — and critically, it's persisted to the `refresh_tokens` table in the database with the user's IP address and user agent.

It also writes a `LOGIN_SUCCESS` event to the security audit log. Then it returns both tokens plus the full user profile — 20 fields including name, role, department, skills, timezone.

The frontend stores both tokens and the user object in `localStorage`, then schedules a silent refresh to fire at 14 minutes — one minute before the access token expires."

---

### Q: Why use two tokens? Why not just one long-lived token?

"Security. If a long-lived token is stolen, the attacker has access until it expires — potentially days or weeks. With short-lived access tokens (15 minutes), the exposure window for a stolen token is tiny.

The refresh token is stored in the database, so it can be revoked instantly on logout. If I detect suspicious activity I can revoke all refresh tokens for a user and effectively force a logout across all their devices.

I also do token rotation — every time a refresh token is used, the old one is revoked and a new one is issued. This gives replay protection: if an attacker somehow gets the refresh token and uses it, the legitimate user's next refresh will fail (old token already revoked), alerting them."

---

### Q: How do you verify a JWT on every request?

"`OAuth2PasswordBearer` extracts the `Authorization: Bearer {token}` header. My `verify_token` function decodes it with `jwt.decode(token, SECRET_KEY, algorithms=['HS256'])` — this validates the signature and checks expiry. Then it checks the `type` claim is `'access'`. Then it checks Redis for token revocation: `redis.exists(f'revoked_token:{jti}')`. If any check fails, it returns `None` and the endpoint raises HTTP 401.

On success, it extracts `user_id` from the payload and queries the database for the actual user object, which is then passed into the route handler."

---

### Q: How does token refresh work?

"The frontend fires a `POST /auth/refresh` with the refresh token in the request body at 14 minutes. The backend verifies the JWT signature and type claim, checks the `jti` isn't in the Redis revocation list, then queries the `refresh_tokens` table to confirm the specific token row exists and hasn't been revoked.

Then it does rotation: marks the old `RefreshToken` row as `revoked=True`, generates a brand new access token and refresh token, saves the new refresh token to the database, and returns both. The frontend updates both `localStorage` entries and schedules the next refresh."

---

### Q: What happens if the user closes the browser tab?

"The timer is cleared when the component unmounts via `clearTimeout(refreshTimerRef.current)`. On the next visit, `AuthContext` reads `localStorage` on mount — if the access token is still valid (opened within 15 minutes) it restores the session and schedules the refresh timer again. If the access token is expired, the first API call returns 401 and the user is redirected to login. The refresh token in localStorage could be used to silently renew — that's a TODO improvement."

---

### Q: How do you store passwords?

"bcrypt via passlib's `CryptContext`. bcrypt is a slow adaptive hash — it has a cost factor that makes brute-forcing expensive. Passlib handles the work factor automatically. I never store plaintext passwords. The only exception is a legacy code path I kept for migration — if the stored hash doesn't start with `$2b$` or `$2a$` (the bcrypt prefix) it falls back to plain comparison, which lets me migrate old accounts."

---

### Q: How do you implement logout?

"Two things happen. The frontend fires a non-blocking `POST /auth/logout` with the access token as Bearer auth and the refresh token in the body, then immediately clears localStorage and resets React state regardless of the server's response — so the UI logout is instant even on slow networks.

The backend marks the specific `RefreshToken` database row as revoked, then writes the access token's `jti` to Redis with a 24-hour expiry (`SETEX revoked_token:{jti} 86400 1`). So even though the access token is still technically valid for up to 15 more minutes, every request with it will hit the Redis check and fail."

---

## SECTION 4 — The AI Pipeline

### Q: Walk me through what happens when a user uploads a meeting recording.

"It's a six-step pipeline.

First, the audio file is saved to disk. Then `POST /process` starts the pipeline.

Step one is transcription. If `USE_LOCAL_WHISPER=true`, I load a faster-whisper model — singleton pattern so it only loads once — and run transcription with VAD filtering to skip silence. If using the Colab API, I send the file as multipart form data to the ngrok URL with a 5-minute timeout.

Step two creates a `Meeting` database row with the transcript, user ID, and a title derived from the filename.

Step three is AI extraction. I run NLP pre-processing first — spaCy detects speaker turns by regex, tags action-bearing and decision-bearing sentences. Then I build a structured prompt with those hints plus the transcript and send it through my LLM router. Gemini 1.5 Flash gets the call first. It returns JSON with `summary`, `decisions`, and `action_items`. Each action item has a task, assignee, deadline, and confidence score.

Step four validates and saves action items to the database — anything below 0.4 confidence is discarded.

Steps five and six are background tasks — they run after the response is already sent. RAG indexing chunks the transcript, generates 768-dim embeddings, and stores them in pgvector. The evaluation service scores the AI output quality. And an automation webhook fires to n8n or Activepieces.

The full pipeline from upload to structured output takes about 30–60 seconds depending on audio length."

---

### Q: How does your LLM router work?

"It's a multi-provider orchestration layer with circuit breakers, caching, and quality scoring.

The routing table defines which providers to try in order per task type. For extraction it's Gemini → OpenAI → Local. For reasoning it's OpenAI first because GPT-4o is better at logic chains. For classification it's Local first because it's zero cost and fast enough.

Before calling any provider, I check a two-tier cache: in-memory LRU with 512 slots, backed by Redis with a 1-hour TTL. Cache key is SHA-256 of provider + model + task type + first 500 chars of prompt.

For each provider in the chain, I check availability (does the API key exist?), check the circuit breaker (hasn't had 3 consecutive failures in the last 60 seconds), then call it in a thread with a timeout — 30 seconds for extraction tasks.

On success I score the response quality, detect hallucinations against the source text, write metrics to the `llm_call_logs` table (tokens, cost, latency, quality, which provider), and cache the result. On failure I record it, increment the circuit breaker counter, and try the next provider. Local is always the final guaranteed fallback."

---

### Q: What is the LLM prompt for extraction? How do you prevent hallucinations?

"The prompt has several layers of grounding. It tells the model it's a professional meeting analyst. It provides the speaker names detected by spaCy as hints. It provides pre-identified action-bearing and decision-bearing sentences as hints. Then it gives the transcript.

The strict rules section is the key part: extract ONLY information explicitly stated in the transcript, do NOT invent names, tasks, dates, or decisions, return ONLY valid JSON with no markdown.

The model also returns a `confidence_score` per action item between 0 and 1. I discard anything below 0.4. For items I do keep, I run `detect_hallucinations()` which checks if the people and dates mentioned in the output actually appear in the source transcript.

Additionally, every response goes through output validation — deadlines must match `YYYY-MM-DD` regex or they're nulled out, assignees default to 'Unassigned' if empty, confidence is clamped to 0.0–1.0."

---

### Q: How do you handle long transcripts that exceed the context window?

"I use a map-reduce approach. The `needs_chunking()` function checks if the transcript is over 4800 characters. If so, the chunker splits it into overlapping chunks — roughly 2000 characters each with 200-character overlap to preserve context at boundaries.

Each chunk is summarized individually by Gemini. Then all the chunk summaries are fed into a final reduce prompt that merges them into a single coherent structured output. The `_meta` field in the response includes `chunked: true` and a chunk count so I can see when this path was taken."

---

### Q: What's the difference between faster-whisper and the Colab approach?

"Faster-whisper runs locally in the Python process. It uses the CTranslate2 runtime with int8 quantization, which is optimized for CPU inference — no GPU needed. The `base` model (default) downloads ~150MB once and gets cached. It's fully offline, consistent, and fast for reasonable-length recordings.

The Colab approach sends audio over HTTP to a separately-running Whisper notebook. That's useful if you need a larger model (the `large-v3` model would need too much RAM locally), but it has an operational cost — someone has to keep the Colab notebook running and update the ngrok URL every session. I made it configurable via env var so you can switch between the two without code changes."

---

### Q: What transcription formats do you support?

"MP3, WAV, M4A, OGG, FLAC, WebM, and MP4 — anything faster-whisper or Colab Whisper can process. I also validate the MIME type by reading magic bytes from the file header to prevent extension spoofing."

---

## SECTION 5 — RAG System

### Q: How does your RAG system work?

"RAG stands for Retrieval-Augmented Generation. Instead of asking the LLM to answer from its training data, I retrieve relevant context from the user's own meeting history and inject it into the prompt.

After every meeting is processed, I index it — I chunk the transcript into ~250-word segments with 50-word overlap, generate a 768-dimensional embedding for each chunk using Gemini's `text-embedding-004` model, and store them in PostgreSQL using the pgvector extension with a `Vector(768)` column.

When a user asks a question, I embed the query with the same model, then run a cosine similarity search against all their meeting chunks using pgvector's `<=>` operator. The top 5 results above a 0.3 similarity threshold are retrieved. I then do hybrid reranking: 60% vector similarity score plus 40% keyword overlap, which improves precision over pure vector search.

The top chunks are formatted as context and injected into a Gemini prompt that says 'answer using ONLY this context, cite the meeting title.' The answer, confidence score, and source citations are returned to the user."

---

### Q: What is pgvector and why did you use it?

"pgvector is a PostgreSQL extension that adds vector similarity search. It lets me store arrays of floats as a native `Vector(768)` column and run nearest-neighbor queries using operators like `<=>` for cosine distance and `<->` for L2 distance.

I chose it because I'm already using PostgreSQL — adding pgvector means I don't need a separate vector database like Pinecone or Weaviate. It simplifies the architecture, the vectors live in the same database as everything else, and I get transactional consistency for free — when a meeting is deleted, its chunks are cascade-deleted too."

---

### Q: What happens if pgvector isn't installed?

"I have a keyword fallback. The `similarity_search` function first tries the pgvector SQL query. If it fails, it falls back to `_keyword_search` which uses PostgreSQL's `ILIKE` operator to find chunks containing the query keywords. Results are scored by what fraction of query keywords appear in the chunk. It's less accurate than semantic search but it never breaks."

---

### Q: How do you chunk the transcripts?

"First I try speaker-turn detection using a regex that matches patterns like `Alice: ...` or `[Alice] ...`. If the transcript has labeled speakers I split on speaker changes, which is the most natural chunking boundary.

If no speakers are detected I fall back to paragraph splitting on double newlines.

After the initial split: chunks under 30 words are merged with adjacent chunks, chunks over 400 words are split further — targeting 250 words with 50-word overlap to preserve context at boundaries.

On top of the transcript chunks I add the AI-generated summary and each decision as separate chunks with `chunk_type='summary'` and `chunk_type='decision'`. That way if someone asks 'what decisions were made?' the highly-relevant decision chunks surface first."

---

### Q: What is the embedding model you use?

"Google's `text-embedding-004` via the Gemini API. It produces 768-dimensional dense vectors. Input is capped at 8000 characters. If the Gemini API is unavailable, I have a fallback that generates a deterministic character-hash-based vector — not semantically meaningful, but at least the system doesn't crash."

---

## SECTION 6 — Database & Data Modeling

### Q: Walk me through your database schema.

"The core tables are `users`, `meetings`, `action_items`, and `results`. Users have a full profile — not just email and password but also job title, department, manager, skills stored as a JSON string, work mode, timezone — because the project is designed for enterprise use.

Meetings belong to a user and store the title, audio file path, full transcript, and created timestamp. Action items belong to a meeting with cascade delete — if the meeting is deleted, its action items go too. They have assignee, deadline as a YYYY-MM-DD string, status, and description.

For the AI features: `meeting_chunks` stores the RAG vector embeddings with a pgvector `Vector(768)` column. `query_history` tracks every RAG question and its answer. `llm_call_logs` tracks every AI API call with cost, latency, token counts, and quality scores.

For security: `refresh_tokens` stores JWT refresh tokens for rotation and revocation, with IP and user agent. `security_audit_logs` tracks every significant event. `eval_results` stores AI output quality scores across 6 dimensions.

For integrations: `oauth_tokens` stores encrypted OAuth tokens (AES-256) for each external service per user. `external_meetings` stores meetings imported from Zoom, Google Meet, etc."

---

### Q: Why did you choose PostgreSQL over MongoDB or SQLite?

"Three reasons. First, my data is highly relational — users have meetings, meetings have action items, meetings have chunks, chunks have embeddings. SQL joins handle that naturally. Second, I needed pgvector for the RAG semantic search — that's a PostgreSQL-specific extension. Third, PostgreSQL gives me ACID transactions, which matters for things like token rotation where I need to atomically revoke the old token and create the new one.

SQLite would work for local dev but doesn't support pgvector and has limitations at scale. MongoDB would make the relational queries harder and I'd still need a separate vector database."

---

### Q: How do you handle database migrations?

"Currently I use SQLAlchemy's `create_all(checkfirst=True)` — it creates tables that don't exist but never alters existing ones. That's fine for this stage of the project. For production I'd add Alembic, which generates versioned migration scripts so you can evolve the schema safely without dropping tables."

---

### Q: How do you prevent SQL injection?

"SQLAlchemy's ORM layer uses parameterized queries for all ORM operations — I never concatenate user input into SQL strings. For the one raw SQL query I use in the pgvector similarity search, I use SQLAlchemy's `text()` with named parameters passed as a dict. This is always safe from SQL injection."

---

## SECTION 7 — Redis & Celery

### Q: What do you use Redis for?

"Four things. First, Celery broker — Redis is the message broker that queues background tasks and stores results. Second, LLM response cache — I cache AI responses in Redis with a 1-hour TTL so identical prompts don't hit the Gemini API again. Third, rate limiting — I use Redis INCR and EXPIRE for sliding-window counters per IP address. Fourth, security — token revocation lists (revoked JTI → 24-hour TTL key), failed login tracking, and webhook replay prevention."

---

### Q: How does Celery work in your project?

"Celery is a distributed task queue. I have five queues: transcription, ai_extraction, email_delivery, analytics, and webhooks. Each queue has a recommended concurrency — transcription gets 2 workers because it's I/O-bound waiting on the Colab API, email gets 8 because it's fast, analytics gets 2 because it runs heavy DB queries.

Every task uses idempotency keys — SHA-256 of the task type plus meeting ID plus file path. Before processing, I check the `task_logs` table for an existing non-failed entry with the same key. If one exists, I skip. This means retrying a failed task never double-processes a meeting.

The retry policy uses exponential backoff — for transcription it's 60, 120, 240 seconds. After 3 failures the task is marked dead-letter. Celery Beat runs two periodic tasks: retry dead-letter webhooks every 10 minutes, and clean up old task log entries daily.

On Windows I have to use `--pool=solo` because Windows doesn't support the default prefork (fork-based) pool."

---

### Q: What's the task chain after a meeting is processed?

"The transcription task runs first. On success it chains to the AI extraction task. On success there, it fans out to three parallel tasks: webhook delivery (posts meeting data to n8n/Activepieces), RAG indexing (generates embeddings and stores chunks), and email delivery (sends task assignment notifications to assignees)."

---

## SECTION 8 — Security

### Q: What security measures did you implement?

"Several layers. JWT authentication with short-lived access tokens (15 min) and rotatable refresh tokens stored in the database. bcrypt password hashing. Redis-based token revocation for immediate logout. RBAC with four roles (viewer, employee, manager, admin). Redis rate limiting — auth endpoints allow 10 req/min per IP, upload 5/min, general API 100/min. Failed login lockout after 5 attempts per IP for 15 minutes. OWASP security headers on every response. File security — MIME magic byte validation, extension whitelist, malware pattern scanning. Audit logging of every significant event. Anomaly detection with IP risk scoring."

---

### Q: How does your RBAC work?

"Four roles in ascending order: viewer (0), employee (1), manager (2), admin (3). I have a `require_role(minimum)` FastAPI dependency — it calls `get_current_user` and then checks if the user's role level is at least the minimum. I also have `assert_owns_or_admin(resource_user_id, current_user)` which raises 403 unless the current user owns the resource or is an admin — used for profile updates and meeting access."

---

### Q: How does your rate limiter work?

"Redis sliding window. Every request hits `ratelimit:{context}:{ip}` where context is 'auth', 'upload', 'api', etc. I run `INCR key` then `EXPIRE key 60` — the expire only sets if the key doesn't already have one (first request sets the window). If the count exceeds the threshold, I raise HTTP 429. If Redis is unreachable, I fail open — allow all requests — because availability matters more than rate limiting when the store is down."

---

### Q: How do you validate file uploads?

"Five-layer validation. First, sanitize the filename — strip path separators, control characters, limit to 200 chars. Second, check extension against a whitelist (`.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.webm`, `.mp4`). Third, read the first 16 bytes of the file and detect the MIME type from magic bytes — ID3 tag means audio/mpeg, RIFF header means audio/wav. This catches extension spoofing. Fourth, read the full file and check it's under 100MB. Fifth, scan the first 1024 bytes for PHP and script injection patterns. Optionally calls ClamAV via Unix socket if configured."

---

### Q: What is anomaly detection in your system?

"It's a Redis-backed IP risk scoring system. Each IP has a score from 0 to 100. Failed logins add 10 points (capped at 40). High request rates add 15–30 points. Each 404 response adds 5 (capped at 20). Requests outside business hours (6am–11pm UTC) add 5. When an IP's score hits 51, an `ANOMALY_DETECTED` event is written to the security audit log. The `SecurityHeadersMiddleware` hooks into this by calling `record_404(ip)` on every 404 response."

---

## SECTION 9 — Frontend

### Q: How is the frontend structured?

"Vite + React 19 with React Router 7. Pages in `src/pages/`, shared components in `src/components/`, global state in `src/context/` (AuthContext for auth, ThemeProvider for dark/light mode), API calls in `src/services/api.js`. Tailwind CSS for styling, Recharts for analytics charts, Framer Motion for animations, Radix UI for accessible primitives like dialogs and switches."

---

### Q: How does auth state work in the frontend?

"`AuthContext` is a React context that wraps the entire app. It holds `user`, `token`, `loading`, and `error`. On mount it reads from `localStorage` — if there's a stored user and access token, it restores the session immediately and schedules the 14-minute refresh timer. `useAuth()` is a custom hook that any component can call to get the current user and auth functions. The `ProtectedRoute` component in `App.jsx` just checks `!user` from `useAuth()` and redirects to `/auth` if not logged in."

---

### Q: How do you make API calls? How is the token attached?

"`api.js` is a thin wrapper around `fetch`. Every call goes through `getHeaders()` which reads `localStorage.getItem('access_token')` and adds `Authorization: Bearer {token}`. Every call uses `AbortController` with a 30-second timeout. Error handling extracts the `detail` field from FastAPI error responses. For file uploads, it uses `FormData` and doesn't set `Content-Type` — letting the browser set it with the multipart boundary."

---

### Q: How does the live meeting feature work?

"It uses WebSockets. The `LiveMeetingPage` creates a WebSocket connection to `ws://backend/live/ws/{meeting_id}?token={access_token}`. The token is in the query parameter because WebSockets don't support custom headers. The server authenticates by parsing the token from the query string. Once connected, the frontend can stream transcript chunks as someone speaks, and the server sends back AI suggestions, detected action items, and participant join events as JSON messages over the same socket."

---

### Q: How do you protect routes on the frontend?

"With a `ProtectedRoute` component that wraps all authenticated pages:
```jsx
function ProtectedRoute({ children }) {
    const { user } = useAuth();
    return user ? children : <Navigate to='/auth' replace />;
}
```
If `user` is null (not in localStorage or cleared on logout), React Router redirects to `/auth`. The `replace` prop prevents the auth page from appearing in browser history so pressing Back doesn't loop."

---

## SECTION 10 — Deployment

### Q: How would you deploy this?

"The project has a `render.yaml` Blueprint file that deploys everything to Render with one click. It defines five services: the FastAPI backend as a web service (2 Uvicorn workers, health check at `/health`), a Celery worker with 5 queue routing, Celery Beat for scheduled tasks, Flower for task monitoring UI, and the React frontend as a static site.

Render handles PostgreSQL and Redis as managed services — I just connect the internal URLs. The frontend build runs `npm run build` and Vite outputs to `dist/`. The backend build runs `pip install -r requirements.txt && python -m spacy download en_core_web_sm`.

Environment variables are set in the Render dashboard. The ones not set automatically (like API keys) are marked `sync: false` in the YAML. `SECRET_KEY` uses Render's `generateValue: true` so it's auto-generated on first deploy."

---

### Q: What's the difference between the local and production setup?

"Locally: PostgreSQL runs as a Windows service on port 5433, Redis runs from the extracted binary in the `Redis/` folder, Whisper runs locally via faster-whisper, and Celery uses `--pool=solo`. The backend starts with `--reload` for hot-reload.

In production on Render: PostgreSQL and Redis are managed services with internal URLs. Whisper uses the Colab API (Render doesn't have enough RAM for even the base model in production). Celery uses the default pool (Linux supports forking). Uvicorn runs with `--workers 2`. SSL is required for the database connection."

---

### Q: How do you handle CORS in production?

"The `CORS_ORIGINS` environment variable is set to the frontend's Render URL — e.g. `https://meettrack-frontend.onrender.com`. The backend reads this on startup and passes it to `CORSMiddleware`. `allow_credentials` is set to `True` only when the origins list is not `*` — this is a CORS spec requirement. In development I set it to `http://localhost:5173,http://127.0.0.1:5173`."

---

## SECTION 11 — Integrations

### Q: What external integrations does the project support?

"Google (Calendar, Meet, Tasks), Zoom, Microsoft Teams, Trello, Notion, and Jira — all via OAuth 2.0. The `oauth_tokens` table stores the encrypted access and refresh tokens (AES-256 encryption) per user per provider. The integration system can sync meetings from Google Calendar or Zoom into the app, and push action items out to Trello cards, Notion databases, or Jira tickets.

There's also a webhook receiver for Zoom and Google Meet that auto-processes recordings when a meeting ends. And outbound webhook support to n8n and Activepieces for custom automation workflows."

---

### Q: How do you store OAuth tokens securely?

"AES-256 encryption before storing in the database. The encryption key is derived from the `SECRET_KEY` environment variable. So even if the database is compromised, the tokens are useless without the key. The `oauth_tokens` table has columns `access_token` and `refresh_token` as TEXT — both store the encrypted ciphertext, not the raw tokens."

---

## SECTION 12 — Challenges & Design Decisions

### Q: What was the hardest part to build?

"The LLM router. Getting reliable structured JSON output from a language model is non-trivial. The model sometimes returns JSON wrapped in markdown code fences, sometimes returns partial JSON, sometimes ignores the schema entirely. I built multiple parsing layers — strip markdown fences first, then `json.loads`, then fallback to regex `{.*}` extraction, then a keyword-based local fallback. I also had to handle the case where Gemini is rate-limited or slow and route to OpenAI, with circuit breakers to avoid hammering a failing provider."

---

### Q: What would you improve if you had more time?

"Three things. First, add Alembic for proper database migrations — right now schema changes require manual SQL. Second, improve the transcription pipeline to handle speaker diarization properly (identifying who said what), which would make the AI extraction more accurate. Third, add proper end-to-end tests with a test database — right now there are no automated tests, which makes refactoring risky."

---

### Q: Why did you use Celery instead of FastAPI's BackgroundTasks for everything?

"FastAPI's `BackgroundTasks` runs in the same process as the web server, so if the server restarts during a long operation — like a 5-minute transcription job — the task just dies. Celery persists tasks in Redis, so they survive restarts. Celery also supports proper retry with exponential backoff, dead-letter queues, task deduplication via idempotency keys, and monitoring via Flower. For quick fire-and-forget tasks like logging analytics or sending a webhook I still use `BackgroundTasks` — Celery adds overhead that's not worth it for those."

---

### Q: How does your system handle a failing AI provider?

"The circuit breaker pattern. Each provider has an in-memory failure counter. After 3 consecutive failures, the circuit 'opens' for 60 seconds — any call to that provider is skipped without even trying. After 60 seconds it auto-resets and tries again. This prevents cascading failures where a slow Gemini API causes every request to hang for 30 seconds waiting for a timeout.

While Gemini is circuit-broken, all calls route to OpenAI. If OpenAI also fails, they fall through to the Local provider, which uses regex-based extraction and always returns a response — quality is lower but the system never fully breaks."

---

## SECTION 13 — Behavioral / Soft Skill Questions

### Q: How did you decide on the project scope?

"I started with the core loop: upload → transcribe → AI extract → display. Once that worked end-to-end, I added persistence and history. Then I added the RAG search because meeting data is only useful if you can retrieve it. Security came next because without proper auth and validation the app couldn't be used by real users. Integrations and analytics were the final layer. I tried to build each layer completely before moving to the next."

---

### Q: What did you learn from this project?

"A few things. LLM output is non-deterministic — you can't trust it to always return valid JSON, so defensive parsing is essential. Vector search is powerful but needs hybrid approaches — pure semantic search misses obvious keyword matches. Windows has real differences from Linux for Python backend development, especially with Celery process pools. And deployment configuration is as important as the code — the `render.yaml` and `.env.production.example` files save a lot of setup pain."

---

### Q: How would you scale this to 10,000 users?

"Several changes. First, add a read replica for PostgreSQL and route analytics queries there. Second, increase Celery worker concurrency and potentially add more worker instances behind the Redis broker. Third, add a proper CDN for audio file storage (currently stored on disk — should be S3). Fourth, add connection pooling like PgBouncer for the database. Fifth, for pgvector performance at scale, add an HNSW index on the embedding column — right now it does exact search which is O(n) for each query."

---

## SECTION 14 — Quick-Fire Tech Questions

**Q: What does `async def` do in FastAPI?**
"It makes the route handler a coroutine, allowing Uvicorn to handle other requests while it's awaiting I/O — like a database query or an external API call. Routes that don't do I/O can use regular `def`."

**Q: What is Pydantic used for?**
"Request and response validation. I define a schema class like `UserCreate` with typed fields — Pydantic automatically validates the request body and returns a 422 with field-level errors if it doesn't match. It also serializes ORM objects to JSON for responses."

**Q: What is the difference between `commit()` and `flush()` in SQLAlchemy?**
"`flush()` sends the SQL to the database within the current transaction but doesn't commit it — changes are visible within the session but not to other sessions yet. `commit()` makes the transaction permanent and visible to everyone."

**Q: What is a JWT?**
"JSON Web Token — a Base64-encoded JSON header and payload with a cryptographic signature. The server signs it with a secret key. Anyone can decode the payload (it's not encrypted), but only the server can verify it hasn't been tampered with. It's stateless — the server doesn't need to look it up in a database to verify it."

**Q: What is the difference between SQL `JOIN` and subquery?**
"A JOIN combines rows from two tables based on a condition — typically faster and more readable for most cases. A subquery returns a result set used by an outer query — useful when you need aggregated values or when the logic is clearer expressed that way."

**Q: What is bcrypt and why is it better than MD5 for passwords?**
"bcrypt is a slow adaptive hash function. 'Slow' is intentional — it has a cost factor that makes brute-forcing computationally expensive. MD5 is extremely fast, so an attacker with a GPU can try billions of MD5 combinations per second. bcrypt limits that to thousands. It also automatically handles salting, preventing rainbow table attacks."

**Q: What is a circuit breaker pattern?**
"A design pattern that prevents cascading failures. After a service fails N times, the circuit 'opens' — subsequent calls fail immediately without trying, giving the service time to recover. After a timeout, the circuit 'half-opens' and tries one request. If it succeeds, it closes. This prevents your app from hanging on every request waiting for a timeout on a dead service."

**Q: What is cosine similarity?**
"A measure of similarity between two vectors based on the angle between them — not their magnitude. Two vectors pointing in the same direction have cosine similarity of 1.0 (identical), perpendicular vectors have 0.0, opposite vectors have -1.0. For text embeddings, similar meanings produce vectors pointing in similar directions, so cosine similarity measures semantic relatedness."

**Q: What is WebSocket and how is it different from HTTP?**
"WebSocket is a persistent bidirectional communication channel over TCP. Unlike HTTP where the client sends a request and the server sends one response, a WebSocket connection stays open and both sides can send messages at any time. Used in the live meeting feature for streaming transcript chunks from client to server and AI suggestions from server to client in real time."

**Q: What is CORS and why does it matter?**
"Cross-Origin Resource Sharing. Browsers block JavaScript from making requests to a different domain than the page's origin — this is the Same-Origin Policy. CORS is the mechanism that lets the server say 'I allow requests from these specific origins.' My backend sets `Access-Control-Allow-Origin` to my frontend URL. Without it, the browser would block all API calls from the frontend."

**Q: What is Celery Beat?**
"A scheduler that runs periodic/scheduled Celery tasks. Like cron but integrated with Celery. I use it to retry failed webhook deliveries every 10 minutes and clean up old task log entries daily."

**Q: What does `checkfirst=True` do in SQLAlchemy's `create_all`?**
"It checks if each table already exists before trying to create it. Without it, calling `create_all` on an existing database would throw an error. With it, existing tables are skipped — only new tables are created."

---

## SECTION 15 — Numbers to Remember

Memorize these — interviewers love specific numbers:

| Thing | Number |
|-------|--------|
| Access token lifetime | 15 minutes |
| Refresh token lifetime | 7 days |
| Silent refresh timer | 14 minutes |
| Embedding dimensions | 768 |
| RAG top-k chunks | 5 |
| Minimum similarity threshold | 0.3 |
| Max context chars for RAG | 3000 |
| Chunking trigger | 4800 chars |
| Target chunk size | 250 words |
| Chunk overlap | 50 words |
| Circuit breaker threshold | 3 failures |
| Circuit breaker reset | 60 seconds |
| LLM in-memory cache slots | 512 |
| LLM Redis cache TTL | 1 hour |
| Celery soft timeout | 300 seconds (5 min) |
| Celery hard timeout | 360 seconds (6 min) |
| Celery result expiry | 24 hours |
| Max audio file size | 100 MB |
| OWASP headers set | 6 |
| Rate limit: auth | 10 req/min |
| Rate limit: upload | 5 req/min |
| Rate limit: API | 100 req/min |
| Failed login lockout | 5 attempts / 15 min |
| Anomaly risk threshold | 51 |
| Token revocation Redis TTL | 24 hours |
| Webhook replay window | 300 seconds (5 min) |
| DB tables total | 18 |
| Frontend pages | 15 |
| Celery queues | 5 |
| API routes (approx) | 40+ |

---

## SECTION 16 — One-Line Answers (for rapid-fire rounds)

- **What is MeetTrack?** — AI meeting outcome tracker: upload audio → get summary, decisions, action items via Gemini
- **Stack?** — FastAPI + PostgreSQL + Redis + React 19 + Celery + Gemini 2.0
- **Auth?** — JWT with bcrypt passwords, 15-min access tokens, 7-day refresh tokens with DB revocation
- **Why JWT?** — Stateless, scales horizontally, no session store needed per request
- **Why Redis?** — Celery broker + LLM cache + rate limiting + token revocation + anomaly detection
- **Why pgvector?** — Native PostgreSQL vector search, no separate vector DB, cascade deletes, transactions
- **RAG in one line?** — Embed query → cosine search 768-dim chunks → hybrid rerank → Gemini grounded answer
- **Whisper options?** — Local faster-whisper (CPU int8) or remote Colab API, configurable via env var
- **LLM fallback chain?** — Gemini → OpenAI → Local regex (always succeeds)
- **Circuit breaker?** — 3 failures → 60s open → auto-reset
- **Celery on Windows?** — Must use `--pool=solo` (Windows has no fork support)
- **Token rotation?** — Use refresh token → get new pair → old refresh token revoked in DB
- **RBAC levels?** — viewer < employee < manager < admin
- **File security?** — Filename sanitize → extension whitelist → magic byte MIME check → size limit → malware scan
- **Background tasks after processing?** — n8n webhook + RAG indexing + AI quality evaluation (all async)
