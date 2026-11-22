"""Customer portal and partner operations portal (vendor / 3PL / warehouse)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import llm
from .. import models as m
from .. import orchestrator
from ..agents.prediction import latest_forecast
from ..agents.recovery import recovery_queue
from ..db import BASE_DIR, get_db
from ..ml import nlp, resale
from ..rbac import current_user, require
from ..reference import REASON_CATEGORY, REASONS, SIZES
from ..services import actions
from ..services import intelligence as intel
from ..services import settings as st

router = APIRouter()
UPLOADS = BASE_DIR / "data" / "uploads"
CUSTOMER_STATUS = {
    "pickup_scheduled": "Pickup scheduled", "in_transit": "Picked up, on the way to the returns centre",
    "received": "Received at the returns centre", "inspected": "Quality check completed", "recovered": "Return completed",
}
REASON_OPTIONS = [
    {"category": "Size & fit", "hint": "Too tight, too loose, length"},
    {"category": "Quality", "hint": "Stitching, fabric, finishing"},
    {"category": "Listing mismatch", "hint": "Colour or design differs from photos"},
    {"category": "Damaged", "hint": "Arrived torn, stained or broken"},
    {"category": "Other", "hint": "Changed mind, arrived late"},
]


def _customer(user: m.User) -> str:
    if user.role != "customer":
        raise HTTPException(403, "Customer portal is for customer accounts. Switch persona to a customer.")
    return user.scope_id


def _timeline(db: Session, r: m.Return, D) -> list[dict]:
    steps = [("Return requested", r.request_date, True), ("Pickup scheduled", r.request_date, True)]
    steps.append(("Picked up", r.pickup_date if r.status not in ("pickup_scheduled",) else None, r.status != "pickup_scheduled"))
    steps.append(("Received at returns centre", r.received_date, r.received_date is not None))
    steps.append(("Quality check", r.inspected_date, r.inspected_date is not None))
    if r.resolution == "exchange":
        steps.append(("Replacement dispatched", r.inspected_date, r.inspected_date is not None))
    else:
        steps.append(("Refund initiated", r.inspected_date or r.refund_date, (r.inspected_date or r.refund_date) is not None))
        steps.append(("Refund processed", r.refund_date, r.refund_date is not None))
    out = [{"label": l, "date": d.isoformat() if d else None, "done": bool(done)} for l, d, done in steps]
    for e in db.scalars(select(m.ReturnEvent).where(m.ReturnEvent.return_id == r.id, m.ReturnEvent.customer_visible.is_(True)).order_by(m.ReturnEvent.ts)).all():
        if e.status in ("quality_check",):
            out.insert(-1, {"label": "Additional quality check", "date": None, "done": False, "note": e.note})
    return out


def _explain_customer(r: m.Return, p: m.Product) -> str:
    if r.status == "pickup_scheduled":
        nxt = f"Our partner will collect it on {r.pickup_date:%d %b} ({r.pickup_slot}). Keep the brand tag attached and pack it in the original bag."
    elif r.status == "in_transit":
        nxt = "Once it reaches the returns centre we run a standard quality check, usually within 2 days."
    elif r.status == "received":
        nxt = "It is in the quality-check queue. Your refund starts as soon as the check is done."
    elif r.resolution == "exchange":
        nxt = f"Your replacement in size {r.exchange_size or 'requested'} has been dispatched."
    else:
        nxt = "Your refund has been processed to the original payment method." if r.refund_date else "Your refund will be initiated shortly."
    text_, _ = llm.explain("customer_return", {"product": p.name, "status_text": CUSTOMER_STATUS.get(r.status, r.status), "next_step": nxt})
    return text_


def _return_view(db: Session, r: m.Return, D) -> dict:
    p = db.get(m.Product, r.sku)
    imgs = db.scalars(select(m.ReturnImage).where(m.ReturnImage.return_id == r.id)).all()
    return {"id": r.id, "order_id": r.order_id, "sku": r.sku, "product": p.name, "category": p.category, "size": r.size, "price": r.price,
            "status": r.status, "status_text": CUSTOMER_STATUS.get(r.status, r.status), "request_date": r.request_date.isoformat(),
            "reason_category": r.reason_category, "reason_text": r.reason_text, "resolution": r.resolution, "exchange_size": r.exchange_size,
            "pickup_date": r.pickup_date.isoformat() if r.pickup_date else None, "pickup_slot": r.pickup_slot,
            "refund_amount": r.refund_amount, "timeline": _timeline(db, r, D), "explanation": _explain_customer(r, p),
            "images": [{"filename": i.filename, "size_bytes": i.size_bytes} for i in imgs]}


@router.get("/customer/me")
def customer_me(db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    cid = _customer(user)
    D = st.scenario_date(db)
    window = (st.get(db, "scenario", {}) or {}).get("return_window_days", 10)
    c = db.get(m.Customer, cid)
    orders = db.scalars(select(m.Order).where(m.Order.customer_id == cid).order_by(m.Order.order_date.desc())).all()
    returned = {r.order_id: r for r in db.scalars(select(m.Return).where(m.Return.customer_id == cid)).all()}
    out = []
    for o in orders:
        p = db.get(m.Product, o.sku)
        eligible = o.delivered_date is not None and o.id not in returned and (D - o.delivered_date).days <= window
        out.append({"id": o.id, "sku": o.sku, "product": p.name, "category": p.category, "size": o.size, "price": o.price, "colour": p.colour,
                    "order_date": o.order_date.isoformat(), "delivered_date": o.delivered_date.isoformat() if o.delivered_date else None,
                    "return_id": returned[o.id].id if o.id in returned else None, "eligible": eligible,
                    "return_by": (o.delivered_date + timedelta(days=window)).isoformat() if o.delivered_date else None})
    rets = [_return_view(db, r, D) for r in sorted(returned.values(), key=lambda x: x.request_date, reverse=True)]
    return {"customer": {"id": c.id, "name": c.name, "pin": c.pin}, "scenario_date": D.isoformat(), "return_window_days": window,
            "orders": out, "returns": rets}


def _slots(db: Session, cluster_id: str, D) -> list[dict]:
    """Pickup slots for the next 3 days; availability reflects forecast load vs fleet capacity."""
    fc = latest_forecast(db) or {"clusters": []}
    c = next((x for x in fc["clusters"] if x["cluster_id"] == cluster_id), None)
    prov = next((p for p in db.scalars(select(m.LogisticsProvider)).all() if any(cc["cluster_id"] == cluster_id for cc in p.clusters)), None)
    veh = next(cc["vehicles"] for cc in prov.clusters if cc["cluster_id"] == cluster_id) + st.capacity_overrides(db).get(f"vehicles:{cluster_id}", 0)
    cap = veh * prov.pickups_per_vehicle
    out = []
    for k in range(1, 4):
        d = D + timedelta(days=k)
        load = next((p["network_forecast"] for p in (c or {}).get("forecast", []) if p["day"] == d.isoformat()), None)
        ratio = (load / cap) if load else 0.8
        for slot in ("09:00-13:00", "13:00-17:00", "17:00-21:00"):
            out.append({"date": d.isoformat(), "slot": slot, "availability": "limited" if ratio > 1.0 else "available"})
    return out


@router.get("/customer/orders/{order_id}/return-options")
def return_options(order_id: str, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    cid = _customer(user)
    o = db.get(m.Order, order_id)
    if not o or o.customer_id != cid:
        raise HTTPException(404, "order not found")
    p = db.get(m.Product, o.sku)
    D = st.scenario_date(db)
    sizes = [s for s in SIZES if s != o.size] if o.size in SIZES else []
    return {"order_id": o.id, "product": p.name, "size": o.size, "reasons": REASON_OPTIONS, "exchange_sizes": sizes,
            "exchange_first": p.exchange_first, "size_chart": p.size_chart, "size_chart_version": p.size_chart_version,
            "exchange_message": ("This style tends to run small. Many customers keep it by exchanging for one size up, delivered with the same pickup."
                                 if p.exchange_first else None),
            "slots": _slots(db, o.cluster_id, D), "max_images": 4}


class ReturnIn(BaseModel):
    order_id: str
    reason_category: str
    reason_text: str = Field(min_length=3, max_length=600)
    resolution: str = "refund"
    exchange_size: str | None = None
    pickup_date: str
    pickup_slot: str


@router.post("/customer/returns")
def create_return(body: ReturnIn, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    cid = _customer(user)
    D = st.scenario_date(db)
    o = db.get(m.Order, body.order_id)
    if not o or o.customer_id != cid:
        raise HTTPException(404, "order not found")
    if o.delivered_date is None:
        raise HTTPException(400, "order has not been delivered yet")
    window = (st.get(db, "scenario", {}) or {}).get("return_window_days", 10)
    if (D - o.delivered_date).days > window:
        raise HTTPException(400, f"return window of {window} days has closed")
    if db.scalar(select(m.Return.id).where(m.Return.order_id == o.id)):
        raise HTTPException(409, "a return already exists for this order")
    if body.reason_category not in {r["category"] for r in REASON_OPTIONS}:
        raise HTTPException(400, "invalid reason category")
    if body.resolution not in ("refund", "exchange"):
        raise HTTPException(400, "resolution must be refund or exchange")
    if body.resolution == "exchange" and body.exchange_size not in SIZES:
        raise HTTPException(400, "choose a valid exchange size")
    pd_ = datetime.fromisoformat(body.pickup_date).date()
    if not (D < pd_ <= D + timedelta(days=3)):
        raise HTTPException(400, "pickup date must be within the next 3 days")
    p = db.get(m.Product, o.sku)
    cl = db.get(m.PinCluster, o.cluster_id)
    n = db.scalar(select(func.count(m.Return.id)))
    rid = f"RT{n + 1:07d}"
    while db.get(m.Return, rid):
        n += 1
        rid = f"RT{n + 1:07d}"
    facility = cl.default_facility_id
    ro = st.routing_overrides(db).get(cl.id, {})
    h = int(hashlib.md5(rid.encode()).hexdigest()[:4], 16) / 65535
    acc = 0.0
    for fid, share in ro.items():
        acc += share
        if h < acc:
            facility = fid
            break
    prov = next(pp for pp in db.scalars(select(m.LogisticsProvider)).all() if any(cc["cluster_id"] == cl.id for cc in pp.clusters))
    nlp.ensure_trained(db)
    (pred, conf), = nlp.classify([body.reason_text])
    (sent,) = nlp.sentiment([body.reason_text])
    r = m.Return(id=rid, order_id=o.id, customer_id=cid, sku=o.sku, vendor_id=p.vendor_id, cluster_id=cl.id, size=o.size, price=o.price,
                 request_date=D, reason_category=body.reason_category, reason_text=body.reason_text.strip(), predicted_reason=pred,
                 reason_confidence=round(conf, 3), sentiment=sent, resolution=body.resolution,
                 exchange_size=body.exchange_size if body.resolution == "exchange" else None, status="pickup_scheduled",
                 pickup_date=pd_, pickup_slot=body.pickup_slot, facility_id=facility, provider_id=prov.id, images_count=0,
                 created_via="portal", is_synthetic=True)
    db.add(r)
    db.flush()
    actions.add_event(db, rid, "requested", "Return requested via customer portal")
    actions.add_event(db, rid, "pickup_scheduled", f"Pickup booked with {prov.name} for {pd_:%d %b}, {body.pickup_slot}")
    actions.add_event(db, rid, "classified", f"Reason classified as {REASONS[pred]} ({conf:.0%}); routed to {facility}", customer_visible=False)
    actions.audit(db, user.name, "user", "return.created", "return", rid, {"order_id": o.id, "facility": facility, "predicted_reason": pred})
    db.commit()
    run_id = orchestrator.run_async("return_created", {"return_id": rid, "customer_portal": True})
    return {"return": _return_view(db, r, D), "orchestrator_run_id": run_id}


@router.post("/customer/returns/{return_id}/images")
async def upload_image(return_id: str, file: UploadFile = File(...), db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    cid = _customer(user)
    r = db.get(m.Return, return_id)
    if not r or r.customer_id != cid:
        raise HTTPException(404, "return not found")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(400, "only image files are accepted")
    existing = db.scalar(select(func.count(m.ReturnImage.id)).where(m.ReturnImage.return_id == return_id))
    if existing >= 4:
        raise HTTPException(400, "maximum 4 images per return")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "image larger than 5 MB")
    d = UPLOADS / return_id
    d.mkdir(parents=True, exist_ok=True)
    safe = Path(file.filename or "image").name.replace(" ", "_")[-80:]
    path = d / f"{existing + 1}_{safe}"
    path.write_bytes(data)
    db.add(m.ReturnImage(return_id=return_id, filename=safe, content_type=file.content_type, size_bytes=len(data), path=str(path), uploaded_at=datetime.now()))
    r.images_count = existing + 1
    db.commit()
    return {"ok": True, "images": r.images_count}


@router.get("/customer/returns/{return_id}")
def customer_return(return_id: str, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    cid = _customer(user)
    r = db.get(m.Return, return_id)
    if not r or r.customer_id != cid:
        raise HTTPException(404, "return not found")
    return _return_view(db, r, st.scenario_date(db))


# ---------------- Partner: vendor ----------------
def _vendor_scope(user: m.User, vendor_id: str | None) -> str:
    if user.role == "vendor":
        return user.scope_id
    if user.role in ("ops_manager", "vendor_quality_manager"):
        return vendor_id or "V03"
    raise HTTPException(403, "vendor view not available for this role")


@router.get("/partners/vendor")
def vendor_view(vendor_id: str | None = None, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    vid = _vendor_scope(user, vendor_id)
    D = st.scenario_date(db)
    v = db.get(m.Vendor, vid)
    ranking = intel.vendor_rankings(db, D)
    me = next(x for x in ranking if x["vendor_id"] == vid)
    net = {k: round(float(pd.Series([x[k] for x in ranking]).mean()), 4) for k in ("return_rate", "defect_rate", "size_issue_rate", "avoidable_rate")}
    df = intel.returns_frame(db, D, 90)
    mine = df[df.vendor_id == vid]
    sku_rows = []
    for sku, g in mine.groupby("sku"):
        rc = g.reason.value_counts()
        sku_rows.append({"sku": sku, "name": g.product_name.iloc[0], "returns": int(len(g)), "top_reason": REASONS.get(rc.index[0], rc.index[0]),
                         "top_share": round(float(rc.iloc[0] / len(g)), 3), "by_reason": {REASONS.get(k, k): int(c) for k, c in rc.items()},
                         "by_size": {k: int(c) for k, c in g["size"].value_counts().items()}})
    sku_rows.sort(key=lambda x: -x["returns"])
    # anonymised customer comments: text only, no identity
    comments = mine.sort_values("request_date", ascending=False).head(10)[["reason_text", "reason", "size", "request_date"]]
    monthly = pd.read_sql(text("""SELECT o.order_date d, CASE WHEN r.id IS NULL THEN 0 ELSE 1 END ret FROM orders o
                                  JOIN products p ON p.sku=o.sku LEFT JOIN returns r ON r.order_id=o.id WHERE p.vendor_id=:v"""),
                          db.bind, params={"v": vid}, parse_dates=["d"])
    trend = monthly.groupby(monthly.d.dt.to_period("M")).ret.mean().tail(12)
    recs = db.scalars(select(m.Recommendation).where(m.Recommendation.entity_type == "vendor", m.Recommendation.entity_id == vid)).all()
    products = db.scalars(select(m.Product).where(m.Product.vendor_id == vid)).all()
    alerts_ = db.scalars(select(m.Alert).where(m.Alert.audience == "vendor", m.Alert.scope_id == vid).order_by(m.Alert.created_at.desc()).limit(10)).all()
    return {"vendor": {"id": v.id, "name": v.name, "city": v.city, "specialty": v.specialty, "qc_hold": v.qc_hold},
            "metrics": me, "network": net, "sku_patterns": sku_rows[:15],
            "complaints": [{"text": c.reason_text, "reason": REASONS.get(c.reason, c.reason), "size": c.size, "date": str(c.request_date)[:10]} for c in comments.itertuples()],
            "reason_mix": {REASONS.get(k, k): int(c) for k, c in mine.reason.value_counts().items()},
            "trend": [{"month": str(k), "return_rate": round(float(x), 4)} for k, x in trend.items()],
            "recommendations": [{"id": r.id, "kind": r.kind, "title": r.title, "status": r.status, "rationale": r.rationale, "created_at": r.created_at.isoformat()} for r in recs],
            "products": [{"sku": p.sku, "name": p.name, "pre_dispatch_qc": p.pre_dispatch_qc, "exchange_first": p.exchange_first,
                          "size_chart_version": p.size_chart_version} for p in products],
            "alerts": [{"id": a.id, "title": a.title, "body": a.body, "severity": a.severity, "acknowledged": a.acknowledged, "created_at": a.created_at.isoformat()} for a in alerts_],
            "privacy": "Customer identities and other vendors' data are not shown."}


class VendorResponseIn(BaseModel):
    recommendation_id: str
    note: str = Field(min_length=5, max_length=1000)


@router.post("/partners/vendor/response")
def vendor_response(body: VendorResponseIn, db: Session = Depends(get_db), user: m.User = Depends(require("vendor"))):
    r = db.get(m.Recommendation, body.recommendation_id)
    if not r or r.entity_id != user.scope_id:
        raise HTTPException(404, "recommendation not found for your account")
    db.add(m.Alert(created_at=datetime.now(), agent="vendor", severity="low", audience="ops_manager", scope_id=None,
                   title=f"Vendor response on: {r.title}", body=f"{user.name}: {body.note}", entity_type="recommendation", entity_id=r.id))
    actions.audit(db, user.name, "user", "vendor.response", "recommendation", r.id, {"note": body.note})
    db.commit()
    return {"ok": True}


# ---------------- Partner: 3PL ----------------
def _provider_scope(user: m.User, provider_id: str | None) -> str:
    if user.role == "logistics":
        return user.scope_id
    if user.role in ("ops_manager",):
        return provider_id or "LP-SWR"
    raise HTTPException(403, "logistics view not available for this role")


@router.get("/partners/logistics")
def logistics_view(provider_id: str | None = None, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    pid = _provider_scope(user, provider_id)
    D = st.scenario_date(db)
    p = db.get(m.LogisticsProvider, pid)
    fc = latest_forecast(db) or {"clusters": []}
    co = st.capacity_overrides(db)
    clusters = []
    for cc in p.clusters:
        f = next((x for x in fc["clusters"] if x["cluster_id"] == cc["cluster_id"]), {})
        veh = cc["vehicles"] + co.get(f"vehicles:{cc['cluster_id']}", 0)
        clusters.append({"cluster_id": cc["cluster_id"], "city": f.get("city"), "vehicles": veh, "extra_vehicles_approved": co.get(f"vehicles:{cc['cluster_id']}", 0),
                         "capacity": veh * p.pickups_per_vehicle, "forecast": [{"day": x["day"], "pickups": x["network_forecast"], "lo": x["network_lo"], "hi": x["network_hi"]} for x in f.get("forecast", [])],
                         "normal_daily": f.get("network_normal_daily"), "risk": f.get("risk")})
    tasks = db.scalars(select(m.Return).where(m.Return.provider_id == pid, m.Return.status == "pickup_scheduled").order_by(m.Return.created_via.desc(), m.Return.pickup_date, m.Return.id).limit(80)).all()
    sla = pd.read_sql(text("""SELECT cluster_id, pickup_date d, pickup_sla_met s FROM returns WHERE provider_id=:p AND pickup_sla_met IS NOT NULL AND pickup_date >= :since"""),
                      db.bind, params={"p": pid, "since": D - timedelta(days=60)}, parse_dates=["d"])
    sla_trend = sla.groupby(sla.d.dt.to_period("W")).s.mean()
    alerts_ = db.scalars(select(m.Alert).where(m.Alert.audience == "logistics", m.Alert.scope_id == pid).order_by(m.Alert.created_at.desc()).limit(10)).all()
    orders = {o.id: o for o in db.scalars(select(m.Order).where(m.Order.id.in_([t.order_id for t in tasks]))).all()}
    return {"provider": {"id": p.id, "name": p.name, "pickups_per_vehicle": p.pickups_per_vehicle, "cost_per_pickup": p.cost_per_pickup, "sla_hours": p.sla_hours},
            "clusters": clusters,
            "pickup_tasks": [{"return_id": t.id, "cluster_id": t.cluster_id, "pin": db.get(m.Customer, t.customer_id).pin, "sku": t.sku,
                              "pickup_date": t.pickup_date.isoformat(), "slot": t.pickup_slot, "facility_id": t.facility_id, "created_via": t.created_via,
                              "expected_serial": orders[t.order_id].serial_no if t.order_id in orders else None} for t in tasks],
            "sla": {"overall_60d": round(float(sla.s.mean()), 3) if len(sla) else None,
                    "by_cluster": {k: round(float(x), 3) for k, x in sla.groupby("cluster_id").s.mean().items()},
                    "weekly": [{"week": str(k.start_time.date()), "sla": round(float(x), 3)} for k, x in sla_trend.items()]},
            "alerts": [{"id": a.id, "title": a.title, "body": a.body, "severity": a.severity, "acknowledged": a.acknowledged} for a in alerts_],
            "note": "Forecast pickups are network-scale estimates; the task list shows individual synthetic pickup records."}


class PickupIn(BaseModel):
    tag_intact: bool = True
    serial_scanned: str
    weight_delta_pct: float = 0.0


@router.post("/partners/logistics/pickups/{return_id}/complete")
def complete_pickup(return_id: str, body: PickupIn, db: Session = Depends(get_db), user: m.User = Depends(require("logistics", "ops_manager"))):
    r = db.get(m.Return, return_id)
    if not r or (user.role == "logistics" and r.provider_id != user.scope_id):
        raise HTTPException(404, "pickup not found")
    if r.status != "pickup_scheduled":
        raise HTTPException(400, f"return is {r.status}, not awaiting pickup")
    D = st.scenario_date(db)
    r.status = "in_transit"
    r.pickup_date = D if r.pickup_date > D else r.pickup_date
    r.tag_intact = body.tag_intact
    r.serial_returned = body.serial_scanned.strip()
    r.weight_delta_pct = body.weight_delta_pct
    r.pickup_sla_met = (r.pickup_date - r.request_date).days <= 2
    r.pickup_cost = db.get(m.LogisticsProvider, r.provider_id).cost_per_pickup
    actions.add_event(db, r.id, "in_transit", "Picked up by courier")
    actions.add_event(db, r.id, "pickup_evidence", f"Tag intact: {body.tag_intact}; serial {body.serial_scanned}; weight delta {body.weight_delta_pct:+.1f}%", customer_visible=False)
    actions.audit(db, user.name, "user", "pickup.completed", "return", r.id, body.model_dump())
    db.commit()
    run_id = orchestrator.run_async("pickup_completed", {"return_id": r.id})
    return {"ok": True, "status": r.status, "orchestrator_run_id": run_id}


# ---------------- Partner: warehouse ----------------
def _facility_scope(user: m.User, facility_id: str | None) -> str:
    if user.role == "warehouse":
        return user.scope_id
    if user.role in ("ops_manager", "warehouse_manager"):
        return facility_id or "FAC-PUN"
    raise HTTPException(403, "warehouse view not available for this role")


@router.get("/partners/warehouse")
def warehouse_view(facility_id: str | None = None, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    fid = _facility_scope(user, facility_id)
    D = st.scenario_date(db)
    f = db.get(m.Facility, fid)
    cfg = dict(resale.DEFAULTS, **(st.get(db, "resale", {}) or {}))
    resale.build_demand_index(db, D)
    q = [i for i in recovery_queue(db, D, cfg) if i["facility_id"] == fid]
    fast = set((st.get(db, "fast_track", {}) or {}).get("return_ids", []))
    integ = {r.entity_id: r.status for r in db.scalars(select(m.Recommendation).where(m.Recommendation.kind == "integrity_inspection")).all()}
    for i in q:
        i["fast_track"] = i["return_id"] in fast
        i["integrity"] = integ.get(i["return_id"])
    fc = latest_forecast(db) or {"clusters": []}
    clusters = db.scalars(select(m.PinCluster).where(m.PinCluster.default_facility_id == fid)).all()
    ro = st.routing_overrides(db)
    expected = []
    for c in clusters:
        fcc = next((x for x in fc["clusters"] if x["cluster_id"] == c.id), None)
        if fcc:
            keep = 1 - sum(ro.get(c.id, {}).values())
            expected.append({"cluster_id": c.id, "city": c.city, "share_kept": round(keep, 3),
                             "forecast": [{"day": x["day"], "units": round(x["network_forecast"] * keep)} for x in fcc["forecast"]]})
    for cid, alloc in ro.items():
        if fid in alloc:
            fcc = next((x for x in fc["clusters"] if x["cluster_id"] == cid), None)
            if fcc:
                expected.append({"cluster_id": cid, "city": fcc["city"], "share_kept": alloc[fid], "diverted_in": True,
                                 "forecast": [{"day": x["day"], "units": round(x["network_forecast"] * alloc[fid])} for x in fcc["forecast"]]})
    daily = db.scalars(select(m.FacilityDaily).where(m.FacilityDaily.facility_id == fid).order_by(m.FacilityDaily.day.desc()).limit(45)).all()
    extra = st.capacity_overrides(db).get(f"inspection:{fid}", 0)
    graded = pd.read_sql(text("SELECT grade, COUNT(*) n FROM returns WHERE facility_id=:f AND grade IS NOT NULL AND inspected_date >= :s GROUP BY 1"),
                         db.bind, params={"f": fid, "s": D - timedelta(days=30)})
    return {"facility": {"id": f.id, "name": f.name, "city": f.city, "inspection_capacity": f.inspection_capacity + extra, "extra_capacity_approved": extra,
                         "storage_capacity": f.storage_capacity, "normal_load": f.normal_load},
            "queue": q[:120], "queue_total": len(q), "expected_inbound": expected,
            "daily": [{"day": d.day.isoformat(), "inbound": d.inbound, "processed": d.processed, "backlog": d.backlog, "utilisation": d.utilisation} for d in reversed(daily)],
            "grade_mix_30d": {r.grade: int(r.n) for r in graded.itertuples()},
            "alerts": [{"id": a.id, "title": a.title, "body": a.body, "severity": a.severity, "acknowledged": a.acknowledged}
                       for a in db.scalars(select(m.Alert).where(m.Alert.audience == "warehouse").order_by(m.Alert.created_at.desc()).limit(8)).all()
                       if a.scope_id in (None, fid)]}


@router.post("/partners/warehouse/receive/{return_id}")
def receive(return_id: str, db: Session = Depends(get_db), user: m.User = Depends(require("warehouse", "warehouse_manager", "ops_manager"))):
    r = db.get(m.Return, return_id)
    if not r or (user.role == "warehouse" and r.facility_id != user.scope_id):
        raise HTTPException(404, "return not found at your facility")
    if r.status != "in_transit":
        raise HTTPException(400, f"return is {r.status}, not in transit")
    r.status, r.received_date = "received", st.scenario_date(db)
    actions.add_event(db, r.id, "received", "Received at the returns centre")
    actions.audit(db, user.name, "user", "return.received", "return", r.id, {"facility": r.facility_id})
    db.commit()
    return {"ok": True, "status": r.status}


class InspectIn(BaseModel):
    grade: str
    verified_reason: str
    defects: str | None = None
    recovery_action: str | None = None


@router.post("/partners/warehouse/inspect/{return_id}")
def inspect(return_id: str, body: InspectIn, db: Session = Depends(get_db), user: m.User = Depends(require("warehouse", "warehouse_manager", "ops_manager"))):
    r = db.get(m.Return, return_id)
    if not r or (user.role == "warehouse" and r.facility_id != user.scope_id):
        raise HTTPException(404, "return not found at your facility")
    if r.status != "received":
        raise HTTPException(400, f"return is {r.status}; receive it before inspection")
    if body.grade not in ("A", "B", "C") or body.verified_reason not in REASONS:
        raise HTTPException(400, "invalid grade or reason")
    D = st.scenario_date(db)
    vend_problem = body.verified_reason in ("STITCHING", "FABRIC_QUALITY")
    action = body.recovery_action or {"A": "restock", "B": "refurbish", "C": "return_to_vendor" if vend_problem else "liquidate"}[body.grade]
    if action not in ("restock", "refurbish", "liquidate", "return_to_vendor"):
        raise HTTPException(400, "invalid recovery action")
    p = db.get(m.Product, r.sku)
    cfg = dict(resale.DEFAULTS, **(st.get(db, "resale", {}) or {}))
    resale.build_demand_index(db, D)
    lead = 1 if action == "restock" else 5
    val = resale.value_on(r.price, p.category, body.grade, D + timedelta(days=lead), D, cfg)
    r.status, r.inspected_date, r.grade, r.defects = "inspected", D, body.grade, body.defects
    r.verified_reason, r.recovery_action = body.verified_reason, action
    r.recovered_value = max(0.0, val["value"]) if action in ("restock", "refurbish") else round(r.price * (0.22 if action == "liquidate" else 0.55), 2)
    if r.resolution == "refund":
        r.refund_amount, r.refund_date = r.price, D
    actions.add_event(db, r.id, "inspected", "Quality check completed" + (". Refund processed to your original payment method." if r.resolution == "refund" else ". Replacement dispatched."))
    actions.audit(db, user.name, "user", "return.inspected", "return", r.id, body.model_dump() | {"recovery_action": action, "value": r.recovered_value})
    db.commit()
    run_id = orchestrator.run_async("inspection_completed", {"return_id": r.id})
    return {"ok": True, "status": r.status, "recovery_action": action, "estimated_recovery_value": r.recovered_value, "orchestrator_run_id": run_id,
            "nlp_agreed": r.predicted_reason == body.verified_reason}
