"""Экран «История публикаций»: статус каждой публикации по площадкам."""

from __future__ import annotations

import flet as ft

from ...core.models import Publication, PublicationStatus
from ...platforms import get_adapter
from .. import components as ui
from .. import format as fmt
from .. import theme as th

_COLS = (1.7, 1.0, 1.0, 1.1)


def build(app) -> ft.Control:
    pubs = app.db.history()

    header = ft.Container(
        content=ft.Row([
            _hcell("Пост", _COLS[0]), _hcell("Аккаунт", _COLS[1]),
            _hcell("Опубликован", _COLS[2]), _hcell("Статус", _COLS[3]),
        ], spacing=0),
        padding=ft.padding.only(16, 0, 16, 12),
        border=ft.border.only(bottom=ft.BorderSide(1, th.white(0.07))))

    rows: list[ft.Control] = [header]
    for pub in pubs:
        rows.append(_row(app, pub))

    if not pubs:
        rows = [ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.HISTORY, size=30, color=th.TEXT_DIM),
                ft.Text("Публикаций пока нет", size=15,
                        weight=ft.FontWeight.W_600, color=th.TEXT_GRAY),
                ft.Text("Здесь появится статус каждой публикации",
                        size=13, color=th.TEXT_LABEL),
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            alignment=ft.alignment.center, expand=True)]

    return ft.Column([
        ui.page_header("История публикаций", "Статус каждой публикации по площадкам"),
        ft.Container(
            content=ft.Column(rows, spacing=0, scroll=ft.ScrollMode.AUTO, expand=True),
            padding=ft.padding.symmetric(20, 30), expand=True),
    ], spacing=0, expand=True)


def _hcell(text: str, weight: float) -> ft.Container:
    return ft.Container(content=ui.mono_label(text), expand=int(weight * 10))


def _row(app, pub: Publication) -> ft.Container:
    status = _status_cell(pub)
    row = ft.Container(
        content=ft.Row([
            ft.Container(
                content=ft.Text(pub.post_title or "Без названия", size=14,
                                weight=ft.FontWeight.W_600, max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS),
                expand=int(_COLS[0] * 10),
                padding=ft.padding.only(right=12)),
            ft.Container(
                content=ft.Column([
                    ft.Text(pub.account_name or "—", size=14, color=th.TEXT_MUTED,
                            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(get_adapter(pub.platform).name, size=11.5,
                            color=th.TEXT_FAINT),
                ], spacing=1),
                expand=int(_COLS[1] * 10),
                padding=ft.padding.only(right=12)),
            ft.Container(
                content=ft.Text(fmt.short_datetime(pub.published_at),
                                size=12.5, color=th.TEXT_GRAY,
                                font_family=th.FONT_MONO),
                expand=int(_COLS[2] * 10)),
            ft.Container(content=status, expand=int(_COLS[3] * 10),
                         padding=ft.padding.only(right=8)),
        ], spacing=0),
        padding=ft.padding.symmetric(15, 16), border_radius=8,
        border=ft.border.only(bottom=ft.BorderSide(1, th.white(0.05))))
    ui.hover_style(row, lambda c, h: setattr(c, "bgcolor",
                                             th.white(0.02) if h else None))
    if pub.external_url:
        row.on_click = lambda e, url=pub.external_url: app.page.launch_url(url)
        row.tooltip = pub.external_url
    elif pub.error:
        row.tooltip = pub.error
    return row


def _status_cell(pub: Publication) -> ft.Control:
    if pub.status == PublicationStatus.SUCCESS:
        return ui.status_dot(th.SUCCESS, "Успешно", th.SUCCESS_TEXT, text_size=14)
    if pub.status == PublicationStatus.ERROR:
        short = pub.error.split(":")[0] if pub.error else "ошибка"
        cell = ui.status_dot(th.ERROR, f"Ошибка · {short}", th.ERROR_TEXT2,
                             text_size=14)
        cell.tight = False
        label = cell.controls[1]
        label.max_lines = 1
        label.overflow = ft.TextOverflow.ELLIPSIS
        label.expand = True
        return cell
    return ui.status_dot(th.TEXT_DIM, "В процессе…", th.TEXT_GRAY, text_size=14)
