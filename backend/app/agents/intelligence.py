from __future__ import annotations

from ..ml import nlp
from ..services import intelligence as intel
from .base import Agent, AgentContext, AgentResult, alert


class IntelligenceAgent(Agent):
    id = "intelligence"
    name = "Product, Vendor & Customer Intelligence"
    group = "Sensing & scenario"
    purpose = "Classify return reasons and sentiment, detect repeated product and vendor defects, attribute root causes."
    inputs = ["Customer reviews", "Return reasons (free text)", "Product descriptions", "Size charts", "Vendor records", "Inspection findings"]
    models = ["TF-IDF + logistic regression reason classifier", "Sentiment classifier", "Two-proportion z-tests"]

    def run(self, ctx: AgentContext) -> AgentResult:
        db = ctx.db
        nlp.ensure_trained(db)
        scored = nlp.score_all(db, only_missing=True)
        f = intel.findings(db, ctx.scenario_date)
        ranking = intel.vendor_rankings(db, ctx.scenario_date)
        feedback = intel.recurring_feedback(db, ctx.scenario_date)
        alerts = []
        for vf in f["vendor_findings"]:
            alerts.append(alert("high" if vf["z"] >= 8 else "medium", "vendor",
                                f"Quality alert: {vf['reason_label'].lower()} on {len(vf['top_skus'])} SKUs",
                                f"{vf['returns']} of your {vf['vendor_returns']} returns in the last {f['window_days']} days cite "
                                f"{vf['reason_label'].lower()} ({vf['share']:.0%} vs {vf['network_share']:.0%} marketplace average).",
                                "vendor", vf["vendor_id"], scope_id=vf["vendor_id"]))
        ev = (ctx.event or {})
        new_return = None
        if ev.get("return_id"):
            from .. import models as m
            r = db.get(m.Return, ev["return_id"])
            if r:
                new_return = {"return_id": r.id, "predicted_reason": r.predicted_reason, "confidence": r.reason_confidence,
                              "matches_open_finding": any(v["vendor_id"] == r.vendor_id and v["reason"] == r.predicted_reason for v in f["vendor_findings"])}
        out = {
            "newly_classified_returns": scored, "classifier": nlp.metrics().get("reason_classifier", {}).get("accuracy"),
            "vendor_findings": [{k: v[k] for k in ("vendor_id", "vendor_name", "reason", "reason_label", "returns", "vendor_returns", "share", "network_share", "z", "top_skus", "sizes")}
                                for v in f["vendor_findings"]],
            "sku_findings": len(f["sku_findings"]), "top_sku_findings": f["sku_findings"][:5],
            "worst_vendors": [{k: v[k] for k in ("vendor_id", "name", "quality_score", "return_rate", "defect_rate")} for v in ranking[:3]],
            "recurring_feedback": feedback[:3], "event_return": new_return,
        }
        ctx.send(self.id, "prevention", "quality_findings", {"vendor_findings": len(f["vendor_findings"]), "sku_findings": len(f["sku_findings"])})
        ctx.send(self.id, "recovery", "defect_skus", {"skus": sorted({s["sku"] for v in f["vendor_findings"] for s in v["top_skus"]})})
        ctx.send(self.id, "governance", "customer_context", {"note": "customer return history available for integrity scoring"})
        ctx.state["_findings"] = f
        return AgentResult(outputs=out, alerts=alerts)
