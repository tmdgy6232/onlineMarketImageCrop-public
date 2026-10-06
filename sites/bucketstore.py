# -*- coding: utf-8 -*-
"""버킷스토어 어댑터.

조사 결과 전문: docs/sites/bucketstore.md

요약: Next.js App Router 사이트지만 RSC 스트리밍 데이터가 평문 HTML에 그대로 들어있어
브라우저 렌더링이 필요 없다. `"imageList":[...]` 하나만 뽑으면 된다.
"""

import json
import logging
import re

from .base import ProductNotFound, SiteAdapter

log = logging.getLogger(__name__)

# RSC flight data 안에 JSON이 이스케이프된 채 박혀 있다:
#   \"imageList\":[\"https://...\",\"https://...\"]
_IMAGE_LIST_ESCAPED = re.compile(r'\\"imageList\\":(\[[^\]]*\])')

# 혹시 이스케이프되지 않은 형태로 노출되는 경우(API 응답 등)도 대비한다.
_IMAGE_LIST_PLAIN = re.compile(r'"imageList":(\[[^\]]*\])')

# 제외 패턴.
#
# imageList 에는 애초에 상품 컷만 들어오므로 지금은 아무것도 걸러지지 않는다.
# 사이트 개편으로 다른 이미지가 섞여 들어올 때를 대비한 안전망이다.
_EXCLUDE_PATTERNS = (
    "/card-company/",        # 카드사 로고
    "not_found.svg",         # 이미지 없음 더미
    "transparent.png",       # 1x1 투명 더미
    "/size/common/",         # 사이즈표
    "/extmall_brand/",       # 브랜드 개런티
    "/contents/brand/",      # 브랜드 배너
    "/contents/promotion/",  # 프로모션 배너
    "/contents/style/",      # 코디 추천
)


class BucketStoreAdapter(SiteAdapter):
    """버킷스토어(bucketstore.com)."""

    name = "bucketstore"

    # 평문 HTML로 추출 가능하다. Chromium을 띄우지 않는다.
    needs_browser = False

    PRODUCT_URL = "https://bucketstore.com/goods/detail/{code}"

    # 평문 추출이 실패했을 때 브라우저로 한 번 더 시도할지 여부.
    #
    # 기본값 False. 없는 상품코드도 "imageList 없음"으로 떨어지는데, 그때마다
    # Chromium을 띄우면 품절 상품이 많은 엑셀에서 매우 느려진다.
    # 사이트가 개편돼 평문 추출이 깨지면 이 값을 True로 올려 즉시 대응할 수 있다.
    browser_fallback = False

    def get_product_url(self, code: str) -> str:
        return self.PRODUCT_URL.format(code=code)

    def _fetch_image_urls(self, code: str) -> list[str]:
        url = self.get_product_url(code)

        html = self.ctx.http.get_html(url)
        urls = self._parse_image_list(html)

        # 평소엔 HTTP로 가다가 필요할 때만 브라우저로 올라타는 부분 이탈 경로.
        if not urls and self.browser_fallback:
            log.info("평문 추출 실패, 브라우저로 재시도합니다: %s", code)
            html = self.ctx.browser.get_html(url)
            urls = self._parse_image_list(html)

        if not urls:
            # 버킷스토어는 없는 상품에도 HTTP 200을 주므로 상태코드로는 구분되지 않는다.
            raise ProductNotFound(
                f"상품 페이지에서 이미지를 찾지 못했습니다 (품절/삭제 추정): {code}"
            )

        return urls

    @classmethod
    def _parse_image_list(cls, html: str) -> list[str]:
        """HTML에서 imageList 배열을 뽑아 정제한다."""
        match = _IMAGE_LIST_ESCAPED.search(html)
        if match:
            raw = match.group(1).replace('\\"', '"')
        else:
            match = _IMAGE_LIST_PLAIN.search(html)
            if not match:
                return []
            raw = match.group(1)

        try:
            urls = json.loads(raw)
        except json.JSONDecodeError as exc:
            log.warning("imageList 파싱 실패: %s", exc)
            return []

        if not isinstance(urls, list):
            return []

        cleaned = []
        for url in urls:
            if not isinstance(url, str) or not url.strip():
                continue
            url = cls._normalize(url.strip())
            if cls._is_excluded(url):
                log.debug("제외 패턴에 걸려 건너뜁니다: %s", url)
                continue
            cleaned.append(url)

        return SiteAdapter.dedupe(cleaned)

    @staticmethod
    def _normalize(url: str) -> str:
        """원본 이미지를 받도록 URL을 정리한다.

        CDN이 ?s=750 같은 리사이즈 파라미터를 지원하지만 쓰지 않는다.
        원본(1500x1500)을 받아 LANCZOS로 줄이는 쪽이 품질이 낫고,
        리사이즈 규칙을 image_processor 한 곳에 모아둘 수 있다.
        """
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = "https://bucketstore.com" + url
        # 쿼리스트링을 떼어 원본을 요청한다.
        return url.split("?", 1)[0]

    @staticmethod
    def _is_excluded(url: str) -> bool:
        lowered = url.lower()
        return any(pattern in lowered for pattern in _EXCLUDE_PATTERNS)
