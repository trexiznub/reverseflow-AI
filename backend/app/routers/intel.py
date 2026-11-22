from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..db import get_db
from ..ml import nlp
from ..rbac import require
from ..reference import REASONS
from ..services import intelligence as intel
from ..services import settings as st

router = APIRouter()


@router.get("/intelligence/summary")
def summary(window: int = 90, db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    D = st.scenario_date(db)
    nlp.ensure_trained(db)
    f = intel.findings(db, D, window)
    df = intel.returns_frame(db, D, window)
    by_cat = df.groupby(["category", "reason"]).size().unstack(fill_value=0)
    terms = {}
    for v in f["vendor_findings"][:4]:
        try:
            terms[v["reason"]] = nlp.top_terms(v["reason"])
        except Exception:
            pass
    return {
        "window_days": window, "total_returns": f["total_returns"], "reasons": REASONS,
        "reason_share": f["network_reason_share"], "vendor_findings": f["vendor_findings"], "sku_findings": f["sku_findings"][:15],
        "vendor_rankings": intel.vendor_rankings(db, D, window), "recurring_feedback": intel.recurring_feedback(db, D, window),
        "category_reason": {cat: {k: int(v) for k, v in row.items()} for cat, row in by_cat.iterrows()},
        "model_metrics": nlp.metrics(), "indicative_terms": terms,
        "sentiment_by_reason": {k: round(float(v), 3) for k, v in df.groupby("reason").sentiment.mean().dropna().items()},
    }


@router.get("/intelligence/graph")
def graph(vendor_id: str | None = None, sku: str | None = None, window: int = 90, db: Session = Depends(get_db),
          _: m.User = Depends(require("internal"))):
    return intel.build_graph(db, st.scenario_date(db), vendor_id=vendor_id, sku=sku, window_days=window)


@router.get("/intelligence/sku/{sku}")
def sku_detail(sku: str, db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    p = db.get(m.Product, sku)
    if not p:
        raise HTTPException(404, "SKU not found")
    d = intel.sku_reason_matrix(db, st.scenario_date(db), sku)
    reviews = db.scalars(select(m.Review).where(m.Review.sku == sku).order_by(m.Review.review_date.desc()).limit(8)).all()
    return {"product": {"sku": p.sku, "name": p.name, "category": p.category, "vendor_id": p.vendor_id, "price": p.price, "description": p.description,
                        "size_chart": p.size_chart, "size_chart_version": p.size_chart_version, "pre_dispatch_qc": p.pre_dispatch_qc,
                        "exchange_first": p.exchange_first},
            **d, "reviews": [{"rating": r.rating, "text": r.text, "sentiment": r.sentiment, "date": r.review_date.isoformat()} for r in reviews]}


@router.post("/intelligence/classify")
def classify(body: dict, db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    text = (body or {}).get("text", "").strip()
    if not text:
        raise HTTPException(400, "text required")
    nlp.ensure_trained(db)
    (label, conf), = nlp.classify([text])
    (s,) = nlp.sentiment([text])
    proba = nlp._reason_model.predict_proba([text])[0]
    return {"reason": label, "label": REASONS[label], "confidence": round(conf, 3), "sentiment": s,
            "distribution": sorted([{"reason": c, "p": round(float(p), 3)} for c, p in zip(nlp._reason_model.classes_, proba)], key=lambda x: -x["p"])[:5]}
