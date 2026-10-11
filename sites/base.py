# -*- coding: utf-8 -*-
"""사이트 어댑터 공통 인터페이스.

새 사이트를 추가할 때는 이 클래스를 상속해서
`get_product_url()` 과 `_fetch_image_urls()` 두 개만 구현하면 된다.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ProductInfo:
    """상품 페이지에서 뽑아낸 정보.

    페이지를 한 번만 받기 위해 어댑터가 이 묶음으로 반환하고, base 가 캐시한다.
    """

    image_urls: list[str] = field(default_factory=list)  # 위→아래 순서
    name: str = ""                                       # 상품명 (양식 헤더에 쓴다)
    note: str = ""                                       # 결과 리포트에 남길 메모 (예: 색상 자동 매칭)


class ProductNotFound(Exception):
    """상품 페이지는 열렸지만 이미지를 찾을 수 없을 때.

    품절/삭제된 상품은 보통 여기로 떨어진다. 실패로 기록하고 다음 상품으로 넘어간다.
    """


class SiteAdapter(ABC):
    """사이트별 이미지 URL 추출기.

    이미지 가공(리사이즈, 이어붙이기)은 사이트와 무관하므로 여기서 다루지 않는다.
    이 클래스의 책임은 '상품코드 → 이미지 URL 목록'뿐이다.
    """

    # 레지스트리 키이자 엑셀 '사이트' 컬럼에 적는 이름
    name: str = ""

    # 평문 HTML로 추출이 불가능해 브라우저 렌더링이 필요한 사이트만 True.
    # 런너는 이 값을 보고 Chromium 기동 여부를 판단한다.
    needs_browser: bool = False

    def __init__(self, ctx):
        """ctx: core.fetcher.FetchContext — HTTP / 브라우저 가져오기 수단."""
        self.ctx = ctx
        # 상품코드 → ProductInfo. 페이지를 두 번 받지 않기 위한 캐시다.
        self._cache: dict[str, ProductInfo] = {}

    # ------------------------------------------------------------ 구현 대상

    @abstractmethod
    def get_product_url(self, code: str) -> str:
        """상품 상세 페이지 URL."""

    @abstractmethod
    def _fetch_product(self, code: str) -> ProductInfo:
        """상품 페이지에서 이미지 URL(위→아래 순서)과 상품명을 뽑는다.

        페이지 요청은 이 메서드 안에서 1회만 일어나야 한다.
        제외 규칙(사이즈표, 브랜드 개런티, 배너, 추천상품 등)도 여기서 적용한다.
        찾지 못하면 ProductNotFound 를 던진다.
        """

    # -------------------------------------------------- 공개 인터페이스

    def get_main_image_url(self, code: str) -> str:
        """대표이미지 URL. 기본값은 첫 번째 이미지다."""
        urls = self._product(code).image_urls
        if not urls:
            raise ProductNotFound(f"대표이미지를 찾을 수 없습니다: {code}")
        return urls[0]

    def get_detail_image_urls(self, code: str) -> list[str]:
        """상세이미지 URL 목록(위→아래 순서)."""
        return list(self._product(code).image_urls)

    def get_product_name(self, code: str) -> str:
        """상품명. 상세 상단 양식에 쓴다.

        뽑지 못하는 사이트는 빈 문자열을 반환한다. 그 경우 양식의 상품명 줄은 비게 된다.
        """
        return self._product(code).name

    def get_note(self, code: str) -> str:
        """결과 리포트 메시지 칸에 남길 메모. 없으면 빈 문자열."""
        return self._product(code).note

    # 대표와 상세의 출처가 다른 사이트는 위 메서드들을 오버라이드하면 된다.

    # ------------------------------------------------------------- 내부

    def _product(self, code: str) -> ProductInfo:
        """캐시를 거쳐 상품 정보를 가져온다.

        get_main_image_url() / get_detail_image_urls() / get_product_name() 를
        모두 호출해도 실제 페이지 요청은 상품당 1회만 발생한다.
        """
        if code not in self._cache:
            self._cache[code] = self._fetch_product(code)
        return self._cache[code]

    def clear_cache(self, code: str | None = None) -> None:
        """캐시 비우기. 상품 수가 많을 때 메모리 정리용."""
        if code is None:
            self._cache.clear()
        else:
            self._cache.pop(code, None)

    @staticmethod
    def dedupe(urls):
        """순서를 지키면서 중복 URL을 제거한다."""
        seen = set()
        result = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                result.append(url)
        return result

    def __repr__(self):
        return f"<{type(self).__name__} name={self.name!r}>"
