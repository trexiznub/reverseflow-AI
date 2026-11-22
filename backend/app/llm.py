"""LLM abstraction layer.

Agents never depend on an LLM to *decide* anything; decisions come from models,
optimisation and rules. The LLM layer only phrases explanations.

Providers
---------
* template (default): deterministic, evidence-grounded text built from the
  structured evidence. No network, no API key.
* openai_compatible: any OpenAI-compatible chat endpoint (LLM_BASE_URL,
  LLM_API_KEY, LLM_MODEL). Used only if configured.
* sap_genai_hub: placeholder adapter for SAP Generative AI Hub (AI Core). Not
  connected in this prototype; it reports itself as "not configured".

If a configured provider fails, the layer falls back to the template and
records the source, so the UI can show where every explanation came from.
"""
from __future__ import annotations

import json
import os
import urllib.request


class TemplateProvider:
    name = "template"

    def explain(self, kind: str, facts: dict) -> str:
        f = facts
        t = {
            "vendor_quality": "{share:.0%} of {vendor}'s returns in the last {window} days were for {reason_label}, against {base:.0%} for other sellers "
                              "({n} returns). A gap this size is very unlikely to be chance (z = {z:.1f}). It is mostly in {top_skus}.",
            "size_chart": "{n} of {total} recent returns of {sku} say it runs small ({share:.0%}, against {base:.0%} for similar items). "
                          "Sizes {sizes} are hit hardest. Suggested fix: make the size chart {delta} inch bigger at the bust and waist.",
            "listing_fix": "{n} returns of {sku} say it looked different from the listing ({reason_label}: {share:.0%}, against {base:.0%} for similar items). "
                           "Suggested fix: re-shoot the photos in daylight and correct the colour name.",
            "exchange_first": "About {n} returns for {scope} are expected to be about size. Offering a different size before a refund keeps the sale; "
                              "{uptake:.0%} of customers took a size swap when offered in the past.",
            "reroute": "{city} expects about {peak:,} returns a day at the peak, but can only inspect {cap:,} a day. Sending {share:.0%} "
                       "to {alt} uses its {spare:,} a day of spare room, for about ₹{cost:,.0f} in extra transport.",
            "extra_pickup": "{city}'s vans can collect {cap:,} returns a day, but about {peak:,} a day are expected at the peak. {veh} more vans close the gap.",
            "integrity": "Return {rid} needs a closer look at the warehouse: {evidence}. This is not proof of wrongdoing. "
                         "The refund is not held up; a person decides after the item is checked.",
            "refurbish": "{n} items that need a small repair can be fixed and resold for about ₹{value:,.0f}, "
                         "for about ₹{cost:,.0f} in repair costs.",
            "restock": "{n} festive items that are probably like new are worth about ₹{value:,.0f}, and lose about ₹{decay:,.0f} a day while they wait. "
                       "They move to the front of the inspection queue so they are back on sale within 3 days.",
            "customer_return": "{status_text} for your {product}. {next_step}",
        }.get(kind)
        if not t:
            return json.dumps(f)[:400]
        try:
            return t.format(**f)
        except (KeyError, ValueError, IndexError):
            return json.dumps(f)[:400]


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(self):
        self.base = os.getenv("LLM_BASE_URL")
        self.key = os.getenv("LLM_API_KEY")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    @property
    def configured(self) -> bool:
        return bool(self.base and self.key)

    def explain(self, kind: str, facts: dict) -> str:
        body = json.dumps({
            "model": self.model, "temperature": 0.2, "max_tokens": 180,
            "messages": [
                {"role": "system", "content": "You write one short, factual operations explanation for a returns manager. Use only the facts given. Never accuse customers."},
                {"role": "user", "content": f"Recommendation type: {kind}. Facts: {json.dumps(facts, default=str)}"},
            ],
        }).encode()
        req = urllib.request.Request(self.base.rstrip("/") + "/chat/completions", data=body,
                                     headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"].strip()


class SapGenAiHubProvider:
    """Adapter boundary for SAP Generative AI Hub (SAP AI Core). Not connected."""
    name = "sap_genai_hub"
    configured = False

    def explain(self, kind: str, facts: dict) -> str:  # pragma: no cover
        raise RuntimeError("SAP Generative AI Hub is a proposed integration and is not connected in this prototype")


_template = TemplateProvider()


def provider_status() -> list[dict]:
    oc = OpenAICompatibleProvider()
    return [
        {"id": "template", "label": "Evidence template (offline)", "configured": True, "implemented": True},
        {"id": "openai_compatible", "label": "OpenAI-compatible endpoint", "configured": oc.configured, "implemented": True},
        {"id": "sap_genai_hub", "label": "SAP Generative AI Hub", "configured": False, "implemented": False},
    ]


def explain(kind: str, facts: dict, provider: str = "template") -> tuple[str, str]:
    """Return (text, source)."""
    if provider == "openai_compatible":
        p = OpenAICompatibleProvider()
        if p.configured:
            try:
                return p.explain(kind, facts), "openai_compatible"
            except Exception:  # network / auth: fall back, never break the agent
                pass
    return _template.explain(kind, facts), "template"
