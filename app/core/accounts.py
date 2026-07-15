"""Учётные записи площадок: метаданные в БД + секреты доступа по id аккаунта.

Одна площадка обслуживает несколько аккаунтов компании. Отображаемое имя
и площадка хранятся в БД, а креды доступа (токен, имя блога и т.п.) — в
защищённом хранилище с ключом по id аккаунта (см. core.secrets).
"""

from __future__ import annotations

import uuid
from typing import Optional

from ..platforms import get_adapter
from . import secrets
from .database import Database
from .logger import log_event
from .models import Account


class AccountService:
    def __init__(self, db: Database):
        self.db = db

    # ---------- метаданные ----------

    def list(self, platform: Optional[str] = None) -> list[Account]:
        return self.db.accounts(platform)

    def get(self, account_id: str) -> Optional[Account]:
        return self.db.get_account(account_id)

    def create(self, platform: str, name: str) -> Account:
        account = Account(id=uuid.uuid4().hex, platform=platform,
                          name=name.strip() or "Без названия")
        self.db.save_account(account)
        log_event("accounts", f"Добавлен аккаунт «{account.name}» ({platform})")
        return account

    def rename(self, account_id: str, name: str) -> None:
        account = self.db.get_account(account_id)
        if account:
            account.name = name.strip() or account.name
            self.db.save_account(account)

    def delete(self, account_id: str) -> None:
        account = self.db.get_account(account_id)
        if account is None:
            return
        for field in get_adapter(account.platform).credential_fields():
            secrets.delete_secret(secrets.account_secret(account_id, field.key))
        self.db.delete_account(account_id)
        log_event("accounts", f"Удалён аккаунт «{account.name}»")

    # ---------- секреты доступа ----------

    def set_credentials(self, account_id: str, values: dict[str, str]) -> None:
        for key, value in values.items():
            value = (value or "").strip()
            if value:
                secrets.set_secret(secrets.account_secret(account_id, key), value)

    def get_credential(self, account_id: str, key: str) -> Optional[str]:
        return secrets.get_secret(secrets.account_secret(account_id, key))

    def is_ready(self, account: Account) -> bool:
        """Все обязательные секреты аккаунта заданы — можно публиковать."""
        return get_adapter(account.platform).account_ready(account.id)
