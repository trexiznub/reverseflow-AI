"""SAP connections: what each SAP service does here, its tested state, the
S/4HANA and AI Core readers, and the outbox of messages for IBP, TM and Ariba."""
from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..db import get_db, session_scope
from ..rbac import auth_mode, require, require_admin
from ..sap import aicore, btp, destinations, health, outbox, s4hana
from ..services import actions
from ..services import settings as st

router = APIRouter()

GROUPS_ORDER = ["Platform", "Data and AI", "Business systems", "Analytics and access"]
STATES = ("connected", "configured", "not_configured", "no_entitlement", "failed")


def services(db: Session) -> list[dict]:
    """Every SAP service the app can use, with its real state (see sap/health.py)."""
    state = health.current(db)
    counts = outbox.summary(db)
    llm_choice = (st.get(db, "llm", {}) or {}).get("provider", "template")
    s4_sandbox = not s4hana.configured() and s4hana.sandbox_enabled()

    def svc(sid, product, group, does, connect, needs, **extra):
        return {"id": sid, "product": product, "group": group, "does": does, "connect": connect, "needs": needs,
                **state.get(sid, {"state": "not_configured", "detail": None, "tested_at": None}), **extra}

    def system(sid, product, does, built):
        return svc(sid, product, "Business systems", does,
                   f"Set SAP_{sid.upper()}_URL (with SAP_{sid.upper()}_TOKEN_URL, _CLIENT_ID, _CLIENT_SECRET, or _USER/_PASSWORD), "
                   f"or bind the Destination service and create a destination named {destinations.destination_name(sid)}.",
                   f"A {product} tenant and an inbound API (usually through SAP Integration Suite).",
                   messages=counts[sid], built=built)

    return [
        svc("btp", "SAP BTP, Cloud Foundry runtime", "Platform",
            "Hosts the backend, the CAP business service and the website next to the SAP services they use.",
            "In SAP Business Application Studio: mbt build, then cf deploy mta_archives/reverseflow_1.0.0.mtar",
            "A BTP subaccount with Cloud Foundry enabled and a space (free tier is enough)."),
        svc("xsuaa", "SAP Authorization and Trust Management (XSUAA)", "Platform",
            "Sign-in with SAP ID or your company's identity provider. Roles and approval rights come from role collections.",
            "Bind an xsuaa service created from xs-security.json (mta.yaml does this), then assign the ReverseFlow role collections.",
            "Authorization and Trust Management (application plan), included in BTP."),
        svc("destination", "SAP BTP Destination service", "Platform",
            "Keeps addresses and sign-in details of S/4HANA, IBP, TM and Ariba outside the code, including on-premise systems through Cloud Connector.",
            "Bind a destination service (plan lite) and create destinations reverseflow-s4, reverseflow-ibp, reverseflow-tm, reverseflow-ariba.",
            "Destination service (lite plan), included in BTP."),
        svc("cap", "SAP Cloud Application Programming Model (CAP)", "Platform",
            "The business service: OData V4 access to orders, returns, sellers, stock, corrective actions, approvals and the audit log, "
            "with SAP roles. AI work stays in this backend; CAP calls it for decisions and seller scores.",
            "Run sap-business-service (npm start) and set CAP_URL to its address. On BTP, mta.yaml deploys it and sets CAP_URL.",
            "Nothing extra: runs on Cloud Foundry next to the backend."),
        svc("hana", "SAP HANA Cloud", "Data and AI",
            "One database for orders, returns, stock and forecasts, shared by this backend, the CAP service and SAP Analytics Cloud.",
            "Bind a HANA Cloud schema (service hana, plan schema), or set DATABASE_URL=hana://USER:PASSWORD@HOST:443?encrypt=true. "
            "Copy the demo data with: python -m app.tools.migrate_to_hana",
            "A HANA Cloud instance (free tier) in the subaccount, and the hana schema plan entitled.",
            database=db.bind.dialect.name),
        svc("genai", "SAP Generative AI Hub", "Data and AI",
            "Writes the plain-English explanations: return comments, seller quality summaries, root causes and corrective actions. "
            "It never decides or approves; forecasts, scores and money figures stay with the models and rules.",
            "Bind the aicore service, set AICORE_DEPLOYMENT_ID to a running chat-model deployment, then pick SAP Generative AI Hub in Settings.",
            "SAP AI Core (extended plan for Generative AI Hub models) and a running model deployment.",
            selected=llm_choice == "sap_genai_hub"),
        svc("aicore", "SAP AI Core", "Data and AI",
            "Model lifecycle: scenarios, configurations, deployments and executions for the AI models the app uses.",
            "Bind the aicore service (or set AICORE_AUTH_URL, AICORE_CLIENT_ID, AICORE_CLIENT_SECRET, AICORE_BASE_URL).",
            "SAP AI Core entitlement and a resource group."),
        svc("launchpad", "SAP AI Launchpad", "Data and AI",
            "SAP's screens for managing AI Core: deployments, versions, runs and the Generative AI Hub prompt tools.",
            "Subscribe to AI Launchpad, connect it to the AI Core instance, and set AI_LAUNCHPAD_URL so the link shows here.",
            "SAP AI Launchpad subscription (standard plan)."),
        svc("s4", "SAP S/4HANA", "Business systems",
            "Source of sales orders, customer returns, products, suppliers, stock by plant and deliveries (read-only, SAP's published OData APIs).",
            "Set SAP_S4_URL with SAP_S4_API_KEY (SAP Business Accelerator Hub sandbox) or a communication user or OAuth client, "
            "or create destination reverseflow-s4.",
            "An S/4HANA system with these APIs enabled, or a free SAP Business Accelerator Hub API key for its sandbox.",
            sandbox=s4_sandbox),
        system("ibp", "SAP Integrated Business Planning", "Planners see returning stock as incoming supply, so they buy and allocate less new stock.",
               "After every agent run the return forecast is prepared as IBP planning data, and recovered stock as extra supply."),
        system("tm", "SAP Transportation Management", "Approved extra vans and warehouse changes become transport bookings with the carrier.",
               "Each approved van booking or warehouse change becomes a transportation request."),
        system("ariba", "SAP Ariba / SAP Business Network", "Quality holds and fix requests reach the seller in the supplier network they already use.",
               "Each approved quality hold, size-chart or listing fix becomes a quality notification for the seller."),
        {"id": "integration_suite", "product": "SAP Integration Suite", "group": "Business systems", "state": "not_configured", "detail": None,
         "tested_at": None, "does": "Maps our JSON messages to each system's exact API (IBP planning data, TM freight units, Ariba cXML).",
         "connect": "Build one integration flow per system, then point SAP_IBP_URL, SAP_TM_URL and SAP_ARIBA_URL at them.",
         "needs": "SAP Integration Suite entitlement. The flows are not part of this project."},
        svc("sac", "SAP Analytics Cloud", "Analytics and access",
            "Executive dashboards: returns, seller performance, reverse logistics and inventory recovery.",
            "Live: create a live connection to the HANA Cloud tables. Import: load the datasets under Reports. "
            "To test from here set SAC_URL, SAC_TOKEN_URL, SAC_CLIENT_ID, SAC_CLIENT_SECRET.",
            "An SAP Analytics Cloud tenant (trial or licensed) and an OAuth client in it."),
        svc("workzone", "SAP Build Work Zone", "Analytics and access",
            "Puts ReverseFlow on the company launchpad next to other SAP apps, with SAP sign-in.",
            "Add the app (the approuter URL) in the Work Zone Content Manager, add it to a group and role, then set WORKZONE_SITE_URL.",
            "SAP Build Work Zone, standard edition subscription."),
    ]


@router.get("/sap/status")
def sap_status(db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    items = services(db)
    return {"auth_mode": auth_mode(), "on_cloud_foundry": btp.on_cloud_foundry(), "database": db.bind.dialect.name,
            "services": items, "outbox": outbox.summary(db), "groups": GROUPS_ORDER,
            "counts": {s: sum(1 for i in items if i["state"] == s) for s in STATES},
            "links": {"launchpad": os.getenv("AI_LAUNCHPAD_URL"), "workzone": os.getenv("WORKZONE_SITE_URL"), "cap": os.getenv("CAP_URL")}}


@router.post("/sap/status/test")
def sap_test(db: Session = Depends(get_db), user: m.User = Depends(require_admin)):
    """Run a real connection test against every configured SAP service."""
    health.run_tests(session_scope)
    out = sap_status(db, user)
    actions.audit(db, user.name, "user", "sap.test_connections", "sap", "*", {s["id"]: s["state"] for s in out["services"]})
    db.commit()
    return out


@router.get("/sap/s4")
def s4_entities(_: m.User = Depends(require("internal"))):
    return {"configured": s4hana.configured(), "sandbox": s4hana.sandbox_enabled(),
            "entities": [{"id": k, "title": v["label"], "api": s4hana.path(k)} for k, v in s4hana.ENTITIES.items()]}


@router.get("/sap/s4/{entity}")
def s4_read(entity: str, top: int = 20, skip: int = 0, db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    if entity not in s4hana.ENTITIES:
        raise HTTPException(404, f"entity must be one of {list(s4hana.ENTITIES)}")
    return {**s4hana.fetch(db, entity, top, skip), "title": s4hana.ENTITIES[entity]["label"]}


@router.get("/sap/aicore")
def aicore_overview(_: m.User = Depends(require("internal"))):
    return aicore.overview()


@router.get("/sap/outbox")
def sap_outbox(system: str | None = None, limit: int = 100, db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    q = select(m.SapMessage).order_by(m.SapMessage.created_at.desc()).limit(min(limit, 500))
    if system:
        q = q.where(m.SapMessage.system == system)
    return [outbox.as_dict(x) for x in db.scalars(q).all()]


@router.get("/sap/outbox/{msg_id}")
def sap_message(msg_id: str, db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    msg = db.get(m.SapMessage, msg_id)
    if not msg:
        raise HTTPException(404, "No such message")
    return outbox.as_dict(msg, full=True)


@router.post("/sap/outbox/{msg_id}/send")
def sap_send(msg_id: str, db: Session = Depends(get_db), user: m.User = Depends(require("ops_manager"))):
    msg = db.get(m.SapMessage, msg_id)
    if not msg:
        raise HTTPException(404, "No such message")
    if msg.status == "sent":
        raise HTTPException(409, "Already sent")
    outbox.deliver(db, msg)
    actions.audit(db, user.name, "user", "sap.send", "sap_message", msg.id, {"status": msg.status, "system": msg.system})
    db.commit()
    return outbox.as_dict(msg)


@router.post("/sap/outbox/send-waiting")
def sap_send_waiting(db: Session = Depends(get_db), user: m.User = Depends(require("ops_manager"))):
    msgs = db.scalars(select(m.SapMessage).where(m.SapMessage.status.in_(["waiting", "failed"]))).all()
    for msg in msgs:
        outbox.deliver(db, msg)
    result = {s: sum(1 for x in msgs if x.status == s) for s in ("sent", "waiting", "failed")}
    actions.audit(db, user.name, "user", "sap.send_waiting", "sap_message", "*", result)
    db.commit()
    return result


@router.post("/sap/ibp/forecast")
def sap_publish_forecast(db: Session = Depends(get_db), user: m.User = Depends(require("ops_manager", "vendor_quality_manager", "warehouse_manager"))):
    msg = outbox.publish_forecast(db, user.name)
    if not msg:
        raise HTTPException(503, "No forecast yet")
    actions.audit(db, user.name, "user", "sap.publish_forecast", "sap_message", msg.id, {"status": msg.status})
    db.commit()
    return outbox.as_dict(msg)


# A stand-in receiver for trying the connection end to end without an SAP
# tenant: point SAP_TM_URL (etc.) at http://localhost:8040/api/sap/sandbox/tm.
# Switched off unless REVERSEFLOW_SAP_SANDBOX=1. It stores nothing.
@router.post("/sap/sandbox/{system}")
async def sap_sandbox(system: str, request: Request):
    if os.getenv("REVERSEFLOW_SAP_SANDBOX") != "1":
        raise HTTPException(404, "Not found")
    body = await request.json()
    return {"accepted": True, "system": system, "messageId": body.get("messageId"), "receivedAt": datetime.now().isoformat(timespec="seconds"),
            "note": "Test receiver, not an SAP system."}


# The same S/4HANA sandbox over HTTP, at SAP's OData paths, so the live code path
# can be tried end to end: SAP_S4_URL=http://localhost:8040/api/sap/s4-sandbox
# Off unless REVERSEFLOW_SAP_SANDBOX=1. Synthetic data only.
@router.get("/sap/s4-sandbox/sap/opu/odata/sap/{service}/{entity_set}")
def s4_sandbox(service: str, entity_set: str, request: Request, db: Session = Depends(get_db)):
    if os.getenv("REVERSEFLOW_SAP_SANDBOX") != "1":
        raise HTTPException(404, "Not found")
    match = next((k for k, v in s4hana.ENTITIES.items() if v["service"] == service and v["set"] == entity_set), None)
    if not match:
        raise HTTPException(404, "Unknown service or entity set")
    top = int(request.query_params.get("$top", 20))
    skip = int(request.query_params.get("$skip", 0))
    return {"d": {"results": s4hana.sandbox_records(db, match, min(top, 200), skip)}, "__sandbox": s4hana.SANDBOX_LABEL}
