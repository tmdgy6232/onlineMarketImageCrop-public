# -*- coding: utf-8 -*-
"""전역 설정값.

결과물 사양이나 동작을 바꿀 일이 생기면 이 파일만 수정한다.
사이트별 설정은 각 어댑터(sites/*.py) 안에 둔다.
"""

# ---------------------------------------------------------------- 결과물 사양

# 대표이미지: 600 x 600 고정
MAIN_SIZE = 600

# 상세이미지: 가로 750 고정, 세로 가변
DETAIL_WIDTH = 750

# 상세 이미지를 이어붙일 때 이미지 사이 여백(px)
DETAIL_GAP = 0

# JPEG 포맷의 최대 높이. 이를 넘으면 _detail_01, _02 ... 로 분할한다.
JPEG_MAX_HEIGHT = 65535

# 여백 / 투명 배경 합성에 쓰는 배경색
BG_COLOR = (255, 255, 255)

# 저장 품질
JPEG_QUALITY = 90

# ------------------------------------------------------- 상세 상단 양식(헤더)

# 상세이미지 맨 위에 상품명/모델명이 적힌 양식을 붙일지 여부
HEADER_ENABLED = True

# 글자가 비어있는 양식 이미지
HEADER_TEMPLATE_PATH = "samples/top_format_clear.jpg"

HEADER_FONT_PATH = r"C:\Windows\Fonts\malgunbd.ttf"   # 맑은 고딕 Bold
HEADER_FONT_MAX_SIZE = 48
HEADER_FONT_MIN_SIZE = 12

# 글자를 그릴 세로 구간 (y0, y1). 양식 이미지 기준 좌표다.
# top_format_clear.jpg 의 MODEL / NO. 줄 위치에서 측정했다.
HEADER_NAME_BAND = (75, 100)    # 상품명
HEADER_CODE_BAND = (117, 138)   # 모델명

# 글자의 가로 중심과 최대 폭. 양식 왼쪽 바코드 영역을 침범하지 않는 선이다.
HEADER_CENTER_X = 478
HEADER_TEXT_MAX_WIDTH = 500

HEADER_TEXT_COLOR = (0, 0, 0)

# 양식 아래쪽 순백 여백을 잘라낸다. 남겨둘 여백(px).
HEADER_TRIM_BOTTOM_WHITE = True
HEADER_BOTTOM_MARGIN = 0

# --------------------------------------------------------------- 이미지 필터

# 이 크기보다 작은 이미지는 아이콘/더미로 보고 상세에서 제외한다.
MIN_IMAGE_WIDTH = 100
MIN_IMAGE_HEIGHT = 100

# ------------------------------------------------------------------ 네트워크

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 요청 타임아웃(초). requests 의 timeout 인자로 그대로 전달된다.
REQUEST_TIMEOUT = 30

# 다운로드 최대 재시도 횟수
MAX_RETRIES = 3

# 재시도 간 대기(초). 시도할 때마다 2배씩 늘어난다.
RETRY_BACKOFF = 1.0

# 사이트 부하 방지를 위한 상품 간 딜레이(초) 범위
DELAY_MIN = 0.5
DELAY_MAX = 1.0

# ------------------------------------------------------------------- 브라우저

BROWSER_HEADLESS = True

# lazy 이미지를 모두 로드하기 위한 스크롤 설정.
#
# 스크롤 "횟수"에는 상한을 두지 않는다. 상세 이미지가 몇 장이든 끝까지 내려가야 하므로,
# 페이지가 더 이상 자라지 않을 때까지(문서 높이와 <img> 개수가 둘 다 변하지 않을 때까지)
# 반복한다. 횟수를 고정하면 긴 상세페이지가 조용히 잘려나간다.

# 스크롤 한 번마다 대기(ms). lazy 로딩이 따라올 시간을 준다.
BROWSER_SCROLL_WAIT_MS = 300

# 높이와 이미지 개수가 연속 이 횟수만큼 그대로일 때 "바닥에 닿았다"고 판단한다.
# 한 번만 보고 끝내면 로딩이 잠깐 끊긴 순간을 바닥으로 오인한다.
BROWSER_SCROLL_SETTLE_ROUNDS = 3

# 무한 스크롤 피드처럼 끝이 없는 페이지에서 영원히 돌지 않기 위한 안전장치(초).
# 분량 제한이 아니라 멈춤 방지용이므로 넉넉하게 둔다.
# 이 값에 걸리면 이미지가 잘렸을 수 있다는 뜻이므로 WARNING 로그를 남긴다.
BROWSER_SCROLL_MAX_SECONDS = 180

# ---------------------------------------------------------------- 입력 / 출력

# 엑셀에 사이트 컬럼이 없을 때 사용할 기본 사이트
DEFAULT_SITE = "bucketstore"

# 출력 루트. 실행할 때마다 그 아래 {YYYYMMDD_HHMMSS}/ 폴더가 생긴다.
OUTPUT_ROOT = "output"

# 결과 리포트 파일명
REPORT_NAME = "result.xlsx"

# 로그 파일명
LOG_NAME = "log.txt"
