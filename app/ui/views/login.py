"""Экран авторизации: single-user логин/пароль (первый запуск — создание доступа)."""

from __future__ import annotations

import flet as ft

from ... import APP_VERSION
from ...core.logger import log_event
from .. import components as ui
from .. import theme as th


class LoginView:
    def __init__(self, app):
        self.app = app

    def build(self) -> ft.Control:
        first_run = not self.app.auth.is_configured()

        self.f_login = ui.text_field("Логин", size=14.5,
                                     value="" if first_run else self.app.auth.login_name())
        self.f_password = ui.text_field("Пароль", password=True, size=14.5)
        self.f_confirm = ui.text_field("Повторите пароль", password=True, size=14.5)
        self.f_confirm.visible = first_run
        self.error = ft.Text("", size=12.5, color=th.ERROR_TEXT, visible=False)
        for f in (self.f_login, self.f_password, self.f_confirm):
            f.on_submit = self._submit

        title = "Создайте доступ" if first_run else "Вход"
        sub = ("Первый запуск: задайте логин и пароль администратора"
               if first_run else "Единственный пользователь · Администратор")
        action = "Создать и войти" if first_run else "Войти"

        card = ft.Container(
            content=ft.Column([
                ft.Row([
                    ui.brand_dot(9),
                    ft.Text("Centurio", font_family=th.FONT_HEAD, size=24,
                            weight=ft.FontWeight.W_600,
                            style=ft.TextStyle(letter_spacing=-0.4)),
                ], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
                ft.Text(f"МУЛЬТИАККАУНТНЫЙ ПОСТИНГ · V{APP_VERSION}",
                        font_family=th.FONT_MONO,
                        size=10.5, color=th.TEXT_DIM,
                        text_align=ft.TextAlign.CENTER,
                        style=ft.TextStyle(letter_spacing=1.2)),
                ft.Container(height=10),
                ft.Text(title, font_family=th.FONT_HEAD, size=18,
                        weight=ft.FontWeight.W_600,
                        style=ft.TextStyle(letter_spacing=-0.3)),
                ft.Text(sub, size=12.5, color=th.TEXT_FAINT),
                ft.Container(height=4),
                self.f_login,
                self.f_password,
                self.f_confirm,
                self.error,
                ft.Container(height=4),
                ui.light_button(action, self._submit,
                                padding=ft.padding.symmetric(13, 26)),
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                tight=True),
            width=380, bgcolor=th.BG_CARD_PLATFORM,
            border=ft.border.all(1, th.BORDER_CARD), border_radius=18,
            padding=ft.padding.symmetric(34, 34),
            shadow=ui.card_shadow(0.5))

        return ft.Container(
            content=card, alignment=ft.alignment.center, expand=True,
            gradient=ft.RadialGradient(center=ft.alignment.center, radius=1.1,
                                       colors=["#17171b", th.BG_WINDOW]))

    def _submit(self, _) -> None:
        auth = self.app.auth
        login = (self.f_login.value or "").strip()
        password = self.f_password.value or ""

        if not auth.is_configured():
            if not login or len(password) < 4:
                self._fail("Укажите логин и пароль не короче 4 символов")
                return
            if password != (self.f_confirm.value or ""):
                self._fail("Пароли не совпадают")
                return
            auth.setup(login, password)
            log_event("auth", f"Создан доступ администратора «{login}»")
        elif not auth.verify(login, password):
            self._fail("Неверный логин или пароль")
            log_event("auth", "Неудачная попытка входа", "WARNING")
            return

        log_event("auth", "Вход выполнен")
        self.app.on_login()

    def _fail(self, message: str) -> None:
        self.error.value = message
        self.error.visible = True
        self.app.page.update()
