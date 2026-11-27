"""Role-based access.

Two sign-in modes:

* Demo (default): the person is picked with the X-User-Id header (the persona
  switcher in the top bar).
* SAP BTP XSUAA: switches on when an XSUAA service is bound to the app on
  Cloud Foundry (or REVERSEFLOW_AUTH=xsuaa with XSUAA_* variables). Every API
  call then needs a valid XSUAA token, normally added by the SAP application
  router after the person signs in with SAP ID / IAS. The token's scopes decide
  the role (see xs-security.json). Operations managers may still switch
  persona to present the demo; everyone else is fixed to their own role.

The role and scope model is the same in both modes.
"""
from __future__ import annotations

import os
import threading

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .db import get_db
from .sap import btp

INTERNAL = {"ops_manager", "vendor_quality_manager", "warehouse_manager", "dispute_reviewer"}
PARTNER = {"vendor", "logistics", "warehouse"}

# Navigation each role may open (frontend uses this, backend enforces per endpoint)
PAGES = {
    "ops_manager": ["overview", "case", "customer", "partners", "agents", "forecasting", "twin", "root-cause", "recovery", "governance", "analytics", "sap", "settings"],
    "vendor_quality_manager": ["overview", "case", "agents", "forecasting", "root-cause", "governance", "analytics", "sap", "settings"],
    "warehouse_manager": ["overview", "case", "partners", "agents", "twin", "recovery", "governance", "analytics", "sap", "settings"],
    "dispute_reviewer": ["overview", "case", "governance", "settings"],
    "vendor": ["partners", "settings"],
    "logistics": ["partners", "settings"],
    "warehouse": ["partners", "settings"],
    "customer": ["customer", "settings"],
}

# XSUAA scope (without the "<xsappname>." prefix) -> role, strongest first
SCOPE_ROLE = [("OpsManager", "ops_manager"), ("VendorQuality", "vendor_quality_manager"), ("WarehouseManager", "warehouse_manager"),
              ("DisputeReviewer", "dispute_reviewer"), ("Vendor", "vendor"), ("Logistics", "logistics"),
              ("WarehousePartner", "warehouse"), ("Customer", "customer")]


def _xsuaa_creds() -> dict | None:
    c = btp.binding("xsuaa")
    if c:
        return c
    if os.getenv("REVERSEFLOW_AUTH") == "xsuaa" and os.getenv("XSUAA_URL"):
        return {"url": os.getenv("XSUAA_URL"), "xsappname": os.getenv("XSUAA_XSAPPNAME", "reverseflow"),
                "clientid": os.getenv("XSUAA_CLIENT_ID", "")}
    return None


def auth_mode() -> str:
    return "xsuaa" if _xsuaa_creds() else "demo"


_jwks = {}
_jwks_lock = threading.Lock()


def _verify(token: str) -> dict:
    import jwt  # PyJWT, only needed in XSUAA mode
    creds = _xsuaa_creds()
    url = creds["url"].rstrip("/") + "/token_keys"
    with _jwks_lock:
        client = _jwks.get(url) or _jwks.setdefault(url, jwt.PyJWKClient(url, cache_keys=True))
    key = client.get_signing_key_from_jwt(token).key
    claims = jwt.decode(token, key, algorithms=["RS256"], options={"verify_aud": False})
    app = creds.get("xsappname", "")
    claims["_scopes"] = {s.split(".", 1)[1] for s in claims.get("scope", []) if s.startswith(app + ".") and "." in s}
    return claims


def _user_for_claims(db: Session, claims: dict) -> m.User:
    role = next((r for s, r in SCOPE_ROLE if s in claims["_scopes"]), None)
    if not role:
        raise HTTPException(403, "Your SAP account has no ReverseFlow role. Ask an administrator to assign a role collection.")
    attrs = claims.get("xs.user.attributes") or {}
    scope_id = (attrs.get("scope_id") or [None])[0]
    q = select(m.User).where(m.User.role == role)
    if scope_id:
        q = q.where(m.User.scope_id == scope_id)
    u = db.scalars(q).first()
    if not u:
        raise HTTPException(403, f"No ReverseFlow profile for role {role}")
    return u


def current_user(x_user_id: str | None = Header(default=None), authorization: str | None = Header(default=None),
                 db: Session = Depends(get_db)) -> m.User:
    if auth_mode() == "xsuaa":
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "Sign in with your SAP account")
        try:
            claims = _verify(authorization.split(" ", 1)[1])
        except Exception:
            raise HTTPException(401, "Your SAP sign-in has expired or is not valid. Sign in again.")
        u = _user_for_claims(db, claims)
        if u.role == "ops_manager" and x_user_id and x_user_id != u.id:
            other = db.get(m.User, x_user_id)  # presenter switching persona for the demo
            if other:
                return other
        return u
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
