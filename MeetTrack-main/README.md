# MeetTrack — AI-Powered Meeting Outcome Tracker

Upload a meeting audio file or paste a transcript → get an AI-generated **summary**, **decisions**, and **action items** instantly. Built with FastAPI + React + Gemini 2.0.

---

## What It Does

| Feature | Description |
|---|---|
| **AI Extraction** | Gemini 2.0 Flash extracts structured summary, decisions, action items with assignees + deadlines |
| **Local Whisper** | Transcribe audio locally via `faster-whisper` (no cloud needed) |
| **RAG Search** | Ask natural language questions across all your meetings |
| **Live Meeting** | Real-time WebSocket transcription and AI suggestions |
| **Analytics** | Trends, heatmaps, productivity insights with charts |
| **Integrations** | Google Calendar, Zoom, Teams, Trello, Notion, Jira (OAuth) |
| **Security** | JWT refresh tokens, RBAC, audit logging, anomaly detection |

---

## Quick Start (Local)

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.10+ | `python --version` |
| Node.js | 20.x | `node --version` |
| PostgreSQL | 16 | Running on port 5433 (or update `.env`) |
| Redis | any | Windows binary included in `Redis/` |

### 1. Create & activate virtual environment

```powershell
cd MeetTrack-main
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure environment

```powershell
# .env is already configured for local dev
# Edit GEMINI_API_KEY if you want AI features to work
notepad .env
```

Minimum required variables:
- `DATABASE_URL` — already set to `postgresql://postgres:2210@localhost:5433/meeting_dbs`
- `GEMINI_API_KEY` — get free key at https://aistudio.google.com/app/apikey
- `SECRET_KEY` — already set for dev (change for production)

### 3. Start all services

Open **4 separate PowerShell terminals**:

**Terminal 1 — Redis:**
```powershell
.\scripts\start-redis.ps1
# Or manually:
.\Redis\redis-server.exe --port 6379
```

**Terminal 2 — Backend:**
```powershell
.\scripts\start-backend.ps1
# Or manually:
$env:PYTHONPATH = $PWD
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 3 — Celery Worker** (needed for background AI tasks):
```powershell
.\scripts\start-worker.ps1
# Or manually:
$env:PYTHONPATH = $PWD
.venv\Scripts\python.exe -m celery -A backend.worker.celery_app worker -Q transcription,ai_extraction,email_delivery,analytics,webhooks --loglevel=info --concurrency=2 --pool=solo
```

**Terminal 4 — Frontend:**
```powershell
.\scripts\start-frontend.ps1
# Or manually:
cd frontend
npm run dev
```

### 4. Open in browser

| URL | Service |
|---|---|
| http://localhost:5173 | Frontend (React app) |
| http://127.0.0.1:8000 | Backend API |
| http://127.0.0.1:8000/docs | Interactive API docs (Swagger) |

---

## Transcription Modes

### Local Whisper (recommended for local dev)

Already configured in `.env`:
```
USE_LOCAL_WHISPER=true
WHISPER_MODEL_SIZE=base   # tiny | base | small | medium
```

First run downloads the model (~150MB for `base`) automatically. Subsequent runs use the cached model. No GPU needed — CPU int8 mode.

**Model size guide:**

| Size | Speed | Quality | RAM |
|---|---|---|---|
| tiny | Very fast | Basic | 1 GB |
| base | Fast | Good | 1 GB |
| small | Medium | Better | 2 GB |
| medium | Slow | Best CPU | 5 GB |

### Colab Whisper (alternative)

Run the Colab notebook, copy the ngrok URL, then set in `.env`:
```
USE_LOCAL_WHISPER=false
COLAB_API_URL=https://xxxx.ngrok-free.app
```

---

## Database Setup

PostgreSQL 16 is already running on port 5433. The `meeting_dbs` database and pgvector extension are already set up.

To reset the database:
```powershell
$env:PGPASSWORD = "2210"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -p 5433 -h localhost -d meeting_dbs -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
# Restart backend — tables recreate automatically
```

---

## Deploying to Render

### Step 1 — Push to GitHub

```bash
git add .
git commit -m "ready to deploy"
git push origin main
```

### Step 2 — Create Render services

1. Go to https://render.com → New → Blueprint
2. Connect your GitHub repo
3. Render reads `render.yaml` and creates all services automatically

### Step 3 — Create managed services in Render dashboard

Before deploying, create these in Render:
- **PostgreSQL** (any plan) — enable pgvector: connect via psql and run `CREATE EXTENSION vector;`
- **Redis** (any plan)

### Step 4 — Set environment variables

In the Render dashboard, set these for the `meettrack-backend` service:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Internal URL from your Render PostgreSQL |
| `REDIS_URL` | Internal URL from your Render Redis |
| `GEMINI_API_KEY` | Your Gemini API key |
| `CORS_ORIGINS` | `https://meettrack-frontend.onrender.com` |
| `FRONTEND_URL` | `https://meettrack-frontend.onrender.com` |
| `BACKEND_URL` | `https://meettrack-backend.onrender.com` |
| `COLAB_API_URL` | Your Colab ngrok URL (or leave blank if using paste-transcript) |

Set `VITE_API_BASE_URL` for the `meettrack-frontend` service:
```
VITE_API_BASE_URL=https://meettrack-backend.onrender.com
```

See `.env.production.example` for the full list.

### Step 5 — Deploy

Click **Deploy** in Render. The frontend will be live at your Render static site URL.

> **Note on transcription in production:** Render has no GPU and limited RAM. For production use, either:
> - Keep `USE_LOCAL_WHISPER=false` and use a Colab Whisper server
> - Use `USE_AWS_TRANSCRIBE=true` with an S3 bucket
> - Use the paste-transcript input (no audio upload needed)

---

## Project Structure

```
MeetTrack-main/
├── backend/
│   ├── app/           # FastAPI app (main.py, auth, DB, settings, CRUD)
│   ├── models/        # SQLAlchemy ORM models
│   ├── routes/        # API routers (upload, process, meetings, RAG, analytics…)
│   ├── services/      # AI extraction, transcription, RAG, LLM router
│   ├── worker/        # Celery app + 5 task modules
│   └── security/      # RBAC, audit log, anomaly detection, rate limiter
├── frontend/
│   └── src/
│       ├── pages/     # 15 pages (Dashboard, History, Ask, Live, Analytics…)
│       ├── components/
│       ├── context/   # AuthContext, ThemeProvider
│       └── services/  # API client (api.js, authService.js)
├── Redis/             # Windows Redis binary (redis-server.exe, redis-cli.exe)
├── scripts/           # PowerShell startup scripts
├── .env               # Local dev environment (gitignored)
├── .env.production.example  # Production template
├── render.yaml        # Render Blueprint deployment config
└── requirements.txt   # Python dependencies
```

---

## Common Issues

**Backend won't start — DB connection error**
```powershell
# Check PostgreSQL service is running
Get-Service postgresql-x64-16
# Check connection manually
$env:PGPASSWORD="2210"; & "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -p 5433 -h localhost -c "\l"
```

**Redis not responding**
```powershell
.\Redis\redis-cli.exe -p 6379 ping   # should print PONG
# If not, start it:
.\scripts\start-redis.ps1
```

**Celery worker won't start on Windows**
Make sure you use `--pool=solo` — Windows doesn't support the default `prefork` pool:
```powershell
.venv\Scripts\python.exe -m celery -A backend.worker.celery_app worker --pool=solo --loglevel=info
```

**Whisper model downloading slowly**
The `base` model is ~150MB and downloads once to `~/.cache/huggingface/`. Switch to `tiny` for a much faster first run:
```
WHISPER_MODEL_SIZE=tiny
```

**Frontend can't reach backend (CORS error)**
Check `CORS_ORIGINS` in `.env` includes your frontend URL:
```
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```
