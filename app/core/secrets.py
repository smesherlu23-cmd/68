"""Хранение секретов (API-ключей платформ).

Основной путь — системное хранилище учётных данных ОС через keyring
(Windows Credential Manager, macOS Keychain, Secret Service в Linux).
Если keyring недоступен (например, headless-окружение), используется
локальный файл с обфускацией XOR+base64 и правами 0600 — секреты
не лежат в открытом виде ни в коде, ни в БД.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from pathlib import Path
from typing import Optional

from .paths import data_dir

_SERVICE = "CenturioCrosspost"
_FALLBACK_FILE = data_dir() / ".secrets.json"

try:
    import keyring
    from keyring.errors import KeyringError

    try:
        keyring.get_password(_SERVICE, "__probe__")
        _KEYRING_OK = True
    except BaseException:  # noqa: BLE001
        _KEYRING_OK = False
except ImportError:
    keyring = None
    _KEYRING_OK = False


def keyring_available() -> bool:
    return _KEYRING_OK


def account_secret(account_id: str, key: str) -> str:
    """Имя секрета учётной записи: креды аккаунта хранятся отдельно по его id."""
    return f"acct:{account_id}:{key}"


def _machine_key() -> bytes:
    return uuid.UUID(int=uuid.getnode()).bytes + b"centurio-local-secret"


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _read_fallback() -> dict:
    if not _FALLBACK_FILE.exists():
        return {}
    try:
        raw = base64.b64decode(_FALLBACK_FILE.read_bytes())
        return json.loads(_xor(raw, _machine_key()).decode("utf-8"))
    except Exception:
        return {}


def _write_fallback(data: dict) -> None:
    raw = _xor(json.dumps(data, ensure_ascii=False).encode("utf-8"), _machine_key())
    _FALLBACK_FILE.write_bytes(base64.b64encode(raw))
    try:
        os.chmod(_FALLBACK_FILE, 0o600)
    except OSError:
        pass


def set_secret(name: str, value: str) -> None:
    if _KEYRING_OK:
        try:
            keyring.set_password(_SERVICE, name, value)
            return
        except KeyringError:
            pass
    data = _read_fallback()
    data[name] = value
    _write_fallback(data)


def get_secret(name: str) -> Optional[str]:
    if _KEYRING_OK:
        try:
            value = keyring.get_password(_SERVICE, name)
            if value is not None:
                return value
        except KeyringError:
            pass
    return _read_fallback().get(name)


def delete_secret(name: str) -> None:
    if _KEYRING_OK:
        try:
            keyring.delete_password(_SERVICE, name)
        except Exception:
            pass
    data = _read_fallback()
    if name in data:
        del data[name]
        _write_fallback(data)
