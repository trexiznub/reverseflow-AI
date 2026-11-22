"""Return-integrity anomaly detection.

An anomaly is NOT proof of misuse. This module produces:

* hard evidence checks (tag missing, serial mismatch, large weight deviation)
* an unsupervised IsolationForest score over behavioural features

and combines them into a transparent score with per-component contributions.
The only automated consequence is a *request for physical inspection*, which a
human reviewer approves or rejects. No customer is rejected automatically.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sqlalchemy import text
from sqlalchemy.orm import Session

FEATURES = ["abs_weight_delta", "days_to_request", "cust_return_rate", "cust_returns", "no_images", "log_price"]

_model: IsolationForest | None = None
_ref_scores: np.ndarray | None = None


def _frame(db: Session, where: str = "", params: dict | None = None) -> pd.DataFrame:
    q = f"""
    SELECT r.id, r.customer_id, r.sku, r.price, r.request_date, r.status, r.tag_intact, r.serial_returned,
           r.weight_delta_pct, r.images_count, r.cluster_id, r.reason_text, r.predicted_reason,
           o.serial_no, o.delivered_date
    FROM returns r JOIN orders o ON o.id = r.order_id
    WHERE r.tag_intact IS NOT NULL {where}
    """
    df = pd.read_sql(text(q), db.bind, params=params or {}, parse_dates=["request_date", "delivered_date"])
    stats = pd.read_sql(text("""
        SELECT c.id customer_id,
               (SELECT COUNT(*) FROM orders o WHERE o.customer_id=c.id) n_orders,
               (SELECT COUNT(*) FROM returns r WHERE r.customer_id=c.id) n_returns
        FROM customers c WHERE c.id IN (SELECT DISTINCT customer_id FROM returns WHERE tag_intact IS NOT NULL {w})
    """.replace("{w}", where.replace("r.", ""))), db.bind, params=params or {})
    df = df.merge(stats, on="customer_id", how="left")
    df["abs_weight_delta"] = df.weight_delta_pct.abs().fillna(0)
    df["days_to_request"] = (df.request_date - df.delivered_date).dt.days.fillna(5)
    df["cust_returns"] = df.n_returns.fillna(1)
    df["cust_return_rate"] = (df.n_returns / df.n_orders.clip(lower=1)).fillna(0)
    df["no_images"] = (df.images_count == 0).astype(int)
    df["log_price"] = np.log(df.price)
    df["tag_missing"] = (~df.tag_intact.astype(bool)).astype(int)
    df["serial_mismatch"] = (df.serial_returned != df.serial_no).astype(int)
    return df


def train(db: Session) -> dict:
    global _model, _ref_scores
    df = _frame(db, "AND r.status = 'recovered'")
    _model = IsolationForest(n_estimators=200, contamination="auto", random_state=5).fit(df[FEATURES].values)
    _ref_scores = np.sort(-_model.score_samples(df[FEATURES].values))
    return {"train_n": int(len(df)), "features": FEATURES, "model": "IsolationForest(n_estimators=200)",
            "note": "Unsupervised. No ground-truth labels exist, so no accuracy is claimed."}


def score(db: Session, return_ids: list[str] | None = None, open_only: bool = True) -> list[dict]:
    if _model is None:
        train(db)
    where = "AND r.status IN ('in_transit','received','inspected')" if open_only else ""
    params = {}
    if return_ids:
        where += " AND r.id IN (" + ",".join(f":r{i}" for i in range(len(return_ids))) + ")"
        params = {f"r{i}": v for i, v in enumerate(return_ids)}
    df = _frame(db, where, params)
    if df.empty:
        return []
    raw = -_model.score_samples(df[FEATURES].values)
    pct = np.searchsorted(_ref_scores, raw) / len(_ref_scores)
    out = []
    for row, p in zip(df.itertuples(), pct):
        weight_flag = abs(row.weight_delta_pct or 0) >= 8
        comps = {
            "tag_missing": 0.35 * row.tag_missing,
            "serial_mismatch": 0.40 * row.serial_mismatch,
            "weight_deviation": 0.10 * int(weight_flag),
            "behavioural_outlier": round(0.15 * float(p), 3),
        }
        s = round(min(1.0, sum(comps.values())), 3)
        evidence = []
        if row.tag_missing:
            evidence.append("Brand tag not attached at pickup (courier checklist)")
        if row.serial_mismatch:
            evidence.append(f"Returned serial {row.serial_returned} does not match dispatched serial {row.serial_no}")
        if weight_flag:
            evidence.append(f"Parcel weight deviates {row.weight_delta_pct:+.1f}% from dispatch weight")
        if p >= 0.97:
            evidence.append(f"Behavioural pattern in top {100 - p * 100:.1f}% of historical returns (return rate {row.cust_return_rate:.0%})")
        out.append({
            "return_id": row.id, "customer_id": row.customer_id, "sku": row.sku, "cluster_id": row.cluster_id,
            "status": row.status, "score": s, "components": comps, "behavioural_percentile": round(float(p), 4),
            "hard_evidence": bool(row.tag_missing or row.serial_mismatch),
            "evidence": evidence, "features": {k: (round(float(getattr(row, k)), 3)) for k in FEATURES},
        })
    return out
