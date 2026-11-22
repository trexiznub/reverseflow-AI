"""KPIs computed from application data, and SAP Analytics Cloud-ready exports."""
from __future__ import annotations

import io
from datetime import timedelta

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import models as m
from ..agents.prediction import latest_forecast
from ..agents.recovery import recovery_queue
from ..db import get_db
from ..ml import resale
from ..rbac import require
from ..reference import AVOIDABLE_REASONS
from ..services import settings as st

router = APIRouter()

DEFS = {
    "forecast_accuracy": ("How accurate the forecast is", "How close the 7-day forecast came to what actually happened, on days it hadn't seen (100% would be perfect). Technically: 1 minus WAPE, daily by city."),
    "surge_lead_time": ("How early the surge was spotted", "Days of warning between the forecast first showing 1.5× normal returns and the actual peak, in last year's festive season."),
    "avoidable_rate": ("Returns that could be avoided", "Share of returns caused by size, quality or listing problems, which a fix could prevent. Uses the warehouse's reason, or the system's reading of the customer's words."),
    "cost_per_return": ("Cost of handling one return", "Pickup, warehouse handling and ₹6 a day of storage until inspection, per returned item."),
    "return_to_restock": ("Time to get back on sale", "Hours from pickup until an item is back on sale (or repaired and back on sale)."),
    "sellable_recovery": ("Value we get back", "Money recovered from returned items (resale, repaired resale, clearance, or credit from the seller) as a share of their original price."),
    "warehouse_utilisation": ("How busy the warehouses are", "Items inspected as a share of what the warehouses can inspect."),
    "pickup_sla": ("Picked up on time", "Share of returns collected within 2 days of the customer asking."),
    "vendor_defect_rate": ("Returns for quality faults", "Share of returns caused by stitching or fabric faults, by seller."),
    "value_recovered": ("Money recovered", "Total value recovered from returns completed in the period."),
    "value_at_risk": ("Value lost if we're slow", "Value that would be lost if every returned item now on its way waited 7 more days before resale."),
}


def _returns(db: Session) -> pd.DataFrame:
    return pd.read_sql(text("""SELECT r.id, r.request_date, r.pickup_date, r.received_date, r.inspected_date, r.restock_date, r.vendor_id, r.facility_id,
                                      r.price, r.recovered_value, r.recovery_action, r.pickup_sla_met, r.pickup_cost, r.status, r.cluster_id,
                                      COALESCE(r.verified_reason, r.predicted_reason) reason, f.handling_cost
                               FROM returns r LEFT JOIN facilities f ON f.id=r.facility_id"""), db.bind,
                       parse_dates=["request_date", "pickup_date", "received_date", "inspected_date", "restock_date"])


def _monthly(s: pd.Series, how="mean", months=12) -> list[dict]:
    g = getattr(s.groupby(s.index.to_period("M")), how)().tail(months)
    return [{"period": str(k), "value": round(float(v), 4)} for k, v in g.items()]


def _kpi(key, value, unit, trend=None, chart=None, drill=None, extra=None):
    name, definition = DEFS[key]
    return {"key": key, "name": name, "definition": definition, "value": value, "unit": unit, "trend": trend or [], "chart": chart, "drilldown": drill or [], **(extra or {})}


@router.get("/analytics/kpis")
def kpis(db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    D = st.scenario_date(db)
    r = _returns(db)
    fc = latest_forecast(db) or {}
    out = []
    ev = (fc.get("evaluations") or [{}])[0]
    if ev:
        weekly = {}
        for p in ev.get("series", []):
            wk = pd.Timestamp(p["day"]).to_period("W").start_time.date().isoformat()
            a = weekly.setdefault(wk, [0.0, 0.0, 0.0])
            a[0] += p["actual"]; a[1] += abs(p["ml"] - p["actual"]); a[2] += abs(p["baseline"] - p["actual"])
        out.append(_kpi("forecast_accuracy", round(1 - ev["daily_cluster"]["ml"]["wape"], 4), "ratio",
                        trend=[{"period": k, "value": round(1 - v[1] / max(v[0], 1), 4), "baseline": round(1 - v[2] / max(v[0], 1), 4)} for k, v in sorted(weekly.items())],
                        chart="line", extra={"baseline_value": round(1 - ev["daily_cluster"]["baseline"]["wape"], 4), "evaluation": ev["label"],
                                             "weekly_accuracy": round(1 - ev["weekly_cluster"]["ml"]["wape"], 4),
                                             "weekly_baseline": round(1 - ev["weekly_cluster"]["baseline"]["wape"], 4)}))
        leads = ev.get("surge_lead_time", [])
        out.append(_kpi("surge_lead_time", round(sum(l["lead_days"] for l in leads) / len(leads), 1) if leads else None, "days",
                        drill=leads, chart="bar", extra={"current_alerts": fc.get("surge_alerts", [])}))
    ri = r.set_index("request_date").sort_index()
    av = ri.reason.isin(list(AVOIDABLE_REASONS)).astype(float)
    last90 = av[av.index >= pd.Timestamp(D - timedelta(days=90))]
    out.append(_kpi("avoidable_rate", round(float(last90.mean()), 4), "ratio", trend=_monthly(av), chart="line",
                    drill=[{"label": k, "value": int(v)} for k, v in r[r.request_date >= pd.Timestamp(D - timedelta(days=90))].reason.value_counts().items()]))
    wait = (r.inspected_date - r.received_date).dt.days.clip(lower=0).fillna(0)
    cost = r.pickup_cost.fillna(0) + r.handling_cost.fillna(45).where(r.inspected_date.notna(), 0) + 6 * wait
    cs = pd.Series(cost.values, index=r.request_date).sort_index()
    cs = cs[r.set_index("request_date").sort_index().pickup_cost.notna().values]
    out.append(_kpi("cost_per_return", round(float(cs[cs.index >= pd.Timestamp(D - timedelta(days=30))].mean()), 2), "INR", trend=_monthly(cs), chart="line",
                    drill=[{"label": k, "value": round(float(v), 2)} for k, v in pd.Series(cost.values, index=r.cluster_id).groupby(level=0).mean().items()]))
    rs = r[r.restock_date.notna() & r.recovery_action.isin(["restock", "refurbish"])]
    hrs = pd.Series(((rs.restock_date - rs.pickup_date).dt.days * 24).values, index=rs.request_date).sort_index()
    out.append(_kpi("return_to_restock", round(float(hrs[hrs.index >= pd.Timestamp(D - timedelta(days=60))].mean()), 1), "hours", trend=_monthly(hrs), chart="line",
                    drill=[{"label": k, "value": round(float(v) * 24, 1)} for k, v in ((rs.restock_date - rs.pickup_date).dt.days).groupby(rs.recovery_action).mean().items()]))
    done = r[r.recovered_value.notna()]
    rec_s = pd.Series(done.recovered_value.values, index=done.request_date).sort_index()
    val_s = pd.Series(done.price.values, index=done.request_date).sort_index()
    ratio_m = (rec_s.groupby(rec_s.index.to_period("M")).sum() / val_s.groupby(val_s.index.to_period("M")).sum()).tail(12)
    recent = done[done.request_date >= pd.Timestamp(D - timedelta(days=90))]
    out.append(_kpi("sellable_recovery", round(float(recent.recovered_value.sum() / max(recent.price.sum(), 1)), 4), "ratio",
                    trend=[{"period": str(k), "value": round(float(v), 4)} for k, v in ratio_m.items()], chart="line",
                    drill=[{"label": k, "value": round(float(v), 4)} for k, v in (recent.groupby("recovery_action").recovered_value.sum() / recent.groupby("recovery_action").price.sum()).items()]))
    fd = pd.read_sql(text("SELECT f.facility_id, f.day, f.processed, c.inspection_capacity cap FROM facility_daily f JOIN facilities c ON c.id=f.facility_id"),
                     db.bind, parse_dates=["day"])
    fd["u"] = fd.processed / fd.cap
    last30 = fd[fd.day >= pd.Timestamp(D - timedelta(days=30))]
    daily_u = fd.groupby("day").apply(lambda g: g.processed.sum() / g.cap.sum(), include_groups=False)
    out.append(_kpi("warehouse_utilisation", round(float(last30.processed.sum() / last30.cap.sum()), 4), "ratio",
                    trend=[{"period": k.date().isoformat(), "value": round(float(v), 4)} for k, v in daily_u.tail(60).items()], chart="area",
                    drill=[{"label": k, "value": round(float(v), 4)} for k, v in last30.groupby("facility_id").u.mean().items()]))
    sl = r[r.pickup_sla_met.notna()]
    sla_s = pd.Series(sl.pickup_sla_met.astype(float).values, index=sl.pickup_date).sort_index()
    out.append(_kpi("pickup_sla", round(float(sla_s[sla_s.index >= pd.Timestamp(D - timedelta(days=30))].mean()), 4), "ratio", trend=_monthly(sla_s), chart="line",
                    drill=[{"label": k, "value": round(float(v), 4)} for k, v in sl.groupby("cluster_id").pickup_sla_met.mean().items()]))
    r90 = r[r.request_date >= pd.Timestamp(D - timedelta(days=90))]
    dr = r90.groupby("vendor_id").reason.apply(lambda s: s.isin(["STITCHING", "FABRIC_QUALITY"]).mean()).sort_values(ascending=False)
    net_d = ri.reason.isin(["STITCHING", "FABRIC_QUALITY"]).astype(float)
    vnames = dict(db.execute(text("SELECT id, name FROM vendors")).all())
    out.append(_kpi("vendor_defect_rate", round(float(r90.reason.isin(["STITCHING", "FABRIC_QUALITY"]).mean()), 4), "ratio", trend=_monthly(net_d), chart="bar",
                    drill=[{"label": vnames.get(k, k), "value": round(float(v), 4), "vendor_id": k} for k, v in dr.items()]))
    out.append(_kpi("value_recovered", round(float(recent.recovered_value.sum()), 0), "INR", trend=_monthly(rec_s, "sum"), chart="bar",
                    drill=[{"label": k, "value": round(float(v), 0)} for k, v in recent.groupby("recovery_action").recovered_value.sum().items()],
                    extra={"window": "last 90 days, synthetic sample scale"}))
    cfg = dict(resale.DEFAULTS, **(st.get(db, "resale", {}) or {}))
    resale.build_demand_index(db, D)
    q = recovery_queue(db, D, cfg)
    by_fac = {}
    for i in q:
        by_fac[i["facility_id"]] = by_fac.get(i["facility_id"], 0) + i["value_at_risk_7d"]
    out.append(_kpi("value_at_risk", round(sum(i["value_at_risk_7d"] for i in q), 0), "INR", chart="bar",
                    drill=[{"label": k, "value": round(v, 0)} for k, v in sorted(by_fac.items(), key=lambda x: -x[1])],
                    extra={"items_in_pipeline": len(q), "window": "current pipeline, synthetic sample scale"}))
    return {"scenario_date": D.isoformat(), "kpis": out, "note": "Worked out from the demo data and the latest agent run."}


DATASETS = ("returns_fact", "forecast", "vendor_kpis", "recovery_queue")


@router.get("/integrations/sac/{dataset}.csv")
def sac_export(dataset: str, db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    if dataset not in DATASETS:
        raise HTTPException(404, f"dataset must be one of {DATASETS}")
    D = st.scenario_date(db)
    if dataset == "returns_fact":
        df = pd.read_sql(text("""SELECT r.id return_id, r.request_date, r.cluster_id, r.vendor_id, r.sku, p.category, r.size, r.price,
                                        COALESCE(r.verified_reason, r.predicted_reason) reason, r.status, r.grade, r.recovery_action, r.recovered_value,
                                        r.pickup_sla_met, r.facility_id, r.is_synthetic FROM returns r JOIN products p ON p.sku=r.sku"""), db.bind)
    elif dataset == "forecast":
        fc = latest_forecast(db) or {"clusters": []}
        df = pd.DataFrame([dict(cluster_id=c["cluster_id"], city=c["city"], **p) for c in fc["clusters"] for p in c["forecast"]])
    elif dataset == "vendor_kpis":
        from ..services.intelligence import vendor_rankings
        df = pd.DataFrame(vendor_rankings(db, D))
    else:
        cfg = dict(resale.DEFAULTS, **(st.get(db, "resale", {}) or {}))
        resale.build_demand_index(db, D)
        df = pd.DataFrame(recovery_queue(db, D, cfg))
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="reverseflow_{dataset}_{D.isoformat()}.csv"'})
