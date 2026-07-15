"""Оболочка приложения: тайтлбар, сайдбар, навигация, оверлеи."""

from __future__ import annotations

import time

import flet as ft

from .. import APP_NAME, APP_VERSION
from . import components as ui
from . import theme as th
from .views import analytics, history
from .views.compose import ComposeView
from .views.login import LoginView
from .views.schedule import ScheduleView
from .views.settings import SettingsView

_NAV = (
    ("compose", "Создать пост", ft.Icons.EDIT_OUTLINED),
    ("schedule", "Расписание", ft.Icons.CALENDAR_TODAY_OUTLINED),
    ("history", "История", ft.Icons.HISTORY),
    ("analytics", "Аналитика", ft.Icons.SHOW_CHART),
    ("settings", "Настройки", ft.Icons.SETTINGS_OUTLINED),
)


class CenturioApp:
    def __init__(self, page: ft.Page, db, service, auth, accounts):
        self.page = page
        self.db = db
        self.service = service
        self.auth = auth
        self.accounts = accounts
        self.nav = "compose"
        self.compose = ComposeView(self)
        self._nav_items: dict[str, ft.Container] = {}
        self._badge_holder: ft.Container | None = None
        self.content_slot = ft.Container(expand=True)
        self.overlay_slot = ft.Container(visible=False, expand=True)

    # ---------- жизненный цикл ----------

    def mount(self) -> None:
        if self.auth.is_configured() and not getattr(self, "_logged_in", False):
            self._show_login()
        elif not self.auth.is_configured():
            self._show_login()
        else:
            self._show_main()

    def on_login(self) -> None:
        self._logged_in = True
        self._show_main()

    def _show_login(self) -> None:
        self.page.controls.clear()
        self.page.add(ft.Column([
            self._titlebar(),
            LoginView(self).build(),
        ], spacing=0, expand=True))
        self.page.update()

    def _show_main(self) -> None:
        main_area = ft.Stack([
            ft.Container(content=self.content_slot, bgcolor=th.BG_WINDOW,
                         expand=True),
            self.overlay_slot,
        ], expand=True)

        self.page.controls.clear()
        self.page.add(ft.Column([
            self._titlebar(),
            ft.Row([self._sidebar(), main_area], spacing=0, expand=True,
                   vertical_alignment=ft.CrossAxisAlignment.STRETCH),
        ], spacing=0, expand=True))
        self.page.on_keyboard_event = self._on_keyboard
        self.set_nav("compose", update=False)
        self.page.update()

    def _on_keyboard(self, e: ft.KeyboardEvent) -> None:
        """Ctrl/Cmd+Enter — публикация на экране создания поста."""
        if e.key == "Enter" and (e.ctrl or e.meta):
            if self.nav == "compose" and not self.overlay_slot.visible:
                self.compose._publish_clicked(None)

    # ---------- тайтлбар ----------

    def _titlebar(self) -> ft.Control:
        def win_btn(icon: str, on_click, size: int = 14,
                    danger: bool = False) -> ft.Container:
            btn = ft.Container(
                content=ft.Icon(icon, size=size, color=th.TEXT_DIM),
                padding=6, border_radius=6, on_click=on_click)

            def style(c, h):
                c.bgcolor = ((th.ERROR if danger else th.white(0.07))
                             if h else None)
                c.content.color = (th.ACCENT_FG if danger and h
                                   else th.TEXT_SOFT if h else th.TEXT_DIM)

            ui.hover_style(btn, style)
            return btn

        def minimize(_):
            self.page.window.minimized = True
            self.page.update()

        def maximize(_):
            self.page.window.maximized = not self.page.window.maximized
            self.page.update()

        bar = ft.Container(
            content=ft.Row([
                ft.Row([
                    ui.brand_dot(8),
                    ft.Text(APP_NAME, size=13, weight=ft.FontWeight.W_600,
                            color="#d6d6da"),
                    ft.Text("·", size=13, color="#4f4f55"),
                    ft.Text(f"v{APP_VERSION}", size=13, color=th.TEXT_GRAY2),
                ], spacing=10),
                ft.Row([
                    win_btn(ft.Icons.REMOVE, minimize),
                    win_btn(ft.Icons.CROP_SQUARE, maximize, size=12),
                    win_btn(ft.Icons.CLOSE, lambda e: self.page.window.close(),
                            danger=True),
                ], spacing=4),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            height=44, padding=ft.padding.symmetric(0, 12),
            bgcolor=th.BG_TITLEBAR,
            border=ft.border.only(bottom=ft.BorderSide(1, th.BORDER_SOFT)))
        return ft.WindowDragArea(content=bar)

    # ---------- сайдбар ----------

    def _sidebar(self) -> ft.Container:
        items: list[ft.Control] = []
        self._nav_items = {}
        for key, label, icon in _NAV:
            trailing: ft.Control | None = None
            if key == "schedule":
                self._badge_holder = ft.Container()
                trailing = self._badge_holder
            elif key == "analytics":
                trailing = ft.Container(
                    content=ft.Text("скоро", size=10, color=th.TEXT_FAINT,
                                    font_family=th.FONT_MONO),
                    border=ft.border.all(1, th.BORDER_DASHED),
                    padding=ft.padding.symmetric(2, 6), border_radius=6)

            row_children: list[ft.Control] = [
                ft.Icon(icon, size=17),
                ft.Text(label, size=14.5, weight=ft.FontWeight.W_500),
            ]
            if trailing is not None:
                row_children.append(ft.Container(expand=True))
                row_children.append(trailing)

            item = ft.Container(
                content=ft.Row(row_children, spacing=12),
                padding=ft.padding.symmetric(11, 12), border_radius=9,
                on_click=lambda e, k=key: self.set_nav(k))

            def nav_hover(e, k=key, it=item):
                if self.nav != k:
                    it.bgcolor = th.white(0.04) if e.data == "true" else None
                    try:
                        it.update()
                    except Exception:
                        pass

            item.on_hover = nav_hover
            self._nav_items[key] = item
            items.append(item)

        user_card = ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Text("А", size=14, weight=ft.FontWeight.W_700,
                                    color="#101012"),
                    width=34, height=34, border_radius=9, bgcolor=th.ACCENT,
                    alignment=ft.alignment.center),
                ft.Column([
                    ft.Text("Администратор", size=13.5, weight=ft.FontWeight.W_600),
                    ft.Text("Единственная роль", size=11.5, color=th.TEXT_LABEL),
                ], spacing=1),
            ], spacing=11),
            padding=ft.padding.symmetric(12, 10),
            border=ft.border.only(top=ft.BorderSide(1, th.BORDER_SOFT)))

        return ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ui.brand_dot(9),
                            ft.Text(APP_NAME, font_family=th.FONT_HEAD, size=20,
                                    weight=ft.FontWeight.W_600,
                                    style=ft.TextStyle(letter_spacing=-0.4)),
                        ], spacing=9),
                        ft.Container(
                            content=ft.Text(f"v{APP_VERSION}",
                                            font_family=th.FONT_MONO, size=11,
                                            color=th.TEXT_DIM),
                            margin=ft.margin.only(left=18, top=2)),
                    ], spacing=0),
                    padding=ft.padding.only(10, 0, 10, 22)),
                ft.Column(items, spacing=3),
                ft.Container(expand=True),
                user_card,
            ], spacing=0),
            width=236, bgcolor=th.BG_SIDEBAR,
            padding=ft.padding.symmetric(22, 14),
            border=ft.border.only(right=ft.BorderSide(1, th.BORDER_SOFT)))

    def refresh_sidebar(self, update: bool = True) -> None:
        """Обновляет счётчик запланированных постов в сайдбаре."""
        if self._badge_holder is None:
            return
        count = len(self.db.scheduled_posts())
        self._badge_holder.content = (ft.Container(
            content=ft.Text(str(count), size=11, font_family=th.FONT_MONO,
                            color=th.TEXT_MUTED),
            bgcolor=th.white(0.1), border_radius=6,
            padding=ft.padding.symmetric(2, 7)) if count else None)
        if update and self.page:
            try:
                self.page.update()
            except Exception:
                pass

    # ---------- навигация ----------

    def set_nav(self, key: str, update: bool = True) -> None:
        self.nav = key
        for k, item in self._nav_items.items():
            active = k == key
            item.bgcolor = th.white(0.09) if active else None
            row = item.content
            row.controls[0].color = th.TEXT if active else th.TEXT_GRAY
            row.controls[1].color = th.TEXT if active else th.TEXT_GRAY

        if key == "compose":
            self.content_slot.content = self.compose.build()
        elif key == "schedule":
            self.content_slot.content = ScheduleView(self).build()
        elif key == "history":
            self.content_slot.content = history.build(self)
        elif key == "analytics":
            self.content_slot.content = analytics.build(self)
        elif key == "settings":
            self.content_slot.content = SettingsView(self).build()

        self.refresh_sidebar(update=False)
        if update:
            self.page.update()

    # ---------- оверлеи и уведомления ----------

    def show_overlay(self, control: ft.Control) -> None:
        wrapper = ft.Container(
            content=control, expand=True, opacity=0,
            animate_opacity=ft.Animation(180, ft.AnimationCurve.EASE_OUT))
        self.overlay_slot.content = wrapper
        self.overlay_slot.visible = True
        self.page.update()

        def reveal():
            time.sleep(0.05)
            wrapper.opacity = 1
            try:
                self.page.update()
            except Exception:
                pass

        self.page.run_thread(reveal)

    def hide_overlay(self, update: bool = True) -> None:
        self.overlay_slot.visible = False
        self.overlay_slot.content = None
        if update:
            self.page.update()

    def snack(self, message: str) -> None:
        self.page.open(ft.SnackBar(
            content=ft.Text(message, color=th.TEXT, size=13.5),
            bgcolor=th.BG_DIALOG,
            behavior=ft.SnackBarBehavior.FLOATING,
            shape=ft.RoundedRectangleBorder(radius=12),
            width=420))
