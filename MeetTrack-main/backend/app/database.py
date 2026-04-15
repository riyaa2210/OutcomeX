from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.app.settings import DATABASE_URL
import os
DATABASE_URL = os.getenv("DATABASE_URL")

if "localhost" in DATABASE_URL:
    # Local PostgreSQL (NO SSL)
    engine = create_engine(DATABASE_URL)
else:
    # Render PostgreSQL (SSL REQUIRED)
    engine = create_engine(
        DATABASE_URL,
        connect_args={"sslmode": "require"}
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()