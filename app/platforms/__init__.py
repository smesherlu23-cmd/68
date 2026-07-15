"""Реестр адаптеров платформ.

Добавление новой площадки = новый модуль с классом-наследником
PlatformAdapter + регистрация здесь. Ядро при этом не меняется.
"""

from __future__ import annotations

from .base import PlatformAdapter, PublishResult
from .boosty import BoostyAdapter
from .pinterest import PinterestAdapter

_ADAPTERS: dict[str, PlatformAdapter] = {}


def register(adapter: PlatformAdapter) -> None:
    _ADAPTERS[adapter.key] = adapter


def get_adapter(key: str) -> PlatformAdapter:
    return _ADAPTERS[key]


def all_adapters() -> list[PlatformAdapter]:
    return list(_ADAPTERS.values())


register(PinterestAdapter())
register(BoostyAdapter())

__all__ = [
    "PlatformAdapter", "PublishResult",
    "register", "get_adapter", "all_adapters",
]
