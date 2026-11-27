"""The business case: the problem in numbers, from published market figures and
from the live demo (forecast, agents, reverse-logistics simulation)."""
from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..agents.prediction import latest_forecast
from ..db import get_db
from ..rbac import require
from ..sap import outbox
from ..simulation import twin

router = APIRouter()

SOURCES = {
    "moneycontrol26": {"label": "Moneycontrol, citing Datum Intelligence: festive online sales rise 17% to ₹1.41 lakh crore (2026)",
                       "url": "https://www.moneycontrol.com/news/business/startup/festive-online-sales-rise-17-to-rs-1-41-lakh-crore-slowest-growth-since-2023-14077755.html"},
    "ibef26": {"label": "IBEF, citing Redseer: 2026 festive season forecast ₹1.40–1.49 lakh crore",
               "url": "https://www.ibef.org/news/india-s-online-retail-to-cross-us-90-billion-in-2026-redseer"},
    "redseer": {"label": "Redseer festive season forecast, via Business Standard (Aug 2025)",
                "url": "https://www.business-standard.com/industry/news/india-festive-season-ecommerce-sale-redseer-report-125082700476_1.html"},
    "ibef": {"label": "IBEF: festive e-commerce GMV to cross ₹1,15,000 crore",
             "url": "https://ibef.org/news/e-commerce-gmv-set-to-cross-rs-1-15-000-crore-us-13-12-billion-grow-20-in-festive-season-redseer"},
    "redseer11": {"label": "Redseer: first 11 days of the festive sales",
                  "url": "https://redseer.com/articles/e-commerce-festive-1st-leg-11-day/"},
    "clickpost_fashion": {"label": "Clickpost: fashion e-commerce returns in India",
                          "url": "https://www.clickpost.ai/blog/fashion-ecommerce-returns-statistics-india"},
    "clickpost_rate": {"label": "Clickpost: e-commerce return rate in India",
                       "url": "https://www.clickpost.ai/blog/ecommerce-return-rate-india"},
    "shipmozo": {"label": "Shipmozo: e-commerce returns and reverse logistics",
                 "url": "https://www.shipmozo.com/blog/ecommerce-returns-and-reverse-logistics"},
    "base": {"label": "Base: returns management for D2C brands in India", "url": "https://base.com/en-IN/blog/returns-management-in-d2c-india/"},
    "dfu": {"label": "DFU Publications: how returns are reshaping fashion e-commerce in India",
            "url": "https://dfupublications.com/news/apparel/the-high-cost-of-growth-how-returns-are-reshaping-fashion-e-commerce-in-india"},
    "row": {"label": "Rest of World: the end of free returns", "url": "https://restofworld.org/2023/end-of-free-returns/"},
}

# Published figures behind the market model. "kind" says how sure we are.
FACTS = [
    {"id": "festive_gmv", "label": "Festive season online sales in India, 2026", "value": "about ₹1,41,000 crore, up 17% on 2025", "sources": ["moneycontrol26"], "kind": "published"},
    {"id": "festive_gmv_forecast", "label": "2026 pre-season forecast (Redseer)", "value": "₹1,40,000–1,49,000 crore (US$15–16 billion), about 25% growth", "sources": ["ibef26"], "kind": "published forecast"},
    {"id": "festive_gmv_2025", "label": "Festive season online sales, 2025 (forecast)", "value": "₹1,15,000 crore, up 20–25%", "sources": ["redseer", "ibef"], "kind": "published"},
    {"id": "first_days", "label": "Sales in the first 11 days of 2025, against normal days", "value": "about 3.5×", "sources": ["redseer11"], "kind": "published"},
    {"id": "fashion_share", "label": "Fashion's share of festive sales (2025)", "value": "about one fifth", "sources": ["redseer", "ibef"], "kind": "published"},
    {"id": "all_returns", "label": "Return rate, all Indian e-commerce (2024)", "value": "7.8% of orders", "sources": ["clickpost_rate"], "kind": "published"},
    {"id": "fashion_returns", "label": "Customer return rate, online fashion in India", "value": "17–25% of orders", "sources": ["clickpost_fashion", "dfu"], "kind": "published"},
    {"id": "with_rto", "label": "Including cash-on-delivery orders refused at the door", "value": "25–40% of orders", "sources": ["clickpost_fashion", "row"], "kind": "industry estimate"},
    {"id": "reverse_cost", "label": "Cost of a return compared with a delivery", "value": "1.5–2× the forward shipping cost; ₹70–120 per pickup in a metro", "sources": ["shipmozo", "base"], "kind": "industry estimate"},
    {"id": "reverse_share", "label": "Reverse logistics as a share of order value", "value": "about 5–7% on average", "sources": ["clickpost_fashion", "base"], "kind": "industry estimate"},
]

# Starting values for the calculator on the case page (all editable there).
ASSUMPTIONS = [
    {"id": "festive_gmv_cr", "label": "Festive online sales, 2026 (₹ crore)", "value": 141000, "min": 50000, "max": 200000, "step": 1000, "sources": ["moneycontrol26"], "kind": "published"},
    {"id": "fashion_share", "label": "Fashion's share of sales (2025 figure)", "value": 0.20, "min": 0.10, "max": 0.35, "step": 0.01, "sources": ["redseer"], "kind": "published", "unit": "pct"},
    {"id": "return_rate", "label": "Share of fashion orders returned", "value": 0.20, "min": 0.10, "max": 0.40, "step": 0.01, "sources": ["clickpost_fashion"], "kind": "published range 17–25%", "unit": "pct"},
    {"id": "reverse_cost_pct", "label": "Cost of handling a return (share of its price)", "value": 0.06, "min": 0.03, "max": 0.15, "step": 0.005, "sources": ["clickpost_fashion", "base"], "kind": "industry estimate 5–7%", "unit": "pct"},
    {"id": "value_lost_pct", "label": "Resale value lost while returns wait", "value": 0.05, "min": 0.0, "max": 0.20, "step": 0.005, "sources": [], "kind": "our assumption", "unit": "pct"},
    {"id": "prevented_share", "label": "Avoidable returns prevented by fixing the cause", "value": 0.25, "min": 0.0, "max": 0.6, "step": 0.05, "sources": [], "kind": "our assumption", "unit": "pct"},
]


@lru_cache(maxsize=1)
def _simulation() -> dict:
    """Do nothing vs the combined plan, from the reverse-logistics simulation (Digital Twin engine)."""
    r = twin.run({"replications": 20}, ["baseline", "C"])
    out = {}
    for k, sc in r["scenarios"].items():
        kp = sc["kpis"]
        out[k] = {"value_lost": round(kp["value_at_risk"]["mean"]), "pickup_on_time": round(kp["pickup_sla_pct"]["mean"], 3),
                  "days_to_resale": round(kp["avg_return_to_restock_days"]["mean"], 2), "cost_per_return": round(kp["cost_per_return"]["mean"], 1),
                  "total_returns": round(kp["total_returns"]["mean"])}
    b, c = out["baseline"], out["C"]
    out["reduction"] = round(1 - c["value_lost"] / b["value_lost"], 3) if b["value_lost"] else 0
    out["scenario"] = "Standard simulation: Pune, Ahmedabad and Jaipur, 14 days, 20 runs. Illustrative assumptions."
    return out


def _rec(db: Session, kind: str, entity_id: str | None = None) -> m.Recommendation | None:
    q = select(m.Recommendation).where(m.Recommendation.kind == kind)
    if entity_id:
        q = q.where(m.Recommendation.entity_id == entity_id)
    return db.scalars(q.order_by(m.Recommendation.created_at.desc())).first()


@router.get("/case")
def case(db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    fc = latest_forecast(db) or {}
    alerts = {a["cluster_id"]: a for a in fc.get("surge_alerts", [])}
    cities = [alerts[c] for c in ("PNQ", "AMD", "JAI") if c in alerts]
    pickup = _rec(db, "extra_pickup", "PNQ")
    qc = _rec(db, "pre_dispatch_qc") or _rec(db, "vendor_qc_hold")
    reroute = _rec(db, "reroute")
    gap = (pickup.evidence or {}).get("gap", {}) if pickup else {}
    finding = (qc.evidence or {}).get("finding", {}) if qc else {}
    alloc = (reroute.evidence or {}).get("allocation", {}) if reroute else {}
    integrity = db.scalar(select(func.count(m.Recommendation.id)).where(m.Recommendation.kind == "integrity_inspection")) or 0
    waiting = db.scalar(select(func.count(m.Recommendation.id)).where(m.Recommendation.status.in_(["pending", "escalated"]))) or 0
    from ..services import settings as st
    from .analytics import _returns
    from ..reference import AVOIDABLE_REASONS
    r = _returns(db)
    avoidable = float(r.reason.isin(list(AVOIDABLE_REASONS)).mean()) if len(r) else 0
    return {
        "scenario_date": st.scenario_date(db).isoformat(),
        "facts": FACTS, "assumptions": ASSUMPTIONS, "sources": SOURCES,
        "demo": {
            "surge": [{"city": a["city"], "peak_multiplier": a["peak_multiplier"], "lead_days": a["lead_days"], "peak_day": a["peak_day"]} for a in cities],
            "pickup": {"city": gap.get("city"), "needed_per_day": gap.get("planning_volume"), "capacity_per_day": gap.get("pickup_capacity"),
                       "extra_vans": (pickup.evidence or {}).get("vehicles") if pickup else None, "status": pickup.status if pickup else None},
            "seller": {"name": finding.get("vendor_name"), "reason": finding.get("reason_label"), "share": finding.get("share"),
                       "others_share": finding.get("network_share"), "status": qc.status if qc else None},
            "reroute": {"from": reroute.evidence.get("cluster_id") if reroute else None, "to": alloc.get("facility_id"), "share": alloc.get("share"),
                        "status": reroute.status if reroute else None},
            "simulation": _simulation(),
            "integrity_checks": integrity, "decisions_waiting": waiting, "avoidable_share": round(avoidable, 3),
            "sap_messages": outbox.summary(db),
        },
        "note": "Market figures come from the published sources listed. Demo figures come from synthetic data and are illustrative.",
    }
