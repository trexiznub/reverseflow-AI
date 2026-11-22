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
        yield c


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


def test_twin_recalculates(client):
    base = client.post("/api/twin/simulate", json={"params": {"replications": 10}}, headers=OPS).json()
    heavy = client.post("/api/twin/simulate", json={"params": {"replications": 10, "surge_intensity": 1.8}}, headers=OPS).json()
    b, h = base["scenarios"]["baseline"]["kpis"], heavy["scenarios"]["baseline"]["kpis"]
    assert h["peak_pickup_backlog"]["mean"] > b["peak_pickup_backlog"]["mean"]
    assert base["scenarios"]["C"]["kpis"]["value_at_risk"]["mean"] < b["value_at_risk"]["mean"]


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
