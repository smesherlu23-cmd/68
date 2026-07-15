"""Экран «Создать пост»: платформа → аккаунты → контент → публикация.

Сначала выбирается одна площадка, затем один или несколько аккаунтов
компании на этой площадке — пост уходит во все выбранные аккаунты
независимо (ошибка одного не прерывает остальные).
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta

import flet as ft

from ...core.models import Post, PublicationStatus
from ...platforms import all_adapters, get_adapter
from .. import components as ui
from .. import format as fmt
from .. import theme as th


class ComposeView:
    """Держит состояние формы; живёт, пока пользователь не сбросит форму."""

    def __init__(self, app):
        self.app = app
        adapters = all_adapters()
        self.platform = adapters[0].key if adapters else ""
        self.selected: set[str] = set()
        self.schedule_on = False
        self.media: list[str] = []
        self.sched_date: date = date.today() + timedelta(days=1)
        self.sched_time: time = time(9, 0)
        self._pub_state: dict[str, str] = {}
        self._pub_post: Post | None = None
        self._build_controls()
        self._select_all_ready(update=False)

    def _platform_accounts(self) -> list:
        return self.app.accounts.list(self.platform)

    def _is_ready(self, account) -> bool:
        return self.app.accounts.is_ready(account)

    def _ready_selected_ids(self) -> list[str]:
        return [a.id for a in self._platform_accounts()
                if a.id in self.selected and self._is_ready(a)]

    def _select_all_ready(self, update: bool = True) -> None:
        self.selected = {a.id for a in self._platform_accounts()
                         if self._is_ready(a)}
        if update:
            self.refresh()

    def current_post(self) -> Post:
        return Post(
            title=self.f_title.value or "",
            text=self.f_text.value or "",
            link=self.f_link.value or "",
            board=self.f_board.value or "",
            media=list(self.media),
            platform=self.platform,
            accounts=self._ready_selected_ids(),
        )

    def _validity(self) -> tuple[list[str], bool]:
        post = self.current_post()
        if not self.platform:
            return [], False
        missing = get_adapter(self.platform).validate(post)
        ok = bool(post.accounts) and not missing
        return missing, ok

    def _build_controls(self) -> None:
        on_change = lambda e: self.refresh()  # noqa: E731

        self.f_title = ui.text_field("Заголовок поста", size=16,
                                     weight=ft.FontWeight.W_600, on_change=on_change)
        self.f_text = ui.text_field("Текст / описание…", multiline=True,
                                    min_lines=4, on_change=on_change)
        self.title_counter = ft.Text("", size=11, color=th.TEXT_DIM,
                                     font_family=th.FONT_MONO)
        self.text_counter = ft.Text("", size=11, color=th.TEXT_DIM,
                                    font_family=th.FONT_MONO)

        self.picker = ft.FilePicker(on_result=self._media_picked)
        self.media_row = ft.Row(spacing=12, wrap=True, run_spacing=12)
        self.media_count = ft.Text("", size=12, color=th.TEXT_FAINT)
        self.media_clear = ui.text_link("Очистить всё", self._clear_media,
                                        icon=ft.Icons.CLOSE)
        self.media_clear.visible = False
        self.media_hint = ft.Row([
            ft.Icon(ft.Icons.INFO_OUTLINE, size=13, color=th.ERROR_TEXT),
            ft.Text("Pinterest требует изображение (JPG или PNG)",
                    size=12, color=th.ERROR_TEXT),
        ], spacing=6, tight=True, visible=False)

        self.f_link = ui.text_field("https://…", nested=True, mono=True,
                                    size=12.5, on_change=on_change)
        self.f_board = ui.text_field("Название доски", nested=True,
                                     size=12.5, on_change=on_change)

        self.platform_row = ft.Row(spacing=12, wrap=True, run_spacing=12)
        self.accounts_holder = ft.Column(spacing=10)
        self.accounts_summary = ft.Text("", size=12, color=th.TEXT_FAINT)
        self.pin_params = self._pin_params_card()
        self.preview_holder = ft.Container(alignment=ft.alignment.top_center)
        self.preview_platform_label = ui.mono_label("Предпросмотр")
        self.preview_targets = ft.Text("", size=12, color=th.TEXT_FAINT)

        self.tg_schedule = ui.PillToggle(False, self._toggle_schedule)
        self.date_btn = self._dt_field(self._pick_date, ft.Icons.CALENDAR_TODAY_OUTLINED)
        self.time_btn = self._dt_field(self._pick_time, ft.Icons.SCHEDULE)
        self.dt_row = ft.Row(spacing=8, visible=False)
        self.dt_row.controls = [
            self.date_btn, self.time_btn,
            ft.Container(width=1, height=20, bgcolor=th.BORDER_STRONG,
                         margin=ft.margin.symmetric(0, 2)),
            self._preset_chip("Через час", self._preset_hour),
            self._preset_chip("Завтра 09:00", self._preset_morning),
            self._preset_chip("Вечером 18:00", self._preset_evening),
        ]
        self.hint_text = ft.Text("", size=12.5, color=th.TEXT_FAINT)
        self.publish_btn = ft.Container(
            content=ft.Text("", size=14, weight=ft.FontWeight.W_700),
            padding=ft.padding.symmetric(12, 26), border_radius=10,
            on_click=self._publish_clicked, animate_opacity=120,
            tooltip="Ctrl+Enter")

        self.steps: list[tuple[ft.Container, ft.Text, ft.Text]] = []

    def _pin_params_card(self) -> ft.Container:
        return ft.Container(
            content=ft.Column([
                ui.mono_label("Параметры Pinterest"),
                ft.Row([
                    ft.Column([ft.Text("Ссылка пина", size=11, color=th.TEXT_LABEL),
                               self.f_link], spacing=6, expand=True),
                    ft.Column([ft.Text("Доска", size=11, color=th.TEXT_LABEL),
                               self.f_board], spacing=6, expand=True),
                ], spacing=12),
            ], spacing=12),
            bgcolor=th.BG_CARD_PLATFORM, border_radius=13,
            border=ft.border.all(1, th.BORDER_STRONG),
            padding=ft.padding.symmetric(15, 16))

    @staticmethod
    def _dt_field(on_click, icon: str) -> ft.Container:
        field = ft.Container(
            content=ft.Row([
                ft.Icon(icon, size=15, color=th.TEXT_FAINT),
                ft.Text("", size=13.5, color=th.TEXT_SOFT),
            ], spacing=8, tight=True),
            bgcolor=th.BG_CARD, border=ft.border.all(1, th.BORDER_INPUT),
            border_radius=9, padding=ft.padding.symmetric(9, 13),
            on_click=on_click)
        ui.hover_style(field, lambda c, h: setattr(
            c, "border", ft.border.all(1, th.white(0.28 if h else 0.09))))
        return field

    def _preset_chip(self, text: str, on_click) -> ft.Container:
        chip = ft.Container(
            content=ft.Text(text, size=12.5, color=th.TEXT_GRAY2),
            bgcolor=th.white(0.04), border_radius=8,
            padding=ft.padding.symmetric(8, 12),
            on_click=lambda e: on_click())

        def style(c, h):
            c.bgcolor = th.white(0.1 if h else 0.04)
            c.content.color = th.TEXT_SOFT if h else th.TEXT_GRAY2

        ui.hover_style(chip, style)
        return chip

    def build(self) -> ft.Control:
        if self.picker not in self.app.page.overlay:
            self.app.page.overlay.append(self.picker)

        root = ft.Column([
            self._header(),
            ft.Row([self._editor(), self._preview_panel()],
                   spacing=0, expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH),
            self._action_bar(),
        ], spacing=0, expand=True)
        self.refresh(update=False)
        return root

    def _header(self) -> ft.Container:
        self.steps = []
        items: list[ft.Control] = []
        for num, label in (("1", "Платформа"), ("2", "Аккаунты"), ("3", "Контент")):
            circle_text = ft.Text(num, size=11, weight=ft.FontWeight.W_700,
                                  font_family=th.FONT_MONO)
            circle = ft.Container(content=circle_text, width=22, height=22,
                                  border_radius=11, alignment=ft.alignment.center)
            caption = ft.Text(label, size=12.5, weight=ft.FontWeight.W_500)
            self.steps.append((circle, circle_text, caption))
            if items:
                items.append(ft.Container(width=26, height=1.5,
                                          bgcolor=th.BORDER_STRONG,
                                          margin=ft.margin.symmetric(0, 12)))
            items.append(ft.Row([circle, caption], spacing=9, tight=True))

        return ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text("Новый пост", font_family=th.FONT_HEAD, size=22,
                            weight=ft.FontWeight.W_600,
                            style=ft.TextStyle(letter_spacing=-0.4)),
                    ft.Text("Один контент — сразу в несколько аккаунтов площадки",
                            size=13, color=th.TEXT_FAINT),
                ], spacing=2),
                ft.Row(items, spacing=0, tight=True),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            padding=ft.padding.only(30, 20, 30, 18),
            border=ft.border.only(bottom=ft.BorderSide(1, th.BORDER_SOFT)),
        )

    def _editor(self) -> ft.Container:
        upload_box = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.UPLOAD_OUTLINED, size=20, color=th.TEXT_FAINT),
                ft.Text("Перетащите медиа или нажмите", size=12.5, color=th.TEXT_FAINT),
            ], spacing=5, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER),
            height=88, expand=True, border_radius=11,
            border=ft.border.all(1.5, th.BORDER_DASHED),
            on_click=lambda e: self.picker.pick_files(
                allow_multiple=True,
                allowed_extensions=["jpg", "jpeg", "png", "gif", "webp",
                                    "mp4", "mov", "webm", "mp3", "wav", "pdf", "zip"]),
            ink=True)

        def upload_hover(c, h):
            c.border = ft.border.all(1.5, th.white(0.32 if h else 0.15))
            for child in c.content.controls:
                child.color = "#a4a4aa" if h else th.TEXT_FAINT

        ui.hover_style(upload_box, upload_hover)

        platform_section = ft.Column([
            ui.mono_label("1 · Платформа"),
            self.platform_row,
        ], spacing=12)

        accounts_section = ft.Column([
            ft.Row([ui.mono_label("2 · Аккаунты"),
                    ft.Row([self.accounts_summary,
                            ui.text_link("Выбрать все", lambda e: self._select_all_ready())],
                           spacing=8, tight=True)],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            self.accounts_holder,
        ], spacing=12)

        title_block = ft.Column([
            self.f_title,
            ft.Row([self.title_counter], alignment=ft.MainAxisAlignment.END),
        ], spacing=5)
        text_block = ft.Column([
            self.f_text,
            ft.Row([self.text_counter], alignment=ft.MainAxisAlignment.END),
        ], spacing=5)
        media_header = ft.Row([
            ui.mono_label("Медиа"),
            ft.Row([self.media_count, self.media_clear], spacing=4, tight=True),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        content_section = ft.Column([
            ui.mono_label("3 · Контент"),
            title_block,
            text_block,
            media_header,
            ft.Column([self.media_row,
                       ft.Row([upload_box], spacing=12),
                       self.media_hint], spacing=12),
            self.pin_params,
        ], spacing=16)

        return ft.Container(
            content=ft.Column([platform_section, accounts_section, content_section],
                              spacing=26, scroll=ft.ScrollMode.AUTO),
            padding=ft.padding.symmetric(24, 28), expand=True)

    def _platform_card(self, adapter, active: bool) -> ft.Container:
        count = len(self.app.accounts.list(adapter.key))
        card = ft.Container(
            content=ft.Row([
                ui.platform_letter(adapter.letter),
                ft.Column([
                    ft.Text(adapter.name, size=14.5, weight=ft.FontWeight.W_600),
                    ft.Text(f"{count} {self._plural_accounts(count)}", size=12,
                            color=th.TEXT_FAINT),
                ], spacing=2),
            ], spacing=12, tight=True),
            padding=ft.padding.symmetric(12, 15), border_radius=12,
            bgcolor=th.white(0.06) if active else th.BG_CARD_PLATFORM,
            border=ft.border.all(1.5, th.ACCENT if active else th.BORDER_STRONG),
            on_click=lambda e, k=adapter.key: self._select_platform(k))
        if not active:
            ui.hover_style(card, lambda c, h: setattr(
                c, "border", ft.border.all(1.5, th.white(0.22 if h else 0.12))))
        return card

    def _account_row(self, account) -> ft.Container:
        ready = self._is_ready(account)
        selected = account.id in self.selected and ready
        if ready:
            dot, text, color = ((th.SUCCESS, "Готов к публикации", th.SUCCESS_TEXT2)
                                if selected else
                                (th.TEXT_GHOST, "Не выбран", th.TEXT_DIM))
        else:
            dot, text, color = th.ERROR, "Нет ключа — задайте в настройках", th.ERROR_TEXT

        check = ft.Container(
            content=(ft.Icon(ft.Icons.CHECK, size=14, color=th.ACCENT_FG)
                     if selected else None),
            width=24, height=24, border_radius=7,
            bgcolor=th.ACCENT if selected else None,
            border=(None if selected else ft.border.all(1.5, th.BORDER_DASHED)),
            alignment=ft.alignment.center)

        trailing = check if ready else ui.text_link(
            "Настроить", lambda e: self.app.set_nav("settings"))

        row = ft.Container(
            content=ft.Row([
                ui.platform_letter(account.name[:1].upper() or "?"),
                ft.Column([
                    ft.Text(account.name, size=14.5, weight=ft.FontWeight.W_600),
                    ui.status_dot(dot, text, color, text_size=12),
                ], spacing=3, expand=True),
                trailing,
            ], spacing=13),
            bgcolor=th.BG_CARD, border_radius=12,
            border=ft.border.all(1, th.ACCENT if selected else th.BORDER_CARD),
            padding=ft.padding.symmetric(12, 15))
        if ready:
            row.on_click = lambda e, a=account: self._toggle_account(a.id)
            ui.hover_style(row, lambda c, h, sel=selected: setattr(
                c, "border", ft.border.all(
                    1, th.ACCENT if sel else th.white(0.16 if h else 0.08))))
        else:
            row.opacity = 0.75
        return row

    def _preview_panel(self) -> ft.Container:
        return ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Column([
                        self.preview_platform_label,
                        self.preview_targets,
                    ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.START),
                    padding=ft.padding.only(24, 20, 24, 14)),
                ft.Container(
                    content=ft.Column([self.preview_holder],
                                      scroll=ft.ScrollMode.AUTO),
                    padding=ft.padding.only(24, 6, 24, 24), expand=True),
            ], spacing=0),
            width=452, bgcolor=th.BG_SIDEBAR,
            border=ft.border.only(left=ft.BorderSide(1, th.BORDER_SOFT)))

    def _preview_empty(self, message: str, sub: str) -> ft.Control:
        return ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.VISIBILITY_OFF_OUTLINED, size=28,
                        color=th.TEXT_GHOST),
                ft.Text(message, size=14, weight=ft.FontWeight.W_600,
                        color=th.TEXT_GRAY, text_align=ft.TextAlign.CENTER),
                ft.Text(sub, size=12.5, color=th.TEXT_LABEL,
                        text_align=ft.TextAlign.CENTER),
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True),
            alignment=ft.alignment.center, padding=ft.padding.only(top=80))

    def _first_image(self) -> str | None:
        for p in self.media:
            if p.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                return p
        return None

    def _media_box(self, width, height) -> ft.Control:
        img = self._first_image()
        if img:
            return ft.Container(
                content=ft.Image(src=img, fit=ft.ImageFit.COVER,
                                 width=width, height=height),
                width=width, height=height,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS)
        return ui.media_placeholder(width, height, radius=0)

    def _pinterest_preview(self) -> ft.Control:
        post = self.current_post()
        pv = get_adapter("pinterest").preview(post)
        save_pill = ft.Container(
            content=ft.Text("Сохранить", size=12, weight=ft.FontWeight.W_700,
                            color=th.ACCENT_FG),
            bgcolor=th.ACCENT, border_radius=999,
            padding=ft.padding.symmetric(6, 13), right=10, top=10)
        return ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Stack([self._media_box(236, 308), save_pill]),
                    height=308),
                ft.Container(
                    content=ft.Column([
                        ft.Text(pv.title or "Заголовок поста", size=14.5,
                                weight=ft.FontWeight.W_600,
                                color=th.TEXT if pv.title else th.TEXT_DIM),
                        ft.Text(pv.text or "Текст появится здесь", size=13,
                                color="#a4a4aa" if pv.text else th.TEXT_DIM),
                        ft.Text(pv.link_domain or "ссылка не задана", size=12,
                                color=th.TEXT_FAINT, font_family=th.FONT_MONO),
                        ft.Row([
                            ft.Container(width=22, height=22, border_radius=11,
                                         bgcolor="#2a2a2e"),
                            ft.Text(f"Доска · {pv.board or 'не выбрана'}",
                                    size=12, color=th.TEXT_GRAY),
                        ], spacing=7),
                    ], spacing=8),
                    padding=ft.padding.only(14, 13, 14, 16)),
            ], spacing=0),
            width=236, bgcolor=th.BG_CARD, border_radius=16,
            border=ft.border.all(1, th.BORDER_INPUT),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS)

    def _boosty_preview(self) -> ft.Control:
        post = self.current_post()
        pv = get_adapter("boosty").preview(post)
        selected = [a for a in self._platform_accounts() if a.id in self.selected]
        blog = selected[0].name if selected else "Ваш блог"
        return ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Row([
                        ft.Container(
                            content=ft.Text(blog[:1].upper(), size=15,
                                            weight=ft.FontWeight.W_700,
                                            color=th.ACCENT_FG),
                            width=38, height=38, border_radius=19,
                            bgcolor=th.ACCENT, alignment=ft.alignment.center),
                        ft.Column([
                            ft.Text(blog, size=14, weight=ft.FontWeight.W_600),
                            ft.Text("только что · для подписчиков", size=11.5,
                                    color=th.TEXT_FAINT),
                        ], spacing=1),
                    ], spacing=11),
                    padding=ft.padding.only(16, 15, 16, 12)),
                ft.Container(
                    content=ft.Column([
                        ft.Text(pv.title or "Заголовок поста", size=15,
                                weight=ft.FontWeight.W_600,
                                color=th.TEXT if pv.title else th.TEXT_DIM),
                        ft.Text(pv.text or "Текст появится здесь", size=13.5,
                                color=th.TEXT_MUTED if pv.text else th.TEXT_DIM),
                    ], spacing=6),
                    padding=ft.padding.only(16, 0, 16, 12)),
                self._media_box(404, 210),
                ft.Container(
                    content=ft.Row([
                        ft.Text("♡ Нравится", size=13, color=th.TEXT_FAINT),
                        ft.Text("💬 Комментарий", size=13, color=th.TEXT_FAINT),
                    ], spacing=20),
                    padding=ft.padding.symmetric(12, 16)),
            ], spacing=0),
            bgcolor=th.BG_CARD, border_radius=16,
            border=ft.border.all(1, th.BORDER_INPUT),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS)

    def _action_bar(self) -> ft.Container:
        draft_btn = ui.ghost_button("Черновик", self._save_draft,
                                    padding=ft.padding.symmetric(12, 18))
        self.clear_btn = ui.text_link("Очистить", self._clear_form,
                                      icon=ft.Icons.REFRESH)
        return ft.Container(
            content=ft.Row([
                ft.Row([self.tg_schedule,
                        ft.Text("Отложить", size=14, color=th.TEXT_MUTED,
                                weight=ft.FontWeight.W_500)], spacing=11),
                self.dt_row,
                ft.Row([self.hint_text, self.clear_btn, draft_btn,
                        self.publish_btn],
                       spacing=12, expand=True,
                       alignment=ft.MainAxisAlignment.END,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=18),
            padding=ft.padding.symmetric(15, 30), bgcolor=th.BG_ACTIONBAR,
            border=ft.border.only(top=ft.BorderSide(1, th.BORDER_SOFT)))

    def _select_platform(self, key: str) -> None:
        if key == self.platform:
            return
        self.platform = key
        self._select_all_ready(update=False)
        self.refresh()

    def _toggle_account(self, account_id: str) -> None:
        if account_id in self.selected:
            self.selected.discard(account_id)
        else:
            self.selected.add(account_id)
        self.refresh()

    def _toggle_schedule(self, value: bool) -> None:
        self.schedule_on = value
        self.refresh()

    def _media_picked(self, e: ft.FilePickerResultEvent) -> None:
        if e.files:
            self.media.extend(f.path for f in e.files if f.path)
        self.refresh()

    def _remove_media(self, path: str) -> None:
        self.media = [m for m in self.media if m != path]
        self.refresh()

    def _clear_media(self, _) -> None:
        self.media = []
        self.refresh()

    def _clear_form(self, _) -> None:
        self.reset_form()
        self.refresh()
        self.app.snack("Форма очищена")

    def _pick_date(self, _) -> None:
        picker = ft.DatePicker(
            value=datetime.combine(self.sched_date, time.min),
            first_date=datetime.now(),
            last_date=datetime.now() + timedelta(days=365),
            on_change=self._date_changed)
        self.app.page.open(picker)

    def _date_changed(self, e) -> None:
        if e.control.value:
            self.sched_date = e.control.value.date()
        self.refresh()

    def _pick_time(self, _) -> None:
        picker = ft.TimePicker(value=self.sched_time, on_change=self._time_changed)
        self.app.page.open(picker)

    def _time_changed(self, e) -> None:
        if e.control.value:
            self.sched_time = e.control.value
        self.refresh()

    def _apply_when(self, when: datetime) -> None:
        self.sched_date = when.date()
        self.sched_time = when.time().replace(second=0, microsecond=0)
        self.refresh()

    def _preset_hour(self) -> None:
        self._apply_when(datetime.now() + timedelta(hours=1))

    def _preset_morning(self) -> None:
        tomorrow = datetime.now() + timedelta(days=1)
        self._apply_when(tomorrow.replace(hour=9, minute=0))

    def _preset_evening(self) -> None:
        now = datetime.now()
        target = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        self._apply_when(target)

    def _save_draft(self, _) -> None:
        post = self.current_post()
        self.app.service.save_draft(post)
        self.app.snack("Черновик сохранён")

    def refresh(self, update: bool = True) -> None:
        adapter = get_adapter(self.platform) if self.platform else None
        accounts = self._platform_accounts()
        missing, can_publish = self._validity()
        selected_ready = self.current_post().accounts
        n_sel = len(selected_ready)

        self.platform_row.controls = [
            self._platform_card(a, a.key == self.platform) for a in all_adapters()]

        self.accounts_summary.value = (
            f"{n_sel} из {len(accounts)} выбрано" if accounts else "Нет аккаунтов")
        if accounts:
            self.accounts_holder.controls = [self._account_row(a) for a in accounts]
        else:
            self.accounts_holder.controls = [ui.dashed_stub(
                "＋ Добавить аккаунт в «Настройках»")]
            self.accounts_holder.controls[0].on_click = (
                lambda e: self.app.set_nav("settings"))

        self.pin_params.visible = self.platform == "pinterest"
        self._refresh_counters()
        self._refresh_media_row()
        self.media_hint.visible = bool(
            self.platform == "pinterest" and n_sel
            and not get_adapter("pinterest").has_image(self.current_post()))

        self.preview_platform_label.value = (
            f"ПРЕДПРОСМОТР · {adapter.name}".upper() if adapter else "ПРЕДПРОСМОТР")
        self.preview_targets.value = (
            f"→ {n_sel} {self._plural_accounts(n_sel)}" if n_sel
            else "Выберите аккаунты назначения")
        if not accounts:
            self.preview_holder.content = self._preview_empty(
                "Нет аккаунтов площадки",
                "Добавьте аккаунт в «Настройках»,\nчтобы публиковать")
        elif n_sel == 0:
            self.preview_holder.content = self._preview_empty(
                "Аккаунты не выбраны",
                "Отметьте хотя бы один аккаунт\nдля публикации")
        else:
            self.preview_holder.content = (self._pinterest_preview()
                                           if self.platform == "pinterest"
                                           else self._boosty_preview())

        self._refresh_steps(can_publish, n_sel)

        self.dt_row.visible = self.schedule_on
        self.date_btn.content.controls[1].value = self.sched_date.strftime("%d.%m.%Y")
        self.time_btn.content.controls[1].value = self.sched_time.strftime("%H:%M")

        summary = f"{n_sel} {self._plural_accounts(n_sel)}"
        if not accounts:
            self.hint_text.value = "Добавьте аккаунт в настройках"
            self.hint_text.color = th.ERROR_TEXT
        elif n_sel == 0:
            self.hint_text.value = "Выберите хотя бы один аккаунт"
            self.hint_text.color = th.ERROR_TEXT
        elif can_publish:
            self.hint_text.value = f"Всё готово · {summary}"
            self.hint_text.color = th.SUCCESS_TEXT2
        else:
            self.hint_text.value = "Заполните: " + ", ".join(missing)
            self.hint_text.color = th.TEXT_FAINT

        label = ("Запланировать" if self.schedule_on
                 else (f"Опубликовать · {n_sel}" if n_sel > 1 else "Опубликовать"))
        self.publish_btn.content.value = label
        self.publish_btn.content.color = th.ACCENT_FG if can_publish else th.TEXT_DIM
        self.publish_btn.bgcolor = th.ACCENT if can_publish else th.white(0.08)
        self.publish_btn.opacity = 1.0 if can_publish else 0.55
        self.publish_btn.shadow = ui.primary_shadow() if can_publish else None

        if update and self.app.page:
            self.app.page.update()

    def _refresh_counters(self) -> None:
        """Счётчики символов с учётом лимитов Pinterest."""
        show_limit = self.platform == "pinterest"
        pin = get_adapter("pinterest")
        title_n = len(self.f_title.value or "")
        text_n = len(self.f_text.value or "")

        def apply(counter: ft.Text, n: int, limit: int) -> None:
            if show_limit:
                counter.value = f"{n} / {limit}"
                if n > limit:
                    counter.color = th.ERROR
                elif n > limit * 0.9:
                    counter.color = th.ERROR_TEXT
                else:
                    counter.color = th.TEXT_DIM
            else:
                counter.value = (f"{n} символов" if n else "")
                counter.color = th.TEXT_DIM

        apply(self.title_counter, title_n, pin.TITLE_LIMIT)
        apply(self.text_counter, text_n, pin.TEXT_LIMIT)

    def _refresh_media_row(self) -> None:
        thumbs = []
        for path in self.media:
            name = os.path.basename(path)
            is_img = path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))
            inner = (ft.Image(src=path, fit=ft.ImageFit.COVER, width=88, height=88)
                     if is_img else
                     ft.Container(
                         content=ft.Column([
                             ft.Icon(ft.Icons.INSERT_DRIVE_FILE_OUTLINED,
                                     color=th.TEXT_FAINT, size=22),
                             ft.Text(name[-9:], size=9, color=th.TEXT_FAINT,
                                     max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                         ], spacing=4,
                             alignment=ft.MainAxisAlignment.CENTER,
                             horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                         alignment=ft.alignment.center, width=88, height=88,
                         bgcolor="#1a1a1d"))
            remove = ft.Container(
                content=ft.Icon(ft.Icons.CLOSE, size=12, color="#f1f1f3"),
                width=22, height=22, border_radius=6,
                bgcolor=ft.Colors.with_opacity(0.6, "#000000"),
                alignment=ft.alignment.center, right=5, top=5,
                on_click=lambda e, p=path: self._remove_media(p),
                tooltip="Удалить")
            thumbs.append(ft.Container(
                content=ft.Stack([inner, remove]), width=88, height=88,
                border_radius=11, border=ft.border.all(1, th.white(0.1)),
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS, tooltip=name))
        self.media_row.controls = thumbs
        self.media_row.visible = bool(thumbs)

        n = len(self.media)
        self.media_count.value = (f"{n} {self._plural_files(n)}" if n else "")
        self.media_clear.visible = n > 0

    @staticmethod
    def _plural_files(n: int) -> str:
        if 11 <= n % 100 <= 14:
            return "файлов"
        d = n % 10
        return "файл" if d == 1 else "файла" if 2 <= d <= 4 else "файлов"

    @staticmethod
    def _plural_accounts(n: int) -> str:
        if 11 <= n % 100 <= 14:
            return "аккаунтов"
        d = n % 10
        return "аккаунт" if d == 1 else "аккаунта" if 2 <= d <= 4 else "аккаунтов"

    def _refresh_steps(self, can_publish: bool, n_sel: int) -> None:
        platform_ready = bool(self.platform)
        accounts_ready = n_sel > 0
        states = [
            "done" if platform_ready else "active",
            "done" if accounts_ready else ("active" if platform_ready else "pending"),
            "done" if can_publish else ("active" if accounts_ready else "pending"),
        ]
        palette = {
            "done": (th.ACCENT, th.ACCENT_FG, th.TEXT_MUTED),
            "active": (th.white(0.14), th.TEXT, th.TEXT),
            "pending": (th.white(0.05), th.TEXT_DIM, th.TEXT_DIM),
        }
        for (circle, num, caption), state in zip(self.steps, states):
            bg, fg, tx = palette[state]
            circle.bgcolor = bg
            num.color = fg
            caption.color = tx

    def reset_form(self) -> None:
        for f in (self.f_title, self.f_text, self.f_link, self.f_board):
            f.value = ""
        self.media = []
        self.schedule_on = False
        self.tg_schedule.set_value(False, update=False)
        self._select_all_ready(update=False)
        self.refresh(update=False)

    def _publish_clicked(self, _) -> None:
        missing, can_publish = self._validity()
        if not can_publish:
            return
        post = self.current_post()
        if self.schedule_on:
            when = datetime.combine(self.sched_date, self.sched_time)
            if when <= datetime.now():
                self.app.snack("Выберите время в будущем")
                return
            self.app.service.schedule_post(post, when)
            self.app.refresh_sidebar()
            self._show_scheduled_overlay(when, post)
        else:
            self._start_publish(post)

    def _start_publish(self, post: Post) -> None:
        self._pub_post = post
        self._pub_accounts = [a for a in
                              (self.app.accounts.get(i) for i in post.accounts)
                              if a is not None]
        self._pub_state = {a.id: PublicationStatus.QUEUE for a in self._pub_accounts}
        self._pub_rows = {}
        self._build_pub_overlay(post)
        self.app.show_overlay(self._pub_overlay)

        def work():
            self.app.service.publish_now(post, self._on_progress)
            self._pub_finished()

        self.app.page.run_thread(work)

    def _build_pub_overlay(self, post: Post) -> None:
        adapter = get_adapter(post.platform)
        rows = []
        for account in self._pub_accounts:
            label = ft.Text("В очереди…", size=12.5, color=th.TEXT_GRAY2)
            trailing = ft.Container(content=self._spinner(),
                                    alignment=ft.alignment.center_right)
            self._pub_rows[account.id] = (label, trailing)
            rows.append(ft.Container(
                content=ft.Row([
                    ui.platform_letter(account.name[:1].upper() or "?"),
                    ft.Column([
                        ft.Text(account.name, size=14.5, weight=ft.FontWeight.W_600),
                        label,
                    ], spacing=2, expand=True),
                    trailing,
                ], spacing=14),
                padding=ft.padding.symmetric(16, 0),
                border=ft.border.only(bottom=ft.BorderSide(1, th.white(0.05)))))

        self._pub_title = ft.Text(f"Публикуем в {adapter.name}",
                                  font_family=th.FONT_HEAD,
                                  size=19, weight=ft.FontWeight.W_600)
        self._pub_note = ft.Text("Не закрывайте окно приложения", size=12.5,
                                 color=th.TEXT_LABEL)
        self._pub_finish = ft.Container(
            content=ft.Text("Готово", size=14, weight=ft.FontWeight.W_700,
                            color=th.TEXT_DIM),
            bgcolor=th.white(0.08), padding=ft.padding.symmetric(11, 22),
            border_radius=10, opacity=0.55, on_click=None)

        self._pub_overlay = ui.overlay_scrim(ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Column([
                        self._pub_title,
                        ft.Text("Публикация идёт независимо по каждому аккаунту",
                                size=13, color=th.TEXT_FAINT),
                    ], spacing=4),
                    padding=ft.padding.only(26, 24, 26, 18),
                    border=ft.border.only(bottom=ft.BorderSide(1, th.white(0.07)))),
                ft.Container(content=ft.Column(rows, spacing=0),
                             padding=ft.padding.symmetric(12, 26)),
                ft.Container(
                    content=ft.Row([self._pub_note, self._pub_finish],
                                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=ft.padding.only(26, 16, 26, 22)),
            ], spacing=0, tight=True),
            width=520, bgcolor=th.BG_DIALOG, border_radius=18,
            border=ft.border.all(1, th.white(0.1)),
            shadow=ui.card_shadow()))

    @staticmethod
    def _spinner() -> ft.ProgressRing:
        return ft.ProgressRing(width=20, height=20, stroke_width=2.5,
                               color=th.ACCENT, bgcolor=th.white(0.15))

    def _on_progress(self, account_id: str, status: str, error: str) -> None:
        self._pub_state[account_id] = status
        label, trailing = self._pub_rows[account_id]
        if status == PublicationStatus.PUBLISHING:
            label.value, label.color = "Публикуется…", th.TEXT_MUTED
            trailing.content = self._spinner()
        elif status == PublicationStatus.SUCCESS:
            label.value, label.color = "Опубликовано", th.SUCCESS_TEXT2
            trailing.content = ft.Container(
                content=ft.Text("✓", size=13, weight=ft.FontWeight.W_900,
                                color="#06140d"),
                width=22, height=22, border_radius=11, bgcolor=th.SUCCESS,
                alignment=ft.alignment.center)
        else:
            label.value = f"Ошибка · {error}" if error else "Ошибка"
            label.color = th.ERROR_TEXT
            trailing.content = ft.Container(
                content=ft.Text("↻ Повторить", size=12.5,
                                weight=ft.FontWeight.W_700, color=th.ACCENT_FG),
                bgcolor=th.ERROR, border_radius=8,
                padding=ft.padding.symmetric(7, 13),
                on_click=lambda e, a=account_id: self._retry(a))
        self._safe_update()

    def _retry(self, account_id: str) -> None:
        if self._pub_post is None or self._pub_post.id is None:
            return
        post_id = self._pub_post.id

        def work():
            self.app.service.retry_account(post_id, account_id, self._on_progress)
            self._pub_finished()

        self.app.page.run_thread(work)

    def _pub_finished(self) -> None:
        states = self._pub_state.values()
        busy = any(s in (PublicationStatus.QUEUE, PublicationStatus.PUBLISHING)
                   for s in states)
        if busy:
            return
        all_ok = all(s == PublicationStatus.SUCCESS for s in states)
        any_err = any(s == PublicationStatus.ERROR for s in states)
        self._pub_title.value = ("Готово" if all_ok
                                 else "Часть аккаунтов не ответила" if any_err
                                 else self._pub_title.value)
        self._pub_note.value = ("Все аккаунты опубликованы" if all_ok
                                else "Остальные аккаунты опубликованы независимо")
        self._pub_finish.opacity = 1.0
        self._pub_finish.bgcolor = th.ACCENT
        self._pub_finish.content.color = th.ACCENT_FG
        self._pub_finish.on_click = self._finish_publish
        self.app.refresh_sidebar(update=False)
        self._safe_update()

    def _finish_publish(self, _) -> None:
        all_ok = all(s == PublicationStatus.SUCCESS
                     for s in self._pub_state.values())
        if all_ok:
            self._show_done_overlay()
        else:
            self.app.hide_overlay()
            self.app.snack("Результаты публикации сохранены в истории")

    def _safe_update(self) -> None:
        try:
            self.app.page.update()
        except Exception:
            pass

    def _show_done_overlay(self) -> None:
        count = len(self._pub_state)
        title = "Опубликовано во все аккаунты" if count > 1 else "Опубликовано"
        card = ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Text("✓", size=30, weight=ft.FontWeight.W_900,
                                    color="#06140d"),
                    width=60, height=60, border_radius=30, bgcolor=th.SUCCESS,
                    alignment=ft.alignment.center),
                ft.Text(title, font_family=th.FONT_HEAD, size=22,
                        weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER),
                ft.Text("Пост добавлен в историю. Ссылки на публикации доступны там же.",
                        size=14, color=th.TEXT_FAINT, text_align=ft.TextAlign.CENTER),
                ft.Row([
                    ui.ghost_button("Открыть историю",
                                    lambda e: self._leave_to("history")),
                    ui.light_button("Новый пост", lambda e: self._leave_to("compose"),
                                    padding=ft.padding.symmetric(12, 22)),
                ], spacing=12, alignment=ft.MainAxisAlignment.CENTER),
            ], spacing=18, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True),
            width=460, bgcolor=th.BG_DIALOG, border_radius=18,
            border=ft.border.all(1, th.white(0.1)),
            padding=ft.padding.symmetric(32, 30),
            shadow=ui.card_shadow())
        self.app.show_overlay(ui.overlay_scrim(card))

    def _show_scheduled_overlay(self, when: datetime, post: Post) -> None:
        adapter = get_adapter(post.platform)
        count = len(post.accounts)
        summary = f"{adapter.name} · {count} {self._plural_accounts(count)}"
        card = ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Icon(ft.Icons.CALENDAR_TODAY_OUTLINED, size=28,
                                    color=th.ACCENT),
                    width=60, height=60, border_radius=16,
                    border=ft.border.all(1, th.BORDER_DASHED),
                    alignment=ft.alignment.center),
                ft.Text("Публикация запланирована", font_family=th.FONT_HEAD,
                        size=21, weight=ft.FontWeight.W_600),
                ft.Text(f"{fmt.human_datetime(when)} · {summary}.\n"
                        "Планировщик опубликует пост автоматически.",
                        size=14, color=th.TEXT_FAINT, text_align=ft.TextAlign.CENTER),
                ft.Row([
                    ui.ghost_button("В расписание",
                                    lambda e: self._leave_to("schedule")),
                    ui.light_button("Новый пост", lambda e: self._leave_to("compose"),
                                    padding=ft.padding.symmetric(12, 22)),
                ], spacing=12, alignment=ft.MainAxisAlignment.CENTER),
            ], spacing=18, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True),
            width=440, bgcolor=th.BG_DIALOG, border_radius=18,
            border=ft.border.all(1, th.white(0.1)),
            padding=ft.padding.symmetric(32, 30),
            shadow=ui.card_shadow())
        self.app.show_overlay(ui.overlay_scrim(card))

    def _leave_to(self, nav: str) -> None:
        self.reset_form()
        self.app.hide_overlay(update=False)
        self.app.set_nav(nav)
