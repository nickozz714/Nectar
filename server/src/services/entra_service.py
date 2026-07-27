from __future__ import annotations

import secrets
import time

from neo4j import Session

from src.config import get_settings
from src.repository import audit_repo, registration_repo, tenancy_repo

_SCOPES = ["User.Read"]
_states: dict[str, float] = {}  # state -> created-at (one replica; short-lived)
_STATE_TTL = 600


def _client():
    import msal  # imported lazily so the app runs without msal when Entra is off

    s = get_settings()
    return msal.ConfidentialClientApplication(
        s.ENTRA_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{s.ENTRA_TENANT_ID}",
        client_credential=s.ENTRA_CLIENT_SECRET,
    )


def login_url(redirect_uri: str) -> str:
    now = time.time()
    for k in [k for k, t in _states.items() if now - t > _STATE_TTL]:
        _states.pop(k, None)
    state = secrets.token_urlsafe(16)
    _states[state] = now
    return _client().get_authorization_request_url(
        _SCOPES, redirect_uri=redirect_uri, state=state
    )


def complete(session: Session, code: str, state: str, redirect_uri: str) -> dict:
    """Validate the Entra auth-code callback, map the user to a HiveMind account by email,
    and mint a login token. First Entra user of an empty hive becomes org_admin; others
    must already have an account with that email (an admin created/invited them)."""
    if state not in _states:
        raise PermissionError("Invalid or expired login state")
    _states.pop(state, None)

    result = _client().acquire_token_by_authorization_code(
        code, scopes=_SCOPES, redirect_uri=redirect_uri
    )
    claims = result.get("id_token_claims")
    if not claims:
        raise PermissionError(result.get("error_description", "Entra login failed"))
    email = (claims.get("preferred_username") or claims.get("email") or "").strip()
    name = (claims.get("name") or email).strip()
    if not email:
        raise PermissionError("No email in the Microsoft token")

    account = tenancy_repo.get_account_by_email(session, email)
    if account is None:
        if registration_repo.org_count(session) == 0:
            reg = registration_repo.register_first(
                session, get_settings().HIVE_ORG_NAME, name or email, email
            )
            return {"token": reg["token"], "name": name or email, "role": "org_admin"}
        raise PermissionError(
            f"{email} is niet geregistreerd — vraag een org_admin om een account/invite"
        )

    token = tenancy_repo.create_token(session, account["uid"], "entra-login", 30, role=account["role"])
    audit_repo.log(session, account["org_uid"], account["uid"], "login_entra", email)
    return {"token": token["token"], "name": account["name"], "role": account["role"]}
