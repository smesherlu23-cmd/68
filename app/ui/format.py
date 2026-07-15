"""Форматирование дат по-русски для интерфейса."""

from __future__ import annotations

from datetime import datetime

MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг",
            "Пятница", "Суббота", "Воскресенье"]


def day_label(dt: datetime) -> str:
    """«Вторник · 8 июля» — заголовок группы в расписании."""
    return f"{WEEKDAYS[dt.weekday()]} · {dt.day} {MONTHS_GEN[dt.month - 1]}"


def human_datetime(dt: datetime) -> str:
    """«8 июля в 09:00» — для подтверждения планирования."""
    return f"{dt.day} {MONTHS_GEN[dt.month - 1]} в {dt:%H:%M}"


def short_datetime(dt: datetime | None) -> str:
    """«05.07 · 10:02» — колонка истории."""
    return f"{dt:%d.%m · %H:%M}" if dt else "—"
