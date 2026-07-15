"""Переиспользуемые элементы интерфейса в стиле макета."""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from . import theme as th


def hover_style(ctrl: ft.Control, apply_fn) -> None:
    """Вешает hover-обработчик: apply_fn(ctrl, hovered) правит свойства."""
    def handler(e: ft.ControlEvent):
        apply_fn(ctrl, e.data == "true")
        try:
            ctrl.update()
        except Exception:
            pass
    ctrl.on_hover = handler


def card_shadow(strength: float = 0.6) -> ft.BoxShadow:
    """Глубокая тень модальных карточек, как в макете."""
    return ft.BoxShadow(blur_radius=120, offset=ft.Offset(0, 40),
                        color=ft.Colors.with_opacity(strength, "#000000"))


def primary_shadow() -> ft.BoxShadow:
    """Мягкая тень главного действия — слегка приподнимает акцентную кнопку."""
    return ft.BoxShadow(blur_radius=20, spread_radius=-6,
                        offset=ft.Offset(0, 8),
                        color=ft.Colors.with_opacity(0.45, "#000000"))


def brand_dot(size: int = 9, glow: bool = True) -> ft.Container:
    """Фирменная точка-акцент с мягким свечением (заголовки, тайтлбар, вход)."""
    return ft.Container(
        width=size, height=size, border_radius=size, bgcolor=th.ACCENT,
        shadow=(ft.BoxShadow(blur_radius=size + 3, spread_radius=-1,
                             color=th.GLOW_ACCENT, offset=ft.Offset(0, 0))
                if glow else None))


def mono_label(text: str, size: int = 11, color: str = th.TEXT_LABEL) -> ft.Text:
    """Секционная подпись: моноширинный шрифт, капс, разрядка."""
    return ft.Text(text.upper(), font_family=th.FONT_MONO, size=size,
                   color=color, weight=ft.FontWeight.W_500,
                   style=ft.TextStyle(letter_spacing=1.2))


def heading(text: str, size: int = 23) -> ft.Text:
    return ft.Text(text, font_family=th.FONT_HEAD, size=size,
                   weight=ft.FontWeight.W_600, color=th.TEXT,
                   style=ft.TextStyle(letter_spacing=-0.4))


def subtitle(text: str, size: float = 13.5) -> ft.Text:
    return ft.Text(text, size=size, color=th.TEXT_FAINT)


def page_header(title: str, sub: str) -> ft.Container:
    return ft.Container(
        content=ft.Column([heading(title), subtitle(sub)], spacing=3),
        padding=ft.padding.symmetric(22, 30),
        border=ft.border.only(bottom=ft.BorderSide(1, th.BORDER_SOFT)),
    )


def platform_letter(letter: str, size: int = 34, radius: int = 9) -> ft.Container:
    return ft.Container(
        content=ft.Text(letter, font_family=th.FONT_HEAD, size=size * 0.47,
                        weight=ft.FontWeight.W_800, color=th.ACCENT_FG),
        width=size, height=size, border_radius=radius, bgcolor=th.ACCENT,
        alignment=ft.alignment.center,
    )


def status_dot(dot_color: str, text: str, text_color: str,
               dot_size: int = 7, text_size: float = 13) -> ft.Row:
    return ft.Row([
        ft.Container(width=dot_size, height=dot_size, border_radius=dot_size,
                     bgcolor=dot_color),
        ft.Text(text, size=text_size, color=text_color),
    ], spacing=8, tight=True)


class PillToggle(ft.Container):
    """Тумблер-переключатель, как в макете (42×24, светлый в положении «вкл»)."""

    def __init__(self, value: bool = False,
                 on_change: Optional[Callable[[bool], None]] = None,
                 width: int = 42, height: int = 24):
        super().__init__()
        self.value = value
        self._on_change = on_change
        self._w, self._h = width, height
        self._knob = ft.Container(
            width=height - 6, height=height - 6, border_radius=height,
            bgcolor="#ffffff",
            shadow=ft.BoxShadow(blur_radius=3, color=ft.Colors.with_opacity(0.4, "#000000"),
                                offset=ft.Offset(0, 1)),
            animate_position=150,
        )
        self.width, self.height = width, height
        self.border_radius = 999
        self.on_click = self._toggle
        self.animate = 150
        self.content = ft.Stack([self._knob])
        self._sync()

    def _sync(self) -> None:
        self.bgcolor = th.ACCENT if self.value else th.white(0.15)
        self._knob.top = 3
        self._knob.left = self._w - self._h + 3 if self.value else 3

    def set_value(self, value: bool, update: bool = True) -> None:
        self.value = value
        self._sync()
        if update and self.page:
            self.update()

    def _toggle(self, _) -> None:
        self.set_value(not self.value)
        if self._on_change:
            self._on_change(self.value)


def light_button(text: str, on_click=None, disabled: bool = False,
                 padding: ft.Padding | None = None) -> ft.Container:
    """Главная светлая кнопка (акцент макета)."""
    btn = ft.Container(
        content=ft.Text(text, size=14, weight=ft.FontWeight.W_700,
                        color=th.ACCENT_FG if not disabled else th.TEXT_DIM),
        bgcolor=th.ACCENT if not disabled else th.white(0.08),
        padding=padding or ft.padding.symmetric(12, 26),
        border_radius=10,
        on_click=None if disabled else on_click,
        ink=not disabled,
        opacity=0.55 if disabled else 1.0,
        animate_opacity=120,
        shadow=None if disabled else primary_shadow(),
    )
    if not disabled:
        hover_style(btn, lambda c, h: setattr(c, "bgcolor",
                                              "#ffffff" if h else th.ACCENT))
    return btn


def ghost_button(text: str, on_click=None,
                 padding: ft.Padding | None = None) -> ft.Container:
    """Вторичная кнопка с тонкой рамкой."""
    btn = ft.Container(
        content=ft.Text(text, size=14, weight=ft.FontWeight.W_600, color="#d6d6da"),
        border=ft.border.all(1, th.BORDER_DASHED),
        padding=padding or ft.padding.symmetric(12, 20),
        border_radius=10,
        on_click=on_click,
        ink=True,
    )
    hover_style(btn, lambda c, h: setattr(
        c, "border", ft.border.all(1, th.white(0.3 if h else 0.14))))
    return btn


def chip_button(text: str, on_click=None) -> ft.Container:
    """Маленькая кнопка-таблетка (строки списков, настройки)."""
    btn = ft.Container(
        content=ft.Text(text, size=12.5, color=th.TEXT_GRAY2),
        border=ft.border.all(1, th.BORDER_STRONG),
        padding=ft.padding.symmetric(6, 13),
        border_radius=8,
        on_click=on_click,
        ink=True,
    )

    def style(c, h):
        c.border = ft.border.all(1, th.white(0.25 if h else 0.12))
        c.content.color = th.TEXT_SOFT if h else th.TEXT_GRAY2

    hover_style(btn, style)
    return btn


def text_field(hint: str = "", value: str = "", on_change=None,
               multiline: bool = False, min_lines: int = 1,
               nested: bool = False, mono: bool = False,
               size: float = 14.5, weight: ft.FontWeight | None = None,
               password: bool = False) -> ft.TextField:
    """Поле ввода в стиле макета (тёмный фон, тонкая рамка, светлый фокус)."""
    return ft.TextField(
        value=value, hint_text=hint, on_change=on_change,
        multiline=multiline, min_lines=min_lines,
        max_lines=None if multiline else 1,
        password=password, can_reveal_password=password,
        bgcolor=th.BG_INPUT_NESTED if nested else th.BG_CARD,
        border_color=th.BORDER_INPUT,
        focused_border_color=th.white(0.28),
        border_radius=8 if nested else 10,
        border_width=1,
        text_style=ft.TextStyle(
            size=size, color=th.TEXT_SOFT, weight=weight,
            font_family=th.FONT_MONO if mono else th.FONT_BODY),
        hint_style=ft.TextStyle(size=size, color=th.TEXT_DIM),
        cursor_color=th.TEXT,
        content_padding=ft.padding.symmetric(11, 13) if nested
        else ft.padding.symmetric(13, 15),
    )


def text_link(text: str, on_click=None, size: float = 12,
              color: str = th.TEXT_GRAY2, icon: str | None = None) -> ft.Container:
    """Деликатная текст-ссылка для вспомогательных действий."""
    row: list[ft.Control] = []
    if icon:
        row.append(ft.Icon(icon, size=size + 2, color=color))
    row.append(ft.Text(text, size=size, weight=ft.FontWeight.W_500, color=color))
    link = ft.Container(
        content=ft.Row(row, spacing=5, tight=True),
        padding=ft.padding.symmetric(4, 6), border_radius=7,
        on_click=on_click)

    def style(c, h):
        c.bgcolor = th.white(0.06) if h else None
        for ctrl in c.content.controls:
            ctrl.color = th.TEXT_SOFT if h else color

    hover_style(link, style)
    return link


def dashed_stub(text: str, height: int | None = None) -> ft.Container:
    """Пунктирная заглушка «подключить новую площадку» и т.п."""
    stub = ft.Container(
        content=ft.Text(text, size=13, color=th.TEXT_LABEL),
        border=ft.border.all(1.5, th.BORDER_DASHED),
        border_radius=13,
        padding=ft.padding.symmetric(14, 16),
        height=height,
        alignment=ft.alignment.center,
    )

    def style(c, h):
        c.border = ft.border.all(1.5, th.white(0.3 if h else 0.14))
        c.content.color = "#a4a4aa" if h else th.TEXT_LABEL

    hover_style(stub, style)
    return stub


def media_placeholder(width: int | float, height: int,
                      radius: int = 11) -> ft.Container:
    """Градиентная заглушка медиа, как в макете."""
    return ft.Container(
        width=width, height=height, border_radius=radius,
        gradient=ft.LinearGradient(
            begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
            colors=["#2a2a2e", "#161619"]),
    )


def overlay_scrim(content: ft.Control) -> ft.Stack:
    """Затемняющая подложка модальных оверлеев (скрим + карточка поверх)."""
    return ft.Stack([
        ft.Container(bgcolor=ft.Colors.with_opacity(0.78, "#060608"),
                     blur=ft.Blur(6, 6), expand=True),
        ft.Container(content=content, alignment=ft.alignment.center,
                     expand=True),
    ], expand=True)
