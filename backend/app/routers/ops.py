from __future__ import annotations

from copy import deepcopy
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import orchestrator
from ..agents.prediction import latest_forecast
from ..agents.recovery import recovery_queue
from ..db import get_db
from ..ml import anomaly, resale
from ..rbac import current_user, require
from ..services import actions
from ..services import settings as st
from ..simulation import twin

router = APIRouter()


# ---------------- Digital Twin ----------------
@router.get("/twin/defaults")
def twin_defaults(source: str = "deck", db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    p = deepcopy(twin.DEFAULTS)
    note = "Default illustrative scenario from the presentation (Pune +1,200/day, Ahmedabad +800/day, Jaipur +600/day)."
    if source == "forecast":
        fc = latest_forecast(db)
        if not fc:
            raise HTTPException(503, "No forecast available")
        D = st.scenario_date(db)
        by = {c["cluster_id"]: c for c in fc["clusters"]}
        co = st.capacity_overrides(db)
        for c in p["clusters"]:
            f = by[c["id"]]
            c["base"] = f["network_normal_daily"]
            c["additional"] = max(0, f["additional_network_at_peak"])
            c["vehicles"] += co.get(f"vehicles:{c['id']}", 0)
        peaks = [(date.fromisoformat(by[c["id"]]["peak_day"]) - D).days for c in p["clusters"] if by[c["id"]]["peak_day"]]
        if peaks:
            p["peak_day"] = int(round(sum(peaks) / len(peaks)))
        ro = st.routing_overrides(db)
        for cid, alloc in ro.items():
            if cid in p["allocation"]:
                p["allocation"][cid] = alloc
        note = "Loaded from the Return Prediction Agent's latest forecast (network-scale peak volumes) and approved capacity / routing changes."
    return {"params": p, "scenarios": twin.SCENARIOS, "note": note}


class TwinIn(BaseModel):
    params: dict = {}
    scenarios: list[str] | None = None


@router.post("/twin/simulate")
def twin_simulate(body: TwinIn, _: m.User = Depends(require("internal"))):
    p = body.params or {}
    if p.get("replications", 40) > 200 or p.get("days", 14) > 45:
        raise HTTPException(400, "replications <= 200 and days <= 45")
    if p.get("processing_minutes", 12) <= 0:
        raise HTTPException(400, "processing_minutes must be positive")
    try:
        return twin.run(p, body.scenarios)
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(400, f"invalid parameters: {e}")


# ---------------- Inventory recovery ----------------
@router.get("/recovery/queue")
def rec_queue(limit: int = 200, db: Session = Depends(get_db), _: m.User = Depends(require("internal", "warehouse"))):
    D = st.scenario_date(db)
    cfg = dict(resale.DEFAULTS, **(st.get(db, "resale", {}) or {}))
    resale.build_demand_index(db, D)
    q = recovery_queue(db, D, cfg)
    fast = set((st.get(db, "fast_track", {}) or {}).get("return_ids", []))
    for i in q:
        i["fast_track"] = i["return_id"] in fast
    fifo = sorted(q, key=lambda x: -x["age_days"])
    # what FIFO vs value-priority means for the first N items processed (daily sample capacity)
    n = max(1, len(q) // 3)
    return {"scenario_date": D.isoformat(), "config": cfg, "items": q[:limit], "total": len(q),
            "totals": {"value_if_fast": round(sum(i["value_if_fast"] for i in q)), "value_at_risk_7d": round(sum(i["value_at_risk_7d"] for i in q))},
            "comparison": {"first_n": n, "value_priority_protected": round(sum(i["value_at_risk_7d"] for i in q[:n])),
                           "fifo_protected": round(sum(i["value_at_risk_7d"] for i in fifo[:n]))},
            "grade_mix": {g: sum(1 for i in q if i["expected_grade"] == g) for g in "ABC"},
            "by_action": {a: sum(1 for i in q if {"A": "restock", "B": "refurbish", "C": "liquidate / RTV"}[i["expected_grade"]] == a) for a in ("restock", "refurbish", "liquidate / RTV")}}


@router.get("/recovery/curve")
def rec_curve(price: float = 7999, category: str = "Lehenga", days: int = 120, db: Session = Depends(get_db), _: m.User = Depends(require("internal", "warehouse"))):
    D = st.scenario_date(db)
    cfg = dict(resale.DEFAULTS, **(st.get(db, "resale", {}) or {}))
    resale.build_demand_index(db, D)
    return {"category": category, "price": price, "curves": {g: resale.curve(price, category, g, D, cfg, min(days, 200)) for g in "ABC"},
            "model": resale.__doc__}


# ---------------- Approvals ----------------
def _rec_dict(r: m.Recommendation, logs: list | None = None) -> dict:
    d = {k: getattr(r, k) for k in ("id", "run_id", "agent", "kind", "title", "rationale", "evidence", "entity_type", "entity_id", "impact_inr", "cost_inr",
                                    "confidence", "priority", "requires_approval", "approver_role", "status", "applied", "explanation_source")}
    d["created_at"], d["updated_at"] = r.created_at.isoformat(), r.updated_at.isoformat()
    if logs is not None:
        d["decisions"] = [{"user": l.user_name, "role": l.role, "ts": l.ts.isoformat(), "action": l.action, "reason": l.reason,
                           "previous_status": l.previous_status, "new_status": l.new_status} for l in logs]
    return d


@router.get("/approvals")
def approvals(status: str | None = None, kind: str | None = None, db: Session = Depends(get_db), user: m.User = Depends(require("internal"))):
    q = select(m.Recommendation).order_by(m.Recommendation.created_at.desc())
    if status:
        q = q.where(m.Recommendation.status == status)
    if kind:
        q = q.where(m.Recommendation.kind == kind)
    rows = db.scalars(q).all()
    logs = {}
    for l in db.scalars(select(m.DecisionLog).order_by(m.DecisionLog.ts)).all():
        logs.setdefault(l.recommendation_id, []).append(l)
    out = []
    for r in rows:
        d = _rec_dict(r, logs.get(r.id, []))
        ok, why = actions.can_decide(user, r)
        d["can_decide"] = ok and r.status in ("pending", "escalated")
        d["decide_reason"] = why
        out.append(d)
    counts = {}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    return {"items": out, "counts": counts}


class DecisionIn(BaseModel):
    action: str
    reason: str


@router.post("/approvals/{rec_id}/decision")
def decide(rec_id: str, body: DecisionIn, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    r = db.get(m.Recommendation, rec_id)
    if not r:
        raise HTTPException(404, "recommendation not found")
    try:
        return actions.decide(db, r, user, body.action, body.reason)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/integrity/cases")
def integrity_cases(db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    cases = anomaly.score(db)
    recs = {r.entity_id: r for r in db.scalars(select(m.Recommendation).where(m.Recommendation.kind == "integrity_inspection")).all()}
    logs = {}
    for l in db.scalars(select(m.DecisionLog).order_by(m.DecisionLog.ts)).all():
        logs.setdefault(l.recommendation_id, []).append(l)
    out = []
    for c in sorted(cases, key=lambda x: -x["score"]):
        r = recs.get(c["return_id"])
        if not (c["hard_evidence"] or c["score"] >= 0.3 or r):
            continue
        c = dict(c, customer_id=None)  # reviewers see evidence, not identity, by default
        c["recommendation"] = _rec_dict(r, logs.get(r.id, [])) if r else None
        c["recommended_inspection"] = ("Physical inspection: verify brand tag, match serial label, weigh parcel against dispatch record"
                                       if c["hard_evidence"] else "No inspection required; behavioural signal only (monitor)")
        out.append(c)
    return {"cases": out, "policy": "An anomaly is not proof of misuse. No return is rejected automatically.", "model": anomaly.FEATURES}


# ---------------- Orchestrator ----------------
class RunIn(BaseModel):
    trigger: str = "full_cycle"
    event: dict = {}


@router.post("/orchestrator/run")
def start_run(body: RunIn, user: m.User = Depends(require("internal"))):
    if body.trigger not in orchestrator.PLANS:
        raise HTTPException(400, f"trigger must be one of {list(orchestrator.PLANS)}")
    rid = orchestrator.run_async(body.trigger, dict(body.event, requested_by=user.name))
    return {"run_id": rid}


@router.get("/orchestrator/runs")
def runs(limit: int = 20, db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    rows = db.scalars(select(m.OrchestratorRun).order_by(m.OrchestratorRun.started_at.desc()).limit(limit)).all()
    return [{"id": r.id, "trigger": r.trigger, "status": r.status, "started_at": r.started_at.isoformat(),
             "finished_at": r.finished_at.isoformat() if r.finished_at else None, "summary": r.summary, "event": r.event, "plan": r.plan} for r in rows]


@router.get("/orchestrator/runs/{run_id}")
def run_detail(run_id: str, db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    r = db.get(m.OrchestratorRun, run_id)
    if not r:
        raise HTTPException(404, "run not found")
    agents = db.scalars(select(m.AgentRun).where(m.AgentRun.run_id == run_id).order_by(m.AgentRun.id)).all()
    msgs = db.scalars(select(m.AgentMessage).where(m.AgentMessage.run_id == run_id).order_by(m.AgentMessage.id)).all()
    recs = db.scalars(select(m.Recommendation).where(m.Recommendation.run_id == run_id)).all()
    return {"id": r.id, "trigger": r.trigger, "status": r.status, "event": r.event, "plan": r.plan, "started_at": r.started_at.isoformat(),
            "finished_at": r.finished_at.isoformat() if r.finished_at else None, "summary": r.summary, "conflicts": r.conflicts,
            "agents": [{"agent": a.agent, "status": a.status, "attempts": a.attempts, "duration_ms": a.duration_ms, "error": a.error,
                        "started_at": a.started_at.isoformat() if a.started_at else None, "inputs": a.inputs, "outputs": a.outputs} for a in agents],
            "messages": [{"ts": x.ts.isoformat(), "sender": x.sender, "receiver": x.receiver, "topic": x.topic, "payload": x.payload} for x in msgs],
            "human_requests": [{"id": x.id, "title": x.title, "approver_role": x.approver_role, "status": x.status, "agent": x.agent}
                               for x in recs if x.requires_approval]}


@router.get("/agents")
def agents(_: m.User = Depends(current_user)):
    return {"agents": [orchestrator.AGENTS[a].describe() for a in orchestrator.ORDER],
            "plans": orchestrator.PLANS, "max_attempts": orchestrator.MAX_ATTEMPTS}


@router.get("/governance/policy")
def policy(db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    from ..agents.governance import FORBIDDEN, POLICY
    gov = st.get(db, "governance", {}) or {}
    users = db.scalars(select(m.User).where(m.User.role.in_(["ops_manager", "vendor_quality_manager", "warehouse_manager", "dispute_reviewer"]))).all()
    return {"rules": [{"kind": k, "rule": v[0], "approver_role": v[1], "category": v[2]} for k, v in POLICY.items()],
            "forbidden": sorted(FORBIDDEN), "auto_approve_limit_inr": gov.get("auto_approve_logistics_limit_inr", 25000),
            "approvers": [{"name": u.name, "role": u.role, "approval_limit": u.approval_limit} for u in users]}
