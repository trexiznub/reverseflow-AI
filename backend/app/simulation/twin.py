"""Return Wave Digital Twin.

A discrete-time (daily), cohort-based simulation of the reverse chain:

    return requests -> pickup queue (vehicles x pickups/vehicle) -> line-haul to
    facility (1 day, +1 day for alternative facility) -> inspection queue
    (inspectors x shift minutes / processing minutes) -> grading -> restock /
    refurbish / liquidate.

Queues are FIFO cohorts so per-unit waiting times are exact for the model. In
"value-priority" mode the inspection line processes high-value, likely Grade-A
festive stock first (Resale Window Intelligence). Arrivals are Poisson around
the expected wave and the model is replicated (Monte Carlo) to give P10/P90.

All defaults are ILLUSTRATIVE demonstration assumptions, not marketplace data.
"""
from __future__ import annotations

import math
from copy import deepcopy

import numpy as np

DEFAULTS = {
    "days": 14,
    "replications": 40,
    "seed": 7,
    "surge_intensity": 1.0,  # scales the additional wave volume
    "peak_day": 5,  # day index of the wave peak
    "wave_width": 5,  # days from peak to zero (triangular)
    "pickups_per_vehicle": 35,
    "shift_minutes": 960,  # two 8h shifts
    "processing_minutes": 12.0,  # inspection minutes per unit
    "inspection_capacity_pct": 100,  # scales inspectors
    "vendor_defect_rate": 0.18,  # share of returns with a vendor defect (B/C grade)
    "recovery_rate": 0.82,  # share sellable after inspection (A+B)
    "avg_item_value": 4800.0,  # INR, ethnicwear average selling price
    "pickup_cost": 78.0,
    "surge_pickup_cost": 112.0,  # per pickup on additional (spot) vehicles
    "storage_cost_per_day": 6.0,
    "transfer_cost_per_km": 0.12,
    "transfer_fixed": 8.0,
    "target_days_to_restock": 3,
    "value_decay_pct_per_day": {"priority": 1.2, "other": 0.35},
    "priority_share": 0.45,  # share of returns that are likely Grade-A festive stock
    "clusters": [
        {"id": "PNQ", "name": "Pune", "base": 1500, "additional": 1200, "vehicles": 48, "facility": "FAC-PUN"},
        {"id": "AMD", "name": "Ahmedabad", "base": 1000, "additional": 800, "vehicles": 32, "facility": "FAC-AMD"},
        {"id": "JAI", "name": "Jaipur", "base": 750, "additional": 600, "vehicles": 24, "facility": "FAC-JAI"},
    ],
    "facilities": [
        {"id": "FAC-PUN", "name": "Pune Chakan", "inspectors": 19, "storage": 12000, "background": 0},
        {"id": "FAC-AMD", "name": "Ahmedabad Changodar", "inspectors": 16, "storage": 10000, "background": 0},
        {"id": "FAC-JAI", "name": "Jaipur Sitapura", "inspectors": 11, "storage": 8000, "background": 0},
        {"id": "FAC-NSK", "name": "Nashik Ambad", "inspectors": 14, "storage": 10000, "background": 300},
        {"id": "FAC-BHW", "name": "Bhiwandi Hub", "inspectors": 30, "storage": 30000, "background": 1800},
        {"id": "FAC-GGN", "name": "Gurugram Hub", "inspectors": 29, "storage": 26000, "background": 2000},
    ],
    "distances_km": {
        "PNQ>FAC-PUN": 35, "PNQ>FAC-NSK": 210, "PNQ>FAC-BHW": 160,
        "AMD>FAC-AMD": 20, "AMD>FAC-BHW": 520, "AMD>FAC-NSK": 430,
        "JAI>FAC-JAI": 18, "JAI>FAC-GGN": 245,
    },
    # share of each cluster's picked-up returns sent to an alternative facility
    "allocation": {"PNQ": {"FAC-NSK": 0.0}, "AMD": {"FAC-BHW": 0.0}, "JAI": {"FAC-GGN": 0.0}},
    "interventions": {
        "A_extra_vehicles_pct": 40,
        "B_allocation": {"PNQ": {"FAC-NSK": 0.30}, "AMD": {"FAC-BHW": 0.15}, "JAI": {"FAC-GGN": 0.20}},
        "C_value_priority": True,
        "C_extra_inspection_pct": 10,
    },
}


def wave_shape(day: int, peak: int, width: int) -> float:
    return max(0.0, 1.0 - abs(day - peak) / max(width, 1))


def _merge(base: dict, override: dict | None) -> dict:
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k not in ("allocation",):
            out[k] = _merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def _take(queue: list[list], n: float) -> list[tuple[int, float]]:
    """Remove up to n units FIFO from cohort queue [[day, qty], ...]; return taken cohorts."""
    taken = []
    while n > 1e-9 and queue:
        d, q = queue[0]
        t = min(q, n)
        taken.append((d, t))
        n -= t
        if q - t <= 1e-9:
            queue.pop(0)
        else:
            queue[0][1] = q - t
    return taken


def simulate_once(p: dict, rng: np.random.Generator | None, value_priority: bool) -> dict:
    days = p["days"]
    fac_ids = [f["id"] for f in p["facilities"]]
    insp_cap = {}
    for f in p["facilities"]:
        cap = f["inspectors"] * p["shift_minutes"] / p["processing_minutes"] * p["inspection_capacity_pct"] / 100
        insp_cap[f["id"]] = cap
    storage = {f["id"]: f["storage"] for f in p["facilities"]}
    background = {f["id"]: f.get("background", 0) for f in p["facilities"]}

    pickup_q = {c["id"]: [] for c in p["clusters"]}
    transit = []  # (arrive_day, facility, cls, request_day, qty)
    insp_q = {f: {"priority": [], "other": []} for f in fac_ids}
    series = []
    tot = dict(requests=0.0, picked=0.0, inspected=0.0, pickup_cost=0.0, transfer_cost=0.0, handling_cost=0.0, storage_cost=0.0,
               pickup_wait_sum=0.0, pickup_sla_ok=0.0, insp_wait_sum=0.0, restock_sum=0.0, value_lost=0.0, value_recovered=0.0,
               restocked_units=0.0, on_time_restock=0.0)
    ps = p["priority_share"]
    decay = p["value_decay_pct_per_day"]
    gross_value = p["avg_item_value"] * p["recovery_rate"]
    peak_pickup_backlog = 0.0
    peak_congestion = 0.0
    for day in range(days):
        # 1. arrivals
        day_req = {}
        for c in p["clusters"]:
            lam = c["base"] + c["additional"] * p["surge_intensity"] * wave_shape(day, p["peak_day"], p["wave_width"])
            n = float(rng.poisson(lam)) if rng is not None else lam
            pickup_q[c["id"]].append([day, n])
            tot["requests"] += n
            day_req[c["id"]] = n
        # 2. pickups
        row = {"day": day, "requests": round(sum(day_req.values())), "pickup_backlog": 0, "picked": 0}
        for c in p["clusters"]:
            base_veh = c["vehicles"]
            veh = c.get("vehicles_effective", base_veh)
            cap = veh * p["pickups_per_vehicle"]
            spot_cap = max(0.0, (veh - base_veh) * p["pickups_per_vehicle"])
            taken = _take(pickup_q[c["id"]], cap)
            picked = sum(q for _, q in taken)
            spot = min(picked, spot_cap)
            tot["pickup_cost"] += (picked - spot) * p["pickup_cost"] + spot * p["surge_pickup_cost"]
            tot["picked"] += picked
            for d0, q in taken:
                wait = day - d0 + 1
                tot["pickup_wait_sum"] += q * wait
                if wait <= 2:
                    tot["pickup_sla_ok"] += q
            alloc = p["allocation"].get(c["id"], {})
            alt_share = sum(alloc.values())
            for d0, q in taken:
                for fac, share in list(alloc.items()) + [(c["facility"], 1 - alt_share)]:
                    if share <= 0:
                        continue
                    qty = q * share
                    km = p["distances_km"].get(f"{c['id']}>{fac}", 40)
                    extra_day = 0 if fac == c["facility"] else 1
                    if fac != c["facility"]:
                        tot["transfer_cost"] += qty * (p["transfer_fixed"] + p["transfer_cost_per_km"] * km)
                    for cls, frac in (("priority", ps), ("other", 1 - ps)):
                        transit.append((day + 1 + extra_day, fac, cls, d0, qty * frac))
            backlog = sum(q for _, q in pickup_q[c["id"]])
            row[f"backlog_{c['id']}"] = round(backlog)
            row["pickup_backlog"] += backlog
            row["picked"] += picked
        peak_pickup_backlog = max(peak_pickup_backlog, row["pickup_backlog"])
        # 3. line-haul arrivals into inspection queues
        remaining = []
        for arr, fac, cls, d0, q in transit:
            if arr <= day:
                insp_q[fac][cls].append([d0, q, arr])
            else:
                remaining.append((arr, fac, cls, d0, q))
        transit = remaining
        # 4. inspection
        row["inspection_queue"] = 0
        for fac in fac_ids:
            cap = max(0.0, insp_cap[fac] - background[fac])
            order = ("priority", "other") if value_priority else None
            processed_total = 0.0
            if order:
                for cls in order:
                    if cap <= 0:
                        break
                    took = _take_insp(insp_q[fac][cls], cap)
                    cap -= sum(q for _, q, _ in took)
                    processed_total += _account(tot, took, day, cls, p, decay, gross_value)
            else:
                # FIFO across classes by arrival order
                merged = sorted([(a, d0, q, cls) for cls in ("priority", "other") for d0, q, a in insp_q[fac][cls]])
                budget = cap
                newq = {"priority": [], "other": []}
                for a, d0, q, cls in merged:
                    t = min(q, budget)
                    if t > 0:
                        processed_total += _account(tot, [(d0, t, a)], day, cls, p, decay, gross_value)
                        budget -= t
                    if q - t > 1e-9:
                        newq[cls].append([d0, q - t, a])
                insp_q[fac] = newq
            on_hand = sum(q for cls in ("priority", "other") for _, q, _ in insp_q[fac][cls])
            tot["storage_cost"] += on_hand * p["storage_cost_per_day"]
            cong = (on_hand + background[fac] * 0.5) / storage[fac]
            row[f"queue_{fac}"] = round(on_hand)
            row[f"util_{fac}"] = round(min(1.5, (processed_total + background[fac]) / max(insp_cap[fac], 1)), 3)
            row["inspection_queue"] += on_hand
            peak_congestion = max(peak_congestion, cong)
        series.append({k: (round(v) if isinstance(v, float) and not k.startswith("util") else v) for k, v in row.items()})
    # units still waiting at horizon end: value at risk = expected further decay until cleared
    unprocessed = 0.0
    for fac in fac_ids:
        cap = max(1.0, insp_cap[fac] - background[fac])
        q_tot = sum(q for cls in ("priority", "other") for _, q, _ in insp_q[fac][cls])
        clear_days = q_tot / cap
        for cls in ("priority", "other"):
            for d0, q, _ in insp_q[fac][cls]:
                wait = days - d0 + clear_days / 2
                tot["value_lost"] += q * gross_value * min(0.9, decay[cls] / 100 * max(0, wait - p["target_days_to_restock"]))
                unprocessed += q
    for c in p["clusters"]:
        for d0, q in pickup_q[c["id"]]:
            unprocessed += q
            tot["value_lost"] += q * gross_value * min(0.9, decay["other"] / 100 * max(0, days - d0))
    for arr, fac, cls, d0, q in transit:
        unprocessed += q
    n_proc = max(tot["inspected"], 1)
    total_cost = tot["pickup_cost"] + tot["transfer_cost"] + tot["handling_cost"] + tot["storage_cost"]
    return {
        "series": series,
        "kpis": {
            "total_returns": tot["requests"],
            "peak_pickup_backlog": peak_pickup_backlog,
            "avg_pickup_wait_days": tot["pickup_wait_sum"] / max(tot["picked"], 1),
            "pickup_sla_pct": tot["pickup_sla_ok"] / max(tot["picked"], 1),
            "peak_warehouse_congestion_pct": peak_congestion,
            "avg_inspection_wait_days": tot["insp_wait_sum"] / n_proc,
            "avg_return_to_restock_days": tot["restock_sum"] / max(tot["restocked_units"], 1),
            "on_time_restock_pct": tot["on_time_restock"] / max(tot["restocked_units"], 1),
            "cost_per_return": total_cost / max(tot["picked"], 1),
            "total_cost": total_cost,
            "value_at_risk": tot["value_lost"],
            "value_recovered": tot["value_recovered"],
            "units_unprocessed_at_horizon": unprocessed,
            "units_inspected": tot["inspected"],
        },
    }


def _take_insp(q: list[list], n: float) -> list[tuple[int, float, int]]:
    taken = []
    while n > 1e-9 and q:
        d0, qty, a = q[0]
        t = min(qty, n)
        taken.append((d0, t, a))
        n -= t
        if qty - t <= 1e-9:
            q.pop(0)
        else:
            q[0][1] = qty - t
    return taken


def _account(tot, took, day, cls, p, decay, gross_value) -> float:
    n = 0.0
    for d0, q, a in took:
        n += q
        tot["inspected"] += q
        tot["handling_cost"] += q * 45.0
        tot["insp_wait_sum"] += q * (day - a)
        restock_days = day - d0 + 1 + (0 if cls == "priority" else 2)  # B-grade refurb adds time on 'other'
        tot["restock_sum"] += q * restock_days * p["recovery_rate"]
        tot["restocked_units"] += q * p["recovery_rate"]
        if restock_days <= p["target_days_to_restock"] + 1:
            tot["on_time_restock"] += q * p["recovery_rate"]
        late = max(0, restock_days - p["target_days_to_restock"])
        lost_frac = min(0.9, decay[cls] / 100 * late)
        defect_penalty = 1 - p["vendor_defect_rate"] * 0.5
        value = q * gross_value * defect_penalty * (1.6 if cls == "priority" else 0.5)
        tot["value_lost"] += value * lost_frac
        tot["value_recovered"] += value * (1 - lost_frac)
    return n


SCENARIOS = {
    "baseline": "Baseline: current capacity, default routing, FIFO inspection",
    "A": "Intervention A: additional pickup capacity",
    "B": "Intervention B: alternative warehouse allocation",
    "C": "Intervention C: combined optimisation (A + B + value-priority inspection)",
}


def _scenario_params(p: dict, name: str) -> tuple[dict, bool]:
    q = deepcopy(p)
    iv = p["interventions"]
    vp = False
    if name in ("A", "C"):
        for c in q["clusters"]:
            c["vehicles_effective"] = math.ceil(c["vehicles"] * (1 + iv["A_extra_vehicles_pct"] / 100))
    if name in ("B", "C"):
        q["allocation"] = deepcopy(iv["B_allocation"])
    if name == "C":
        vp = bool(iv.get("C_value_priority", True))
        q["inspection_capacity_pct"] = p["inspection_capacity_pct"] * (1 + iv.get("C_extra_inspection_pct", 0) / 100)
    return q, vp


def run(params: dict | None = None, scenarios: list[str] | None = None) -> dict:
    p = _merge(DEFAULTS, params)
    scenarios = scenarios or list(SCENARIOS)
    out = {"assumptions_note": "Illustrative demonstration assumptions, not real marketplace data.", "params": p, "scenarios": {}}
    for name in scenarios:
        q, vp = _scenario_params(p, name)
        det = simulate_once(q, None, vp)
        rng = np.random.default_rng(p["seed"])
        reps = [simulate_once(q, rng, vp)["kpis"] for _ in range(int(p["replications"]))]
        kpis = {}
        for k in det["kpis"]:
            vals = np.array([r[k] for r in reps])
            kpis[k] = {"mean": round(float(vals.mean()), 4), "p10": round(float(np.percentile(vals, 10)), 4),
                       "p90": round(float(np.percentile(vals, 90)), 4), "expected": round(float(det["kpis"][k]), 4)}
        out["scenarios"][name] = {"label": SCENARIOS[name], "value_priority": vp, "series": det["series"], "kpis": kpis,
                                  "effective": {"vehicles": {c["id"]: c.get("vehicles_effective", c["vehicles"]) for c in q["clusters"]},
                                                "allocation": q["allocation"], "inspection_capacity_pct": q["inspection_capacity_pct"],
                                                "inspection_capacity_units": {f["id"]: round(f["inspectors"] * q["shift_minutes"] / q["processing_minutes"] * q["inspection_capacity_pct"] / 100) for f in q["facilities"]}}}
    base = out["scenarios"].get("baseline")
    if base:
        for name, sc in out["scenarios"].items():
            sc["vs_baseline"] = {k: round(sc["kpis"][k]["mean"] - base["kpis"][k]["mean"], 4) for k in sc["kpis"]}
    return out
