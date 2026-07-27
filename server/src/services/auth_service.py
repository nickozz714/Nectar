from __future__ import annotations

from neo4j import Session

from src.authentication.deps import AuthedAccount, assert_role
from src.authentication.passwords import hash_password, verify_password
from src.repository import audit_repo, tenancy_repo

MIN_PASSWORD_LEN = 8


def set_own_password(session: Session, account: AuthedAccount, password: str) -> dict:
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"Wachtwoord moet minstens {MIN_PASSWORD_LEN} tekens zijn")
    tenancy_repo.set_password(session, account.uid, hash_password(password))
    audit_repo.log(session, account.org_uid, account.uid, "password_set", account.name)
    return {"ok": True, "name": account.name}


def set_password_for(
    session: Session, admin: AuthedAccount, target_name: str, password: str
) -> dict:
    """org_admin sets/resets a password for another account in their org."""
    assert_role(admin, "org_admin", "Setting passwords")
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"Wachtwoord moet minstens {MIN_PASSWORD_LEN} tekens zijn")
    if not tenancy_repo.set_password_by_name(session, admin.org_uid, target_name, hash_password(password)):
        raise ValueError(f"Geen account '{target_name}' in je org")
    audit_repo.log(session, admin.org_uid, admin.uid, "password_set_for", target_name)
    return {"ok": True, "name": target_name}


def login(session: Session, name: str, password: str) -> dict:
    """Verify username + password and mint a login token (30 days). All other endpoints
    keep using that token as the bearer, so password login is just a way to get a token."""
    account = tenancy_repo.get_account_for_login(session, name.strip())
    if account is None or not verify_password(password, account.get("password_hash")):
        raise PermissionError("Ongeldige gebruikersnaam of wachtwoord")
    token = tenancy_repo.create_token(
        session, account["uid"], "gui-login", 30, role=account["role"]
    )
    audit_repo.log(session, account["org_uid"], account["uid"], "login", name)
    return {"token": token["token"], "role": account["role"], "name": account["name"]}
