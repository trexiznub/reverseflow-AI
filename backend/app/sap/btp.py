"""Reading SAP BTP service bindings.

On Cloud Foundry, services bound to the app (XSUAA, HANA Cloud, AI Core,
Destination) arrive as JSON in the VCAP_SERVICES environment variable. Locally
the same credentials can be given as plain environment variables.
"""
from __future__ import annotations

import gzip
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


def vcap() -> dict:
    try:
        return json.loads(os.getenv("VCAP_SERVICES", "") or "{}")
    except ValueError:
        return {}


def binding(*labels: str) -> dict | None:
    """Credentials of the first bound service whose label (or tag) matches."""
    services = vcap()
    for label in labels:
        for inst in services.get(label, []):
            return inst.get("credentials") or {}
    for insts in services.values():
        for inst in insts:
            if any(t in labels for t in inst.get("tags", [])):
                return inst.get("credentials") or {}
    return None


def on_cloud_foundry() -> bool:
    return bool(os.getenv("VCAP_APPLICATION"))


def app_info() -> dict:
    try:
        return json.loads(os.getenv("VCAP_APPLICATION", "") or "{}")
    except ValueError:
        return {}


# ---------------- OAuth client-credentials tokens (cached) ----------------
_tokens: dict[tuple, tuple[str, float]] = {}
_lock = threading.Lock()


def client_credentials_token(token_url: str, client_id: str, client_secret: str, timeout: float = 10) -> str:
    """Fetch (and cache until shortly before expiry) an OAuth access token."""
    key = (token_url, client_id)
    with _lock:
        hit = _tokens.get(key)
        if hit and hit[1] > time.time() + 30:
            return hit[0]
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": client_id,
                                   "client_secret": client_secret}).encode()
    req = urllib.request.Request(token_url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded",
                                                                 "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    tok = data["access_token"]
    with _lock:
        _tokens[key] = (tok, time.time() + float(data.get("expires_in", 600)))
    return tok


def _text(body: bytes, headers) -> str:
    """Response body as text. Some SAP gateways (the Business Accelerator Hub
    sandbox, for one) compress replies even when not asked to."""
    if (headers.get("Content-Encoding", "") if headers else "").lower() == "gzip" or body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return body.decode(errors="replace")


def http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None, timeout: float = 15) -> tuple[int, dict | str]:
    h = {"Accept": "application/json", **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body, default=str).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = _text(r.read(), r.headers)
            code = r.status
    except urllib.error.HTTPError as e:  # keep the SAP error text for the outbox
        raw = _text(e.read(), e.headers)
        code = e.code
    try:
        return code, json.loads(raw) if raw else {}
    except ValueError:
        return code, raw[:2000]
