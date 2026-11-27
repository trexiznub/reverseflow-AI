"""End-to-end API tests over the demo dataset.

Run from backend/:  .venv/bin/pytest -q
Uses a separate SQLite file so the demo database is untouched.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

TEST_DB = Path(__file__).resolve().parent / "test_reverseflow.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
# Exercise the full generate-and-train path here; the snapshot path has its own test.
os.environ["REVERSEFLOW_NO_SNAPSHOT"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import orchestrator  # noqa: E402
from app.main import app  # noqa: E402

OPS = {"X-User-Id": "U-RAHUL"}
CUST = {"X-User-Id": "U-C-DEMO-01"}
VQM = {"X-User-Id": "U-KAVYA"}
NEHA = {"X-User-Id": "U-NEHA"}
VENDOR = {"X-User-Id": "U-VEN-V03"}
TPL = {"X-User-Id": "U-3PL-SWR"}
WH = {"X-User-Id": "U-WH-PUN"}


@pytest.fixture(scope="session")
def client():
    for p in (TEST_DB, Path(str(TEST_DB) + "-wal"), Path(str(TEST_DB) + "-shm")):
        p.unlink(missing_ok=True)
    with TestClient(app) as c:
        # Startup prepares the demo in a background thread; wait for it.
        t0 = time.time()
        while not c.get("/api/health").json().get("ready"):
            assert time.time() - t0 < 300, "demo did not become ready"
            time.sleep(0.5)
        yield c


def test_api_waits_for_bootstrap(client):
    """While the demo is being prepared, API calls get a clear 503; health stays up for the host's checks."""
    from app import bootstrap
    bootstrap._ready.clear()
    try:
        r = client.get("/api/meta", headers=OPS)
        assert r.status_code == 503 and r.json()["detail"] == "The demo is getting ready"
        assert client.get("/api/health").status_code == 200
    finally:
        bootstrap._ready.set()


def wait_run(client, run_id, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/api/orchestrator/runs/{run_id}", headers=OPS).json()
        if r["status"] in ("completed", "partial", "failed"):
            return r
        time.sleep(0.5)
    raise AssertionError("run did not finish")


def test_health_and_dataset(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["ready"]
    meta = client.get("/api/meta", headers=OPS).json()
    assert meta["synthetic"] is True and meta["user"]["role"] == "ops_manager"


def test_forecast_metrics_are_computed(client):
    fc = client.get("/api/forecast", headers=OPS).json()
    ev = fc["evaluations"][0]
    assert ev["rows_test"] > 100
    assert 0 < ev["daily_cluster"]["ml"]["wape"] < 1
    # the ML model must beat the seasonal-naive baseline in the surge window
    assert ev["surge_window"]["ml"]["wape"] < ev["surge_window"]["baseline"]["wape"]
    west = {c["cluster_id"]: c for c in fc["clusters"]}
    assert west["PNQ"]["risk"] == "high" and len(west["PNQ"]["forecast"]) == 7


def test_six_agents_ran(client):
    runs = client.get("/api/orchestrator/runs", headers=OPS).json()
    full = next(r for r in runs if r["trigger"] == "full_cycle")
    d = client.get(f"/api/orchestrator/runs/{full['id']}", headers=OPS).json()
    assert {a["agent"] for a in d["agents"]} == {"prediction", "intelligence", "prevention", "logistics", "recovery", "governance"}
    assert all(a["status"] == "completed" for a in d["agents"])
    assert d["messages"] and d["conflicts"]


def test_intelligence_finds_problem_vendors(client):
    s = client.get("/api/intelligence/summary", headers=OPS).json()
    found = {(v["vendor_id"], v["reason"]) for v in s["vendor_findings"]}
    assert ("V03", "STITCHING") in found and ("V07", "SIZE_SMALL") in found
    g = client.get("/api/intelligence/graph", headers=OPS).json()
    types = {n["type"] for n in g["nodes"]}
    assert {"customer", "return", "sku", "size", "vendor", "defect", "intervention"} <= types


def test_integrity_flags_and_no_auto_rejection(client):
    c = client.get("/api/integrity/cases", headers=OPS).json()
    hard = [x for x in c["cases"] if x["hard_evidence"]]
    assert len(hard) == 14
    assert all(x["recommendation"]["status"] in ("pending", "approved", "rejected", "escalated") for x in hard)
    assert all(x["recommendation"]["kind"] == "integrity_inspection" for x in hard)


def test_simulation_engine_still_drives_case_numbers():
    """The Planner page is gone; the simulation engine stays for the business case."""
    from app.simulation import twin
    base = twin.run({"replications": 10}, ["baseline", "C"])
    heavy = twin.run({"replications": 10, "surge_intensity": 1.8}, ["baseline"])
    b, h = base["scenarios"]["baseline"]["kpis"], heavy["scenarios"]["baseline"]["kpis"]
    assert h["peak_pickup_backlog"]["mean"] > b["peak_pickup_backlog"]["mean"]
    assert base["scenarios"]["C"]["kpis"]["value_at_risk"]["mean"] < b["value_at_risk"]["mean"]


def test_planner_removed(client):
    assert client.post("/api/twin/simulate", json={}, headers=OPS).status_code == 404
    assert client.get("/api/twin/defaults", headers=OPS).status_code == 404
    assert "twin" not in client.get("/api/meta", headers=OPS).json()["pages"]


def test_rbac(client):
    assert client.get("/api/overview", headers=CUST).status_code == 403
    assert client.get("/api/customer/me", headers=OPS).status_code == 403
    v = client.get("/api/partners/vendor?vendor_id=V07", headers=VENDOR).json()
    assert v["vendor"]["id"] == "V03"  # vendor scope cannot be overridden
    assert client.get("/api/approvals", headers=VENDOR).status_code == 403


def test_customer_return_flow_updates_shared_state(client):
    me = client.get("/api/customer/me", headers=CUST).json()
    order = next(o for o in me["orders"] if o["eligible"] and o["category"] == "Lehenga")
    opts = client.get(f"/api/customer/orders/{order['id']}/return-options", headers=CUST).json()
    slot = opts["slots"][0]
    r = client.post("/api/customer/returns", headers=CUST, json={
        "order_id": order["id"], "reason_category": "Quality", "reason_text": "Stitching came apart at the waist after one wear",
        "resolution": "refund", "pickup_date": slot["date"], "pickup_slot": slot["slot"]})
    assert r.status_code == 200, r.text
    body = r.json()
    rid = body["return"]["id"]
    run = wait_run(client, body["orchestrator_run_id"])
    assert run["status"] == "completed"
    assert run["event"]["return_id"] == rid
    # duplicate return is refused
    dup = client.post("/api/customer/returns", headers=CUST, json={
        "order_id": order["id"], "reason_category": "Quality", "reason_text": "again", "resolution": "refund",
        "pickup_date": slot["date"], "pickup_slot": slot["slot"]})
    assert dup.status_code == 409
    # image upload
    up = client.post(f"/api/customer/returns/{rid}/images", headers=CUST, files={"file": ("photo.png", b"\x89PNG\r\n\x1a\nfake", "image/png")})
    assert up.status_code == 200
    # 3PL picks up with a serial mismatch -> governance flags for inspection (no rejection)
    tasks = client.get("/api/partners/logistics", headers=TPL).json()["pickup_tasks"]
    assert any(t["return_id"] == rid for t in tasks)
    pk = client.post(f"/api/partners/logistics/pickups/{rid}/complete", headers=TPL, json={"tag_intact": True, "serial_scanned": "SNWRONG0001", "weight_delta_pct": -12})
    assert pk.status_code == 200
    wait_run(client, pk.json()["orchestrator_run_id"])
    ap = client.get("/api/approvals?kind=integrity_inspection", headers=OPS).json()["items"]
    assert any(a["entity_id"] == rid for a in ap)
    # warehouse receives and inspects
    assert client.post(f"/api/partners/warehouse/receive/{rid}", headers=OPS).status_code == 200
    ins = client.post(f"/api/partners/warehouse/inspect/{rid}", headers=OPS, json={"grade": "B", "verified_reason": "STITCHING", "defects": "seam opening"})
    assert ins.status_code == 200
    wait_run(client, ins.json()["orchestrator_run_id"])
    view = client.get(f"/api/customer/returns/{rid}", headers=CUST).json()
    assert view["status"] == "inspected" and view["refund_amount"]
    assert "vendor" not in view["explanation"].lower()


def test_approval_workflow_persists(client):
    items = client.get("/api/approvals?status=pending", headers=OPS).json()["items"]
    hold = next(i for i in items if i["kind"] == "vendor_qc_hold")
    # wrong role
    assert client.post(f"/api/approvals/{hold['id']}/decision", headers=NEHA, json={"action": "approve", "reason": "ok"}).status_code == 403
    # reason required
    assert client.post(f"/api/approvals/{hold['id']}/decision", headers=VQM, json={"action": "approve", "reason": ""}).status_code == 400
    ok = client.post(f"/api/approvals/{hold['id']}/decision", headers=VQM, json={"action": "approve", "reason": "Stitching evidence is conclusive"})
    assert ok.status_code == 200 and ok.json()["new_status"] == "approved"
    after = client.get("/api/approvals?status=approved", headers=OPS).json()["items"]
    rec = next(i for i in after if i["id"] == hold["id"])
    assert rec["decisions"][-1]["user"] == "Kavya Iyer" and rec["decisions"][-1]["previous_status"] == "pending"
    vend = client.get("/api/partners/vendor", headers=VENDOR).json()
    assert vend["vendor"]["qc_hold"] is True
    audit = client.get("/api/audit", headers=OPS).json()
    assert any(a["action"] == "recommendation.approve" for a in audit)


def test_sap_outbox_from_approval_and_forecast(client):
    # the approved QC hold above became an Ariba quality notification, waiting because Ariba isn't connected
    msgs = client.get("/api/sap/outbox?system=ariba", headers=OPS).json()
    note = next(x for x in msgs if x["kind"] == "vendor_qc_hold")
    assert note["status"] == "waiting" and note["created_by"] == "Kavya Iyer"
    full = client.get(f"/api/sap/outbox/{note['id']}", headers=OPS).json()
    qn = full["payload"]["qualityNotification"]
    assert qn["requestedAction"] == "HOLD_SHIPMENTS_UNTIL_QC_PASSED" and qn["supplier"]["id"]
    # every full agent run prepares the forecast for IBP
    ibp = client.get("/api/sap/outbox?system=ibp", headers=OPS).json()
    assert any(x["kind"] == "return_forecast" for x in ibp)
    pub = client.post("/api/sap/ibp/forecast", headers=OPS).json()
    rows = client.get(f"/api/sap/outbox/{pub['id']}", headers=OPS).json()["payload"]["rows"]
    assert rows and {"PRDID", "LOCID", "PERIODID_DAY", "RETURNSFORECAST"} <= set(rows[0])
    # partners and customers can't see the outbox
    assert client.get("/api/sap/outbox", headers=VENDOR).status_code == 403


def test_sap_delivery_when_connected(client, monkeypatch):
    from app.sap import btp
    sent = []
    monkeypatch.setenv("SAP_ARIBA_URL", "https://integration.example/ariba")
    monkeypatch.setattr(btp, "http_json", lambda method, url, body=None, headers=None, timeout=15: (sent.append((url, body)) or (202, {"ok": True})))
    note = next(x for x in client.get("/api/sap/outbox?system=ariba", headers=OPS).json() if x["status"] == "waiting")
    assert client.post(f"/api/sap/outbox/{note['id']}/send", headers=VQM).status_code == 403  # only the ops manager resends
    r = client.post(f"/api/sap/outbox/{note['id']}/send", headers=OPS).json()
    assert r["status"] == "sent" and r["response"]["http_status"] == 202 and r["response"]["via"] == "environment"
    assert sent[0][0] == "https://integration.example/ariba" and sent[0][1]["messageId"] == note["id"]


def test_sap_status_and_case(client):
    st = client.get("/api/sap/status", headers=OPS).json()
    by = {s["id"]: s for s in st["services"]}
    # nothing is set up in tests, so nothing may claim to be connected
    assert by["hana"]["state"] == "not_configured" and by["tm"]["state"] == "not_configured" and by["cap"]["state"] == "not_configured"
    assert st["counts"]["connected"] == 0 and "bas" not in by and by["s4"]["sandbox"] is True
    assert st["auth_mode"] == "demo"
    c = client.get("/api/case", headers=OPS).json()
    assert c["facts"] and c["assumptions"] and c["sources"]
    p = c["demo"]["simulation"]
    assert p["baseline"]["value_lost"] > p["C"]["value_lost"] > 0 and 0 < p["reduction"] < 1
    assert c["demo"]["seller"]["share"] > c["demo"]["seller"]["others_share"]


def test_xsuaa_sign_in(client, monkeypatch):
    """With XSUAA bound, a token is required and its scopes decide the role."""
    import json
    from app import rbac
    monkeypatch.setenv("VCAP_SERVICES", json.dumps({"xsuaa": [{"credentials": {"url": "https://x.authentication.example", "xsappname": "reverseflow!t1", "clientid": "c"}}]}))
    assert client.get("/api/meta").status_code == 401
    monkeypatch.setattr(rbac, "_verify", lambda tok: {"_scopes": {"WarehouseManager"}} if tok == "good" else (_ for _ in ()).throw(ValueError()))
    assert client.get("/api/meta", headers={"Authorization": "Bearer bad"}).status_code == 401
    me = client.get("/api/meta", headers={"Authorization": "Bearer good", "X-User-Id": "U-RAHUL"}).json()
    assert me["user"]["role"] == "warehouse_manager"  # can't switch persona without the ops scope
    assert client.get("/api/sap/status", headers={"Authorization": "Bearer good"}).json()["auth_mode"] == "xsuaa"
    # an operations manager without the Admin scope can no longer switch persona
    monkeypatch.setattr(rbac, "_verify", lambda tok: {"_scopes": {"OpsManager"} if tok == "ops" else {"Admin"}})
    monkeypatch.setenv("REVERSEFLOW_DEMO_SWITCH", "1")
    me = client.get("/api/meta", headers={"Authorization": "Bearer ops", "X-User-Id": "U-NEHA"}).json()
    assert me["user"]["id"] == "U-RAHUL" and me["user"]["is_admin"] is False
    assert client.post("/api/sap/status/test", headers={"Authorization": "Bearer ops"}).status_code == 403
    me = client.get("/api/meta", headers={"Authorization": "Bearer admin", "X-User-Id": "U-NEHA"}).json()
    assert me["user"]["id"] == "U-NEHA"  # admin presenting another persona, only with REVERSEFLOW_DEMO_SWITCH=1
    monkeypatch.delenv("REVERSEFLOW_DEMO_SWITCH")
    me = client.get("/api/meta", headers={"Authorization": "Bearer admin", "X-User-Id": "U-NEHA"}).json()
    assert me["user"]["role"] == "ops_manager" and me["user"]["is_admin"] is True


def test_sap_genai_hub_explanations(monkeypatch):
    from app import llm
    from app.sap import btp
    for k, v in {"AICORE_AUTH_URL": "https://auth.example", "AICORE_CLIENT_ID": "id", "AICORE_CLIENT_SECRET": "s",
                 "AICORE_BASE_URL": "https://api.ai.example", "AICORE_DEPLOYMENT_ID": "d123"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(btp, "client_credentials_token", lambda *a, **k: "tok")
    calls = []
    monkeypatch.setattr(btp, "http_json", lambda m_, url, body=None, headers=None, timeout=15: (calls.append((url, headers)) or
                        (200, {"choices": [{"message": {"content": "Pune needs more vans."}}]})))
    text, src = llm.explain("extra_pickup", {"city": "Pune"}, "sap_genai_hub")
    assert (text, src) == ("Pune needs more vans.", "sap_genai_hub")
    assert "/v2/inference/deployments/d123/chat/completions" in calls[0][0] and calls[0][1]["AI-Resource-Group"] == "default"
    monkeypatch.setattr(btp, "http_json", lambda *a, **k: (500, {}))
    assert llm.explain("extra_pickup", {"city": "Pune", "cap": 1, "peak": 2, "veh": 3}, "sap_genai_hub")[1] == "template"


def test_analytics_and_exports(client):
    k = client.get("/api/analytics/kpis", headers=OPS).json()["kpis"]
    keys = {x["key"] for x in k}
    assert {"forecast_accuracy", "cost_per_return", "pickup_sla", "value_at_risk", "sellable_recovery"} <= keys
    csv = client.get("/api/integrations/sac/returns_fact.csv", headers=OPS)
    assert csv.status_code == 200 and csv.text.startswith("return_id")


def test_fault_injection_retry(client):
    client.put("/api/settings/fault_injection", headers=OPS, json={"value": {"agent": "logistics", "failures": 1}})
    rid = client.post("/api/orchestrator/run", headers=OPS, json={"trigger": "pickup_completed"}).json()["run_id"]
    run = wait_run(client, rid)
    lg = next(a for a in run["agents"] if a["agent"] == "logistics")
    assert lg["status"] == "completed" and lg["attempts"] == 2


def test_snapshot_restore(tmp_path):
    """A fresh server restores the prepared demo and its models instead of rebuilding them."""
    import subprocess
    import sys
    from app import bootstrap
    if not bootstrap.SNAPSHOT_DB.exists():
        pytest.skip("no snapshot built")
    code = (
        "import time; t=time.time()\n"
        "from app import bootstrap\n"
        "bootstrap.ensure_ready()\n"
        "from app.ml import nlp, anomaly\n"
        "from app.db import SessionLocal\n"
        "from app import models as m\n"
        "from sqlalchemy import select, func\n"
        "with SessionLocal() as db:\n"
        "    n = db.scalar(select(func.count(m.Return.id)))\n"
        "assert bootstrap.status()['ready'] and nlp._reason_model is not None and anomaly._model is not None\n"
        "print(n, round(time.time()-t, 1))\n"
    )
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'fresh.db'}"}
    env.pop("REVERSEFLOW_NO_SNAPSHOT", None)
    out = subprocess.run([sys.executable, "-c", code], env=env, cwd=Path(__file__).resolve().parents[1],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    n, secs = out.stdout.split()
    assert int(n) > 15000
    assert float(secs) < 20


def test_s4hana_sandbox_is_labelled(client):
    r = client.get("/api/sap/s4/customer_returns?top=3", headers=OPS).json()
    assert r["source"] == "sandbox" and "Not from an SAP S/4HANA system" in r["label"]
    assert r["api"] == "/sap/opu/odata/sap/API_CUSTOMER_RETURN_SRV/A_CustomerReturn"
    assert len(r["records"]) == 3 and r["records"][0]["CustomerReturn"].startswith("RT")
    for e in ("sales_orders", "products", "suppliers", "stock", "deliveries"):
        assert client.get(f"/api/sap/s4/{e}?top=2", headers=OPS).json()["records"], e
    assert client.get("/api/sap/s4/nope", headers=OPS).status_code == 404
    assert client.get("/api/sap/s4/products", headers=VENDOR).status_code == 403


def test_s4hana_live_path_through_http_sandbox(client, monkeypatch):
    """The live adapter, pointed at the HTTP sandbox, gets the same OData answer."""
    from app.sap import s4hana
    from app.db import SessionLocal
    monkeypatch.setenv("REVERSEFLOW_SAP_SANDBOX", "1")
    monkeypatch.setenv("SAP_S4_URL", "http://s4.test")
    monkeypatch.setenv("SAP_S4_API_KEY", "k")
    seen = {}

    def fake_http(method, url, body=None, headers=None, timeout=15):
        seen["url"], seen["headers"] = url, headers
        path = url.replace("http://s4.test", "/api/sap/s4-sandbox")
        r = client.get(path)
        return r.status_code, r.json()
    monkeypatch.setattr(s4hana.btp, "http_json", fake_http)
    with SessionLocal() as db:
        r = s4hana.fetch(db, "products", top=2)
    assert r["source"] == "s4hana" and r["ok"] and len(r["records"]) == 2
    assert seen["headers"]["APIKey"] == "k" and "API_PRODUCT_SRV/A_Product" in seen["url"]


def test_connection_tests_report_failures_honestly(client, monkeypatch):
    monkeypatch.setenv("CAP_URL", "http://127.0.0.1:9")  # nothing listens here
    before = {s["id"]: s for s in client.get("/api/sap/status", headers=OPS).json()["services"]}
    assert before["cap"]["state"] == "configured"
    assert client.post("/api/sap/status/test", headers=VQM).status_code == 403  # admin only
    after = {s["id"]: s for s in client.post("/api/sap/status/test", headers=OPS).json()["services"]}
    assert after["cap"]["state"] == "failed" and after["cap"]["tested_at"]
    monkeypatch.setenv("CAP_URL", "http://127.0.0.1:10")  # a new setting clears the old result
    again = {s["id"]: s for s in client.get("/api/sap/status", headers=OPS).json()["services"]}
    assert again["cap"]["state"] == "configured"


def test_production_refuses_demo_header(client, monkeypatch):
    monkeypatch.setenv("REVERSEFLOW_ENV", "production")
    assert client.get("/api/meta", headers=OPS).status_code == 401
    monkeypatch.setenv("REVERSEFLOW_ALLOW_DEMO_AUTH", "1")
    assert client.get("/api/meta", headers=OPS).status_code == 200


def test_admin_only_actions(client):
    assert client.get("/api/meta", headers=OPS).json()["user"]["is_admin"] is True
    assert client.get("/api/meta", headers=VQM).json()["user"]["is_admin"] is False
    assert client.post("/api/admin/reset", headers=VQM).status_code == 403


def test_ai_summaries_are_grounded(client):
    c = client.get("/api/ai/summary/compliance_summary", headers=OPS).json()
    assert c["source"] == "template" and str(c["facts"]["total"]) in c["text"]
    sku = client.get("/api/intelligence/summary", headers=OPS).json()["sku_findings"][0]["sku"]
    r = client.get(f"/api/ai/summary/return_comments?sku={sku}", headers=OPS).json()
    assert sku in r["text"] and r["facts"]["n"] > 0


def test_sac_datasets(client):
    for d in ("returns_fact", "corrective_actions", "pickup_performance", "warehouse_daily"):
        r = client.get(f"/api/integrations/sac/{d}.csv", headers=OPS)
        assert r.status_code == 200 and len(r.text.splitlines()) > 1, d
    assert "days_to_resale" in client.get("/api/integrations/sac/returns_fact.csv", headers=OPS).text.splitlines()[0]


def test_test_receivers_never_count_as_connected(client, monkeypatch):
    from app.sap import health, s4hana
    monkeypatch.setenv("REVERSEFLOW_SAP_SANDBOX", "1")
    monkeypatch.setenv("SAP_S4_URL", "http://s4.test")
    monkeypatch.setattr(s4hana.btp, "http_json", lambda m_, url, body=None, headers=None, timeout=15:
                        (lambda r: (r.status_code, r.json()))(client.get(url.replace("http://s4.test", "/api/sap/s4-sandbox"))))
    by = {s["id"]: s for s in client.post("/api/sap/status/test", headers=OPS).json()["services"]}
    assert by["s4"]["state"] == "configured" and "test sandbox" in by["s4"]["detail"]
    health.clear()
