from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet

from src.config import get_settings

# Persist an auto-generated vault key on the data volume so the hive can run with zero
# required secrets while staying decryptable across restarts.
_KEY_FILE = Path("/data/.hive_master_key")
_cached: str | None = None


def get_master_key() -> str:
    global _cached
    if _cached:
        return _cached
    configured = get_settings().SECRET_MASTER_KEY
    if configured:
        _cached = configured
        return _cached
    if _KEY_FILE.exists():
        _cached = _KEY_FILE.read_text().strip()
        return _cached
    key = Fernet.generate_key().decode()
    try:
        _KEY_FILE.write_text(key)
        _KEY_FILE.chmod(0o600)
    except OSError:
        pass  # non-writable /data (e.g. tests): fall back to an in-memory key
    _cached = key
    return _cached
