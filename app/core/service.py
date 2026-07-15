"""Модуль-ядро: логика поста, публикация по аккаунтам, отложенный постинг.

Ключевое требование надёжности: публикация идёт независимо по каждому
аккаунту выбранной площадки — ошибка одного не прерывает остальные
(отдельный поток на аккаунт).
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Callable, Optional

from ..platforms import get_adapter
from .database import Database
from .logger import log_event
from .models import Account, Post, PostStatus, PublicationStatus

ProgressFn = Callable[[str, str, str], None]


class CrosspostService:
    def __init__(self, db: Database):
        self.db = db
        self.scheduler = None

    def _post_accounts(self, post: Post) -> list[Account]:
        """Аккаунты поста в порядке выбора (пропуская удалённые)."""
        resolved = (self.db.get_account(a) for a in post.accounts)
        return [a for a in resolved if a is not None]

    def publish_now(self, post: Post, on_progress: Optional[ProgressFn] = None) -> None:
        """Публикует пост во все выбранные аккаунты параллельно (блокирующий вызов)."""
        post.status = PostStatus.PUBLISHED
        self.db.save_post(post)
        accounts = self._post_accounts(post)
        pub_ids = {
            a.id: self.db.add_publication(post.id, post.platform, a.id, a.name)
            for a in accounts
        }

        threads = [
            threading.Thread(
                target=self._publish_one,
                args=(post, account, pub_ids[account.id], on_progress),
                daemon=True,
            )
            for account in accounts
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self._finalize_post_status(post.id)

    def retry_account(self, post_id: int, account_id: str,
                      on_progress: Optional[ProgressFn] = None) -> None:
        """Повторная попытка публикации в один аккаунт."""
        post = self.db.get_post(post_id)
        account = self.db.get_account(account_id)
        if post is None or account is None:
            return
        pub = next((p for p in self.db.publications_for_post(post_id)
                    if p.account_id == account_id), None)
        pub_id = (pub.id if pub else
                  self.db.add_publication(post_id, post.platform,
                                          account.id, account.name))
        self._publish_one(post, account, pub_id, on_progress, retry=True)
        self._finalize_post_status(post_id)

    def _publish_one(self, post: Post, account: Account, pub_id: int,
                     on_progress: Optional[ProgressFn], retry: bool = False) -> None:
        adapter = get_adapter(post.platform)
        self.db.update_publication(pub_id, PublicationStatus.PUBLISHING,
                                   bump_attempts=True)
        if on_progress:
            on_progress(account.id, PublicationStatus.PUBLISHING, "")
        log_event("service", f"Публикация поста #{post.id} в {adapter.name} · "
                             f"{account.name}" + (" (повтор)" if retry else ""))
        result = adapter.publish(post, account)
        if result.ok:
            self.db.update_publication(pub_id, PublicationStatus.SUCCESS,
                                       external_url=result.external_url)
            if on_progress:
                on_progress(account.id, PublicationStatus.SUCCESS, "")
        else:
            self.db.update_publication(pub_id, PublicationStatus.ERROR,
                                       error=result.error)
            log_event("service", f"Ошибка {adapter.name} · {account.name}: "
                                 f"{result.error}", "ERROR")
            if on_progress:
                on_progress(account.id, PublicationStatus.ERROR, result.error)

    def _finalize_post_status(self, post_id: int) -> None:
        pubs = self.db.publications_for_post(post_id)
        if not pubs:
            return
        oks = [p for p in pubs if p.status == PublicationStatus.SUCCESS]
        if len(oks) == len(pubs):
            status = PostStatus.PUBLISHED
        elif oks:
            status = PostStatus.PARTIAL
        else:
            status = PostStatus.ERROR
        self.db.set_post_status(post_id, status)

    def schedule_post(self, post: Post, when: datetime) -> Post:
        post.status = PostStatus.SCHEDULED
        post.scheduled_at = when
        self.db.save_post(post)
        if self.scheduler:
            self.scheduler.add_post_job(post)
        log_event("service", f"Пост #{post.id} запланирован на {when:%d.%m.%Y %H:%M}")
        return post

    def reschedule_post(self, post_id: int, when: datetime) -> None:
        post = self.db.get_post(post_id)
        if post is None or post.status != PostStatus.SCHEDULED:
            return
        post.scheduled_at = when
        self.db.save_post(post)
        if self.scheduler:
            self.scheduler.add_post_job(post)
        log_event("service", f"Пост #{post_id} перенесён на {when:%d.%m.%Y %H:%M}")

    def cancel_scheduled(self, post_id: int) -> None:
        self.db.set_post_status(post_id, PostStatus.CANCELLED)
        if self.scheduler:
            self.scheduler.remove_post_job(post_id)
        log_event("service", f"Запланированный пост #{post_id} отменён")

    def publish_scheduled(self, post_id: int) -> None:
        """Вызывается планировщиком в назначенное время."""
        post = self.db.get_post(post_id)
        if post is None or post.status != PostStatus.SCHEDULED:
            return
        log_event("scheduler", f"Наступило время публикации поста #{post_id}")
        self.publish_now(post)

    def save_draft(self, post: Post) -> Post:
        post.status = PostStatus.DRAFT
        return self.db.save_post(post)
