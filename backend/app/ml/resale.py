"""Resale Window Intelligence.

Estimates how a returned item's recoverable value changes with the day it gets
back on sale. Transparent and configurable (Settings > resale):

    V(t) = price x grade_factor x realisation(t) - refurb_cost(grade) - inspection_cost - storage_cost x t

realisation(t) = [floor + (1 - floor) x min(1, demand30(t) / demand_ref)] x exp(-obsolescence x t)

* obsolescence: per-category design-season decay (festive styles age faster).

* demand30(t): mean category demand index over the 30 days after listing day t.
  The index is derived from historical order volumes (same calendar week, prior
  year), so seasonality comes from data, not from assumed market prices.
* demand_ref: 75th percentile of demand30 across the year for that category.

Priority for inspection = value lost if the item waits 7 more days. Items are
processed by economic urgency rather than arrival order.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

DEFAULTS = {"storage_cost_per_day": 6.0, "refurb_cost_pct": 0.08, "inspection_cost": 45.0,
            "grade_factor": {"A": 0.95, "B": 0.72, "C": 0.30}, "markdown_floor": 0.35,
            "obsolescence_per_day": {"Lehenga": 0.0045, "Indo-western": 0.004, "Festive dress": 0.004, "Saree": 0.0012, "Kurta set": 0.0015}}

_index: dict[str, pd.Series] = {}


def build_demand_index(db: Session, scenario_date: date) -> dict[str, pd.Series]:
    """Daily demand index per category for the next 400 days, from prior-year orders."""
    global _index
    o = pd.read_sql(text("SELECT p.category, o.order_date FROM orders o JOIN products p ON p.sku=o.sku"), db.bind, parse_dates=["order_date"])
    out = {}
    for cat, g in o.groupby("category"):
        s = g.groupby("order_date").size().asfreq("D", fill_value=0).rolling(7, center=True, min_periods=1).mean()
        mean = s.loc[str(scenario_date - timedelta(days=365)):str(scenario_date)].mean()
        idx = pd.date_range(pd.Timestamp(scenario_date) - pd.Timedelta(days=30), periods=430)
        vals = []
        for d in idx:
            ref = d - pd.DateOffset(years=1)
            if d <= pd.Timestamp(scenario_date):
                ref = d
            vals.append(float(s.get(ref, mean)) / mean if mean else 1.0)
        out[cat] = pd.Series(vals, index=idx)
    _index = out
    return out


def demand30(category: str, day: date) -> float:
    s = _index.get(category)
    if s is None:
        return 1.0
    w = s.loc[pd.Timestamp(day): pd.Timestamp(day) + pd.Timedelta(days=29)]
    return float(w.mean()) if len(w) else 1.0


@lru_cache(maxsize=16)
def _demand_ref(category: str) -> float:
    s = _index.get(category)
    if s is None:
        return 1.0
    roll = s.rolling(30, min_periods=10).mean().dropna()
    return float(np.percentile(roll, 75)) if len(roll) else 1.0


def value_on(price: float, category: str, grade: str, list_day: date, today: date, cfg: dict) -> dict:
    gf = cfg["grade_factor"].get(grade, 0.5)
    d30 = demand30(category, list_day)
    age = max(0, (list_day - today).days)
    obs = float(np.exp(-cfg.get("obsolescence_per_day", DEFAULTS["obsolescence_per_day"]).get(category, 0.002) * age))
    real = (cfg["markdown_floor"] + (1 - cfg["markdown_floor"]) * min(1.0, d30 / _demand_ref(category))) * obs
    refurb = cfg["refurb_cost_pct"] * price if grade in ("B", "C") else 0.0
    storage = cfg["storage_cost_per_day"] * max(0, (list_day - today).days)
    gross = price * gf * real
    return {"day": list_day.isoformat(), "value": round(gross - refurb - cfg["inspection_cost"] - storage, 2),
            "realisation": round(real, 3), "demand30": round(d30, 3), "gross": round(gross, 2), "refurb": round(refurb, 2), "storage": round(storage, 2), "obsolescence": round(obs, 3)}


def curve(price: float, category: str, grade: str, today: date, cfg: dict, days: int = 60) -> list[dict]:
    return [value_on(price, category, grade, today + timedelta(days=k), today, cfg) for k in range(0, days + 1, 2)]


def prioritise(items: list[dict], today: date, cfg: dict) -> list[dict]:
    """items: dicts with price, category, expected_grade, ready_in_days. Adds value fields and sorts."""
    out = []
    for it in items:
        g = it["expected_grade"]
        lead = it.get("ready_in_days", 1) + (5 if g == "B" else 0)
        now_v = value_on(it["price"], it["category"], g, today + timedelta(days=lead), today, cfg)["value"]
        late_v = value_on(it["price"], it["category"], g, today + timedelta(days=lead + 7), today, cfg)["value"]
        it = dict(it, value_if_fast=now_v, value_if_delayed_7d=late_v, value_at_risk_7d=round(now_v - late_v, 2),
                  decay_per_day=round((now_v - late_v) / 7, 2))
        out.append(it)
    out.sort(key=lambda x: x["value_at_risk_7d"], reverse=True)
    for i, it in enumerate(out, 1):
        it["priority_rank"] = i
    return out
