from __future__ import annotations

from collections import Counter

import pandas as pd
from sqlalchemy import text

from .. import llm
from ..ml import resale
from ..services import settings as st
from .base import Agent, AgentContext, AgentResult, alert, rec


def grade_priors(db) -> dict[str, dict[str, float]]:
    """P(grade | reason) from historical inspections."""
    g = pd.read_sql(text("SELECT verified_reason r, grade g FROM returns WHERE grade IS NOT NULL AND verified_reason IS NOT NULL"), db.bind)
    tab = g.groupby("r").g.value_counts(normalize=True).unstack(fill_value=0)
    return {r: {k: round(float(tab.loc[r].get(k, 0)), 3) for k in "ABC"} for r in tab.index}


def recovery_queue(db, scenario_date, cfg) -> list[dict]:
    q = pd.read_sql(text("""
        SELECT r.id, r.sku, r.status, r.price, r.facility_id, r.cluster_id, r.request_date, r.received_date, r.grade, r.predicted_reason,
               r.verified_reason, r.vendor_id, p.category, p.name
        FROM returns r JOIN products p ON p.sku=r.sku
        WHERE r.status IN ('pickup_scheduled','in_transit','received','inspected')
    """), db.bind, parse_dates=["request_date", "received_date"])
    pri = grade_priors(db)
    items = []
    for r in q.itertuples():
        if r.grade:
            g, pa = r.grade, 1.0 if r.grade == "A" else 0.0
            conf = 1.0
        else:
            dist = pri.get(r.verified_reason or r.predicted_reason, {"A": 0.6, "B": 0.3, "C": 0.1})
            g = max(dist, key=dist.get)
            pa, conf = dist.get("A", 0), dist[g]
        ready = {"pickup_scheduled": 3, "in_transit": 2, "received": 1, "inspected": 0}[r.status]
        items.append({"return_id": r.id, "sku": r.sku, "name": r.name, "category": r.category, "vendor_id": r.vendor_id, "status": r.status,
                      "facility_id": r.facility_id, "cluster_id": r.cluster_id, "price": float(r.price), "expected_grade": g,
                      "grade_known": bool(r.grade), "p_grade_a": round(float(pa), 3), "grade_confidence": round(float(conf), 3),
                      "ready_in_days": ready, "age_days": int((pd.Timestamp(scenario_date) - r.request_date).days)})
    return resale.prioritise(items, scenario_date, cfg)


class InventoryRecoveryAgent(Agent):
    id = "recovery"
    name = "Inventory Recovery"
    group = "Logistics & inventory"
    purpose = "Grade returns, decide restock / refurbish / redistribute, and sequence work by resale-window value."
    inputs = ["Inspection queue", "Grade history", "Seasonal demand index", "Refurbishment and storage costs", "Inbound plan"]
    depends_on = ["prediction", "logistics"]
    models = ["Resale Window Intelligence value model", "Grade priors P(grade | reason)"]

    def run(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        cfg = dict(resale.DEFAULTS, **(st.get(db, "resale", {}) or {}))
        resale.build_demand_index(db, ctx.scenario_date)
        queue = recovery_queue(db, ctx.scenario_date, cfg)
        provider = (ctx.settings.get("llm") or {}).get("provider", "template")
        recs, alerts = [], []
        fast = [i for i in queue if i["expected_grade"] == "A" and i["category"] in ("Lehenga", "Indo-western", "Festive dress")]
        top_fast = fast[:40]
        if top_fast:
            value = sum(i["value_if_fast"] for i in top_fast)
            decay = sum(i["decay_per_day"] for i in top_fast)
            txt, src = llm.explain("restock", dict(n=len(top_fast), value=value, decay=decay), provider)
            not_inspected = sum(1 for i in top_fast if not i["grade_known"])
            recs.append(rec("rapid_restock", f"Inspect {len(top_fast)} festive items first: they are probably like new", txt,
                            {"items": [{k: i[k] for k in ("return_id", "sku", "name", "facility_id", "value_if_fast", "value_at_risk_7d", "p_grade_a", "grade_known")} for i in top_fast],
                             "not_yet_inspected": not_inspected,
                             "condition_basis": "Predicted from the return reason and past inspections, not seen yet. Nothing goes back on sale until it passes inspection.",
                             "method": "Sorted by value lost if delayed 7 days (Resale Window Intelligence)"},
                            "queue", "festive-grade-a", impact=sum(i["value_at_risk_7d"] for i in top_fast), cost=0, confidence=0.72,
                            priority="high", source=src))
        grade_b = [i for i in queue if i["grade_known"] and i["expected_grade"] == "B"]
        if grade_b:
            value = sum(i["value_if_fast"] for i in grade_b)
            cost = sum(i["price"] * cfg["refurb_cost_pct"] for i in grade_b)
            txt, src = llm.explain("refurbish", dict(n=len(grade_b), value=value, cost=cost), provider)
            recs.append(rec("refurbish_batch", f"Repair and resell {len(grade_b)} items that need small fixes", txt,
                            {"items": [{k: i[k] for k in ("return_id", "sku", "name", "facility_id", "value_if_fast")} for i in grade_b[:60]]},
                            "batch", "grade-b-current", impact=value, cost=cost, confidence=0.8, source=src))
        # redistribution: inspected Grade-A stock sitting in clusters with lower near-term demand than the network
        demand = pd.read_sql(text("""SELECT o.cluster_id, p.category, COUNT(*) n FROM orders o JOIN products p ON p.sku=o.sku
                                     WHERE o.order_date >= :s GROUP BY 1, 2"""), db.bind, params={"s": ctx.scenario_date.replace(day=1)})
        grade_a_known = [i for i in queue if i["grade_known"] and i["expected_grade"] == "A"]
        redistribution = []
        for cat in {i["category"] for i in grade_a_known}:
            d = demand[demand.category == cat].set_index("cluster_id").n
            if d.empty:
                continue
            share_d = d / d.sum()
            stock = Counter(i["cluster_id"] for i in grade_a_known if i["category"] == cat)
            tot = sum(stock.values())
            for cid, k in stock.items():
                excess = k - share_d.get(cid, 0) * tot
                if excess >= 2:
                    dest = share_d.drop(cid, errors="ignore").idxmax()
                    redistribution.append({"category": cat, "from_cluster": cid, "to_cluster": dest, "units": int(excess)})
        if redistribution:
            recs.append(rec("redistribute", f"Move {sum(r['units'] for r in redistribution)} like-new items to cities where they sell faster",
                            "Inspected Grade-A stock is concentrated where near-term demand is lower than its share; moving it to the cluster with the highest current demand shortens time to sale.",
                            {"moves": redistribution}, "batch", "redistribution-current", impact=sum(r["units"] for r in redistribution) * 300,
                            cost=sum(r["units"] for r in redistribution) * 55, confidence=0.6, source="template"))
        qc_vendors = set(ctx.state.get("_qc_vendors", []))
        blocked = [i for i in top_fast if i["vendor_id"] in qc_vendors]
        grade_mix = Counter(i["expected_grade"] for i in queue)
        out = {"queue_size": len(queue), "grade_mix_expected": dict(grade_mix),
               "value_in_queue_inr": round(sum(i["value_if_fast"] for i in queue)),
               "value_at_risk_7d_inr": round(sum(i["value_at_risk_7d"] for i in queue)),
               "top_priority": [{k: i[k] for k in ("priority_rank", "return_id", "name", "expected_grade", "value_if_fast", "value_at_risk_7d")} for i in queue[:8]],
               "fast_track_from_qc_vendors": len(blocked), "redistribution_moves": redistribution[:6]}
        if queue:
            alerts.append(alert("medium", "warehouse", f"Value-priority sequence ready: {len(top_fast)} items to fast-track",
                                f"₹{out['value_at_risk_7d_inr']:,} of queue value is lost if the current queue waits 7 more days.", "queue", "festive-grade-a"))
        ctx.state["_fast_track"] = top_fast
        return AgentResult(outputs=out, recommendations=recs, alerts=alerts)
