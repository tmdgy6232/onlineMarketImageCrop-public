# -*- coding: utf-8 -*-
"""다이나핏 어댑터 (케이빌리지 공식몰).

조사 결과 전문: docs/sites/dynafit.md

요약: 다이나핏 판권사(K2코리아 그룹) 공식몰 케이빌리지의 상품 페이지는 서버 렌더링이라
평문 HTML 1회로 끝난다. 상세 HTML 블록의 상품 단독 컷(_DF_nn)만 쓴다.

    https://www.k-village.co.kr/goods/YWU25232Z2
    상세 블록 <img src=".../YWU25232Z2_DF_01.JPG/k2dims/optimize">
      → 접미사를 떼면 원본 1500x2000
"""

import html as html_lib
import logging
import re

from .base import ProductInfo, ProductNotFound, SiteAdapter

log = logging.getLogger(__name__)

# 상세 HTML 블록. 같은 주석 블록이 두 번 나오는데 두 번째는 비어 있어 첫 번째만 본다.
_DETAIL_BLOCK = re.compile(
    r"<!--\s*상품 상세 HTML START\s*-->(.*?)<!--\s*상품 상세 HTML END\s*-->", re.S
)
_IMG_SRC = re.compile(r"<img[^>]+src\s*=\s*[\"']([^\"']+)[\"']", re.I)

# 리사이즈 접미사. 떼면 원본이다.
#   .../YWU25232Z2_DF_01.JPG/k2dims/resize/520/...  →  .../YWU25232Z2_DF_01.JPG
_K2DIMS = re.compile(r"(\.(?:jpe?g|png))/k2dims/.*$", re.I)

_OG_TITLE = re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', re.I)

# 없는 코드면 HTTP 200 으로 사이트 기본 제목의 페이지를 준다.
_SITE_TITLE_PREFIX = "K.VILLAGE"


class DynafitAdapter(SiteAdapter):
    """다이나핏 (케이빌리지 k-village.co.kr)."""

    name = "dynafit"

    # 서버 렌더링 HTML. Chromium 불필요.
    needs_browser = False

    PRODUCT_URL = "https://www.k-village.co.kr/goods/{code}"

    def get_product_url(self, code: str) -> str:
        return self.PRODUCT_URL.format(code=code.strip())

    def _fetch_product(self, code: str) -> ProductInfo:
        page = self.ctx.http.get_html(self.get_product_url(code))

        urls = self._parse_images(page, code)
        if not urls:
            raise ProductNotFound(f"케이빌리지에 상품 없음 (상품 컷을 찾지 못함): {code}")

        # 대표 = DF_01 (상세 첫 컷, 흰 배경). 갤러리 첫 장(og:image)은 모델컷인 상품이 있어 쓰지 않는다.
        return ProductInfo(image_urls=urls, name=self._parse_name(page, code))

    # ------------------------------------------------------------- 내부

    @classmethod
    def _parse_images(cls, page: str, code: str) -> list[str]:
        """상세 블록의 <img> 중 이 상품의 _DF_nn 컷만, 위→아래 순서로.

        화이트리스트라 모델컷(_DM_nn), RFID 정품인증, 이벤트 배너는 자동으로 빠진다.
        """
        block = _DETAIL_BLOCK.search(page)
        if not block:
            return []
        own_cut = re.compile(rf"/{re.escape(code.strip())}_DF_\d+\.(?:jpe?g|png)$", re.I)
        urls = []
        for src in _IMG_SRC.findall(block.group(1)):
            src = _K2DIMS.sub(r"\1", html_lib.unescape(src).strip())
            if src.startswith("//"):
                src = "https:" + src
            if own_cut.search(src):
                urls.append(src)
        return cls.dedupe(urls)

    @staticmethod
    def _parse_name(page: str, code: str) -> str:
        """og:title. 브랜드 머리말·품번 꼬리가 없어 그대로 쓴다. 끝의 (색상명)도 남긴다."""
        match = _OG_TITLE.search(page)
        name = html_lib.unescape(match.group(1)).strip() if match else ""
        if not name or name.startswith(_SITE_TITLE_PREFIX):
            log.warning("케이빌리지에서 상품명을 찾지 못했습니다: %s", code)
            return ""
        return name
