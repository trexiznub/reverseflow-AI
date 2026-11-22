"""Build the prepared demo snapshot shipped with the code.

    cd backend && .venv/bin/python -m app.seed.snapshot

Generates the synthetic dataset into a temporary database, trains the models,
runs the first six-agent cycle, then writes:

    backend/snapshot/reverseflow.db.gz   compressed SQLite database
    backend/snapshot/models.pkl.gz       trained NLP + anomaly models

On a fresh server the backend restores these in seconds instead of rebuilding
everything (which takes minutes on a small free instance). Re-run this script
after changing the generator, the agents or the explanation wording.
"""
from __future__ import annotations

import gzip
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path


def main():
    tmpdir = Path(tempfile.mkdtemp(prefix="rf-snapshot-"))
    db_path = tmpdir / "reverseflow.db"
    # The engine is created at import time from DATABASE_URL, so set it first.
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["REVERSEFLOW_NO_SNAPSHOT"] = "1"

    from app import bootstrap
    from app.db import engine

    print("Generating data, training models and running the first agent cycle…")
    bootstrap.reset(regenerate=True)
    if bootstrap.status()["state"] != "ready":
        sys.exit(f"Bootstrap failed: {bootstrap.status()}")
    engine.dispose()

    con = sqlite3.connect(db_path)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.execute("PRAGMA journal_mode=DELETE")
    con.execute("VACUUM")
    con.close()

    out = bootstrap.SNAPSHOT_DIR
    out.mkdir(exist_ok=True)
    with open(db_path, "rb") as src, gzip.open(out / "reverseflow.db.gz", "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst, 1 << 20)
    bootstrap.save_models(out / "models.pkl.gz")
    shutil.rmtree(tmpdir, ignore_errors=True)
    for f in sorted(out.iterdir()):
        print(f"  {f.relative_to(out.parent)}  {f.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
