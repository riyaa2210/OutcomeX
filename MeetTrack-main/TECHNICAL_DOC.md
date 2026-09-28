# MeetTrack — Complete Internal Technical Documentation

> This document covers every internal system in the project: what happens step-by-step when a user registers, logs in, uploads a meeting, queries their meeting history with natural language, and everything in between. Written for developers who need to understand, extend, or debug the codebase.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Application Startup](#2-application-startup)
3. [Registration Flow](#3-registration-flow)
4. [Login Flow — Every Internal Step](#4-login-flow--every-internal-step)
5. [How Every API Request is Authenticated](#5-how-every-api-request-is-authenticated)
6. [Token Refresh & Proactive Rotation](#6-token-refresh--proactive-rotation)
7. [Logout Flow](#7-logout-flow)
8. [Meeting Upload & Processing Pipeline](#8-meeting-upload--processing-pipeline)
9. [AI Extraction — LLM Router Internals](#9-ai-extraction--llm-router-internals)
10. [RAG System — Ask Your Meetings](#10-rag-system--ask-your-meetings)
11. [Celery Task Queue](#11-celery-task-queue)
12. [Security System](#12-security-system)
13. [Database — Every Table & Column](#13-database--every-table--column)
14. [Frontend Architecture](#14-frontend-architecture)
15. [API Reference](#15-api-reference)
16. [Environment Variables Reference](#16-environment-variables-reference)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (React 19)                       │
│  Vite 8 · React Router 7 · Tailwind 4 · Recharts · Framer Motion│
│  AuthContext (localStorage tokens) · api.js (Bearer auto-attach) │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTPS / WebSocket
┌──────────────────────▼──────────────────────────────────────────┐
│              FastAPI 0.129 (Uvicorn 0.41)                       │
│  Middleware stack:                                               │
│   1. CORSMiddleware (origin whitelist from CORS_ORIGINS env)    │
│   2. SecurityHeadersMiddleware (OWASP headers, 404 tracking)    │
│  15 routers mounted · OAuth2PasswordBearer scheme               │
└───────┬──────────────┬────────────────┬────────────────────────-┘
        │              │                │
┌───────▼──────┐ ┌─────▼──────┐ ┌──────▼──────────────┐
│ PostgreSQL 16│ │  Redis 7   │ │  Gemini 2.0 Flash    │
│ + pgvector   │ │ (Celery    │ │  (AI extraction +    │
│ (all tables) │ │ broker +   │ │   RAG embeddings)    │
│              │ │ LLM cache +│ └──────────────────────┘
│              │ │ rate limit)│ ┌──────────────────────┐
└──────────────┘ └────────────┘ │  faster-whisper (CPU)│
                                │  or Colab Whisper API│
                                └──────────────────────┘
┌────────────────────────────────────────────────────────────────┐
│                  Celery Workers (5 queues)                      │
│  transcription · ai_extraction · email_delivery · analytics    │
│  webhooks  —  all backed by same Redis broker                  │
└────────────────────────────────────────────────────────────────┘
```

**Tech stack versions:**

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend framework | FastAPI | 0.129.0 |
| ASGI server | Uvicorn | 0.41.0 |
| ORM | SQLAlchemy | 2.0.46 |
| Validation | Pydantic | 2.12.5 |
| Auth | python-jose (JWT) + passlib (bcrypt) | 3.5.0 / 1.7.4 |
| Task queue | Celery | 5.4.0 |
| DB | PostgreSQL 16 + pgvector 0.8.0 | — |
| Cache/broker | Redis 7 | — |
| AI | google-genai (Gemini 2.0 Flash) | 1.16.0 |
| Transcription | faster-whisper (local) | latest |
| Frontend | React | 19.2.4 |
| Build tool | Vite | 8.0.1 |
| CSS | Tailwind CSS | 4.2.2 |

---

## 2. Application Startup

When you run `uvicorn backend.app.main:app`, this is the exact sequence:

### 1. Environment loading (`backend/app/main.py`, lines 1–9)
```python
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)
```
Loads `.env` from the project root (2 directories above `backend/app/`). This runs **before any imports** to ensure env vars are available when other modules load.

### 2. SQLAlchemy engine creation (`backend/app/database.py`)
```python
if "localhost" in DATABASE_URL:
    engine = create_engine(DATABASE_URL)            # no SSL — local dev
else:
    engine = create_engine(DATABASE_URL,            # SSL for Render/cloud
        connect_args={"sslmode": "require"})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
```
Auto-detects local vs. cloud environment by checking for `"localhost"` in the URL. All models inherit from `Base`.

### 3. All model imports
`main.py` imports every model class before calling `create_all`. This is critical — SQLAlchemy only knows about tables whose Python classes have been imported.

```python
from backend.models import user, meeting, action_item, result, webhook_log
from backend.models.task_log import TaskLog
from backend.services.llm.metrics import LLMCallLog    # llm_call_logs table
from backend.models.evaluation import EvalResult, HumanFeedback, BenchmarkSample
from backend.models.integration import OAuthToken, IntegrationAuditLog, ExternalMeeting
from backend.app.auth import RefreshToken              # refresh_tokens table
from backend.security.audit_log import SecurityAuditLog
```

### 4. Table creation
```python
Base.metadata.create_all(bind=engine, checkfirst=True)
```
Creates all tables that don't already exist. `checkfirst=True` means existing tables are skipped (not dropped). Errors are logged as warnings but don't crash startup.

### 5. FastAPI app + middleware
```python
app = FastAPI(title="MeetTrack API", version="1.0.0")
```
Two middleware layers are applied (in reverse order — last-added runs outermost):
- `SecurityHeadersMiddleware` — wraps every response
- `CORSMiddleware` — handles preflight and origin checks

### 6. All 15 routers mounted
Each router handles a feature domain. Route prefixes are defined inside each router file:
- `upload_router` → `/audio`, `/process`, `/process-transcript`
- `meeting_router` → `/meetings/*`
- `rag_router` → `/rag/*`
- `analytics_router` → `/analytics/*`
- `security_router` → `/auth/*` (token refresh, logout, audit)
- ... (12 more)

---

## 3. Registration Flow

### Frontend side

The `AuthPage.jsx` renders a toggle between login and register forms. On submit, it calls:

```javascript
// AuthContext.jsx — register()
const response = await authService.register(email, password, fullName, role);
```

`authService.register` (`frontend/src/services/authService.js`):
```javascript
POST /register
Content-Type: application/json
Body: { email, password, full_name, role }
```

### Backend: `POST /register` (`main.py`)

```python
@app.post("/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, request: Request, db: Session = Depends(get_db)):
```

**Step 1 — Pydantic validation (`schemas.py`):**
`UserCreate` schema:
- `email: EmailStr` — validates format
- `password: str`
- `full_name: str` default `""`
- `role: str` default `"employee"`

**Step 2 — Duplicate check + user creation (`crud.py`):**
```python
def create_user(db, user: UserCreate):
    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        return None   # signals duplicate to caller
    hashed = auth.hash_password(user.password)  # bcrypt via passlib
    db_user = User(
        full_name = user.full_name,
        email     = user.email,
        password  = hashed,
        role      = user.role,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user
```

**Step 3 — Audit logging:**
```python
log_from_request(request, AuditEventType.REGISTER, user=db_user)
```
Writes a `SecurityAuditLog` row with event_type=`REGISTER`, the user's IP (from `x-forwarded-for` header or `request.client.host`), user agent, and endpoint.

**Step 4 — Response:**
Returns `UserResponse` schema — the newly created user with all profile fields (most will be `null` at this point).

**Frontend after register:**
```javascript
const userData = { id, email, full_name, name, role };
localStorage.setItem("user", JSON.stringify(userData));
setUser(userData);
```
Note: **no token is issued on registration**. The user must log in separately to get JWT tokens.

---

## 4. Login Flow — Every Internal Step

This is the most critical flow. Here is every single thing that happens.

### Step 1 — Frontend sends credentials

`authService.login(email, password)`:
```javascript
POST /login
Content-Type: application/x-www-form-urlencoded
Body: username=alice@example.com&password=secret123
```
Note the content type: `application/x-www-form-urlencoded`, **not** JSON. FastAPI's `OAuth2PasswordRequestForm` requires this exact format. The email goes in the `username` field.

### Step 2 — FastAPI parses the form (`main.py`)

```python
@app.post("/login")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
```
`OAuth2PasswordRequestForm` automatically parses the form body and exposes `.username` and `.password`.

### Step 3 — CRUD layer verifies credentials (`crud.py`)

```python
db_user = crud.login_user(db, UserLogin(email=form_data.username, password=form_data.password))
```

Inside `login_user`:
1. `db.query(User).filter(User.email == email).first()` — looks up user by email
2. If no user found → returns `None`
3. `auth.verify_password(plain, db_user.password)`:
   - If stored hash starts with `$2b$` or `$2a$` → bcrypt verify via passlib
   - Otherwise → legacy plaintext comparison (for migration period)
4. If password wrong → returns `None`
5. Returns the `User` ORM object on success

If `None` is returned → raises `HTTP 401 "Invalid email or password"`

### Step 4 — Access token creation (`auth.py`)

```python
access_token = create_access_token(data={"user_id": db_user.id})
```

Inside `create_access_token`:
```python
jti = str(uuid.uuid4())           # unique token ID for revocation
expire = datetime.now(UTC) + timedelta(minutes=15)
payload = {
    "user_id": db_user.id,
    "exp":     expire,
    "type":    "access",
    "jti":     jti,
}
return jwt.encode(payload, SECRET_KEY, algorithm="HS256")
```
Result: a signed JWT string like `eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoxLCJleHAiOjE3...`

### Step 5 — Refresh token creation + DB persistence (`auth.py`)

```python
refresh_token = create_refresh_token(
    db_user.id, db,
    ip_address=request.client.host,
    user_agent=request.headers.get("user-agent", ""),
)
```

Inside `create_refresh_token`:
```python
jti        = str(uuid.uuid4())
expires_at = datetime.now(UTC) + timedelta(days=7)
payload = {
    "user_id": db_user.id,
    "type":    "refresh",
    "jti":     jti,
    "exp":     expires_at,
}
token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

# Persist to DB
rt = RefreshToken(
    jti        = jti,
    user_id    = db_user.id,
    expires_at = expires_at,
    ip_address = ip_address,         # e.g. "192.168.1.1"
    user_agent = user_agent[:500],   # e.g. "Mozilla/5.0 ..."
)
db.add(rt)
db.commit()
return token
```

The `refresh_tokens` table now has a row for this login session.

### Step 6 — Audit log

```python
log_from_request(request, AuditEventType.LOGIN_SUCCESS, user=db_user)
```
Writes to `security_audit_logs` with event_type=`LOGIN_SUCCESS`, risk_score, IP, user agent.

### Step 7 — Response sent to frontend

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "user_id": 1,
  "email": "alice@example.com",
  "full_name": "Alice Smith",
  "role": "employee",
  "phone_number": null,
  "profile_image": null,
  "bio": null,
  "job_title": null,
  "department": null,
  "employee_id": null,
  "manager_name": null,
  "skills": [],
  "location": null,
  "work_mode": null,
  "timezone": null
}
```

### Step 8 — Frontend stores tokens and state (`AuthContext.jsx`)

```javascript
localStorage.setItem("access_token",  response.access_token);
localStorage.setItem("refresh_token", response.refresh_token);

const userData = {
    id:        response.user_id || 1,
    email:     response.email,
    name:      response.full_name || email.split("@")[0],
    full_name: response.full_name || "",
    role:      response.role || "employee",
};
localStorage.setItem("user", JSON.stringify(userData));
setUser(userData);
setToken(response.access_token);
scheduleRefresh();   // schedule silent refresh at 14 minutes
```

All three keys are in `localStorage` — they survive page refreshes and browser restarts.

### Step 9 — Proactive refresh scheduled

```javascript
// fires after 14 minutes
setTimeout(async () => {
    const refreshToken = localStorage.getItem("refresh_token");
    const res = await fetch(`${API}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (res.ok) {
        const data = await res.json();
        localStorage.setItem("access_token",  data.access_token);
        localStorage.setItem("refresh_token", data.refresh_token);
        setToken(data.access_token);
        scheduleRefresh();   // schedule again
    }
}, 14 * 60 * 1000);
```

This means the user never sees an expired token popup as long as the tab stays open.

---

## 5. How Every API Request is Authenticated

### Frontend side — `api.js`

```javascript
function getHeaders(includeAuth = true) {
    const headers = { "Content-Type": "application/json" };
    if (includeAuth) {
        const token = localStorage.getItem("access_token");
        if (token) headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
}

async function request(method, endpoint, data) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);  // 30s timeout
    const response = await fetch(`${BASE_URL}${endpoint}`, {
        method,
        headers: getHeaders(),
        body: data ? JSON.stringify(data) : undefined,
        signal: controller.signal,
    });
    // throws Error("Request timeout") on abort
    // extracts response.detail for API errors
}
```

Every call to `api.get()`, `api.post()` etc. automatically attaches the Bearer token from localStorage.

### Backend side — `get_current_user` dependency

Every protected endpoint declares `current_user = Depends(get_current_user)`.

```python
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme)):
    # 1. Extract Bearer token from Authorization header
    # 2. Verify JWT signature + expiry + type claim
    payload = verify_token(token, expected_type="access")
```

Inside `verify_token`:
```python
def verify_token(token: str, expected_type: str = "access") -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        
        # Check type claim
        if payload.get("type") != expected_type:
            return None
        
        # Check Redis revocation list (for logout-before-expiry)
        if expected_type == "access":
            jti = payload.get("jti", "")
            if jti and is_token_revoked(jti):
                return None                  # token was revoked
        
        return payload
    except JWTError:
        return None   # expired, tampered, wrong key
```

Then:
```python
user_id = payload.get("user_id")
db = SessionLocal()
user = db.query(User).filter(User.id == user_id).first()
if user is None:
    raise HTTPException(401, "User not found")
return user
```

If anything fails → `HTTP 401 Unauthorized` with `WWW-Authenticate: Bearer` header.

### Frontend protected routes — `App.jsx`

```javascript
function ProtectedRoute({ children }) {
    const { user } = useAuth();
    return user ? children : <Navigate to="/auth" replace />;
}
```

On page load, `AuthContext` reads `localStorage["user"]` and `localStorage["access_token"]`. If both exist, `user` is populated and the ProtectedRoute renders normally. If either is missing, the user gets redirected to `/auth`.

---

## 6. Token Refresh & Proactive Rotation

### Proactive (silent) refresh — every 14 minutes

See Step 9 in the Login Flow above. Triggered automatically by `scheduleRefresh()`.

### Manual refresh — `POST /auth/refresh`

Handled by `security_routes.py`:

```
POST /auth/refresh
Content-Type: application/json
Body: { "refresh_token": "eyJ..." }
```

Backend process:
1. `verify_token(token, expected_type="refresh")` — decode, check type claim
2. `is_token_revoked(jti)` — Redis lookup
3. DB query: `RefreshToken WHERE jti=? AND revoked=False`
4. Check `rt.expires_at < now()` — if expired, mark revoked and return 401
5. `rotate_refresh_token(old_jti, user_id, db, ip, ua)`:
   - Sets old record `revoked=True`
   - Creates new `RefreshToken` row with new jti
6. `create_access_token(data={"user_id": user_id})`
7. Returns `{ access_token, refresh_token }` (new pair)

This is **token rotation** — every refresh issues a completely new pair and revokes the old one, preventing replay attacks.

### On page load — session persistence

```javascript
useEffect(() => {
    const storedUser  = localStorage.getItem("user");
    const storedToken = localStorage.getItem("access_token");
    if (storedUser && storedToken) {
        setUser(JSON.parse(storedUser));
        setToken(storedToken);
        scheduleRefresh();   // resume refresh cycle
    }
    setLoading(false);
}, []);
```

If the tab was open but expired (>15 min idle, no proactive refresh), the next API call returns 401 and the user is redirected to login.

---

## 7. Logout Flow

### Frontend (`AuthContext.jsx`)

```javascript
const logout = async () => {
    clearTimeout(refreshTimerRef.current);    // cancel refresh timer
    
    const refreshToken = localStorage.getItem("refresh_token");
    const accessToken  = localStorage.getItem("access_token");
    
    // Fire-and-forget server logout (non-blocking)
    if (refreshToken && accessToken) {
        fetch(`${API}/auth/logout`, {
            method: "POST",
            headers: {
                "Content-Type":  "application/json",
                "Authorization": `Bearer ${accessToken}`,
            },
            body: JSON.stringify({ refresh_token: refreshToken }),
        }).catch(() => {});   // ignore network errors
    }
    
    // Always clear locally regardless of server response
    authService.logout();                              // clears localStorage
    localStorage.removeItem("user");
    localStorage.removeItem("refresh_token");
    setUser(null);
    setToken(null);
    setError(null);
};
```

### Backend — `POST /auth/logout` (`security_routes.py`)

1. Extracts Bearer token (access token) from Authorization header
2. Gets `user_id` from access token
3. Finds and marks the specific `RefreshToken` row as `revoked=True`
4. Calls `revoke_token(jti_of_access_token)` — writes `SETEX revoked_token:{jti} 86400 1` to Redis
   - Access tokens now also check this Redis key on every subsequent request
5. Writes `AuditEventType.LOGOUT` to `security_audit_logs`

The access token is now invalid even though it hasn't expired. Any request with it will fail the `is_token_revoked(jti)` check in `verify_token`.

**Logout all devices — `POST /auth/logout-all`:**
```python
revoke_all_user_tokens(user_id, db)
# UPDATE refresh_tokens SET revoked=True WHERE user_id=? AND revoked=False
```
All refresh tokens for the user are revoked. Access tokens expire naturally (15 min) but are not individually revoked.

---

## 8. Meeting Upload & Processing Pipeline

This is the core product feature. Here's exactly what happens when a user uploads an audio file.

### Entry point: Dashboard page

`DashboardPage.jsx` has two input modes:
1. **Audio file drop** (`.mp3`, `.wav`, `.m4a`) — upload first, then process
2. **Transcript paste** — skip transcription, go straight to AI

**Audio path (2-step):**
```
POST /audio   →   POST /process
```

**Transcript path (1-step):**
```
POST /process-transcript
```

---

### Step 1 — File Upload: `POST /audio`

```python
@router.post("/audio")
async def upload_audio(file: UploadFile = File(...), current_user=Depends(get_current_user)):
```

1. Validates file exists
2. Saves to `uploads/{filename}` using `shutil.copyfileobj(file.file, buffer)`
3. Returns `{ message, file_path: "/absolute/path/to/uploads/recording.mp3", file_name }`

The frontend stores `file_path` and sends it in the next request.

---

### Step 2 — Full Pipeline: `POST /process`

```python
@router.post("/process")
async def process_meeting(request: ProcessRequest, background_tasks: BackgroundTasks, ...):
    # ProcessRequest: { file_path: str, file_name: str }
```

#### Sub-step A — Transcription

```python
transcript = transcribe_audio(file_path)
```

**If `USE_LOCAL_WHISPER=true`** (faster-whisper):
```python
# Model loaded once and cached as a singleton
model = WhisperModel(
    WHISPER_MODEL_SIZE,    # "base" by default
    device="cpu",
    compute_type="int8",   # fastest on CPU
)
segments, info = model.transcribe(
    file_path,
    beam_size=5,
    language=None,         # auto-detect language
    vad_filter=True,       # skip silence — much faster
)
transcript = " ".join(seg.text.strip() for seg in segments)
```

**If `USE_LOCAL_WHISPER=false`** (Colab API):
```python
colab_url = os.getenv("COLAB_API_URL")
response = requests.post(
    f"{colab_url}/transcribe",
    files={"file": (filename, audio_file, "audio/mpeg")},
    headers={
        "bypass-tunnel-reminder":     "true",
        "ngrok-skip-browser-warning": "69420",
    },
    timeout=300,
)
transcript = response.json()["transcription"]
```

#### Sub-step B — Create Meeting Record

```python
new_meeting = Meeting(
    user_id    = current_user.id,
    title      = "recording"   # stripped .mp3/.wav extension
    audio_path = file_path,
    transcript = transcript,
    created_at = datetime.utcnow(),
)
db.add(new_meeting)
db.commit()
db.refresh(new_meeting)   # populates new_meeting.id
```

#### Sub-step C — NLP Pre-processing (`nlp_service.py`)

Called inside `generate_structured_summary`:

```python
pipeline = run_preprocessing_pipeline(transcript)
```

Returns:
```python
{
    "cleaned_transcript":   "...",   # punctuation fixed, whitespace normalized
    "speakers":             ["Alice", "Bob"],  # detected from "Alice: ..." patterns
    "action_sentences":     ["Alice will send the report..."],  # spaCy-tagged
    "decision_sentences":   ["We decided to delay the launch..."],
}
```

spaCy (`en_core_web_sm`) is used to:
- Detect speaker turns via regex `^(?:([A-Z][a-zA-Z\s]{1,25}):|(?:\[([^\]]+)\])\s*:?)`
- Extract action-bearing sentences (contains future tense, verbs like "will", "should", "needs to")
- Extract decision-bearing sentences (contains "decided", "agreed", "confirmed", etc.)
- Extract named person mentions and date expressions

#### Sub-step D — LLM Structured Extraction

**Short transcripts (<4800 chars):** single LLM call

A detailed prompt is built:
```
You are a professional meeting analyst...
Known speakers: Alice, Bob.
Pre-identified action-bearing sentences:
  - Alice will send the report by Friday
  - Bob needs to schedule the demo
Pre-identified decision-bearing sentences:
  - We decided to delay the launch by 2 weeks
STRICT RULES:
  1. Extract ONLY information explicitly stated...
  2. Do NOT invent, assume, or hallucinate...
  ...
Output schema: {"summary": "...", "decisions": [...], "action_items": [...]}
Transcript: {first 3500 chars}
Return ONLY the JSON object:
```

**Long transcripts (≥4800 chars):** map-reduce

`llm/chunker.py` splits the transcript into overlapping chunks (~2000 chars each with 200-char overlap), summarizes each chunk individually with Gemini, then reduces all chunk summaries into a final structured output.

Both paths go through the **LLM Router** (see Section 9).

**Output validation** — every action item is strictly validated:
- `task` must be a non-empty string
- `assignee` defaults to `"Unassigned"` if missing
- `deadline` must match `^\d{4}-\d{2}-\d{2}$` or is set to `null`
- `confidence_score` is clamped to `[0.0, 1.0]`, defaults to `0.8`

#### Sub-step E — Persist Action Items

```python
for item in structured["action_items"]:
    if item["confidence_score"] < 0.4:
        continue    # skip very low confidence items
    
    action = ActionItem(
        meeting_id  = new_meeting.id,
        assigned_to = item["assignee"],
        title       = item["task"][:100],
        description = item["task"],
        deadline    = item["deadline"],
        status      = "Pending",
    )
    db.add(action)

db.commit()
```

#### Sub-step F — Background Tasks (non-blocking)

Three tasks are queued with `FastAPI BackgroundTasks` — they run after the response is sent:

**1. Automation webhook** (`trigger_n8n_workflow`):
- Builds payload `{ meeting_id, event_type: "meeting_processed", summary, decisions, action_items }`
- Computes SHA-256 idempotency key from payload hash
- Checks `webhook_logs` for existing delivery with same key (deduplication)
- Posts to `N8N_WEBHOOK_URL` with up to 3 retry attempts
- Saves delivery status to `webhook_logs`

**2. RAG indexing** (`rag_index_meeting`):
- Chunks transcript and stores embeddings in `meeting_chunks` table
- See Section 10 for full RAG details

**3. AI Evaluation** (`evaluate_meeting_output`):
- Scores summary quality, decision accuracy, action precision
- Detects hallucinations (names/dates/decisions not grounded in transcript)
- Saves `EvalResult` row with 6 dimension scores

#### Sub-step G — Response

```json
{
  "status": "success",
  "meeting_id": 42,
  "title": "Q3 Planning Call",
  "transcript": "Alice: Good morning everyone. Today we need to...",
  "structured_output": {
    "summary": "The team reviewed Q3 priorities and decided to delay the product launch by two weeks pending design approval. Alice will finalize the roadmap by Friday.",
    "decisions": [
      "Launch delayed by 2 weeks pending design sign-off",
      "Weekly sync moved to Tuesdays"
    ],
    "action_items": [
      {
        "task": "Finalize Q3 roadmap document",
        "assignee": "Alice",
        "deadline": "2024-01-19",
        "confidence_score": 0.95
      },
      {
        "task": "Schedule design review meeting",
        "assignee": "Bob",
        "deadline": null,
        "confidence_score": 0.82
      }
    ]
  }
}
```

---

## 9. AI Extraction — LLM Router Internals

The LLM router lives in `backend/services/llm/router.py` and is a singleton (`get_router()` via double-checked locking).

### Provider hierarchy

| Task type | Primary | Fallback 1 | Fallback 2 |
|-----------|---------|-----------|-----------|
| SUMMARIZATION | Gemini 1.5 Pro | OpenAI GPT-4o | Local (regex) |
| EXTRACTION | Gemini 1.5 Flash | OpenAI GPT-4o | Local |
| REASONING | GPT-4o | Gemini | Local |
| SENTIMENT | Gemini Flash | Local | OpenAI |
| CLASSIFICATION | Local | Gemini | OpenAI |
| CHAT | GPT-4o-mini | Gemini | Local |
| EMBEDDING | Gemini text-embedding-004 | Local (TF-IDF) | — |
| FALLBACK | Local | Gemini | OpenAI |

### Per-task timeouts

| Task | Timeout |
|------|---------|
| SUMMARIZATION | 45s |
| EXTRACTION | 30s |
| REASONING | 60s |
| SENTIMENT | 15s |
| CLASSIFICATION | 10s |
| CHAT | 20s |
| FALLBACK | 5s |

Timeouts are enforced via Python `threading.Timer` — the call is interrupted after the timeout and the next provider in the chain is tried.

### Complete `router.complete()` flow

```
1. Check two-tier cache
   ├── In-memory LRU (512 slots, OrderedDict, thread-safe)
   └── Redis (1-hour TTL)
   If cache hit → return immediately (cache_hit=True)

2. For each provider in the routing chain:
   a. Check provider.is_available()
      └── GeminiProvider: GEMINI_API_KEY must be set
      └── OpenAIProvider: OPENAI_API_KEY must be set
      └── LocalProvider: always available
   b. Check circuit breaker.is_open(provider)
      └── Circuit opens after 3 consecutive failures
      └── Auto-resets after 60 seconds
   c. _call_with_timeout(provider, prompt, task_type, max_tokens, timeout)
      └── Runs provider.complete() in a thread
      └── Main thread waits up to `timeout` seconds
      └── Returns error response if timeout exceeded
   
   If call succeeds:
   d. breaker.record_success(provider)
   e. score_response(text, task_type, source_text, prompt)
      └── Returns quality float 0.0–1.0
   f. detect_hallucinations(text, source_text)
      └── Returns {hallucination_risk: float, ...}
   g. record_call(response, ...) → writes LLMCallLog to DB
   h. set_cached(key, response) → writes to LRU + Redis
   i. Return response
   
   If call fails:
   d. breaker.record_failure(provider)
   e. record_call(response, ...) (failure recorded)
   f. Continue to next provider in chain

3. If ALL providers fail:
   └── LocalProvider guaranteed fallback (regex extraction)
   └── quality_score = 0.3
```

### Cache key construction

```python
key_source = f"{provider.value}:{model}:{task_type.value}:{prompt[:500]}"
cache_key  = "llm:" + sha256(key_source.encode()).hexdigest()
```

Only the first 500 chars of the prompt are used in the key to avoid unbounded memory use.

### Cost tracking per provider

Every `LLMCallLog` row stores:
- `prompt_tokens`, `completion_tokens`, `total_tokens`
- `cost_usd` — calculated from per-provider pricing:

| Model | Input ($/1K tokens) | Output ($/1K tokens) |
|-------|-------------------|---------------------|
| gemini-1.5-flash | $0.000075 | $0.0003 |
| gemini-1.5-pro | $0.00125 | $0.005 |
| gpt-4o | $0.005 | $0.015 |
| gpt-4o-mini | $0.00015 | $0.0006 |
| local | $0 | $0 |

---

## 10. RAG System — Ask Your Meetings

The RAG (Retrieval-Augmented Generation) system lets users ask natural language questions like "What tasks were assigned to Alice last week?" and get accurate answers grounded in their own meeting transcripts.

### Indexing Phase (happens after every meeting)

Called as a background task in `process_meeting`:

```python
rag_index_meeting(db, meeting_id, user_id, transcript, title, summary, decisions)
```

**Step 1 — Delete existing chunks** (re-index clean):
```python
db.query(MeetingChunk).filter(MeetingChunk.meeting_id == meeting_id).delete()
```

**Step 2 — Chunk the transcript** (`embedding_service.chunk_transcript`):

Speaker-turn splitting:
```python
# Pattern: "Alice: ..." or "[Alice] ..."
speaker_pattern = r"^(?:([A-Z][a-zA-Z\s]{1,25}):|(?:\[([^\]]+)\])\s*:?)"
```

If no speakers found: splits on double-newlines (paragraph mode).

After splitting:
- Chunks <30 words are merged with adjacent chunks
- Chunks >400 words are split further (target: 250 words, 50-word overlap)

Then summary and decisions are appended as special chunks:
```python
chunks.append({"text": summary, "chunk_type": "summary", ...})
for decision in decisions:
    chunks.append({"text": decision, "chunk_type": "decision", ...})
```

**Step 3 — Generate embeddings** (`embed_text(text)`):

Primary: Google Gemini `text-embedding-004` model:
```python
genai.Client.models.embed_content(
    model="models/text-embedding-004",
    contents=text[:8000],
)
→ 768-dimensional float vector
```

Fallback (if Gemini unavailable): deterministic character-hash TF-IDF vector (not semantic, but searchable).

**Step 4 — Store in database**:
```python
MeetingChunk(
    meeting_id    = meeting_id,
    user_id       = user_id,
    chunk_text    = text,
    chunk_index   = i,
    chunk_type    = "transcript" | "summary" | "decision",
    speaker       = "Alice",
    meeting_title = "Q3 Planning",
    embedding     = [0.023, -0.14, 0.89, ...]   # 768 floats, stored as pgvector Vector(768)
)
```

### Query Phase: `POST /rag/ask-meetings`

```
Input: { "query": "What tasks were assigned to Alice?", "meeting_id": null }
```

**Step 1 — Embed the query**:
```python
query_embedding = embed_text(query)   # → same 768-dim vector space
```

**Step 2 — Vector similarity search** (pgvector):
```sql
SELECT
    mc.id,
    mc.meeting_id,
    mc.chunk_text,
    mc.chunk_type,
    mc.speaker,
    mc.meeting_title,
    1 - (mc.embedding <=> :query_embedding::vector) AS similarity
FROM meeting_chunks mc
WHERE mc.user_id = :user_id
  AND mc.embedding IS NOT NULL
ORDER BY mc.embedding <=> :query_embedding::vector
LIMIT 5
```

The `<=>` operator is pgvector's cosine distance. `1 - distance = similarity`.
Chunks with `similarity < 0.3` are filtered out.

If pgvector fails (extension not installed): falls back to keyword ILIKE search.

**Step 3 — Hybrid reranking**:
```python
rerank_score = 0.6 × vector_similarity + 0.4 × keyword_overlap
```
Where `keyword_overlap = |query_words ∩ chunk_words| / |query_words|`.

Results sorted by `rerank_score` descending.

**Step 4 — Build context** (max 3000 chars):
```
[Q3 Planning — transcript]
Alice: I'll send the revised roadmap by Friday.

[Q3 Planning — decision]
Product launch delayed by 2 weeks pending design approval.
```

**Step 5 — Generate answer with Gemini**:
```
Grounded prompt:
  "Answer the user's question using ONLY the meeting context provided.
   Cite the meeting title when referencing information.
   If the information is not in the context, say so clearly."
```

**Step 6 — Save query history**:
```python
QueryHistory(
    user_id    = user_id,
    query      = query,
    answer     = answer,
    confidence = 0.5 + len(context)/10000,   # scales with context amount
    sources    = [{meeting_id, meeting_title, chunk_type, similarity, excerpt}]
)
```

**Step 7 — Response**:
```json
{
  "answer": "Alice was assigned two tasks: finalize the Q3 roadmap document (due Friday, from the 'Q3 Planning' meeting) and review the design mockups before the next sprint.",
  "sources": [
    {
      "meeting_id": 42,
      "meeting_title": "Q3 Planning Call",
      "chunk_type": "transcript",
      "speaker": "Alice",
      "similarity": 0.87,
      "excerpt": "Alice: I'll get the roadmap done before Friday and also take a look at..."
    }
  ],
  "confidence": 0.74,
  "chunks_used": 3
}
```

---

## 11. Celery Task Queue

Redis serves dual duty: Celery message broker (db=0) and result backend (db=1).

### Queue architecture

| Queue | Concurrency | Use case |
|-------|-------------|---------|
| `transcription` | 2 | Colab API calls (I/O-bound) |
| `ai_extraction` | 4 | Gemini API calls (CPU-light) |
| `email_delivery` | 8 | SMTP sends (I/O-bound, fast) |
| `analytics` | 2 | Heavy DB aggregation queries |
| `webhooks` | 4 | HTTP retries to n8n/Activepieces |
| `dead_letter` | — | Failed tasks awaiting retry |

### Task idempotency

Every task uses `task_logger.py` for deduplication:

```python
key = make_idempotency_key("transcribe", meeting_id, file_path)
# → SHA-256("transcribe|42|/path/to/file.mp3")

if is_duplicate(db, key):
    return {"skipped": True, "reason": "already processed"}
```

### Task state machine

```
queued → processing → completed
                   ↓
                failed (attempt < max)
                   ↓
                retrying (exponential backoff)
                   ↓
                dead_letter (after 3 failures)
```

### Retry policy

`transcription_tasks.transcribe_audio_task`:
- Max retries: 3
- Backoff: 60s × 2^attempt (60s, 120s, 240s)

`ai_tasks.ai_extraction_task`:
- Max retries: 3
- Backoff: 30s × 2^attempt (30s, 60s, 120s)

### Task chain

```
transcription_task
    └── ai_extraction_task
            ├── webhook_delivery_task    (queue: webhooks)
            ├── rag_index_task           (queue: ai_extraction)
            └── send_task_assignment_emails  (queue: email_delivery)
```

### Beat schedule (periodic tasks)

```python
beat_schedule = {
    "retry-failed-webhooks-every-10min": {
        "task":     "backend.worker.tasks.webhook_tasks.retry_dead_letter_webhooks",
        "schedule": 600,   # every 10 minutes
    },
    "cleanup-old-task-logs-daily": {
        "task":     "backend.worker.tasks.analytics_tasks.cleanup_old_task_logs",
        "schedule": 86400, # every 24 hours
    },
}
```

### Windows quirk

On Windows, Celery's default `prefork` pool doesn't work (no `os.fork`). Start with:
```
celery ... --pool=solo
```

---

## 12. Security System

### RBAC — Role-Based Access Control

Four roles in order of permissions:
```
viewer (0) < employee (1) < manager (2) < admin (3)
```

**FastAPI dependency:**
```python
require_role("manager")   # → dependency that checks role level ≥ 2
```

**Ownership check:**
```python
assert_owns_or_admin(resource_user_id, current_user)
# → raises HTTP 403 unless current_user.id == resource_user_id OR admin
```

**Permission set per role (examples):**

| Permission | viewer | employee | manager | admin |
|-----------|--------|----------|---------|-------|
| read own meetings | ✓ | ✓ | ✓ | ✓ |
| write own meetings | — | ✓ | ✓ | ✓ |
| read all meetings | — | — | ✓ | ✓ |
| manage users | — | — | — | ✓ |
| view security dashboard | — | — | ✓ | ✓ |

### Rate Limiting

Redis sliding-window counter (INCR + EXPIRE):

| Context | Limit | Window |
|---------|-------|--------|
| Authentication endpoints | 10 requests | 1 minute |
| File upload | 5 requests | 1 minute |
| General API | 100 requests | 1 minute |
| Global (all requests) | 1000 requests | 1 minute |
| Webhooks | 50 requests | 1 minute |

Key format: `ratelimit:{context}:{ip_address}`

If Redis is unreachable → **fails open** (allows all requests — availability over security).

**Failed login lockout:**
```python
record_failed_login(ip)    # INCR + EXPIRE 900s
# After 5 failures:
is_ip_locked(ip)           # → True → HTTP 429 "Too many failed attempts"
# On success:
clear_failed_logins(ip)    # DEL key
```

### Anomaly Detection

Redis-backed IP risk scoring (0–100):

| Trigger | Risk added |
|---------|-----------|
| Failed login | +10 (max +40) |
| >200 req/min | +30 |
| >100 req/min | +15 |
| 404 response | +5 (max +20) |
| Request outside 6am–11pm UTC | +5 |

When `risk_score ≥ 51`: writes `ANOMALY_DETECTED` audit log.

**Token revocation via Redis:**
```python
revoke_token(jti):
    redis.setex(f"revoked_token:{jti}", 86400, 1)   # expires after 24h

is_token_revoked(jti):
    return redis.exists(f"revoked_token:{jti}")
```

Every access token verification checks this.

**Webhook replay prevention:**
```python
check_webhook_replay(event_id, window=300):
    result = redis.set(f"webhook_replay:{event_id}", 1, nx=True, ex=300)
    return result is None   # True = already seen = replay
```

### Security Headers (on every response)

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; ...
```

Server fingerprint headers (`Server`, `X-Powered-By`) are removed.

### File Security

For audio uploads, `validate_upload` runs in this order:
1. Sanitize filename (strip paths, control chars, limit to 200 chars)
2. Check extension whitelist: `.mp3 .wav .m4a .ogg .flac .webm .mp4`
3. Read 16 magic bytes and detect MIME type (ID3 → audio/mpeg, RIFF → audio/wav, etc.)
4. Verify detected MIME is an allowed audio MIME type
5. Read full file content, check ≤ 100MB
6. Scan first 1024 bytes for PHP/script injection patterns
7. Optionally: ClamAV socket scan (if `CLAMAV_SOCKET` env var is set)
8. Returns `{filename, size, mime_type, extension, sha256}`

---

## 13. Database — Every Table & Column

### `users`

| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | auto-increment |
| full_name | VARCHAR(255) | NOT NULL |
| email | VARCHAR | UNIQUE, indexed |
| password | VARCHAR | bcrypt hash |
| role | VARCHAR(50) | default="employee" |
| phone_number | VARCHAR(20) | nullable |
| profile_image | VARCHAR(500) | file path or URL |
| bio | TEXT | nullable |
| job_title | VARCHAR(255) | nullable |
| department | VARCHAR(255) | nullable |
| employee_id | VARCHAR(100) | nullable, UNIQUE |
| manager_name | VARCHAR(255) | nullable |
| skills | TEXT | JSON array as string: `["Python","React"]` |
| location | VARCHAR(255) | nullable |
| work_mode | VARCHAR(50) | "Remote"/"Hybrid"/"Office" |
| timezone | VARCHAR(100) | e.g. "Asia/Kolkata" |

### `meetings`

| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | indexed |
| user_id | INT FK | → users.id |
| title | VARCHAR(255) | nullable |
| audio_path | TEXT | nullable (absolute path) |
| transcript | TEXT | nullable |
| created_at | DateTime(tz) | server_default=now() |

Relationships: `action_items` (back_populates), `chunks` (backref)

### `action_items`

| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | indexed |
| meeting_id | INT FK | → meetings.id ON DELETE CASCADE |
| title | VARCHAR(255) | first 100 chars of task |
| description | TEXT | full task text |
| assigned_to | VARCHAR(255) | person name or "Unassigned" |
| deadline | VARCHAR | YYYY-MM-DD string or null |
| status | VARCHAR(50) | default="Pending" |
| created_at | DateTime(tz) | server_default=now() |

### `results`

| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | indexed |
| meeting_id | INT FK | → meetings.id |
| transcript | TEXT | |
| summary | TEXT | JSON string: `{summary, decisions, action_items}` |
| summary_approved | Boolean | default=False |

### `refresh_tokens`

| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| jti | VARCHAR(64) | UUID, UNIQUE, indexed |
| user_id | INT FK | → users.id ON DELETE CASCADE |
| revoked | Boolean | default=False |
| expires_at | DateTime(tz) | |
| created_at | DateTime(tz) | server_default=now() |
| user_agent | VARCHAR(500) | browser/client info |
| ip_address | VARCHAR(45) | IPv4 or IPv6 |

### `meeting_chunks` (RAG vector store)

| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | indexed |
| meeting_id | INT FK | → meetings.id ON DELETE CASCADE, indexed |
| user_id | INT FK | → users.id, indexed |
| chunk_text | TEXT | NOT NULL |
| chunk_index | INT | position in transcript, default=0 |
| chunk_type | VARCHAR(50) | "transcript" / "summary" / "decision" |
| speaker | VARCHAR(255) | nullable, detected speaker name |
| meeting_title | VARCHAR(255) | denormalized for display |
| embedding | Vector(768) | pgvector column; JSON fallback if no pgvector |
| created_at | DateTime | |

### `query_history`

| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| user_id | INT FK | → users.id, indexed |
| query | TEXT | user's natural language question |
| answer | TEXT | AI-generated answer |
| confidence | Float | 0.0–1.0 |
| sources | JSON | list of source chunks used |
| created_at | DateTime | |

### `task_logs` (Celery execution history)

| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| celery_task_id | VARCHAR(255) | Celery task UUID |
| task_type | VARCHAR(100) | e.g. "transcribe" |
| task_name | VARCHAR(255) | full module path |
| meeting_id | INT | nullable |
| user_id | INT | nullable |
| idempotency_key | VARCHAR(64) | SHA-256, UNIQUE |
| state | Enum | queued/processing/completed/failed/retrying/revoked |
| created_at, started_at, completed_at | DateTime | |
| duration_secs | Float | |
| attempt_number, max_attempts | INT | |
| input_summary, result_summary | TEXT | |
| error_message, error_traceback | TEXT | |
| meta | JSON | |

### `webhook_logs`

| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| meeting_id | INT | indexed |
| event_type | VARCHAR(64) | default="meeting_processed" |
| status | VARCHAR(32) | pending/delivered/failed/skipped |
| attempt_count, max_attempts | INT | default=3 |
| n8n_status_code | INT | HTTP response code |
| n8n_response | TEXT | first 2000 chars of response |
| last_error | TEXT | |
| idempotency_key | VARCHAR(64) | UNIQUE, SHA-256 |
| created_at, last_attempted_at, delivered_at | DateTime | |

### `oauth_tokens`

| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| user_id | INT FK | → users.id |
| provider | Enum | google_calendar/zoom/microsoft_teams/trello/notion/jira/... |
| access_token, refresh_token | TEXT | AES-256 encrypted |
| token_type, scope | VARCHAR | |
| expires_at | DateTime | |
| is_expired | Boolean | |
| provider_user_id, provider_email | VARCHAR | |
| webhook_id, webhook_secret | VARCHAR | webhook_secret encrypted |
| is_active | Boolean | |
| last_synced_at, sync_error | DateTime/TEXT | |

Unique index on `(user_id, provider)`.

### `eval_results` (AI quality scores)

| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| meeting_id | INT FK | |
| user_id | INT | |
| provider, model | VARCHAR | which LLM produced the output |
| summary_quality_score | Float 0–1 | |
| decision_accuracy_score | Float 0–1 | |
| action_precision_score | Float 0–1 | |
| hallucination_score | Float 0–1 | higher = more hallucination detected |
| groundedness_score | Float 0–1 | |
| completeness_score | Float 0–1 | |
| overall_score | Float 0–1 | |
| flagged_terms, unsupported_claims | JSON | |
| fabricated_deadlines, incorrect_assignees | JSON | |
| action_items_count, decisions_count, low_confidence_items | INT | |
| precision, recall, f1_score | Float | |

### `security_audit_logs`

| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| event_type | VARCHAR(60) | LOGIN_SUCCESS / LOGOUT / REGISTER / PROFILE_UPDATED / ANOMALY_DETECTED / etc. |
| user_id | INT | nullable |
| user_email, user_role | VARCHAR | denormalized |
| ip_address | VARCHAR(45) | |
| user_agent | TEXT | |
| endpoint, method | VARCHAR | |
| resource_type, resource_id | VARCHAR | |
| details | JSON | additional context |
| old_value, new_value | TEXT | for change events |
| success | Boolean | |
| risk_score | INT 0–100 | |
| created_at | DateTime | |

### `llm_call_logs`

| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| provider | VARCHAR | "gemini" / "openai" / "local" |
| model | VARCHAR | e.g. "gemini-1.5-flash" |
| task_type | VARCHAR | "summarization" / "extraction" / etc. |
| meeting_id | INT | nullable |
| user_id | INT | nullable |
| latency_ms | INT | |
| prompt_tokens, completion_tokens, total_tokens | INT | |
| cost_usd | Float | computed cost |
| quality_score | Float 0–1 | |
| hallucination_risk | Float 0–1 | |
| cache_hit | Boolean | |
| success | Boolean | |
| error_type | VARCHAR | nullable |
| fallback_used | Boolean | |
| provider_chain | VARCHAR(200) | e.g. "gemini→openai" |
| created_at | DateTime | indexed |

---

## 14. Frontend Architecture

### Directory structure

```
frontend/src/
├── pages/              # 15 page components
│   ├── AuthPage.jsx            — login + register toggle
│   ├── DashboardPage.jsx       — main upload + AI output
│   ├── HistoryPage.jsx         — past meetings list
│   ├── AskMeetingsPage.jsx     — RAG chat interface
│   ├── LiveMeetingPage.jsx     — WebSocket live meeting
│   ├── AnalyticsDashboardPage.jsx — charts + trends
│   ├── TaskMonitorPage.jsx     — Celery task status
│   ├── LLMAdminPage.jsx        — LLM provider management
│   ├── EvalDashboardPage.jsx   — AI quality evaluation
│   ├── SecurityDashboardPage.jsx — security audit log
│   ├── ProfilePage.jsx         — user profile editor
│   ├── LandingPage.jsx         — marketing page
│   ├── AboutPage.jsx
│   ├── ContactPage.jsx
│   └── NotFoundPage.jsx
├── components/
│   ├── MeetingOutput.jsx       — AI result cards
│   ├── UploadProcessor.jsx     — upload progress steps
│   ├── StatPills.jsx           — decision/action counts
│   └── ... (6 more)
├── context/
│   ├── AuthContext.jsx         — auth state + token management
│   ├── authContextObject.js    — createContext() object
│   └── ThemeProvider.jsx       — dark/light mode
├── hooks/
│   └── useLiveMeeting.js       — WebSocket hook
├── services/
│   ├── api.js                  — base HTTP client
│   └── authService.js          — auth-specific API calls
├── layouts/
│   ├── AppLayout.jsx           — sidebar + nav (authenticated)
│   └── PublicLayout.jsx        — simple header/footer
└── main.jsx                    — providers setup
```

### React root setup (`main.jsx`)

```jsx
<BrowserRouter>
    <ThemeProvider>
        <AuthProvider>
            <App />
        </AuthProvider>
    </ThemeProvider>
</BrowserRouter>
```

### Route structure (`App.jsx`)

```
/                   → LandingPage     (public)
/about              → AboutPage       (public)
/contact            → ContactPage     (public)
/auth               → AuthPage        (public)
/dashboard          → DashboardPage   (protected)
/history            → HistoryPage     (protected)
/ask                → AskMeetingsPage (protected)
/live/:meetingId    → LiveMeetingPage (protected)
/analytics          → AnalyticsDashboardPage (protected)
/tasks              → TaskMonitorPage (protected)
/llm-admin          → LLMAdminPage    (protected)
/eval               → EvalDashboardPage (protected)
/security           → SecurityDashboardPage (protected)
/profile            → ProfilePage     (protected)
*                   → NotFoundPage
```

### `api.js` request flow

Every API call uses `AbortController` with a 30-second timeout:

```javascript
const controller = new AbortController();
const timeoutId  = setTimeout(() => controller.abort(), 30000);

fetch(url, { signal: controller.signal, headers: getHeaders(), ... })
```

Error handling extracts the most useful message:
- If response has `{ detail: ... }` → uses `detail`
- If JSON parse fails → uses `statusText`
- On abort → throws `"Request timeout"`

### Live Meeting WebSocket (`useLiveMeeting.js`)

```javascript
const ws = new WebSocket(`ws://127.0.0.1:8000/live/ws/{meeting_id}?token={access_token}`);

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    // data.type: "transcript_chunk" | "ai_suggestion" | "action_item_detected" | "participant_joined"
};
```

The token is passed as a query parameter because the WebSocket protocol doesn't support custom headers.

---

## 15. API Reference

### Authentication

| Method | Path | Auth | Body | Returns |
|--------|------|------|------|---------|
| POST | `/register` | None | `{email, password, full_name?, role?}` | User object |
| POST | `/login` | None | FormData `username=&password=` | Tokens + user profile |
| POST | `/auth/refresh` | None | `{refresh_token}` | `{access_token, refresh_token}` |
| POST | `/auth/logout` | Bearer | `{refresh_token}` | `{message}` |
| POST | `/auth/logout-all` | Bearer | — | `{revoked_count}` |
| GET | `/profile/{user_id}` | Bearer | — | User profile |
| PUT | `/profile/{user_id}` | Bearer | Profile fields | Updated user |
| POST | `/profile/{user_id}/upload-image` | Bearer | Multipart file | `{file_path}` |

### Meeting Processing

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/audio` | Bearer | Save audio file, returns `file_path` |
| POST | `/process` | Bearer | Full pipeline: `{file_path, file_name}` |
| POST | `/process-transcript` | Bearer | Paste mode: `{transcript, title?}` |
| POST | `/generate-summary/{meeting_id}` | Bearer | Re-run AI extraction |
| POST | `/approve-summary` | Bearer | Mark summary approved |

### Meetings

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/meetings/` | Bearer | List own meetings |
| GET | `/meetings/{id}` | Bearer | Single meeting |
| GET | `/meetings/{id}/transcript` | Bearer | Transcript only |
| GET | `/meetings/{id}/summary` | Bearer | AI summary |
| POST | `/meetings/create` | Bearer | Create blank meeting (live mode) |

### Action Items

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/action-items/` | Bearer | All items (filter: `?meeting_id=`) |
| GET | `/action-items/me` | Bearer | Items assigned to current user |
| GET | `/action-items/{id}` | Bearer | Single item |
| POST | `/action-items/` | Bearer | Create item manually |
| PUT | `/action-items/{id}` | Bearer | Update full item |
| PUT | `/action-items/{id}/status` | Bearer | Update status only |
| DELETE | `/action-items/{id}` | Bearer | Delete item |

### RAG / Ask Meetings

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/rag/ask-meetings` | Bearer | `{query, meeting_id?}` → answer + sources |
| GET | `/rag/semantic-search` | Bearer | `?q=&top_k=&chunk_type=` |
| GET | `/rag/query-history` | Bearer | Past queries `?limit=10` |
| POST | `/rag/index/{meeting_id}` | Bearer | Re-index a meeting |

### Analytics

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/analytics/overview` | Bearer | Totals (meetings, actions, completion %) |
| GET | `/analytics/meetings-trend` | Bearer | Time series `?granularity=day\|week\|month` |
| GET | `/analytics/action-items` | Bearer | By-assignee breakdown |
| GET | `/analytics/productivity` | Bearer | Weekly meetings + completion rate |
| GET | `/analytics/heatmap` | Bearer | Day×Hour matrix |
| GET | `/analytics/ai-insights` | Bearer | AI-computed insights |
| GET | `/analytics/report` | Bearer | Download `?fmt=csv\|json` |

### System

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | None | Health ping |
| GET | `/health` | None | DB connectivity check |
| GET | `/debug/config` | None | Env var status |
| GET | `/results/pending/tasks` | Bearer | Real pending action items |
| POST | `/contact` | None | Contact form submission |

---

## 16. Environment Variables Reference

### Required — app won't function without these

| Variable | Example | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql://postgres:2210@localhost:5433/meeting_dbs` | PostgreSQL connection |
| `SECRET_KEY` | `a3f8b2...` (32 hex chars) | JWT signing key |
| `GEMINI_API_KEY` | `AIzaSy...` | AI extraction + embeddings |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker + cache + rate limit |

### Required for audio transcription (choose one)

| Variable | Value | Purpose |
|----------|-------|---------|
| `USE_LOCAL_WHISPER` | `true` | Use local faster-whisper |
| `WHISPER_MODEL_SIZE` | `base` | Whisper model size (tiny/base/small/medium) |
| `COLAB_API_URL` | `https://xxxx.ngrok-free.app` | Use Colab Whisper API |
| `USE_AWS_TRANSCRIBE` | `true` | Use AWS Transcribe service |

### Auth settings

| Variable | Default | Purpose |
|----------|---------|---------|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime |

### CORS + deployment

| Variable | Example | Purpose |
|----------|---------|---------|
| `CORS_ORIGINS` | `https://myapp.onrender.com` | Allowed frontend origins (comma-separated, or `*`) |
| `FRONTEND_URL` | `https://myapp.onrender.com` | Used in OAuth redirect URIs |
| `BACKEND_URL` | `https://myapi.onrender.com` | Used in OAuth redirect URIs |

### LLM caching

| Variable | Default | Purpose |
|----------|---------|---------|
| `LLM_CACHE_ENABLED` | `true` | Enable LRU + Redis LLM response caching |
| `LLM_CACHE_TTL` | `3600` | Cache entry lifetime in seconds |

### Optional — enables specific features

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | Enables GPT-4o as secondary LLM provider |
| `AWS_REGION` | AWS region (default: ap-south-1) |
| `AWS_ACCESS_KEY_ID` | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials |
| `TRANSCRIBE_BUCKET` | S3 bucket for AWS Transcribe |
| `SNS_TOPIC_ARN` | AWS SNS push notifications |
| `GOOGLE_CLIENT_ID/SECRET` | Google Calendar/Meet/Tasks OAuth |
| `ZOOM_CLIENT_ID/SECRET` | Zoom OAuth + webhook receiver |
| `AZURE_CLIENT_ID/SECRET` | Microsoft Teams OAuth |
| `TRELLO_API_KEY/SECRET` | Trello task sync |
| `NOTION_CLIENT_ID/SECRET` | Notion sync |
| `JIRA_CLIENT_ID/SECRET` | Jira integration |
| `ACTIVEPIECES_WEBHOOK_URL` | Post-processing automation |
| `ACTIVEPIECES_SECRET` | HMAC webhook verification |
| `CLAMAV_SOCKET` | ClamAV path for malware scanning |
| `FLOWER_USER/PASSWORD` | Celery monitoring UI credentials |
