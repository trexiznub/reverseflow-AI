"""Deterministic synthetic data generator for the REVERSEFLOW AI demo.

ALL RECORDS PRODUCED HERE ARE SYNTHETIC. They are shaped to contain realistic,
discoverable correlations (not hard-coded answers):

* Two vendors carry hidden quality problems (V03 stitching, V07 sizes run small).
  The agents must find these from return text, reviews and inspection grades.
* XS / XXL sizes have elevated fit returns.
* Festive-window ethnicwear orders produce a post-festival return wave whose
  intensity depends on regional Navratri intensity (Ahmedabad > Pune/Jaipur > ...).
* Pickup and inspection delays grow when network load exceeds capacity.

Run:  python -m app.seed.generate        (from backend/)
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta

import numpy as np
from sqlalchemy import insert

from .. import models as m
from ..db import Base, engine, session_scope
from ..reference import (
    CATEGORIES, CLUSTERS, DEMO_CUSTOMERS, DEMO_USERS, FACILITIES, FESTIVALS, FIRST_NAMES,
    HISTORY_START, LAST_NAMES, PROVIDERS, REASON_CATEGORY, SCENARIO_DATE, SEED, SIZE_WEIGHTS,
    SIZES, VENDORS,
)
from .text_bank import product_description, reason_text, review_text

D = SCENARIO_DATE
FESTIVE_CATS = {"Lehenga", "Indo-western", "Festive dress"}


def _daterange(a: date, b: date):
    for i in range((b - a).days + 1):
        yield a + timedelta(days=i)


def _festivals(kind: str, name_prefix: str | None = None):
    return [f for f in FESTIVALS if f[3] == kind and (name_prefix is None or f[0].startswith(name_prefix))]


NAVRATRIS = _festivals("festival", "Navratri")
DIWALIS = _festivals("festival", "Diwali")
WEDDINGS = _festivals("wedding-season")


def demand_profile(day: date, category: str, nav_intensity: float) -> tuple[float, str | None]:
    """Order-rate multiplier for a category on a day, plus festival tag."""
    mult, tag = 1.0, None
    for name, s, e, _ in NAVRATRIS:
        pre = (s - day).days
        if -5 <= (day - s).days <= 5 or 0 <= pre <= 21:
            if category in FESTIVE_CATS:
                ramp = 1.0 if pre <= 10 else (21 - pre) / 11
                mult *= 1 + 1.0 * nav_intensity * max(ramp, 0.2)
                tag = name
            elif category == "Saree" and nav_intensity < 0.4:  # Durga Puja in the east
                mult *= 1.4
    for name, s, e, _ in DIWALIS:
        pre = (s - day).days
        if 0 <= pre <= 16 and category in {"Saree", "Kurta set", "Festive dress"}:
            mult *= 1.7
            tag = tag or name
    for name, s, e, _ in WEDDINGS:
        if s <= day <= e and category in {"Lehenga", "Saree"}:
            mult *= 1.3
    return mult, tag


def build_products(rng: np.random.Generator):
    colours = ["Maroon", "Emerald", "Mustard", "Rani pink", "Royal blue", "Ivory", "Teal", "Wine", "Peach", "Black", "Magenta", "Bottle green"]
    styles = {
        "Lehenga": ["Mirror-work chaniya choli", "Bandhani lehenga", "Gota patti lehenga", "Zardozi bridal lehenga", "Navratri flared lehenga", "Kutchi embroidered lehenga"],
        "Saree": ["Banarasi silk saree", "Kanjeevaram silk saree", "Chanderi cotton-silk saree", "Bandhani georgette saree", "Organza floral saree"],
        "Kurta set": ["Chikankari kurta set", "Block-print anarkali set", "Straight kurta with palazzo", "Angrakha kurta set"],
        "Indo-western": ["Cape-sleeve fusion gown", "Dhoti-pant co-ord set", "Jacket lehenga set", "Draped saree gown"],
        "Festive dress": ["Tiered festive maxi", "Embroidered festive midi", "Sequin festive gown"],
    }
    fabrics = {"Lehenga": ["Georgette", "Silk", "Cotton", "Velvet"], "Saree": ["Silk", "Georgette", "Cotton-silk", "Organza"],
               "Kurta set": ["Cotton", "Rayon", "Linen"], "Indo-western": ["Crepe", "Georgette", "Satin"], "Festive dress": ["Georgette", "Net", "Crepe"]}
    vendor_for_cat = defaultdict(list)
    for vid, _, _, spec, _ in VENDORS:
        vendor_for_cat[spec].append(vid)
    cat_to_spec = {"Lehenga": "Lehengas", "Saree": "Sarees", "Kurta set": "Kurta sets", "Indo-western": "Indo-western", "Festive dress": "Festive dresses"}
    counts = {"Lehenga": 20, "Saree": 14, "Kurta set": 12, "Indo-western": 8, "Festive dress": 8}
    products = []
    for cat, n in counts.items():
        vids = vendor_for_cat[cat_to_spec[cat]]
        # lehenga specialists also produce indo-western / festive dresses occasionally
        for i in range(n):
            vid = vids[i % len(vids)]
            if cat in {"Indo-western", "Festive dress"} and i % 3 == 2:
                vid = "V03" if i % 2 else "V07"
            style = styles[cat][i % len(styles[cat])]
            colour = colours[(i * 5 + len(cat)) % len(colours)]
            lo, hi = CATEGORIES[cat][1]
            price = float(round(rng.uniform(lo, hi) / 50) * 50 - 1)
            fabric = fabrics[cat][i % len(fabrics[cat])]
            code = {"Lehenga": "LHG", "Saree": "SAR", "Kurta set": "KRT", "Indo-western": "IDW", "Festive dress": "FDR"}[cat]
            sku = f"{code}-{vid}-{i + 1:03d}"
            bust = {"XS": 32, "S": 34, "M": 36, "L": 38, "XL": 40, "XXL": 42}
            waist = {"XS": 26, "S": 28, "M": 30, "L": 32, "XL": 34, "XXL": 36}
            chart = {} if cat == "Saree" else {s: {"bust_in": bust[s], "waist_in": waist[s], "length_in": 40 if cat == "Lehenga" else 44} for s in SIZES}
            products.append(dict(
                sku=sku, name=f"{style}, {colour.lower()}", category=cat, vendor_id=vid, price=price,
                fabric=fabric, colour=colour, description=product_description(cat, style, colour, fabric),
                size_chart=chart, size_chart_version=1,
                season="festive" if cat in FESTIVE_CATS else ("wedding" if cat == "Saree" else "all-season"),
                pre_dispatch_qc=False, exchange_first=False, is_synthetic=True,
            ))
    return products


def generate(verbose: bool = True) -> dict:
    rng = np.random.default_rng(SEED)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    vendor_profile = {v[0]: v[4] for v in VENDORS}
    products = build_products(rng)
    prod_by_cat = defaultdict(list)
    for p in products:
        prod_by_cat[p["category"]].append(p)
    # popularity weights per SKU (zipf-ish), fixed per seed
    pop = {cat: rng.dirichlet(np.ones(len(lst)) * 1.5) for cat, lst in prod_by_cat.items()}
    colour_problem_skus = {p["sku"] for p in products if p["vendor_id"] == "V09"} | {prod_by_cat["Festive dress"][1]["sku"]}

    cluster_info = {c[0]: c for c in CLUSTERS}
    base_cat_mix = {"Lehenga": 0.26, "Saree": 0.22, "Kurta set": 0.28, "Indo-western": 0.12, "Festive dress": 0.12}

    # ---------------- customers -----------------
    customers = []
    cust_by_cluster = defaultdict(list)
    n_cust = {c[0]: int(c[9] * 260) for c in CLUSTERS}
    for cid, n in n_cust.items():
        prefix = cluster_info[cid][3]
        for i in range(n):
            cust_id = f"C-{cid}-{i + 1:05d}"
            name = f"{FIRST_NAMES[rng.integers(len(FIRST_NAMES))]} {LAST_NAMES[rng.integers(len(LAST_NAMES))]}"
            customers.append(dict(id=cust_id, name=name, cluster_id=cid, pin=f"{prefix}{rng.integers(1, 99):03d}", is_synthetic=True))
            cust_by_cluster[cid].append(cust_id)
    # habitual returners (small share) — used to give the anomaly model realistic signal
    habitual = set(rng.choice([c["id"] for c in customers], size=len(customers) // 150, replace=False))
    for cid_, name, cl, pin, *_ in DEMO_CUSTOMERS:
        customers.append(dict(id=cid_, name=name, cluster_id=cl, pin=pin, is_synthetic=True))

    # ---------------- orders -----------------
    orders, order_meta = [], []
    oid = 0
    for day in _daterange(HISTORY_START, D):
        trend = 1 + 0.18 * ((day - HISTORY_START).days / 365)
        dow = [0.95, 0.9, 0.92, 0.97, 1.05, 1.15, 1.1][day.weekday()]
        for cid, info in cluster_info.items():
            nav_int = info[8]
            for cat, share in base_cat_mix.items():
                mult, tag = demand_profile(day, cat, nav_int)
                lam = info[9] * share * trend * dow * mult
                n = rng.poisson(lam)
                if not n:
                    continue
                plist = prod_by_cat[cat]
                idx = rng.choice(len(plist), size=n, p=pop[cat])
                sizes = rng.choice(SIZES, size=n, p=SIZE_WEIGHTS) if cat != "Saree" else ["Free"] * n
                custs = rng.choice(cust_by_cluster[cid], size=n)
                for k in range(n):
                    p = plist[idx[k]]
                    oid += 1
                    deliv = day + timedelta(days=int(rng.integers(2, 6)))
                    order = dict(
                        id=f"OD{oid:07d}", customer_id=str(custs[k]), sku=p["sku"], size=str(sizes[k]),
                        price=p["price"], order_date=day, delivered_date=deliv if deliv <= D else None,
                        cluster_id=cid, festival_tag=tag, serial_no=f"SN{p['sku'][:3]}{rng.integers(10**7, 10**8)}",
                        is_synthetic=True,
                    )
                    orders.append(order)
                    order_meta.append((order, p))

    # Demo customers: a guaranteed, recently delivered, not-yet-returned order each
    demo_orders = []
    for i, (cid_, name, cl, pin, vid, cat, size) in enumerate(DEMO_CUSTOMERS):
        p = next(pp for pp in prod_by_cat[cat] if pp["vendor_id"] == vid)
        for j, (od, dd) in enumerate([(D - timedelta(days=12), D - timedelta(days=8)), (D - timedelta(days=60), D - timedelta(days=56))]):
            pp = p if j == 0 else prod_by_cat["Kurta set"][i]
            oid += 1
            o = dict(id=f"OD{oid:07d}", customer_id=cid_, sku=pp["sku"], size=size if pp["category"] != "Saree" else "Free",
                     price=pp["price"], order_date=od, delivered_date=dd, cluster_id=cl,
                     festival_tag="Navratri 2026" if j == 0 else None,
                     serial_no=f"SN{pp['sku'][:3]}{rng.integers(10**7, 10**8)}", is_synthetic=True)
            orders.append(o)
            demo_orders.append(o["id"])
        # a second recent order (a saree) so the customer has more than one choice
        sp = prod_by_cat["Saree"][i]
        oid += 1
        orders.append(dict(id=f"OD{oid:07d}", customer_id=cid_, sku=sp["sku"], size="Free", price=sp["price"],
                           order_date=D - timedelta(days=9), delivered_date=D - timedelta(days=5), cluster_id=cl,
                           festival_tag="Navratri 2026", serial_no=f"SNSAR{rng.integers(10**7, 10**8)}", is_synthetic=True))
        demo_orders.append(orders[-1]["id"])
    demo_order_set = set(demo_orders)

    # ---------------- returns (first pass: decide who returns, why, when) -----------------
    raw_returns = []
    nav_end_by_name = {f[0]: f[2] for f in NAVRATRIS}
    for order, p in order_meta:
        if order["delivered_date"] is None:
            continue
        cat = p["category"]
        prof = vendor_profile[p["vendor_id"]]
        comps = {}
        base = CATEGORIES[cat][0]
        comps["base"] = base
        if order["size"] in {"XS", "XXL"}:
            comps["fit_extreme"] = 0.05
        if "stitching" in prof:
            comps["stitching"] = prof["stitching"]
        if "size_small" in prof and order["size"] in {"S", "M", "L"}:
            comps["size_small"] = prof["size_small"]
        if "fabric" in prof:
            comps["fabric"] = prof["fabric"]
        if p["sku"] in colour_problem_skus:
            comps["colour"] = 0.05 + prof.get("colour", 0)
        festival_wave = False
        tag = order["festival_tag"]
        if tag in nav_end_by_name and cat in FESTIVE_CATS:
            comps["festive_wave"] = 0.075 * cluster_info[order["cluster_id"]][8]
            festival_wave = True
        if order["customer_id"] in habitual:
            comps["habitual"] = 0.25
        total = min(sum(comps.values()), 0.85)
        if rng.random() >= total:
            continue
        keys = list(comps)
        w = np.array([comps[k] for k in keys]) / sum(comps.values())
        driver = keys[rng.choice(len(keys), p=w)]
        if driver == "base":
            reason = rng.choice(["SIZE_SMALL", "SIZE_LARGE", "CHANGED_MIND", "COLOUR_MISMATCH", "FABRIC_QUALITY", "NOT_AS_DESCRIBED", "DAMAGED_IN_TRANSIT", "LATE_DELIVERY"],
                                p=[0.17, 0.14, 0.29, 0.07, 0.08, 0.10, 0.07, 0.08])
        elif driver == "fit_extreme":
            reason = "SIZE_SMALL" if order["size"] == "XS" else "SIZE_LARGE"
        elif driver == "stitching":
            reason = "STITCHING"
        elif driver == "size_small":
            reason = "SIZE_SMALL"
        elif driver == "fabric":
            reason = "FABRIC_QUALITY"
        elif driver == "colour":
            reason = "COLOUR_MISMATCH"
        elif driver == "festive_wave":
            reason = rng.choice(["CHANGED_MIND", "SIZE_SMALL", "SIZE_LARGE", "NOT_AS_DESCRIBED"], p=[0.62, 0.16, 0.12, 0.10])
        else:  # habitual
            reason = rng.choice(["CHANGED_MIND", "SIZE_LARGE", "NOT_AS_DESCRIBED"], p=[0.6, 0.2, 0.2])
        reason = str(reason)
        if festival_wave and driver == "festive_wave":
            fest_end = nav_end_by_name[tag]
            lag = int(round(rng.triangular(1, 5.5, 10)))
            req = max(fest_end + timedelta(days=lag), order["delivered_date"] + timedelta(days=1))
        else:
            lag = int(round(rng.triangular(1, 3, 10)))
            req = order["delivered_date"] + timedelta(days=lag)
        if req > D or order["id"] in demo_order_set:
            continue  # future returns are not known yet: that is what we forecast
        raw_returns.append(dict(order=order, product=p, reason=reason, request_date=req, festival_wave=festival_wave,
                                habitual=order["customer_id"] in habitual))

    # ---------------- network load → pickup & inspection delays -----------------
    sample_daily = defaultdict(lambda: defaultdict(int))
    for r in raw_returns:
        sample_daily[r["order"]["cluster_id"]][r["request_date"]] += 1
    scale = {}
    for cid, info in cluster_info.items():
        normal_days = [d for d in _daterange(date(2026, 3, 1), date(2026, 8, 31))]
        mean_normal = np.mean([sample_daily[cid].get(d, 0) for d in normal_days]) or 1.0
        scale[cid] = info[6] / mean_normal  # network returns represented by one sample return
    prov_cap = {}
    prov_of = {}
    for pid, name, cl, ppv, cost in PROVIDERS:
        for c, veh in cl:
            prov_cap[c] = veh * ppv
            prov_of[c] = (pid, cost)
    fac_cap = {f[0]: f[6] for f in FACILITIES}

    def network_load(cid, day):
        # 3-day smoothed scaled requests
        s = sum(sample_daily[cid].get(day - timedelta(days=k), 0) for k in range(3)) / 3
        return s * scale[cid]

    returns, reviews = [], []
    rid = 0
    for r in sorted(raw_returns, key=lambda x: x["request_date"]):
        o, p = r["order"], r["product"]
        cid = o["cluster_id"]
        rid += 1
        req = r["request_date"]
        load = network_load(cid, req)
        ratio_p = load / prov_cap[cid]
        pick_delay = 1 + int(math.ceil(max(0.0, ratio_p - 1.0) * 2.5)) + (1 if rng.random() < 0.08 else 0)
        pickup = req + timedelta(days=pick_delay)
        fac = cluster_info[cid][7]
        ratio_f = load / fac_cap[fac]
        received = pickup + timedelta(days=1)
        insp_delay = int(math.ceil(max(0.0, ratio_f - 0.9) * 4)) + (1 if rng.random() < 0.3 else 0)
        inspected = received + timedelta(days=insp_delay)
        reason = r["reason"]
        # grade distribution by reason
        gp = {
            "STITCHING": [0.06, 0.54, 0.40], "FABRIC_QUALITY": [0.2, 0.5, 0.3], "DAMAGED_IN_TRANSIT": [0.05, 0.35, 0.60],
            "COLOUR_MISMATCH": [0.72, 0.23, 0.05], "NOT_AS_DESCRIBED": [0.66, 0.27, 0.07], "LATE_DELIVERY": [0.9, 0.08, 0.02],
        }.get(reason, [0.80, 0.16, 0.04])
        if r["festival_wave"] and reason == "CHANGED_MIND":
            gp = [0.48, 0.44, 0.08]  # worn once for the festival
        grade = str(rng.choice(["A", "B", "C"], p=gp))
        defects = {"A": None, "B": rng.choice(["minor creasing", "loose thread", "missing hook", "light makeup stain", "seam re-stitch needed"]),
                   "C": rng.choice(["torn seam", "embroidery damage", "colour bleed", "large stain", "fabric tear"])}[grade]
        if reason == "STITCHING" and grade != "A":
            defects = rng.choice(["loose stitching at waistband", "seam opening at side panel", "blouse hem unstitched", "dupatta border thread pull"])
        vend_problem = reason in {"STITCHING", "FABRIC_QUALITY"}
        action = {"A": "restock", "B": "refurbish", "C": "return_to_vendor" if vend_problem else "liquidate"}[grade]
        restock = inspected + timedelta(days={"restock": 1, "refurbish": 5, "liquidate": 3, "return_to_vendor": 2}[action])
        resolution = "exchange" if reason in {"SIZE_SMALL", "SIZE_LARGE"} and rng.random() < 0.14 else "refund"
        refund_date = received + timedelta(days=1) if resolution == "refund" else None

        # integrity evidence (captured at pickup)
        anomalous = rng.random() < (0.035 if r["habitual"] else 0.004)
        tag_intact = not (anomalous and rng.random() < 0.75) and rng.random() > 0.01
        serial_ret = o["serial_no"]
        if anomalous and rng.random() < 0.55:
            serial_ret = f"SN{p['sku'][:3]}{rng.integers(10**7, 10**8)}"
        wdelta = float(np.round(rng.normal(0, 1.6) + (rng.uniform(-22, -9) if anomalous and rng.random() < 0.6 else 0), 1))

        stages = [("pickup_scheduled", req), ("in_transit", pickup), ("received", received), ("inspected", inspected), ("recovered", restock)]
        status = "pickup_scheduled"
        for st, dt in stages:
            if dt <= D:
                status = st
        price = p["price"]
        recovered_value = None
        if status == "recovered":
            factor = {"restock": 0.92, "refurbish": 0.68, "liquidate": 0.22, "return_to_vendor": 0.55}[action]
            age_pen = max(0.5, 1 - 0.012 * (restock - req).days)
            recovered_value = round(price * factor * age_pen, 2)
        pd_ok = pickup <= D
        ret = dict(
            id=f"RT{rid:07d}", order_id=o["id"], customer_id=o["customer_id"], sku=p["sku"], vendor_id=p["vendor_id"],
            cluster_id=cid, size=o["size"], price=price, request_date=req, reason_category=REASON_CATEGORY[reason],
            reason_text=reason_text(rng, reason, p["category"], o["size"]), verified_reason=reason if status in {"inspected", "recovered"} else None,
            predicted_reason=None, reason_confidence=None, sentiment=None, resolution=resolution,
            exchange_size=None, status=status,
            pickup_date=pickup, pickup_slot=str(rng.choice(["09:00-13:00", "13:00-17:00", "17:00-21:00"])),
            received_date=received if received <= D else None,
            inspected_date=inspected if inspected <= D else None,
            facility_id=fac, provider_id=prov_of[cid][0],
            grade=grade if inspected <= D else None, defects=str(defects) if (defects and inspected <= D) else None,
            recovery_action=action if inspected <= D else None, recovered_value=recovered_value,
            refund_amount=price if (resolution == "refund" and refund_date and refund_date <= D) else None,
            refund_date=refund_date if (refund_date and refund_date <= D) else None,
            restock_date=restock if restock <= D else None,
            tag_intact=tag_intact if pd_ok else None, serial_returned=serial_ret if pd_ok else None,
            weight_delta_pct=wdelta if pd_ok else None, images_count=int(rng.choice([0, 1, 2, 3], p=[0.35, 0.3, 0.25, 0.1])),
            anomaly_score=None, integrity_flag=False, pickup_sla_met=(pick_delay <= 2) if pd_ok else None,
            pickup_cost=prov_of[cid][1] if pd_ok else None, created_via="generator", is_synthetic=True,
            _true_anomaly=anomalous, _serial_expected=o["serial_no"],
        )
        if ret["resolution"] == "exchange":
            ret["exchange_size"] = {"SIZE_SMALL": SIZES[min(SIZES.index(o["size"]) + 1, 5)] if o["size"] in SIZES else None,
                                    "SIZE_LARGE": SIZES[max(SIZES.index(o["size"]) - 1, 0)] if o["size"] in SIZES else None}.get(reason)
        returns.append(ret)
        if rng.random() < 0.33:
            rating, text, topic = review_text(rng, reason, p["category"], returned=True)
            rd = min(req + timedelta(days=int(rng.integers(0, 3))), D)
            reviews.append(dict(sku=p["sku"], customer_id=o["customer_id"], order_id=o["id"], rating=rating, text=text,
                                review_date=rd, sentiment=None, topic=topic, is_synthetic=True))

    returned_orders = {r["order_id"] for r in returns}
    for order, p in order_meta:
        if order["id"] in returned_orders or order["delivered_date"] is None:
            continue
        if rng.random() < 0.045:
            # kept items: mostly positive, but problem vendors still collect complaints from people who kept the item
            prof = vendor_profile[p["vendor_id"]]
            issue = None
            if "stitching" in prof and rng.random() < 0.35:
                issue = "STITCHING"
            elif "size_small" in prof and rng.random() < 0.3:
                issue = "SIZE_SMALL"
            rating, text, topic = review_text(rng, issue, p["category"], returned=False)
            rd = min(order["delivered_date"] + timedelta(days=int(rng.integers(1, 9))), D)
            reviews.append(dict(sku=p["sku"], customer_id=order["customer_id"], order_id=order["id"], rating=rating, text=text,
                                review_date=rd, sentiment=None, topic=topic, is_synthetic=True))

    # ---------------- demo scenario: exactly 14 integrity mismatches in the live window -----------------
    for r in returns:  # all currently open returns start with clean evidence
        if r["status"] in {"in_transit", "received", "inspected"}:
            r["tag_intact"] = True
            r["serial_returned"] = r["_serial_expected"]
            r["weight_delta_pct"] = float(np.round(rng.normal(0, 1.5), 1))
    window = [r for r in returns if r["request_date"] >= D - timedelta(days=8) and r["status"] in {"in_transit", "received"}]
    for r in window:  # clean evidence in the window first
        r["tag_intact"] = True
        r["serial_returned"] = r["_serial_expected"]
        r["weight_delta_pct"] = float(np.round(rng.normal(0, 1.5), 1))
    focus = [r for r in window if r["cluster_id"] in {"PNQ", "AMD", "JAI"}]
    rng.shuffle(focus)
    for i, r in enumerate(focus[:14]):
        kind = i % 3
        if kind in (0, 2):
            r["tag_intact"] = False
        if kind in (1, 2):
            r["serial_returned"] = f"SN{r['sku'][:3]}{rng.integers(10**7, 10**8)}"
        if i % 2 == 0:
            r["weight_delta_pct"] = float(np.round(rng.uniform(-18, -8), 1))

    # demo customer Priya also has an in-progress return on her older kurta order (shows tracking)
    priya_old = next(o for o in orders if o["customer_id"] == "C-DEMO-01" and o["order_date"] == D - timedelta(days=60))
    rid += 1
    returns.append(dict(
        id=f"RT{rid:07d}", order_id=priya_old["id"], customer_id="C-DEMO-01", sku=priya_old["sku"],
        vendor_id=next(p["vendor_id"] for p in products if p["sku"] == priya_old["sku"]), cluster_id="PNQ", size=priya_old["size"],
        price=priya_old["price"], request_date=D - timedelta(days=50), reason_category="Size & fit",
        reason_text="Kurta was too long and loose at the shoulders, ordered M but fits like L.", verified_reason="SIZE_LARGE",
        predicted_reason=None, reason_confidence=None, sentiment=None, resolution="refund", exchange_size=None, status="recovered",
        pickup_date=D - timedelta(days=49), pickup_slot="09:00-13:00", received_date=D - timedelta(days=48), inspected_date=D - timedelta(days=47),
        facility_id="FAC-PUN", provider_id="LP-SWR", grade="A", defects=None, recovery_action="restock",
        recovered_value=round(priya_old["price"] * 0.9, 2), refund_amount=priya_old["price"], refund_date=D - timedelta(days=47),
        restock_date=D - timedelta(days=46), tag_intact=True, serial_returned=priya_old["serial_no"], weight_delta_pct=0.4,
        images_count=1, anomaly_score=None, integrity_flag=False, pickup_sla_met=True, pickup_cost=78.0, created_via="generator",
        is_synthetic=True, _true_anomaly=False, _serial_expected=priya_old["serial_no"],
    ))

    # ---------------- facility daily records (network scale, derived from sample flows) -----------------
    fac_daily = []
    clusters_of_fac = defaultdict(list)
    for c in CLUSTERS:
        clusters_of_fac[c[7]].append(c[0])
    recv_daily = defaultdict(lambda: defaultdict(int))
    for r in returns:
        if r["received_date"]:
            recv_daily[r["facility_id"]][r["received_date"]] += 1
    fac_by_id = {f[0]: f for f in FACILITIES}
    for fid, f in fac_by_id.items():
        backlog = 0
        for day in _daterange(D - timedelta(days=150), D):
            if clusters_of_fac[fid]:
                cl = clusters_of_fac[fid][0]
                inbound = int(round(recv_daily[fid].get(day, 0) * scale[cl]))
            else:  # Nashik: local volume only, normal weeks
                inbound = int(f[8] * (0.9 + 0.2 * rng.random()))
            work = inbound + backlog
            processed = min(work, f[6])
            backlog = work - processed
            fac_daily.append(dict(facility_id=fid, day=day, inbound=inbound, processed=processed, backlog=backlog,
                                  utilisation=round(processed / f[6], 3), is_synthetic=True))

    # ---------------- write -----------------
    for r in returns:
        r.pop("_true_anomaly", None)
        r.pop("_serial_expected", None)
    with session_scope() as db:
        db.execute(insert(m.Vendor), [dict(id=v[0], name=v[1], city=v[2], onboarded=date(2021 + i % 4, 1 + i % 12, 1), specialty=v[3], qc_hold=False, is_synthetic=True) for i, v in enumerate(VENDORS)])
        db.execute(insert(m.Product), products)
        db.execute(insert(m.Facility), [dict(id=f[0], name=f[1], city=f[2], lat=f[3], lon=f[4], kind=f[5], inspection_capacity=f[6], storage_capacity=f[7], normal_load=f[8], handling_cost=f[9], is_synthetic=True) for f in FACILITIES])
        db.execute(insert(m.PinCluster), [dict(id=c[0], city=c[1], state=c[2], pin_prefix=c[3], lat=c[4], lon=c[5], network_daily_returns=c[6], default_facility_id=c[7], is_synthetic=True) for c in CLUSTERS])
        db.execute(insert(m.LogisticsProvider), [dict(id=p[0], name=p[1], clusters=[{"cluster_id": c, "vehicles": v} for c, v in p[2]], vehicles=sum(v for _, v in p[2]), pickups_per_vehicle=p[3], cost_per_pickup=p[4], sla_hours=48, is_synthetic=True) for p in PROVIDERS])
        db.execute(insert(m.Customer), customers)
        for i in range(0, len(orders), 20000):
            db.execute(insert(m.Order), orders[i:i + 20000])
        for i in range(0, len(returns), 10000):
            db.execute(insert(m.Return), returns[i:i + 10000])
        db.execute(insert(m.Review), reviews)
        db.execute(insert(m.FacilityDaily), fac_daily)
        db.execute(insert(m.Festival), [dict(name=f[0], start=f[1], end=f[2], kind=f[3]) for f in FESTIVALS])
        db.execute(insert(m.User), [dict(id=u[0], name=u[1], role=u[2], title=u[3], scope_id=u[4], approval_limit=u[5]) for u in DEMO_USERS]
                   + [dict(id=f"U-{c[0]}", name=c[1], role="customer", title="Customer", scope_id=c[0], approval_limit=0) for c in DEMO_CUSTOMERS])
        db.execute(insert(m.Setting), [
            dict(key="scenario", value={"scenario_date": D.isoformat(), "return_window_days": 10, "network_scale": {k: round(v, 2) for k, v in scale.items()}}),
            dict(key="resale", value={"storage_cost_per_day": 6.0, "refurb_cost_pct": 0.08, "inspection_cost": 45.0,
                                      "grade_factor": {"A": 0.95, "B": 0.72, "C": 0.30}, "markdown_floor": 0.35}),
            dict(key="governance", value={"auto_approve_logistics_limit_inr": 25000, "anomaly_threshold": 0.62}),
            dict(key="llm", value={"provider": "template"}),
            dict(key="fault_injection", value={"agent": None, "failures": 0}),
        ])
        db.add(m.AuditLog(ts=datetime.now(), actor="system", actor_type="system", action="dataset.generated",
                          entity_type="dataset", entity_id=str(SEED), detail={"orders": len(orders), "returns": len(returns), "reviews": len(reviews), "synthetic": True}))
    stats = dict(orders=len(orders), returns=len(returns), reviews=len(reviews), skus=len(products), vendors=len(VENDORS),
                 clusters=len(CLUSTERS), customers=len(customers), facility_days=len(fac_daily))
    if verbose:
        print("Synthetic dataset generated:", stats)
    return stats


if __name__ == "__main__":
    generate()
