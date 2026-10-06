# -*- coding: utf-8 -*-
"""상세이미지 최상단에 붙일 양식(헤더)을 만든다.

글자가 비어있는 양식 이미지에 상품명과 모델명만 얹는다.
양식 디자인 자체는 건드리지 않는다.

좌표는 config 에 있다. 양식 디자인이 바뀌면 거기만 고치면 된다.
"""

import logging
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

import config

log = logging.getLogger(__name__)


class HeaderError(Exception):
    """양식을 만들 수 없을 때."""


_font_cache: dict[int, ImageFont.FreeTypeFont] = {}


def _font(size: int) -> ImageFont.FreeTypeFont:
    if size not in _font_cache:
        try:
            _font_cache[size] = ImageFont.truetype(config.HEADER_FONT_PATH, size)
        except OSError as exc:
            raise HeaderError(
                f"폰트를 열 수 없습니다: {config.HEADER_FONT_PATH} ({exc})"
            ) from exc
    return _font_cache[size]


def _fit_font(text: str, max_h: int, max_w: int) -> ImageFont.FreeTypeFont:
    """밴드 높이와 폭을 둘 다 넘지 않는 가장 큰 폰트를 고른다.

    상품명이 길면 글자가 작아진다. 잘라내는 것보다 작게라도 전부 보이는 편이 낫다.
    """
    size = config.HEADER_FONT_MAX_SIZE
    while size > config.HEADER_FONT_MIN_SIZE:
        f = _font(size)
        box = f.getbbox(text)
        if (box[3] - box[1]) <= max_h and (box[2] - box[0]) <= max_w:
            return f
        size -= 1
    return _font(config.HEADER_FONT_MIN_SIZE)


def _draw_centered(img: Image.Image, text: str, band: tuple[int, int]) -> None:
    """밴드의 세로 중앙, 지정된 가로 중심에 글자를 그린다."""
    if not text:
        return
    y0, y1 = band
    draw = ImageDraw.Draw(img)
    font = _fit_font(text, y1 - y0, config.HEADER_TEXT_MAX_WIDTH)
    box = draw.textbbox((0, 0), text, font=font)
    x = config.HEADER_CENTER_X - (box[2] - box[0]) // 2 - box[0]
    y = (y0 + y1) // 2 - (box[3] - box[1]) // 2 - box[1]
    draw.text((x, y), text, font=font, fill=config.HEADER_TEXT_COLOR)


def _trim_bottom_white(img: Image.Image) -> Image.Image:
    """아래쪽 순백 여백을 잘라낸다.

    양식 파일에 빈 여백이 딸려오는 경우가 있는데, 그대로 두면
    상세이미지 맨 위에 그만큼 빈 공간이 생긴다.
    """
    white = Image.new("RGB", img.size, config.BG_COLOR)
    bbox = ImageChops.difference(img, white).getbbox()
    if bbox is None:
        return img  # 전부 흰색이면 건드리지 않는다
    bottom = min(img.height, bbox[3] + config.HEADER_BOTTOM_MARGIN)
    if bottom >= img.height:
        return img
    log.debug("양식 아래 여백 %dpx 를 잘랐습니다", img.height - bottom)
    return img.crop((0, 0, img.width, bottom))


def build_header(name: str, code: str, width: int | None = None) -> Image.Image:
    """상품명/모델명이 적힌 헤더 이미지를 만든다.

    name: 상품명. 비어 있으면 그 줄은 비워둔다.
    code: 상품코드. '_' 는 공백으로 바꿔 모델명으로 쓴다.
    """
    width = width or config.DETAIL_WIDTH

    path = Path(config.HEADER_TEMPLATE_PATH)
    if not path.exists():
        raise HeaderError(f"양식 파일을 찾을 수 없습니다: {path}")

    try:
        img = Image.open(path).convert("RGB")
    except Exception as exc:
        raise HeaderError(f"양식 파일을 열 수 없습니다: {path} ({exc})") from exc

    if config.HEADER_TRIM_BOTTOM_WHITE:
        img = _trim_bottom_white(img)

    _draw_centered(img, name, config.HEADER_NAME_BAND)
    _draw_centered(img, code.replace("_", " "), config.HEADER_CODE_BAND)

    # 상세이미지 폭에 맞춘다. 보통 양식이 이미 750폭이라 그대로 지나간다.
    if img.width != width:
        new_h = max(1, round(img.height * width / img.width))
        img = img.resize((width, new_h), Image.LANCZOS)

    return img


def check_template() -> None:
    """실행 시작 시 양식과 폰트가 쓸 수 있는 상태인지 확인한다.

    상품을 다 돌린 뒤에 양식이 없다는 걸 알게 되면 늦다.
    """
    path = Path(config.HEADER_TEMPLATE_PATH)
    if not path.exists():
        raise HeaderError(
            f"양식 파일을 찾을 수 없습니다: {path}\n"
            f"config.HEADER_TEMPLATE_PATH 를 확인하거나, "
            f"config.HEADER_ENABLED = False 로 끄세요."
        )
    _font(config.HEADER_FONT_MAX_SIZE)
