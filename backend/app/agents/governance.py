from __future__ import annotations

from .. import llm
from ..ml import anomaly
from .base import Agent, AgentContext, AgentResult, alert, rec

# kind -> (approval rule, approver role, description)
#   "always": a human must decide;  "limit": auto-approve under the cost cap, else human
POLICY = {
    "vendor_qc_hold": ("always", "vendor_quality_manager", "Vendor restriction"),
    "pre_dispatch_qc": ("always", "vendor_quality_manager", "Vendor process change"),
    "size_chart_update": ("always", "vendor_quality_manager", "Listing change"),
    "listing_fix": ("always", "vendor_quality_manager", "Listing change"),
    "exchange_first": ("always", "ops_manager", "Return-policy change"),
    "reroute": ("limit", "ops_manager", "Logistics move"),
    "extra_pickup": ("limit", "ops_manager", "Logistics spend"),
    "inspection_overtime": ("limit", "warehouse_manager", "Warehouse spend"),
    "rapid_restock": ("limit", "warehouse_manager", "Processing order"),
    "refurbish_batch": ("limit", "warehouse_manager", "Refurbishment spend"),
    "redistribute": ("limit", "ops_manager", "Inventory move"),
    "integrity_inspection": ("always", "dispute_reviewer", "Customer-affecting check"),
}
FORBIDDEN = {"customer_rejection", "customer_penalty", "vendor_suspension", "refund_block"}


class GovernanceAgent(Agent):
    id = "governance"
    name = "Compliance & Governance"
    group = "Compliance & HITL"
    purpose = "Evidence-based integrity checks, guardrails, cost-limit approvals, decision logging and human-in-the-loop routing."
    inputs = ["All agent recommendations", "Pickup evidence (tag, serial, weight)", "Approval policies and cost limits", "Role permissions"]
    depends_on = ["intelligence", "prevention", "logistics", "recovery"]
    models = ["IsolationForest + hard-evidence rules", "Policy rules engine"]

    def run(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        provider = (ctx.settings.get("llm") or {}).get("provider", "template")
        limit = (ctx.settings.get("governance") or {}).get("auto_approve_logistics_limit_inr", 25000)
        anomaly.train(db) if anomaly._model is None else None
        ids = [ctx.event["return_id"]] if ctx.event.get("return_id") and ctx.trigger == "pickup_completed" else None
        cases = anomaly.score(db, return_ids=ids)
        flagged = [c for c in cases if c["hard_evidence"]]
        recs, alerts = [], []
        for c in flagged:
            txt, src = llm.explain("integrity", dict(rid=c["return_id"], evidence="; ".join(c["evidence"]).lower()), provider)
            recs.append(rec("integrity_inspection", f"Take a closer look at return {c['return_id']}", txt,
                            {"case": c, "no_automatic_action": True,
                             "customer_impact": "Refund timeline unchanged until a reviewer decides; customer sees a neutral 'additional quality check' status."},
                            "return", c["return_id"], impact=0, cost=120, confidence=c["score"], priority="high" if c["score"] >= 0.7 else "medium",
                            source=src))
        if flagged:
            alerts.append(alert("high", "ops_manager", f"{len(flagged)} returns need physical inspection (tag / serial evidence)",
                                "Anomaly signals only. No customer action is taken automatically.", "queue", "integrity"))
        # guardrails over every recommendation produced in this run
        produced = ctx.state.get("_all_recs", []) + recs
        checks = []
        conflict_entities = {e for cf in ctx.conflicts for e in cf.get("entities", [])}
        for r in produced:
            if r["kind"] in FORBIDDEN:
                r["_blocked"] = True
                checks.append({"kind": r["kind"], "entity": r["entity_id"], "result": "blocked", "rule": "forbidden automated action"})
                continue
            rule, role, label = POLICY.get(r["kind"], ("always", "ops_manager", "Unclassified"))
            needs = rule == "always" or r["cost_inr"] > limit or r["entity_id"] in conflict_entities
            r["requires_approval"] = needs
            r["approver_role"] = role
            why = "policy: human decision required" if rule == "always" else (
                f"cost ₹{r['cost_inr']:,.0f} above ₹{limit:,.0f} pre-authorised limit" if r["cost_inr"] > limit else
                ("involved in a cross-agent conflict" if r["entity_id"] in conflict_entities else f"within ₹{limit:,.0f} pre-authorised limit"))
            checks.append({"kind": r["kind"], "entity": r["entity_id"], "category": label, "result": "route to human" if needs else "auto-approve",
                           "approver_role": role if needs else "system (pre-authorised)", "reason": why})
        out = {"integrity_cases_scored": len(cases), "integrity_flags": len(flagged),
               "flagged": [{k: c[k] for k in ("return_id", "score", "evidence")} for c in flagged[:20]],
               "guardrail_checks": checks, "routed_to_humans": sum(1 for c in checks if c["result"] == "route to human"),
               "auto_approved": sum(1 for c in checks if c["result"] == "auto-approve"),
               "policy": "Anomalies trigger inspection requests only. Customer rejections, penalties and vendor suspensions are never automated."}
        return AgentResult(outputs=out, recommendations=recs, alerts=alerts)
