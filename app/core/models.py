"""Модели данных ядра: пост, аккаунт и публикация не зависят от платформы."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


class PostStatus:
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    PARTIAL = "partial"       # опубликован не во всех аккаунтах
    ERROR = "error"
    CANCELLED = "cancelled"


class PublicationStatus:
    QUEUE = "queue"
    PUBLISHING = "publishing"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class Account:
    """Аккаунт компании на конкретной площадке.

    Метаданные (имя, площадка) лежат в БД, а секреты доступа (токен, имя
    блога и т.п.) — в защищённом хранилище с ключом по id аккаунта.
    """

    id: str = ""               # уникальный идентификатор (uuid4 hex)
    platform: str = ""         # "pinterest" | "boosty"
    name: str = ""             # отображаемое имя, напр. «Основной бренд»
    created_at: Optional[datetime] = None


@dataclass
class Post:
    """Единица контента: создаётся один раз и уходит в несколько аккаунтов
    одной выбранной площадки."""

    id: Optional[int] = None
    title: str = ""
    text: str = ""
    link: str = ""             # целевой URL пина (Pinterest)
    board: str = ""            # доска Pinterest
    media: list[str] = field(default_factory=list)  # пути к файлам медиа
    platform: str = ""         # выбранная площадка публикации
    accounts: list[str] = field(default_factory=list)  # id выбранных аккаунтов
    status: str = PostStatus.DRAFT
    created_at: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None

    def text_for(self, platform: str) -> str:
        return self.text

    def media_json(self) -> str:
        return json.dumps(self.media, ensure_ascii=False)

    def accounts_json(self) -> str:
        return json.dumps(self.accounts, ensure_ascii=False)


@dataclass
class Publication:
    """Результат публикации поста в конкретный аккаунт площадки."""

    id: Optional[int] = None
    post_id: int = 0
    post_title: str = ""
    platform: str = ""
    account_id: str = ""
    account_name: str = ""
    status: str = PublicationStatus.QUEUE
    published_at: Optional[datetime] = None
    error: str = ""
    external_url: str = ""
    attempts: int = 0
