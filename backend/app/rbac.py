"""Role-based access. Demo identity comes from the X-User-Id header (persona switcher).

In production this would be replaced by SAP BTP XSUAA / IAS JWTs; the role and
scope model stays the same.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from . import models as m
from .db import get_db

INTERNAL = {"ops_manager", "vendor_quality_manager", "warehouse_manager", "dispute_reviewer"}
PARTNER = {"vendor", "logistics", "warehouse"}

# Navigation each role may open (frontend uses this, backend enforces per endpoint)
PAGES = {
    "ops_manager": ["overview", "customer", "partners", "agents", "forecasting", "twin", "root-cause", "recovery", "governance", "analytics", "settings"],
    "vendor_quality_manager": ["overview", "agents", "forecasting", "root-cause", "governance", "analytics", "settings"],
    "warehouse_manager": ["overview", "partners", "agents", "twin", "recovery", "governance", "analytics", "settings"],
    "dispute_reviewer": ["overview", "governance", "settings"],
    "vendor": ["partners", "settings"],
    "logistics": ["partners", "settings"],
    "warehouse": ["partners", "settings"],
    "customer": ["customer", "settings"],
}


def current_user(x_user_id: str | None = Header(default=None), db: Session = Depends(get_db)) -> m.User:
    uid = x_user_id or "U-RAHUL"
    u = db.get(m.User, uid)
    if not u:
        raise HTTPException(401, f"Unknown user {uid}")
    return u


def require(*roles: str):
    allowed = set()
    for r in roles:
        allowed |= INTERNAL if r == "internal" else {r}

    def dep(user: m.User = Depends(current_user)) -> m.User:
        if user.role not in allowed:
            raise HTTPException(403, f"Role '{user.role}' cannot access this resource")
        return user
    return dep
