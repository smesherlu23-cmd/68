"""Single-user авторизация: логин/пароль, хэш с солью в настройках БД."""

from __future__ import annotations

import hashlib
import secrets as pysecrets

from .database import Database

_KEY_LOGIN = "auth.login"
_KEY_HASH = "auth.hash"
_KEY_SALT = "auth.salt"


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    ).hex()


class Auth:
    def __init__(self, db: Database):
        self.db = db

    def is_configured(self) -> bool:
        return bool(self.db.get_setting(_KEY_HASH))

    def setup(self, login: str, password: str) -> None:
        salt = pysecrets.token_hex(16)
        self.db.set_setting(_KEY_LOGIN, login.strip())
        self.db.set_setting(_KEY_SALT, salt)
        self.db.set_setting(_KEY_HASH, _hash(password, salt))

    def verify(self, login: str, password: str) -> bool:
        if not self.is_configured():
            return False
        salt = self.db.get_setting(_KEY_SALT)
        return (login.strip() == self.db.get_setting(_KEY_LOGIN)
                and pysecrets.compare_digest(_hash(password, salt),
                                             self.db.get_setting(_KEY_HASH)))

    def change_password(self, old_password: str, new_password: str) -> bool:
        login = self.db.get_setting(_KEY_LOGIN)
        if not self.verify(login, old_password):
            return False
        self.setup(login, new_password)
        return True

    def login_name(self) -> str:
        return self.db.get_setting(_KEY_LOGIN, "admin")
