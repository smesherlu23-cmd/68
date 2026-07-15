"""Журнал технических событий: файл + таблица logs в БД."""

from __future__ import annotations

import logging
from pathlib import Path

from .paths import data_dir

_LOG_FILE = data_dir() / "centurio.log"

_db = None


def bind_database(db) -> None:
    global _db
    _db = db


def get_logger(name: str = "centurio") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


def log_event(source: str, message: str, level: str = "INFO") -> None:
    """Пишет событие и в файл, и в БД (если она уже подключена)."""
    logger = get_logger(source)
    logger.log(getattr(logging, level, logging.INFO), message)
    if _db is not None:
        try:
            _db.add_log(level, source, message)
        except Exception:
            logger.exception("Не удалось записать лог в БД")


def log_file_path() -> Path:
    return _LOG_FILE
