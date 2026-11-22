"""Database engine and session management.

SQLite is used for the local prototype. All models use portable SQLAlchemy types
(no SQLite-specific features), so the same schema can be pointed at PostgreSQL
or SAP HANA Cloud (via sqlalchemy-hana) by changing DATABASE_URL.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = f"sqlite:///{BASE_DIR / 'data' / 'reverseflow.db'}"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB)

if DATABASE_URL.startswith("sqlite"):
    (BASE_DIR / "data").mkdir(exist_ok=True)
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - driver hook
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
else:  # pragma: no cover
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
