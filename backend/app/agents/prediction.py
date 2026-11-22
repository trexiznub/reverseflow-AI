from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from .. import models as m
from ..ml.forecasting import breakdown_by_vendor_sku, run_forecast
from ..services import settings as st
from .base import Agent, AgentContext, AgentResult, alert

_cache: dict = {}


def latest_forecast(db) -> dict | None:
    if _cache.get("payload"):
        return _cache["payload"]
    snap = db.scalars(select(m.ForecastSnapshot).order_by(m.ForecastSnapshot.id.desc()).limit(1)).first()
    if snap:
        _cache["payload"] = snap.payload
        _cache["returns_count"] = snap.payload.get("_returns_count")
        return snap.payload
    return None


def invalidate():
    _cache.clear()


class ReturnPredictionAgent(Agent):
    id = "prediction"
    name = "Return Prediction"
    group = "Sensing & scenario"
    purpose = "Forecast return volumes by PIN cluster, SKU, size and vendor; warn of surges 5-7 days ahead; size capacity needs."
    inputs = ["Orders", "Return history", "Festival calendar", "Product category, SKU, size", "Vendor", "PIN clusters"]
    models = ["Gradient boosting (Poisson) + quantile P10/P90", "Seasonal-naive baseline"]

    def run(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        n_returns = db.scalar(select(func.count(m.Return.id)))
        cached = latest_forecast(db)
        retrain = ctx.trigger == "full_cycle" or cached is None
        if retrain:
            fc = run_forecast(db, ctx.scenario_date, st.network_scale(db))
            fc["breakdown"] = breakdown_by_vendor_sku(db, ctx.scenario_date, fc["clusters"])
            fc["_returns_count"] = n_returns
            fc["generated_at"] = datetime.now().isoformat(timespec="seconds")
            db.add(m.ForecastSnapshot(run_id=ctx.run_id, created_at=datetime.now(), origin=ctx.scenario_date, payload=fc))
            db.commit()
            _cache["payload"] = fc
        else:
            fc = cached
        delta = n_returns - (fc.get("_returns_count") or n_returns)
        alerts = []
        for a in fc["surge_alerts"]:
            alerts.append(alert("high" if a["avg_multiplier"] >= 1.9 else "medium", "ops_manager",
                                f"Return surge forecast: {a['city']} at {a['avg_multiplier']:.1f}x normal",
                                f"Peak expected {a['peak_day']} ({a['lead_days']} days ahead), about {a['additional_network_at_peak']:,} additional returns a day at peak.",
                                "cluster", a["cluster_id"]))
            prov = db.scalars(select(m.LogisticsProvider)).all()
            for p in prov:
                if any(c["cluster_id"] == a["cluster_id"] for c in p.clusters):
                    alerts.append(alert("medium", "logistics", f"Pickup volume forecast: {a['city']} {a['avg_multiplier']:.1f}x",
                                        f"Plan for about {a['additional_network_at_peak']:,} extra pickups a day around {a['peak_day']}.",
                                        "cluster", a["cluster_id"], scope_id=p.id))
        clusters = [{k: c[k] for k in ("cluster_id", "city", "avg_multiplier", "peak_multiplier", "peak_day", "network_normal_daily",
                                       "peak_network", "additional_network_at_peak", "expected_network_7d", "risk")} for c in fc["clusters"]]
        ev = fc["evaluations"][0]
        out = {
            "retrained": retrain, "new_returns_since_training": int(delta),
            "origin": fc["origin"], "horizon_days": fc["horizon_days"], "clusters": clusters, "surge_alerts": fc["surge_alerts"],
            "west_surge_avg_multiplier": fc["west_surge_avg_multiplier"],
            "holdout": {"label": ev["label"], "ml_wape": ev["daily_cluster"]["ml"]["wape"], "baseline_wape": ev["daily_cluster"]["baseline"]["wape"],
                        "surge_ml_wape": (ev["surge_window"] or {}).get("ml", {}).get("wape"),
                        "surge_baseline_wape": (ev["surge_window"] or {}).get("baseline", {}).get("wape")},
            "top_vendors": fc.get("breakdown", {}).get("vendors", [])[:5],
        }
        ctx.send(self.id, "logistics", "volume_forecast", {"clusters": [(c["cluster_id"], c["peak_network"]) for c in clusters]})
        ctx.send(self.id, "recovery", "expected_inbound", {"west_7d": sum(c["expected_network_7d"] for c in clusters if c["cluster_id"] in ("PNQ", "AMD", "JAI"))})
        ctx.send(self.id, "intelligence", "high_exposure_vendors", {"vendors": [v["vendor_id"] for v in out["top_vendors"]]})
        return AgentResult(outputs=out, alerts=alerts)
