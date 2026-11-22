from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..agents.prediction import latest_forecast
from ..db import get_db
from ..rbac import require

router = APIRouter()


@router.get("/forecast")
def forecast(db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    fc = latest_forecast(db)
    if not fc:
        raise HTTPException(503, "Forecast not available yet. Run the agent cycle.")
    clusters = {c.id: c for c in db.scalars(select(m.PinCluster)).all()}
    out = dict(fc)
    out["clusters"] = [dict(c, lat=clusters[c["cluster_id"]].lat, lon=clusters[c["cluster_id"]].lon, state=clusters[c["cluster_id"]].state,
                            pin_prefix=clusters[c["cluster_id"]].pin_prefix) for c in fc["clusters"]]
    vendors = {v.id: v.name for v in db.scalars(select(m.Vendor)).all()}
    if "breakdown" in out:
        out["breakdown"] = dict(out["breakdown"], vendors=[dict(v, name=vendors.get(v["vendor_id"])) for v in out["breakdown"]["vendors"]])
    out.pop("_returns_count", None)
    return out


@router.get("/geo")
def geo(db: Session = Depends(get_db), _: m.User = Depends(require("internal", "logistics", "warehouse"))):
    fc = latest_forecast(db) or {"clusters": []}
    by = {c["cluster_id"]: c for c in fc["clusters"]}
    return {
        "clusters": [{"id": c.id, "city": c.city, "lat": c.lat, "lon": c.lon, "pin_prefix": c.pin_prefix, "default_facility_id": c.default_facility_id,
                      "risk": by.get(c.id, {}).get("risk"), "avg_multiplier": by.get(c.id, {}).get("avg_multiplier"),
                      "expected_network_7d": by.get(c.id, {}).get("expected_network_7d")} for c in db.scalars(select(m.PinCluster)).all()],
        "facilities": [{"id": f.id, "name": f.name, "city": f.city, "lat": f.lat, "lon": f.lon, "kind": f.kind,
                        "inspection_capacity": f.inspection_capacity} for f in db.scalars(select(m.Facility)).all()],
    }
