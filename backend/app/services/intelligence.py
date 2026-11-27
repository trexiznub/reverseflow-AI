"""Product, vendor & customer intelligence: aggregates, statistical findings and
the Return Root-Cause Intelligence Graph."""
from __future__ import annotations

import math
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..reference import AVOIDABLE_REASONS, REASONS

INTERVENTION_FOR = {
    "STITCHING": ("pre_dispatch_qc", "Pre-dispatch stitching QC + vendor quality alert"),
    "FABRIC_QUALITY": ("pre_dispatch_qc", "Fabric QC at vendor inbound"),
    "SIZE_SMALL": ("size_chart_update", "Grade size chart up; add fit note"),
    "SIZE_LARGE": ("size_chart_update", "Grade size chart down; add fit note"),
    "COLOUR_MISMATCH": ("listing_fix", "Re-shoot images, correct colour name"),
    "NOT_AS_DESCRIBED": ("listing_fix", "Correct listing description"),
    "DAMAGED_IN_TRANSIT": ("packaging", "Packaging review with 3PL"),
    "CHANGED_MIND": ("exchange_first", "Offer exchange / store credit first"),
    "LATE_DELIVERY": ("promise_date", "Tighten delivery promise before festival dates"),
}


def returns_frame(db: Session, scenario_date: date, window_days: int = 90) -> pd.DataFrame:
    since = scenario_date - timedelta(days=window_days)
    df = pd.read_sql(text("""
        SELECT r.id, r.customer_id, r.sku, r.vendor_id, r.cluster_id, r.size, r.price, r.request_date, r.status, r.grade,
               r.reason_text, r.predicted_reason, r.reason_confidence, r.verified_reason, r.sentiment, r.defects,
               p.name product_name, p.category, v.name vendor_name
        FROM returns r JOIN products p ON p.sku=r.sku JOIN vendors v ON v.id=r.vendor_id
        WHERE r.request_date >= :since
    """), db.bind, params={"since": since}, parse_dates=["request_date"])
    df["reason"] = df.verified_reason.fillna(df.predicted_reason)
    return df


def _z(k: int, n: int, p0: float) -> float:
    if n == 0 or p0 <= 0 or p0 >= 1:
        return 0.0
    return (k / n - p0) / math.sqrt(p0 * (1 - p0) / n)


def findings(db: Session, scenario_date: date, window_days: int = 90) -> dict:
    df = returns_frame(db, scenario_date, window_days)
    total = len(df)
    net_share = df.reason.value_counts(normalize=True).to_dict()
    out_vendor, out_sku = [], []
    for (vid, reason), g in df.groupby(["vendor_id", "reason"]):
        vdf = df[df.vendor_id == vid]
        n, k = len(vdf), len(g)
        rest = df[df.vendor_id != vid]
        p0 = (rest.reason == reason).mean() if len(rest) else net_share.get(reason, 0)
        z = _z(k, n, p0)
        if reason in AVOIDABLE_REASONS and n >= 20 and k >= 10 and z >= 4 and k / n >= 2 * p0:
            top = g.groupby(["sku", "product_name"]).size().sort_values(ascending=False).head(4)
            sizes = g.groupby("size").size().sort_values(ascending=False)
            out_vendor.append({
                "vendor_id": vid, "vendor_name": g.vendor_name.iloc[0], "reason": reason, "reason_label": REASONS[reason],
                "returns": int(k), "vendor_returns": int(n), "share": round(k / n, 4), "network_share": round(float(p0), 4),
                "others_returns": int(len(rest)), "others_with_reason": int((rest.reason == reason).sum()),
                "z": round(z, 2), "top_skus": [{"sku": s, "name": nm, "returns": int(c)} for (s, nm), c in top.items()],
                "sizes": {s: int(c) for s, c in sizes.items()},
                "avg_sentiment": round(float(g.sentiment.mean()), 3) if g.sentiment.notna().any() else None,
                "intervention": INTERVENTION_FOR[reason][1],
            })
    cat_share = df.groupby("category").reason.value_counts(normalize=True)
    for (sku, reason), g in df.groupby(["sku", "reason"]):
        sdf = df[df.sku == sku]
        n, k = len(sdf), len(g)
        cat = sdf.category.iloc[0]
        p0 = float(cat_share.get((cat, reason), 0.01))
        z = _z(k, n, max(p0, 0.01))
        if reason in AVOIDABLE_REASONS and n >= 12 and k >= 6 and z >= 3 and k / n >= 1.8 * p0:
            out_sku.append({"sku": sku, "name": sdf.product_name.iloc[0], "vendor_id": sdf.vendor_id.iloc[0], "category": cat,
                            "reason": reason, "reason_label": REASONS[reason], "returns": int(k), "sku_returns": int(n),
                            "share": round(k / n, 4), "category_share": round(p0, 4), "z": round(z, 2),
                            "sizes": {s: int(c) for s, c in g.groupby("size").size().items()}})
    out_vendor.sort(key=lambda x: -x["z"])
    out_sku.sort(key=lambda x: -x["z"])
    return {"window_days": window_days, "total_returns": total, "network_reason_share": {k: round(v, 4) for k, v in net_share.items()},
            "vendor_findings": out_vendor, "sku_findings": out_sku}


def vendor_rankings(db: Session, scenario_date: date, window_days: int = 90) -> list[dict]:
    since = scenario_date - timedelta(days=window_days)
    o = pd.read_sql(text("""SELECT p.vendor_id, COUNT(*) n FROM orders o JOIN products p ON p.sku=o.sku
                            WHERE o.order_date >= :s AND o.delivered_date IS NOT NULL GROUP BY 1"""), db.bind, params={"s": since - timedelta(days=10)})
    df = returns_frame(db, scenario_date, window_days)
    rv = pd.read_sql(text("""SELECT p.vendor_id, AVG(rv.sentiment) s, AVG(rv.rating) rating, COUNT(*) n FROM reviews rv JOIN products p ON p.sku=rv.sku
                             WHERE rv.review_date >= :s GROUP BY 1"""), db.bind, params={"s": since})
    vendors = pd.read_sql(text("SELECT id vendor_id, name, city, specialty, qc_hold FROM vendors"), db.bind)
    rows = []
    for v in vendors.itertuples():
        g = df[df.vendor_id == v.vendor_id]
        n_orders = int(o.loc[o.vendor_id == v.vendor_id, "n"].sum())
        n_ret = len(g)
        defect = g.reason.isin(["STITCHING", "FABRIC_QUALITY"]).mean() if n_ret else 0
        size = g.reason.isin(["SIZE_SMALL", "SIZE_LARGE"]).mean() if n_ret else 0
        avoid = g.reason.isin(list(AVOIDABLE_REASONS)).mean() if n_ret else 0
        graded = g[g.grade.notna()]
        grade_c = (graded.grade == "C").mean() if len(graded) else 0
        r = rv[rv.vendor_id == v.vendor_id]
        sent = float(r.s.iloc[0]) if len(r) and pd.notna(r.s.iloc[0]) else 0.0
        rate = n_ret / n_orders if n_orders else 0
        score = 100 - (rate * 120 + defect * 60 + grade_c * 40 + size * 25 - sent * 8)
        rows.append({"vendor_id": v.vendor_id, "name": v.name, "city": v.city, "specialty": v.specialty, "qc_hold": bool(v.qc_hold),
                     "orders": n_orders, "returns": n_ret, "return_rate": round(rate, 4), "defect_rate": round(float(defect), 4),
                     "size_issue_rate": round(float(size), 4), "avoidable_rate": round(float(avoid), 4), "grade_c_rate": round(float(grade_c), 4),
                     "review_sentiment": round(sent, 3), "avg_rating": round(float(r.rating.iloc[0]), 2) if len(r) else None,
                     "quality_score": round(max(0.0, min(100.0, score)), 1)})
    rows.sort(key=lambda x: x["quality_score"])
    for i, r in enumerate(rows, 1):
        r["rank_worst_first"] = i
    return rows


def sku_reason_matrix(db: Session, scenario_date: date, sku: str, window_days: int = 180) -> dict:
    df = returns_frame(db, scenario_date, window_days)
    g = df[df.sku == sku]
    return {"sku": sku, "returns": int(len(g)), "by_reason": {k: int(v) for k, v in g.reason.value_counts().items()},
            "by_size": {k: int(v) for k, v in g["size"].value_counts().items()},
            "samples": g.sort_values("request_date", ascending=False).head(12)[["id", "reason_text", "reason", "reason_confidence", "size"]].to_dict("records")}


def build_graph(db: Session, scenario_date: date, vendor_id: str | None = None, sku: str | None = None,
                window_days: int = 90, max_customers: int = 14) -> dict:
    """Customer -> Return -> SKU -> Size -> Vendor -> Defect -> Intervention.

    Customer/return layers are sampled for legibility; all counts on SKU, size,
    vendor, defect and intervention nodes are full aggregates.
    """
    df = returns_frame(db, scenario_date, window_days)
    df = df[df.reason.isin(list(AVOIDABLE_REASONS))]
    fnd = findings(db, scenario_date, window_days)
    flagged_vendors = {f["vendor_id"] for f in fnd["vendor_findings"]}
    if vendor_id:
        df = df[df.vendor_id == vendor_id]
    elif sku:
        df = df[df.sku == sku]
    else:
        df = df[df.vendor_id.isin(flagged_vendors)] if flagged_vendors else df
    nodes, edges = {}, []

    def node(nid, ntype, label, **data):
        if nid not in nodes:
            nodes[nid] = {"id": nid, "type": ntype, "label": label, "data": data}
        return nid

    def edge(a, b, weight, label=""):
        edges.append({"id": f"{a}->{b}", "source": a, "target": b, "weight": int(weight), "label": label})

    top_skus = df.groupby("sku").size().sort_values(ascending=False).head(4).index.tolist()
    df = df[df.sku.isin(top_skus)]
    rc = df.reason.value_counts()
    material = rc[rc >= max(3, 0.06 * len(df))].index
    df = df[df.reason.isin(material)]
    for vid, gv in df.groupby("vendor_id"):
        vf = [f for f in fnd["vendor_findings"] if f["vendor_id"] == vid]
        node(f"vendor:{vid}", "vendor", gv.vendor_name.iloc[0], returns=int(len(gv)), flagged=bool(vf),
             findings=[{"reason": f["reason_label"], "share": f["share"], "network_share": f["network_share"], "z": f["z"]} for f in vf])
    for s, gs in df.groupby("sku"):
        node(f"sku:{s}", "sku", gs.product_name.iloc[0], sku=s, returns=int(len(gs)), category=gs.category.iloc[0],
             by_reason={k: int(v) for k, v in gs.reason.value_counts().items()})
        top_sizes = gs["size"].value_counts().head(3).index
        for sz, gz in gs[gs["size"].isin(top_sizes)].groupby("size"):
            nid = node(f"size:{s}:{sz}", "size", f"Size {sz}", sku=s, size=sz, returns=int(len(gz)),
                       by_reason={k: int(v) for k, v in gz.reason.value_counts().items()})
            edge(f"sku:{s}", nid, len(gz))
            edge(nid, f"vendor:{gs.vendor_id.iloc[0]}", len(gz))
    for (vid, reason), g in df.groupby(["vendor_id", "reason"]):
        did = node(f"defect:{reason}", "defect", REASONS[reason], reason=reason)
        nodes[did]["data"]["returns"] = nodes[did]["data"].get("returns", 0) + int(len(g))
        edge(f"vendor:{vid}", did, len(g), f"{len(g)} returns")
        kind, lab = INTERVENTION_FOR[reason]
        iid = node(f"intervention:{kind}", "intervention", lab, kind=kind)
        if not any(e["id"] == f"{did}->{iid}" for e in edges):
            edge(did, iid, len(g))
    # sampled customers / returns (most recent) for the human layer of the graph
    sample = df.sort_values("request_date", ascending=False).groupby("sku").head(max(2, max_customers // max(len(top_skus), 1)))
    for r in sample.itertuples():
        cid = node(f"customer:{r.customer_id}", "customer", f"Customer {r.customer_id[-5:]}", cluster=r.cluster_id)
        rid = node(f"return:{r.id}", "return", r.id, reason=REASONS.get(r.reason, r.reason), text=r.reason_text,
                   confidence=r.reason_confidence, size=r.size, verified=r.verified_reason is not None)
        edge(cid, rid, 1)
        edge(rid, f"sku:{r.sku}", 1)
    # recommendation status on intervention nodes
    recs = pd.read_sql(text("SELECT kind, status, entity_id, title FROM recommendations"), db.bind)
    for n in nodes.values():
        if n["type"] == "intervention":
            rk = recs[recs.kind == n["data"]["kind"]]
            n["data"]["recommendations"] = rk[["title", "status", "entity_id"]].to_dict("records")[:6]
    return {"nodes": list(nodes.values()), "edges": edges, "window_days": window_days,
            "note": "Customer and return nodes are a recent sample; SKU, size, vendor and defect counts are full aggregates."}


def recurring_feedback(db: Session, scenario_date: date, window_days: int = 90, top: int = 6) -> list[dict]:
    """'150 customers return the same lehenga: 110 sizing, 25 stitching...' style summaries."""
    df = returns_frame(db, scenario_date, window_days)
    out = []
    for sku, g in df.groupby("sku"):
        if len(g) < 20:
            continue
        rc = g.reason.value_counts()
        out.append({"sku": sku, "name": g.product_name.iloc[0], "vendor_id": g.vendor_id.iloc[0], "vendor_name": g.vendor_name.iloc[0],
                    "customers": int(g.customer_id.nunique()), "returns": int(len(g)),
                    "breakdown": [{"reason": k, "label": REASONS[k], "count": int(v)} for k, v in rc.items()],
                    "dominant_share": round(float(rc.iloc[0] / len(g)), 3)})
    out.sort(key=lambda x: (-x["dominant_share"] * x["returns"]))
    return out[:top]
