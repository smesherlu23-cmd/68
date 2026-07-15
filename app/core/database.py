"""Локальная база данных SQLite: посты, аккаунты, публикации, логи, настройки."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from typing import Optional

from .models import Account, Post, Publication, PublicationStatus
from .paths import data_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '',
    link TEXT NOT NULL DEFAULT '',
    board TEXT NOT NULL DEFAULT '',
    media TEXT NOT NULL DEFAULT '[]',
    platform TEXT NOT NULL DEFAULT '',
    accounts TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    scheduled_at TEXT
);
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS publications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    account_id TEXT NOT NULL DEFAULT '',
    account_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queue',
    published_at TEXT,
    error TEXT NOT NULL DEFAULT '',
    external_url TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    source TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Столбцы, добавленные в новой (мультиаккаунтной) схеме, — для миграции
# баз, созданных прошлыми версиями приложения.
_MIGRATIONS = {
    "posts": {
        "platform": "TEXT NOT NULL DEFAULT ''",
        "accounts": "TEXT NOT NULL DEFAULT '[]'",
    },
    "publications": {
        "account_id": "TEXT NOT NULL DEFAULT ''",
        "account_name": "TEXT NOT NULL DEFAULT ''",
    },
}

_FMT = "%Y-%m-%d %H:%M:%S"


def _dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.strptime(value, _FMT) if value else None


def _ts(value: Optional[datetime]) -> Optional[str]:
    return value.strftime(_FMT) if value else None


class Database:
    """Потокобезопасная обёртка над SQLite (одно соединение + lock)."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or str(data_dir() / "centurio.db")
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)
            self._migrate()

    def _migrate(self) -> None:
        """Добавляет недостающие столбцы в БД, созданные прошлыми версиями."""
        for table, columns in _MIGRATIONS.items():
            existing = {r["name"] for r in
                        self._conn.execute(f"PRAGMA table_info({table})")}
            for name, decl in columns.items():
                if name not in existing:
                    self._conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

    # ---------- посты ----------

    def save_post(self, post: Post) -> Post:
        with self._lock, self._conn:
            if post.created_at is None:
                post.created_at = datetime.now()
            row = (
                post.title, post.text, post.link, post.board,
                post.media_json(), post.platform, post.accounts_json(),
                post.status, _ts(post.created_at), _ts(post.scheduled_at),
            )
            if post.id is None:
                cur = self._conn.execute(
                    "INSERT INTO posts (title, text, link, board,"
                    " media, platform, accounts, status, created_at, scheduled_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)", row)
                post.id = cur.lastrowid
            else:
                self._conn.execute(
                    "UPDATE posts SET title=?, text=?, link=?, board=?,"
                    " media=?, platform=?, accounts=?, status=?, created_at=?,"
                    " scheduled_at=? WHERE id=?", row + (post.id,))
        return post

    def get_post(self, post_id: int) -> Optional[Post]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        return self._row_to_post(row) if row else None

    def scheduled_posts(self) -> list[Post]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM posts WHERE status='scheduled' ORDER BY scheduled_at").fetchall()
        return [self._row_to_post(r) for r in rows]

    def set_post_status(self, post_id: int, status: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE posts SET status=? WHERE id=?", (status, post_id))

    @staticmethod
    def _row_to_post(row: sqlite3.Row) -> Post:
        return Post(
            id=row["id"], title=row["title"], text=row["text"], link=row["link"],
            board=row["board"], media=json.loads(row["media"]),
            platform=row["platform"], accounts=json.loads(row["accounts"]),
            status=row["status"], created_at=_dt(row["created_at"]),
            scheduled_at=_dt(row["scheduled_at"]),
        )

    # ---------- аккаунты ----------

    def save_account(self, account: Account) -> Account:
        with self._lock, self._conn:
            if account.created_at is None:
                account.created_at = datetime.now()
            self._conn.execute(
                "INSERT INTO accounts (id, platform, name, created_at)"
                " VALUES (?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET platform=excluded.platform,"
                " name=excluded.name",
                (account.id, account.platform, account.name,
                 _ts(account.created_at)))
        return account

    def get_account(self, account_id: str) -> Optional[Account]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        return self._row_to_account(row) if row else None

    def accounts(self, platform: Optional[str] = None) -> list[Account]:
        with self._lock:
            if platform:
                rows = self._conn.execute(
                    "SELECT * FROM accounts WHERE platform=? ORDER BY created_at",
                    (platform,)).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM accounts ORDER BY platform, created_at").fetchall()
        return [self._row_to_account(r) for r in rows]

    def delete_account(self, account_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))

    @staticmethod
    def _row_to_account(row: sqlite3.Row) -> Account:
        return Account(
            id=row["id"], platform=row["platform"], name=row["name"],
            created_at=_dt(row["created_at"]),
        )

    # ---------- публикации ----------

    def add_publication(self, post_id: int, platform: str, account_id: str = "",
                        account_name: str = "",
                        status: str = PublicationStatus.QUEUE) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO publications"
                " (post_id, platform, account_id, account_name, status)"
                " VALUES (?,?,?,?,?)",
                (post_id, platform, account_id, account_name, status))
            return cur.lastrowid

    def update_publication(self, pub_id: int, status: str, error: str = "",
                           external_url: str = "", bump_attempts: bool = False) -> None:
        with self._lock, self._conn:
            published = _ts(datetime.now()) if status == PublicationStatus.SUCCESS else None
            self._conn.execute(
                "UPDATE publications SET status=?, error=?, external_url=?,"
                " published_at=COALESCE(?, published_at),"
                " attempts=attempts + ? WHERE id=?",
                (status, error, external_url, published, 1 if bump_attempts else 0, pub_id))

    def publications_for_post(self, post_id: int) -> list[Publication]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT p.*, s.title AS post_title FROM publications p"
                " JOIN posts s ON s.id = p.post_id WHERE p.post_id=? ORDER BY p.id",
                (post_id,)).fetchall()
        return [self._row_to_pub(r) for r in rows]

    def history(self, limit: int = 200) -> list[Publication]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT p.*, s.title AS post_title FROM publications p"
                " JOIN posts s ON s.id = p.post_id"
                " ORDER BY COALESCE(p.published_at, s.created_at) DESC, p.id DESC LIMIT ?",
                (limit,)).fetchall()
        return [self._row_to_pub(r) for r in rows]

    @staticmethod
    def _row_to_pub(row: sqlite3.Row) -> Publication:
        return Publication(
            id=row["id"], post_id=row["post_id"], post_title=row["post_title"],
            platform=row["platform"], account_id=row["account_id"],
            account_name=row["account_name"], status=row["status"],
            published_at=_dt(row["published_at"]), error=row["error"],
            external_url=row["external_url"], attempts=row["attempts"],
        )

    # ---------- логи ----------

    def add_log(self, level: str, source: str, message: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO logs (ts, level, source, message) VALUES (?,?,?,?)",
                (_ts(datetime.now()), level, source, message))

    # ---------- настройки ----------

    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES (?,?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
