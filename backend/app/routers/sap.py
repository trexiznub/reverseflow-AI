"""SAP connections: what each SAP product does here, whether it is connected,
and the outbox of messages prepared for SAP IBP, TM and Ariba."""
from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import llm
from .. import models as m
from ..db import get_db
from ..rbac import auth_mode, require
from ..sap import btp, destinations, outbox
from ..services import actions
from ..services import settings as st

router = APIRouter()


def _state(connected: bool, built: bool = True) -> str:
    return "connected" if connected else ("ready" if built else "planned")


def services(db: Session) -> list[dict]:
    dialect = db.bind.dialect.name
    counts = outbox.summary(db)
    llm_choice = (st.get(db, "llm", {}) or {}).get("provider", "template")
    genai = llm.SapGenAiHubProvider()
    on_cf = btp.on_cloud_foundry()

    def system(sid: str, product: str, does: str, messages: str) -> dict:
        how = destinations.configured(sid)
        return {"id": sid, "product": product, "group": "Run the business", "does": does,
                "state": _state(bool(how)), "via": how, "messages": counts[sid],
                "today": (f"Connected through {how}. Approved decisions are sent as soon as they are made." if how else
                          f"Built and working: {messages} They wait in the outbox below, because no {product} system is connected."),
                "connect": f"Set SAP_{sid.upper()}_URL (and SAP_{sid.upper()}_TOKEN_URL, _CLIENT_ID, _CLIENT_SECRET), "
                           f"or bind the Destination service and create a destination named {destinations.destination_name(sid)}."}

    return [
        {"id": "bas", "product": "SAP Business Application Studio", "group": "Build and run", "state": "in_use",
         "does": "The development environment. The whole app is developed and run in a BAS dev space.",
         "today": "In use: the backend and website run side by side in the hackathon dev space.", "connect": "Already in use."},
        {"id": "btp", "product": "SAP BTP, Cloud Foundry runtime", "group": "Build and run", "state": "in_use" if on_cf else "ready",
         "does": "Hosts the app on SAP's cloud, next to the SAP services it uses.",
         "today": f"Running on Cloud Foundry as {btp.app_info().get('application_name', 'reverseflow')}." if on_cf else
                  "Ready to deploy: mta.yaml describes the backend, website, sign-in router and services. Run it from BAS with mbt build and cf deploy.",
         "connect": "In BAS: mbt build, then cf deploy mta_archives/reverseflow_1.0.0.mtar"},
        {"id": "xsuaa", "product": "SAP Authorization and Trust Management (XSUAA)", "group": "Build and run",
         "state": _state(auth_mode() == "xsuaa"),
         "does": "Real sign-in with SAP ID or your company's identity provider. Roles and approval rights come from role collections.",
         "today": "Connected: every request needs an SAP sign-in, and roles come from the token." if auth_mode() == "xsuaa" else
                  "Built and working in code: token checks and role mapping switch on when XSUAA is bound. The demo uses the person switcher instead.",
         "connect": "Bind an xsuaa service created from xs-security.json (the mta.yaml does this)."},
        {"id": "hana", "product": "SAP HANA Cloud", "group": "Data", "state": _state(dialect == "hana"),
         "does": "One fast database for orders, returns, stock and forecasts, so the agents and SAP Analytics Cloud read the same data.",
         "today": "Connected: all app data is stored in SAP HANA Cloud." if dialect == "hana" else
                  f"Ready: the schema is portable and checked against the HANA dialect. The demo stores data in {dialect}.",
         "connect": "Bind a HANA Cloud schema (service hana, plan schema), or set DATABASE_URL=hana://USER:PASSWORD@HOST:443?encrypt=true"},
        {"id": "genai", "product": "SAP Generative AI Hub (SAP AI Core)", "group": "Data",
         "state": "in_use" if genai.configured and llm_choice == "sap_genai_hub" else _state(genai.configured),
         "does": "Writes the plain-English explanation behind each suggestion. It never makes the decision; the models and rules do.",
         "today": ("In use for explanations." if genai.configured and llm_choice == "sap_genai_hub" else
                   "Connected. Choose it under Settings to use it for explanations." if genai.configured else
                   "Built: the AI Core client is in place. Explanations use offline templates until a model deployment is connected."),
         "connect": "Bind the aicore service and set AICORE_DEPLOYMENT_ID to a chat-model deployment, then pick SAP Generative AI Hub in Settings."},
        system("ibp", "SAP Integrated Business Planning", "Planners see returning stock as incoming supply, so they buy and allocate less new stock.",
               "after every agent run the return forecast is prepared as IBP planning data, and recovered stock as extra supply."),
        system("tm", "SAP Transportation Management", "Approved extra vans and warehouse changes become real transport bookings with the carrier.",
               "each approved van booking or warehouse change becomes a transportation request."),
        system("ariba", "SAP Ariba / SAP Business Network", "Quality holds and fix requests reach the seller in the supplier network they already use.",
               "each approved quality hold, size-chart or listing fix becomes a quality notification for the seller."),
        {"id": "destination", "product": "SAP BTP Destination service", "group": "Connect", "state": _state(bool(btp.binding("destination"))),
         "does": "Keeps the addresses and sign-in details of IBP, TM and Ariba outside the code, including on-premise systems through Cloud Connector.",
         "today": "Bound: SAP systems are looked up by destination name." if btp.binding("destination") else
                  "Built: destination lookup is in the code and switches on when the service is bound.",
         "connect": "Bind a destination service (plan lite) and create destinations reverseflow-ibp, reverseflow-tm and reverseflow-ariba."},
        {"id": "integration_suite", "product": "SAP Integration Suite", "group": "Connect", "state": "planned",
         "does": "Maps our messages to each system's exact API (IBP planning data, TM freight units, Ariba cXML).",
         "today": "Planned. Our messages are plain JSON documents; an Integration Suite flow would translate them for each system.",
         "connect": "Point SAP_IBP_URL, SAP_TM_URL and SAP_ARIBA_URL (or the destinations) at the integration flows."},
        {"id": "sac", "product": "SAP Analytics Cloud", "group": "Report", "state": "ready",
         "does": "Management dashboards and planning for leadership.",
         "today": "Working: four ready-to-import datasets (returns, forecast, seller scorecard, resale list) under Reports.",
         "connect": "Import the CSV files in SAC, or build a live model on the HANA Cloud tables."},
    ]


@router.get("/sap/status")
def sap_status(db: Session = Depends(get_db), _: m.User = Depends(require("internal"))):
    items = services(db)
    return {"auth_mode": auth_mode(), "on_cloud_foundry": btp.on_cloud_foundry(), "database": db.bind.dialect.name,
            "services": items, "outbox": outbox.summary(db),
            "counts": {s: sum(1 for i in items if i["state"] == s) for s in ("in_use", "connected", "ready", "planned")}}


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
