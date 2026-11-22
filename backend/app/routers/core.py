from __future__ import annotations

import threading
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import bootstrap, llm
from .. import models as m
from ..db import get_db
from ..rbac import PAGES, current_user, require
from ..services import actions
from ..services import settings as st

router = APIRouter()


def latest_agent_outputs(db: Session) -> tuple[m.OrchestratorRun | None, dict]:
    # Prefer runs that executed the whole plan; narrow event runs (e.g. a single pickup) only
    # score one return and would understate network-wide figures.
    full = ["full_cycle", "return_created"]
    run = db.scalars(select(m.OrchestratorRun).where(m.OrchestratorRun.status.in_(["completed", "partial"]), m.OrchestratorRun.trigger.in_(full))
                     .order_by(m.OrchestratorRun.started_at.desc())).first()
    outs = {}
    q = (select(m.AgentRun).join(m.OrchestratorRun, m.OrchestratorRun.id == m.AgentRun.run_id)
         .where(m.AgentRun.status == "completed", m.OrchestratorRun.trigger.in_(full)).order_by(m.AgentRun.id.desc()).limit(60))
    for ar in db.scalars(q).all():
        outs.setdefault(ar.agent, ar.outputs)
    return run, outs


@router.get("/health")
def health():
    return {"ok": True, **bootstrap.status()}


@router.get("/meta")
def meta(db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    return {"scenario_date": st.scenario_date(db).isoformat(), "synthetic": True,
            "disclaimer": "All records are synthetic and all scenario numbers are illustrative assumptions for demonstration.",
            "user": {"id": user.id, "name": user.name, "role": user.role, "title": user.title, "scope_id": user.scope_id,
                     "approval_limit": user.approval_limit},
            "pages": PAGES.get(user.role, []), "status": bootstrap.status()}


@router.get("/users")
def users(db: Session = Depends(get_db)):
    return [{"id": u.id, "name": u.name, "role": u.role, "title": u.title, "scope_id": u.scope_id} for u in db.scalars(select(m.User)).all()]


@router.get("/overview")
def overview(db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    run, outs = latest_agent_outputs(db)
    D = st.scenario_date(db)
    pred, intel, prev, logi, reco, gov = (outs.get(k, {}) for k in ("prediction", "intelligence", "prevention", "logistics", "recovery", "governance"))
    open_returns = db.scalar(select(func.count(m.Return.id)).where(m.Return.status.in_(["pickup_scheduled", "in_transit", "received", "inspected"])))
    pending = db.scalar(select(func.count(m.Recommendation.id)).where(m.Recommendation.status.in_(["pending", "escalated"])))
    since = D - timedelta(days=30)
    sla = db.scalar(select(func.avg(func.cast(m.Return.pickup_sla_met, m.Float))).where(m.Return.pickup_date >= since, m.Return.pickup_sla_met.isnot(None)))
    west = [c for c in pred.get("clusters", []) if c["cluster_id"] in ("PNQ", "AMD", "JAI")]
    vf = intel.get("vendor_findings", [])
    pune_gap = next((g for g in logi.get("capacity_gaps", []) if g["cluster_id"] == "PNQ"), None)
    reroute = next((a for a in logi.get("allocation_plan", {}).get("allocation", {}).get("PNQ", []) if not a["default"]), None)
    timeline = [
        {"t": "T-7", "agent": "prediction", "title": "Return Prediction",
         "text": f"Forecasts {pred.get('west_surge_avg_multiplier', 0):.1f}x normal ethnicwear returns across Pune, Ahmedabad and Jaipur over the next 7 days."
         if pred else "Waiting for first forecast."},
        {"t": "T-6", "agent": "intelligence", "title": "Product, Vendor & Customer Intelligence",
         "text": "; ".join(f"{v['vendor_name']}: {v['reason_label'].lower()} {v['share']:.0%} vs {v['network_share']:.0%}" for v in vf[:2]) or "No significant vendor pattern."},
        {"t": "T-6", "agent": "governance", "title": "Return-integrity check",
         "text": f"Flags {gov.get('integrity_flags', 0)} returns with tag or serial mismatches for physical inspection. No automatic action on customers."},
        {"t": "T-5", "agent": "prevention", "title": "Prevention & Policy",
         "text": f"{prev.get('recommendations', 0)} preventive actions proposed ({', '.join(k.replace('_', ' ') for k in prev.get('kinds', []))})."},
        {"t": "T-4", "agent": "logistics", "title": "Reverse Logistics",
         "text": (f"Pune inspection gap about {pune_gap['inspection_gap']:,} units/day at the forecast peak"
                  + (f"; proposes routing {reroute['share']:.0%} to Nashik." if reroute else ".")) if pune_gap else "Capacity analysis pending."},
        {"t": "T-2", "agent": "recovery", "title": "Inventory Recovery",
         "text": f"Prioritises likely Grade-A festive items by resale-window value; INR {reco.get('value_at_risk_7d_inr', 0):,} at risk if the queue waits 7 days."},
        {"t": "T-1", "agent": "governance", "title": "Compliance & Governance",
         "text": f"Routes {gov.get('routed_to_humans', 0)} high-impact interventions to managers; {gov.get('auto_approved', 0)} within pre-authorised limits."},
    ]
    alerts = db.scalars(select(m.Alert).where(m.Alert.audience == "ops_manager").order_by(m.Alert.created_at.desc()).limit(8)).all()
    return {
        "scenario_date": D.isoformat(),
        "kpis": {"open_returns_sample": open_returns, "west_surge_multiplier": pred.get("west_surge_avg_multiplier"),
                 "pending_approvals": pending, "value_at_risk_7d_inr": reco.get("value_at_risk_7d_inr"),
                 "pickup_sla_30d": round(float(sla or 0), 3), "integrity_flags": db.scalar(select(func.count(m.Recommendation.id)).where(m.Recommendation.kind == "integrity_inspection",
                                                                                       m.Recommendation.status.in_(["pending", "escalated"]))),
                 "network_expected_7d": sum(c["expected_network_7d"] for c in pred.get("clusters", [])),
                 "west_expected_7d": sum(c["expected_network_7d"] for c in west)},
        "clusters": pred.get("clusters", []), "vendor_findings": vf, "worst_vendors": intel.get("worst_vendors", []),
        "capacity_gaps": logi.get("capacity_gaps", []), "timeline": timeline,
        "reroutes": [dict(a, cluster_id=cid) for cid, lst in logi.get("allocation_plan", {}).get("allocation", {}).items() for a in lst if not a["default"]],
        "lifecycle": _lifecycle(db, intel),
        "alerts": [{"id": a.id, "severity": a.severity, "title": a.title, "body": a.body, "agent": a.agent, "created_at": a.created_at.isoformat()} for a in alerts],
        "last_run": {"id": run.id, "trigger": run.trigger, "status": run.status, "started_at": run.started_at.isoformat(),
                     "finished_at": run.finished_at.isoformat() if run.finished_at else None, "summary": run.summary} if run else None,
    }


def _lifecycle(db: Session, intel: dict) -> list[dict]:
    """Closed-loop feedback steps with live counts for the strongest stitching finding."""
    vf = next((v for v in intel.get("vendor_findings", []) if v["reason"] == "STITCHING"), None)
    if not vf:
        return []
    vid = vf["vendor_id"]
    recs = db.scalars(select(m.Recommendation).where(m.Recommendation.entity_id == vid)).all()
    qc = next((r for r in recs if r.kind == "pre_dispatch_qc"), None)
    hold = next((r for r in recs if r.kind == "vendor_qc_hold"), None)
    valerts = db.scalars(select(m.Alert).where(m.Alert.audience == "vendor", m.Alert.scope_id == vid)).all()
    portal = db.scalar(select(func.count(m.Return.id)).where(m.Return.vendor_id == vid, m.Return.created_via == "portal"))
    graded = db.scalar(select(func.count(m.Return.id)).where(m.Return.vendor_id == vid, m.Return.grade.isnot(None), m.Return.verified_reason == "STITCHING"))
    decisions = db.scalar(select(func.count(m.DecisionLog.id)).where(m.DecisionLog.recommendation_id.in_([r.id for r in recs]))) if recs else 0
    return [
        {"step": 1, "title": "Customer reports loose stitching", "metric": f"{vf['returns']} returns", "detail": f"{portal} filed through the portal in this session", "done": True},
        {"step": 2, "title": "Similar complaints identified", "metric": f"{vf['share']:.0%} vs {vf['network_share']:.0%}", "detail": f"z = {vf['z']:.1f} across {vf['vendor_returns']} vendor returns", "done": True},
        {"step": 3, "title": "Root cause linked to vendor + SKU", "metric": vf["vendor_name"], "detail": ", ".join(s["sku"] for s in vf["top_skus"][:3]), "done": True},
        {"step": 4, "title": "Pre-dispatch QC recommended", "metric": (qc.status if qc else "none"), "detail": "Prevention & Policy Agent", "done": bool(qc and qc.status == "approved")},
        {"step": 5, "title": "Vendor receives quality alert", "metric": f"{len(valerts)} alerts", "detail": f"{sum(a.acknowledged for a in valerts)} acknowledged by vendor", "done": any(a.acknowledged for a in valerts)},
        {"step": 6, "title": "Return Prediction monitors pattern", "metric": "7-day horizon", "detail": "Vendor exposure tracked in forecast breakdown", "done": True},
        {"step": 7, "title": "Returned stock graded and recovered", "metric": f"{graded} graded", "detail": "Inventory Recovery Agent, stitching defects", "done": graded > 0},
        {"step": 8, "title": "Outcomes recorded for learning", "metric": f"{decisions} decisions", "detail": "QC hold " + (hold.status if hold else "n/a") + "; decisions feed the next cycle", "done": decisions > 0},
    ]


@router.get("/alerts")
def alerts(db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    q = select(m.Alert).order_by(m.Alert.created_at.desc()).limit(60)
    if user.role in ("vendor", "logistics", "warehouse"):
        q = q.where(m.Alert.audience == user.role, m.Alert.scope_id == user.scope_id)
    elif user.role == "customer":
        return []
    rows = db.scalars(q).all()
    return [{"id": a.id, "severity": a.severity, "audience": a.audience, "title": a.title, "body": a.body, "agent": a.agent,
             "acknowledged": a.acknowledged, "created_at": a.created_at.isoformat(), "entity_type": a.entity_type, "entity_id": a.entity_id} for a in rows]


@router.post("/alerts/{alert_id}/ack")
def ack(alert_id: int, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    a = db.get(m.Alert, alert_id)
    if not a:
        raise HTTPException(404, "alert not found")
    if user.role in ("vendor", "logistics", "warehouse") and (a.audience != user.role or a.scope_id != user.scope_id):
        raise HTTPException(403, "not your alert")
    a.acknowledged = True
    actions.audit(db, user.name, "user", "alert.acknowledged", "alert", str(a.id), {"title": a.title})
    db.commit()
    return {"ok": True}


@router.get("/audit")
def audit(limit: int = 100, db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    rows = db.scalars(select(m.AuditLog).order_by(m.AuditLog.id.desc()).limit(min(limit, 500))).all()
    return [{"id": r.id, "ts": r.ts.isoformat(), "actor": r.actor, "actor_type": r.actor_type, "action": r.action,
             "entity_type": r.entity_type, "entity_id": r.entity_id, "detail": r.detail} for r in rows]


EDITABLE = {"resale", "governance", "llm", "fault_injection"}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: m.User = Depends(current_user)):
    return {k: st.get(db, k) for k in ("scenario", "resale", "governance", "llm", "fault_injection", "routing_overrides", "capacity_overrides")} | \
           {"llm_providers": llm.provider_status()}


class SettingIn(BaseModel):
    value: dict


@router.put("/settings/{key}")
def put_setting(key: str, body: SettingIn, db: Session = Depends(get_db), user: m.User = Depends(require("ops_manager"))):
    if key not in EDITABLE:
        raise HTTPException(400, f"{key} is not editable")
    prev = st.get(db, key)
    st.put(db, key, body.value)
    actions.audit(db, user.name, "user", "settings.updated", "setting", key, {"previous": prev, "new": body.value})
    db.commit()
    return {"ok": True, "key": key, "value": body.value}


@router.post("/admin/reset")
def admin_reset(db: Session = Depends(get_db), _: m.User = Depends(require("ops_manager"))):
    if bootstrap.status()["state"] in ("generating", "training", "orchestrating"):
        raise HTTPException(409, "reset already in progress")
    db.close()
    threading.Thread(target=bootstrap.reset, kwargs={"regenerate": True}, daemon=True).start()
    return {"ok": True, "detail": "Regenerating the synthetic dataset and re-running the agents (about 30 seconds)."}


@router.get("/integrations")
def integrations(db: Session = Depends(get_db), _: m.User = Depends(current_user)):
    url = str(db.bind.url)
    return [
        {"system": "Operational database", "status": "implemented", "detail": f"SQLAlchemy over {url.split(':')[0]}; portable schema, no vendor-specific SQL.",
         "sap_target": "SAP HANA Cloud", "pathway": "Point DATABASE_URL at HANA via sqlalchemy-hana; tables map 1:1 to HANA column tables."},
        {"system": "Analytics export", "status": "implemented", "detail": "Flat CSV datasets at /api/integrations/sac/{dataset}.csv (returns_fact, forecast, vendor_kpis, recovery_queue).",
         "sap_target": "SAP Analytics Cloud", "pathway": "Import as SAC datasets or expose via HANA calculation views for live models."},
        {"system": "LLM explanations", "status": "implemented (offline template)", "detail": "Provider-agnostic layer; OpenAI-compatible endpoint optional via env vars.",
         "sap_target": "SAP Generative AI Hub", "pathway": "Adapter boundary exists (SapGenAiHubProvider); not connected in this prototype."},
        {"system": "Agent orchestration & APIs", "status": "implemented locally", "detail": "FastAPI + dependency-ordered orchestrator with retries and audit.",
         "sap_target": "SAP BTP (Cloud Foundry / Kyma)", "pathway": "Containerise backend; XSUAA for roles; Destination service for SAP systems."},
        {"system": "Inventory & supply planning", "status": "proposed", "detail": "Not implemented.", "sap_target": "SAP IBP",
         "pathway": "Publish return forecasts as supply signals; consume recovered-stock availability."},
        {"system": "Transportation planning", "status": "proposed", "detail": "Not implemented.", "sap_target": "SAP Transportation Management",
         "pathway": "Send pickup allocation and re-route plans as freight units / orders."},
        {"system": "Supplier collaboration", "status": "proposed", "detail": "Not implemented.", "sap_target": "SAP Ariba / Business Network",
         "pathway": "Deliver vendor quality alerts and QC holds to supplier portal."},
    ]
