# -*- coding: utf-8 -*-
"""데상트 어댑터.

조사 결과 전문: docs/sites/descente.md

요약: 데상트 상품 이미지는 공식 이미지 서버(img.dk-on.com)에 품번 규칙대로 올라가 있다.
검색이나 브라우저 없이 품번으로 주소를 만들어 바로 받는다.
무신사 등 다른 몰도 이 서버 이미지를 그대로 가져다 쓴다.

    SQ323UKC94_PAT0  →  base = SQ323UKC94, color = PAT0
    https://img.dk-on.com/product/S/Q3/SQ323UKC94/1780/SQ323UKC94_PAT0_N01.JPG

상품명은 공식몰(dk-on.com) 상품 페이지의 <title>에서 가져온다.
"""

import html as html_lib
import logging
import re

from core.fetcher import FetchError

from .base import ProductInfo, ProductNotFound, SiteAdapter

log = logging.getLogger(__name__)

IMAGE_HOST = "https://img.dk-on.com"

# 상품 컷 폴더. 1780 은 현행 원본(1780x1780)이고 모든 상품에 있다.
# 550 은 그 저해상도 사본이라 쓰지 않는다.
_N_FOLDER = "1780"

# 옛 상품만 따로 갖고 있는 디테일 컷 폴더(620x620). 현행 상품은 비어 있다.
_D_FOLDER = "D/620"

# 번호를 올려가며 찾을 때의 상한. 실측 최대는 N16 이다.
# 끝없이 요청하지 않게 하는 안전장치일 뿐, 보통은 첫 404에서 멈춘다.
_MAX_SHOTS = 40

_TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)

# 없는 품번이면 공식몰이 이 제목의 안내 페이지를 준다.
_NOT_FOUND_TITLE = "서비스 이용 안내"

# 상품명 앞의 브랜드 머리말. [NEO ARCHIVE] 같은 라인명은 남긴다.
_BRAND_PREFIX = re.compile(r"^\s*\[DESCENTE\]\s*", re.I)


class DescenteAdapter(SiteAdapter):
    """데상트 (공식 이미지 서버 직접)."""

    name = "descente"

    # 이미지 서버와 공식몰 모두 평문 HTTP로 된다.
    needs_browser = False

    PRODUCT_URL = "https://dk-on.com/product/{base}/{color}"

    def get_product_url(self, code: str) -> str:
        base, color = self._split(code)
        return self.PRODUCT_URL.format(base=base, color=color)

    def _fetch_product(self, code: str) -> ProductInfo:
        base, _ = self._split(code)
        code = code.strip().upper()

        # 상품 컷 → 옛 상품의 디테일 컷 순서로 이어붙인다.
        urls = self._collect(base, code, _N_FOLDER, "N")
        if not urls:
            raise ProductNotFound(f"데상트 서버에 이미지 없음: {code}")
        urls += self._collect(base, code, _D_FOLDER, "D")

        return ProductInfo(image_urls=urls, name=self._fetch_name(code))

    # ------------------------------------------------------------- 내부

    @staticmethod
    def _split(code: str) -> tuple[str, str]:
        """품번을 base 와 color 로 나눈다."""
        base, sep, color = code.strip().upper().partition("_")
        if not sep or not color or len(base) < 3:
            raise ProductNotFound(
                f"데상트 품번 형식이 아닙니다 (예: SQ323UKC94_PAT0): {code}"
            )
        return base, color

    def _collect(self, base: str, code: str, folder: str, kind: str) -> list[str]:
        """{kind}01 부터 번호를 올리며 있는 이미지 주소를 모은다. 첫 404에서 멈춘다."""
        root = f"{IMAGE_HOST}/product/{base[0]}/{base[1]}{base[2]}/{base}/{folder}"
        urls = []
        for n in range(1, _MAX_SHOTS + 1):
            url = f"{root}/{code}_{kind}{n:02d}.JPG"
            if not self.ctx.http.exists(url):
                break
            urls.append(url)
        log.debug("%s: %s 컷 %d장", code, kind, len(urls))
        return urls

    def _fetch_name(self, code: str) -> str:
        """공식몰 상품 페이지 제목에서 상품명을 뽑는다. 못 찾으면 빈 문자열."""
        try:
            page = self.ctx.http.get_html(self.get_product_url(code))
        except FetchError as exc:
            log.warning("상품명을 가져오지 못했습니다: %s (%s)", code, exc)
            return ""
        return self._parse_name(page, code)

    @staticmethod
    def _parse_name(page: str, code: str) -> str:
        match = _TITLE.search(page)
        title = html_lib.unescape(match.group(1)).strip() if match else ""
        if not title or title == _NOT_FOUND_TITLE:
            log.warning("공식몰에서 상품명을 찾지 못했습니다: %s", code)
            return ""
        name = _BRAND_PREFIX.sub("", title)
        # 끝에 품번이 붙어 있으면 뗀다. 모델명 줄에 이미 들어간다.
        base = code.partition("_")[0]
        name = re.sub(rf"\s*\(?{re.escape(base)}[^)]*\)?\s*$", "", name, flags=re.I)
        return name.strip()
