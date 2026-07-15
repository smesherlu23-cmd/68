"""Единый интерфейс адаптера платформы: publish, preview, validate.

Публикация выполняется в конкретный аккаунт компании: креды доступа
(токен, имя блога и т.п.) хранятся отдельно по id аккаунта — площадка
может обслуживать несколько независимых аккаунтов одновременно.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..core.models import Account, Post


@dataclass
class PublishResult:
    ok: bool
    external_url: str = ""
    error: str = ""


@dataclass
class CredentialField:
    """Описание одного секрета аккаунта (для формы подключения в настройках)."""
    key: str
    label: str
    password: bool = False
    hint: str = ""
    auto_managed: bool = False
    optional: bool = False
    advanced: bool = False


@dataclass
class PreviewData:
    """Данные для отрисовки предпросмотра поста на площадке."""
    title: str = ""
    text: str = ""
    link_domain: str = ""
    board: str = ""
    media: list[str] = field(default_factory=list)


class PlatformAdapter(ABC):
    key: str = ""
    name: str = ""
    letter: str = ""

    def credential_fields(self) -> list[CredentialField]:
        """Секреты, которые нужно задать для аккаунта этой площадки."""
        return []

    @abstractmethod
    def validate(self, post: Post) -> list[str]:
        """Возвращает список недостающих полей (пустой список — пост валиден)."""

    @abstractmethod
    def publish(self, post: Post, account: Account) -> PublishResult:
        """Публикует пост в аккаунт; не бросает исключение — ошибки в PublishResult."""

    def preview(self, post: Post) -> PreviewData:
        text = post.text_for(self.key)
        domain = post.link.replace("https://", "").replace("http://", "").split("/")[0]
        return PreviewData(title=post.title, text=text, link_domain=domain,
                           board=post.board, media=list(post.media))

    def account_ready(self, account_id: str) -> bool:
        """Все обязательные секреты аккаунта заданы — можно публиковать.
        Поля auto_managed/optional заполняются или выводятся автоматически и
        в проверку готовности не входят."""
        from ..core import secrets
        return all(secrets.get_secret(secrets.account_secret(account_id, f.key))
                   for f in self.credential_fields()
                   if not f.auto_managed and not f.optional)
