from __future__ import annotations

from cryptography.fernet import Fernet
from neo4j import Session

from src.authentication.deps import AuthedAccount
from src.config import get_settings
from src.repository import audit_repo, vault_repo


def _fernet() -> Fernet:
    key = get_settings().SECRET_MASTER_KEY
    if not key:
        raise RuntimeError("Vault disabled: SECRET_MASTER_KEY is not configured")
    return Fernet(key.encode())


def set_secret(session: Session, account: AuthedAccount, name: str, value: str) -> dict:
    ciphertext = _fernet().encrypt(value.encode()).decode()
    result = vault_repo.set_secret(session, account, name, ciphertext)
    audit_repo.log(session, account.org_uid, account.uid, "secret_set", name)
    return result


def get_secret(session: Session, account: AuthedAccount, name: str) -> str | None:
    """Every read is audited. Values are meant for env injection, never chat context."""
    ciphertext = vault_repo.get_secret(session, account, name)
    audit_repo.log(
        session, account.org_uid, account.uid, "secret_get", name,
        {"granted": ciphertext is not None},
    )
    if ciphertext is None:
        return None
    return _fernet().decrypt(ciphertext.encode()).decode()
