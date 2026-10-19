"""Sign-in, roles, CSRF and approvals with AUTH_MODE=ldap / oidc (directory and provider are faked)."""

import base64
import hashlib
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.auth import ldap_auth, oidc, roles_for
from app.config import get_settings

GROUPS = {
    "AUTH_VIEWER_GROUPS": "CN=PX Viewers,OU=Groups,DC=corp,DC=example",
    "AUTH_OPERATOR_GROUPS": "px-operators",
    "AUTH_APPROVER_GROUPS": "px-approvers; 0f1e2d3c-aaaa-bbbb-cccc-000000000001",
}
DIRECTORY = {  # username -> (password, groups)
    "vera": ("pw-vera-123", ["CN=PX Viewers,OU=Groups,DC=corp,DC=example"]),
    "otto": ("pw-otto-123", ["cn=px-operators,ou=groups,dc=corp,dc=example"]),
    "anna": ("pw-anna-123", ["CN=px-approvers,OU=Groups,DC=corp,DC=example"]),
    "bert": ("pw-bert-123", ["CN=px-approvers,OU=Groups,DC=corp,DC=example"]),
    "nobody": ("pw-nobody-123", ["CN=Domain Users,CN=Users,DC=corp,DC=example"]),
}


def _settings_env(monkeypatch, **env):
    for k, v in {**GROUPS, **env}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()


@pytest.fixture
def ldap_client(monkeypatch):
    _settings_env(monkeypatch, AUTH_MODE="ldap", LDAP_URL="ldaps://dc.example.invalid", AUTH_COOKIE_SECURE="false",
                  PUBLIC_URL="http://testserver")

    def fake_authenticate(settings, username, password):
        entry = DIRECTORY.get(username)
        if not entry or entry[0] != password:
            raise ldap_auth.HTTPException(401, "Wrong username or password.")
        return {"username": username, "display_name": username.title(), "groups": entry[1]}

    monkeypatch.setattr(ldap_auth, "authenticate", fake_authenticate)
    from app.main import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def login(client, name):
    r = client.post("/api/auth/login", json={"username": name, "password": DIRECTORY[name][0]})
    assert r.status_code == 200, r.text
    client.headers["X-CSRF-Token"] = r.json()["csrf"]
    return r.json()


def test_roles_from_groups(monkeypatch):
    _settings_env(monkeypatch)
    s = get_settings()
    assert roles_for(s, ["CN=PX Viewers,OU=Groups,DC=corp,DC=example"]) == ["viewer"]
    assert roles_for(s, ["cn=PX-Operators,ou=x,dc=y"]) == ["viewer", "operator"]  # CN match, case-insensitive
    assert roles_for(s, ["0F1E2D3C-AAAA-BBBB-CCCC-000000000001"]) == ["viewer", "operator", "approver"]  # Entra ID
    assert roles_for(s, ["px-approvers"]) == ["viewer", "operator", "approver"]  # plain name (Authentik)
    assert roles_for(s, ["CN=Domain Users,CN=Users,DC=corp,DC=example"]) == []
    get_settings.cache_clear()


def test_api_needs_sign_in(ldap_client):
    assert ldap_client.get("/api/vms").status_code == 401
    assert ldap_client.get("/api/health").json() == {"status": "ok"}  # container health check, no details
    assert ldap_client.get("/api/auth/config").json()["mode"] == "ldap"
    r = ldap_client.post("/api/auth/login", json={"username": "otto", "password": "wrong"})
    assert r.status_code == 401
    r = ldap_client.post("/api/auth/login", json={"username": "nobody", "password": DIRECTORY["nobody"][0]})
    assert r.status_code == 403 and "none of the console's groups" in r.json()["detail"]


def test_session_cookie_and_csrf(ldap_client):
    me = login(ldap_client, "otto")
    assert me["roles"] == ["viewer", "operator"]
    cookie = ldap_client.cookies.get("pac_session")
    assert cookie and len(cookie) > 30
    assert ldap_client.get("/api/auth/me").json()["username"] == "otto"
    assert ldap_client.get("/api/health").json()["version"]
    # a write without the CSRF header is refused even with a valid session cookie
    token = ldap_client.headers.pop("X-CSRF-Token")
    assert ldap_client.post("/api/platform/plan").status_code == 403
    ldap_client.headers["X-CSRF-Token"] = token
    assert ldap_client.post("/api/platform/plan").status_code == 202
    # sign-in from another site is refused
    r = ldap_client.post("/api/auth/login", json={"username": "otto", "password": DIRECTORY["otto"][0]},
                         headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    ldap_client.post("/api/auth/logout")
    assert ldap_client.get("/api/vms").status_code == 401


def test_viewer_cannot_change_anything(ldap_client):
    login(ldap_client, "vera")
    assert ldap_client.get("/api/vms").status_code == 200
    r = ldap_client.post("/api/platform/plan")
    assert r.status_code == 403 and "operator" in r.json()["detail"]


def test_only_approvers_decide_and_four_eyes(ldap_client, monkeypatch):
    monkeypatch.setenv("AUTH_FOUR_EYES", "true")
    get_settings.cache_clear()
    login(ldap_client, "otto")
    # operators may plan the platform but not apply it, and may not approve production changes
    r = ldap_client.post("/api/platform/apply", json={"plan_job_id": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 403 and "approver" in r.json()["detail"]
    r = ldap_client.post("/api/vms/promote/production",
                         json={"name": "x-test", "stage": "approve", "approval_job_id": "x", "acknowledge": True,
                               "confirmation": "PROMOTE"})
    assert r.status_code == 403 and "approver" in r.json()["detail"]
    # an approval job requested by anna can be decided by bert, not by anna herself
    from app.workers.job_runner import create_job
    from app.database import session_scope
    from app.models import Job, JobStatus

    job_id = create_job(action="promote", environment="prod", vm_name="x", user="anna", params={"source_vm": "x-test"})
    with session_scope() as db:
        db.get(Job, job_id).status = JobStatus.AWAITING_APPROVAL
    body = {"name": "x-test", "stage": "reject", "approval_job_id": job_id}
    ldap_client.post("/api/auth/logout")
    login(ldap_client, "anna")
    r = ldap_client.post("/api/vms/promote/production", json=body)
    assert r.status_code == 403 and "Four-eyes" in r.json()["detail"]
    ldap_client.post("/api/auth/logout")
    login(ldap_client, "bert")
    assert ldap_client.post("/api/vms/promote/production", json=body).status_code == 202
    with session_scope() as db:
        assert db.get(Job, job_id).result["decided_by"] == "bert"


# ---- LDAP logic against a fake directory ---------------------------------------

class FakeConn:
    def __init__(self, user, password):
        self.user, self.password, self.response = user, password, []

    def search(self, base, flt, scope, attributes=None, size_limit=0):
        FakeConn.filters.append(flt)
        if "member:1.2.840.113556.1.4.1941:=" in flt:
            self.response = [{"type": "searchResEntry", "dn": "CN=px-approvers,OU=Groups,DC=corp,DC=example"}]
        elif "otto" in flt:
            self.response = [{"type": "searchResEntry", "dn": "CN=Otto,OU=Users,DC=corp,DC=example",
                              "attributes": {"memberOf": ["CN=Nested,OU=Groups,DC=corp,DC=example"],
                                             "displayName": "Otto Operator"}}]
        else:
            self.response = []

    def unbind(self):
        pass


def test_ldap_binds_as_user_and_resolves_nested_groups(monkeypatch):
    _settings_env(monkeypatch, AUTH_MODE="ldap", LDAP_URL="ldaps://dc.example.invalid", LDAP_NESTED_GROUPS="true",
                  LDAP_BIND_DN="CN=svc,DC=corp,DC=example", LDAP_BIND_PASSWORD="svc-pw")
    FakeConn.filters = []
    binds = []

    def fake_connect(settings, server, user, password):
        binds.append(user)
        if user == "CN=Otto,OU=Users,DC=corp,DC=example" and password != "right":
            raise ldap_auth.LDAPBindError("invalid credentials")
        return FakeConn(user, password)

    monkeypatch.setattr(ldap_auth, "_connect", fake_connect)
    s = get_settings()
    info = ldap_auth.authenticate(s, "otto", "right")
    assert binds == ["CN=svc,DC=corp,DC=example", "CN=Otto,OU=Users,DC=corp,DC=example"]
    assert info["display_name"] == "Otto Operator"
    assert "CN=px-approvers,OU=Groups,DC=corp,DC=example" in info["groups"]  # nested via matching rule
    # filter injection is escaped
    with pytest.raises(ldap_auth.HTTPException):
        ldap_auth.authenticate(s, "*)(objectClass=*", "x")
    assert "\\2a\\29\\28objectClass=\\2a" in FakeConn.filters[-1]
    # empty password never reaches the directory (anonymous bind)
    with pytest.raises(ldap_auth.HTTPException):
        ldap_auth.authenticate(s, "otto", "")
    # wrong password, then lockout after 5 failures
    for _ in range(5):
        with pytest.raises(ldap_auth.HTTPException) as exc:
            ldap_auth.authenticate(s, "otto", "wrong")
        assert exc.value.status_code == 401
    with pytest.raises(ldap_auth.HTTPException) as exc:
        ldap_auth.authenticate(s, "otto", "right")
    assert exc.value.status_code == 429
    ldap_auth._failures.clear()
    get_settings.cache_clear()


def test_ldap_requires_tls(monkeypatch):
    _settings_env(monkeypatch, AUTH_MODE="ldap", LDAP_URL="ldap://dc.example.invalid", LDAP_START_TLS="false")
    with pytest.raises(ldap_auth.HTTPException) as exc:
        ldap_auth.authenticate(get_settings(), "otto", "pw")
    assert "TLS" in exc.value.detail
    get_settings.cache_clear()


# ---- OIDC flow against a fake provider -----------------------------------------

ISSUER = "https://idp.example.invalid/application/o/proxmox/"


@pytest.fixture
def oidc_client(monkeypatch):
    _settings_env(monkeypatch, AUTH_MODE="oidc", OIDC_ISSUER=ISSUER, OIDC_CLIENT_ID="px-console",
                  OIDC_CLIENT_SECRET="client-secret", PUBLIC_URL="http://testserver", AUTH_COOKIE_SECURE="false")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    state = {"groups_in_token": False, "nonce": None, "verifier": None, "aud": "px-console"}

    def handler(request: httpx.Request):
        url = str(request.url)
        if url.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json={"issuer": ISSUER, "authorization_endpoint": ISSUER + "authorize",
                                             "token_endpoint": ISSUER + "token", "jwks_uri": ISSUER + "jwks",
                                             "userinfo_endpoint": ISSUER + "userinfo"})
        if url.endswith("/token"):
            form = parse_qs(request.content.decode())
            challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"][0].encode()).digest())
            assert challenge.rstrip(b"=").decode() == state["challenge"]  # PKCE
            assert request.headers["authorization"].startswith("Basic ")
            claims = {"iss": ISSUER, "aud": state["aud"], "sub": "u-1", "iat": int(time.time()),
                      "exp": int(time.time()) + 300, "nonce": state["nonce"], "preferred_username": "anna",
                      "name": "Anna Approver"}
            if state["groups_in_token"]:
                claims["groups"] = ["px-approvers"]
            return httpx.Response(200, json={"id_token": jwt.encode(claims, key, algorithm="RS256",
                                                                     headers={"kid": "k1"}),
                                             "access_token": "at"})
        if url.endswith("/userinfo"):
            return httpx.Response(200, json={"sub": "u-1", "groups": ["px-operators"]})
        return httpx.Response(404)

    monkeypatch.setattr(oidc, "_http", lambda s: httpx.Client(transport=httpx.MockTransport(handler)))

    class Keys:
        def get_signing_key_from_jwt(self, token):
            return type("K", (), {"key": key.public_key()})()

    monkeypatch.setitem(oidc._jwks_clients, ISSUER + "jwks", Keys())
    oidc._discovery.clear()
    from app.main import app

    with TestClient(app, follow_redirects=False) as c:
        c.oidc_state = state
        yield c
    get_settings.cache_clear()


def _start(client):
    r = client.get("/api/auth/login?return_to=/stacks")
    assert r.status_code == 302
    q = parse_qs(urlsplit(r.headers["location"]).query)
    assert q["redirect_uri"] == ["http://testserver/api/auth/callback"] and q["code_challenge_method"] == ["S256"]
    client.oidc_state.update(nonce=q["nonce"][0], challenge=q["code_challenge"][0])
    return q["state"][0]


def test_oidc_login_with_groups_from_userinfo(oidc_client):
    st = _start(oidc_client)
    r = oidc_client.get(f"/api/auth/callback?code=c1&state={st}")
    assert r.status_code == 302 and r.headers["location"] == "/stacks"
    me = oidc_client.get("/api/auth/me").json()
    assert me["username"] == "anna" and me["roles"] == ["viewer", "operator"]  # userinfo groups
    # the state is single-use
    r = oidc_client.get(f"/api/auth/callback?code=c1&state={st}")
    assert "login_error" in r.headers["location"]


def test_oidc_rejects_token_for_another_client(oidc_client):
    oidc_client.oidc_state.update(aud="someone-else", groups_in_token=True)
    st = _start(oidc_client)
    r = oidc_client.get(f"/api/auth/callback?code=c1&state={st}")
    assert "login_error" in r.headers["location"] and "audience" in r.headers["location"].lower()
    assert oidc_client.get("/api/auth/me").status_code == 401


def test_oidc_open_redirect_blocked(oidc_client):
    oidc_client.oidc_state.update(groups_in_token=True)
    r = oidc_client.get("/api/auth/login?return_to=//evil.example/x")
    q = parse_qs(urlsplit(r.headers["location"]).query)
    oidc_client.oidc_state.update(nonce=q["nonce"][0], challenge=q["code_challenge"][0])
    r = oidc_client.get(f"/api/auth/callback?code=c1&state={q['state'][0]}")
    assert r.headers["location"] == "/"
