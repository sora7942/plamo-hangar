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
COLLECTION_FILE = "collection.json"      # 사이트가 쓰는 내 컬렉션 — 크롤러는 읽기만 한다
SERIES_FILE = "series-ko.json"          # seriesKey → 한국어 시리즈 사전 (크롤러만 씀, 4단계)
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
GIRL_BRANDS = ["30ms", "30mp", "figurerise-standard", "figurerise-standard-amp"]   # 브랜드 목록으로 전체 수집 (GIRL의 키와 같아야 한다)
DETAIL_NEW_MAX = 40               # 실행당 상세: 이번에 처음 본 상품
DETAIL_BACKLOG_MAX = 150          # 실행당 상세: 밀린 상품
DETAIL_HARD_MAX = 400             # 어떤 옵션을 줘도 실행당 상세 합계는 이 수를 넘지 않는다
MANUAL_DETAIL_MAX = 20           # 실행당 상세: 사용자가 사이트에서 연결했는데 카탈로그에 없는 상품 (새·밀린 상품 상한과 별개)
DETAIL_MAX_FAILURES = 3           # 상세가 이 횟수 실패한 항목은 더 시도하지 않는다
BRAND_MAX_PAGES = 60              # 브랜드 목록 쪽수 안전 상한

# ---------------------------------------------------------------- 피드·알림 (SPEC 4·7장)
FEED_MAX = 1000
DISCORD_PER_MESSAGE = 10
DISCORD_MAX_MESSAGES = 3
MINE_PRIORITY_TYPES = ("kr-restock", "kr-new")     # '내 프라 우선'은 국내 입고만 (SPEC 7장: 내 보유·위시와 연결된 국내 입고)
MINE_COLOR = 0xF1C40F                           # 내 프라 임베드 강조 색
MINE_LABELS = {"own": "보유", "wish": "위시"}
DISCORD_SEND_INTERVAL = 1.0       # 메시지 사이 대기(초)
DISCORD_TIMEOUT = 10
# 종류 → (표시 이름, 임베드 색, 알림 우선순위(작을수록 먼저)). kr-* 는 3단계에서 채워진다 (SPEC 7장 순서: kr → pb-new → new)
FEED_TYPES = {
    "kr-restock": ("국내 재입고", 0xE67E22, 0),
    "kr-new": ("국내 신규 입고", 0xE67E22, 1),
    "pb-new": ("P-반다이 한정 신규", 0x9B59B6, 2),
    "new": ("신제품 발매", 0x3498DB, 3),
}

# ---------------------------------------------------------------- 조이하비 국내 입고 (SPEC 4·5장, 3단계)
JOY_BASE = "https://www.joyhobby.co.kr"
JOY_BOARD_URL = JOY_BASE + "/mall/board_list.asp?siteid=joyhobby&BoardCode=notice"      # 2쪽부터 &nowPage=N
JOY_POST_URL = JOY_BASE + "/mall/board_view.asp?SiteID=joyhobby&BoardCode=notice&B_iID={id}"
KR_ARRIVALS_FILE = "kr-arrivals.json"
JOY_BOARD_PAGE_SIZE = 20          # 쪽당 일반 글 수. 이보다 적은 쪽이 마지막 쪽이다 (고정 공지 7개는 쪽마다 반복되므로 세지 않는다)
JOY_DAILY_PAGES = 2               # 매 실행: 목록 1~N쪽 (새 글 확인)
JOY_BACKFILL_PAGES = 25           # --bootstrap 실행당 과거 쪽 수 (2026-10 기준 게시판이 20쪽이라 한 번에 끝난다). 커서는 meta.crawl.joyNext
JOY_BOARD_MAX_PAGE = 60           # 안전 상한 (21쪽부터는 마지막 행이 반복해서 나온다)
JOY_POSTS_PER_RUN_MAX = 300       # 실행당 글 본문 요청 상한 (안전장치)
JOY_POST_MAX_FAILURES = 3         # 글 본문이 이 횟수 실패하면 더 시도하지 않는다
JOY_TITLE_KEYWORDS = ("반다이", "입고")      # 후보 조건: 제목에 하나라도 있으면 본문을 열어 본다. 반다이 상품코드(BD#######) 행이 있어야 기록한다
JOY_BANDAI_CODE = r"BD\d{7}"
JOY_RESTOCK_WORD = "재입고"

KR_RESTOCK_AFTER_DAYS = 60        # 일본 발매일보다 이만큼 이상 뒤에 입고되면 restock, 아니면 new
KR_SALE_DATE_MAX_DIFF_DAYS = 60   # 제목의 판매예정일이 글 날짜와 이보다 멀면 글 날짜를 쓴다
KR_FEED_DAYS = 30                 # 글 날짜가 최근 N일 이내인 행만 피드에 넣는다 (과거 글은 kr 이력·원본 행에만)
KR_NOTIFY_DAYS = 3                # 디스코드 알림은 글 날짜가 최근 N일 이내인 것만

# 상품명 앞 대괄호 코드의 영문·한글 접두 → 카탈로그 등급 (위에서부터 첫 일치). None = 카탈로그 대상이 아님(매칭하지 않음).
JOY_BRACKET_GRADES: list[tuple[str, str | None]] = [
    (r"^30M[MF]", None), (r"^30MS", "30MS"), (r"^30MP", "30MP"),
    (r"^HG", "HG"), (r"^MGSD", "MGSD"), (r"^MGEX", "MGEX"), (r"^MG", "MG"), (r"^PG", "PG"), (r"^RG", "RG"), (r"^EG", "EG"),
    (r"^SDCS", "SDCS"), (r"^SDEX", "SDEX"), (r"^SD", "SD"), (r"^BB", "BB"), (r"^RE$", "RE/100"),
    (r"^피규어라이즈스탠다드", "Figure-rise Standard"),
]
# 같은 계열로 보고 후보에 넣는 카탈로그 등급 (없으면 같은 등급만)
JOY_GRADE_FAMILIES: dict[str, set[str]] = {
    "SD": {"SD", "SDCS", "SDEX", "BB"}, "BB": {"BB", "SD"},
    "Figure-rise Standard": {"Figure-rise Standard", "Figure-rise Standard Amplified"},
}
# 이름 매칭 (match.py). 점수는 0~100.
MATCH_LINK_SCORE = 80             # 1등이 이 점수 이상이고
MATCH_MARGIN = 10                 # 2등과 이만큼 이상 차이 나야 연결한다. 아니면 연결하지 않는다
MATCH_NAME_SCORE = 92             # nameKo를 조이하비 한글명으로 바꾸는 더 엄격한 기준 (연결 기준과 별도)
MATCH_MODEL_BONUS = 12            # 모델번호(MS-09F 등)가 양쪽에 있고 같으면 더하는 점수
MATCH_MODEL_CONFLICT = 15         # 양쪽에 있는데 서로 다르면 빼는 점수
MATCH_TOKEN_RATIO = 80             # 보호 규칙: 정확히 같은 낱말이 없을 때 4글자 이상 낱말끼리 이만큼(%) 비슷하면 철자 변형으로 본다. 짧은 낱말(3글자 이하)은 정확히 같아야 한다.
                                   # 낮추면 르브리스/루브리스 같은 철자 변형을 더 잡지만 큐리오스/헬리오스(75%) 같은 다른 상품도 통과한다
# 사람이 고치는 표: 조이하비 상품코드 → 카탈로그 id(강제 연결) 또는 None(연결 금지).
# None이면 이미 굳은 연결을 풀고, 그 코드가 바꿔 놓은 nameKo를 nameKoAi로 되돌리고, 그 코드로 쌓인 kr 항목을 그 상품에서 뺀다.
KR_CODE_OVERRIDES: dict[str, str | None] = {}
# 이름 끝의 " - <꼬리>"는 보통 작품명이라 떼지만, 꼬리에 변형 표시어가 있으면 변형 이름(`큐베레이 마크2 - 플 전용기`)이라 **떼지 않는다**
# (떼면 기본형으로 잘못 연결될 수 있다. 틀린 연결 < 연결 없음). 낱말 경계로 찾는다: 한글 표시어는 뒤에 한글이 이어지지 않을 때
# (`컬러` ≠ `컬러즈`), 영문 표시어는 앞뒤에 영문자가 없을 때(`Ver`는 `Ver.Ka`·`VER.`에 걸리고 `Version`은 아래에서 따로).
JOY_VARIANT_MARKERS = ("전용기", "커스텀", "사양", "타입", "Type", "컬러", "Ver", "Version", "버전", "장비", "유닛", "에디션", "Edition")
# 표시어가 들어 있어도 작품명인 꼬리(부분 문자열 일치) — 여기 있으면 떼어낸다. 현재 데이터에는 해당 없음(`아이돌마스터 샤이니 컬러즈`는 경계 규칙으로 이미 안 걸림)
JOY_TAIL_EXEMPT = ("아이돌마스터 샤이니 컬러즈",)

# ---------------------------------------------------------------- 번역 (SPEC 5장)
DEFAULT_MODEL = "claude-sonnet-5-5"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL") or DEFAULT_MODEL
# 번역 용어집 (일본어 → 지정 표기). 시스템 프롬프트에 그대로 들어간다 — 틀린 번역이 자주 보이면 여기에 한 줄씩 추가한다.
# 값에는 히라가나·가타카나를 쓰지 않는다(테스트가 막는다). 값이 영문이면 영문 그대로 쓴다.
TRANSLATE_GLOSSARY: dict[str, str] = {
    # 기동전사 건담 수성의 마녀 — 인물·기체 (사용자 지정)
    "ディランザ": "딜란자",
    "グエル": "구엘",
    "スレッタ": "슬레타",
    "ミオリネ": "미오리네",
    # 상품명 공통 표기 (사용자 지정): [カラーC] → [컬러C]
    "カラー": "컬러",
    # 국내 매장(조이하비) 표기 — tests/fixtures/joyhobby-post-*.html 에 실제로 나온 한국어 명칭
    "ガンダム": "건담",
    "エアリアル": "에어리얼",
    "シャイニング": "샤이닝",
    "クシャトリヤ": "크샤트리아",
    "サザビー": "사자비",
    "キュベレイ": "큐베레이",
    "ジオング": "지옹",
    "ベギルベウ": "베귀르베우",
    "ドム・トローペン": "돔 트로펜",
    "ゲルググ": "겔구그",
    "シャア": "샤아",
    "マグナガルルモン": "매그너가루몬",
    # 한글로 옮기지 않고 영문 그대로 쓰는 용어 (값이 영문이면 그대로 쓰라는 뜻이다)
    "アンプリファイド": "Amplified",
    "パリトン": "파리톤",
    "ヴィダール": "비다르",          # 한자(`达`)가 섞여 나왔던 용어 — 2026-10 확인
}

# nameKo 후처리: 이미 저장된 번역에서 해당 부분 문자열만 바꾼다 (나머지 글자·다른 필드는 그대로). 용어집을 고친 뒤
# 이전 번역을 맞추는 용도이고, 매 실행 시작과 번역 직후에 적용한다. 값에는 가나를 쓰지 않는다.
NAME_KO_REPLACEMENTS: dict[str, str] = {
    "앰플리파이드": "Amplified",
}
# 시리즈 한국어: 번역 결과보다 우선하는 사람이 고치는 표 {seriesKey: 한국어}. 틀린 번역이 보이면 한 줄 추가한다. 값에는 가나를 쓰지 않는다(테스트가 막는다).
SERIES_KO_OVERRIDES: dict[str, str] = {}
SERIES_BATCH = 50
SERIES_MAX_PER_RUN = 300
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
    # figurerise-bust: 한 번 걸프라로 옮겼다가(6ee610b) 첫 crawl 결과를 보고 다시 제외로 돌렸다. 앞으로는 이 표만 고치면 된다 —
    # 기존 항목은 다음 실행에서 자동으로 다시 분류된다 (catalog.reclassify)
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
