"""Автоопределение IMAP-сервера по адресу почты.

Чтобы для нового аккаунта Boosty не приходилось вручную вводить хост и порт
IMAP, параметры популярных провайдеров захардкожены, а для остальных берётся
разумная эвристика ``imap.<домен>:993`` (её всегда можно переопределить в
дополнительных настройках аккаунта).
"""

from __future__ import annotations

_DEFAULT_PORT = 993

_PROVIDERS: dict[str, tuple[str, int]] = {
    "gmail.com": ("imap.gmail.com", 993),
    "googlemail.com": ("imap.gmail.com", 993),
    "yandex.ru": ("imap.yandex.ru", 993),
    "yandex.com": ("imap.yandex.ru", 993),
    "ya.ru": ("imap.yandex.ru", 993),
    "yandex.by": ("imap.yandex.ru", 993),
    "yandex.kz": ("imap.yandex.ru", 993),
    "mail.ru": ("imap.mail.ru", 993),
    "inbox.ru": ("imap.mail.ru", 993),
    "list.ru": ("imap.mail.ru", 993),
    "bk.ru": ("imap.mail.ru", 993),
    "internet.ru": ("imap.mail.ru", 993),
    "outlook.com": ("outlook.office365.com", 993),
    "hotmail.com": ("outlook.office365.com", 993),
    "live.com": ("outlook.office365.com", 993),
    "msn.com": ("outlook.office365.com", 993),
    "icloud.com": ("imap.mail.me.com", 993),
    "me.com": ("imap.mail.me.com", 993),
    "mac.com": ("imap.mail.me.com", 993),
    "rambler.ru": ("imap.rambler.ru", 993),
    "ro.ru": ("imap.rambler.ru", 993),
    "lenta.ru": ("imap.rambler.ru", 993),
    "autorambler.ru": ("imap.rambler.ru", 993),
    "fastmail.com": ("imap.fastmail.com", 993),
    "zoho.com": ("imap.zoho.com", 993),
    "gmx.com": ("imap.gmx.com", 993),
    "gmx.net": ("imap.gmx.net", 993),
    "aol.com": ("imap.aol.com", 993),
}


def domain(email: str) -> str:
    return email.split("@", 1)[1].strip().lower() if "@" in email else ""


def is_known(email: str) -> bool:
    return domain(email) in _PROVIDERS


def imap_settings(email: str) -> tuple[str, int]:
    """(хост, порт) IMAP по адресу почты; для незнакомого домена — эвристика."""
    dom = domain(email)
    if dom in _PROVIDERS:
        return _PROVIDERS[dom]
    return (f"imap.{dom}" if dom else "", _DEFAULT_PORT)
