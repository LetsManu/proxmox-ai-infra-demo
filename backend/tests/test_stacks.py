"""Stacks: VMs + LXC containers + Docker services, planned, deployed, validated and promoted together."""

import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import StackSpec
from app.services import compose_service


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def wait(client, job_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("success", "failed", "awaiting_approval"):
            return job
        time.sleep(0.05)
    raise AssertionError(job)


def test_docker_rules_block_secrets_and_host_mounts():
    base = {"name": "shop", "components": [{"name": "app", "profiles": ["docker"], "services": []}]}
    bad = [
        {"name": "db", "image": "postgres:17", "env": {"POSTGRES_PASSWORD": "hunter2"}},
        {"name": "db", "image": "postgres:17", "volumes": ["/etc:/host-etc"]},
        {"name": "db", "image": "postgres:17", "ports": ["5432"]},
        {"name": "db", "image": "postgres:17; rm -rf /"},
    ]
    for svc in bad:
        data = {**base, "components": [{**base["components"][0], "services": [svc]}]}
        with pytest.raises(ValueError):
            StackSpec(**data)
    with pytest.raises(ValueError, match="docker"):
        StackSpec(name="shop", components=[{"name": "app", "services": [{"name": "web", "image": "nginx:1"}]}])


def test_compose_renders_secret_references_only():
    text, secrets = compose_service.render([
        {"name": "db", "image": "mariadb:11.4", "ports": [], "volumes": ["db-data:/var/lib/mysql"],
         "env": {"MARIADB_PASSWORD": "secret:db_password", "MARIADB_USER": "wp"}},
    ])
    assert "${STACKSECRET_DB_PASSWORD}" in text and "db-data" in text and "no-new-privileges" in text
    assert secrets == ["STACKSECRET_DB_PASSWORD"]


def test_stack_limits_apply_to_the_total():
    comps = [{"name": f"n{i}", "cores": 4, "memory_mb": 8192, "disk_gb": 64} for i in range(5)]
    with pytest.raises(ValueError, match="Stack total"):
        StackSpec(name="big", components=comps)


def test_full_stack_lifecycle(client):
    # platform: build VM templates and download the LXC templates
    plan = wait(client, client.post("/api/platform/plan").json()["job_id"])
    if plan["result"]["plan"]["changes"]:
        assert wait(client, client.post("/api/platform/apply", json={"plan_job_id": plan["id"]}).json()["job_id"])[
            "status"] == "success"
    cts = {t["key"]: t for t in client.get("/api/templates").json() if t["kind"] == "lxc"}
    assert cts["debian-12-lxc"]["available"]

    draft = client.post("/api/ai/generate-stack",
                        json={"prompt": "WordPress for marketing with monitoring"}).json()
    stack = draft["stack"]
    kinds = {c["name"]: c["kind"] for c in stack["components"]}
    assert kinds == {"app": "vm", "monitor": "lxc"}
    assert any(s["name"] == "wordpress" for s in stack["components"][0]["services"])

    plan = wait(client, client.post("/api/stacks/plan", json={"stack": stack}).json()["job_id"])
    assert plan["status"] == "success", plan["logs"]
    text = plan["result"]["plan"]["text"]
    assert 'module.vm["wordpress-app-test"]' in text and 'module.lxc["wordpress-monitor-test"]' in text
    assert plan["result"]["plan"]["counts"]["create"] == 2

    dep = wait(client, client.post("/api/stacks/deploy", json={"plan_job_id": plan["id"]}).json()["job_id"])
    assert dep["status"] == "success", dep["logs"]
    assert "docker compose up -d (db, wordpress)" in dep["logs"]

    # promotion blocked until the whole stack validated
    assert client.post("/api/stacks/promote", json={"name": "wordpress"}).status_code == 409
    val = wait(client, client.post("/api/stacks/validate", json={"name": "wordpress"}).json()["job_id"])
    assert val["status"] == "success", val["logs"]
    app_checks = {t["title"] for t in val["result"]["members"]["wordpress-app-test"]["tests"]}
    assert "Container wordpress is running" in app_checks and "wordpress reachable on port 80" in app_checks
    monitor = val["result"]["members"]["wordpress-monitor-test"]["tests"]
    assert any(t["title"] == "SSH root login only with a key" for t in monitor)

    listed = {s["name"]: s for s in client.get("/api/stacks").json() if s["environment"] == "test"}
    assert listed["wordpress"]["last_validation"] == "PASS" and len(listed["wordpress"]["members"]) == 2

    req = wait(client, client.post("/api/stacks/promote", json={"name": "wordpress"}).json()["job_id"])
    assert req["status"] == "awaiting_approval"
    assert 'module.vm["wordpress-app"]' in req["result"]["plan"]["text"]
    bad = client.post("/api/stacks/promote", json={"name": "wordpress", "stage": "approve",
                                                   "approval_job_id": req["id"], "acknowledge": True,
                                                   "confirmation": "promote"})
    assert bad.status_code == 400
    ok = client.post("/api/stacks/promote", json={"name": "wordpress", "stage": "approve",
                                                  "approval_job_id": req["id"], "acknowledge": True,
                                                  "confirmation": "PROMOTE"})
    applied = wait(client, ok.json()["job_id"])
    assert applied["status"] == "success", applied["logs"]
    prod = {s["name"]: s for s in client.get("/api/stacks").json() if s["environment"] == "prod"}
    assert {m["name"] for m in prod["wordpress"]["members"]} == {"wordpress-app", "wordpress-monitor"}

    # recreate in TEST replaces every member; removing a component destroys it
    re_plan = wait(client, client.post("/api/stacks/plan", json={"stack": stack, "recreate": True}).json()["job_id"])
    assert re_plan["result"]["plan"]["counts"]["destroy"] == 2
    smaller = {**stack, "components": stack["components"][:1]}
    shrink = wait(client, client.post("/api/stacks/plan", json={"stack": smaller, "update": True}).json()["job_id"])
    assert shrink["result"]["removed"] == ["wordpress-monitor-test"]
    assert shrink["result"]["plan"]["counts"]["destroy"] == 1


def test_software_only_change_is_stored_and_resets_validation(client):
    stack = {"name": "swonly", "components": [{"name": "app", "kind": "vm", "template": "ubuntu-24-04", "cores": 1,
             "memory_mb": 1024, "disk_gb": 16, "profiles": ["docker"], "packages": [],
             "services": [{"name": "web", "image": "nginx:1.27", "ports": ["80:80"]}]}]}
    plan = wait(client, client.post("/api/stacks/plan", json={"stack": stack}).json()["job_id"])
    assert wait(client, client.post("/api/stacks/deploy", json={"plan_job_id": plan["id"]}).json()["job_id"])[
        "status"] == "success"
    assert wait(client, client.post("/api/stacks/validate", json={"name": "swonly"}).json()["job_id"])[
        "status"] == "success"
    stack["components"][0]["services"].append({"name": "adminer", "image": "adminer:5", "ports": ["8080:8080"]})
    stack["components"][0]["packages"] = ["git"]
    assert client.post("/api/stacks/plan", json={"stack": stack}).status_code == 409  # name clash refused
    plan2 = wait(client, client.post("/api/stacks/plan", json={"stack": stack, "update": True}).json()["job_id"])
    assert plan2["result"]["plan"]["changes"] == []
    dep = wait(client, client.post("/api/stacks/deploy", json={"plan_job_id": plan2["id"]}).json()["job_id"])
    assert dep["status"] == "success" and "(web, adminer)" in dep["logs"]
    vm = next(v for v in client.get("/api/vms").json() if v["name"] == "swonly-app-test")
    assert [s["name"] for s in vm["spec"]["services"]] == ["web", "adminer"] and vm["spec"]["packages"] == ["git"]
    assert vm["last_validation"] is None
    assert client.post("/api/stacks/promote", json={"name": "swonly"}).status_code == 409  # must validate again
