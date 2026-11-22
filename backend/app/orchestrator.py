"""Central Agent Orchestrator.

1. Receives an operational event (full cycle, return created, pickup completed,
   inspection completed).
2. Selects the agents the event needs and orders them by dependency.
3. Executes each agent with retries, passing a shared state between them and
   recording agent-to-agent messages.
4. Detects conflicting recommendations across agents.
5. Lets the Compliance & Governance agent apply guardrails and route decisions.
6. Persists recommendations, alerts, agent runs and an audit trail.
"""
from __future__ import annotations

import hashlib
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from . import models as m
from .agents.base import AgentContext
from .agents.governance import GovernanceAgent
from .agents.intelligence import IntelligenceAgent
from .agents.logistics import ReverseLogisticsAgent
from .agents.prediction import ReturnPredictionAgent
from .agents.prevention import PreventionAgent
from .agents.recovery import InventoryRecoveryAgent
from .db import SessionLocal
from .services import actions
from .services import settings as st

AGENTS = {a.id: a for a in [ReturnPredictionAgent(), IntelligenceAgent(), PreventionAgent(), ReverseLogisticsAgent(),
                            InventoryRecoveryAgent(), GovernanceAgent()]}
ORDER = ["prediction", "intelligence", "prevention", "logistics", "recovery", "governance"]
PLANS = {
    "full_cycle": ORDER,
    "return_created": ORDER,
    "pickup_completed": ["logistics", "governance"],
    "inspection_completed": ["intelligence", "prevention", "recovery", "governance"],
}
MAX_ATTEMPTS = 3
_lock = threading.Lock()


def _json(o):
    """Make outputs JSON-safe (dates, numpy)."""
    import numpy as np
    from datetime import date
    if isinstance(o, dict):
        return {str(k): _json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json(v) for v in o]
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, np.generic):
        return o.item()
    return o


def detect_conflicts(ctx: AgentContext) -> list[dict]:
    out = []
    fast = ctx.state.get("_fast_track", [])
    qc = set(ctx.state.get("_qc_vendors", []))
    hit = [i for i in fast if i["vendor_id"] in qc]
    if hit:
        out.append({"type": "restock_vs_quality_hold", "agents": ["recovery", "prevention"],
                    "description": f"{len(hit)} fast-track restock items come from vendors proposed for QC action ({', '.join(sorted({i['vendor_id'] for i in hit}))}).",
                    "resolution": "Fast-track is kept, but these items get an enhanced stitching inspection before restock; the fast-track decision is routed to a human.",
                    "entities": ["festive-grade-a"], "items": [i["return_id"] for i in hit][:20]})
    recs = ctx.state.get("_all_recs", [])
    ex = [r for r in recs if r["kind"] == "exchange_first"]
    gaps = {g["cluster_id"]: g for g in (ctx.state.get("logistics", {}).get("capacity_gaps", []))}
    tight = [g for g in gaps.values() if g["pickup_gap"] > 0]
    if ex and tight:
        out.append({"type": "exchange_first_vs_pickup_capacity", "agents": ["prevention", "logistics"],
                    "description": f"Exchange-first creates an outbound delivery plus a reverse pickup per exchange, while {len(tight)} clusters already lack pickup capacity "
                                   f"({', '.join(g['city'] for g in tight)}).",
                    "resolution": "Approve exchange-first together with the extra-pickup bookings for the affected clusters, or defer exchange-first until after the peak.",
                    "entities": [r["entity_id"] for r in ex]})
    rr = ctx.state.get("_reroutes", [])
    if rr and fast:
        decay = sum(i["decay_per_day"] for i in fast) / max(len(fast), 1)
        out.append({"type": "reroute_vs_recovery_speed", "agents": ["logistics", "recovery"],
                    "description": f"Re-routing adds one transit day for diverted units; for likely Grade-A festive stock that costs about INR {decay:,.0f} per item.",
                    "resolution": "Divert non-festive and likely Grade-B/C returns first; keep likely Grade-A festive items at the default facility.",
                    "entities": [r["entity_id"] for r in rr]})
    return out


def _rec_id(kind: str, entity: str) -> str:
    return "RC-" + hashlib.sha1(f"{kind}|{entity}".encode()).hexdigest()[:10].upper()


def _persist_recs(db, run_id: str, recs: list[dict], agent_of: dict) -> dict:
    created = updated = auto = 0
    now = datetime.now()
    for r in recs:
        if r.get("_blocked"):
            continue
        rid = _rec_id(r["kind"], r["entity_id"])
        row = db.get(m.Recommendation, rid)
        fields = {k: r[k] for k in ("kind", "title", "rationale", "entity_type", "entity_id", "impact_inr", "cost_inr", "confidence", "priority", "explanation_source")}
        fields["evidence"] = _json(r["evidence"])
        if row:
            if row.status in ("pending", "escalated"):
                for k, v in fields.items():
                    setattr(row, k, v)
                row.run_id = run_id
                row.updated_at = now
                updated += 1
            continue
        row = m.Recommendation(id=rid, run_id=run_id, agent=agent_of.get(id(r), "governance"), status="pending",
                               requires_approval=r.get("requires_approval", True), approver_role=r.get("approver_role", "ops_manager"),
                               created_at=now, updated_at=now, **fields)
        db.add(row)
        db.flush()
        created += 1
        if not row.requires_approval:
            row.status = "approved"
            db.add(m.DecisionLog(recommendation_id=rid, user_id="system", user_name="System (pre-authorised workflow)", role="system", ts=now,
                                 action="auto_approve", reason="Within pre-authorised limits set by Compliance & Governance policy",
                                 previous_status="pending", new_status="approved"))
            actions.apply(db, row, "system (pre-authorised)")
            auto += 1
    return {"created": created, "updated": updated, "auto_approved": auto}


def _persist_alerts(db, run_id: str, alerts: list[dict], agent_of: dict):
    since = datetime.now() - timedelta(days=2)
    existing = {(a.title, a.scope_id) for a in db.scalars(select(m.Alert).where(m.Alert.created_at >= since, m.Alert.acknowledged.is_(False))).all()}
    n = 0
    for a in alerts:
        if (a["title"], a["scope_id"]) in existing:
            continue
        db.add(m.Alert(run_id=run_id, created_at=datetime.now(), agent=agent_of.get(id(a), "orchestrator"), acknowledged=False, **a))
        existing.add((a["title"], a["scope_id"]))
        n += 1
    return n


def create_run(trigger: str, event: dict | None = None) -> str:
    if trigger not in PLANS:
        raise ValueError(f"unknown trigger {trigger}")
    run_id = "RUN-" + uuid.uuid4().hex[:10].upper()
    plan = PLANS[trigger]
    with SessionLocal() as db:
        db.add(m.OrchestratorRun(id=run_id, trigger=trigger, event=event or {}, plan=plan, status="queued", started_at=datetime.now(),
                                 conflicts=[], summary={}))
        db.flush()
        for aid in plan:
            db.add(m.AgentRun(run_id=run_id, agent=aid, status="queued", attempts=0, inputs={}, outputs={}))
        db.commit()
    return run_id


def execute(run_id: str) -> dict:
    with _lock:  # one orchestration at a time over the shared state
        db = SessionLocal()
        try:
            return _execute(db, run_id)
        finally:
            db.close()


def _execute(db, run_id: str) -> dict:
    run = db.get(m.OrchestratorRun, run_id)
    run.status = "running"
    db.commit()
    ctx = AgentContext(db=db, run_id=run_id, trigger=run.trigger, event=run.event or {}, scenario_date=st.scenario_date(db),
                       settings={k: st.get(db, k, {}) for k in ("llm", "governance", "resale")})
    ctx.state["_all_recs"] = []
    agent_of: dict = {}
    all_alerts = []
    failed = set()
    for aid in run.plan:
        agent = AGENTS[aid]
        ar = db.scalars(select(m.AgentRun).where(m.AgentRun.run_id == run_id, m.AgentRun.agent == aid)).first()
        missing = [d for d in agent.depends_on if d in failed]
        if missing and aid != "governance":
            ar.status, ar.error = "skipped", f"upstream failed: {', '.join(missing)}"
            db.commit()
            failed.add(aid)
            continue
        if aid == "governance":
            ctx.conflicts = detect_conflicts(ctx)
            for c in ctx.conflicts:
                for a in c["agents"]:
                    ctx.send("orchestrator", a, "conflict", {"type": c["type"]})
        ar.status, ar.started_at = "running", datetime.now()
        ar.inputs = _json({"trigger": run.trigger, "event": run.event, "data_sources": agent.inputs,
                           "upstream": [d for d in agent.depends_on if d in ctx.state]})
        db.commit()
        t0 = time.perf_counter()
        last_err = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            ar.attempts = attempt
            db.commit()
            try:
                fi = st.get(db, "fault_injection", {}) or {}
                if fi.get("agent") == aid and fi.get("failures", 0) > 0:
                    st.put(db, "fault_injection", {"agent": aid, "failures": fi["failures"] - 1})
                    raise RuntimeError("Injected transient fault (Settings > Fault injection)")
                res = agent.run(ctx)
                last_err = None
                break
            except Exception as e:  # retry transient failures
                db.rollback()
                last_err = f"{type(e).__name__}: {e}"
                ar = db.scalars(select(m.AgentRun).where(m.AgentRun.run_id == run_id, m.AgentRun.agent == aid)).first()
                ar.error = f"attempt {attempt}: {last_err}"
                db.commit()
                if attempt < MAX_ATTEMPTS:
                    time.sleep(0.4 * attempt)
                else:
                    traceback.print_exc()
        ar = db.scalars(select(m.AgentRun).where(m.AgentRun.run_id == run_id, m.AgentRun.agent == aid)).first()
        ar.finished_at = datetime.now()
        ar.duration_ms = int((time.perf_counter() - t0) * 1000)
        if last_err:
            ar.status, ar.error = "failed", last_err
            failed.add(aid)
            db.commit()
            continue
        ctx.state[aid] = res.outputs
        for r in res.recommendations:
            agent_of[id(r)] = aid
        for a in res.alerts:
            agent_of[id(a)] = aid
        ctx.state["_all_recs"].extend(res.recommendations)
        all_alerts.extend(res.alerts)
        ar.status = "completed"
        ar.outputs = _json(res.outputs)
        if ar.attempts > 1:
            ar.error = f"recovered after {ar.attempts - 1} failed attempt(s)"
        db.commit()
    for msg in ctx.messages:
        db.add(m.AgentMessage(run_id=run_id, ts=msg["ts"], sender=msg["sender"], receiver=msg["receiver"], topic=msg["topic"], payload=_json(msg["payload"])))
    rec_stats = _persist_recs(db, run_id, ctx.state["_all_recs"], agent_of)
    n_alerts = _persist_alerts(db, run_id, all_alerts, agent_of)
    run = db.get(m.OrchestratorRun, run_id)
    run.conflicts = _json(ctx.conflicts)
    run.finished_at = datetime.now()
    run.status = "completed" if not failed else ("partial" if len(failed) < len(run.plan) else "failed")
    pending = db.query(m.Recommendation).filter(m.Recommendation.status.in_(["pending", "escalated"])).count()
    run.summary = {"recommendations": rec_stats, "alerts": n_alerts, "conflicts": len(ctx.conflicts), "failed_agents": sorted(failed),
                   "pending_approvals": pending, "messages": len(ctx.messages)}
    actions.audit(db, "orchestrator", "system", "orchestrator.run", "run", run_id, run.summary)
    db.commit()
    return run.summary


def run_async(trigger: str, event: dict | None = None) -> str:
    run_id = create_run(trigger, event)
    threading.Thread(target=execute, args=(run_id,), daemon=True).start()
    return run_id


def run_sync(trigger: str, event: dict | None = None) -> tuple[str, dict]:
    run_id = create_run(trigger, event)
    return run_id, execute(run_id)
