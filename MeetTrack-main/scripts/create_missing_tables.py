"""
Run this script to create any missing tables in the database.
Usage: python scripts/create_missing_tables.py
"""
import os
import sys
from pathlib import Path

# Load .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.database import Base, engine
from backend.app.auth import RefreshToken  # noqa
from backend.security.audit_log import SecurityAuditLog  # noqa
from backend.models import *  # noqa
from backend.services.llm.metrics import LLMCallLog  # noqa
from backend.models.evaluation import EvalResult, HumanFeedback, BenchmarkSample  # noqa
from backend.models.integration import OAuthToken, IntegrationAuditLog, ExternalMeeting  # noqa
from backend.models.task_log import TaskLog  # noqa

import sqlalchemy
from sqlalchemy import text

print("Creating missing tables...")

# Enable pgvector if available
try:
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
    print("pgvector extension: OK")
except Exception as e:
    print(f"pgvector: {e} (non-fatal)")

# Create all tables, skipping existing ones
tables_created = []
for table in Base.metadata.sorted_tables:
    try:
        table.create(engine, checkfirst=True)
        tables_created.append(table.name)
    except Exception as e:
        print(f"  {table.name}: {e}")

print(f"\nDone. Tables processed: {len(tables_created)}")
for t in tables_created:
    print(f"  ✓ {t}")
