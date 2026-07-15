"""Экран «Настройки»: аккаунты площадок, хранение ключей, доступ."""

from __future__ import annotations

import flet as ft

from ...core import secrets
from ...core.logger import log_event, log_file_path
from ...platforms import all_adapters, get_adapter
from .. import components as ui
from .. import theme as th


class SettingsView:
    def __init__(self, app):
        self.app = app

    def build(self) -> ft.Control:
        cards: list[ft.Control] = []
        for adapter in all_adapters():
            cards.append(ft.Container(
                content=ui.mono_label(f"Аккаунты · {adapter.name}"),
                margin=ft.margin.only(top=14 if cards else 0)))
            accounts = self.app.accounts.list(adapter.key)
            for account in accounts:
                cards.append(self._account_card(adapter, account))
            stub = ui.dashed_stub(f"＋ Добавить аккаунт {adapter.name}")
            stub.on_click = lambda e, a=adapter: self._account_dialog(a)
            cards.append(stub)

        cards += [
            ft.Container(content=ui.mono_label("Доступ"),
                         margin=ft.margin.only(top=14)),
            self._auth_card(),
            ft.Container(content=ui.mono_label("Журнал"),
                         margin=ft.margin.only(top=14)),
            self._log_card(),
        ]

        return ft.Column([
            ui.page_header("Настройки",
                           "Аккаунты компании по площадкам и хранение ключей"),
            ft.Container(
                content=ft.Column(cards, spacing=16, scroll=ft.ScrollMode.AUTO,
                                  expand=True),
                padding=ft.padding.symmetric(26, 30), expand=True, width=820),
        ], spacing=0, expand=True)

    def _account_card(self, adapter, account) -> ft.Container:
        ready = self.app.accounts.is_ready(account)
        status = (ui.status_dot(th.SUCCESS, "Ключи заданы", th.SUCCESS_TEXT)
                  if ready else
                  ui.status_dot(th.TEXT_GHOST, "Ключи не заданы", th.TEXT_DIM))
        buttons = [
            ui.chip_button("Ключи и имя",
                           lambda e, a=adapter, ac=account: self._account_dialog(a, ac)),
        ]
        if adapter.key == "boosty" and adapter.auto_login_configured(account.id):
            buttons.append(ui.chip_button(
                "Войти автоматически",
                lambda e, ac=account: self._boosty_auto_login(ac)))
        buttons.append(ui.chip_button("Удалить",
                                      lambda e, ac=account: self._confirm_delete(ac)))
        return ft.Container(
            content=ft.Row([
                ui.platform_letter(account.name[:1].upper() or "?", size=40, radius=11),
                ft.Column([
                    ft.Text(account.name, size=15, weight=ft.FontWeight.W_600),
                    status,
                ], spacing=3, expand=True),
                *buttons,
            ], spacing=16),
            bgcolor=th.BG_CARD, border=ft.border.all(1, th.BORDER_CARD),
            border_radius=12, padding=ft.padding.symmetric(18, 20))

    def _boosty_auto_login(self, account) -> None:
        """Запускает автовход Boosty (форма + email-2FA) в фоновом потоке."""
        self.app.snack("Выполняется вход в Boosty и проверка почты за кодом…")

        def work() -> None:
            ok, message = get_adapter("boosty").auto_login(account.id)
            self.app.snack(message)
            if ok:
                self.app.set_nav("settings")

        self.app.page.run_thread(work)

    def _auth_card(self) -> ft.Container:
        return ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text("Авторизация", size=15, weight=ft.FontWeight.W_600),
                    ft.Text("Логин / пароль · единственный пользователь (Администратор)",
                            size=12.5, color=th.TEXT_FAINT),
                ], spacing=2, expand=True),
                ui.chip_button("Сменить пароль", lambda e: self._password_dialog()),
            ], spacing=16),
            bgcolor=th.BG_CARD, border=ft.border.all(1, th.BORDER_CARD),
            border_radius=12, padding=ft.padding.symmetric(18, 20))

    def _log_card(self) -> ft.Container:
        return ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text("Журнал технических событий", size=15,
                            weight=ft.FontWeight.W_600),
                    ft.Text(str(log_file_path()), size=12.5, color=th.TEXT_FAINT,
                            font_family=th.FONT_MONO),
                ], spacing=2, expand=True),
            ], spacing=16),
            bgcolor=th.BG_CARD, border=ft.border.all(1, th.BORDER_CARD),
            border_radius=12, padding=ft.padding.symmetric(18, 20))

    @staticmethod
    def _derive_name(values: dict[str, str]) -> str:
        """Имя по умолчанию, если поле пустое: из email (часть до @) или блога."""
        email = values.get("login_email", "")
        if email:
            return email.split("@", 1)[0]
        return values.get("blog", "")

    def _account_dialog(self, adapter, account=None) -> None:
        editing = account is not None
        storage_note = ("Ключи сохранятся в защищённом хранилище ОС"
                        if secrets.keyring_available()
                        else "Ключи сохранятся в зашифрованном локальном файле")

        name_field = ui.text_field("Имя аккаунта · можно оставить пустым",
                                   value=account.name if editing else "", size=13.5)
        cred_inputs: dict[str, ft.TextField] = {}

        def make_input(field) -> ft.TextField:
            existing = (self.app.accounts.get_credential(account.id, field.key)
                        if editing else None)
            if field.password and existing:
                hint = "Оставьте пустым, чтобы не менять"
            elif field.hint:
                hint = f"{field.label} · {field.hint}"
            else:
                hint = field.label
            inp = ui.text_field(
                hint, value="" if field.password else (existing or ""),
                password=field.password, size=13.5)
            cred_inputs[field.key] = inp
            return inp

        visible = [f for f in adapter.credential_fields() if not f.auto_managed]
        fields: list[ft.Control] = [name_field]
        fields += [make_input(f) for f in visible if not f.advanced]

        adv_fields = [f for f in visible if f.advanced]
        if adv_fields:
            adv_box = ft.Column([make_input(f) for f in adv_fields], spacing=12,
                                tight=True, visible=False)
            toggle = ui.text_link("Дополнительно · обычно определяется само",
                                  icon=ft.Icons.KEYBOARD_ARROW_RIGHT)

            def toggle_adv(_e, box=adv_box, link=toggle):
                box.visible = not box.visible
                link.content.controls[0].name = (
                    ft.Icons.KEYBOARD_ARROW_DOWN if box.visible
                    else ft.Icons.KEYBOARD_ARROW_RIGHT)
                self.app.page.update()

            toggle.on_click = toggle_adv
            fields += [ft.Container(content=toggle, margin=ft.margin.only(top=2)),
                       adv_box]
        fields.append(ft.Text(storage_note, size=11.5, color=th.TEXT_DIM))

        def save(_):
            values = {k: (inp.value or "").strip()
                      for k, inp in cred_inputs.items() if (inp.value or "").strip()}
            name = (name_field.value or "").strip() or self._derive_name(values)
            if not name:
                self.app.snack("Укажите имя аккаунта")
                return
            if editing:
                self.app.accounts.rename(account.id, name)
                target = account
            else:
                target = self.app.accounts.create(adapter.key, name)
            if values:
                self.app.accounts.set_credentials(target.id, values)
            log_event("settings",
                      f"Аккаунт {adapter.name} · {name} " +
                      ("обновлён" if editing else "добавлен"))
            self.app.page.close(dialog)
            self.app.snack(f"{adapter.name} · {name}: сохранено")
            self.app.set_nav("settings")

        title = (f"Аккаунт · {adapter.name}" if editing
                 else f"Новый аккаунт · {adapter.name}")
        dialog = self._dialog(title, fields, "Сохранить", save)
        self.app.page.open(dialog)

    def _confirm_delete(self, account) -> None:
        def do_delete(_):
            self.app.accounts.delete(account.id)
            self.app.page.close(dialog)
            self.app.snack(f"Аккаунт «{account.name}» удалён")
            self.app.set_nav("settings")

        dialog = ft.AlertDialog(
            modal=True, bgcolor=th.BG_DIALOG,
            shape=ft.RoundedRectangleBorder(radius=18),
            title=ft.Text("Удалить аккаунт?", font_family=th.FONT_HEAD, size=19,
                          weight=ft.FontWeight.W_600),
            content=ft.Container(
                content=ft.Text(
                    f"Аккаунт «{account.name}» и его ключи доступа будут удалены. "
                    "Опубликованные посты останутся в истории.",
                    size=13.5, color=th.TEXT_FAINT), width=380),
            actions=[
                ui.ghost_button("Отмена", lambda e: self.app.page.close(dialog),
                                padding=ft.padding.symmetric(10, 16)),
                ui.light_button("Удалить", do_delete,
                                padding=ft.padding.symmetric(10, 20)),
            ])
        self.app.page.open(dialog)

    def _password_dialog(self) -> None:
        old_f = ui.text_field("Текущий пароль", password=True, size=13.5)
        new_f = ui.text_field("Новый пароль", password=True, size=13.5)
        rep_f = ui.text_field("Повторите новый пароль", password=True, size=13.5)
        error = ft.Text("", size=12.5, color=th.ERROR_TEXT, visible=False)

        def save(_):
            if (new_f.value or "") != (rep_f.value or ""):
                error.value, error.visible = "Пароли не совпадают", True
                self.app.page.update()
                return
            if len(new_f.value or "") < 4:
                error.value, error.visible = "Минимум 4 символа", True
                self.app.page.update()
                return
            if not self.app.auth.change_password(old_f.value or "", new_f.value):
                error.value, error.visible = "Неверный текущий пароль", True
                self.app.page.update()
                return
            log_event("settings", "Пароль администратора изменён")
            self.app.page.close(dialog)
            self.app.snack("Пароль обновлён")

        dialog = self._dialog("Смена пароля", [old_f, new_f, rep_f, error],
                              "Сохранить", save)
        self.app.page.open(dialog)

    def _dialog(self, title: str, fields: list[ft.Control],
                action: str, on_save) -> ft.AlertDialog:
        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=th.BG_DIALOG,
            shape=ft.RoundedRectangleBorder(radius=18),
            title=ft.Text(title, font_family=th.FONT_HEAD, size=19,
                          weight=ft.FontWeight.W_600),
            content=ft.Container(
                content=ft.Column(fields, spacing=12, tight=True), width=380),
            actions=[
                ui.ghost_button("Отмена",
                                lambda e: self.app.page.close(dialog),
                                padding=ft.padding.symmetric(10, 16)),
                ui.light_button(action, on_save,
                                padding=ft.padding.symmetric(10, 20)),
            ],
        )
        return dialog
