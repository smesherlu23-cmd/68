"""Расположение локальных данных приложения (БД, логи, секреты)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    """Каталог данных рядом с приложением; при сборке в exe — рядом с бинарником."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(os.environ.get("CENTURIO_DATA_DIR", Path(__file__).resolve().parents[2]))
    d = base / "storage"
    d.mkdir(parents=True, exist_ok=True)
    return d
