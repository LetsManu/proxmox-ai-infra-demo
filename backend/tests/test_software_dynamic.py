"""Software is project-specific: profiles are discovered from role folders, packages are free-form."""

import os
import tempfile
import time

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


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


def test_profiles_are_discovered_including_project_folder(client):
    profiles = {p["key"]: p for p in client.get("/api/profiles").json()}
    assert profiles["docker"]["source"] == "built-in"
    assert profiles["redis"]["source"] == "profiles" and profiles["redis"]["port"] == 6379
    assert "linux_base" not in profiles and "packages_linux" not in profiles


def test_new_role_folder_appears_without_restart(client):
    s = get_settings()
    extra = tempfile.mkdtemp()
    os.makedirs(os.path.join(extra, "grafana", "tasks"))
    with open(os.path.join(extra, "grafana", "tasks", "main.yml"), "w") as fh:
        fh.write("- ansible.builtin.debug: { msg: hi }\n")
    with open(os.path.join(extra, "grafana", "profile.yml"), "w") as fh:
        fh.write("label: Grafana\nos_family: linux\ndescription: Dashboards\nport: 3000\n")
    os.makedirs(os.path.join(extra, "Bad Name", "tasks"))  # invalid name: ignored
    old = s.extra_profile_dirs
    s.extra_profile_dirs = f"{old}:{extra}"
    try:
        keys = {p["key"] for p in client.get("/api/profiles").json()}
        assert "grafana" in keys
        spec = {"name": "graf-test", "template": "ubuntu-24-04", "profiles": ["grafana"]}
        assert client.post("/api/vms/plan", json={"spec": spec}).status_code == 202
    finally:
        s.extra_profile_dirs = old
    assert "grafana" not in {p["key"] for p in client.get("/api/profiles").json()}


@pytest.mark.parametrize("template,packages,ok", [
    ("ubuntu-24-04", ["redis-server", "git", "nginx-extras=1.24.0-2"], True),
    ("ubuntu-24-04", ["rm -rf /"], False),
    ("ubuntu-24-04", ["curl|sh"], False),
    ("ubuntu-24-04", ["telnetd"], False),  # denylist
    ("windows-2022", ["googlechrome", "vscode", "7zip.install"], True),
    ("windows-2022", ["https://evil.example/x.msi"], False),
])
def test_package_validation(client, template, packages, ok):
    spec = {"name": "pkg-test", "template": template, "packages": packages}
    r = client.post("/api/vms/plan", json={"spec": spec})
    assert (r.status_code == 202) is ok, r.text


def test_packages_are_installed_on_deploy(client):
    # build the platform first if an earlier test module has not done it
    if client.get("/api/platform").json()["needs_platform_apply"]:
        plan = wait(client, client.post("/api/platform/plan").json()["job_id"])
        wait(client, client.post("/api/platform/apply", json={"plan_job_id": plan["id"]}).json()["job_id"])
    spec = {"name": "cache-test", "template": "ubuntu-24-04", "profiles": ["redis"], "packages": ["git", "jq"]}
    plan = wait(client, client.post("/api/vms/plan", json={"spec": spec}).json()["job_id"])
    assert plan["status"] == "success", plan["logs"]
    deploy = wait(client, client.post("/api/vms/deploy/test",
                                      json={"spec": {**plan["params"]["spec"]}, "plan_job_id": plan["id"]}).json()["job_id"])
    assert deploy["status"] == "success", deploy["logs"]
    assert "redis : main" in deploy["logs"] and "Install extra packages (git, jq)" in deploy["logs"]


def test_ai_uses_project_profiles_and_packages(client):
    out = client.post("/api/ai/generate-vm-spec",
                      json={"prompt": "Ubuntu cache server with Redis and git, 2 cpus 4 GB RAM"}).json()
    assert "redis" in out["spec"]["profiles"] and out["spec"]["packages"] == ["git"]
    win = client.post("/api/ai/generate-vm-spec",
                      json={"prompt": "Windows box with IIS, chrome and vscode"}).json()
    assert win["spec"]["profiles"] == ["iis"] and set(win["spec"]["packages"]) == {"googlechrome", "vscode"}
