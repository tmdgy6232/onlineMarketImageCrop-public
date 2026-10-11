# -*- coding: utf-8 -*-
"""사이트 어댑터 레지스트리.

새 사이트 추가 = 파일 하나 추가 + 아래 _ADAPTER_CLASSES 에 한 줄 등록.
main.py 에는 사이트별 분기가 생기지 않는다.
"""

from .base import ProductNotFound, SiteAdapter
from .bucketstore import BucketStoreAdapter
from .descente import DescenteAdapter

# 사이트 이름 → 어댑터 클래스
_ADAPTER_CLASSES = {
    cls.name: cls
    for cls in (
        BucketStoreAdapter,
        DescenteAdapter,
        # 여기에 새 어댑터를 추가한다.
    )
}


class UnknownSite(Exception):
    """엑셀에 등록되지 않은 사이트 이름이 적혀 있을 때."""


def available_sites() -> list[str]:
    """등록된 사이트 이름 목록."""
    return sorted(_ADAPTER_CLASSES)


def get_adapter_class(name: str):
    key = (name or "").strip().lower()
    if key not in _ADAPTER_CLASSES:
        raise UnknownSite(
            f"알 수 없는 사이트입니다: {name!r} "
            f"(사용 가능: {', '.join(available_sites())})"
        )
    return _ADAPTER_CLASSES[key]


class AdapterPool:
    """사이트별 어댑터 인스턴스를 재사용하기 위한 보관소.

    같은 사이트의 상품이 여러 개여도 어댑터는 1개만 만든다.
    (어댑터가 들고 있는 세션과 캐시를 공유하기 위해서다.)
    """

    def __init__(self, ctx):
        self._ctx = ctx
        self._instances: dict[str, SiteAdapter] = {}

    def get(self, name: str) -> SiteAdapter:
        key = (name or "").strip().lower()
        if key not in self._instances:
            self._instances[key] = get_adapter_class(key)(self._ctx)
        return self._instances[key]

    def __iter__(self):
        return iter(self._instances.values())


__all__ = [
    "AdapterPool",
    "ProductNotFound",
    "SiteAdapter",
    "UnknownSite",
    "available_sites",
    "get_adapter_class",
]
