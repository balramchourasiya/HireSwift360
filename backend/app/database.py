import os
from pathlib import Path
from typing import Mapping
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def configured_database_url(environ: Mapping[str, str]) -> str:
    url = (
        environ.get("DATABASE_URL")
        or environ.get("POSTGRES_URL")
        or environ.get("POSTGRES_URL_NON_POOLING")
    )
    if not url and environ.get("VERCEL") == "1":
        raise RuntimeError(
            "No PostgreSQL database is configured for Vercel. "
            "Set DATABASE_URL or connect a Vercel Postgres integration that provides POSTGRES_URL."
        )
    return normalize_database_url(url or "sqlite:///./hireswift.db")


DATABASE_URL = configured_database_url(os.environ)
if os.getenv("VERCEL") == "1" and DATABASE_URL.startswith("sqlite"):
    raise RuntimeError(
        "Vercel requires a persistent PostgreSQL database. "
        "Set DATABASE_URL to your provider's PostgreSQL connection string."
    )
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
