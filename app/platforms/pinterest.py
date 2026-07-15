"""Адаптер Pinterest: публикация пинов через Pinterest API v5.

Пин = изображение + заголовок + описание + целевая ссылка + доска.
Токен доступа хранится в защищённом хранилище (см. core.secrets).
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

import requests

from ..core import secrets
from ..core.logger import log_event
from ..core.models import Account, Post
from .base import CredentialField, PlatformAdapter, PublishResult

API_BASE = "https://api.pinterest.com/v5"
_IMAGE_TYPES = {"image/jpeg", "image/png"}


class PinterestAdapter(PlatformAdapter):
    key = "pinterest"
    name = "Pinterest"
    letter = "P"

    # лимиты Pinterest API v5 (используются в UI для счётчиков символов)
    TITLE_LIMIT = 100
    TEXT_LIMIT = 800

    def credential_fields(self) -> list[CredentialField]:
        return [CredentialField(
            "token", "Токен доступа Pinterest API v5", password=True,
            hint="scope boards:read, pins:write")]

    def validate(self, post: Post) -> list[str]:
        missing = []
        if not post.title.strip():
            missing.append("заголовок")
        if not self.valid_link(post.link):
            missing.append("ссылка")
        if not post.board.strip():
            missing.append("доска")
        if not self.has_image(post):
            missing.append("изображение")
        return missing

    @staticmethod
    def valid_link(link: str) -> bool:
        """Ссылка пина должна быть корректным http(s)-URL."""
        link = (link or "").strip().lower()
        return link.startswith("http://") or link.startswith("https://")

    @staticmethod
    def has_image(post: Post) -> bool:
        """У пина обязательно есть изображение (Pinterest принимает JPEG/PNG)."""
        return any(mimetypes.guess_type(p)[0] in _IMAGE_TYPES
                   for p in post.media)

    def publish(self, post: Post, account: Account) -> PublishResult:
        token = secrets.get_secret(secrets.account_secret(account.id, "token"))
        if not token:
            return PublishResult(ok=False, error="токен доступа не настроен")
        headers = {"Authorization": f"Bearer {token}"}
        try:
            board_id = self._find_board(headers, post.board)
            if board_id is None:
                return PublishResult(ok=False, error=f"доска «{post.board}» не найдена")

            body = {
                "board_id": board_id,
                "title": post.title[:self.TITLE_LIMIT],
                "description": post.text_for(self.key)[:self.TEXT_LIMIT],
                "link": post.link,
            }
            media = self._image_source(post)
            if media is None:
                return PublishResult(
                    ok=False,
                    error="нужно изображение (JPEG/PNG) — пин без медиа невозможен")
            body["media_source"] = media

            resp = requests.post(f"{API_BASE}/pins", json=body, headers=headers, timeout=60)
            if resp.status_code in (200, 201):
                pin_id = resp.json().get("id", "")
                url = f"https://www.pinterest.com/pin/{pin_id}/" if pin_id else ""
                log_event("pinterest", f"Пин опубликован: {pin_id}")
                return PublishResult(ok=True, external_url=url)
            return PublishResult(ok=False, error=self._api_error(resp))
        except requests.RequestException as exc:
            log_event("pinterest", f"Сетевая ошибка: {exc}", "ERROR")
            return PublishResult(ok=False, error=f"сетевая ошибка: {exc}")
        except Exception as exc:  # noqa: BLE001 — ошибка одной площадки не должна ронять остальные
            log_event("pinterest", f"Неожиданная ошибка: {exc}", "ERROR")
            return PublishResult(ok=False, error=str(exc))

    def _find_board(self, headers: dict, board_name: str) -> str | None:
        """Ищет доску по имени (без учёта регистра), с постраничным обходом."""
        bookmark = None
        for _ in range(10):
            params = {"page_size": 100}
            if bookmark:
                params["bookmark"] = bookmark
            resp = requests.get(f"{API_BASE}/boards", headers=headers,
                                params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("items", []):
                if item.get("name", "").strip().lower() == board_name.strip().lower():
                    return item["id"]
            bookmark = data.get("bookmark")
            if not bookmark:
                break
        return None

    @staticmethod
    def _image_source(post: Post) -> dict | None:
        for path in post.media:
            ctype = mimetypes.guess_type(path)[0]
            if ctype in _IMAGE_TYPES and Path(path).exists():
                data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
                return {"source_type": "image_base64",
                        "content_type": ctype, "data": data}
        return None

    @staticmethod
    def _api_error(resp: requests.Response) -> str:
        try:
            message = resp.json().get("message", resp.text[:200])
        except ValueError:
            message = resp.text[:200]
        if resp.status_code == 401:
            return "истёк токен доступа"
        return f"API {resp.status_code}: {message}"
