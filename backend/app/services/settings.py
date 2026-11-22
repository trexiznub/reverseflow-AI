from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from .. import models as m
from ..reference import SCENARIO_DATE


def get(db: Session, key: str, default=None):
    s = db.get(m.Setting, key)
    return s.value if s else default


def put(db: Session, key: str, value):
    s = db.get(m.Setting, key)
    if s:
        s.value = value
    else:
        db.add(m.Setting(key=key, value=value))
    db.commit()


def scenario_date(db: Session) -> date:
    v = get(db, "scenario", {}) or {}
    return date.fromisoformat(v.get("scenario_date", SCENARIO_DATE.isoformat()))


def network_scale(db: Session) -> dict:
    return (get(db, "scenario", {}) or {}).get("network_scale", {})


def routing_overrides(db: Session) -> dict:
    return get(db, "routing_overrides", {}) or {}


def capacity_overrides(db: Session) -> dict:
    return get(db, "capacity_overrides", {}) or {}
