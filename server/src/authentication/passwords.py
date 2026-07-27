from __future__ import annotations

import hashlib
import secrets

# scrypt password hashing (stdlib) — salt$hash, both hex.
_N, _R, _P, _DKLEN = 16384, 8, 1, 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or "$" not in stored:
        return False
    salt_hex, hash_hex = stored.split("$", 1)
    try:
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                            n=_N, r=_R, p=_P, dklen=_DKLEN)
    except ValueError:
        return False
    return secrets.compare_digest(dk.hex(), hash_hex)
