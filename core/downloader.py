# -*- coding: utf-8 -*-
"""이미지 다운로드.

재시도 자체는 core/fetcher.py 의 HttpFetcher 가 담당한다.
여기서는 여러 장을 받으면서 실패를 어떻게 다룰지를 정한다.
"""

import logging

from .fetcher import FetchError

log = logging.getLogger(__name__)


def download(ctx, url, referer=None) -> bytes:
    """이미지 1장을 받는다. 실패하면 FetchError."""
    return ctx.http.get_bytes(url, referer=referer)


def download_many(ctx, urls, referer=None):
    """여러 장을 순서대로 받는다.

    반환: (받은 bytes 목록, 실패한 URL 목록)

    일부가 실패해도 중단하지 않는다. 상세 이미지 5장 중 1장이 깨졌다고
    상품 전체를 실패시키는 것보다 나머지로 이어붙이는 편이 낫다.
    다만 실패 목록을 함께 돌려줘서 호출부가 리포트에 남길 수 있게 한다.
    """
    blobs = []
    failed = []

    for url in urls:
        try:
            blobs.append(download(ctx, url, referer=referer))
        except FetchError as exc:
            log.warning("이미지 다운로드 실패: %s (%s)", url, exc)
            failed.append(url)

    return blobs, failed
