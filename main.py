# -*- coding: utf-8 -*-
"""진입점.

    python main.py input.xlsx

엑셀의 상품코드를 읽어 사이트별 어댑터로 이미지 URL을 뽑고,
대표(600x600) / 상세(750폭 이어붙임) 이미지를 생성한다.

여기에는 사이트별 분기가 없다. 새 사이트가 늘어도 이 파일은 바뀌지 않는다.
"""

import argparse
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

import config
from core import downloader, header as header_mod, image_processor as improc
from core.header import HeaderError
from core.excel_io import ResultRow, read_codes, write_report
from core.fetcher import FetchContext, FetchError
from sites import AdapterPool, ProductNotFound, UnknownSite, available_sites

log = logging.getLogger("main")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="엑셀의 상품코드로 쇼핑몰 대표/상세 이미지를 수집·가공한다.",
    )
    parser.add_argument("input", help="입력 엑셀 파일(.xlsx)")
    parser.add_argument(
        "--site", default=None,
        help=f"기본 사이트 (기본값: {config.DEFAULT_SITE}, "
             f"사용 가능: {', '.join(available_sites())})",
    )
    parser.add_argument("--out", default=None, help="출력 루트 폴더")
    parser.add_argument("--limit", type=int, default=None,
                        help="앞에서 N건만 처리 (검수용)")
    parser.add_argument("--delay", type=float, default=None,
                        help="상품 간 고정 딜레이(초). 미지정 시 0.5~1초 랜덤")
    parser.add_argument("--verbose", action="store_true", help="디버그 로그 출력")
    return parser.parse_args(argv)


def setup_logging(log_path: Path, verbose: bool) -> None:
    """콘솔과 log.txt에 동시에 기록한다."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%H:%M:%S")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    console = _TqdmHandler()
    console.setFormatter(fmt)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(console)


class _TqdmHandler(logging.Handler):
    """진행률 바를 깨뜨리지 않고 로그를 출력한다."""

    def emit(self, record):
        try:
            tqdm.write(self.format(record))
        except Exception:
            self.handleError(record)


def process_one(ctx, adapter, code: str, out_dir: Path) -> ResultRow:
    """상품 1건을 처리한다. 예외는 호출부에서 잡아 실패로 기록한다."""
    site = adapter.name
    referer = adapter.get_product_url(code)

    # 1) URL 추출 — 사이트별로 다른 유일한 단계. 페이지 요청은 내부 캐시로 1회만 발생한다.
    main_url = adapter.get_main_image_url(code)
    detail_urls = adapter.get_detail_image_urls(code)
    log.debug("%s: 대표 1장 / 상세 %d장", code, len(detail_urls))

    product_dir = out_dir / code
    product_dir.mkdir(parents=True, exist_ok=True)

    warnings = []
    # 어댑터가 남긴 메모 (예: 색상 자동 매칭). 성공이어도 확인이 필요한 내용이다.
    note = adapter.get_note(code)
    if note:
        warnings.append(note)

    # 2) 대표이미지
    main_blob = downloader.download(ctx, main_url, referer=referer)
    main_img = improc.make_main_image(main_blob)
    main_name = improc.main_filename(code)
    improc.save_jpeg(main_img, product_dir / main_name)

    # 3) 상세이미지
    blobs, failed = downloader.download_many(ctx, detail_urls, referer=referer)
    if failed:
        warnings.append(f"상세 이미지 {len(failed)}장 다운로드 실패")
    if not blobs:
        raise improc.ImageProcessingError("상세 이미지를 한 장도 받지 못했습니다")

    # 상세 맨 위에 붙일 양식. 상품명/모델명을 적어 넣는다.
    head = None
    if config.HEADER_ENABLED:
        name = adapter.get_product_name(code)
        if not name:
            warnings.append("상품명을 찾지 못해 양식의 상품명이 비어 있음")
        head = header_mod.build_header(name, code)

    detail_imgs = improc.build_detail_images(blobs, header=head)
    names = improc.detail_filenames(code, len(detail_imgs))
    total_height = 0
    for img, name in zip(detail_imgs, names):
        improc.save_jpeg(img, product_dir / name)
        total_height += img.height

    if len(detail_imgs) > 1:
        warnings.append(f"높이 한계 초과로 {len(detail_imgs)}장으로 분할")

    # 파일 저장이 모두 끝난 뒤에 성공으로 기록한다.
    return ResultRow(
        code=code,
        site=site,
        success=True,
        main_image=main_name,
        detail_count=len(detail_imgs),
        detail_height=total_height,
        message=" / ".join(warnings),
    )


def main(argv=None) -> int:
    args = parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"입력 파일을 찾을 수 없습니다: {input_path}", file=sys.stderr)
        return 1

    out_root = Path(args.out or config.OUTPUT_ROOT)
    run_dir = out_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    setup_logging(run_dir / config.LOG_NAME, args.verbose)
    log.info("출력 폴더: %s", run_dir.resolve())

    default_site = args.site or config.DEFAULT_SITE
    rows = read_codes(input_path, default_site=default_site)
    if args.limit:
        rows = rows[:args.limit]

    if not rows:
        log.error("처리할 상품코드가 없습니다: %s", input_path)
        return 1

    # 양식과 폰트는 시작할 때 확인한다.
    # 상품을 다 돌린 뒤에 양식이 없다는 걸 알게 되면 늦다.
    if config.HEADER_ENABLED:
        try:
            header_mod.check_template()
        except HeaderError as exc:
            log.error("%s", exc)
            return 1
        log.info("상세 상단 양식: %s", config.HEADER_TEMPLATE_PATH)

    log.info("상품 %d건을 처리합니다 (기본 사이트: %s)", len(rows), default_site)

    results: list[ResultRow] = []

    with FetchContext() as ctx:
        pool = AdapterPool(ctx)

        for index, row in enumerate(tqdm(rows, desc="처리 중", unit="건")):
            try:
                adapter = pool.get(row.site)
                results.append(process_one(ctx, adapter, row.code, run_dir))
                log.info("성공: %s", row.code)

            except (ProductNotFound, UnknownSite, FetchError, HeaderError,
                    improc.ImageProcessingError) as exc:
                # 예상 가능한 실패. 상품 1건만 실패로 기록하고 계속 진행한다.
                log.warning("실패: %s — %s", row.code, exc)
                results.append(ResultRow(row.code, row.site, False, message=str(exc)))

            except Exception as exc:  # noqa: BLE001 - 전체 중단 방지가 목적
                log.exception("예상치 못한 오류: %s", row.code)
                results.append(ResultRow(
                    row.code, row.site, False,
                    message=f"{type(exc).__name__}: {exc}",
                ))

            # 사이트 부하 방지. 마지막 건 뒤에는 쉬지 않는다.
            if index < len(rows) - 1:
                time.sleep(args.delay if args.delay is not None
                           else random.uniform(config.DELAY_MIN, config.DELAY_MAX))

    report_path = run_dir / config.REPORT_NAME
    write_report(report_path, results)

    succeeded = sum(1 for r in results if r.success)
    failed = len(results) - succeeded
    log.info("완료: 성공 %d건 / 실패 %d건", succeeded, failed)
    log.info("리포트: %s", report_path.resolve())

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
