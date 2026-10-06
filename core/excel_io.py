# -*- coding: utf-8 -*-
"""엑셀 입력 읽기 / 결과 리포트 쓰기."""

import logging
from dataclasses import dataclass, field

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import config

log = logging.getLogger(__name__)

# 헤더로 인정할 단어들 (1행이 헤더인지 판단할 때 쓴다)
_CODE_HEADERS = {"상품코드", "코드", "품번", "code", "goods_code", "goodscode"}
_SITE_HEADERS = {"사이트", "site", "쇼핑몰", "mall"}


@dataclass
class InputRow:
    """입력 엑셀의 한 줄."""
    code: str
    site: str


@dataclass
class ResultRow:
    """결과 리포트의 한 줄."""
    code: str
    site: str
    success: bool
    main_image: str = ""          # 생성된 대표이미지 파일명
    detail_count: int = 0         # 상세이미지 장수
    detail_height: int = 0        # 최종 상세 높이(px). 분할된 경우 합계
    message: str = ""             # 오류 또는 경고 메시지

    @property
    def status(self) -> str:
        return "성공" if self.success else "실패"


def read_codes(path, default_site: str | None = None) -> list[InputRow]:
    """입력 엑셀을 읽어 (상품코드, 사이트) 목록을 만든다.

    - A열: 상품코드
    - '사이트' 헤더를 가진 열이 있으면 그 열의 값을 사이트로 쓴다
    - 1행이 헤더로 보이면 건너뛴다
    - 빈 행은 무시하고, 앞뒤 공백은 제거한다
    """
    default_site = default_site or config.DEFAULT_SITE

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()

    if not rows:
        return []

    site_col = None
    start = 0

    first = [_clean(v) for v in rows[0]]
    if first and first[0].lower() in _CODE_HEADERS:
        start = 1
        for idx, value in enumerate(first):
            if value.lower() in _SITE_HEADERS:
                site_col = idx
                break
        log.debug("1행을 헤더로 보고 건너뜁니다 (사이트 컬럼: %s)", site_col)

    if site_col is None:
        # 상품코드만으로는 어느 사이트 상품인지 판별할 수 없다.
        # 조용히 기본 사이트로 돌리면, 다른 몰 상품이 섞였을 때
        # "품절/삭제 추정" 으로 잘못 기록된다. 실제로는 사이트를 잘못 고른 것이다.
        log.warning(
            "'사이트' 컬럼이 없어 전부 %s 로 처리합니다. "
            "다른 몰 상품이 섞여 있다면 B열에 사이트를 지정하세요.",
            default_site,
        )

    result = []
    seen = set()
    for row in rows[start:]:
        if not row:
            continue
        code = _clean(row[0])
        if not code:
            continue
        if code in seen:
            log.warning("중복 상품코드를 건너뜁니다: %s", code)
            continue
        seen.add(code)

        site = ""
        if site_col is not None and site_col < len(row):
            site = _clean(row[site_col])

        result.append(InputRow(code=code, site=site or default_site))

    return result


def write_report(path, results: list[ResultRow]) -> None:
    """결과 리포트(result.xlsx)를 쓴다."""
    wb = Workbook()
    ws = wb.active
    ws.title = "결과"

    headers = [
        "상품코드", "사이트", "상태", "대표이미지",
        "상세이미지 장수", "최종 상세 높이(px)", "오류메시지",
    ]
    ws.append(headers)

    header_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="EEEEEE")
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    fail_fill = PatternFill("solid", fgColor="FFE6E6")
    for item in results:
        ws.append([
            item.code,
            item.site,
            item.status,
            item.main_image,
            item.detail_count,
            item.detail_height,
            item.message,
        ])
        if not item.success:
            for cell in ws[ws.max_row]:
                cell.fill = fail_fill

    widths = [22, 14, 8, 28, 16, 20, 60]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    ws.freeze_panes = "A2"
    wb.save(path)


def _clean(value) -> str:
    """셀 값을 문자열로 정리한다."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        # 엑셀이 숫자 코드를 1234.0 으로 읽는 경우를 방지한다.
        value = int(value)
    return str(value).strip()
