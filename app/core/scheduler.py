"""Планировщик отложенных публикаций (APScheduler, фоновый поток).

Работает, пока запущено приложение. При старте восстанавливает задания
из БД; посты, чьё время прошло, пока приложение было закрыто,
публикуются сразу (misfire grace).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from .logger import log_event
from .models import Post
from .service import CrosspostService


class PostScheduler:
    def __init__(self, service: CrosspostService):
        self.service = service
        service.scheduler = self
        self._sched = BackgroundScheduler(daemon=True)

    def start(self) -> None:
        self._sched.start()
        restored = 0
        for post in self.service.db.scheduled_posts():
            self.add_post_job(post)
            restored += 1
        if restored:
            log_event("scheduler", f"Восстановлено заданий из БД: {restored}")

    def add_post_job(self, post: Post) -> None:
        when = post.scheduled_at or datetime.now()
        if when < datetime.now():
            when = datetime.now() + timedelta(seconds=3)
        self._sched.add_job(
            self.service.publish_scheduled,
            trigger=DateTrigger(run_date=when),
            args=[post.id],
            id=f"post-{post.id}",
            replace_existing=True,
            misfire_grace_time=3600,
        )

    def remove_post_job(self, post_id: int) -> None:
        try:
            self._sched.remove_job(f"post-{post_id}")
        except Exception:
            pass

    def shutdown(self) -> None:
        try:
            self._sched.shutdown(wait=False)
        except Exception:
            pass
