"""SAP AI Core: the AI API for model lifecycle (read-only here).

Uses the same credentials as the Generative AI Hub provider in llm.py: a bound
"aicore" service, or AICORE_AUTH_URL / AICORE_CLIENT_ID / AICORE_CLIENT_SECRET /
AICORE_BASE_URL. Calls documented AI API endpoints under /v2/lm/ in the
resource group AICORE_RESOURCE_GROUP (default "default").

SAP AI Launchpad is the SAP user interface on top of this same API; it has no
API of its own for the app to call. Anything shown here can also be managed
there.
"""
from __future__ import annotations

import os

from . import btp


def creds() -> dict:
    c = btp.binding("aicore") or {}
    return {
        "auth_url": os.getenv("AICORE_AUTH_URL") or c.get("url"),
        "client_id": os.getenv("AICORE_CLIENT_ID") or c.get("clientid"),
        "client_secret": os.getenv("AICORE_CLIENT_SECRET") or c.get("clientsecret"),
        "base": os.getenv("AICORE_BASE_URL") or (c.get("serviceurls") or {}).get("AI_API_URL"),
        "group": os.getenv("AICORE_RESOURCE_GROUP", "default"),
        "deployment": os.getenv("AICORE_DEPLOYMENT_ID"),
    }


def configured() -> bool:
    c = creds()
    return all([c["auth_url"], c["client_id"], c["client_secret"], c["base"]])


def _token(c: dict) -> str:
    url = c["auth_url"].rstrip("/")
    return btp.client_credentials_token(url if url.endswith("/oauth/token") else url + "/oauth/token", c["client_id"], c["client_secret"])


def get(path: str, timeout: float = 12) -> tuple[int, dict | str]:
    c = creds()
    tok = _token(c)
    return btp.http_json("GET", c["base"].rstrip("/") + path, headers={"Authorization": f"Bearer {tok}", "AI-Resource-Group": c["group"]},
                         timeout=timeout)


def overview() -> dict:
    """Scenarios, configurations, deployments and executions in the resource group."""
    if not configured():
        return {"configured": False}
    out = {"configured": True, "resource_group": creds()["group"]}
    for key, p in (("scenarios", "/v2/lm/scenarios"), ("configurations", "/v2/lm/configurations"),
                   ("deployments", "/v2/lm/deployments"), ("executions", "/v2/lm/executions")):
        try:
            code, body = get(p)
        except Exception as e:  # network or sign-in failure
            out[key] = {"error": f"{type(e).__name__}: {e}"}
            continue
        out[key] = {"count": body.get("count"), "items": body.get("resources", [])[:50]} if code == 200 and isinstance(body, dict) \
            else {"error": f"HTTP {code}", "detail": body if isinstance(body, str) else body}
    return out
