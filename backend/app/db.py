"""Database engine and session management.

SQLite is used by default. All models use portable SQLAlchemy types (no
SQLite-specific features), so the same schema runs on SAP HANA Cloud through
sqlalchemy-hana. The database is chosen in this order:

1. DATABASE_URL, for example hana://USER:PASSWORD@HOST:443?encrypt=true
2. a SAP HANA Cloud service bound to the app on SAP BTP Cloud Foundry
   (service "hana", plan "schema"; credentials arrive in VCAP_SERVICES)
3. the local SQLite file backend/data/reverseflow.db
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = f"sqlite:///{BASE_DIR / 'data' / 'reverseflow.db'}"


def _hana_url() -> str | None:
    from urllib.parse import quote_plus
    from .sap.btp import binding
    c = binding("hana", "hana-cloud")
    if not c or not c.get("host"):
        return None
    url = f"hana://{quote_plus(c['user'])}:{quote_plus(c['password'])}@{c['host']}:{c.get('port', 443)}?encrypt=true&sslValidateCertificate=true"
    if c.get("schema"):
        url += f"&currentSchema={quote_plus(c['schema'])}"
    return url


DATABASE_URL = os.getenv("DATABASE_URL") or _hana_url() or DEFAULT_DB

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
