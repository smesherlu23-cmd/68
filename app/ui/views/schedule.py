"""Экран «Расписание»: запланированные публикации, перенос и отмена."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import flet as ft

from ...core.models import Post
from ...platforms import get_adapter
from .. import components as ui
from .. import format as fmt
from .. import theme as th


class ScheduleView:
    def __init__(self, app):
        self.app = app
        self._edit_post: Post | None = None
        self._new_date = None
        self._new_time = None

    def build(self) -> ft.Control:
        posts = self.app.db.scheduled_posts()
        body: list[ft.Control] = []
        current_day = None
        for post in posts:
            day = post.scheduled_at.date()
            if day != current_day:
                current_day = day
                body.append(ft.Container(
                    content=ui.mono_label(fmt.day_label(post.scheduled_at)),
                    margin=ft.margin.only(top=14 if len(body) else 0)))
            body.append(self._row(post))

        if not posts:
            body = [ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.CALENDAR_TODAY_OUTLINED, size=30,
                            color=th.TEXT_DIM),
                    ft.Text("Запланированных публикаций нет", size=15,
                            weight=ft.FontWeight.W_600, color=th.TEXT_GRAY),
                    ft.Text("Включите «Отложить» при создании поста",
                            size=13, color=th.TEXT_LABEL),
                ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                alignment=ft.alignment.center, expand=True)]

        return ft.Column([
            ui.page_header("Расписание",
                           "Запланированные публикации · фоновый планировщик активен"),
            ft.Container(
                content=ft.Column(body, spacing=12, scroll=ft.ScrollMode.AUTO,
                                  expand=True),
                padding=ft.padding.symmetric(24, 30), expand=True),
        ], spacing=0, expand=True)

    def _row(self, post: Post) -> ft.Container:
        names = [a.name for a in
                 (self.app.db.get_account(i) for i in post.accounts) if a]
        platform_name = get_adapter(post.platform).name if post.platform else "—"
        if names:
            targets = f"{platform_name} · " + ", ".join(names)
        else:
            targets = platform_name
        cancel_btn = ft.Container(
            content=ft.Text("Отменить", size=12, color=th.TEXT_GRAY2),
            padding=ft.padding.symmetric(5, 6),
            on_click=lambda e, p=post: self._cancel(p))
        ui.hover_style(cancel_btn, lambda c, h: setattr(
            c.content, "color", th.ERROR_TEXT if h else th.TEXT_GRAY2))

        row = ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Text(post.scheduled_at.strftime("%H:%M"),
                                    font_family=th.FONT_MONO, size=14,
                                    color=th.ACCENT),
                    width=50),
                ft.Column([
                    ft.Text(post.title or "Без названия", size=15,
                            weight=ft.FontWeight.W_600, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(targets, size=12.5, color=th.TEXT_FAINT, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS),
                ], spacing=3, expand=True),
                ui.chip_button("Изменить", lambda e, p=post: self._edit(p)),
                cancel_btn,
            ], spacing=18),
            bgcolor=th.BG_CARD, border=ft.border.all(1, th.BORDER_CARD),
            border_radius=12, padding=ft.padding.symmetric(16, 20))
        ui.hover_style(row, lambda c, h: setattr(
            c, "border", ft.border.all(1, th.white(0.14 if h else 0.08))))
        return row

    def _edit(self, post: Post) -> None:
        self._edit_post = post
        self._new_date = post.scheduled_at.date()
        self._new_time = post.scheduled_at.time()
        picker = ft.DatePicker(
            value=post.scheduled_at, first_date=datetime.now(),
            last_date=datetime.now() + timedelta(days=365),
            on_change=self._date_chosen)
        self.app.page.open(picker)

    def _date_chosen(self, e) -> None:
        if not e.control.value:
            return
        self._new_date = e.control.value.date()
        picker = ft.TimePicker(value=self._new_time, on_change=self._time_chosen)
        self.app.page.open(picker)

    def _time_chosen(self, e) -> None:
        if not e.control.value or self._edit_post is None:
            return
        self._new_time = e.control.value
        when = datetime.combine(self._new_date, self._new_time)
        if when <= datetime.now():
            when = datetime.now() + timedelta(minutes=1)
        self.app.service.reschedule_post(self._edit_post.id, when)
        self.app.snack(f"Публикация перенесена на {fmt.human_datetime(when)}")
        self.app.set_nav("schedule")

    def _cancel(self, post: Post) -> None:
        self.app.service.cancel_scheduled(post.id)
        self.app.snack("Публикация отменена")
        self.app.set_nav("schedule")
