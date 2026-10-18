"""End-to-end test of the full workflow in mock mode (no Proxmox, no Terraform, no AI key).

Run from backend/:  pytest -q
"""

import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

SPEC = {"name": "demo-web-test", "environment": "test", "template": "ubuntu-24-04", "cores": 2,
        "memory_mb": 4096, "disk_gb": 32, "network": "test", "description": "demo",
        "cloud_init": {"packages": ["qemu-guest-agent", "docker.io"], "commands": []}, "tags": []}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def wait(client, job_id, until=("success", "failed", "awaiting_approval"), timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in until:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish: {job}")


def test_health_and_inventory(client):
    assert client.get("/api/health").json()["mode"] == "mock"
    status = client.get("/api/proxmox/status").json()
    assert status["connected"] and status["templates"]
    assert "secret" not in str(status).lower()
    templates = client.get("/api/templates").json()
    assert {t["key"] for t in templates} == {"ubuntu-24-04", "debian-12"}
    assert all(t["available"] for t in templates)
    envs = {e["key"]: e for e in client.get("/api/environments").json()}
    assert envs["test"]["vmid_min"] == 900 and envs["prod"]["requires_approval"]


def test_limits_enforced(client):
    r = client.post("/api/vms/plan", json={"spec": {**SPEC, "cores": 6}})
    assert r.status_code == 422
    r = client.post("/api/vms/plan", json={"spec": {**SPEC, "network": "prod"}})
    assert r.status_code == 422


def test_full_lifecycle(client):
    # Plan
    plan = wait(client, client.post("/api/vms/plan", json={"spec": SPEC}).json()["job_id"])
    assert plan["status"] == "success", plan["logs"]
    assert plan["result"]["plan"]["counts"] == {"create": 1, "update": 0, "destroy": 0}
    assert 900 <= plan["result"]["vmid"] <= 999

    # AI summary (local fallback)
    summary = client.post("/api/ai/summarize-plan",
                          json={"plan_text": plan["result"]["plan"]["text"], "environment": "test"}).json()
    assert summary["risk_level"] == "low" and summary["source"] == "local-fallback"

    # Deploy refuses a changed form
    r = client.post("/api/vms/deploy/test", json={"spec": {**SPEC, "cores": 3}, "plan_job_id": plan["id"]})
    assert r.status_code == 409
    deploy = wait(client, client.post("/api/vms/deploy/test",
                                      json={"spec": SPEC, "plan_job_id": plan["id"]}).json()["job_id"])
    assert deploy["status"] == "success", deploy["logs"]
    assert "Apply complete!" in deploy["logs"]

    # Promotion blocked before validation
    r = client.post("/api/vms/promote/production", json={"name": "demo-web-test", "stage": "request"})
    assert r.status_code == 409

    # Failing validation, then troubleshooting
    bad = wait(client, client.post("/api/vms/validate", json={"name": "demo-web-test",
                                                              "simulate_failure": True}).json()["job_id"])
    assert bad["status"] == "failed" and bad["result"]["validation"]["overall"] == "FAIL"
    tips = client.post("/api/ai/troubleshoot", json={"vm_name": "demo-web-test", "job_logs": bad["logs"],
                                                     "validation_output": bad["result"]["validation"]}).json()
    assert tips["recreate_appropriate"] is True

    # Recreate TEST VM, then passing validation
    rec = wait(client, client.post("/api/vms/recreate", json={"name": "demo-web-test"}).json()["job_id"])
    assert rec["status"] == "success" and rec["result"]["plan"]["has_destroy"]
    good = wait(client, client.post("/api/vms/validate", json={"name": "demo-web-test",
                                                               "health_check_port": 22}).json()["job_id"])
    assert good["status"] == "success" and good["result"]["validation"]["overall"] == "PASS"

    # Promotion request -> awaiting approval, nothing changed in prod
    req = wait(client, client.post("/api/vms/promote/production",
                                   json={"name": "demo-web-test", "stage": "request"}).json()["job_id"])
    assert req["status"] == "awaiting_approval", req["logs"]
    assert req["result"]["required_confirmation"] == "PROMOTE"
    assert 100 <= req["result"]["vmid"] <= 299
    assert not [v for v in client.get("/api/vms").json() if v["environment"] == "prod"]

    # Approval needs acknowledge + exact word
    base = {"name": "demo-web-test", "stage": "approve", "approval_job_id": req["id"]}
    assert client.post("/api/vms/promote/production", json={**base, "confirmation": "PROMOTE"}).status_code == 400
    assert client.post("/api/vms/promote/production",
                       json={**base, "acknowledge": True, "confirmation": "promote"}).status_code == 400
    r = client.post("/api/vms/promote/production", json={**base, "acknowledge": True, "confirmation": "PROMOTE"})
    applied = wait(client, r.json()["job_id"])
    assert applied["status"] == "success", applied["logs"]
    prod = [v for v in client.get("/api/vms").json() if v["environment"] == "prod"]
    assert prod and prod[0]["name"] == "demo-web" and prod[0]["spec"]["environment"] == "prod"

    # Double approval rejected
    again = client.post("/api/vms/promote/production", json={**base, "acknowledge": True, "confirmation": "PROMOTE"})
    assert again.status_code == 409

    # Production recreate requires approval and is high risk
    rq = wait(client, client.post("/api/vms/recreate", json={"name": "demo-web", "environment": "prod"}).json()["job_id"])
    assert rq["status"] == "awaiting_approval" and rq["result"]["plan"]["has_destroy"]
    risk = client.post("/api/ai/summarize-plan", json={"plan_text": rq["result"]["plan"]["text"],
                                                       "environment": "prod"}).json()
    assert risk["risk_level"] == "high" and risk["human_approval_required"]

    hist = client.get("/api/history").json()
    assert {h["action"] for h in hist} >= {"plan", "deploy", "validate", "promote-apply", "recreate"}


def test_ai_spec_generation(client):
    out = client.post("/api/ai/generate-vm-spec", json={"prompt": (
        "Create a small Ubuntu test server for a web app with 2 CPUs, 4 GB RAM, 40 GB disk, "
        "and Docker installed.")}).json()
    spec = out["spec"]
    assert spec["cores"] == 2 and spec["memory_mb"] == 4096 and spec["disk_gb"] == 40
    assert "docker.io" in spec["cloud_init"]["packages"] and spec["environment"] == "test"

    r = client.post("/api/ai/generate-vm-spec", json={"prompt": "production database with 64 cpus and 512 GB RAM"})
    assert r.status_code == 422
    assert any("max" in e for e in r.json()["detail"]["errors"])
