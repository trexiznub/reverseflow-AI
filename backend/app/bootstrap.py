"""First-run setup: generate synthetic data, train models, run the first agent cycle."""
from __future__ import annotations

import threading

from sqlalchemy import inspect, select

from . import models as m
from .db import SessionLocal, engine

_ready = threading.Event()
_status = {"state": "starting", "detail": ""}


def status() -> dict:
    return dict(_status, ready=_ready.is_set())


def _db_populated() -> bool:
    if not inspect(engine).has_table("returns"):
        return False
    with SessionLocal() as db:
        return db.scalar(select(m.Return.id).limit(1)) is not None


def reset(regenerate: bool = True):
    from .agents import prediction
    from .ml import anomaly, nlp
    from .orchestrator import run_sync
    from .seed.generate import generate
    _ready.clear()
    try:
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
        reset(regenerate=True)
        return
    with SessionLocal() as db:
        nlp.train(db)
        anomaly.train(db)
        if db.scalar(select(m.OrchestratorRun.id).limit(1)) is None:
            from .orchestrator import run_sync
            run_sync("full_cycle", {"source": "bootstrap"})
    _status.update(state="ready")
    _ready.set()
