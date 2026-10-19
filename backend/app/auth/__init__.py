"""Sign-in, sessions and roles (docs/authentication.md).

Identity comes from the company directory, never from the console itself:
  - oidc: Authentik, Microsoft Entra ID, AD FS, Keycloak (authorization code + PKCE)
  - ldap: Active Directory, OpenLDAP, Authentik LDAP outpost (bind as the user)
  - none: no login; everyone is APP_USER with every role (demo, single admin on localhost)

Roles come from directory groups (AUTH_*_GROUPS, separated by ";" because DNs contain commas):
  viewer    read everything
  operator  plan, deploy and validate in TEST, request production changes
  approver  approve or reject production changes, apply the platform stack, approve AI drafts

A session is a random token in an HttpOnly cookie; the database keeps its SHA-256 only.
Every state-changing request must echo the session's CSRF token in X-CSRF-Token.
"""

from __future__ import annotations

import contextvars
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from ..config import Settings, get_settings
from ..database import session_scope
from ..models import AuthSession

ROLES = ("viewer", "operator", "approver")
COOKIE = "pac_session"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# reachable without a session: health check (docker), sign-in itself
PUBLIC_PATHS = ("/api/health", "/api/auth/")


@dataclass
class User:
    username: str
    display_name: str = ""
    roles: list[str] = field(default_factory=list)
    provider: str = "none"
    csrf: str = ""

    def has(self, role: str) -> bool:
        return role in self.roles

    def public(self) -> dict:
        return {"username": self.username, "display_name": self.display_name or self.username,
                "roles": self.roles, "provider": self.provider}


_current: contextvars.ContextVar[User | None] = contextvars.ContextVar("current_user", default=None)


def current_user() -> User | None:
    return _current.get()


def actor() -> str:
    """Name recorded in jobs, history and approvals for the current request."""
    user = _current.get()
    return user.username if user else get_settings().app_user


def require_role(role: str) -> User:
    user = _current.get()
    if user is None:
        raise HTTPException(401, "Sign in first.")
    if not user.has(role):
        raise HTTPException(403, f"This needs the {role} role. Ask an administrator to add you to the "
                                 f"directory group for {role}s.")
    return user


def require_second_person(requested_by: str) -> None:
    """With AUTH_FOUR_EYES the approver must differ from whoever requested the change."""
    s = get_settings()
    if s.auth_four_eyes and auth_enabled(s) and requested_by.lower() == actor().lower():
        raise HTTPException(403, "Four-eyes rule: a different approver must approve or reject this change.")


def auth_enabled(settings: Settings) -> bool:
    return settings.auth_mode.lower() in ("oidc", "ldap")


# ---- roles from groups -------------------------------------------------------

def _group_keys(group: str) -> set[str]:
    """A group matches by full value (DN, name, ID) or, for a DN, by its first CN/OU value."""
    g = group.strip().lower()
    keys = {g}
    first = g.split(",", 1)[0]
    if "=" in first:
        keys.add(first.split("=", 1)[1].strip())
    return keys


def roles_for(settings: Settings, groups: list[str]) -> list[str]:
    have: set[str] = set()
    for g in groups:
        have |= _group_keys(str(g))
    granted = []
    for role in ROLES:
        wanted = {w.strip().lower() for w in getattr(settings, f"auth_{role}_groups").split(";") if w.strip()}
        if wanted & have:
            granted.append(role)
    # approver includes operator includes viewer
    if "approver" in granted:
        return list(ROLES)
    if "operator" in granted:
        return ["viewer", "operator"]
    return granted


# ---- sessions ----------------------------------------------------------------

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(settings: Settings, *, username: str, display_name: str, roles: list[str],
                  provider: str) -> tuple[str, User]:
    if not roles:
        raise HTTPException(403, "You signed in, but you are in none of the console's groups. Ask an administrator "
                                 "to add you to the viewer, operator or approver group.")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        db.query(AuthSession).filter(AuthSession.expires_at < now).delete()
        db.add(AuthSession(token_hash=_hash(token), username=username[:128], display_name=display_name[:256],
                           roles=roles, csrf=csrf, provider=provider,
                           expires_at=now + timedelta(hours=settings.auth_session_hours)))
    return token, User(username, display_name, roles, provider, csrf)


def end_session(token: str | None) -> None:
    if token:
        with session_scope() as db:
            db.query(AuthSession).filter(AuthSession.token_hash == _hash(token)).delete()


def _load_session(token: str | None) -> User | None:
    if not token:
        return None
    with session_scope() as db:
        row = db.get(AuthSession, _hash(token))
        if row is None:
            return None
        expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            db.delete(row)
            return None
        return User(row.username, row.display_name, list(row.roles or []), row.provider, row.csrf)


def set_cookie(response, settings: Settings, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=settings.auth_session_hours * 3600, httponly=True,
                        secure=settings.auth_cookie_secure, samesite="lax", path="/")


def clear_cookie(response, settings: Settings) -> None:
    response.delete_cookie(COOKIE, path="/", secure=settings.auth_cookie_secure, httponly=True, samesite="lax")


# ---- middleware --------------------------------------------------------------

def _deny(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


async def auth_middleware(request: Request, call_next):
    """Resolves the user for every /api request and enforces sign-in, CSRF and the operator role for writes."""
    path = request.url.path
    if not path.startswith("/api"):
        return await call_next(request)
    s = get_settings()
    if not auth_enabled(s):
        user = User(s.app_user, s.app_user, list(ROLES), "none")
    else:
        user = _load_session(request.cookies.get(COOKIE))
    token = _current.set(user)
    try:
        public = path == "/api/health" or path.startswith("/api/auth/")
        if not public:
            if user is None:
                return _deny(401, "Sign in first.")
            if request.method not in SAFE_METHODS:
                if auth_enabled(s) and not hmac.compare_digest(request.headers.get(CSRF_HEADER, ""), user.csrf):
                    return _deny(403, "Missing or wrong CSRF token. Reload the page.")
                if not user.has("operator"):
                    return _deny(403, "Your account can only view. Changes need the operator role.")
        elif request.method not in SAFE_METHODS and auth_enabled(s) and user is not None \
                and path == "/api/auth/logout" \
                and not hmac.compare_digest(request.headers.get(CSRF_HEADER, ""), user.csrf):
            return _deny(403, "Missing or wrong CSRF token. Reload the page.")
        return await call_next(request)
    finally:
        _current.reset(token)
