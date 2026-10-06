# -*- coding: utf-8 -*-
"""이미지 가공. 사이트와 무관한 공통 처리다.

- 대표이미지: 600x600 고정, 자르지 않고 비율 유지 리사이즈 후 흰 배경 중앙 배치
- 상세이미지: 가로 750 고정, 세로 가변. 위→아래 순서로 이어붙이고
              JPEG 높이 한계(65,535px)를 넘으면 분할한다
"""

import io
import logging

from PIL import Image

import config

log = logging.getLogger(__name__)

# 거대한 상세 이미지를 다루므로 Pillow의 폭탄 방지 경고를 끈다.
Image.MAX_IMAGE_PIXELS = None


class ImageProcessingError(Exception):
    """이미지를 가공할 수 없을 때."""


def load_image(data: bytes) -> Image.Image | None:
    """bytes를 RGB 이미지로 연다. 열 수 없으면 None."""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        log.debug("이미지를 열 수 없습니다: %s", exc)
        return None
    return to_rgb(img)


def to_rgb(img: Image.Image) -> Image.Image:
    """투명 배경을 흰색으로 합성하면서 RGB로 변환한다."""
    if img.mode == "RGB":
        return img

    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, config.BG_COLOR)
        canvas.paste(rgba, mask=rgba.split()[-1])  # 알파를 마스크로 써서 합성
        return canvas

    return img.convert("RGB")


def is_usable(img: Image.Image) -> bool:
    """상세에 쓸 수 있는 이미지인지. 아이콘/더미를 걸러낸다."""
    w, h = img.size
    return w >= config.MIN_IMAGE_WIDTH and h >= config.MIN_IMAGE_HEIGHT


def make_main_image(data: bytes, size: int | None = None) -> Image.Image:
    """대표이미지를 만든다.

    자르지 않는다. 비율을 유지한 채 size x size 안에 들어가도록 리사이즈한 뒤
    흰색 배경 정중앙에 배치한다(letterbox).
    """
    size = size or config.MAIN_SIZE

    img = load_image(data)
    if img is None:
        raise ImageProcessingError("대표이미지를 열 수 없습니다")

    w, h = img.size
    if w <= 0 or h <= 0:
        raise ImageProcessingError(f"대표이미지 크기가 비정상입니다: {w}x{h}")

    # 긴 쪽을 size에 맞춘다. 정사각 원본이면 여백 없이 꽉 찬다.
    ratio = min(size / w, size / h)
    new_w = max(1, round(w * ratio))
    new_h = max(1, round(h * ratio))
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (size, size), config.BG_COLOR)
    canvas.paste(resized, ((size - new_w) // 2, (size - new_h) // 2))
    return canvas


def build_detail_images(
    datas: list[bytes],
    width: int | None = None,
) -> list[Image.Image]:
    """상세이미지를 세로로 이어붙인다.

    각 이미지를 가로 `width`로 비율 유지 리사이즈한 뒤 위에서 아래로 연결한다.
    JPEG 높이 한계를 넘으면 여러 장으로 나눠 반환한다.

    반환값이 1장이면 `{코드}_detail.jpg`,
    2장 이상이면 `{코드}_detail_01.jpg`, `_02.jpg` ... 로 저장한다.
    """
    width = width or config.DETAIL_WIDTH
    gap = config.DETAIL_GAP
    max_h = config.JPEG_MAX_HEIGHT

    # 1) 열고 걸러내고 750폭으로 맞춘다.
    tiles: list[Image.Image] = []
    for data in datas:
        img = load_image(data)
        if img is None:
            continue
        if not is_usable(img):
            log.debug("너무 작아 상세에서 제외합니다: %sx%s", *img.size)
            continue
        tiles.append(_resize_to_width(img, width))

    if not tiles:
        raise ImageProcessingError("상세이미지로 쓸 수 있는 이미지가 없습니다")

    # 2) 한 장만으로도 높이 한계를 넘는 이미지는 먼저 잘라둔다.
    #    (아주 긴 세로형 상세컷을 쓰는 사이트 대비)
    prepared: list[Image.Image] = []
    for tile in tiles:
        if tile.height > max_h:
            log.info("이미지 1장이 높이 한계를 넘어 분할합니다: %spx", tile.height)
            prepared.extend(_slice_vertically(tile, max_h))
        else:
            prepared.append(tile)

    # 3) 높이 한계를 넘지 않는 선에서 묶는다.
    groups: list[list[Image.Image]] = []
    current: list[Image.Image] = []
    current_h = 0

    for tile in prepared:
        # 첫 장이 아니면 앞에 여백이 붙는다.
        added = tile.height + (gap if current else 0)
        if current and current_h + added > max_h:
            groups.append(current)
            current, current_h = [tile], tile.height
        else:
            current.append(tile)
            current_h += added

    if current:
        groups.append(current)

    return [_concat_vertical(group, width, gap) for group in groups]


def save_jpeg(img: Image.Image, path) -> None:
    """JPEG로 저장한다."""
    img.save(path, "JPEG", quality=config.JPEG_QUALITY, optimize=True)


def detail_filenames(code: str, count: int) -> list[str]:
    """상세이미지 파일명을 만든다. 2장 이상이면 _01, _02 ... 를 붙인다."""
    if count == 1:
        return [f"{code}_detail.jpg"]
    return [f"{code}_detail_{i:02d}.jpg" for i in range(1, count + 1)]


# ------------------------------------------------------------------ 내부 헬퍼


def _resize_to_width(img: Image.Image, width: int) -> Image.Image:
    """비율을 유지하며 가로를 width에 맞춘다."""
    w, h = img.size
    if w == width:
        return img
    new_h = max(1, round(h * width / w))
    return img.resize((width, new_h), Image.LANCZOS)


def _slice_vertically(img: Image.Image, max_h: int) -> list[Image.Image]:
    """한 장이 높이 한계를 넘을 때 세로로 잘라 여러 장으로 만든다."""
    pieces = []
    top = 0
    while top < img.height:
        bottom = min(top + max_h, img.height)
        pieces.append(img.crop((0, top, img.width, bottom)))
        top = bottom
    return pieces


def _concat_vertical(tiles: list[Image.Image], width: int, gap: int) -> Image.Image:
    """이미지들을 위에서 아래로 이어붙인다."""
    total_h = sum(t.height for t in tiles) + gap * (len(tiles) - 1)
    canvas = Image.new("RGB", (width, total_h), config.BG_COLOR)

    y = 0
    for tile in tiles:
        # 리사이즈 반올림으로 1px 어긋나는 경우가 있어 가로 중앙 기준으로 붙인다.
        x = (width - tile.width) // 2
        canvas.paste(tile, (x, y))
        y += tile.height + gap

    return canvas
