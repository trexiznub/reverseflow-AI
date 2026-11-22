from __future__ import annotations

from datetime import timedelta

import pandas as pd
from sqlalchemy import text

from .. import llm
from ..services import intelligence as intel
from .base import Agent, AgentContext, AgentResult, rec

REVERSE_COST = 78 + 45 + 6 * 4  # pickup + inspection + ~4 days storage (INR), illustrative


class PreventionAgent(Agent):
    id = "prevention"
    name = "Prevention & Policy"
    group = "Sensing & scenario"
    purpose = "Prevent avoidable returns before dispatch: listing and size-chart fixes, pre-dispatch QC, exchange-first, policy exceptions."
    inputs = ["Intelligence findings", "Product listings and size charts", "Order pipeline", "Return policy"]
    depends_on = ["intelligence"]
    models = ["Rules on statistical findings", "Avoidable-return impact estimate"]

    def run(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        f = ctx.state.get("_findings") or intel.findings(db, ctx.scenario_date)
        provider = (ctx.settings.get("llm") or {}).get("provider", "template")
        since = ctx.scenario_date - timedelta(days=30)
        orders30 = pd.read_sql(text("""SELECT p.vendor_id, o.sku, COUNT(*) n, AVG(o.price) price FROM orders o JOIN products p ON p.sku=o.sku
                                        WHERE o.order_date >= :s GROUP BY 1, 2"""), db.bind, params={"s": since})
        recs = []
        high_risk = []
        for vf in f["vendor_findings"]:
            vid, reason = vf["vendor_id"], vf["reason"]
            v_orders = orders30[orders30.vendor_id == vid]
            monthly_orders = int(v_orders.n.sum())
            avg_price = float(v_orders.price.mean()) if len(v_orders) else 4000
            excess_rate = max(0.0, (vf["share"] - vf["network_share"])) * (vf["vendor_returns"] / max(monthly_orders * 3, 1))
            avoidable = int(round(monthly_orders * excess_rate))
            impact = avoidable * (REVERSE_COST + 0.15 * avg_price)
            top = ", ".join(s["name"] for s in vf["top_skus"][:2])
            facts = dict(vendor=vf["vendor_name"], share=vf["share"], reason_label=vf["reason_label"].lower(), window=f["window_days"],
                         base=vf["network_share"], n=vf["returns"], z=vf["z"], top_skus=top)
            txt, src = llm.explain("vendor_quality", facts, provider)
            ev = {"finding": vf, "monthly_orders": monthly_orders, "avoidable_returns_per_month": avoidable,
                  "method": "excess reason share over network x vendor return volume, applied to the last 30 days of orders"}
            if reason in ("STITCHING", "FABRIC_QUALITY"):
                recs.append(rec("pre_dispatch_qc", f"Check {vf['vendor_name']} items before they ship ({vf['reason_label'].lower()})", txt, ev,
                                "vendor", vid, impact=impact, cost=monthly_orders * 18, confidence=min(0.95, 0.5 + vf["z"] / 40),
                                priority="high", source=src))
                if vf["share"] >= 0.3 and vf["z"] >= 10:
                    recs.append(rec("vendor_qc_hold", f"Pause new {vf['vendor_name']} shipments until their stitching passes a check",
                                    txt + " A pause stops new shipments of the affected products until the seller passes a quality check. It needs the seller quality manager's approval.",
                                    ev, "vendor", vid, impact=impact * 1.3, cost=monthly_orders * avg_price * 0.02,
                                    confidence=min(0.9, 0.45 + vf["z"] / 40), priority="high", source=src))
            elif reason in ("SIZE_SMALL", "SIZE_LARGE"):
                sizes = sorted(vf["sizes"], key=lambda s: -vf["sizes"][s])[:3]
                skus = [s["sku"] for s in vf["top_skus"]]
                delta = 1 if reason == "SIZE_SMALL" else -1
                facts2 = dict(n=vf["returns"], total=vf["vendor_returns"], sku=f"{len(skus)} {vf['vendor_name']} products", share=vf["share"],
                              base=vf["network_share"], sizes="/".join(sizes), delta=abs(delta))
                t2, src2 = llm.explain("size_chart", facts2, provider)
                recs.append(rec("size_chart_update", f"Fix the size charts for {len(skus)} {vf['vendor_name']} products ({vf['reason_label'].lower()})",
                                t2, dict(ev, skus=skus, delta_inches=delta, affected_sizes=sizes), "vendor", vid, impact=impact, cost=0,
                                confidence=min(0.95, 0.5 + vf["z"] / 40), priority="high", source=src2))
                uptake = self._exchange_uptake(db)
                t3, src3 = llm.explain("exchange_first", dict(n=vf["returns"], scope=f"{vf['vendor_name']} lehengas", uptake=uptake), provider)
                recs.append(rec("exchange_first", f"Offer a size swap before a refund on {vf['vendor_name']} products", t3,
                                dict(ev, skus=skus, historical_exchange_uptake=uptake), "vendor", vid, impact=impact * 0.4,
                                cost=0, confidence=0.7, priority="medium", source=src3))
            elif reason in ("COLOUR_MISMATCH", "NOT_AS_DESCRIBED"):
                skus = [s["sku"] for s in vf["top_skus"]]
                t4, src4 = llm.explain("listing_fix", dict(n=vf["returns"], sku=f"{vf['vendor_name']} products", reason_label=vf["reason_label"].lower(),
                                                           share=vf["share"], base=vf["network_share"]), provider)
                recs.append(rec("listing_fix", f"Fix the photos and description for {len(skus)} {vf['vendor_name']} products ({vf['reason_label'].lower()})", t4,
                                dict(ev, skus=skus), "vendor", vid, impact=impact, cost=2500 * len(skus), confidence=0.75, source=src4))
            for s in vf["top_skus"]:
                high_risk.append({"sku": s["sku"], "name": s["name"], "vendor_id": vid, "reason": vf["reason_label"], "returns": s["returns"]})
        for sf in f["sku_findings"][:8]:
            if any(h["sku"] == sf["sku"] for h in high_risk):
                continue
            high_risk.append({"sku": sf["sku"], "name": sf["name"], "vendor_id": sf["vendor_id"], "reason": sf["reason_label"], "returns": sf["returns"]})
        out = {"recommendations": len(recs), "high_risk_skus": high_risk[:12],
               "kinds": sorted({r["kind"] for r in recs}),
               "estimated_avoidable_returns_per_month": int(sum(r["evidence"].get("avoidable_returns_per_month", 0) for r in recs if r["kind"] in ("pre_dispatch_qc", "size_chart_update", "listing_fix"))),
               "guardrail": "No automatic vendor suspension or customer penalty; consequential actions are routed for approval."}
        ctx.send(self.id, "logistics", "exchange_first_proposed", {"vendors": [r["entity_id"] for r in recs if r["kind"] == "exchange_first"]})
        ctx.send(self.id, "governance", "policy_actions", {"count": len(recs)})
        ctx.state["_qc_vendors"] = [r["entity_id"] for r in recs if r["kind"] in ("vendor_qc_hold", "pre_dispatch_qc")]
        return AgentResult(outputs=out, recommendations=recs)

    @staticmethod
    def _exchange_uptake(db) -> float:
        r = db.execute(text("""SELECT AVG(CASE WHEN resolution='exchange' THEN 1.0 ELSE 0 END) FROM returns
                               WHERE verified_reason IN ('SIZE_SMALL','SIZE_LARGE')""")).scalar()
        return round(float(r or 0), 3)
