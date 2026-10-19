"""OpenID Connect sign-in: authorization code flow with PKCE, ID token checked against the issuer's keys.

Works with any compliant provider; tested with Authentik. Microsoft Entra ID and AD FS put groups
in the `groups` claim (Entra: object IDs) or app roles in `roles` (OIDC_GROUPS_CLAIM=roles).
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import HTTPException

from ..config import Settings

_PENDING_TTL = 600  # seconds a browser has to come back from the provider
_pending: dict[str, dict] = {}
_lock = threading.Lock()
_discovery: dict[str, tuple[float, dict]] = {}
_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _http(settings: Settings) -> httpx.Client:
    return httpx.Client(timeout=10, follow_redirects=False)


def discovery(settings: Settings) -> dict:
    issuer = settings.oidc_issuer.rstrip("/")
    if not issuer:
        raise HTTPException(500, "OIDC_ISSUER is not set.")
    cached = _discovery.get(issuer)
    if cached and time.time() - cached[0] < 3600:
        return cached[1]
    try:
        with _http(settings) as c:
            r = c.get(f"{issuer}/.well-known/openid-configuration")
            r.raise_for_status()
            doc = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, f"Cannot reach the sign-in provider ({issuer}): {exc}") from exc
    if doc.get("issuer", "").rstrip("/") != issuer:
        raise HTTPException(502, f"The provider reports issuer {doc.get('issuer')!r}, expected {issuer!r}. "
                                 "Set OIDC_ISSUER exactly as the provider shows it.")
    _discovery[issuer] = (time.time(), doc)
    return doc


def redirect_uri(settings: Settings) -> str:
    return settings.public_url.rstrip("/") + "/api/auth/callback"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def login_url(settings: Settings, return_to: str = "/") -> str:
    doc = discovery(settings)
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    now = time.time()
    with _lock:
        for k in [k for k, v in _pending.items() if now - v["at"] > _PENDING_TTL]:
            del _pending[k]
        _pending[state] = {"nonce": nonce, "verifier": verifier, "at": now,
                           "return_to": return_to if return_to.startswith("/") and not return_to.startswith("//")
                           else "/"}
    params = {
        "response_type": "code", "client_id": settings.oidc_client_id, "redirect_uri": redirect_uri(settings),
        "scope": settings.oidc_scopes, "state": state, "nonce": nonce,
        "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256",
    }
    return f"{doc['authorization_endpoint']}?{urlencode(params)}"


def _claim(claims: dict, name: str):
    """Claim by name; dotted names reach into nested objects (e.g. realm_access.roles)."""
    value = claims
    for part in name.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def finish(settings: Settings, code: str, state: str) -> dict:
    """Exchange the code, verify the ID token, return {username, display_name, groups}."""
    with _lock:
        pending = _pending.pop(state, None)
    if not pending or time.time() - pending["at"] > _PENDING_TTL:
        raise HTTPException(400, "The sign-in attempt expired or was started elsewhere. Try again.")
    doc = discovery(settings)
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(settings),
            "code_verifier": pending["verifier"], "client_id": settings.oidc_client_id}
    secret = settings.oidc_client_secret.get_secret_value()
    try:
        with _http(settings) as c:
            r = c.post(doc["token_endpoint"], data=data, auth=(settings.oidc_client_id, secret) if secret else None)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Token request to the sign-in provider failed: {exc}") from exc
    if r.status_code != 200:
        raise HTTPException(401, f"The sign-in provider refused the code ({r.status_code}). Check client ID, "
                                 "secret and redirect URI.")
    tokens = r.json()
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(401, "The provider returned no ID token (is the 'openid' scope enabled?).")
    jwks_uri = doc["jwks_uri"]
    client = _jwks_clients.setdefault(jwks_uri, jwt.PyJWKClient(jwks_uri, cache_keys=True))
    try:
        key = client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(id_token, key.key, algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "PS256"],
                            audience=settings.oidc_client_id, issuer=doc["issuer"],
                            options={"require": ["exp", "iat", "sub"]}, leeway=60)
    except jwt.PyJWTError as exc:
        raise HTTPException(401, f"The ID token is not valid: {exc}") from exc
    if not secrets.compare_digest(str(claims.get("nonce", "")), pending["nonce"]):
        raise HTTPException(401, "The ID token does not belong to this sign-in attempt (nonce).")

    # Groups are often only in the userinfo response (Authentik, Keycloak with defaults).
    groups = _claim(claims, settings.oidc_groups_claim)
    if groups is None and doc.get("userinfo_endpoint") and tokens.get("access_token"):
        try:
            with _http(settings) as c:
                u = c.get(doc["userinfo_endpoint"], headers={"Authorization": f"Bearer {tokens['access_token']}"})
            if u.status_code == 200:
                info = u.json()
                if info.get("sub") == claims["sub"]:
                    claims = {**info, **claims}
                    groups = _claim(info, settings.oidc_groups_claim)
        except (httpx.HTTPError, ValueError):
            pass
    if isinstance(groups, str):
        groups = [groups]
    username = str(_claim(claims, settings.oidc_username_claim) or claims.get("email") or claims["sub"])
    return {"username": username, "display_name": str(claims.get("name") or username),
            "groups": [str(g) for g in (groups or [])], "return_to": pending["return_to"]}
