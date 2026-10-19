"""Sign-in endpoints (docs/authentication.md). No password or token is ever stored by the console."""

from __future__ import annotations

from urllib.parse import quote, urlsplit

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from .. import auth
from ..auth import ldap_auth, oidc
from ..config import get_settings
from ..workers.job_runner import add_history

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LdapLogin(BaseModel):
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=1024)


@router.get("/config")
def config():
    s = get_settings()
    mode = s.auth_mode.lower() if auth.auth_enabled(s) else "none"
    return {"mode": mode, "provider_name": s.auth_provider_name or {"oidc": "single sign-on", "ldap": "directory"}
            .get(mode, ""), "four_eyes": s.auth_four_eyes and mode != "none"}


@router.get("/me")
def me():
    user = auth.current_user()
    if user is None:
        raise HTTPException(401, "Not signed in.")
    return {**user.public(), "csrf": user.csrf, "auth": user.provider != "none"}


def _same_origin(request: Request) -> None:
    """Sign-in by form post: refuse requests started by another site."""
    origin = request.headers.get("origin")
    if origin:
        want = urlsplit(get_settings().public_url)
        got = urlsplit(origin)
        if (got.scheme, got.netloc) != (want.scheme, want.netloc):
            raise HTTPException(403, f"Sign-in from {origin} is not allowed (PUBLIC_URL is {want.scheme}://{want.netloc}).")


def _signed_in(s, info: dict, provider: str) -> tuple[str, auth.User]:
    roles = auth.roles_for(s, info["groups"])
    token, user = auth.start_session(s, username=info["username"], display_name=info["display_name"], roles=roles,
                                     provider=provider)
    add_history(vm_name="-", environment="console", action="sign-in", status="success", user=user.username,
                plan_summary=f"{provider}; roles: {', '.join(roles)}")
    return token, user


@router.get("/login")
def oidc_login(return_to: str = Query("/", max_length=512)):
    s = get_settings()
    if s.auth_mode.lower() != "oidc":
        raise HTTPException(404, "Single sign-on is not configured.")
    return RedirectResponse(oidc.login_url(s, return_to), status_code=302)


@router.get("/callback")
def oidc_callback(code: str = Query("", max_length=4096), state: str = Query("", max_length=256),
                  error: str = Query("", max_length=256), error_description: str = Query("", max_length=1024)):
    s = get_settings()
    if s.auth_mode.lower() != "oidc":
        raise HTTPException(404, "Single sign-on is not configured.")
    try:
        if error:
            raise HTTPException(401, f"The sign-in provider reported: {error_description or error}")
        info = oidc.finish(s, code, state)
        token, _user = _signed_in(s, info, "oidc")
        response = RedirectResponse(info["return_to"], status_code=302)
        auth.set_cookie(response, s, token)
        return response
    except HTTPException as exc:
        return RedirectResponse(f"/?login_error={quote(str(exc.detail)[:300])}", status_code=302)


@router.post("/login")
def ldap_login(body: LdapLogin, request: Request):
    s = get_settings()
    if s.auth_mode.lower() != "ldap":
        raise HTTPException(404, "Directory sign-in is not configured.")
    _same_origin(request)
    info = ldap_auth.authenticate(s, body.username, body.password)
    token, user = _signed_in(s, info, "ldap")
    response = JSONResponse({**user.public(), "csrf": user.csrf, "auth": True})
    auth.set_cookie(response, s, token)
    return response


@router.post("/logout")
def logout(request: Request):
    s = get_settings()
    auth.end_session(request.cookies.get(auth.COOKIE))
    response = JSONResponse({"signed_out": True})
    auth.clear_cookie(response, s)
    return response
