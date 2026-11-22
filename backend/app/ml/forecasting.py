"""Return volume forecasting.

Two models are compared on held-out data:

* Baseline: seasonal-naive. The mean of the same weekday 7/14/21/28 days earlier.
* ML: gradient-boosted trees (Poisson loss) on calendar, festival-proximity,
  lagged order and lagged return features, plus quantile models for P10/P90.

Every feature for target day d uses only data available at d-7 (LEAD = 7), so a
single model produces honest forecasts for horizons 1-7 days. That is where the
5-7 day early warning comes from: festive orders placed before the festival are
already known when the post-festival wave is forecast.

All metrics are computed from held-out data; nothing here is hard-coded.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingRegressor
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..reference import CLUSTERS, FESTIVALS

LEAD = 7
HORIZON = 7
FESTIVE_CATS = ("Lehenga", "Indo-western", "Festive dress")
NAV = [(n, s, e) for n, s, e, k in FESTIVALS if n.startswith("Navratri")]
DIW = [(n, s, e) for n, s, e, k in FESTIVALS if n.startswith("Diwali")]
FEATURES = [
    "dow", "dsn", "wave_kernel", "fest_orders", "fest_x_kernel", "orders_lag", "ret_lag7",
    "ret_mean7", "ret_mean28", "same_dow_mean", "cluster_level", "dsd_kernel", "cluster_code", "fest_ratio", "fest_ratio_x_kernel", "prior_uplift_x_kernel", "fest_lift_x_kernel",
]


def _kernel(x: np.ndarray, a=1.0, c=5.5, b=10.0) -> np.ndarray:
    """Triangular kernel over days-since-festival-end."""
    x = np.asarray(x, dtype=float)
    up = np.clip((x - a) / (c - a), 0, 1)
    down = np.clip((b - x) / (b - c), 0, 1)
    return np.where((x >= a) & (x <= b), np.minimum(up, down), 0.0)


def load_daily(db: Session, end: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    r = pd.read_sql(text("SELECT cluster_id, request_date FROM returns"), db.bind, parse_dates=["request_date"])
    o = pd.read_sql(text("SELECT o.cluster_id, o.order_date, o.festival_tag, p.category FROM orders o JOIN products p ON p.sku=o.sku"),
                    db.bind, parse_dates=["order_date"])
    days = pd.date_range(min(r.request_date.min(), o.order_date.min()), pd.Timestamp(end), freq="D")
    clusters = [c[0] for c in CLUSTERS]
    idx = pd.MultiIndex.from_product([clusters, days], names=["cluster_id", "day"])
    ret = r.groupby(["cluster_id", "request_date"]).size().reindex(idx, fill_value=0).rename("returns")
    ordc = o.groupby(["cluster_id", "order_date"]).size().reindex(idx, fill_value=0).rename("orders")
    o["fest"] = o.festival_tag.fillna("").str.startswith("Navratri") & o.category.isin(FESTIVE_CATS)
    fest = o[o.fest].groupby(["cluster_id", "order_date"]).size().reindex(idx, fill_value=0).rename("fest_orders_day")
    fcat = o[o.category.isin(FESTIVE_CATS)].groupby(["cluster_id", "order_date"]).size().reindex(idx, fill_value=0).rename("festive_cat_orders")
    daily = pd.concat([ret, ordc, fest, fcat], axis=1).reset_index()
    return daily, r


def _days_since_nav_end(day: pd.Timestamp) -> float:
    best = 99.0
    for _, s, e in NAV:
        dsn = (day.date() - e).days
        if -40 <= dsn <= 40 and abs(dsn) < abs(best):
            best = dsn
    return float(best)


def _days_since_diwali_end(day: pd.Timestamp) -> float:
    best = 99.0
    for _, s, e in DIW:
        d = (day.date() - e).days
        if -40 <= d <= 40 and abs(d) < abs(best):
            best = d
    return float(best)


def build_features(daily: pd.DataFrame, extend_to: date | None = None) -> pd.DataFrame:
    """Feature frame indexed by (cluster, target day). Uses only info at d-LEAD."""
    frames = []
    for cid, g in daily.groupby("cluster_id"):
        g = g.set_index("day").sort_index()
        festive_cat = g["festive_cat_orders"].fillna(0) if "festive_cat_orders" in g else g["fest_orders_day"].fillna(0)
        if extend_to is not None:
            future = pd.date_range(g.index.max() + pd.Timedelta(days=1), pd.Timestamp(extend_to))
            g = pd.concat([g, pd.DataFrame(index=future, data={"cluster_id": cid, "returns": np.nan, "orders": np.nan, "fest_orders_day": np.nan, "festive_cat_orders": np.nan})])
        f = pd.DataFrame(index=g.index)
        f["cluster_id"] = cid
        f["returns"] = g["returns"]
        known_ret = g["returns"].shift(LEAD)
        known_ord = g["orders"].shift(LEAD)
        f["ret_lag7"] = known_ret
        f["ret_mean7"] = known_ret.rolling(7, min_periods=3).mean()
        f["ret_mean28"] = known_ret.rolling(28, min_periods=10).mean()
        f["same_dow_mean"] = pd.concat([g["returns"].shift(k) for k in (7, 14, 21, 28)], axis=1).mean(axis=1)
        f["orders_lag"] = known_ord.rolling(14, min_periods=5).sum()
        f["cluster_level"] = known_ret.rolling(90, min_periods=20).mean()
        # festive orders for the most recent Navratri, counted up to d-LEAD
        fest_cum, fest_lift = [], []
        fo = g["fest_orders_day"].fillna(0)
        for day in f.index:
            cutoff = day - pd.Timedelta(days=LEAD)
            tot, lift = 0.0, 1.0
            for _, s, e in NAV:
                if pd.Timestamp(s) - pd.Timedelta(days=25) <= day <= pd.Timestamp(e) + pd.Timedelta(days=14):
                    lo = pd.Timestamp(s) - pd.Timedelta(days=25)
                    hi = min(cutoff, pd.Timestamp(e))
                    if hi >= lo:
                        tot = float(fo.loc[lo:hi].sum())
                        # festive-category order lift vs the same cluster's pre-season rate
                        base = festive_cat.loc[pd.Timestamp(s) - pd.Timedelta(days=75): pd.Timestamp(s) - pd.Timedelta(days=40)].mean()
                        cur = festive_cat.loc[lo:hi].mean()
                        if base and base > 0:
                            lift = float(cur / base)
            fest_cum.append(tot)
            fest_lift.append(lift)
        f["fest_orders"] = fest_cum
        f["fest_lift"] = fest_lift
        f["dsn"] = [_days_since_nav_end(d) for d in f.index]
        f["wave_kernel"] = _kernel(f["dsn"].values)
        f["fest_x_kernel"] = f["fest_orders"] * f["wave_kernel"]
        f["dsd_kernel"] = _kernel(np.array([_days_since_diwali_end(d) for d in f.index]), 0, 4, 9)
        # uplift observed in this cluster after the previous Navratri (known in advance)
        prior = pd.Series(1.0, index=f.index)
        r_hist = g["returns"]
        for i in range(1, len(NAV)):
            _, ps, pe = NAV[i - 1]
            _, cs, ce = NAV[i]
            wave = r_hist.loc[pd.Timestamp(pe) + pd.Timedelta(days=1): pd.Timestamp(pe) + pd.Timedelta(days=10)]
            pre = r_hist.loc[pd.Timestamp(ps) - pd.Timedelta(days=60): pd.Timestamp(ps) - pd.Timedelta(days=26)]
            if len(wave) and len(pre) and pre.mean() > 0:
                upl = float(wave.mean() / pre.mean())
                mask = (f.index >= pd.Timestamp(cs) - pd.Timedelta(days=25)) & (f.index <= pd.Timestamp(ce) + pd.Timedelta(days=14))
                prior[mask] = upl
        f["prior_uplift"] = prior.values
        f["prior_uplift_x_kernel"] = f["prior_uplift"] * f["wave_kernel"]
        f["dow"] = f.index.dayofweek
        f["month"] = f.index.month
        frames.append(f.reset_index(names="day"))
    out = pd.concat(frames, ignore_index=True)
    order = [c[0] for c in CLUSTERS]
    out["cluster_code"] = out["cluster_id"].map({c: i for i, c in enumerate(order)})
    out["fest_ratio"] = out["fest_orders"] / (out["orders_lag"].clip(lower=1) * 2.0)
    out["fest_ratio_x_kernel"] = out["fest_ratio"] * out["wave_kernel"]
    out["fest_lift_x_kernel"] = (out["fest_lift"] - 1).clip(lower=0) * out["wave_kernel"]
    return out


def _metrics(y: np.ndarray, p: np.ndarray) -> dict:
    y, p = np.asarray(y, float), np.asarray(p, float)
    err = p - y
    return {
        "mae": round(float(np.mean(np.abs(err))), 3),
        "rmse": round(float(np.sqrt(np.mean(err ** 2))), 3),
        "wape": round(float(np.sum(np.abs(err)) / max(np.sum(y), 1e-9)), 4),
        "bias": round(float(np.sum(err) / max(np.sum(y), 1e-9)), 4),
        "n": int(len(y)),
    }


@dataclass
class TrainedModels:
    point: HistGradientBoostingRegressor
    lo: GradientBoostingRegressor
    hi: GradientBoostingRegressor


def _fit(train: pd.DataFrame) -> TrainedModels:
    X, y = train[FEATURES].fillna(0).values, train["returns"].values
    point = HistGradientBoostingRegressor(loss="poisson", max_iter=300, learning_rate=0.05, max_leaf_nodes=24,
                                          min_samples_leaf=20, l2_regularization=1.0, random_state=7).fit(X, y)
    lo = GradientBoostingRegressor(loss="quantile", alpha=0.1, n_estimators=150, max_depth=3, learning_rate=0.05, random_state=7).fit(X, y)
    hi = GradientBoostingRegressor(loss="quantile", alpha=0.9, n_estimators=150, max_depth=3, learning_rate=0.05, random_state=7).fit(X, y)
    return TrainedModels(point, lo, hi)


def _predict(models: TrainedModels, df: pd.DataFrame):
    X = df[FEATURES].fillna(0).values
    p = models.point.predict(X)
    lo = np.minimum(models.lo.predict(X), p)
    hi = np.maximum(models.hi.predict(X), p)
    return np.clip(p, 0, None), np.clip(lo, 0, None), np.clip(hi, 0, None)


def backtest(feat: pd.DataFrame, train_end: str, test_start: str, test_end: str, label: str) -> dict:
    valid = feat.dropna(subset=["returns", "ret_mean28"])
    train = valid[valid.day < pd.Timestamp(train_end)]
    test = valid[(valid.day >= pd.Timestamp(test_start)) & (valid.day <= pd.Timestamp(test_end))].copy()
    models = _fit(train)
    p, lo, hi = _predict(models, test)
    test["ml"], test["lo"], test["hi"] = p, lo, hi
    test["baseline"] = test["same_dow_mean"].fillna(test["ret_mean28"]).fillna(0)
    surge = test[test.cluster_id.isin(["PNQ", "AMD", "JAI"]) & (test.wave_kernel > 0)]
    res = {
        "label": label, "train_end": train_end, "test_start": test_start, "test_end": test_end,
        "rows_train": int(len(train)), "rows_test": int(len(test)),
        "daily_cluster": {"baseline": _metrics(test.returns, test.baseline), "ml": _metrics(test.returns, test.ml)},
        "surge_window": {"baseline": _metrics(surge.returns, surge.baseline), "ml": _metrics(surge.returns, surge.ml)} if len(surge) else None,
        "interval_coverage_p10_p90": round(float(((test.returns >= test.lo) & (test.returns <= test.hi)).mean()), 3),
    }
    # weekly aggregate accuracy (planning grain)
    wk = test.assign(week=test.day.dt.to_period("W").dt.start_time).groupby(["cluster_id", "week"])[["returns", "ml", "baseline"]].sum()
    res["weekly_cluster"] = {"baseline": _metrics(wk.returns, wk.baseline), "ml": _metrics(wk.returns, wk.ml)}
    # surge detection lead time: first day a 7-day-ahead forecast crosses 1.5x normal vs actual peak
    leads = []
    for cid in ["PNQ", "AMD", "JAI"]:
        t = test[test.cluster_id == cid].set_index("day").sort_index()
        normal = float(t["cluster_level"].iloc[0]) if len(t) else 0
        if normal <= 0:
            continue
        roll = t["returns"].rolling(3, center=True).mean()
        wave = t[t.wave_kernel > 0]
        if wave.empty:
            continue
        peak = roll.loc[wave.index].idxmax()
        wave_start = wave.index.min() - pd.Timedelta(days=2)
        crossed = t[(t.ml >= 1.5 * normal) & (t.index <= peak) & (t.index >= wave_start)]
        if len(crossed):
            first = crossed.index.min()
            issued = first - pd.Timedelta(days=LEAD)
            leads.append({"cluster_id": cid, "peak": peak.date().isoformat(), "alert_issued": issued.date().isoformat(),
                          "lead_days": int((peak - issued).days)})
    res["surge_lead_time"] = leads
    series = test[test.cluster_id.isin(["PNQ", "AMD", "JAI", "BOM"])][["cluster_id", "day", "returns", "baseline", "ml", "lo", "hi"]]
    res["series"] = [
        {"cluster_id": r.cluster_id, "day": r.day.date().isoformat(), "actual": int(r.returns), "baseline": round(float(r.baseline), 2),
         "ml": round(float(r.ml), 2), "lo": round(float(r.lo), 2), "hi": round(float(r.hi), 2)}
        for r in series.itertuples()
    ]
    imp = getattr(models.point, "feature_importances_", None)
    return res


def run_forecast(db: Session, scenario_date: date, network_scale: dict[str, float]) -> dict:
    daily, _ = load_daily(db, scenario_date)
    feat = build_features(daily, extend_to=scenario_date + timedelta(days=HORIZON))

    evaluations = [
        backtest(feat, "2025-09-01", "2025-09-01", "2025-11-15", "Festive-season holdout 2025 (Navratri + Diwali)"),
        backtest(feat, "2026-06-01", "2026-06-01", scenario_date.isoformat(), "Recent holdout 2026 (Jun to scenario date)"),
    ]

    valid = feat.dropna(subset=["returns", "ret_mean28"])
    models = _fit(valid)
    fut = feat[(feat.day > pd.Timestamp(scenario_date)) & (feat.day <= pd.Timestamp(scenario_date + timedelta(days=HORIZON)))].copy()
    p, lo, hi = _predict(models, fut)
    fut["ml"], fut["lo"], fut["hi"] = p, lo, hi

    # normal level per cluster in sample units = mean daily returns Mar-Aug 2026 (same window as network scale)
    normal = daily[(daily.day >= "2026-03-01") & (daily.day <= "2026-08-31")].groupby("cluster_id")["returns"].mean()
    hist = daily[daily.day > pd.Timestamp(scenario_date - timedelta(days=45))]
    cluster_city = {c[0]: c[1] for c in CLUSTERS}
    clusters_out = []
    alerts = []
    for cid in [c[0] for c in CLUSTERS]:
        f = fut[fut.cluster_id == cid].sort_values("day")
        h = hist[hist.cluster_id == cid].sort_values("day")
        nm = float(normal.get(cid, 1.0)) or 1.0
        sc = float(network_scale.get(cid, 1.0))
        points = [{"day": r.day.date().isoformat(), "forecast": round(float(r.ml), 2), "lo": round(float(r.lo), 2), "hi": round(float(r.hi), 2),
                   "multiplier": round(float(r.ml) / nm, 2), "network_forecast": int(round(r.ml * sc)),
                   "network_lo": int(round(r.lo * sc)), "network_hi": int(round(r.hi * sc))} for r in f.itertuples()]
        peak = max(points, key=lambda x: x["forecast"]) if points else None
        avg_mult = float(np.mean([p_["multiplier"] for p_ in points])) if points else 1.0
        peak_mult = peak["multiplier"] if peak else 1.0
        entry = {
            "cluster_id": cid, "city": cluster_city[cid], "normal_sample_daily": round(nm, 2), "network_scale": round(sc, 1),
            "network_normal_daily": int(round(nm * sc)),
            "history": [{"day": r.day.date().isoformat(), "actual": int(r.returns)} for r in h.itertuples()],
            "forecast": points, "avg_multiplier": round(avg_mult, 2), "peak_multiplier": round(peak_mult, 2),
            "peak_day": peak["day"] if peak else None,
            "peak_network": peak["network_forecast"] if peak else None,
            "additional_network_at_peak": int(round(peak["network_forecast"] - nm * sc)) if peak else 0,
            "expected_network_7d": int(sum(p_["network_forecast"] for p_ in points)),
            "risk": "high" if avg_mult >= 1.9 else ("elevated" if avg_mult >= 1.4 else "normal"),
        }
        clusters_out.append(entry)
        if avg_mult >= 1.5:
            lead = (date.fromisoformat(peak["day"]) - scenario_date).days
            alerts.append({"cluster_id": cid, "city": cluster_city[cid], "peak_day": peak["day"], "lead_days": lead,
                           "peak_multiplier": round(peak_mult, 2), "avg_multiplier": round(avg_mult, 2),
                           "additional_network_at_peak": entry["additional_network_at_peak"]})
    ethnic_mult = float(np.mean([c["avg_multiplier"] for c in clusters_out if c["cluster_id"] in ("PNQ", "AMD", "JAI")]))
    return {
        "origin": scenario_date.isoformat(), "horizon_days": HORIZON, "lead_days": LEAD,
        "model": {"point": "HistGradientBoostingRegressor(loss=poisson)", "interval": "GradientBoostingRegressor quantile P10/P90",
                  "baseline": "Seasonal naive: mean of same weekday at t-7, t-14, t-21, t-28", "features": FEATURES,
                  "training_rows": int(len(valid))},
        "evaluations": evaluations, "clusters": clusters_out, "surge_alerts": alerts,
        "west_surge_avg_multiplier": round(ethnic_mult, 2),
    }


def breakdown_by_vendor_sku(db: Session, scenario_date: date, clusters: list[dict]) -> dict:
    """Disaggregate cluster forecasts to vendor / SKU / size using open festive exposure.

    Exposure = delivered, not-yet-returned orders from the last 30 days, weighted
    by each SKU-size's empirical return rate over the history.
    """
    since = scenario_date - timedelta(days=30)
    o = pd.read_sql(text("""
        SELECT o.id, o.cluster_id, o.sku, o.size, p.vendor_id, p.category, p.name
        FROM orders o JOIN products p ON p.sku=o.sku
        WHERE o.delivered_date IS NOT NULL AND o.order_date >= :since
          AND o.id NOT IN (SELECT order_id FROM returns)
    """), db.bind, params={"since": since})
    rates = pd.read_sql(text("""
        SELECT o.sku, o.size, COUNT(*) n, SUM(CASE WHEN r.id IS NOT NULL THEN 1 ELSE 0 END) k
        FROM orders o LEFT JOIN returns r ON r.order_id=o.id GROUP BY o.sku, o.size
    """), db.bind)
    rates["rate"] = (rates.k + 1) / (rates.n + 10)
    o = o.merge(rates[["sku", "size", "rate"]], on=["sku", "size"], how="left").fillna({"rate": 0.12})
    fc = {c["cluster_id"]: c["expected_network_7d"] for c in clusters}
    rows = []
    for cid, g in o.groupby("cluster_id"):
        w = g.rate / g.rate.sum()
        g = g.assign(expected=w * fc.get(cid, 0))
        rows.append(g)
    if not rows:
        return {"vendors": [], "skus": [], "sizes": []}
    allr = pd.concat(rows)
    vend = allr.groupby("vendor_id").expected.sum().sort_values(ascending=False)
    sku = allr.groupby(["sku", "name", "vendor_id"]).expected.sum().sort_values(ascending=False).head(15)
    size = allr.groupby("size").expected.sum()
    return {
        "vendors": [{"vendor_id": k, "expected_network_7d": int(v)} for k, v in vend.items()],
        "skus": [{"sku": k[0], "name": k[1], "vendor_id": k[2], "expected_network_7d": int(v)} for k, v in sku.items()],
        "sizes": [{"size": k, "expected_network_7d": int(v)} for k, v in size.items()],
        "method": "Open 30-day delivered orders x smoothed historical return rate per SKU-size, scaled to each cluster's 7-day forecast",
    }
