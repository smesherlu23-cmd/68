"""Адаптер Boosty.

Официального публичного API у Boosty нет (см. ТЗ, раздел 8 — доступность
уточняется на этапе аналитики). Адаптер использует механизм публикации
веб-клиента boosty.to. В настройках задаются только имя блога и данные для
входа (email/пароль Boosty и почта для кода 2FA); сам Bearer-токен сессии
адаптер получает автоматически (см. boosty_login) и обновляет при истечении.
Формат запроса может меняться со стороны Boosty — все ошибки фиксируются
в журнале и не влияют на публикацию на других площадках.
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path

import requests

from ..core import mail_providers, secrets
from ..core.logger import log_event
from ..core.models import Account, Post
from . import boosty_login
from .base import CredentialField, PlatformAdapter, PublishResult

API_BASE = "https://api.boosty.to/v1"


class BoostyAdapter(PlatformAdapter):
    key = "boosty"
    name = "Boosty"
    letter = "B"

    def credential_fields(self) -> list[CredentialField]:
        # Для нового аккаунта достаточно email и пароля Boosty — всё остальное
        # (токен, имя блога, параметры IMAP, логин почты) определяется само.
        return [
            CredentialField("token", "Bearer-токен сессии", password=True,
                            auto_managed=True),
            CredentialField("login_email", "Email аккаунта Boosty",
                            hint="через него выполняется вход и приходит код"),
            CredentialField("login_password", "Пароль Boosty", password=True),
            CredentialField("mail_password", "Пароль приложения для почты",
                            password=True, optional=True,
                            hint="нужен, если у почты включена 2FA; "
                                 "иначе оставьте пустым"),
            # дополнительно — обычно определяется автоматически
            CredentialField("blog", "Имя блога (boosty.to/имя)",
                            optional=True, advanced=True,
                            hint="определяется автоматически после входа"),
            CredentialField("mail_host", "IMAP-сервер почты",
                            optional=True, advanced=True,
                            hint="по умолчанию — по домену почты"),
            CredentialField("mail_port", "IMAP-порт",
                            optional=True, advanced=True, hint="по умолчанию 993"),
            CredentialField("mail_user", "Логин почты (IMAP)",
                            optional=True, advanced=True,
                            hint="по умолчанию совпадает с email аккаунта"),
        ]

    def account_ready(self, account_id: str) -> bool:
        """Готов к публикации, если настроен автовход (email + пароль) — тогда
        токен и имя блога получатся автоматически — либо всё уже задано вручную."""
        if self._cred(account_id, "token") and self._cred(account_id, "blog"):
            return True
        return self.auto_login_configured(account_id)

    def validate(self, post: Post) -> list[str]:
        if post.title.strip() or post.text_for(self.key).strip():
            return []
        return ["заголовок или текст"]

    def publish(self, post: Post, account: Account) -> PublishResult:
        token = self._cred(account.id, "token")
        blog = self._cred(account.id, "blog")
        if not token or not blog:
            # чего-то не хватает (первая публикация или истёк токен) —
            # автовход добудет и токен, и имя блога автоматически
            if not self.auto_login_configured(account.id):
                return PublishResult(
                    ok=False, error="не настроен вход в Boosty (email и пароль)")
            ok, message = self.auto_login(account.id)
            if not ok:
                return PublishResult(ok=False,
                                     error=f"автовход не выполнен: {message}")
            token = self._cred(account.id, "token")
            blog = self._cred(account.id, "blog")
        if not blog:
            return PublishResult(
                ok=False,
                error="не удалось определить блог — укажите его в дополнительных настройках")

        result, expired = self._try_publish(post, blog, token)
        if not expired:
            return result

        # токен истёк — обновляем его автовходом и повторяем публикацию
        ok, message = self.auto_login(account.id)
        if not ok:
            log_event("boosty", f"Токен истёк, автовход не выполнен: {message}",
                      "ERROR")
            return result
        log_event("boosty", "Токен истёк — выполнен автоматический повторный вход")
        token = self._cred(account.id, "token")
        result, _ = self._try_publish(post, blog, token)
        return result

    def _try_publish(self, post: Post, blog: str,
                     token: str) -> tuple[PublishResult, bool]:
        """Возвращает (результат, истёк_ли_токен) — второе используется, чтобы
        решить, стоит ли пробовать автовход и повтор."""
        headers = {"Authorization": f"Bearer {token}"}
        try:
            data_blocks = self._blocks(post, headers, blog)
            form = {
                "title": post.title,
                "data": json.dumps(data_blocks, ensure_ascii=False),
                "price": 0,
                "teaser_data": "[]",
                "deny_comments": "false",
                "has_chat": "false",
            }
            resp = requests.post(f"{API_BASE}/blog/{blog}/post/",
                                 data=form, headers=headers, timeout=60)
            if resp.status_code in (200, 201):
                post_id = resp.json().get("id", "")
                url = f"https://boosty.to/{blog}/posts/{post_id}" if post_id else ""
                log_event("boosty", f"Пост опубликован: {post_id}")
                return PublishResult(ok=True, external_url=url), False
            return (PublishResult(ok=False, error=self._api_error(resp)),
                   resp.status_code == 401)
        except requests.RequestException as exc:
            log_event("boosty", f"Сетевая ошибка: {exc}", "ERROR")
            return PublishResult(ok=False, error=f"сетевая ошибка: {exc}"), False
        except Exception as exc:  # noqa: BLE001 — ошибка одной площадки не должна ронять остальные
            log_event("boosty", f"Неожиданная ошибка: {exc}", "ERROR")
            return PublishResult(ok=False, error=str(exc)), False

    # ---------- автовход с email-2FA ----------

    def _cred(self, account_id: str, key: str) -> str:
        return secrets.get_secret(secrets.account_secret(account_id, key)) or ""

    def auto_login_configured(self, account_id: str) -> bool:
        """Для автовхода достаточно email и пароля Boosty — параметры почты
        (сервер, порт, логин) выводятся автоматически."""
        return bool(self._cred(account_id, "login_email")
                   and self._cred(account_id, "login_password"))

    def _mail_config(self, account_id: str) -> tuple[str, int, str, str, str]:
        """Собирает параметры почты для кода 2FA, подставляя разумные значения:
        логин почты = email аккаунта, сервер/порт — по домену, пароль почты —
        пароль Boosty, если отдельный не задан."""
        email = self._cred(account_id, "login_email")
        password = self._cred(account_id, "login_password")
        mail_user = self._cred(account_id, "mail_user") or email
        mail_password = self._cred(account_id, "mail_password") or password
        host = self._cred(account_id, "mail_host")
        port_raw = self._cred(account_id, "mail_port")
        auto_host, auto_port = mail_providers.imap_settings(mail_user)
        host = host or auto_host
        try:
            port = int(port_raw) if port_raw else auto_port
        except ValueError:
            port = auto_port
        return host, port, mail_user, mail_password, email

    def auto_login(self, account_id: str) -> tuple[bool, str]:
        """Проходит вход + email-2FA на boosty.to, сохраняет свежий токен и,
        если имя блога ещё не задано, определяет и сохраняет его."""
        if not self.auto_login_configured(account_id):
            return False, "укажите email и пароль Boosty"

        host, port, mail_user, mail_password, email = self._mail_config(account_id)
        if not host:
            return False, ("не удалось определить IMAP-сервер почты — "
                           "укажите его в дополнительных настройках")

        try:
            token, _cookies, blog = boosty_login.auto_login(
                email, self._cred(account_id, "login_password"),
                host, port, mail_user, mail_password)
        except boosty_login.BoostyLoginError as exc:
            log_event("boosty", f"Автовход не выполнен: {exc}", "ERROR")
            return False, str(exc)
        except Exception as exc:  # noqa: BLE001 — не должно ронять публикацию
            log_event("boosty", f"Автовход: неожиданная ошибка: {exc}", "ERROR")
            return False, str(exc)

        secrets.set_secret(secrets.account_secret(account_id, "token"), token)
        if blog and not self._cred(account_id, "blog"):
            secrets.set_secret(secrets.account_secret(account_id, "blog"), blog)
            log_event("boosty", f"Определён блог аккаунта: {blog}")
        return True, "Вход выполнен, токен обновлён"

    def _blocks(self, post: Post, headers: dict, blog: str) -> list[dict]:
        """Собирает блоки контента поста: текст + загруженные медиа."""
        blocks: list[dict] = []
        text = post.text_for(self.key).strip()
        if text:
            blocks.append({
                "type": "text",
                "content": json.dumps([text, "unstyled", []], ensure_ascii=False),
                "modificator": "",
            })
        for path in post.media:
            uploaded = self._upload_media(path, headers, blog)
            if uploaded:
                blocks.append(uploaded)
        return blocks

    @staticmethod
    def _upload_media(path: str, headers: dict, blog: str) -> dict | None:
        p = Path(path)
        if not p.exists():
            return None
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        try:
            with p.open("rb") as fh:
                resp = requests.post(
                    f"{API_BASE}/blog/{blog}/media/",
                    files={"file": (p.name, fh, ctype)},
                    headers=headers, timeout=300)
            if resp.status_code in (200, 201):
                data = resp.json()
                kind = "image" if ctype.startswith("image/") else (
                    "ok_video" if ctype.startswith("video/") else "file")
                return {"type": kind, "id": data.get("id", ""),
                        "url": data.get("url", "")}
        except requests.RequestException as exc:
            log_event("boosty", f"Ошибка загрузки медиа {p.name}: {exc}", "ERROR")
        return None

    @staticmethod
    def _api_error(resp: requests.Response) -> str:
        try:
            message = resp.json().get("error_description",
                                      resp.json().get("error", resp.text[:200]))
        except ValueError:
            message = resp.text[:200]
        if resp.status_code == 401:
            return "истёк токен доступа"
        return f"API {resp.status_code}: {message}"
