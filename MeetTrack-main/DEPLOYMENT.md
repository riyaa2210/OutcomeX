# OutcomeX — Deployment Guide

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Local Development (Docker)](#local-development)
3. [Environment Variables](#environment-variables)
4. [Production Deployment (Render)](#production-deployment-render)
5. [CI/CD Pipeline](#cicd-pipeline)
6. [Health Checks](#health-checks)
7. [Zero-Downtime Deployment](#zero-downtime-deployment)
8. [Secrets Management](#secrets-management)
9. [Monitoring & Logging](#monitoring--logging)
10. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Internet                              │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │   nginx (port 80/443)   │  ← Frontend static files
              │   React SPA             │    + reverse proxy
              └────────────┬────────────┘
                           │ /api/*
              ┌────────────▼────────────┐
              │   FastAPI (port 8000)   │  ← REST + WebSocket API
              │   uvicorn (4 workers)   │
              └──┬──────────┬───────────┘
                 │          │
    ┌────────────▼──┐  ┌────▼──────────────┐
    │  PostgreSQL   │  │      Redis         │
    │  (pgvector)   │  │  broker + cache    │
    └───────────────┘  └────────┬───────────┘
                                │
              ┌─────────────────▼──────────────┐
              │         Celery Workers          │
              │  transcription | ai_extraction  │
              │  email | analytics | webhooks   │
              └─────────────────────────────────┘
```

---

## Local Development

### Prerequisites
- Docker Desktop 4.x+
- Docker Compose v2.x+

### Quick Start

```bash
# 1. Clone and enter the project
cd MeetTrack-main

# 2. Copy environment template
cp .env.example .env
# Edit .env — at minimum set GEMINI_API_KEY

# 3. Start all services
docker compose up --build

# 4. Access services
#   Frontend:  http://localhost:5173
#   Backend:   http://localhost:8000
#   API Docs:  http://localhost:8000/docs
#   Flower:    http://localhost:5555  (admin/admin)
#   pgAdmin:   connect to localhost:5432 (outcomex/outcomex)
```

### Useful Commands

```bash
# Start only backend + dependencies
docker compose up postgres redis backend

# View logs
docker compose logs -f backend
docker compose logs -f worker

# Run database migrations / table creation
docker compose exec backend python -c "
from backend.app.database import Base, engine
Base.metadata.create_all(bind=engine)
print('Tables created')
"

# Open a Python shell in the backend container
docker compose exec backend python

# Run tests inside container
docker compose exec backend pytest tests/ -v

# Rebuild a single service
docker compose up --build backend

# Stop everything and remove volumes (clean slate)
docker compose down -v
```

---

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `SECRET_KEY` | JWT signing key (min 32 chars) |
| `GEMINI_API_KEY` | Google Gemini API key |

### Optional but Recommended

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key (enables GPT-4o routing) | — |
| `CORS_ORIGINS` | Comma-separated allowed origins | `*` |
| `COLAB_API_URL` | Colab Whisper transcription URL | — |
| `LLM_CACHE_ENABLED` | Enable LLM response caching | `true` |
| `ENVIRONMENT` | `development` / `production` / `test` | `development` |

### Integration OAuth (all optional)

| Variable | Provider |
|----------|----------|
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google Calendar, Meet, Tasks |
| `ZOOM_CLIENT_ID` / `ZOOM_CLIENT_SECRET` | Zoom |
| `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` | Microsoft Teams |
| `NOTION_CLIENT_ID` / `NOTION_CLIENT_SECRET` | Notion |
| `JIRA_CLIENT_ID` / `JIRA_CLIENT_SECRET` | Jira |
| `TRELLO_API_KEY` / `TRELLO_API_SECRET` | Trello |

### Generating a Secure SECRET_KEY

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Production Deployment (Render)

### Services to Create on Render

1. **PostgreSQL** — Render managed database
   - Plan: Starter ($7/mo) or higher
   - After creation: run `CREATE EXTENSION IF NOT EXISTS vector;` in pgAdmin

2. **Redis** — Render managed Redis
   - Plan: Starter ($10/mo)

3. **Backend** — Web Service
   - Runtime: Python 3.11
   - Root Dir: `MeetTrack-main`
   - Build: `pip install -r requirements.txt && python -m spacy download en_core_web_sm`
   - Start: `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`

4. **Celery Worker** — Background Worker
   - Same build as backend
   - Start: `celery -A backend.worker.celery_app worker -Q transcription,ai_extraction,email_delivery,analytics,webhooks --loglevel=info --concurrency=4`

5. **Celery Beat** — Background Worker
   - Start: `celery -A backend.worker.celery_app beat --loglevel=info`

6. **Frontend** — Static Site
   - Root Dir: `MeetTrack-main/frontend`
   - Build: `npm install && npm run build`
   - Publish Dir: `dist`
   - Rewrite: `/* → /index.html`

### Environment Variables on Render

Set these in each service's Environment tab:
- Copy all variables from `.env.example`
- Use Render's "Generate Value" for `SECRET_KEY` and `FLOWER_PASSWORD`
- Use internal URLs for `DATABASE_URL` and `REDIS_URL` (faster, no egress cost)

---

## CI/CD Pipeline

### GitHub Actions Workflow

```
push to main/develop
        │
        ├── lint-backend    (ruff)
        ├── lint-frontend   (eslint)
        │
        ├── test-backend    (pytest + real postgres + redis)
        ├── build-frontend  (vite build)
        │
        ├── docker-build    (build + push to GHCR)  [push only]
        │
        ├── api-smoke-test  (httpx against Docker container)  [main only]
        │
        └── deploy          (trigger Render deploy)  [main only]
```

### Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `RENDER_API_KEY` | Render API key (from Account Settings) |
| `RENDER_BACKEND_SERVICE_ID` | Render service ID for backend |
| `RENDER_FRONTEND_SERVICE_ID` | Render service ID for frontend |

### Required GitHub Variables (non-secret)

| Variable | Description |
|----------|-------------|
| `VITE_API_URL` | Backend URL for frontend build |
| `VITE_API_BASE_URL` | Same as above |
| `BACKEND_URL` | Backend URL for health check after deploy |

### Setting Up

```bash
# Add secrets via GitHub CLI
gh secret set RENDER_API_KEY
gh secret set RENDER_BACKEND_SERVICE_ID
gh secret set RENDER_FRONTEND_SERVICE_ID

# Add variables
gh variable set VITE_API_URL --body "https://meeting-outcome-tracker-backend.onrender.com"
gh variable set BACKEND_URL  --body "https://meeting-outcome-tracker-backend.onrender.com"
```

---

## Health Checks

### Backend Health Endpoint

```
GET /health
```

Response:
```json
{
  "status": "healthy",
  "service": "outcomex-backend",
  "version": "1.0.0",
  "db": "ok",
  "latency_ms": 2.3
}
```

Status values:
- `healthy` — all systems operational
- `degraded` — DB unreachable but service running

### Frontend Health Endpoint

```
GET /health
```

Response: `{"status":"ok","service":"frontend"}`

---

## Zero-Downtime Deployment

### Docker Swarm / Compose

The `docker-compose.prod.yml` uses `order: start-first` in the update config:

```yaml
update_config:
  parallelism: 1
  delay: 10s
  failure_action: rollback
  order: start-first   # new container starts before old one stops
```

### Render

Render automatically performs rolling deployments — new instance starts and passes health checks before traffic is switched.

### Manual Zero-Downtime Steps

```bash
# 1. Build new image
docker build -t outcomex-backend:new .

# 2. Start new container (different port)
docker run -d --name backend-new -p 8001:8000 outcomex-backend:new

# 3. Wait for health check
curl http://localhost:8001/health

# 4. Switch nginx upstream (or load balancer)
# 5. Stop old container
docker stop backend-old
```

---

## Secrets Management

### Local Development
- Use `.env` file (never commit to git — it's in `.gitignore`)
- `.env.example` shows all required variables without values

### GitHub Actions
- Store secrets in GitHub repository Settings → Secrets and Variables
- Access via `${{ secrets.SECRET_NAME }}`
- Non-sensitive config via Variables (not Secrets)

### Production (Render)
- Set environment variables in Render dashboard
- Use "Generate Value" for auto-generated secrets
- Internal service URLs are automatically injected

### Docker Production
- Pass secrets via environment variables, never bake into images
- Use Docker secrets for Swarm deployments:

```bash
echo "my-secret-key" | docker secret create secret_key -
```

### What NEVER Goes in an Image
- API keys
- Database passwords
- OAuth client secrets
- JWT secret keys
- Any `.env` file

---

## Monitoring & Logging

### Structured Logging

The backend uses Python's standard `logging` module with structured output.
In production, set `LOG_LEVEL=warning` to reduce noise.

```bash
# View backend logs
docker compose logs -f backend

# Filter for errors only
docker compose logs backend 2>&1 | grep ERROR
```

### Celery Monitoring (Flower)

Access at `http://localhost:5555` (dev) or your Flower Render URL.

Credentials: `FLOWER_USER` / `FLOWER_PASSWORD` env vars.

### Database Monitoring

```sql
-- Active connections
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';

-- Slow queries
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Table sizes
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

### Key Metrics to Watch

| Metric | Warning Threshold | Critical Threshold |
|--------|-------------------|-------------------|
| API response time (p95) | > 2s | > 5s |
| DB connection pool | > 80% | > 95% |
| Redis memory | > 200MB | > 250MB |
| Celery queue depth | > 100 | > 500 |
| Failed tasks (1h) | > 10 | > 50 |
| Hallucination rate | > 0.2 | > 0.4 |

---

## Troubleshooting

### Backend won't start

```bash
# Check logs
docker compose logs backend

# Common issues:
# 1. DB not ready → wait for postgres healthcheck
# 2. Missing env var → check .env file
# 3. Import error → check requirements.txt
```

### Database connection refused

```bash
# Verify postgres is healthy
docker compose ps postgres

# Test connection manually
docker compose exec postgres psql -U outcomex -d outcomex -c "SELECT 1"
```

### Celery tasks not processing

```bash
# Check worker is running
docker compose ps worker

# Check Redis connection
docker compose exec redis redis-cli ping

# Inspect active tasks
docker compose exec worker celery -A backend.worker.celery_app inspect active
```

### pgvector extension missing

```bash
# Connect to DB and enable
docker compose exec postgres psql -U outcomex -d outcomex \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Frontend build fails

```bash
# Check Node version
node --version  # should be 20.x

# Clear cache and rebuild
cd frontend
rm -rf node_modules dist
npm ci
npm run build
```

### OAuth callback not working

1. Verify `BACKEND_URL` and `FRONTEND_URL` env vars match your deployment URLs
2. Add the callback URL to your OAuth app's allowed redirect URIs:
   - Google: `https://your-backend.onrender.com/integrations/oauth/google_calendar/callback`
   - Zoom: `https://your-backend.onrender.com/integrations/oauth/zoom/callback`
   - Teams: `https://your-backend.onrender.com/integrations/oauth/microsoft_teams/callback`
