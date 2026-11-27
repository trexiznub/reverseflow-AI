"""Where to send messages for each SAP system, and how to sign in to it.

Two ways to connect a system, checked in this order:

1. Environment variables, for example for SAP IBP:
       SAP_IBP_URL             endpoint that receives the message
       SAP_IBP_TOKEN_URL       OAuth token endpoint   } OAuth client
       SAP_IBP_CLIENT_ID                              } credentials
       SAP_IBP_CLIENT_SECRET                          }
   or  SAP_IBP_USER / SAP_IBP_PASSWORD for basic authentication,
   or  SAP_IBP_API_KEY for the SAP Business Accelerator Hub sandbox.

2. The SAP BTP Destination service, when it is bound to the app. The
   destination is looked up by name (default "reverseflow-ibp", or the value
   of SAP_IBP_DESTINATION). The Destination service handles sign-in, including
   principal propagation and Cloud Connector routes to on-premise systems.
"""
from __future__ import annotations

import base64
import os
import urllib.parse
from dataclasses import dataclass, field

from . import btp

SYSTEMS = ("ibp", "tm", "ariba")


@dataclass
class Connection:
    system: str
    url: str
    source: str  # "environment" or "destination:<name>"
    headers: dict = field(default_factory=dict)


def _env(system: str, key: str) -> str | None:
    return os.getenv(f"SAP_{system.upper()}_{key}") or None


def destination_name(system: str) -> str:
    return _env(system, "DESTINATION") or f"reverseflow-{system}"


def _from_env(system: str) -> Connection | None:
    url = _env(system, "URL")
    if not url:
        return None
    headers = {}
    if _env(system, "TOKEN_URL") and _env(system, "CLIENT_ID"):
        tok = btp.client_credentials_token(_env(system, "TOKEN_URL"), _env(system, "CLIENT_ID"), _env(system, "CLIENT_SECRET") or "")
        headers["Authorization"] = f"Bearer {tok}"
    elif _env(system, "API_KEY"):  # SAP Business Accelerator Hub sandbox
        headers["APIKey"] = _env(system, "API_KEY")
    elif _env(system, "USER"):
        pair = f"{_env(system, 'USER')}:{_env(system, 'PASSWORD') or ''}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(pair).decode()
    return Connection(system, url, "environment", headers)


def _from_destination_service(system: str) -> Connection | None:
    creds = btp.binding("destination")
    if not creds:
        return None
    name = destination_name(system)
    tok = btp.client_credentials_token(creds["url"].rstrip("/") + "/oauth/token", creds["clientid"], creds["clientsecret"])
    code, body = btp.http_json("GET", creds["uri"].rstrip("/") + "/destination-configuration/v1/destinations/" + urllib.parse.quote(name),
                               headers={"Authorization": f"Bearer {tok}"})
    if code != 200 or not isinstance(body, dict):
        return None
    cfg = body.get("destinationConfiguration") or {}
    headers = {}
    for t in body.get("authTokens") or []:
        if t.get("http_header"):
            headers[t["http_header"]["key"]] = t["http_header"]["value"]
        elif t.get("value"):
            headers["Authorization"] = f"{t.get('type', 'Bearer')} {t['value']}"
    if cfg.get("ProxyType") == "OnPremise":
        headers["SAP-Connectivity-Authentication"] = headers.get("Authorization", "")
    return Connection(system, cfg.get("URL", ""), f"destination:{name}", headers) if cfg.get("URL") else None


def resolve(system: str) -> Connection | None:
    """The live connection for a system, or None when it isn't connected."""
    return _from_env(system) or _from_destination_service(system)


def configured(system: str) -> str | None:
    """How a system would be reached, without signing in. None if not configured."""
    if _env(system, "URL"):
        return "environment"
    if btp.binding("destination"):
        return f"destination:{destination_name(system)}"
    return None
