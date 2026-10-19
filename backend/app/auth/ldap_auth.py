"""LDAP sign-in: look the user up with a service account, then bind as the user to check the password.

Active Directory: LDAP_USER_FILTER=(&(objectClass=user)(sAMAccountName={username})), groups from memberOf,
LDAP_NESTED_GROUPS=true resolves nested groups. OpenLDAP: (uid={username}) with the memberof overlay.
Authentik LDAP outpost: (cn={username}), groups in memberOf.
"""

from __future__ import annotations

import ssl
import threading
import time

from fastapi import HTTPException
from ldap3 import SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPBindError, LDAPException, LDAPInvalidCredentialsResult
from ldap3.utils.conv import escape_filter_chars

from ..config import Settings

# Simple brute-force brake per username: 5 failures lock it for 5 minutes (per backend process).
_MAX_FAILURES, _LOCK_SECONDS = 5, 300
_failures: dict[str, list[float]] = {}
_lock = threading.Lock()
NESTED_RULE = "1.2.840.113556.1.4.1941"  # LDAP_MATCHING_RULE_IN_CHAIN (Active Directory)


def _server(settings: Settings) -> Server:
    if not settings.ldap_url:
        raise HTTPException(500, "LDAP_URL is not set.")
    if not settings.ldap_url.lower().startswith("ldaps://") and not settings.ldap_start_tls:
        # passwords would cross the network in clear text
        raise HTTPException(500, "LDAP needs TLS: use ldaps:// in LDAP_URL or set LDAP_START_TLS=true.")
    tls =Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=settings.ldap_ca_file or None,
              version=ssl.PROTOCOL_TLS_CLIENT)
    return Server(settings.ldap_url, use_ssl=settings.ldap_url.lower().startswith("ldaps://"), tls=tls,
                  connect_timeout=10, get_info="NO_INFO")


def _connect(settings: Settings, server: Server, user: str | None, password: str | None) -> Connection:
    conn = Connection(server, user=user, password=password, receive_timeout=15, raise_exceptions=True,
                      auto_bind="NONE", read_only=True)
    conn.open()
    if settings.ldap_start_tls and not server.ssl:
        conn.start_tls()
    conn.bind()
    return conn


def _check_lock(username: str) -> None:
    now = time.time()
    with _lock:
        recent = [t for t in _failures.get(username, []) if now - t < _LOCK_SECONDS]
        _failures[username] = recent
        if len(recent) >= _MAX_FAILURES:
            raise HTTPException(429, "Too many failed sign-ins for this user. Wait 5 minutes.")


def _failed(username: str) -> HTTPException:
    with _lock:
        _failures.setdefault(username, []).append(time.time())
    return HTTPException(401, "Wrong username or password.")


def authenticate(settings: Settings, username: str, password: str) -> dict:
    """Return {username, display_name, groups} or raise 401."""
    username = username.strip()
    key = username.lower()
    # An empty password would be an "unauthenticated bind", which many servers accept: never allow it.
    if not username or not password:
        raise HTTPException(401, "Wrong username or password.")
    _check_lock(key)
    server = _server(settings)
    try:
        svc = _connect(settings, server, settings.ldap_bind_dn or None,
                       settings.ldap_bind_password.get_secret_value() or None)
    except LDAPException as exc:
        raise HTTPException(502, f"Cannot reach or bind to the directory: {exc.__class__.__name__}. Check LDAP_URL, "
                                 "LDAP_BIND_DN and the bind password; for a certificate from an internal CA set "
                                 "LDAP_CA_FILE.") from exc
    try:
        flt = settings.ldap_user_filter.replace("{username}", escape_filter_chars(username))
        # memberOf is operational on OpenLDAP: it is only returned when asked for by name
        svc.search(settings.ldap_base_dn, flt, SUBTREE, size_limit=2,
                   attributes=[settings.ldap_group_attribute, settings.ldap_display_name_attribute,
                               settings.ldap_username_attribute])
        entries = [e for e in svc.response if e.get("type") == "searchResEntry"]
        if len(entries) != 1:
            raise _failed(key)  # unknown user or ambiguous filter: same answer as a wrong password
        dn, attrs = entries[0]["dn"], entries[0]["attributes"]
        try:
            _connect(settings, server, dn, password).unbind()
        except (LDAPBindError, LDAPInvalidCredentialsResult):
            raise _failed(key) from None
        groups = [str(g) for g in _as_list(attrs.get(settings.ldap_group_attribute))]
        if settings.ldap_nested_groups:
            svc.search(settings.ldap_base_dn, f"(member:{NESTED_RULE}:={escape_filter_chars(dn)})", SUBTREE,
                       attributes=["cn"])
            groups += [e["dn"] for e in svc.response if e.get("type") == "searchResEntry"]
    except LDAPException as exc:
        raise HTTPException(502, f"Directory search failed: {exc.__class__.__name__}.") from exc
    finally:
        svc.unbind()
    with _lock:
        _failures.pop(key, None)
    display = _as_list(attrs.get(settings.ldap_display_name_attribute))
    canonical = _as_list(attrs.get(settings.ldap_username_attribute))
    name = str(canonical[0]) if canonical else username
    return {"username": name, "display_name": str(display[0]) if display else name, "groups": sorted(set(groups))}


def _as_list(value) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]
