from __future__ import annotations

import math
from datetime import timedelta

import numpy as np
from scipy.optimize import linprog
from sqlalchemy import select, text

from .. import llm
from .. import models as m
from ..services import settings as st
from .base import Agent, AgentContext, AgentResult, alert, rec
from .prediction import latest_forecast

ROAD_FACTOR = 1.25
MAX_KM = 600
BACKLOG_PENALTY = 150.0  # INR per unit left in overflow (value decay + storage over ~2 days), illustrative
SURGE_PICKUP_COST = 112.0
OVERTIME_PREMIUM = 18.0


def haversine(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def transfer_cost(km: float) -> float:
    return 8.0 + 0.12 * km


def plan_allocation(volumes: dict[str, float], clusters, facilities, overrides: dict | None = None) -> dict:
    """Linear programme: route each cluster's planning-day volume to facilities.

    min  sum(c,f) (handling_f + transfer_cf) x_cf + penalty * overflow_f
    s.t. sum_f x_cf = V_c ; sum_c x_cf - overflow_f <= capacity_f - local_f ; x, overflow >= 0
    """
    fac = {f.id: f for f in facilities}
    default_of = {c.id: c.default_facility_id for c in clusters}
    normal_by_fac = {}
    for c in clusters:
        normal_by_fac[c.default_facility_id] = normal_by_fac.get(c.default_facility_id, 0) + c.network_daily_returns
    local = {f.id: max(0, f.normal_load - normal_by_fac.get(f.id, 0)) for f in facilities}
    cap = {f.id: f.inspection_capacity + (overrides or {}).get(f.id, 0) for f in facilities}
    pairs, costs, kms = [], [], {}
    for c in clusters:
        for f in facilities:
            km = haversine(c.lat, c.lon, f.lat, f.lon) * ROAD_FACTOR
            if f.id == default_of[c.id] or km <= MAX_KM:
                pairs.append((c.id, f.id))
                kms[(c.id, f.id)] = km
                costs.append(f.handling_cost + (0 if f.id == default_of[c.id] else transfer_cost(km)))
    fids = [f.id for f in facilities]
    n_x, n_o = len(pairs), len(fids)
    cvec = np.array(costs + [BACKLOG_PENALTY] * n_o)
    A_eq, b_eq = [], []
    for c in clusters:
        row = [1.0 if p[0] == c.id else 0.0 for p in pairs] + [0.0] * n_o
        A_eq.append(row)
        b_eq.append(volumes.get(c.id, 0.0))
    A_ub, b_ub = [], []
    for j, fid in enumerate(fids):
        row = [1.0 if p[1] == fid else 0.0 for p in pairs] + [(-1.0 if k == j else 0.0) for k in range(n_o)]
        A_ub.append(row)
        b_ub.append(max(0.0, cap[fid] - local[fid]))
    res = linprog(cvec, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=[(0, None)] * (n_x + n_o), method="highs")
    if not res.success:
        raise RuntimeError(f"allocation LP failed: {res.message}")
    x = res.x[:n_x]
    over = res.x[n_x:]
    alloc = {}
    for (cid, fid), val in zip(pairs, x):
        if val > 0.5:
            alloc.setdefault(cid, []).append({"facility_id": fid, "units": round(float(val)), "share": round(float(val) / max(volumes.get(cid, 1), 1), 3),
                                               "km": round(kms[(cid, fid)]), "default": fid == default_of[cid],
                                               "unit_cost": round(fac[fid].handling_cost + (0 if fid == default_of[cid] else transfer_cost(kms[(cid, fid)])), 2)})
    fac_load = {fid: {"capacity": cap[fid], "local": local[fid], "assigned": round(float(sum(v for (c_, f_), v in zip(pairs, x) if f_ == fid))),
                      "overflow": round(float(over[j]))} for j, fid in enumerate(fids)}
    return {"allocation": alloc, "facilities": fac_load, "objective_inr": round(float(res.fun), 2), "solver": "scipy HiGHS linear programme"}


class ReverseLogisticsAgent(Agent):
    id = "logistics"
    name = "Reverse Logistics"
    group = "Logistics & inventory"
    purpose = "Predict pickup needs, find PIN-cluster capacity gaps, optimise pickup and facility allocation, monitor SLAs."
    inputs = ["Volume forecast", "3PL fleet capacity", "Facility inspection capacity", "Distances", "Pickup SLA history"]
    depends_on = ["prediction"]
    models = ["Linear programme (HiGHS) for facility allocation", "Capacity gap analysis"]

    def run(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        fc = latest_forecast(db)
        clusters = db.scalars(select(m.PinCluster)).all()
        facilities = db.scalars(select(m.Facility)).all()
        providers = db.scalars(select(m.LogisticsProvider)).all()
        cap_over = st.capacity_overrides(db)
        provider = (ctx.settings.get("llm") or {}).get("provider", "template")
        auto_limit = (ctx.settings.get("governance") or {}).get("auto_approve_logistics_limit_inr", 25000)
        plan_vol, surge_days = {}, {}
        for c in fc["clusters"]:
            vals = sorted([p["network_forecast"] for p in c["forecast"]], reverse=True)
            plan_vol[c["cluster_id"]] = float(np.mean(vals[:3])) if vals else float(c["network_normal_daily"])
        pickup_cap = {}
        for p in providers:
            for cc in p.clusters:
                extra = cap_over.get(f"vehicles:{cc['cluster_id']}", 0)
                pickup_cap[cc["cluster_id"]] = {"provider_id": p.id, "provider": p.name, "vehicles": cc["vehicles"] + extra,
                                                "capacity": (cc["vehicles"] + extra) * p.pickups_per_vehicle, "ppv": p.pickups_per_vehicle,
                                                "cost": p.cost_per_pickup}
        fac_over = {k.split(":", 1)[1]: v for k, v in cap_over.items() if k.startswith("inspection:")}
        plan = plan_allocation(plan_vol, clusters, facilities, fac_over)
        fac_by = {f.id: f for f in facilities}
        cl_by = {c.id: c for c in clusters}
        recs, alerts, gaps = [], [], []
        for c in fc["clusters"]:
            cid = c["cluster_id"]
            pc = pickup_cap[cid]
            days_over = sum(1 for p in c["forecast"] if p["network_forecast"] > pc["capacity"])
            surge_days[cid] = days_over
            insp_cap = fac_by[cl_by[cid].default_facility_id].inspection_capacity
            gap = {"cluster_id": cid, "city": c["city"], "planning_volume": round(plan_vol[cid]), "pickup_capacity": pc["capacity"],
                   "pickup_gap": max(0, round(plan_vol[cid] - pc["capacity"])), "inspection_capacity": insp_cap,
                   "inspection_gap": max(0, round(plan_vol[cid] - insp_cap)), "days_over_pickup_capacity": days_over,
                   "provider": pc["provider"]}
            gaps.append(gap)
            material = c["risk"] == "high" or gap["pickup_gap"] > 0.25 * pc["capacity"]
            if gap["pickup_gap"] > 0 and days_over and material:
                veh = math.ceil(gap["pickup_gap"] / pc["ppv"])
                cost = veh * pc["ppv"] * SURGE_PICKUP_COST * days_over
                txt, src = llm.explain("extra_pickup", dict(city=c["city"], cap=pc["capacity"], peak=round(plan_vol[cid]), veh=veh), provider)
                recs.append(rec("extra_pickup", f"Book {veh} extra pickup vans in {c['city']} for {days_over} days ({pc['provider']})", txt,
                                {"gap": gap, "vehicles": veh, "days": days_over, "unit_cost": SURGE_PICKUP_COST, "provider_id": pc["provider_id"]},
                                "cluster", cid, impact=gap["pickup_gap"] * days_over * 60, cost=cost, confidence=0.75,
                                priority="high" if c["risk"] == "high" else "medium", source=src))
                alerts.append(alert("high", "logistics", f"{c['city']} is short of {gap['pickup_gap']:,} pickups a day",
                                    f"About {gap['planning_volume']:,} returns a day expected at the peak; vans can collect {pc['capacity']:,} a day.",
                                    "cluster", cid, scope_id=pc["provider_id"]))
            for a in plan["allocation"].get(cid, []):
                if a["default"] or a["units"] < 50:
                    continue
                alt = fac_by[a["facility_id"]]
                spare = max(0, alt.inspection_capacity - plan["facilities"][alt.id]["local"])
                days = max(days_over, 3)
                cost = a["units"] * transfer_cost(a["km"]) * days
                txt, src = llm.explain("reroute", dict(city=c["city"], peak=round(plan_vol[cid]), cap=insp_cap, share=a["share"], alt=alt.name,
                                                       spare=spare, cost=cost), provider)
                recs.append(rec("reroute", f"Send {a['share']:.0%} of {c['city']} returns to {alt.name}", txt,
                                {"allocation": a, "planning_volume": round(plan_vol[cid]), "default_capacity": insp_cap, "days": days,
                                 "lp_objective_inr": plan["objective_inr"], "facility_id": alt.id, "cluster_id": cid},
                                "route", f"{cid}>{alt.id}", impact=a["units"] * days * BACKLOG_PENALTY * 0.6, cost=cost, confidence=0.8,
                                priority="high", source=src))
        for fid, fl in plan["facilities"].items():
            if fl["overflow"] > max(100, 0.15 * fl["capacity"]):
                f = fac_by[fid]
                cost = fl["overflow"] * OVERTIME_PREMIUM * 4
                recs.append(rec("inspection_overtime", f"Add an inspection shift at {f.name} (+{fl['overflow']:,} a day)",
                                f"After re-routing, {f.name} still has about {fl['overflow']:,} a day above capacity at the forecast peak. "
                                f"An additional shift for 4 days costs about ₹{cost:,.0f} in overtime premium.",
                                {"facility": fl, "facility_id": fid, "days": 4, "units_per_day": fl["overflow"]}, "facility", fid,
                                impact=fl["overflow"] * 4 * BACKLOG_PENALTY * 0.5, cost=cost, confidence=0.7, priority="medium"))
                alerts.append(alert("medium", "warehouse", f"Expected overload at {f.name}", f"About {fl['overflow']:,} a day above inspection capacity at the forecast peak.",
                                    "facility", fid, scope_id=fid))
        sla = db.execute(text("""SELECT provider_id, cluster_id, AVG(CASE WHEN pickup_sla_met THEN 1.0 ELSE 0 END) sla, COUNT(*) n
                                 FROM returns WHERE pickup_date >= :s AND pickup_sla_met IS NOT NULL GROUP BY 1, 2"""),
                         {"s": ctx.scenario_date - timedelta(days=30)}).all()
        out = {"capacity_gaps": gaps, "allocation_plan": plan, "sla_30d": [{"provider_id": r[0], "cluster_id": r[1], "sla": round(float(r[2]), 3), "n": r[3]} for r in sla],
               "recommendations": len(recs), "auto_approval_limit_inr": auto_limit}
        ctx.send(self.id, "recovery", "inbound_plan", {"facilities": {k: v["assigned"] for k, v in plan["facilities"].items() if v["assigned"]}})
        ctx.send(self.id, "governance", "cost_items", {"total_cost_inr": round(sum(r["cost_inr"] for r in recs))})
        ctx.state["_reroutes"] = [r for r in recs if r["kind"] == "reroute"]
        return AgentResult(outputs=out, recommendations=recs, alerts=alerts)
