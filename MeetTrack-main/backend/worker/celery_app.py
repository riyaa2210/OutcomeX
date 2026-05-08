"""
Celery Application — OutcomeX Distributed Task Queue
=====================================================

Broker  : Redis  (REDIS_URL env var)
Backend : Redis  (same URL, separate DB index)

Worker pools:
  - transcription   : concurrency=2  (I/O-bound, Colab API calls)
  - ai_extraction   : concurrency=4  (CPU-light, Gemini API calls)
  - email_delivery  : concurrency=8  (I/O-bound, fast)
  - analytics       : concurrency=2  (DB-heavy)
  - webhooks        : concurrency=4  (HTTP retries)

Start workers:
  celery -A backend.worker.celery_app worker -Q transcription,ai_extraction,email_delivery,analytics,webhooks --loglevel=info
  celery -A backend.worker.celery_app flower --port=5555   # monitoring UI
"""

import os
from celery import Celery
from kombu import Queue, Exchange

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── App ───────────────────────────────────────────────────────────────────────
celery_app = Celery(
    "outcomex",
    broker=REDIS_URL,
    backend=REDIS_URL.replace("/0", "/1"),  # separate DB for results
    include=[
        "backend.worker.tasks.transcription_tasks",
        "backend.worker.tasks.ai_tasks",
        "backend.worker.tasks.email_tasks",
        "backend.worker.tasks.analytics_tasks",
        "backend.worker.tasks.webhook_tasks",
    ],
)

# ── Queues ────────────────────────────────────────────────────────────────────
default_exchange = Exchange("outcomex", type="direct")

celery_app.conf.task_queues = (
    Queue("transcription",  default_exchange, routing_key="transcription"),
    Queue("ai_extraction",  default_exchange, routing_key="ai_extraction"),
    Queue("email_delivery", default_exchange, routing_key="email_delivery"),
    Queue("analytics",      default_exchange, routing_key="analytics"),
    Queue("webhooks",       default_exchange, routing_key="webhooks"),
    Queue("dead_letter",    default_exchange, routing_key="dead_letter"),
)

celery_app.conf.task_default_queue    = "ai_extraction"
celery_app.conf.task_default_exchange = "outcomex"
celery_app.conf.task_default_routing_key = "ai_extraction"

# ── Routing ───────────────────────────────────────────────────────────────────
celery_app.conf.task_routes = {
    "backend.worker.tasks.transcription_tasks.*": {"queue": "transcription"},
    "backend.worker.tasks.ai_tasks.*":            {"queue": "ai_extraction"},
    "backend.worker.tasks.email_tasks.*":         {"queue": "email_delivery"},
    "backend.worker.tasks.analytics_tasks.*":     {"queue": "analytics"},
    "backend.worker.tasks.webhook_tasks.*":       {"queue": "webhooks"},
}

# ── Serialization ─────────────────────────────────────────────────────────────
celery_app.conf.task_serializer   = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content    = ["json"]

# ── Timeouts ──────────────────────────────────────────────────────────────────
celery_app.conf.task_soft_time_limit = 300   # 5 min soft limit → SoftTimeLimitExceeded
celery_app.conf.task_time_limit      = 360   # 6 min hard kill

# ── Retry defaults ────────────────────────────────────────────────────────────
celery_app.conf.task_acks_late          = True   # ack only after success
celery_app.conf.task_reject_on_worker_lost = True

# ── Result expiry ─────────────────────────────────────────────────────────────
celery_app.conf.result_expires = 60 * 60 * 24  # 24 hours

# ── Concurrency ───────────────────────────────────────────────────────────────
celery_app.conf.worker_prefetch_multiplier = 1   # fair dispatch

# ── Beat schedule (periodic tasks) ───────────────────────────────────────────
celery_app.conf.beat_schedule = {
    "retry-failed-webhooks-every-10min": {
        "task":     "backend.worker.tasks.webhook_tasks.retry_dead_letter_webhooks",
        "schedule": 600,  # every 10 minutes
    },
    "cleanup-old-task-logs-daily": {
        "task":     "backend.worker.tasks.analytics_tasks.cleanup_old_task_logs",
        "schedule": 86400,  # every 24 hours
    },
}

celery_app.conf.timezone = "UTC"
