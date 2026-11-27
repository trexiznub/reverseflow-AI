"""Messages for SAP systems, prepared from approved decisions and forecasts.

Which decision goes where:

    SAP IBP   return forecast by city and day (returns as incoming supply);
              items fast-tracked or repaired for resale (recovered stock)
    SAP TM    extra pickup vans (a transportation request to the carrier);
              sending a share of a city's returns to another warehouse
    Ariba     quality holds, size-chart and listing fixes for a seller
              (a quality notification on SAP Business Network)

Each message is a self-contained JSON document. It is posted to the system's
connection (see destinations.py). In a typical SAP landscape that endpoint is
an SAP Integration Suite flow, which maps the document to the target API
(IBP planning data API, TM freight unit / order APIs, Ariba cXML).

Delivery rules:
  * Master data is checked first (cities, warehouses, carriers, sellers, SKUs
    must exist). A message that fails the check is "blocked" and never sent.
  * One message per decision and system: approving or publishing the same thing
    twice returns the existing message instead of creating a duplicate.
  * Every send carries the message id as an Idempotency-Key header, so a
    receiver can drop a repeat of a message it already processed.
  * A 2xx answer counts as acknowledged; any id the receiver returns is kept.
  * Network errors, 408, 429 and 5xx are retried with growing waits (1, 2, 4,
    8 minutes), up to 5 attempts. Other 4xx answers are rejections: not retried.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import destinations

LABEL = {"ibp": "SAP Integrated Business Planning", "tm": "SAP Transportation Management", "ariba": "SAP Ariba / Business Network"}

MAX_ATTEMPTS = 5
TRANSIENT = {408, 429, 500, 502, 503, 504}
STATUSES = ("waiting", "sent", "failed", "blocked")

TM_KINDS = {"extra_pickup", "reroute"}
ARIBA_KINDS = {"vendor_qc_hold", "pre_dispatch_qc", "size_chart_update", "listing_fix"}
IBP_KINDS = {"rapid_restock", "refurbish_batch"}


def _id() -> str:
    return "SAP-" + uuid.uuid4().hex[:12].upper()


def _envelope(system: str, kind: str, source_id: str, actor: str) -> dict:
    return {"messageId": None, "sender": "REVERSEFLOW", "receiver": system.upper(), "messageType": kind,
            "createdAt": datetime.now().isoformat(timespec="seconds"), "approvedBy": actor, "sourceDecision": source_id,
            "demoData": True}


def _planning_area() -> str:
    return os.getenv("SAP_IBP_PLANNING_AREA", "RFRETURNS")


# ---------------- builders ----------------
def _tm(db: Session, r: m.Recommendation, actor: str) -> tuple[str, dict] | None:
    ev = r.evidence or {}
    if r.kind == "extra_pickup":
        gap = ev.get("gap", {})
        cluster = db.get(m.PinCluster, r.entity_id)
        start = datetime.now().date()
        doc = {**_envelope("tm", "TransportationRequest", r.id, actor),
               "transportationRequest": {
                   "type": "RETURN_PICKUP_CAPACITY", "carrier": {"id": ev.get("provider_id"), "name": gap.get("provider")},
                   "sourceZone": {"id": r.entity_id, "name": gap.get("city"), "postalPrefix": getattr(cluster, "pin_prefix", None)},
                   "destinationLocation": getattr(cluster, "default_facility_id", None),
                   "vehicles": ev.get("vehicles"), "days": ev.get("days"),
                   "validFrom": start.isoformat(), "validTo": (start + timedelta(days=int(ev.get("days") or 1) - 1)).isoformat(),
                   "plannedPickupsPerDay": gap.get("planning_volume"), "currentCapacityPerDay": gap.get("pickup_capacity"),
                   "agreedRatePerPickupINR": ev.get("unit_cost"), "estimatedCostINR": r.cost_inr}}
        return f"Book {ev.get('vehicles')} extra pickup vans in {gap.get('city', r.entity_id)} for {ev.get('days')} days", doc
    if r.kind == "reroute":
        a = ev.get("allocation", {})
        doc = {**_envelope("tm", "TransportationPlanChange", r.id, actor),
               "planChange": {"type": "RETURN_DESTINATION_SPLIT", "sourceZone": ev.get("cluster_id"),
                              "newDestinationLocation": a.get("facility_id"), "shareOfReturns": a.get("share"),
                              "unitsPerDay": a.get("units"), "distanceKm": a.get("km"), "days": ev.get("days"),
                              "costPerUnitINR": a.get("unit_cost"), "estimatedCostINR": r.cost_inr}}
        city = getattr(db.get(m.PinCluster, ev.get("cluster_id") or ""), "city", ev.get("cluster_id"))
        fac = getattr(db.get(m.Facility, a.get("facility_id") or ""), "city", a.get("facility_id"))
        return f"Send {round((a.get('share') or 0) * 100)}% of {city} returns to the {fac} warehouse", doc
    return None


def _ariba(db: Session, r: m.Recommendation, actor: str) -> tuple[str, dict] | None:
    ev = r.evidence or {}
    f = ev.get("finding", {})
    v = db.get(m.Vendor, r.entity_id)
    action = {"vendor_qc_hold": "HOLD_SHIPMENTS_UNTIL_QC_PASSED", "pre_dispatch_qc": "INSPECT_BEFORE_DISPATCH",
              "size_chart_update": "CORRECT_SIZE_CHART", "listing_fix": "CORRECT_LISTING"}[r.kind]
    doc = {**_envelope("ariba", "QualityNotification", r.id, actor),
           "qualityNotification": {
               "supplier": {"id": r.entity_id, "name": getattr(v, "name", f.get("vendor_name")), "city": getattr(v, "city", None)},
               "defect": {"code": f.get("reason"), "description": f.get("reason_label"),
                          "returnsWithDefect": f.get("returns"), "totalReturns": f.get("vendor_returns"),
                          "shareOfReturns": f.get("share"), "shareForOtherSellers": f.get("network_share")},
               "affectedItems": [{"sku": s.get("sku"), "description": s.get("name")} for s in f.get("top_skus", [])][:10],
               "requestedAction": action, "detail": r.rationale[:1000], "responseDueDays": 7}}
    return f"{action.replace('_', ' ').capitalize()} for {getattr(v, 'name', r.entity_id)}", doc


def _ibp_recovered(db: Session, r: m.Recommendation, actor: str) -> tuple[str, dict] | None:
    from ..services import settings as st
    ev = r.evidence or {}
    D = st.scenario_date(db)
    days = 3 if r.kind == "rapid_restock" else 7
    # Inspect-first items are not inspected yet: send the supply we expect after inspection (weighted by the
    # chance each passes as like-new), in a separate key figure, never as confirmed stock.
    expected = r.kind == "rapid_restock"
    rows = {}
    for it in ev.get("items", []):
        key = (it["sku"], it["facility_id"])
        rows[key] = rows.get(key, 0) + (float(it.get("p_grade_a", 0)) if expected else 1)
    kf = "EXPECTEDRECOVEREDSUPPLY" if expected else "RECOVEREDSUPPLY"
    doc = {**_envelope("ibp", "PlanningData", r.id, actor),
           "planningArea": _planning_area(), "keyFigure": kf,
           "aggregationLevel": ["PRDID", "LOCID", "PERIODID_DAY"],
           "rows": [{"PRDID": sku, "LOCID": loc, "PERIODID_DAY": (D + timedelta(days=days)).isoformat(), kf: round(n, 2)}
                    for (sku, loc), n in sorted(rows.items())]}
    if expected:
        doc["note"] = "Expected supply, not confirmed: each item must pass inspection before it is stock."
        return f"About {sum(rows.values()):.0f} items expected back in stock after inspection, in {days} days", doc
    return f"{sum(rows.values()):.0f} repaired items back in stock in {days} days", doc


def forecast_document(db: Session, actor: str) -> tuple[str, dict, str] | None:
    """The latest return forecast, as planning data for SAP IBP."""
    from ..agents.prediction import latest_forecast
    fc = latest_forecast(db)
    if not fc:
        return None
    clusters = {c.id: c for c in db.scalars(select(m.PinCluster)).all()}
    rows = []
    for c in fc["clusters"]:
        loc = getattr(clusters.get(c["cluster_id"]), "default_facility_id", None) or c["cluster_id"]
        for p in c["forecast"]:
            rows.append({"PRDID": "FESTIVE-FASHION-RETURNS", "CUSTID": c["cluster_id"], "LOCID": loc, "PERIODID_DAY": p["day"],
                         "RETURNSFORECAST": p["network_forecast"], "RETURNSFORECAST_P10": p["network_lo"],
                         "RETURNSFORECAST_P90": p["network_hi"]})
    source = f"forecast:{fc.get('origin')}"
    doc = {**_envelope("ibp", "PlanningData", source, actor),
           "planningArea": _planning_area(), "keyFigure": "RETURNSFORECAST",
           "aggregationLevel": ["PRDID", "CUSTID", "LOCID", "PERIODID_DAY"],
           "forecastOrigin": fc.get("origin"), "horizonDays": fc.get("horizon_days"), "rows": rows}
    return f"Return forecast for {len(fc['clusters'])} cities, next {fc.get('horizon_days')} days", doc, source


# ---------------- master data ----------------
def validate(db: Session, doc: dict, r: m.Recommendation | None = None) -> list[str]:
    """Check that every master-data reference in a message exists. Returns the problems found."""
    problems = []

    def need(model, key, what):
        if key and not db.get(model, key):
            problems.append(f"Unknown {what} '{key}'")

    if r is not None:
        ev = r.evidence or {}
        if r.kind == "extra_pickup":
            need(m.PinCluster, r.entity_id, "city cluster")
            need(m.LogisticsProvider, ev.get("provider_id"), "carrier")
        elif r.kind == "reroute":
            need(m.PinCluster, ev.get("cluster_id"), "city cluster")
            need(m.Facility, ev.get("facility_id"), "warehouse")
        elif r.kind in ARIBA_KINDS:
            need(m.Vendor, r.entity_id, "seller")
            for sku in ev.get("skus", []):
                p = db.get(m.Product, sku)
                if not p:
                    problems.append(f"Unknown SKU '{sku}'")
                elif p.vendor_id != r.entity_id:
                    problems.append(f"SKU '{sku}' belongs to seller {p.vendor_id}, not {r.entity_id}")
        elif r.kind in IBP_KINDS:
            for it in ev.get("items", []):
                need(m.Product, it.get("sku"), "SKU")
                need(m.Facility, it.get("facility_id"), "warehouse")
    for row in doc.get("rows", []):  # IBP planning rows
        if row.get("CUSTID"):
            need(m.PinCluster, row["CUSTID"], "city cluster")
    return sorted(set(problems))


# ---------------- outbox ----------------
def _add(db: Session, system: str, kind: str, title: str, doc: dict, source_type: str, source_id: str, actor: str,
         problems: list[str] | None = None) -> m.SapMessage:
    # Duplicate prevention: one live message per (system, kind, source).
    existing = db.scalars(select(m.SapMessage).where(m.SapMessage.system == system, m.SapMessage.kind == kind,
                                                     m.SapMessage.source_type == source_type, m.SapMessage.source_id == source_id,
                                                     m.SapMessage.status.in_(["waiting", "sent", "failed", "blocked"]))).first()
    if existing:
        existing.response = {**(existing.response or {}), "duplicate_prevented_at": datetime.now().isoformat(timespec="seconds")}
        return existing
    mid = _id()
    doc["messageId"] = mid
    blocked = bool(problems)
    msg = m.SapMessage(id=mid, created_at=datetime.now(), system=system, kind=kind, title=title[:200], source_type=source_type,
                       source_id=source_id, created_by=actor, payload=doc, status="blocked" if blocked else "waiting", attempts=0,
                       response={"validation": problems, "note": "Blocked: master data check failed, so it will not be sent."} if blocked else {})
    db.add(msg)
    db.flush()
    return msg


def from_recommendation(db: Session, r: m.Recommendation, actor: str) -> list[m.SapMessage]:
    """Prepare the SAP messages an approved decision needs. Delivery is attempted right away if connected."""
    built = []
    if r.kind in TM_KINDS:
        out = _tm(db, r, actor)
        if out:
            built.append(("tm", *out))
    elif r.kind in ARIBA_KINDS:
        out = _ariba(db, r, actor)
        if out:
            built.append(("ariba", *out))
    elif r.kind in IBP_KINDS:
        out = _ibp_recovered(db, r, actor)
        if out:
            built.append(("ibp", *out))
    msgs = [_add(db, system, r.kind, title, doc, "recommendation", r.id, actor, validate(db, doc, r)) for system, title, doc in built]
    for msg in msgs:
        if msg.status == "waiting" and destinations.configured(msg.system):
            deliver(db, msg)
    return msgs


def publish_forecast(db: Session, actor: str) -> m.SapMessage | None:
    out = forecast_document(db, actor)
    if not out:
        return None
    title, doc, source = out
    msg = _add(db, "ibp", "return_forecast", title, doc, "forecast", source, actor, validate(db, doc))
    if msg.status == "waiting" and destinations.configured("ibp"):
        deliver(db, msg)
    return msg


def _retry(msg: m.SapMessage, info: dict) -> None:
    """Schedule another attempt with a growing wait, or give up after MAX_ATTEMPTS."""
    if msg.attempts >= MAX_ATTEMPTS:
        msg.response = {**info, "retryable": False, "note": f"Gave up after {msg.attempts} attempts."}
    else:
        wait = 2 ** (msg.attempts - 1)
        msg.response = {**info, "retryable": True, "retry_after": (datetime.now() + timedelta(minutes=wait)).isoformat(timespec="seconds")}
    msg.status = "failed"


def due(msg: m.SapMessage) -> bool:
    """Whether a message should be (re)sent now."""
    if msg.status == "waiting":
        return True
    if msg.status != "failed" or not (msg.response or {}).get("retryable"):
        return False
    after = (msg.response or {}).get("retry_after")
    return not after or datetime.fromisoformat(after) <= datetime.now()


def deliver(db: Session, msg: m.SapMessage) -> m.SapMessage:
    """Send one message. Without a connection it stays 'waiting' and nothing leaves the app."""
    from . import btp
    if msg.status in ("sent", "blocked"):
        return msg  # never send twice, never send what failed the master-data check
    try:
        conn = destinations.resolve(msg.system)
    except Exception as e:  # sign-in to the destination failed
        msg.attempts += 1
        msg.last_attempt_at = datetime.now()
        _retry(msg, {"error": f"Could not sign in: {type(e).__name__}: {e}"})
        return msg
    if not conn:
        msg.status, msg.response = "waiting", {"note": f"{LABEL[msg.system]} is not connected, so nothing was sent."}
        return msg
    msg.attempts += 1
    msg.last_attempt_at = datetime.now()
    msg.target = conn.url[:300]
    headers = {**conn.headers, "Idempotency-Key": msg.id, "X-ReverseFlow-Message-Id": msg.id}
    try:
        code, body = btp.http_json("POST", conn.url, msg.payload, headers=headers)
    except Exception as e:  # network: worth retrying
        _retry(msg, {"error": f"{type(e).__name__}: {e}", "via": conn.source})
        return msg
    info = {"http_status": code, "body": body if isinstance(body, dict) else {"text": str(body)[:2000]}, "via": conn.source}
    if 200 <= code < 300:
        b = body if isinstance(body, dict) else {}
        ack = next((b[k] for k in ("messageId", "MessageGuid", "id", "ID", "documentId") if b.get(k)), None)
        msg.status = "sent"
        msg.response = {**info, "acknowledged_at": datetime.now().isoformat(timespec="seconds"), "ack_id": ack,
                        "test_receiver": "test receiver" in str(b.get("note", "")).lower()}
    elif code in TRANSIENT:
        _retry(msg, info)
    else:
        msg.status = "failed"
        msg.response = {**info, "retryable": False, "note": "Rejected by the receiver; fix the cause and resend by hand."}
    return msg


def summary(db: Session) -> dict:
    out = {}
    for s in destinations.SYSTEMS:
        rows = db.scalars(select(m.SapMessage.status).where(m.SapMessage.system == s)).all()
        out[s] = {st: rows.count(st) for st in STATUSES}
    return out


def as_dict(msg: m.SapMessage, full: bool = False) -> dict:
    d = {"id": msg.id, "created_at": msg.created_at.isoformat(timespec="seconds"), "system": msg.system, "system_label": LABEL[msg.system],
         "kind": msg.kind, "title": msg.title, "source_type": msg.source_type, "source_id": msg.source_id, "created_by": msg.created_by,
         "status": msg.status, "attempts": msg.attempts, "target": msg.target,
         "last_attempt_at": msg.last_attempt_at.isoformat(timespec="seconds") if msg.last_attempt_at else None,
         "response": msg.response or {}, "test_receiver": bool((msg.response or {}).get("test_receiver"))}
    if full:
        d["payload"] = msg.payload
    return d

