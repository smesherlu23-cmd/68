"""Centurio — система кросспостинга контента (Pinterest, Boosty).

Точка входа desktop-приложения Flet: единая кодовая база интерфейса
и логики на Python, локальная БД SQLite, фоновый планировщик APScheduler.
"""

from __future__ import annotations

import flet as ft

from app import APP_NAME
from app.core import logger as app_logger
from app.core.accounts import AccountService
from app.core.auth import Auth
from app.core.database import Database
from app.core.scheduler import PostScheduler
from app.core.service import CrosspostService
from app.ui import theme
from app.ui.app import CenturioApp


def main(page: ft.Page) -> None:
    db = Database()
    app_logger.bind_database(db)
    app_logger.log_event("app", "Приложение запущено")

    auth = Auth(db)
    accounts = AccountService(db)
    service = CrosspostService(db)
    scheduler = PostScheduler(service)
    scheduler.start()

    theme.apply(page)
    page.title = APP_NAME
    try:
        page.window.width = 1320
        page.window.height = 860
        page.window.min_width = 1080
        page.window.min_height = 680
        page.window.title_bar_hidden = True
        page.window.center()
    except Exception:
        pass

    def on_disconnect(_):
        scheduler.shutdown()
        app_logger.log_event("app", "Приложение остановлено")

    page.on_disconnect = on_disconnect

    CenturioApp(page, db, service, auth, accounts).mount()


if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
