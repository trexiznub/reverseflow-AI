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


HORIZON_DAYS = 21  # forecast week plus two weeks to clear any backlog


def backlog(arrivals: list[float], capacity: list[float]) -> dict:
    """Day-by-day pickup queue. Returns waiting item-days and pickups made on the day they were due."""
    b, wait, late = 0.0, 0.0, 0.0
    for a, k in zip(arrivals, capacity):
        picked = min(b + a, k)
        late += max(0.0, min(b, picked))  # pickups that cleared earlier backlog
        b = b + a - picked
        wait += b
    return {"item_days_waiting": wait, "left_at_end": b, "late_pickups": late}


def size_vans(arrivals: list[float], cap: float, ppv: int, value_per_item_day: float, cost_per_van_day: float) -> dict:
    """Choose how many extra vans to hire on the over-capacity days so that the value they protect
    exceeds what they cost by the most. Returns the best option and the options compared."""
    hire = [a > cap for a in arrivals]
    hire_days = sum(hire)
    base = backlog(arrivals, [cap] * len(arrivals))
    max_v = math.ceil(max(0.0, max(arrivals[:7]) - cap) / ppv) if arrivals else 0
    options = []
    for v in range(0, max_v + 1):
        caps = [cap + (v * ppv if h else 0) for h in hire]
        q = backlog(arrivals, caps)
        saved_days = base["item_days_waiting"] - q["item_days_waiting"]
        benefit = saved_days * value_per_item_day
        cost = v * cost_per_van_day * hire_days
        options.append({"vans": v, "cost": round(cost), "benefit": round(benefit), "net": round(benefit - cost),
                        "waiting_days_avoided": round(saved_days), "left_after_3_weeks": round(q["left_at_end"])})
    best = max(options, key=lambda o: (o["net"], -o["vans"])) if options else {"vans": 0, "net": 0}
    return {"best": best, "hire_days": hire_days, "no_vans": {"item_days_waiting": round(base["item_days_waiting"]),
            "left_after_3_weeks": round(base["left_at_end"])},
            "options": [o for o in options if o["vans"] in {0, best["vans"], max_v} or o["vans"] % max(1, max_v // 6) == 0]}


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
        # Resale value a returned item loses per day of delay, per city, from recent returns and the resale model.
        from ..ml.resale import DEFAULTS as RESALE
        decay = (ctx.settings.get("resale") or {}).get("obsolescence_per_day") or RESALE["obsolescence_per_day"]
        rows = db.execute(text("""SELECT r.cluster_id, p.category, AVG(r.price), COUNT(*) FROM returns r JOIN products p ON p.sku = r.sku
                                  WHERE r.request_date >= :s GROUP BY 1, 2"""), {"s": ctx.scenario_date - timedelta(days=90)}).all()
        acc: dict[str, list[float]] = {}
        for cid_, cat, price, n in rows:
            v = acc.setdefault(cid_, [0.0, 0.0])
            v[0] += float(price) * decay.get(cat, 0.002) * n
            v[1] += n
        value_per_day = {k: v[0] / v[1] for k, v in acc.items() if v[1]}
        if value_per_day:
            value_per_day["_all"] = sum(value_per_day.values()) / len(value_per_day)
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
                # Size the van hire by its net value: each day a return waits for pickup it also waits to be
                # resold, and festive stock loses value every day (the resale model's obsolescence rates).
                arrivals = [float(p["network_forecast"]) for p in c["forecast"]]
                arrivals += [float(c["network_normal_daily"])] * max(0, HORIZON_DAYS - len(arrivals))
                vpd = value_per_day.get(cid, value_per_day.get("_all", 20.0))
                plan_v = size_vans(arrivals, pc["capacity"], pc["ppv"], vpd, pc["ppv"] * SURGE_PICKUP_COST)
                best = plan_v["best"]
                evidence = {"gap": gap, "vehicles": best["vans"], "days": plan_v["hire_days"], "unit_cost": SURGE_PICKUP_COST,
                            "provider_id": pc["provider_id"], "value_lost_per_item_day": round(vpd, 2),
                            "value_basis": "average value of returned items in this city × the resale model's daily value loss for each category",
                            "without_vans": plan_v["no_vans"], "with_vans": best, "options": plan_v["options"],
                            "covers_share_of_gap": round(min(1.0, best["vans"] * pc["ppv"] / max(gap["pickup_gap"], 1)), 3),
                            "horizon_days": HORIZON_DAYS}
                if best["vans"] > 0 and best["net"] > 0:
                    veh = best["vans"]
                    txt, src = llm.explain("extra_pickup", dict(city=c["city"], cap=pc["capacity"], peak=round(plan_vol[cid]), veh=veh,
                                                                saved=best["waiting_days_avoided"], net=best["net"]), provider)
                    recs.append(rec("extra_pickup", f"Book {veh} extra pickup vans in {c['city']} for {plan_v['hire_days']} days ({pc['provider']})", txt,
                                    evidence, "cluster", cid, impact=best["benefit"], cost=best["cost"], confidence=0.7,
                                    priority="high" if c["risk"] == "high" else "medium", source=src))
                else:
                    alerts.append(alert("medium", "logistics", f"Extra vans in {c['city']} would cost more than they save",
                                        f"{c['city']} is short of {gap['pickup_gap']:,} pickups a day at the peak, but hiring vans costs more than the "
                                        "resale value they protect. Re-routing, exchanges and accepting a short delay are cheaper.",
                                        "cluster", cid, scope_id=pc["provider_id"]))
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
