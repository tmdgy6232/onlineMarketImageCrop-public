# -*- coding: utf-8 -*-
"""페이지를 '어떻게' 가져올지를 담당하는 레이어.

사이트별 로직은 들어오지 않는다. 여기는 수단만 제공하고,
무엇을 뽑을지는 sites/*.py 어댑터가 정한다.

- HttpFetcher    : requests 기반. 빠르고 기본값
- BrowserFetcher : playwright 기반. 실제로 필요해진 순간에만 생성된다
- FetchContext   : 둘을 묶어 어댑터에 주입하는 객체
"""

import logging
import time

import requests

import config

log = logging.getLogger(__name__)


class FetchError(Exception):
    """페이지 또는 이미지를 가져오지 못했을 때."""


class HttpFetcher:
    """requests 세션 기반 가져오기. 재시도를 내장한다."""

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": config.USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        })

    def _request(self, url, referer=None):
        """재시도를 적용해 GET 요청을 보낸다."""
        headers = {"Referer": referer} if referer else None
        last_error = None

        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                resp = self._session.get(
                    url,
                    headers=headers,
                    timeout=config.REQUEST_TIMEOUT,  # 초 단위
                )
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                last_error = exc
                if attempt < config.MAX_RETRIES:
                    wait = config.RETRY_BACKOFF * (2 ** (attempt - 1))
                    log.debug("요청 실패(%d/%d), %.1f초 후 재시도: %s",
                              attempt, config.MAX_RETRIES, wait, url)
                    time.sleep(wait)

        raise FetchError(f"{config.MAX_RETRIES}회 재시도 실패: {url} ({last_error})")

    def get_html(self, url, referer=None):
        """페이지 HTML을 문자열로 반환한다."""
        resp = self._request(url, referer=referer)
        # 서버가 charset을 안 주면 requests가 latin-1로 추측해 한글이 깨진다.
        if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def get_bytes(self, url, referer=None):
        """이미지 등 바이너리를 bytes로 반환한다."""
        return self._request(url, referer=referer).content

    def exists(self, url, referer=None) -> bool:
        """URL에 파일이 있는지 HEAD 요청으로 확인한다.

        번호를 올려가며 이미지가 어디까지 있는지 찾을 때 쓴다.
        404 같은 '없음' 응답은 재시도하지 않고 바로 False를 돌려준다.
        연결 오류만 재시도하고, 끝내 실패하면 FetchError.
        """
        headers = {"Referer": referer} if referer else None
        last_error = None

        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                resp = self._session.head(
                    url,
                    headers=headers,
                    timeout=config.REQUEST_TIMEOUT,
                    allow_redirects=True,
                )
                return resp.status_code == 200
            except requests.RequestException as exc:
                last_error = exc
                if attempt < config.MAX_RETRIES:
                    time.sleep(config.RETRY_BACKOFF * (2 ** (attempt - 1)))

        raise FetchError(f"{config.MAX_RETRIES}회 재시도 실패: {url} ({last_error})")

    def close(self):
        self._session.close()


class BrowserFetcher:
    """playwright 기반 가져오기.

    JS 렌더링 + lazy 로딩 때문에 평문 HTML로는 이미지 URL이 안 잡히는 사이트용이다.
    브라우저는 프로세스당 1개만 띄워 모든 어댑터가 공유한다.
    """

    def __init__(self):
        self._playwright = None
        self._browser = None

    def _ensure_browser(self):
        """playwright를 지연 import하고 브라우저를 한 번만 띄운다."""
        if self._browser is not None:
            return

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise FetchError(
                "이 사이트는 브라우저 렌더링이 필요합니다. 아래를 실행하세요:\n"
                "    pip install playwright\n"
                "    playwright install chromium"
            ) from exc

        log.info("브라우저를 기동합니다 (최초 1회)")
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(
                headless=config.BROWSER_HEADLESS,
            )
        except Exception as exc:
            self._playwright.stop()
            self._playwright = None
            raise FetchError(
                f"Chromium 기동에 실패했습니다. 'playwright install chromium' 실행이 "
                f"필요할 수 있습니다. ({exc})"
            ) from exc

    def get_html(self, url, referer=None, wait_selector=None):
        """페이지를 열고 끝까지 스크롤한 뒤, 렌더링된 DOM을 반환한다."""
        self._ensure_browser()

        context = self._browser.new_context(
            user_agent=config.USER_AGENT,
            locale="ko-KR",
            extra_http_headers={"Referer": referer} if referer else None,
        )
        page = context.new_page()
        try:
            page.goto(url, timeout=config.REQUEST_TIMEOUT * 1000,
                      wait_until="domcontentloaded")
            if wait_selector:
                page.wait_for_selector(wait_selector,
                                       timeout=config.REQUEST_TIMEOUT * 1000)
            self._scroll_to_end(page, url)
            return page.content()
        finally:
            page.close()
            context.close()

    @staticmethod
    def _scroll_to_end(page, url):
        """페이지가 더 이상 자라지 않을 때까지 스크롤한다.

        스크롤 횟수에 상한을 두지 않는다. 상세 이미지가 몇 장이든 끝까지 내려가야 하고,
        횟수를 고정하면 긴 상세페이지가 조용히 잘린다.

        문서 높이와 <img> 개수를 함께 본다. 높이는 그대로인데 이미지만 교체되는
        캐러셀 구조에서도 로딩 완료를 제대로 판단하기 위해서다.
        """
        settle = 0          # 연속으로 변화가 없었던 횟수
        last_state = (0, 0)  # (문서 높이, img 개수)
        started = time.monotonic()
        rounds = 0

        while settle < config.BROWSER_SCROLL_SETTLE_ROUNDS:
            elapsed = time.monotonic() - started
            if elapsed > config.BROWSER_SCROLL_MAX_SECONDS:
                # 분량 제한이 아니라 무한 스크롤 페이지에서의 멈춤 방지용이다.
                # 여기 걸렸다면 이미지가 잘렸을 수 있으므로 반드시 눈에 띄게 남긴다.
                log.warning(
                    "스크롤이 %.0f초를 넘겨 중단했습니다. 상세 이미지가 일부 누락됐을 수 "
                    "있습니다. config.BROWSER_SCROLL_MAX_SECONDS 를 늘려 재시도하세요: %s",
                    elapsed, url,
                )
                break

            page.mouse.wheel(0, 20000)
            page.wait_for_timeout(config.BROWSER_SCROLL_WAIT_MS)
            rounds += 1

            state = tuple(page.evaluate(
                "() => [document.body.scrollHeight, document.images.length]"
            ))
            if state == last_state:
                settle += 1
            else:
                settle = 0
                last_state = state

        # 바닥까지 간 뒤에도 아직 로딩 중인 이미지가 남아있을 수 있으므로 한 번 더 기다린다.
        page.wait_for_timeout(config.BROWSER_SCROLL_WAIT_MS)
        log.debug("스크롤 %d회 후 종료 (높이=%s, 이미지=%s)",
                  rounds, last_state[0], last_state[1])

    def close(self):
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None


class FetchContext:
    """어댑터에 주입되는 가져오기 수단 묶음.

    `browser` 속성은 실제로 접근할 때 처음 생성된다.
    따라서 HTTP만 쓰는 사이트로 실행하면 playwright를 import조차 하지 않는다.
    """

    def __init__(self):
        self.http = HttpFetcher()
        self._browser = None

    @property
    def browser(self):
        if self._browser is None:
            self._browser = BrowserFetcher()
        return self._browser

    @property
    def browser_started(self):
        """브라우저가 실제로 생성됐는지. 종료 처리 판단용."""
        return self._browser is not None

    def close(self):
        self.http.close()
        if self._browser is not None:
            self._browser.close()
            self._browser = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False
