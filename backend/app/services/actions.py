"""Effects of approved recommendations on the shared operational state, and the
approval workflow itself. Every state change is written to the audit log."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import settings as st

STATUSES = {"pending", "approved", "rejected", "escalated"}
ACTION_TO_STATUS = {"approve": "approved", "reject": "rejected", "escalate": "escalated"}


def audit(db: Session, actor: str, actor_type: str, action: str, entity_type: str, entity_id: str, detail: dict):
    db.add(m.AuditLog(ts=datetime.now(), actor=actor, actor_type=actor_type, action=action, entity_type=entity_type,
                      entity_id=entity_id, detail=detail))


def add_event(db: Session, return_id: str, status: str, note: str, customer_visible: bool = True):
    db.add(m.ReturnEvent(return_id=return_id, ts=datetime.now(), status=status, note=note, customer_visible=customer_visible))


def apply(db: Session, r: m.Recommendation, actor: str) -> dict:
    ev = r.evidence or {}
    effect = {}
    if r.kind in ("vendor_qc_hold", "pre_dispatch_qc"):
        prods = db.scalars(select(m.Product).where(m.Product.vendor_id == r.entity_id)).all()
        for p in prods:
            p.pre_dispatch_qc = True
        if r.kind == "vendor_qc_hold":
            v = db.get(m.Vendor, r.entity_id)
            v.qc_hold = True
        effect = {"products_with_pre_dispatch_qc": len(prods), "vendor_qc_hold": r.kind == "vendor_qc_hold"}
        db.add(m.Alert(created_at=datetime.now(), agent="governance", severity="high", audience="vendor", scope_id=r.entity_id,
                       title=("QC hold approved" if r.kind == "vendor_qc_hold" else "Pre-dispatch QC approved") + " for your SKUs",
                       body=r.rationale[:500], entity_type="recommendation", entity_id=r.id))
    elif r.kind == "size_chart_update":
        delta = ev.get("delta_inches", 1)
        changed = []
        for sku in ev.get("skus", []):
            p = db.get(m.Product, sku)
            if p and p.size_chart:
                p.size_chart = {s: {k: (v + delta if k in ("bust_in", "waist_in") else v) for k, v in dims.items()} for s, dims in p.size_chart.items()}
                p.size_chart_version += 1
                changed.append(sku)
        effect = {"size_charts_updated": changed, "delta_inches": delta}
        db.add(m.Alert(created_at=datetime.now(), agent="prevention", severity="medium", audience="vendor", scope_id=r.entity_id,
                       title=f"Size chart corrected on {len(changed)} SKUs", body=r.rationale[:500], entity_type="recommendation", entity_id=r.id))
    elif r.kind == "listing_fix":
        for sku in ev.get("skus", []):
            p = db.get(m.Product, sku)
            if p and "Colour note" not in p.description:
                p.description += " Colour note: shade may appear deeper in natural light than on screen."
        effect = {"listings_updated": ev.get("skus", [])}
    elif r.kind == "exchange_first":
        for sku in ev.get("skus", []):
            p = db.get(m.Product, sku)
            if p:
                p.exchange_first = True
        effect = {"exchange_first_skus": ev.get("skus", [])}
    elif r.kind == "reroute":
        ro = st.routing_overrides(db)
        a = ev["allocation"]
        ro[ev["cluster_id"]] = {a["facility_id"]: a["share"]}
        st.put(db, "routing_overrides", ro)
        effect = {"routing_overrides": ro}
    elif r.kind == "extra_pickup":
        co = st.capacity_overrides(db)
        key = f"vehicles:{r.entity_id}"
        co[key] = co.get(key, 0) + int(ev.get("vehicles", 0))
        st.put(db, "capacity_overrides", co)
        effect = {"capacity_overrides": co}
        db.add(m.Alert(created_at=datetime.now(), agent="logistics", severity="medium", audience="logistics", scope_id=ev.get("provider_id"),
                       title=f"Extra vehicles booked: {ev.get('vehicles')} for {ev.get('days')} days", body=r.title, entity_type="recommendation", entity_id=r.id))
    elif r.kind == "inspection_overtime":
        co = st.capacity_overrides(db)
        key = f"inspection:{r.entity_id}"
        co[key] = co.get(key, 0) + int(ev.get("units_per_day", 0))
        st.put(db, "capacity_overrides", co)
        effect = {"capacity_overrides": co}
    elif r.kind == "rapid_restock":
        ids = [i["return_id"] for i in ev.get("items", [])]
        st.put(db, "fast_track", {"return_ids": ids, "recommendation_id": r.id})
        effect = {"fast_tracked": len(ids)}
    elif r.kind == "refurbish_batch":
        n = 0
        for it in ev.get("items", []):
            ret = db.get(m.Return, it["return_id"])
            if ret and ret.status == "inspected":
                ret.recovery_action = "refurbish"
                n += 1
        effect = {"marked_for_refurbishment": n}
    elif r.kind == "integrity_inspection":
        add_event(db, r.entity_id, "quality_check", "Additional quality check scheduled at the returns centre. Your refund timeline is unchanged.")
        add_event(db, r.entity_id, "integrity_inspection", f"Physical inspection approved by {actor}. Evidence: " + "; ".join(ev.get("case", {}).get("evidence", [])), customer_visible=False)
        effect = {"inspection_requested": r.entity_id}
    r.applied = True
    # Hand the decision to the SAP system that carries it out (IBP, TM or Ariba).
    from ..sap import outbox
    msgs = outbox.from_recommendation(db, r, actor)
    if msgs:
        effect["sap_messages"] = [{"id": x.id, "system": x.system, "status": x.status} for x in msgs]
    audit(db, actor, "user" if not actor.startswith("system") else "system", f"recommendation.applied.{r.kind}", "recommendation", r.id, effect)
    return effect


def can_decide(user: m.User, r: m.Recommendation) -> tuple[bool, str]:
    if user.role in ("vendor", "logistics", "warehouse", "customer"):
        return False, "Partner and customer roles cannot approve marketplace interventions."
    if r.status == "escalated":
        return (user.role == "ops_manager", "Escalated items are decided by the Operations Manager.")
    if user.role != r.approver_role and user.role != "ops_manager":
        return False, f"This item requires the {r.approver_role.replace('_', ' ')} role."
    return True, ""


def decide(db: Session, r: m.Recommendation, user: m.User, action: str, reason: str) -> dict:
    if action not in ACTION_TO_STATUS:
        raise ValueError("action must be approve, reject or escalate")
    ok, why = can_decide(user, r)
    if not ok:
        raise PermissionError(why)
    if not reason or len(reason.strip()) < 3:
        raise ValueError("a reason is required for every decision")
    if r.status in ("approved", "rejected"):
        raise ValueError(f"already {r.status}")
    if action == "approve" and r.cost_inr > user.approval_limit:
        raise PermissionError(f"Cost INR {r.cost_inr:,.0f} exceeds your approval limit of INR {user.approval_limit:,.0f}; escalate instead.")
    prev = r.status
    new = ACTION_TO_STATUS[action]
    r.status = new
    r.updated_at = datetime.now()
    if action == "escalate":
        r.approver_role = "ops_manager"
    db.add(m.DecisionLog(recommendation_id=r.id, user_id=user.id, user_name=user.name, role=user.role, ts=datetime.now(),
                         action=action, reason=reason.strip(), previous_status=prev, new_status=new))
    effect = {}
    if new == "approved":
        effect = apply(db, r, user.name)
    elif new == "rejected" and r.kind == "integrity_inspection":
        add_event(db, r.entity_id, "integrity_cleared", f"Integrity flag cleared by {user.name}: {reason.strip()}", customer_visible=False)
    audit(db, user.name, "user", f"recommendation.{action}", "recommendation", r.id, {"previous": prev, "new": new, "reason": reason.strip()})
    db.commit()
    return {"id": r.id, "previous_status": prev, "new_status": new, "effect": effect}
