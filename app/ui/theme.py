"""Палитра и шрифты интерфейса — токены из дизайн-макета."""

from __future__ import annotations

import flet as ft

# фоны
BG_WINDOW = "#0d0d0f"
BG_SIDEBAR = "#0a0a0c"
BG_TITLEBAR = "#141416"
BG_CARD = "#151517"
BG_CARD_PLATFORM = "#131315"
BG_INPUT_NESTED = "#0e0e10"
BG_ACTIONBAR = "#0b0b0d"
BG_DIALOG = "#141416"

# текст
TEXT = "#f1f1f3"
TEXT_SOFT = "#e2e2e6"
TEXT_MUTED = "#c4c4c9"
TEXT_GRAY = "#9a9aa0"
TEXT_GRAY2 = "#8a8a90"
TEXT_FAINT = "#7a7a80"
TEXT_LABEL = "#6a6a70"
TEXT_DIM = "#5a5a60"
TEXT_GHOST = "#3a3a40"

# акценты
ACCENT = "#ececef"          # светлые кнопки и тумблеры
ACCENT_FG = "#0d0d0f"
SUCCESS = "#3ddc97"
SUCCESS_TEXT = "#a4d4b0"
SUCCESS_TEXT2 = "#8fcfa4"
ERROR = "#e08a6a"
ERROR_TEXT = "#d6a892"
ERROR_TEXT2 = "#e0b0a4"

# шрифты: аналоги Space Grotesk / Space Mono из макета с поддержкой кириллицы
FONT_HEAD = "Onest"
FONT_BODY = "Manrope"
FONT_MONO = "JetBrains Mono"

# шрифты поставляются вместе с приложением (assets/fonts) — работает офлайн
FONTS = {
    FONT_HEAD: "/fonts/Onest.ttf",
    FONT_BODY: "/fonts/Manrope.ttf",
    FONT_MONO: "/fonts/JetBrainsMono.ttf",
}


def white(opacity: float) -> str:
    return ft.Colors.with_opacity(opacity, "#ffffff")


BORDER_SOFT = white(0.06)
BORDER_CARD = white(0.08)
BORDER_INPUT = white(0.09)
BORDER_STRONG = white(0.12)
BORDER_DASHED = white(0.14)

# мягкое свечение фирменной точки-акцента (белый гало на тёмном фоне)
GLOW_ACCENT = white(0.4)


def apply(page: ft.Page) -> None:
    page.bgcolor = BG_WINDOW
    page.padding = 0
    page.fonts = FONTS
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(
        font_family=FONT_BODY,
        color_scheme_seed="#ececef",  # монохромная палитра системных виджетов
        scrollbar_theme=ft.ScrollbarTheme(
            thumb_color=white(0.12),
            track_color=ft.Colors.TRANSPARENT,
            thickness=8,
            radius=6,
            main_axis_margin=4,
            cross_axis_margin=2,
        ),
    )
