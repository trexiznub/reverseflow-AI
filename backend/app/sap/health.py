"""Real connection tests for every SAP service the app can use.

A service is only shown as "connected" after a test in this process actually
reached it. The states are:

    connected        a test just reached the service and it answered correctly
    configured       credentials or a binding are present, but no test has run yet
    not_configured   nothing is set up for this service
    no_entitlement   the service answered 403: the account lacks the entitlement or role
    failed           the test ran and could not reach the service, or got an error

Results are kept in memory with the time of the test. A change of
configuration (for example a new URL) clears the old result.
"""
from __future__ import annotations

import os
import threading
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .. import models as m
from . import aicore, btp, destinations, s4hana

_results: dict[str, dict] = {}
_lock = threading.Lock()


def _http_state(code: int) -> str:
    return "connected" if 200 <= code < 300 else "no_entitlement" if code == 403 else "failed"


def _result(state: str, detail: str) -> dict:
    return {"state": state, "detail": detail}


# ---------------- what is configured (no network) ----------------
def _cap_url() -> str | None:
    return os.getenv("CAP_URL") or None


def _sac() -> dict:
    return {k: os.getenv(f"SAC_{k.upper()}") for k in ("url", "token_url", "client_id", "client_secret")}


def config_signature(db: Session) -> dict:
    """For each service: a short string describing how it is set up, or None."""
    from ..rbac import _xsuaa_creds
    ai = aicore.creds()
    sac = _sac()
    return {
        "btp": "cloud-foundry" if btp.on_cloud_foundry() else None,
        "xsuaa": (_xsuaa_creds() or {}).get("url"),
        "destination": "bound" if btp.binding("destination") else None,
        "hana": "hana" if db.bind.dialect.name == "hana" else None,
        "cap": _cap_url(),
        "genai": f"{ai['base']}|{ai['deployment']}" if aicore.configured() and ai["deployment"] else None,
        "aicore": ai["base"] if aicore.configured() else None,
        "launchpad": os.getenv("AI_LAUNCHPAD_URL") or None,
        "s4": s4hana.configured(),
        "sac": sac["url"] if sac["url"] else None,
        "workzone": os.getenv("WORKZONE_SITE_URL") or None,
        **{s: destinations.configured(s) for s in destinations.SYSTEMS},
    }


# ---------------- the tests ----------------
def _t_btp(db):
    info = btp.app_info()
    return _result("connected", f"Running on Cloud Foundry as {info.get('application_name')} in space {info.get('space_name')}.")


def _t_xsuaa(db):
    from ..rbac import _xsuaa_creds
    code, body = btp.http_json("GET", _xsuaa_creds()["url"].rstrip("/") + "/token_keys", timeout=8)
    ok = code == 200 and isinstance(body, dict) and body.get("keys")
    return _result("connected" if ok else "failed", "Signing keys fetched from XSUAA." if ok else f"XSUAA answered {code}.")


def _t_destination(db):
    c = btp.binding("destination")
    tok = btp.client_credentials_token(c["url"].rstrip("/") + "/oauth/token", c["clientid"], c["clientsecret"])
    code, body = btp.http_json("GET", c["uri"].rstrip("/") + "/destination-configuration/v1/subaccountDestinations",
                               headers={"Authorization": f"Bearer {tok}"}, timeout=8)
    if code == 200 and isinstance(body, list):
        names = sorted(d.get("Name", "") for d in body if str(d.get("Name", "")).startswith("reverseflow-"))
        return _result("connected", f"Destination service reached. ReverseFlow destinations: {', '.join(names) or 'none yet'}.")
    return _result(_http_state(code), f"Destination service answered {code}.")


def _t_hana(db):
    v = db.execute(text("SELECT VERSION FROM SYS.M_DATABASE")).scalar()
    n = db.scalar(select(m.Return.id).limit(1))
    return _result("connected", f"SAP HANA Cloud {v}. App tables readable{'' if n else ' (no returns yet)'}.")


def _t_cap(db):
    code, body = btp.http_json("GET", _cap_url().rstrip("/") + "/health", timeout=8)
    if code == 200 and isinstance(body, dict) and body.get("status") == "UP":
        return _result("connected", f"CAP business service is up ({body.get('service', 'reverseflow-business-service')}, database {body.get('db')}).")
    return _result("failed", f"CAP answered {code}.")


def _t_genai(db):
    dep = aicore.creds()["deployment"]
    code, body = aicore.get(f"/v2/lm/deployments/{dep}", timeout=10)
    if code == 200 and isinstance(body, dict):
        status = body.get("status")
        res = (body.get("details") or {}).get("resources") or {}
        model = ((res.get("backend_details") or res.get("backendDetails") or {}).get("model") or {}).get("name")
        return _result("connected" if status == "RUNNING" else "failed",
                       f"Deployment {dep} is {status}{f' ({model})' if model else ''}.")
    return _result(_http_state(code), f"AI Core answered {code} for deployment {dep}.")


def _t_aicore(db):
    code, body = aicore.get("/v2/lm/scenarios", timeout=10)
    if code == 200 and isinstance(body, dict):
        return _result("connected", f"AI API reached: {body.get('count', 0)} scenarios in resource group {aicore.creds()['group']}.")
    return _result(_http_state(code), f"AI Core answered {code}.")


def _t_s4(db):
    conn = destinations.resolve("s4")
    if not conn:
        return _result("failed", "S/4HANA is configured but the destination could not be read.")
    code, body = btp.http_json("GET", conn.url.rstrip("/") + s4hana.path("products") + "?$top=1&$format=json", headers=conn.headers, timeout=15)
    if code == 200 and isinstance(body, dict) and "__sandbox" in body:
        return _result("configured", "SAP_S4_URL points at ReverseFlow's own test sandbox, not an S/4HANA system. The adapter works; S/4HANA is not connected.")
    if code == 200 and isinstance(body, dict) and "d" in body:
        n = len((body.get("d") or {}).get("results", []))
        return _result("connected", f"Product API answered through {conn.source} and returned readable OData ({n} record).")
    if code == 200:
        return _result("failed", "S/4HANA answered, but not with readable OData JSON. Check SAP_S4_URL points at the host part only.")
    return _result(_http_state(code), f"S/4HANA answered {code} for {s4hana.path('products')}.")


def _t_sac(db):
    s = _sac()
    if not (s["token_url"] and s["client_id"]):
        return _result("configured", "SAC_URL is set but no OAuth client (SAC_TOKEN_URL, SAC_CLIENT_ID, SAC_CLIENT_SECRET), so it can't be tested.")
    tok = btp.client_credentials_token(s["token_url"], s["client_id"], s["client_secret"] or "")
    code, body = btp.http_json("GET", s["url"].rstrip("/") + "/api/v1/dataimport/models", headers={"Authorization": f"Bearer {tok}"}, timeout=12)
    if code == 200:
        n = len(body.get("models", [])) if isinstance(body, dict) else None
        return _result("connected", f"SAP Analytics Cloud data import API reached{f': {n} models' if n is not None else ''}.")
    return _result(_http_state(code), f"SAP Analytics Cloud answered {code}.")


def _t_workzone():
    """Open the Work Zone site URL and check it is a live SAP launchpad site.
    The tile on the site sits behind SAP sign-in, so it can't be checked from here."""
    import urllib.parse
    import urllib.request
    url = os.getenv("WORKZONE_SITE_URL", "")
    host = urllib.parse.urlparse(url).hostname or ""
    if not (host.endswith(".hana.ondemand.com") or host.endswith(".cloud.sap")):
        return _result("failed", "WORKZONE_SITE_URL is not an SAP BTP address (expected …launchpad.cfapps….hana.ondemand.com).")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    try:
        r = urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url, method="GET"), timeout=10)
        code, loc = r.status, ""
    except urllib.error.HTTPError as e:  # a redirect to SAP sign-in arrives here
        code, loc = e.code, e.headers.get("Location", "")
    if code == 200 or (code in (301, 302, 303, 307) and ("authentication" in loc or "login" in loc or "oauth" in loc or host in loc)):
        return _result("connected", f"Work Zone site is live at {host} (answered {code}{', sign-in required' if code != 200 else ''}). "
                                    "The tile itself sits behind SAP sign-in and is not checked.")
    return _result("failed", f"Work Zone site answered {code}.")


def _t_outbox_system(system):
    def t(db):
        last = db.scalars(select(m.SapMessage).where(m.SapMessage.system == system, m.SapMessage.last_attempt_at.is_not(None))
                          .order_by(m.SapMessage.last_attempt_at.desc())).first()
        if not last:
            return _result("configured", "Configured. No message has been sent yet; send one from the outbox to test it.")
        if last.status == "sent" and "Test receiver" in str(((last.response or {}).get("body") or {}).get("note", "")):
            return _result("configured", "The last message went to ReverseFlow's test receiver, not an SAP system. Sending works; the SAP system is not connected.")
        if last.status == "sent":
            return _result("connected", f"Last message accepted on {last.last_attempt_at:%d %b %H:%M}.")
        return _result("failed", f"Last send failed on {last.last_attempt_at:%d %b %H:%M}: {(last.response or {}).get('error') or (last.response or {}).get('http_status')}.")
    return t


def _untestable(what):
    return lambda db: _result("configured", what)


TESTS = {
    "btp": _t_btp, "xsuaa": _t_xsuaa, "destination": _t_destination, "hana": _t_hana, "cap": _t_cap,
    "genai": _t_genai, "aicore": _t_aicore, "s4": _t_s4, "sac": _t_sac,
    "launchpad": _untestable("SAP AI Launchpad is a user interface with no API to test. Open it from the link; it manages the same AI Core shown here."),
    "workzone": lambda db: _t_workzone(),
    **{s: _t_outbox_system(s) for s in destinations.SYSTEMS},
}


def current(db: Session) -> dict[str, dict]:
    """State of every service: the last test result if the setup hasn't changed since, else configured / not configured."""
    sig = config_signature(db)
    out = {}
    for sid, how in sig.items():
        r = _results.get(sid)
        if not how:
            out[sid] = {"state": "not_configured", "detail": None, "tested_at": None}
        elif r and r["signature"] == how:
            out[sid] = {k: r[k] for k in ("state", "detail", "tested_at")}
        else:
            out[sid] = {"state": "configured", "detail": None, "tested_at": None}
    return out


def run_tests(db_factory) -> dict[str, dict]:
    """Run every test for a configured service, in parallel, each with its own database session."""
    with db_factory() as db:
        sig = config_signature(db)

    def one(sid):
        with db_factory() as db:
            try:
                r = TESTS[sid](db)
            except Exception as e:
                r = _result("failed", f"{type(e).__name__}: {str(e)[:200]}")
        r["tested_at"] = datetime.now().isoformat(timespec="seconds")
        r["signature"] = sig[sid]
        with _lock:
            _results[sid] = r

    todo = [s for s, how in sig.items() if how and s in TESTS]
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(one, todo))
    with db_factory() as db:
        return current(db)


def clear():
    with _lock:
        _results.clear()
