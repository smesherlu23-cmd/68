"""Экран «Аналитика» — заглушка (раздел зарезервирован по ТЗ, п. 5.7)."""

from __future__ import annotations

import flet as ft

from .. import components as ui
from .. import theme as th


def build(app) -> ft.Control:
    def stat(label: str) -> ft.Container:
        return ft.Container(
            content=ft.Column([
                ft.Text(label, size=12, color=th.TEXT_LABEL),
                ft.Text("—", font_family=th.FONT_HEAD, size=30,
                        weight=ft.FontWeight.W_600, color=th.TEXT_GHOST),
            ], spacing=6),
            width=150, bgcolor=th.BG_CARD,
            border=ft.border.all(1, th.BORDER_CARD),
            border_radius=12, padding=18)

    return ft.Column([
        ui.page_header("Аналитика", "Охваты и вовлечённость по площадкам"),
        ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Icon(ft.Icons.INSIGHTS_OUTLINED, size=30,
                                    color=th.TEXT_DIM),
                    width=64, height=64, border_radius=16,
                    border=ft.border.all(1, th.BORDER_STRONG),
                    alignment=ft.alignment.center),
                ft.Column([
                    ft.Text("Данные появятся позже", font_family=th.FONT_HEAD,
                            size=19, weight=ft.FontWeight.W_600,
                            text_align=ft.TextAlign.CENTER),
                    ft.Container(
                        content=ft.Text(
                            "Раздел зарезервирован под статистику публикаций. "
                            "Реальные метрики с Pinterest и Boosty подключим "
                            "в следующих итерациях.",
                            size=14, color=th.TEXT_FAINT,
                            text_align=ft.TextAlign.CENTER),
                        width=420),
                ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(
                    content=ft.Row([stat("Охват"), stat("Клики"), stat("Реакции")],
                                   spacing=14, alignment=ft.MainAxisAlignment.CENTER),
                    opacity=0.5, margin=ft.margin.only(top=6)),
            ], spacing=18, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER),
            alignment=ft.alignment.center, expand=True, padding=40),
    ], spacing=0, expand=True)
