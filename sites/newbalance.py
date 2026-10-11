# -*- coding: utf-8 -*-
"""뉴발란스 어댑터 (뉴발란스 공식몰 nbkorea.com 갤러리 API).

조사 결과 전문: docs/sites/newbalance.md

요약: SSG 등 오픈마켓은 판매자마다 이미지가 제각각이라 쓰지 않는다.
공식몰 상세페이지가 색상 변경 때 부르는 갤러리 API를 품번으로 바로 호출하고,
공식 이미지 서버(image.nbkorea.com)의 1200x1200 원본을 받는다.
판매종료로 상세페이지가 막힌 상품도 API는 응답한다.

    NBMDF4W022-19  →  styleCode=NBMDF4W022, colCode=19
"""

import json
import logging
import re

from core.fetcher import FetchError

from .base import ProductInfo, ProductNotFound, SiteAdapter

log = logging.getLogger(__name__)

API_URL = (
    "https://www.nbkorea.com/product/light/getOtherColorOptImage.action"
    "?styleCode={style}&colCode={color}"
)
IMAGE_HOST = "https://image.nbkorea.com"

# 스타일코드 10자리. 색상코드는 그 뒤 (숫자 또는 영문 2자리).
_STYLE_LEN = 10

# ImgUrl 의 업로드 날짜 폴더. /NBRB_Product/20250912/NB2025...jpg
_DATE_FOLDER = re.compile(r"/NBRB_Product/(\d{8})/")


class NewBalanceAdapter(SiteAdapter):
    """뉴발란스 (nbkorea.com)."""

    name = "newbalance"

    # JSON API + 이미지 서버 모두 평문 HTTP. Chromium 불필요.
    needs_browser = False

    PRODUCT_URL = "https://www.nbkorea.com/product/productDetail.action?styleCode={style}&colCode={color}"

    def get_product_url(self, code: str) -> str:
        style, color = self._split(code)
        return self.PRODUCT_URL.format(style=style, color=color)

    def _fetch_product(self, code: str) -> ProductInfo:
        style, color = self._split(code)
        items = self._fetch_gallery(code, style, color)
        if not items:
            raise ProductNotFound(f"뉴발란스 공식몰에 이미지 없음: {code}")

        items.sort(key=lambda it: int(it.get("SortSeq") or 0))
        urls = self._product_cuts(items)
        name = (items[0].get("DisplayName") or "").strip()
        if not name:
            log.warning("뉴발란스 상품명을 찾지 못했습니다: %s", code)
        # 신발은 상품명 자리에 모델 번호(MR530CK 등)만 들어 있다. 그대로 쓴다.
        return ProductInfo(image_urls=urls, name=name)

    # ------------------------------------------------------------- 내부

    @staticmethod
    def _split(code: str) -> tuple[str, str]:
        """'NBMDF4W022-19' → ('NBMDF4W022', '19'). '-', '_', 공백, 붙여 쓰기 모두 받는다."""
        compact = re.sub(r"[\s_\-]+", "", code.strip().upper())
        style, color = compact[:_STYLE_LEN], compact[_STYLE_LEN:]
        if len(style) != _STYLE_LEN or not color:
            raise ProductNotFound(
                f"뉴발란스 품번 형식이 아닙니다 (예: NBMDF4W022-19): {code}"
            )
        return style, color

    def _fetch_gallery(self, code: str, style: str, color: str) -> list[dict]:
        """갤러리 API 응답의 prodOtherImgList. 없는 스타일·색상이면 빈 목록."""
        url = API_URL.format(style=style, color=color)
        # Content-Type 은 text/html 이지만 본문은 JSON 이다.
        raw = self.ctx.http.get_bytes(url, referer=self.get_product_url(code))
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise FetchError(f"뉴발란스 API 응답을 읽지 못했습니다: {code} ({exc})") from exc
        return list(data.get("prodOtherImgList") or [])

    @staticmethod
    def _product_cuts(items: list[dict]) -> list[str]:
        """모델 착용컷을 뺀 상품 단독 컷, SortSeq 순서.

        갤러리는 '1번 상품 정면 → 모델컷 여러 장 → 후면·디테일' 구성이다.
        모델컷은 상품컷과 다른 날 따로 올라가므로, 업로드 날짜 폴더가 1번과 다른 것을 뺀다.
        (실측 8개 상품 61장에서 눈으로 본 결과와 전부 일치)
        """
        def folder(item):
            match = _DATE_FOLDER.search(item.get("ImgUrl") or "")
            return match.group(1) if match else None

        first = folder(items[0])
        urls = []
        for item in items:
            path = (item.get("ImgUrl") or "").strip()
            if not path:
                continue
            if first is not None and folder(item) != first:
                continue
            urls.append(IMAGE_HOST + path if path.startswith("/") else path)
        return SiteAdapter.dedupe(urls)
