"""크롤러 설정 — URL·주기·개수 제한·알림 규칙·사전·모델명은 이 파일 한 곳에만 둔다 (CLAUDE.md Structure)."""
from __future__ import annotations

import os
from datetime import timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))

# ---------------------------------------------------------------- 경로
DATA_DIR = Path(os.environ.get("PLAMO_DATA_DIR") or ROOT / "docs" / "data")   # --data-dir로도 덮어쓴다
REQUEST_LOG = ROOT / "crawler" / "out" / "requests.log"
CATALOG_FILES = {"gunpla": "catalog-gunpla.json", "girl": "catalog-girl.json"}
PENDING_FILE = "catalog-pending.json"   # 아직 line을 모르는 항목 + 제외 목록
FEED_FILE = "feed.json"
META_FILE = "meta.json"
SITE_URL = os.environ.get("SITE_URL") or "https://sora7942.github.io/plamo-hangar/"

# ---------------------------------------------------------------- HTTP (CLAUDE.md Rules: robots 준수, 1.2초 이상, timeout 20, 브라우저형 UA)
TIMEOUT = 20
MIN_INTERVAL = 1.2
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MAX_CONSECUTIVE_FAILURES = 5   # 연속 실패가 이 수에 닿으면 그 소스를 중단 (차단 상태에서 계속 두드리지 않는다)

# ---------------------------------------------------------------- 호비사이트
HOBBY_BASE = "https://bandai-hobby.net"
HOBBY_SCHEDULE_URL = HOBBY_BASE + "/schedule/index.php?saledate={ym}"   # ym = YYYYMM
HOBBY_ITEM_URL = HOBBY_BASE + "/item/{num}/"                            # num = 01_N
HOBBY_BRAND_URL = HOBBY_BASE + "/brand/{key}/"                          # 2쪽부터 ?p=N
PBANDAI_ITEM_URL = "https://p-bandai.jp/item/{num}/"                    # num = item-N (링크만, 요청하지 않는다)

# 안정 이미지 호스트만 저장한다 (서명 URL 금지 — CLAUDE.md Critical). bandai-hobby.net은 /images/ 아래만.
STABLE_IMAGE_HOSTS = {"bandai-a.akamaihd.net", "bandai-hobby.net"}
STABLE_IMAGE_PATHS = {"bandai-hobby.net": "/images/"}
UNSTABLE_URL_MARKERS = ("Expires=", "Signature=", "Key-Pair-Id=")

# ---------------------------------------------------------------- 수집 범위·상한
SCHEDULE_START = "2015-01"        # --bootstrap 때 일정을 거슬러 올라갈 시작 달 (--from으로 덮어씀)
SCHEDULE_AHEAD_MONTHS = 3         # 매 실행: 이번 달 ~ +3개월
GIRL_BRANDS = ["30ms", "30mp", "figurerise-standard", "figurerise-standard-amp"]   # 브랜드 목록으로 전체 수집
DETAIL_NEW_MAX = 40               # 실행당 상세: 이번에 처음 본 상품
DETAIL_BACKLOG_MAX = 150          # 실행당 상세: 밀린 상품
DETAIL_HARD_MAX = 400             # 어떤 옵션을 줘도 실행당 상세 합계는 이 수를 넘지 않는다
DETAIL_MAX_FAILURES = 3           # 상세가 이 횟수 실패한 항목은 더 시도하지 않는다
BRAND_MAX_PAGES = 60              # 브랜드 목록 쪽수 안전 상한

# ---------------------------------------------------------------- 피드·알림 (SPEC 4·7장)
FEED_MAX = 1000
DISCORD_PER_MESSAGE = 10
DISCORD_MAX_MESSAGES = 3
DISCORD_SEND_INTERVAL = 1.0       # 메시지 사이 대기(초)
DISCORD_TIMEOUT = 10
# 종류 → (표시 이름, 임베드 색, 알림 우선순위(작을수록 먼저)). kr-* 는 3단계에서 채워진다 (SPEC 7장 순서: kr → pb-new → new)
FEED_TYPES = {
    "kr-restock": ("국내 재입고", 0xE67E22, 0),
    "kr-new": ("국내 신규 입고", 0xE67E22, 1),
    "pb-new": ("P-반다이 한정 신규", 0x9B59B6, 2),
    "new": ("신제품 발매", 0x3498DB, 3),
}

# ---------------------------------------------------------------- 번역 (SPEC 5장)
DEFAULT_MODEL = "claude-sonnet-5-5"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL") or DEFAULT_MODEL
TRANSLATE_BATCH = 50
TRANSLATE_MAX_PER_RUN = 600
TRANSLATE_MAX_TOKENS = 8000

# ---------------------------------------------------------------- 브랜드 키 → (line, grade)
# 호비사이트 `/item_all/` 필터의 브랜드 키 77개 전부(spike/evidence/hobby-summary.json). line=None 은 "제외로 명시".
# 사전에 없는 새 키는 제외로 취급하고 meta.unknownBrandKeys 에 기록한다. 분류 규칙은 catalog.classify_brand_keys 참고.
GUNPLA_CONFIRMED = {
    "hg": ("gunpla", "HG"), "hg-c": ("gunpla", "HG"), "hguc": ("gunpla", "HG"), "hgce": ("gunpla", "HG"),
    "pb_hg": ("gunpla", "HG"),
    "rg": ("gunpla", "RG"), "rg-c": ("gunpla", "RG"), "pb_rg": ("gunpla", "RG"),
    "mg": ("gunpla", "MG"), "mgka": ("gunpla", "MG"), "pb_mg": ("gunpla", "MG"),
    "mgsd": ("gunpla", "MGSD"), "mgex": ("gunpla", "MGEX"),
    "pg": ("gunpla", "PG"), "pb_pg": ("gunpla", "PG"),
    "entry_grade_g": ("gunpla", "EG"), "entry_grade": ("gunpla", "EG"),
    "sdcs": ("gunpla", "SDCS"), "sdcs-c": ("gunpla", "SDCS"), "sdex": ("gunpla", "SDEX"),
    "bb": ("gunpla", "BB"), "pb_bb": ("gunpla", "BB"), "sdgundamseries": ("gunpla", "SD"),
    "re100": ("gunpla", "RE/100"), "fullmechanics": ("gunpla", "FULL MECHANICS"),
    "pb_gunpla": ("gunpla", None), "pb_others": ("gunpla", None),      # 등급은 상품명 앞 토큰으로
}
GUNPLA_TENTATIVE = {   # 건프라 라인이지만 사용자 판단이 필요해 일단 포함
    "megasize": ("gunpla", "MEGA SIZE"), "hirm": ("gunpla", "Hi-Resolution Model"),
    "gunpla40th": ("gunpla", None), "gundam_g40": ("gunpla", None), "besthit_chronicle": ("gunpla", None),
    "gundarium_gundam": ("gunpla", None), "gfy": ("gunpla", None), "expo2025-gunpla": ("gunpla", None),
    "hgamplifiedimgn": ("gunpla", "HG"),
}
GIRL = {   # 걸프라 — 사용자 지정 4개
    "30ms": ("girl", "30MS"), "30mp": ("girl", "30MP"),
    "figurerise-standard": ("girl", "Figure-rise Standard"),
    "figurerise-standard-amp": ("girl", "Figure-rise Standard Amplified"),
}
EXCLUDED_CANDIDATES = {k: (None, None) for k in (   # 제외, 걸프라/건프라 후보라 확인 필요
    "figurerise-bust", "figurerise-labo", "figurerise-mechanics", "figurerise-effect",
    "pb_charapla", "gundam-assemble", "30mm", "30mf")}
EXCLUDED_ACCESSORY = {k: (None, None) for k in (    # 제외, 건프라 주변 악세서리·도구
    "gundam_decal", "optionpartsset", "optionpartsset_c", "parts", "actionbase", "actionbase_c",
    "tool", "entry_nipper_c", "customize_scenebase", "imaginary_skeleton")}
EXCLUDED_OTHER = {k: (None, None) for k in (        # 제외, 다른 분야
    "claymonsters", "plakoro", "pokepla", "mecha-colle", "ecoplaproject_g", "ecopla", "tokyo2020_official",
    "petit_rits", "keitorabusou", "nekobusou", "peti", "disney_castle", "claymodelkit", "limex",
    "exploringlab_nature", "ultimagear", "geki-drive", "train", "petitgguy")}

BRAND_LINE: dict[str, tuple[str | None, str | None]] = {
    **GUNPLA_CONFIRMED, **GUNPLA_TENTATIVE, **GIRL,
    **EXCLUDED_CANDIDATES, **EXCLUDED_ACCESSORY, **EXCLUDED_OTHER,
}

# 상세 전 임시 판정과 P-반다이 카드(상세 없음) 판정용: NFKC 정규화 + 대문자로 바꾼 제목의 앞부분. 위에서부터 첫 일치.
TITLE_PREFIX_RULES: list[tuple[str, str, str]] = [
    (r"^MGSD", "gunpla", "MGSD"),
    (r"^MGEX", "gunpla", "MGEX"),
    (r"^MG", "gunpla", "MG"),
    (r"^PG", "gunpla", "PG"),
    (r"^RG", "gunpla", "RG"),
    (r"^HG", "gunpla", "HG"),
    (r"^(?:ENTRY GRADE|EG)\b", "gunpla", "EG"),
    (r"^SDCS|^SDガンダム ?クロスシルエット", "gunpla", "SDCS"),
    (r"^SDEX|^SDガンダム ?EX", "gunpla", "SDEX"),
    (r"^(?:SDW|SDガンダム|SD ?GUNDAM)", "gunpla", "SD"),
    (r"^BB戦士", "gunpla", "BB"),
    (r"^RE/100", "gunpla", "RE/100"),
    (r"^FULL MECHANICS", "gunpla", "FULL MECHANICS"),
    (r"^30MS|^30 ?MINUTES SISTERS", "girl", "30MS"),
    (r"^30MP|^30 ?MINUTES PREFERENCE", "girl", "30MP"),
    (r"^FIGURE-RISE STANDARD AMPLIFIED", "girl", "Figure-rise Standard Amplified"),
    (r"^FIGURE-RISE STANDARD", "girl", "Figure-rise Standard"),
]
