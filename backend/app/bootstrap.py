"""First-run setup: generate synthetic data, train models, run the first agent cycle."""
from __future__ import annotations

import gzip
import os
import pickle
import shutil
import threading
from pathlib import Path

from sqlalchemy import inspect, select

from . import models as m
from .db import BASE_DIR, DATABASE_URL, SessionLocal, engine

# A prepared copy of the demo (database + trained models), built by
# `python -m app.seed.snapshot`. Restoring it takes seconds, whereas generating
# the data and training the models takes minutes on a small free server.
SNAPSHOT_DIR = BASE_DIR / "snapshot"
SNAPSHOT_DB = SNAPSHOT_DIR / "reverseflow.db.gz"
SNAPSHOT_MODELS = SNAPSHOT_DIR / "models.pkl.gz"

_ready = threading.Event()
_status = {"state": "starting", "detail": ""}


def status() -> dict:
    return dict(_status, ready=_ready.is_set())


def _db_populated() -> bool:
    if not inspect(engine).has_table("returns"):
        return False
    with SessionLocal() as db:
        return db.scalar(select(m.Return.id).limit(1)) is not None


def _sqlite_path() -> Path | None:
    if not DATABASE_URL.startswith("sqlite:///"):
        return None
    return Path(DATABASE_URL.removeprefix("sqlite:///"))


def snapshot_available() -> bool:
    return (SNAPSHOT_DB.exists() and _sqlite_path() is not None
            and os.getenv("REVERSEFLOW_NO_SNAPSHOT") != "1")


def _restore_snapshot():
    """Replace the SQLite database with the prepared copy."""
    path = _sqlite_path()
    engine.dispose()
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".restoring")
    with gzip.open(SNAPSHOT_DB, "rb") as src, open(tmp, "wb") as dst:
        shutil.copyfileobj(src, dst, 1 << 20)
    tmp.replace(path)
    engine.dispose()
    _add_missing_tables()


def _add_missing_tables():
    """Create tables added after a database (or snapshot) was made, such as the SAP outbox."""
    m.Base.metadata.create_all(engine)


def _load_models() -> bool:
    """Load the models trained when the snapshot was built. False if unusable."""
    import sklearn
    from .ml import anomaly, nlp
    if not SNAPSHOT_MODELS.exists():
        return False
    try:
        with gzip.open(SNAPSHOT_MODELS, "rb") as f:
            blob = pickle.load(f)
        if blob.get("sklearn") != sklearn.__version__:
            return False
        nlp._reason_model, nlp._sentiment_model, nlp._metrics = blob["reason"], blob["sentiment"], blob["metrics"]
        anomaly._model, anomaly._ref_scores = blob["anomaly"], blob["anomaly_ref"]
        return True
    except Exception:
        return False


def save_models(path: Path = SNAPSHOT_MODELS):
    import sklearn
    from .ml import anomaly, nlp
    blob = {"sklearn": sklearn.__version__, "reason": nlp._reason_model, "sentiment": nlp._sentiment_model, "metrics": nlp._metrics,
            "anomaly": anomaly._model, "anomaly_ref": anomaly._ref_scores}
    with gzip.open(path, "wb", compresslevel=9) as f:
        pickle.dump(blob, f, protocol=pickle.HIGHEST_PROTOCOL)


def _from_snapshot():
    """Restore the prepared demo and its models (training only if the models can't be loaded)."""
    from .agents import prediction
    from .ml import anomaly, nlp
    _status.update(state="generating", detail="Loading the prepared demo data")
    prediction.invalidate()
    nlp._reason_model = None
    anomaly._model = None
    _restore_snapshot()
    if not _load_models():
        _status.update(state="training", detail="Training NLP models")
        with SessionLocal() as db:
            nlp.train(db)
            anomaly.train(db)
    _status.update(state="ready", detail="")


def reset(regenerate: bool = True):
    from .agents import prediction
    from .ml import anomaly, nlp
    from .orchestrator import run_sync
    from .seed.generate import generate
    _ready.clear()
    try:
        if regenerate and snapshot_available():
            _from_snapshot()
            return
        if regenerate:
            _status.update(state="generating", detail="Generating synthetic dataset")
            prediction.invalidate()
            nlp._reason_model = None
            anomaly._model = None
            generate(verbose=False)
        _status.update(state="training", detail="Training NLP models")
        with SessionLocal() as db:
            nlp.train(db)
            nlp.score_all(db)
            anomaly.train(db)
        _status.update(state="orchestrating", detail="Running first six-agent cycle")
        run_sync("full_cycle", {"source": "bootstrap"})
        _status.update(state="ready", detail="")
    except Exception as e:  # pragma: no cover
        _status.update(state="error", detail=f"{type(e).__name__}: {e}")
        raise
    finally:
        _ready.set()


def ensure_ready():
    from .ml import anomaly, nlp
    if not _db_populated():
        reset(regenerate=True)  # restores the prepared copy when there is one
        return
    _add_missing_tables()
    with SessionLocal() as db:
        nlp.train(db)
        anomaly.train(db)
        if db.scalar(select(m.OrchestratorRun.id).limit(1)) is None:
            from .orchestrator import run_sync
            run_sync("full_cycle", {"source": "bootstrap"})
    _status.update(state="ready")
    _ready.set()
