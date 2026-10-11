# -*- coding: utf-8 -*-
"""블랙야크 어댑터 (BYN 블랙야크 공식몰).

조사 결과 전문: docs/sites/blackyak.md

요약: 상세 페이지 주소가 품번이 아닌 해시(pno)라서 검색을 한 번 거친다.
검색·상세 모두 서버 렌더링이라 평문 HTTP로 된다.
이미지는 상세 페이지 썸네일 그리드의 공식 이미지 서버(picweb.blackyak.com) 860 원본을 쓴다.

    2BYHTXV915 TP
      → 검색 search_result.php?search_str=2BYHTXV915+TP
      → 상세 detail.php?pno=...  (상품코드 2BYHTXV915TP 대조)
      → .../workbook/2026_BY/2BYHTXV915_TP/2BYHTXV915_TP_WMain_view_860_FRONT.jpg ...
"""

import html as html_lib
import logging
import re
from urllib.parse import quote_plus

from .base import ProductInfo, ProductNotFound, SiteAdapter

log = logging.getLogger(__name__)

SEARCH_URL = "https://www.byn.kr/blackyak/shop/search_result.php?search_str={query}"

# 품번 10자리 + 색상 2자리
_BASE_LEN = 10
_COLOR_LEN = 2

# 검색 결과
_TOTAL_COUNT = re.compile(r'id="listTotalCnt"[^>]*>\s*(\d+)\s*<')
_RESULT_ITEM = re.compile(
    r'<div class="prdimg">\s*<a href="([^"]*detail\.php\?pno=([0-9A-Fa-f]+)[^"]*)"[^>]*>'
    r'\s*<img src="([^"]*)"',
    re.S,
)
DETAIL_URL = "https://www.byn.kr/blackyak/shop/detail.php?pno={pno}"

# 검색 결과 중 상세 페이지를 몇 개까지 열어볼지. 정상이면 1건이다.
_MAX_CANDIDATES = 5

# 상세 페이지
_CODE_VALUE = re.compile(r'<span class="prd-desc__code-value">\s*([^<]*?)\s*</span>')
_NAME = re.compile(r'<h1 class="prd-info__name">\s*(.*?)\s*</h1>', re.S)
_THUMB_GRID = re.compile(
    r'<div class="prd-thumb__grid">(.*?)<p class="prd-thumb__notice">', re.S
)
_THUMB_ITEM = re.compile(
    r'<div class="prd-thumb__item[^"]*"\s+data-type="([^"]*)"\s*>\s*<img src="([^"]*)"', re.S
)


class BlackyakAdapter(SiteAdapter):
    """블랙야크 (byn.kr)."""

    name = "blackyak"

    # 검색·상세 모두 서버 렌더링. Chromium 불필요.
    needs_browser = False

    def get_product_url(self, code: str) -> str:
        # 상세 주소는 검색해야 알 수 있다. Referer 용으로는 검색 주소를 준다.
        base, color = self._split(code)
        return SEARCH_URL.format(query=quote_plus(f"{base} {color}"))

    def _fetch_product(self, code: str) -> ProductInfo:
        base, color = self._split(code)
        page = self._find_detail_page(code, base, color)

        urls = self._parse_images(page, base, color)
        # 이미지 서버에서 지워진 상품이 있다 (403). 실제로 있는 것만 남긴다.
        urls = [u for u in urls if self.ctx.http.exists(u)]
        if not urls or not urls[0].endswith("_FRONT.jpg"):
            raise ProductNotFound(f"블랙야크 이미지 서버에 정면 컷 없음: {code}")

        return ProductInfo(image_urls=urls, name=self._parse_name(page, code))

    # ------------------------------------------------------------- 내부

    @staticmethod
    def _split(code: str) -> tuple[str, str]:
        """'2BYHTXV915 TP' → ('2BYHTXV915', 'TP'). 붙여 쓴 것, _ 로 이은 것도 받는다."""
        compact = re.sub(r"[\s_]+", "", code.strip().upper())
        if len(compact) != _BASE_LEN + _COLOR_LEN:
            raise ProductNotFound(
                f"블랙야크 품번 형식이 아닙니다 (예: 2BYHTXV915 TP): {code}"
            )
        return compact[:_BASE_LEN], compact[_BASE_LEN:]

    def _get(self, url: str) -> str:
        # 응답에 charset 이 빠질 때가 있어 직접 UTF-8 로 읽는다.
        return self.ctx.http.get_bytes(url).decode("utf-8", errors="replace")

    def _find_detail_page(self, code: str, base: str, color: str) -> str:
        """검색 → 상세 페이지. 상세의 상품코드가 품번과 같은 것만 인정한다.

        검색 썸네일 경로만 믿으면 안 된다. 옛 품번 이미지를 재사용하는 상품이 있다.
        """
        search = self._get(self.get_product_url(code))
        total = _TOTAL_COUNT.search(search)
        items = _RESULT_ITEM.findall(search)
        if not items or (total and total.group(1) == "0"):
            raise ProductNotFound(f"블랙야크 공식몰 검색 결과 없음: {code}")

        # 썸네일 경로가 이 품번인 결과부터 본다.
        folder = f"/{base}_{color}/"
        items.sort(key=lambda item: folder not in item[2])

        want = base + color
        for _, pno, _ in items[:_MAX_CANDIDATES]:
            page = self._get(DETAIL_URL.format(pno=pno))
            found = _CODE_VALUE.search(page)
            if found and found.group(1).replace(" ", "").upper() == want:
                return page
        raise ProductNotFound(f"블랙야크 검색 결과에 같은 품번 상품 없음: {code}")

    @classmethod
    def _parse_images(cls, page: str, base: str, color: str) -> list[str]:
        """썸네일 그리드에서 이 품번의 860 상품 단독 컷만, 표시 순서대로.

        화이트리스트: FRONT → BACK → D1…Dn.
        그리드에 섞인 모델 착용컷(_fMall####_view_860_)과 동영상은 빠진다.
        """
        grid = _THUMB_GRID.search(page)
        if not grid:
            return []
        own_cut = re.compile(
            rf"/workbook/[^/]+/{base}_{color}/{base}_{color}_W(?:Main|Detail)_view_860_\w+\.jpg$",
            re.I,
        )
        urls = []
        for kind, src in _THUMB_ITEM.findall(grid.group(1)):
            if kind != "image":
                continue
            src = html_lib.unescape(src).strip().replace("http://", "https://", 1)
            if own_cut.search(src):
                urls.append(src)
        return cls.dedupe(urls)

    @staticmethod
    def _parse_name(page: str, code: str) -> str:
        """상세 페이지 상품명. 브랜드 머리말·품번 꼬리가 없어 그대로 쓴다 (#1 같은 꼬리도 유지)."""
        match = _NAME.search(page)
        name = html_lib.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip() if match else ""
        if not name:
            log.warning("블랙야크 상품명을 찾지 못했습니다: %s", code)
        return name
