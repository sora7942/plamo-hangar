# 0단계(spike) 보고서 — 수집 가능성 검증

- 작성: 2026-10-06 (KST) · 범위: SPEC 12장 0단계만 (1~5단계 구현 없음)
- 실행 환경: 로컬 Windows 11 / Python 3.12(conda `plamo`) / Playwright 1.63 Chromium / **일본 외 IP**(사용자 거주지 기준 한국으로 추정, IP 위치 조회는 하지 않음)
- **Actions 결과 반영됨** — 2026-10-06 13:43~13:49 KST 실행, GitHub 호스티드 러너(Linux azure, Python 3.12.14), `run_all.py --env actions`, 4단계(hobby·pbandai·joyhobby·hotlink) 모두 ok, 상세 페이지 25/30. 근거는 `spike/evidence/actions/`(요약 JSON 5개·`requests.log`). 로컬과 달랐던 점은 9장에 따로 모았다.
- 판정 표기: **[가능]** / **[불가]** / **[부분]** / **[미확인]**. 근거 경로는 저장소 기준이며, `spike/evidence/*`와 `tests/fixtures/*`는 커밋 대상, `spike/screenshots/*`는 `.gitignore`(공식 이미지가 찍혀 있어서) 로컬 전용이다. `spike/evidence/actions/`도 커밋 대상이고, Actions artifact 압축 해제본 `spike/out-actions/`는 `.gitignore`에 들어 있어 **로컬 전용**이다(9장 끝 참고).

## 0. 결론 먼저

1. **호비사이트**: 월별 일정·상품 상세는 수집 가능하고, 이 환경에서는 Playwright 없이 일반 `requests`로도 열린다. 하지만 **再販(재판) 정보는 사이트에 없다**(일정·상세 모두). 그리고 **최신 상품의 이미지 URL은 5분 안에 만료되는 서명 URL**이라 "원본 URL로 링크"가 안 된다(2022~2024년 상품 일부는 안정 URL).
2. **P-반다이(p-bandai.jp)**: 이 PC(일본 외 IP)에서는 모든 경로가 지역 선택 페이지(`/global_newpc.html`)로 리다이렉트된다 → **[불가]**. 우회(VPN·프록시)는 하지 않았다. 대안 후보는 6장.
3. **조이하비**: 공지 게시판의 "N/N(요일) 판매예정 반다이 제품리스트 안내" 글에 상품코드·이름·가격 목록이 있어 **수집 가능**. 단 "재입고 vs 신규"는 글 문구에 의존한다.
4. SPEC에 영향이 큰 것 두 가지: **(a) 일본 재판 이력(`releases`의 reissue)을 호비사이트에서 얻을 수 없다**, **(b) 이미지 링크 방식(2.5절·5장·7장)**. 둘 다 사용자 결정이 필요하다(7장).
5. **Actions(GitHub 러너) 결과**: 호비사이트·조이하비는 Actions에서도 로컬과 같게 열렸고(차단·추가 리다이렉트 없음, 파싱 결과 동일), P-반다이 JP는 같은 지역 리다이렉트, 서명 URL은 같은 5분 만료였다. 다른 점은 쿠키 배너 변형, P-반다이 US 상품 페이지 0/2, 로컬 전용 보조 요청 미반복 정도다(9장).

## 1. SPEC 12장 0번 확인 항목 요약

| # | 확인 항목 | 로컬 | Actions | 근거 |
|---|---|---|---|---|
| 1 | 호비사이트 접속 | **[가능]** `requests`·Playwright 모두 200, 리다이렉트 0 | **[가능]** 같음 — `requests`·Playwright 모두 200, 리다이렉트 0. 일정 18쪽·상세 17개 전부 200, `/schedule/` 92,482바이트(로컬과 같은 크기) | `spike/evidence/hobby-summary.json`(`plain_requests`, `plain_detail`), `requests.log` |
| 2 | 호비사이트 robots.txt | **[가능]** robots.txt 없음(HTML 200 반환) = 명시된 제한 없음 | **[가능]** 같음 — HTML 200 = 규칙 없음 (원문 로컬과 동일) | `tests/fixtures/robots-bandai-hobby.txt` |
| 3 | 월별 일정 페이지 | **[가능]** `/schedule/index.php?saledate=YYYYMM` | **[가능]** 같음 — 카드 수 18개월 전부 로컬과 같음 (2026-10 21 · 2026-11 26 …) | `tests/fixtures/hobby-schedule-202610.html` |
| 4 | 일정의 再販 표시 | **[불가]** 18개월 일정·상세 17개 어디에도 없음 | **[불가]** 같음 — 일정 18쪽·상세 17개 `reissue_text_hits` 전부 0, 월 간 중복 제목 0, 호비 fixture 10개에서도 재판 문구 0 | `hobby-summary.json`(`reissue_text_hits`, `repeated_titles_across_months`), 2.3절 |
| 5 | 과거 월 열람 범위 | **[가능]** 1980-07까지 열림(2건). 단 2005년 이전은 월 2~5건뿐 | **[가능]** 같음 — 1980-07 2건, 1980-10 0건까지 열림 | `hobby-summary.json`(`schedule`), `tests/fixtures/hobby-schedule-199510.html` |
| 6 | 상세: 번호·이름·가격·발매일 | **[가능]** (발매일은 일 단위 또는 월 단위) | **[가능]** 같음 — 17개 필드 동일 | `tests/fixtures/hobby-item-01_4257.html` 외 |
| 7 | 상세: 등급·스케일·작품 | **[부분]** 등급·작품은 링크 키로, 스케일은 이름 문자열에서만 | **[부분]** 같음 | 2.4절 |
| 8 | 상세: 재판 이력 | **[불가]** 표시 없음 | **[불가]** 같음 | 2.3절 |
| 9 | 이미지 URL 패턴 | **[가능]** 3종 패턴 확인 | **[가능]** 같음 — 3종 패턴 동일. 서명 URL 71개 TTL 73~300초(로컬 40~299초): `Expires` = 받은 시각 + 300초 | 2.5절 |
| 10 | 이미지 종류(박스/CG/작례) 구분 | **[부분]** URL·alt로는 불가, 위치 규칙은 일부만 맞음 | **[부분]** 변동 없음 — G행 8/8 로드는 되나 스크린샷이 결과에 없어 위치 규칙 재확인은 못 함 | `screenshots/hotlink-local.png`(G행), 2.5절 |
| 11 | 이미지 핫링크 | **[부분]** 안정 URL은 가능, 서명 URL은 만료 후 403 (localhost 오리진 기준) | **[부분]** 같음 — 서명 방금 8/8, 안정 URL 11/11·3/3·5/5, p-bandai.com 4/4, 만료 서명 0/4 + 직접 요청 403. 오리진은 러너 안 `http://localhost:8000`(github.io 아님) | `hotlink-summary.json`, 5장 |
| 12 | 걸프라 라인 분류 | **[부분]** 30MS는 브랜드 키로 깔끔, 나머지는 후보 | **[부분]** 같음 — `filters` 로컬과 차이 0건 | `hobby-summary.json`(`filters`), 2.6절 |
| 13 | P-반다이 접속 | **[불가]** 지역 리다이렉트 3/3 경로 | **[불가]** 같음 — 3/3 `global_newpc.html` 리다이렉트, robots.txt도 같은 곳으로 → 읽을 수 없음 | `spike/evidence/pbandai-summary.json`(`jp_probes`), `tests/fixtures/pbandai-jp-region-redirect.html` |
| 14 | P-반다이 건프라·걸프라 신규/재예약 구분 페이지 | **[불가]** (JP) · 대안 A(US) **[부분]** | (JP) **[불가]** · 대안 A(US) **[부분]**, 더 불안정 — 홈은 열리나 상품 2개 모두 `PAGE NOT AVAILABLE`(로컬은 1/2 열림) | 3장 |
| 15 | 조이하비 접속·robots | **[가능]** `Disallow: /admin/`만 | **[가능]** 같음 — robots `Disallow: /admin/`만, 홈 1회 리다이렉트(정상), 목록·글·상품 200 | `tests/fixtures/robots-joyhobby.txt` |
| 16 | 조이하비 주별 재입고 목록 주소·구조 | **[가능]** 공지 게시판 글(주 1~2회) | **[가능]** 같음 — 목록 51행, 반다이 리스트 글 12건, 글 4개 141건 파싱 동일 (차이는 조회수 숫자뿐) | 4장, `tests/fixtures/joyhobby-post-139459.html` |
| 17 | 조이하비 재입고 vs 신규 구분 | **[부분]** 글 문구에 의존 | **[부분]** 같음 | 4장 |
| 18 | 조이하비 상품명 형식 | **[가능]** 표본 141건 정리 | **[가능]** 같음 — 141건 동일 | 4장, `joyhobby-summary.json`(`name_samples`) |

## 2. 호비사이트 (bandai-hobby.net)

### 2.1 접속·robots
- robots.txt: `https://bandai-hobby.net/robots.txt`가 **HTML(200)** 을 돌려준다 → 규칙 파일이 없음. 게이트 코드는 "규칙 없음 = 허용"으로 동작했고, 직접 쓴 경로는 `/schedule/`, `/item/…`, `/brand/…`, `/item_all/`, `/news/…` 뿐이다. (`/search/` 등 폼 제출 경로는 쓰지 않았다.)
- CLAUDE.md의 "일반 HTTP 요청에서 리다이렉트가 반복됐다"는 **이 환경에서는 재현되지 않았다**: `requests`로 `/schedule/`(92KB, 카드 포함)과 `/item/01_4257/`(제목·필드·갤러리 11장·브랜드 링크 모두 파싱됨) 모두 200, 리다이렉트 0. **Actions 러너에서도 같았다**: `requests`로 `/schedule/` 200·리다이렉트 0·카드 포함·92,482바이트(로컬과 같은 크기), 상세 `/item/01_4257/`도 제목·필드·갤러리 11장·브랜드 2개 파싱(`plain_detail`). 표본은 목록 1쪽·상세 1쪽이지만 호비사이트는 Playwright 없이 `requests+bs4`로 충분해 보인다. (조이하비는 해당 없음 — 7장 4번)

### 2.2 월별 일정
- URL: `https://bandai-hobby.net/schedule/index.php?saledate=YYYYMM` (현재월은 `/schedule/`). 연도 셀렉트는 1980~2027.
- 한 페이지에 카드 3묶음: ① 일반 판매 (`/item/01_N/`, 날짜 일 단위), ② 公式オンラインショップ販売商品 (`.p-card__tag.-online` = ホビーオンライン, 링크가 `p-bandai.jp/item/item-N`, **날짜는 월만**), ③ ガンダムベース販売商品 (`/item/01_N/`). 카드 = `a.p-card` (`.p-card__tit`, `.p-card__price`, `.p-card_date`, 썸네일 `img`).
- 월별 카드 수: 2026-11 26 · 2026-10 21 · 2026-09 28 · 2026-07 27 · 2025-10 18 · 2024-10 22 · 2022-10 15 · 2020-10 13 · 2018-10 17 · 2015-10 17 · 2010-10 18 · 2005-10 4 · 1995-10 4 · 1993-07 5 · 1990-07 3 · 1985-07 3 · **1980-07 2** · 1980-10 0 (`hobby-summary.json`). 월 20~28건이라 SPEC의 "실행당 상세 40개"로 충분하다. 2005년 이전은 목록이 성기다(전체 이력이 아님).
- 신규 상품 번호는 `01_NNNN`이 대체로 증가 (2022-10 `01_4257` → 2026-10 `01_7249`). 단 구형 상품 번호가 뒤늦게 붙는 경우도 있다(`01_52`는 1995-10 BB전사). "새 번호만 상세를 가져온다"는 규칙은 번호 집합 비교로 가능.

### 2.3 再販(재판) — **[불가]**
- 일정 18개월 페이지 + 상세 17개의 텍스트에서 `再販|再生産|再出荷|再発売|再入荷` 0건. (`REVIVAL Ver.`라는 상품명 1건은 오탐.)
- 같은 상품이 여러 달에 다시 올라오지도 않는다(`repeated_titles_across_months` = 0건). 일정은 **최초 발매 기준**이다.
- 호비사이트가 "商品出荷予定(납품 예정표)" 페이지를 **전매 방지 이유로 중단**했다는 공지가 있다 (`https://bandai-hobby.net/site/schedule.html`, 호비 홈의 "商品納品予定についてみる" 링크가 가리킴). 재판 예정 정보를 공식적으로 내리지 않는 방침으로 보인다.
- 따라서 SPEC 4장의 `releases[].type = "reissue"`를 호비사이트로는 채울 수 없다. (`type: initial`과 일정상의 "미래 발매 예정"은 가능.)

### 2.4 상세 페이지 필드 (17개 샘플, 상세 17/18 사용)
URL `https://bandai-hobby.net/item/01_N/`. 셀렉터: 제목 `h1.p-heading__h1-product`, 값 `dl.pg-products__detail dt/dd`, P-반다이 링크 `a.pg-products__pblink`, 브랜드·작품 `li.p-card__link a.p-card__flat`, 본문 `.pg-products__article`.

| 필드 | 판정 | 비고 |
|---|---|---|
| 상품 번호 | [가능] | URL의 `01_N` |
| 상품명 | [가능] | `h1` |
| 가격 | [가능] | `1,760 円(税10%込)` |
| 발매일 | [가능] | `2022年10月01日 (土)` 또는 월만 `2026年11月` (샘플 17개 중 6개가 월만) |
| 등급 | [부분] | 브랜드 링크 키(`/brand/hg/`)와 라벨. 같은 등급이 키 2개로 갈린다 (`hg`/`hg-c`, `rg`/`rg-c`, `pb_hg` 등) → 매핑표 필요. 샘플 중 2개는 브랜드 링크 없음(구형 `01_1547`, `01_5373`) |
| 스케일 | [부분] | 별도 필드 없음. 상품명 속 `1/144`만 (정규식) |
| 작품 | [부분] | `/series/g-witch/` 링크(키+라벨). 샘플 3개는 없음 (`01_7142` 30MS 등) |
| 재판 이력 | [불가] | 없음 (2.3절) |
| P-반다이 링크 | [부분] | 17개 중 4개만 (`item-1000188677` 형식) |
| 상품 설명(商品情報) | [가능] | 본문 텍스트 |

- 갤러리 이미지 수는 1~12장. og:image는 모든 상품이 공통 `ogp.png`라 쓸 수 없다.

### 2.5 이미지
URL 패턴 3종 (17개 상품 갤러리 + 일정 썸네일 + 브랜드/시리즈 로고 기준):

| 패턴 | 예 | 성질 | 어느 상품 |
|---|---|---|---|
| ① `bandai-a.akamaihd.net/bc/img/model/xl/<번호>_<N>.jpg` | `…/xl/1000179163_1.jpg` | **비서명, 안정** (P-반다이 이미지 CDN). `<번호>`는 상세의 P-반다이 링크 번호(`1000188677`)와 **다를 수 있다** → 링크에서 유도 불가 | 2022~2024년 일부 (`01_4257`, `01_5373`) |
| ② `bandai-hobby.net/images/ecms_…jpg` | 정적 | **안정** | 구형·일부 (`01_4259`, `01_3024`, `01_2909`, `01_1547`, `01_52`) |
| ③ `d3bk8pkqsprcvh.cloudfront.net/hobby/jp/product/…jpg?Expires=…&Key-Pair-Id=…&Signature=…` | 서명 URL | **만료됨**: 71개 측정, 받은 시각 + **40~299초** | 2025년 이후 상품 대부분, 일정 썸네일, 브랜드/시리즈 로고, 상세 본문 이미지 |

- 상세 샘플 17개의 갤러리 호스트: ① 2개, ② 5개, ③ 10개.
- **종류(박스/CG/작례) 구분 [부분]**: alt가 비어 있거나 상품명이라 URL·alt·DOM 클래스로는 구분 못 한다. 화면으로 확인한 위치 규칙: 2022~2024년 상품 3건(`01_4257`, `01_5373`, `01_4259`)은 **마지막 장 = 박스아트**, 앞 장들은 완성품 사진(작례). 반면 2015·2020년 상품 2건(`01_2909`, `01_3024`)은 첫·끝 모두 완성품 사진(박스아트 위치 불명). 미발매 신제품 `01_7249`(서명 URL)는 검은 배경 CG 4장. 즉 **"박스 → CG → 작례" 순서를 자동 보장하려면 별도 규칙(마지막 장 휴리스틱 + 미발매=CG)이 필요하고, 오분류 가능성이 있다.** 표본 5건 육안 확인 기준이다 (`screenshots/hotlink-local.png` A·G행).

### 2.6 걸프라 라인 분류 — [부분]
`/item_all/`의 필터에서 브랜드 키 77개 · 작품 키 114개 · 판매 채널 5개(`order_form`: general/shop/event/gbase/gsidef)를 얻었다 (`hobby-summary.json`의 `filters`).

- **확실한 키**: `30ms` (30 MINUTES SISTERS) — 브랜드 페이지 `/brand/30ms/`가 한 페이지 12건, 페이저 20쪽까지(≈240건)로 라인 전체 열거가 된다. 샘플: `01_7142` 미야스티, `01_7260` 하나미 사키(이 상품은 `idolmaster` 작품 링크도 있음).
- **후보(사용자 확인 필요)**: `30mp`(30 MINUTES PREFERENCE — 마도카·아야나미 레이 등 캐릭터), `figurerise-standard`/`figurerise-standard-amp`(남녀 캐릭터 혼합), `figurerise-bust`, `pb_charapla`(프레반 캐릭터프라), 작품 키 기준(`bluearchive`, `madoka-magica`, `bocchi-rocks`, `idolmaster`, `idolmaster-shinycolors`, `umamusume`, `lovelive`, `girlgunlady`, `garupan` 등 — 작품이 미소녀물이라고 모든 상품이 걸프라는 아님).
- 호비 푸터에 "LINKL PLANET 公式X(@plamogirls)" 링크가 있으나 **브랜드/시리즈 키로는 존재하지 않는다**. 이 이름을 걸프라 라인으로 쓸지는 사용자 판단.
- 분류 방법 제안: `config.py`에 "브랜드 키 → line(gunpla/girl)" 사전을 두고, 미분류 키는 `gunpla`/`girl` 어느 쪽도 아닌 `other`로 두어 카탈로그에서 제외.

## 3. P-반다이 (p-bandai.jp)

### 3.1 JP — [불가]
- robots.txt: `https://p-bandai.jp/robots.txt` 요청이 `https://p-bandai.jp/global_newpc.html`(HTML)로 리다이렉트 → **robots.txt를 읽을 수 없다** (`tests/fixtures/robots-pbandai.txt`).
- 호비사이트가 직접 링크하는 3개 주소(홈 `/`, 카테고리 `/hobby/`, 상품 `/item/item-1000188677`)를 열어 봤고, **3/3 모두** `global_newpc.html`("INTERNATIONAL SHIPPING AVAILABLE" 지역 선택 페이지: 대만·홍콩·싱가포르·미국·호주·뉴질랜드·Shopee 등 링크)로 리다이렉트됐다 (`pbandai-summary.json`의 `jp_probes`, `tests/fixtures/pbandai-jp-region-redirect.html`). 페이지에 "일본에서 접속해도 이 페이지가 보이면 Chrome 데이터 세이버를 끄라"는 안내가 있어 **일본 IP 여부로 갈리는 지역 분기**로 판단한다.
- 브라우저형 UA·`ja-JP` 로케일로도 같았다. **지역 제한을 우회하는 시도(IP 위장, VPN, 프록시)는 하지 않았다.** 이 소스는 막힌 것으로 보고한다. **Actions 러너에서도 같았다**: 3/3 모두 `global_newpc.html` 리다이렉트, `robots.txt`도 같은 곳으로 가서 읽을 수 없음(`pbandai-summary.json`의 `jp_probes`, `jp_blocked_region=true`). 러너의 실제 위치는 조회하지 않았다(호비사이트 쿠키 배너가 캘리포니아용으로 바뀐 점은 미국 위치와 맞지만 추정이다 — 9장).
- 따라서 SPEC의 "P-반다이 건프라·걸프라 신규 예약·재예약(재판) 구분 페이지"는 JP 사이트로는 확인 불가.

### 3.2 대안 A: 해외 P-반다이 `p-bandai.com/us` — [부분]
- robots.txt 읽힘 (`tests/fixtures/robots-pbandai-global.txt`): `Disallow: /*?*offset=`, `/*?*limit=`, `/*?*sortType=`, `/*?*_f_productStatuses=`. 홈의 "VIEW ALL" 링크(`/us/search?limit=20&sortType=NewArrival&_f_productStatuses=On`)는 **robots가 막는 URL이라 요청하지 않았다**(판정만 기록: `search_url_allowed=false`).
- 홈(`/us/`, 이 PC에서 열림, `tests/fixtures/pbandai-global-us-top.html`)에 NEW ARRIVALS 20 · CLOSING SOON 10 · IN STOCK 10 · 상단 9개 타일(PRE-ORDER/EXCLUSIVE 플래그). 건프라 포함(HG/MG/RG). 상품명 영어, 가격 US$.
- 상품 페이지 2개 중 1개 열림 (`F2835905002`, `tests/fixtures/pbandai-global-us-item-F2835905002.html`): 가격 $50, `PRE-ORDER`·`EXCLUSIVE`, 예약 시작 `Sep. 28 2026 3:40 PM (EDT)`, 마감 `Jan. 16 2027`, 발송 `Feb. 2027`. 다른 하나(`F2423965005`)는 "PAGE NOT AVAILABLE"(원인 미확인; 사이트 공지 463은 카드게임 2종만 해당).
- **Actions**: 홈은 열렸지만(200, 리다이렉트 0, 상단 타일 10개 — 로컬은 9개, 진열이 시간에 따라 바뀜) 상품 페이지 2개 **모두 "PAGE NOT AVAILABLE"**(`F2835905002`도 로컬에서는 열렸음). 홈 목록에 있는 상품인데도 실패하므로, 이 경로는 실행 환경·시각에 따라 간헐적이다. 같은 이유로 `tests/fixtures/pbandai-global-us-item-F2835905002.html`에 해당하는 Actions 쪽 fixture는 없다.
- 한계: 일본 카탈로그의 부분집합, 상품 번호 체계가 달라(`F…` vs `item-…`) 호비/일본 상품과는 이름으로만 매칭 가능, **재판 라벨은 관찰되지 않음**, 목록·정렬 URL이 robots로 막혀 홈 40여 개 + 개별 상품 + 사이트맵(`/us/sitemap.xml`은 인덱스로 존재하나 하위 사이트맵은 열어보지 않음)만 가능.

### 3.3 대안 B: 호비사이트가 싣는 P-반다이 정보 — [부분]
- 월별 일정의 ホビーオンライン 카드 (월 1~6건, `p-bandai.jp/item/item-N` 링크 + 발매 월 + 가격)와 `pb_*` 브랜드 키 8개(`pb_gunpla`, `pb_hg` 등)로 P-반다이 한정 상품의 **신규 발매 월**은 알 수 있다 (`pbandai-summary.json`의 `alt_hobby_site`). **재예약(재판)은 알 수 없다.** 뉴스 `?cat=online_shop`은 1쪽에 1건뿐(RG 케로로 사양 상품화 결정).

## 4. 조이하비 (joyhobby.co.kr)

### 4.1 접속·robots
- robots.txt: `User-agent: *` → `Disallow: /admin/` (그 외 SEO 봇 몇 개 전체 차단: Yandex, Semrush, Ahrefs). 사용한 경로는 모두 허용 (`board_url_allowed=true`). 메인은 `/mall/main.asp?siteid=joyhobby&`로 1회 리다이렉트(정상). Classic ASP 쇼핑몰이다.

### 4.2 주별 재입고·신규 입고 목록 — [가능]
- **주소**: 공지 게시판 `https://www.joyhobby.co.kr/mall/board_list.asp?siteid=joyhobby&BoardCode=notice` (`&nowPage=N`). 글 `…/mall/board_view.asp?SiteID=joyhobby&BoardCode=notice&B_iID=<번호>`. 2쪽에서 글 51건 확인.
- **반다이 주간 리스트**: 제목 `N/N(요일) 판매예정 반다이 제품리스트 안내` (2026-07-03 게시분부터 확인된 글 12건, 주 1~2회: 토요일, 평일 입고 시 화요일 등). 예: `B_iID=139506`(10/3), `139459`(9/29), `139407`(9/19).
- **그 외 입고 글**: `프라모델 신제품 입고안내`(`139432`), `피규어 신제품 입고안내`, 브랜드별 입고안내 등 18건.
- 글 구조: 소개 문단 → 상품마다 3줄 `상품코드 / 상품명 / 가격`. 상품코드가 `Item.asp?siteid=joyhobby&productcode=<코드>` 링크(열림, 재고 상태 문구 `품절` 등 표시). 반다이 코드는 `BD#######`, 다른 제조사는 `ANN/PLM/AO/TMT…` 접두.
- 파싱 결과(글 4개): `139459` 19건, `139506` 5건, `139407` 56건, `139432`(타사 포함) 61건 → 141건 (`joyhobby-summary.json`).
- 보조: `NewGoods.asp`(신상품, 입고예정월 문구 `26년 10월 입고예정` 포함, 링크 67개), `ipgo.asp`(13개).

### 4.3 재입고 vs 신규 — [부분]
- `139459`는 소개문에 "**재입고** 제품리스트"라고 명시, `139506`은 신제품(MGSD 크샤트리아 등 이번 달 발매분)이 섞여 있고 "재입고"라는 단어가 없다. 글마다 문구가 달라 **글 텍스트만으로는 구분이 안 되고**, 카탈로그의 발매일과 대조(발매 후 N개월 경과 = 재입고)해야 안전하다.

### 4.4 상품명 형식 (match.py 매칭 대상)
형식: `[등급코드] 스케일 모델번호 한글명(영문명) - 작품(프라모델)`. 141건 중 스케일 109건, 대괄호 코드 125건, `(프라모델)` 꼬리표 130건.

| 상품코드 | 이름 | 가격 |
|---|---|---|
| BD5068558 | `[RG42] 1/144 GF13-017NJ 샤이닝 건담(SHINING GUNDAM) - 기동무투전 G건담(프라모델)` | 38,500원 |
| BD5074303 | `[MGSD06] 크샤트리아(KSHATRIYA) - 기동전사 건담 UC(프라모델)` | 84,000원 |
| BD5072559 | `[피규어라이즈스탠다드] 매그너가루몬 앰플리파이드(MagnaGarurumon Amplified) - 디지몬 프론티어(프라모델)` | 66,000원 |
| BD5074255 | `[30MM_EXM_80] 1/144 xEXM-000 제노발트(XENOVALT)(프라모델)` | 24,200원 |
| BD5063505 | `[HGUC011] 1/144 큐베레이 마크2 - 플 전용기 Qubeley Mk.II` | 19,800원 |
| BD5060658 | `[HGUC017] 1/144 MS-09F 돔 트로펜 (Dom Tropen) - 기동전사 건담 0083 스타더스트 메모리(프라모델)` | 16,500원 |
| BD5061605 | `[RG29] 1/144 MSN-04 사자비(SAZABI) - 기동전사 건담 역습의 샤아(프라모델)` | 52,800원 |
| BD5062166 | `[HGWFM02] 1/144 CEK-040 베귀르베우(Beguir-Beu) - 기동전사 건담 수성의 마녀(프라모델)` | 17,600원 |
| BD5063571 | `[MG] 1/100 MS-14S 샤아 전용 겔구그 Ver.2.0 - 기동전사 건담(프라모델)` | 58,800원 |
| BD5068846 | `[MGSD04] XVX-016 건담 에어리얼(GUNDAM AERIAL) - 기동전사 건담 수성의 마녀(프라모델)` | 46,800원 |

매칭 시 주의: 대괄호 코드가 일본 등급과 대응(`HGUC`, `HGAW`, `HGWFM`, `RG`, `MG`, `MGSD`), 코드 없는 이름(`[MG] 1/100`)·한글 등급(`[피규어라이즈스탠다드]`)·스케일 없는 상품·`(프라모델)` 꼬리표 없는 상품이 섞여 있다.

## 5. 이미지 핫링크 테스트

- `spike/hotlink-test.html`(커밋 대상, 링크만 포함) + `python -m http.server -d spike 8000` → Playwright(자산 차단 해제)로 접속, 이미지를 **1.3초 간격으로 하나씩** 로드, 각 `<img>`의 `complete && naturalWidth>0` 판정 (`spike/evidence/hotlink-summary.json`, 스크린샷 `spike/screenshots/hotlink-local.png`, 로컬 전용).
- 오리진은 `http://localhost:8000`. `github.io` 오리진 결과는 다를 수 있어 **[부분]**: localhost 기준 확인, Pages 오리진 재확인은 push 이후 과제.

| 행 | 대상 | referrerpolicy | 결과 |
|---|---|---|---|
| D | CloudFront **서명 URL, 방금 받음**(일정 썸네일 4 + 상세 갤러리 4) | no-referrer | **8/8 표시** (200) |
| E | CloudFront **서명 URL, 이전에 받아 Expires 지남** | no-referrer | **0/6** (브라우저는 `ERR_BLOCKED_BY_ORB`; 1건 직접 확인: **HTTP 403 `AccessDenied`** XML) |
| A | akamai 갤러리 (`01_4257` 11장) | no-referrer | **11/11** |
| B | 같은 akamai 3장 | 정책 없음(Referer `http://localhost:8000/` 전송) | **3/3** → Referer 기반 차단 없음 |
| C | 호비 정적 이미지 5장 | no-referrer | **5/5** |
| F | p-bandai.com 홈 이미지 4장 | no-referrer | **4/4** |
| G | 갤러리 첫·끝 장 8장 (박스아트 위치 확인) | no-referrer | **8/8** |

- **Actions 재실행** (러너 안 Chromium, 오리진 `http://localhost:8000`, 이미지 43장): D 8/8 · A 11/11 · B 3/3 · C 5/5 · F 4/4 · G 8/8 표시, E(만료 서명 URL)는 0/4(`ERR_BLOCKED_BY_ORB`), 직접 요청은 403 `AccessDenied` XML. 행별로 로컬과 같고 E만 표본이 6→4장이다. 오리진이 github.io가 아니라는 한계도 그대로다(`github.io` 오리진 재확인은 push 이후 과제).
- 결론: **안정 URL(akamai, 호비 정적, p-bandai.com)은 핫링크 가능. 서명 URL은 만료 후 불가 → 크롤러가 저장해 둔 서명 URL은 방문자가 볼 때쯤 모두 죽어 있다.**
- CSP `img-src` 후보 호스트(SPEC 6장): `bandai-a.akamaihd.net`, `bandai-hobby.net`, `p-bandai.com`. `d3bk8pkqsprcvh.cloudfront.net`은 서명 URL이라 허용해도 효용이 거의 없음.

## 6. 막힌·부분 소스와 대안

### 6-1. P-반다이(JP) 접근 불가
| 대안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| ① 호비사이트 ホビーオンライン 카드 + `pb_*` 브랜드 | P-반다이 한정 상품의 신규 발매 월·가격·P-반다이 상품 번호 | 접속 확인됨, 같은 파서 재사용, 월 1~6건 | 재예약(재판) 불가, 예약 시작일 없음(월만) |
| ② 해외 P-반다이(US 등) 홈·상품 페이지 | 신규 예약(PRE-ORDER)·재고(IN STOCK) | 이 PC에서 열림, 예약 기간·발송월 있음 | 부분집합·영어명, 재판 라벨 없음, 검색·정렬 URL은 robots 차단, 상품 페이지 간헐 오류 |
| ③ 조이하비 재입고 글(4장) | 한국 시장의 재입고 신호 | 이미 수집 가능 | 일본 예약/재판과 시차·불일치 |
| ④ 수동 관리 | `events.json`처럼 재판 소식을 사용자가 입력 | 확실함 | 수고 |
| (비권장) 일본 IP에서 실행 | 일본 거주지 PC/서버 | 지역 제한 안 걸림 | 지역 제한 우회 소지, 운영 비용 — 권하지 않음 |

### 6-2. 일본 재판 이력 부재(호비사이트)
| 대안 | 내용 | 비고 |
|---|---|---|
| ① 조이하비 반다이 재입고 → `kr` 이력 | "재판 공백"의 기준을 "마지막 **국내 입고**"로 바꿈 | SPEC 4장 `kr[]`가 이미 이 용도. `releases` 쪽 reissue는 비어 있음 |
| ② 해외 P-반다이 예약 시작 | 재예약 신호 일부 (US 한정) | 라벨 없어 간접 추정 |
| ③ 외부 일본 판매점·정보 사이트의 재판 목록 | 후보 | **이번 spike에서 열어 보지 않음 [미확인]** — 필요하면 별도 spike |

### 6-3. 이미지 서명 URL
| 대안 | 내용 | 비고 |
|---|---|---|
| ① 안정 URL만 링크, 서명 URL 상품은 이미지 없음 + 호비사이트 상세 링크로 대체 | 사이트가 깨지지 않음 | 최신 상품일수록 이미지 없음 |
| ② 크롤러가 실행마다 URL 갱신 | 갱신 직후는 보임 | 만료 40~299초 → 방문자는 거의 못 봄. 비실용 |
| ③ 이미지 재호스팅 | — | CLAUDE.md/SPEC이 금지 |
| ④ 이미지 없이 등급 글자 자리표시 | SPEC 6장의 실패 시 폴백과 동일 | 단순 |

## 7. SPEC에 미치는 영향 · 사용자 결정 필요

1. **재판 데이터 소스**(핵심): 호비사이트에는 재판 정보가 없고 P-반다이(JP)는 접근 불가. "재판 공백" 기능을 `kr`(국내 입고) 기반으로 바꿀지, 해외 P-반다이/외부 소스를 더 조사할지 결정 필요.
2. **이미지 방침**: 6-3 중 선택. 현재 SPEC(4장 `images[]`·6장 CSP)은 서명 URL을 전제하지 않았다.
3. **P-반다이**: 6-1의 ①(+③) 정도로 축소할지, 해외 사이트(②)를 추가로 볼지.
4. **Playwright**: 호비사이트는 Actions에서도 `requests+bs4`로 열렸다(2.1절) → 호비 쪽은 Chromium 설치 단계가 필요 없어 보인다. **단 조이하비는 spike에서 Playwright로만 접속**했고(로컬·Actions 모두 `requests` 단독 시험 없음, `requests.log`의 `pw-*` 태그) P-반다이도 마찬가지다. 조이하비를 `requests`로 열어 보는 확인이 2단계 구현 전에 한 번 필요하다. Chromium 단계를 뺄지는 그 확인 뒤에 정한다.
5. 카탈로그 `images[].kind`(box/cg/sample)는 URL로 판별 불가 → 2.5절의 위치 휴리스틱을 쓰거나 `kind`를 없애고 순서만 쓰는 쪽으로 단순화 검토.
6. 걸프라 `line` 분류 범위(2.6절 후보) 확정, "LINKL PLANET" 포함 여부.
7. 호비 일정의 발매일이 **월만**인 항목(ホビーオンライン 전부, 일부 신제품)이 있어 `releases[].date`는 선택 필드로 두는 게 맞다(SPEC 4장 이미 `month`만 허용).

## 8. 실행 기록·준수 사항

- 총 요청 76건 (`spike/evidence/requests.log`): 호비 52 · 조이하비 12 · p-bandai.com 7 · p-bandai.jp 4 · CloudFront 1. 상세 페이지 **26/30** (호비 17, P-반다이 JP 1, P-반다이 해외 2, 조이하비 6) — `spike/evidence/budget.json`.
- 요청 시작 시각 간격은 코드(`common._wait`)로 **1.2초 이상** 보장. 로그에서 1.2초 미만으로 보이는 3건은 해석상 문제: ① 초기 robots.txt 3건은 로그 수정 전이라 *종료* 시각이 기록됨(간격 0.96·1.15초로 보이나 시작은 1.2초 이상으로 대기), ② p-bandai.com robots → 홈이 1.19초(Windows 시계 해상도 약 15ms 오차).
- robots 차단 경로 요청 0건 (`SKIP` 줄 0). p-bandai.jp는 robots를 읽을 수 없어 호비사이트가 직접 링크하는 주소 3개만 열었다.
- 이미지는 **저장하지 않음**. 브라우저가 화면에 띄우는 이미지 로드(핫링크 테스트 2회, 37장 + 45장, 1.3초 간격)와 만료 URL 1건의 확인 요청(403 XML 앞 200바이트)만 있었다. 크롤링 중에는 이미지·미디어·폰트를 Playwright 라우팅으로 차단했다.
- 실수 1건: 파서 정규식 버그로 조이하비 상품 페이지(`ANN26713`) 1개를 불필요하게 한 번 더 열었다(`requests.log`에 보임). 상세 예산 6/6 이내이고 fixture는 지웠다.
- Actions 실행(`spike/evidence/actions/requests.log`): 요청 63건 — 호비 43 · 조이하비 11 · p-bandai.com 4 · p-bandai.jp 4 · CloudFront 1. 상세 25/30(호비 17, P-반다이 JP 1, 해외 2, 조이하비 5). 시작 시각 간격 최소 1.20초(1.2초 미만 0건), 로그에 robots가 막는 경로 요청 없음, 결과 폴더에 이미지 파일 없음.
- fixture는 `<script>/<style>/<noscript>`를 제거한 렌더링 DOM이다(용량·추적 ID 제거). 원본 응답과 다른 점은 그것뿐이다 (22개, 2.4MB).
- 디스코드·Claude API 호출 없음. commit/push 없음. 지역 제한 우회 없음.

## 9. Actions 결과 — 로컬과 다른 점

같은 스크립트·같은 상한(`python spike/run_all.py --env actions --out spike/out-actions`: 상세 합계 30개 이하, 요청 간 1.2초 이상)으로 돌렸다. 로컬 `spike/evidence/`와 Actions `spike/out-actions/`를 서명 URL·시각·줄바꿈을 빼고 기계적으로 비교한 결과다.

**같은 것 (핵심)**
- **접속·리다이렉트**: 양쪽에 모두 있는 URL 58개의 상태·리다이렉트 수·최종 URL 차이 **0건**. 호비사이트 일정 18쪽·상세 17개·브랜드·`item_all`은 전부 200/리다이렉트 0. 조이하비는 홈 1회 리다이렉트(정상)뿐. 리다이렉트 1회인 5건 = p-bandai.jp 4건 + 조이하비 홈 (로컬과 동일). 403은 만료 서명 URL 직접 확인 1건뿐.
- **호비사이트·조이하비 데이터**: 일정 카드 수, 상세 필드, 필터 목록(`filters`), 조이하비 목록 51행·반다이 리스트 글·파싱 141건이 로컬과 같다. 차단·캡차·빈 페이지 없음.
- **P-반다이 JP**: 3/3 + robots 모두 `global_newpc.html`로 지역 리다이렉트 (3.1절 결론 유지).
- **핫링크**: 5장 표대로 행별 같음. 서명 URL은 받은 시각 + 300초에 만료(71개 측정, 남은 시간 73~300초).

**다른 것**
1. **호비사이트 쿠키 배너 변형** — Actions fixture 10개 전부에 "Privacy Policy for California Residents / Do Not Sell or Share My Personal Information"이 들어 있고 로컬 fixture에는 없다(OneTrust). 접속 지역에 따라 배너만 바뀌는 것으로 보이며, 러너 위치가 미국이라는 정황이지만 위치는 조회하지 않았다. 일정 카드·상세 필드·이미지 URL에는 차이가 없어 파서에 영향은 없다(배너 DOM을 건드리지 않는 한). 그 밖의 차이는 swiper 랜덤 ID와, 로컬에만 있는 t.co 트래킹 픽셀(`01_4257`에서 확인).
2. **P-반다이 US 상품 페이지** — 로컬 1/2 열림 → Actions **0/2** (둘 다 `PAGE NOT AVAILABLE`). 홈은 둘 다 열린다. 대안 A(6-1 ②)는 환경에 따라 더 불안정하다는 근거가 추가됐다.
3. **조이하비** — 본문은 조회수 숫자(예: 17316→17626)만 다르다. 상세 예산은 6→5(로컬의 `ANN26713` 실수 요청이 Actions에는 없음).
4. **로컬 전용 보조 요청은 Actions에서 반복하지 않았다**(차이가 아니라 미실행): 호비 `/`, `/news/`, `/news/?cat=new_product`, `/news/?cat=online_shop`, `/site/schedule.html`, `/characterplastic/`, p-bandai.com `/us/news/463`, `/us/sitemap.xml`, 조이하비 `ANN26713`, 만료 서명 URL 직접 확인(Actions는 다른 URL로 같은 403). 그래서 2.3절의 납품 예정표 중단 공지와 3.3절의 `?cat=online_shop` 뉴스는 **로컬 근거만** 있다.
5. 서명 URL 남은 시간 최솟값 40초(로컬) → 73초(Actions): 받은 시각에서 측정 시각까지의 지연 차이이고 TTL 자체는 둘 다 300초다.

**여전히 미확인**
- **github.io 오리진에서의 핫링크** — 로컬·Actions 모두 `http://localhost:8000` 오리진이다.
- **조이하비·P-반다이를 `requests`로 연 적이 없다** — 둘 다 Playwright(`pw-*`)로만 접속했다. 호비사이트만 `requests` 단독 확인(7장 4번).
- 러너의 실제 IP 위치 (조회하지 않음).
- Actions 쪽 스크린샷은 결과에 없어 이미지 종류(박스/CG/작례) 위치 규칙은 로컬 육안 확인 그대로다.

**근거 파일 보관**: 요약 JSON 5개(`hobby`·`pbandai`·`joyhobby`·`hotlink`·`run`)와 `requests.log`는 `spike/evidence/actions/`에 복사해 커밋 대상으로 두었다(원본과 바이트 단위로 같음). `hobby-summary.json`에는 로컬 `spike/evidence/hobby-summary.json`과 마찬가지로 이미 만료된 서명 URL이 들어 있다. `budget.json`, `hobby-images.json`(서명 URL 목록), robots 원문, fixture는 복사하지 않았다. 호비·조이하비 fixture는 위 차이(쿠키 배너·조회수 등)를 빼면 로컬과 같아 `tests/fixtures/`의 기존 것을 쓰고, Actions 원본 전체는 `spike/out-actions/`(gitignore)에만 있다.

## 10. 파일

- 스크립트: `spike/common.py`, `hobby.py`, `pbandai.py`, `joyhobby.py`, `hotlink_check.py`, `run_all.py`, `requirements.txt` · 테스트 페이지 `spike/hotlink-test.html` · 워크플로 `.github/workflows/spike.yml` · `.gitignore`
- 근거: `spike/evidence/` (요약 JSON 4개, `requests.log`, `budget.json`), `spike/evidence/actions/` (Actions 실행분: 요약 JSON 5개, `requests.log`), `tests/fixtures/` (22개: robots 4, 호비 10, P-반다이 3, 조이하비 5)
- 로컬 전용(gitignore): `spike/out/`(캐시 포함), `spike/out-actions/`(Actions artifact `spike-actions-results` 압축 해제본 전체: 요약 JSON, `requests.log`, `budget.json`, `hobby-images.json`, `run-summary.json`, fixture 21개 — 9장), `spike/screenshots/hotlink-local.png`

로컬 재실행: `conda activate plamo; python spike/run_all.py --env local` (캐시가 있으면 이미 받은 URL은 재요청하지 않는다).
