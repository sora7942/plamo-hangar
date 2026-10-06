# SPEC — plamo-hangar (프라 격납고)  v1.1

내 프라모델(건프라·걸프라) 컬렉션과 위시리스트를 관리하고, 반다이 신제품 소식과 국내 입고(재입고) 소식을 모아 보여주는 사이트.
GitHub Pages(공개 저장소 `sora7942/plamo-hangar`)로 서비스한다. GitHub Actions가 하루 한 번 소식을 모아 저장소에 커밋하고, 디스코드 웹훅으로 알린다.

> 이전 버전은 Claude 아티팩트였다(`reference/artifact-v2.html`). 화면·기능(보유/위시 탭, 통계, 필터, 빈 칸 모아보기, 일괄 수정, 중복 경고, 태그, 조립 기록, 엑셀 가져오기·백업)은 v2를 그대로 살린다.
>
> **v1.1 변경 (0단계 결과 반영, `spike/report.md`)**
> - 일본 재판 정보는 공식 경로로 얻을 수 없다(호비사이트는 최초 발매만 싣고 납품 예정표를 중단, P-반다이 JP는 일본 밖 접속 불가) → **재판은 조이하비 국내 입고 기준**
> - 호비사이트 2025년 이후 상품 이미지는 수 분 안에 만료되는 서명 URL → **안정 URL이 있는 상품만 공식 사진 표시**, 나머지는 자리표시 + 공식 페이지 링크
> - 이미지 종류(박스/CG/작례)는 자동 구분 불가 → `kind` 삭제, **소유자가 대표 사진을 고른다**
> - P-반다이는 호비사이트 일정의 ホビーオンライン 카드로 **한정판 신규 발매 월만**
> - 호비사이트는 일반 `requests`로 열림 → Playwright는 Actions에서도 필요 없으면 쓰지 않는다

## 1. 목표
- `https://sora7942.github.io/plamo-hangar/`에서 사이트가 열린다. 방문자는 보기만 하고, 소유자는 사이트에서 직접 추가·수정·삭제·사진 업로드를 한다
- 내 프라를 반다이 제품 목록(카탈로그)의 제품과 **연결**하면 등급·스케일·시리즈가 채워지고, 안정 URL이 있는 제품은 공식 사진이 자동으로 보인다
- 매일 1회 다음 소식을 모아 사이트의 "신제품·입고" 탭과 디스코드로 알린다
  - 반다이 호비사이트 월별 일정: 건프라 + 걸프라(30MS, 30MP, Figure-rise Standard) **신제품 발매 일정**
  - 같은 일정의 ホビーオンライン(P-반다이) 카드: **한정판 신규 발매 월**
  - 조이하비 공지 게시판의 반다이 제품리스트: **국내 재입고·신규 입고**
- 보유·위시 프라 중 카탈로그와 연결된 것에 **재판 공백**(마지막 국내 입고 후 경과)을 표시하고 그 순서로 정렬할 수 있다
- 비용: GitHub 무료. 한국어 이름 번역에 Claude API (처음 전체 번역 1~2달러 수준, 이후 신제품만)

## 2. 범위 밖 (하지 않음)
- 일본 재판(再販) 일정 수집 — 공식 출처 없음
- P-반다이 JP 직접 수집 — 지역 제한. VPN·프록시·일본 서버 등 **지역 제한 우회 금지**
- 서명 URL 이미지를 살리려는 시도(주기 갱신, 프록시 리다이렉트 등) — 반다이가 핫링크를 막으려는 설정이므로 우회하지 않는다
- 공식 이미지·리뷰어 사진 내려받기·재호스팅. 리뷰는 "리뷰 찾아보기" 검색 링크만
- 조이하비 상품 이미지 핫링크 (판매점 자원)
- 반다이 외 브랜드 카탈로그 (내 컬렉션에는 수동 입력 가능)
- 가격 비교, 재고 실시간 감시, 로그인 시스템

## 3. 저장소 구조
```
plamo-hangar/
├─ .github/workflows/
│  ├─ crawl.yml                 # 매일 1회 수집 → docs/data 커밋 → 디스코드 (+ 수동 실행)
│  └─ spike.yml                 # 0단계 검증용 (그대로 둠)
├─ docs/                        # GitHub Pages 루트 (Deploy from branch: main /docs)
│  ├─ .nojekyll
│  ├─ index.html (+ app.js, style.css)
│  ├─ data/
│  │  ├─ collection.json        # [사이트] 내 보유·위시
│  │  ├─ catalog-gunpla.json    # [자동]
│  │  ├─ catalog-girl.json      # [자동]
│  │  ├─ catalog-pending.json   # [자동] 아직 line을 모르는 항목 + 제외 목록 (4장)
│  │  ├─ feed.json              # [자동]
│  │  └─ meta.json              # [자동]
│  └─ photos/<kitId>/<photoId>.webp, <photoId>_t.webp   # [사이트] 내 사진
├─ crawler/
│  ├─ config.py                 # URL, 브랜드 키 → line 사전, 등급 키 매핑, 개수 제한, 알림 규칙, 모델명
│  ├─ http.py                   # spike/common.py의 RateLimiter·robots 게이트·로그를 정리해 옮김
│  ├─ sources/
│  │  ├─ hobby_schedule.py      # 월별 일정 (일반·ホビーオンライン·ガンダムベース 카드)
│  │  ├─ hobby_item.py          # 상품 상세
│  │  ├─ hobby_brand.py         # 브랜드 목록 페이지 (걸프라 4개 브랜드 열거)
│  │  └─ joyhobby.py            # 공지 게시판 반다이 제품리스트 (3단계)
│  ├─ catalog.py                # 병합·분류·밀린 상품 선택·저장
│  ├─ match.py                  # 3단계
│  ├─ translate.py  feed.py  discord.py
│  ├─ pipeline.py               # 실행 순서(일정 → 브랜드 → 상세 → 번역 → 피드 → 쓰기 → 디스코드). main.py는 인자 처리만
│  └─ store.py                  # JSON 읽기·쓰기(한 항목 한 줄), 시간 helper
├─ spike/                       # 0단계 결과 (보존)
├─ tests/ (fixtures/ 포함)
├─ reference/artifact-v2.html
├─ main.py  requirements.txt  .env.example  CLAUDE.md  SPEC.md  README.md
```

## 4. 데이터 스키마

### collection.json (사이트가 씀, 크롤러는 읽기만)
```json
{"version":3,
 "settings":{"name":"프라 격납고","hidePurchase":true,"hideOfficialPhotos":false},
 "kits":[{
   "id":"k...","created":"ISO","list":"own|wish",
   "name":"건담 에어리얼","grade":"HG","scale":"1/144","series":"","brand":"반다이",
   "status":"unbuilt|building|built|custom","date":"YYYY-MM-DD","shop":"","price":0,
   "tags":[],"startDate":"","doneDate":"","memo":"",
   "catalogId":"bh-01_4257|null",
   "photos":[{"id":"p...","src":"photos/k.../p....webp","thumb":"photos/k.../p..._t.webp"}],
   "cover":"off:2|my:p...|null"
 }]}
```
- v2 필드는 그대로. 새 필드: `catalogId`, `photos`, `cover`, `settings.hideOfficialPhotos`
- v2의 `photo`(data URI)는 가져오기 때 WebP 파일로 바꿔 `photos[0]`에 넣는다
- 사진 순서: `cover`로 지정한 사진 → 나머지 공식 사진(사이트 순서) → 내 사진. `cover`가 없으면 내 사진이 있으면 내 첫 사진, 없으면 공식 첫 사진
- 공식 사진이 없으면 등급 글자 자리표시 + "공식 사진 보기" 버튼(호비사이트 상품 페이지)
- 구매 정보는 공개 저장소에 그대로 보인다. `hidePurchase`는 화면에서만 숨긴다는 안내를 설정 화면에 유지

### catalog-*.json (크롤러가 씀)
```json
{"updatedAt":"ISO","items":[{
  "id":"bh-01_4257","url":"https://bandai-hobby.net/item/01_4257/",
  "line":"gunpla|girl","brandKeys":["hg"],"grade":"HG","scale":"1/144",
  "seriesKey":"g-witch","series":"機動戦士ガンダム 水星の魔女",
  "nameJa":"HG 1/144 ガンダムエアリアル","nameKo":"HG 1/144 건담 에어리얼",
  "priceJpy":1760,"channel":"general|online|gbase","pbUrl":"https://p-bandai.jp/item/item-...|null",
  "release":{"month":"2022-10","date":"2022-10-01"},
  "kr":[{"date":"2026-09-29","type":"restock|new","source":"joyhobby","post":"139459","code":"BD5068846","priceKrw":46800,"seenAt":"ISO"}],
  "images":["https://bandai-a.akamaihd.net/bc/img/model/xl/1000179163_1.jpg"],
  "firstSeen":"ISO","updated":"ISO","detailAt":"ISO|null"}]}
```
- `id`: `bh-` + 호비사이트 상품 번호(`01_N`). ホビーオンライン 카드처럼 호비 상세가 없는 상품은 `pb-` + P-반다이 번호(`item-N`)
- `detailAt` *(2단계에서 추가)*: 상세 페이지로 확정한 시각. **null이면 일정·브랜드 카드와 제목으로 만든 임시 항목**이다(이름·가격·발매일·채널만 믿을 수 있고 `images`·`series`는 비어 있다). 상세 실패가 반복되면 `detailFails`(횟수)가 붙고 3회부터 더 시도하지 않는다
- `channel`: 일정 카드의 묶음. `online`=ホビーオンライン, `gbase`=ガンダムベース 계열(GUNDAM SIDE-F 포함), `general`=그 외. 상세로는 알 수 없어 일정·브랜드 카드에서만 채워진다
- `release`: 일본 최초 발매. 날짜를 모르면 `month`만
- `kr`: 국내 입고 이력. **쌓기만 하고 지우지 않는다.** 같은 (post, code)는 한 번만
  - `type`: 카탈로그 발매일보다 60일 이상 뒤면 `restock`, 아니면 `new` (발매일을 모르면 게시글에 "재입고" 문구가 있을 때만 `restock`, 없으면 `new`)
- `images`: **안정 URL만** (호스트가 `bandai-a.akamaihd.net`, `bandai-hobby.net`). 서명 URL(`?Expires=`)은 저장하지 않는다. 사이트 갤러리 순서 그대로
- `grade`: 브랜드 키 → 등급 매핑(`hg`/`hg-c`/`pb_hg`→HG, `rg`/`rg-c`→RG …)은 `config.py`. 없으면 상품명 앞 토큰
- `scale`: 상품명의 `1/N` 정규식. 없으면 `null`
- `line`: `config.py`의 브랜드 키 사전(`BRAND_LINE`, 호비 필터 키 77개 전부 분류)으로 **확정**한다. 키 중 하나라도 girl이면 girl, 아니면 gunpla 키가 있으면 gunpla, 둘 다 없으면 제외. 사전에 없는 새 키도 제외하고 `meta.unknownBrandKeys`에 남긴다
  - girl: `30ms`, `30mp`, `figurerise-standard`, `figurerise-standard-amp` (브랜드 목록으로 전체 수집). `figurerise-bust`는 제외 — 한 번 걸프라로 옮겼다가 첫 crawl 결과를 보고 다시 제외로 돌렸다
  - gunpla: 건프라 등급·라인 키 (분류표는 사용자가 확인)
  - **브랜드 키가 항상 우선**: 브랜드 키가 하나라도 있으면 그 키로만 판정한다. 키가 제외 브랜드(또는 사전에 없는 키)면 제목이 대상처럼 보여도 항목을 만들지 않고 제외한다 — 제목 판정은 브랜드 키를 **모를 때**(일정 카드)만 쓴다
  - **기존 항목 재분류**: 매 실행 시작(수집 전, `--only`와 무관)에 이전 실행이 저장한 항목을 분류표로 다시 분류한다. 브랜드 키가 있는 항목이 제외 브랜드면 제외 목록으로 옮기고(`brand:<키들>`), line·등급이 달라졌으면 고친다. 그래서 분류표만 고치면 다음 실행에 기존 데이터까지 반영된다. 결과는 `meta.crawl.lastFixups`. **한계**: 제외 → 포함 방향은 되살리지 못한다(제외 목록에는 id와 사유뿐이라 항목 데이터가 없다). 그 경우는 일정·브랜드 목록을 다시 훑어야 한다
  - **상세 전 임시 판정**: 일정 카드에는 브랜드 키가 없어 제목 앞 토큰(`HG`·`RG`·`MG`·`30MS`… 전각은 NFKC로 정규화)으로 line을 임시로 정한다. 임시 판정이 안 되는 카드는 `line=null`로 `catalog-pending.json`에 보류하고, P-반다이 카드(상세 없음)는 제목으로도 판정이 안 되면 제외한다
- `catalog-pending.json`: `{"updatedAt","items":[line=null 항목],"excluded":{"<id>":"<사유>"}}`. 사유는 `brand:<키들>`·`no-brand-key`·`title-no-match`·`detail-404`. 제외된 id는 일정에 다시 나와도 항목을 만들지 않고 상세도 다시 받지 않는다
- `nameKo`: 번역 실패·키 없음이면 `null`. 사이트 검색은 nameKo·nameJa 모두 대상

### feed.json (크롤러가 씀)
```json
{"updatedAt":"ISO","items":[{
  "id":"jh-139459-BD5068846","type":"new|pb-new|kr-restock|kr-new",
  "date":"2026-10|2026-09-29","added":"ISO","catalogId":"bh-01_4257|null",
  "title":"원문 제목","titleKo":"...","url":"https://...","image":"안정 URL|null","source":"bandai-hobby|joyhobby"}]}
```
- id: 호비 신제품 `bh-new-<번호>`(예 `bh-new-01_7249`), P-반다이 `pb-new-<번호>`(예 `pb-new-item-1000249921`), 조이하비 `jh-<글번호>-<상품코드>`
- 호비 신제품 항목은 **이번 실행에서 처음 발견**됐고, 판정이 끝나 line이 gunpla/girl이며, 발매월이 이번 달 이후인 것만 만든다(지난 달 발매분을 최초 채우기로 훑을 때는 만들지 않는다). P-반다이 항목의 `url`은 P-반다이 링크(요청하지 않는다), `image`는 안정 URL이 있을 때만 — P-반다이 카드는 항상 `null`
- `added`: 처음 발견한 시각. 바꾸지 않는다. `titleKo`·`image`는 나중에 번역·상세로 채워지면 빈 칸만 보충한다
- 보관: `added` 내림차순 최대 1000개

### meta.json
```json
{"updatedAt":"ISO","since":"수집 시작 YYYY-MM-DD",
 "sources":{"hobby_schedule":{"ok":true,"at":"ISO","items":21,"error":null},"hobby_brand":{...},"hobby_item":{...},
            "translate":{"ok":true,"at":"ISO","items":50,"error":null,"pending":0,"skipped":null,"model":"...","kanaRetried":0,"kanaRejected":0},"joyhobby":{...}},
 "crawl":{"scheduleFrom":"2015-01","girlBrandsDone":["30ms"],"backlog":120,"counts":{"gunpla":0,"girl":0,"pending":0,"excluded":0},
           "lastFixups":{"toExcluded":0,"lineChanged":0,"nameKoReplaced":0,"feedTitleKoReplaced":0}},
 "stats":{"requests":0,"byKind":{},"failures":0,"elapsedSec":0,"minGapSec":1.2},
 "unknownBrandKeys":[]}
```
- `sources`는 단계별로 나눈다(`hobby`를 `hobby_schedule`·`hobby_brand`·`hobby_item`으로). 일부 항목만 실패하면 `ok:false`와 실패 목록이 `error`에 들어간다. `--only`로 돌리지 않은 소스는 이전 값을 유지한다
- `crawl.lastFixups`: 이번 실행 시작에 적용한 기존 데이터 보정 결과(재분류로 제외된 수·line 변경 수·nameKo/피드 titleKo 치환 수). 매 실행 덮어쓴다
- `crawl`: 최초 채우기 커서(5장) — `scheduleFrom`은 "이 달부터 현재까지 일정을 다 훑었다", `girlBrandsDone`은 전체 쪽수를 끝낸 걸프라 브랜드, `backlog`는 상세를 기다리는 항목 수(0이 되면 채우기 완료)
- 사이트 하단에 "마지막 수집"과 실패한 소스, 재판 공백 문구에 `since`를 쓴다

## 5. 수집 소스 (0단계에서 확인한 구조)
| 소스 | URL | 파싱 | 주기·양 |
|---|---|---|---|
| 호비 월별 일정 | `https://bandai-hobby.net/schedule/index.php?saledate=YYYYMM` | 카드 `a.p-card` (`.p-card__tit`, `.p-card__price`, `.p-card_date`). 묶음 ①일반 `/item/01_N/` ②ホビーオンライン `.p-card__tag.-online` → `p-bandai.jp/item/item-N`, 월 단위 ③ガンダムベース | 매일: 이번 달 ~ +3개월. 과거 월은 최초 채우기(`--bootstrap`) 때 `2015-01`까지 한 번만 |
| 호비 상품 상세 | `https://bandai-hobby.net/item/01_N/` | `h1.p-heading__h1-product`, `dl.pg-products__detail dt/dd`, `a.pg-products__pblink`, `li.p-card__link a.p-card__flat`(브랜드·작품 키), 갤러리 이미지 | 상세가 없는 `bh-` 항목만. 실행당 **새 상품 최대 40 + 밀린 상품 최대 150** |
| 호비 브랜드 목록 | `https://bandai-hobby.net/brand/<key>/?p=N` (`a.c-archives__pagination-list-item-link`) | 카드 `a.p-card`(일정 카드와 같은 구조, 슬라이드 `a.p-slide__link`는 제외) | 걸프라 4개 브랜드: 매일 1쪽, 최초 채우기 때 전체 쪽수 |
| 조이하비 공지 | `https://www.joyhobby.co.kr/mall/board_list.asp?siteid=joyhobby&BoardCode=notice&nowPage=N` → 글 `board_view.asp?SiteID=joyhobby&BoardCode=notice&B_iID=<번호>` | 제목에 `반다이 제품리스트`가 있는 글. 본문 `상품코드 / 상품명 / 가격` 3줄 반복. 반다이 코드 `BD#######`만 | 매일 목록 1~2쪽, 처음 보는 글만 |

- 호출: `requests` + `beautifulsoup4`. Actions에서 결과가 로컬과 다르면(차단·리다이렉트) 그 소스만 Playwright로 바꾼다
- 모든 요청: robots.txt 준수, 요청 간 1.2초 이상, timeout 20초, 브라우저 형태 User-Agent, `requests.log`와 같은 형식으로 로그
- 소스 하나가 실패해도 계속하고 `meta.json`에 기록
- **최초 채우기**(`--bootstrap`) *(2단계에서 방식 변경: 카드 먼저, 상세는 나눠서)*
  1. **일정 카드만으로 먼저 카탈로그 항목을 만든다**(이름·가격·발매일·상품 번호·채널). 상세가 없어도 검색되도록 제목 앞 토큰으로 line·등급·스케일을 임시 판정한다(4장 `detailAt`이 null인 항목)
  2. 건프라는 일정을 `2015-01`(`--from`으로 변경)부터 이번 달까지 **최신 달부터 거슬러** 훑는다. 한 번에 끝나는 양(약 140개월)이고, 중간에 실패하면 거기서 멈추고 `meta.crawl.scheduleFrom` 커서를 남겨 다음 실행이 이어서 한다
  3. 걸프라 4개 브랜드는 브랜드 목록을 전체 쪽수로 훑는다(브랜드 키가 목록에서 이미 알려져 line·등급이 바로 확정된다). 끝난 브랜드는 `meta.crawl.girlBrandsDone`에 기록
  4. **상세는 실행마다 새 상품 최대 40 + 밀린 상품 최대 150**만 받는다(`--max-new`, `--max-backlog`; 합계 400 초과 불가). 밀린 상품은 임시 판정이 된 것 먼저, 발매일 최신순이다. 새 상품이 40개를 넘으면 남은 것도 밀린 슬롯에서 같은 순서로 경쟁한다(그래서 첫 실행도 190개를 받는다). 상세가 오면 브랜드 키로 line이 확정되고, 대상이 아니면 `catalog-pending.json`의 제외 목록으로 간다. `meta.crawl.backlog`가 0이 되면 채우기 끝 — 하루 1회 예약 실행만으로는 며칠 걸리므로 수동 실행(`workflow_dispatch`)을 여러 번 돌려 앞당긴다
  5. 최초 채우기 중에는 디스코드 알림이 없다. 그 이전 상품(2015-01 이전)은 사용자가 연결하려 할 때 상세 URL을 붙여넣어 추가할 수 있게 한다(6장)
- 조이하비 과거 글: 최초 채우기 때 공지 게시판을 거슬러 올라가 반다이 제품리스트 글을 모은다. 몇 쪽까지 가능한지는 3단계에서 확인하고 `meta.since`에 기록

### 매칭 (`match.py`) — 조이하비 상품명 ↔ 카탈로그
- 상품명 형식: `[등급코드] 스케일 모델번호 한글명(영문명) - 작품(프라모델)` (0단계 표본 141건, `tests/fixtures/joyhobby-post-*.html`)
- 대괄호 코드 → 등급: `HGUC/HGAW/HGWFM/HGCE…`→HG, `RG`, `MG`, `MGSD`, `30MM_*`→30MM, `[피규어라이즈스탠다드]`→Figure-rise Standard 등 (사전은 config)
- 비교 키: 등급 + 스케일 + 영문명(괄호 안)을 우선, 없으면 한글명 ↔ `nameKo`. rapidfuzz, 임계값 config
- 애매하면(후보 2개 이상·점수 차 작음) 연결하지 않는다. 연결 안 된 항목도 피드에는 넣는다

### 번역 (`translate.py`)
- 새 카탈로그 항목만, 50개씩 Claude API. 한국 정식 명칭을 따르게 하고 JSON으로 받는다. 조이하비에서 매칭된 한국어 이름이 있으면 그걸 우선 쓴다
- 모델명은 `config.CLAUDE_MODEL` (daily-tech-digest와 같은 방식). `ANTHROPIC_API_KEY` 없으면 건너뜀
- **가나 검사**: 번역(`ko`)에 히라가나·가타카나가 남아 있으면(예: `[カラーC]`) **그 항목만 한 번** 다시 요청한다(앞선 번역을 `prev_ko`로 알려 줌). 그래도 남으면 `nameKo`를 비워 두고 다음 실행에서 다시 시도한다. 중점 `・`은 가나로 보지 않는다. 재요청 수와 비운 수는 `meta.sources.translate`의 `kanaRetried`·`kanaRejected`
- **용어집**: 자주 나오는 고유명사·표기는 `config.TRANSLATE_GLOSSARY`(일본어 → 한국어 사전)에 두고 시스템 프롬프트에 그대로 넣는다. 틀린 번역이 보이면 한 줄 추가하면 되고, 값에 가나를 쓰지 않는다(테스트가 확인)
- **영문 그대로 두는 말**: 용어집 값이 영문이면 영문 그대로 쓴다(예: `アンプリファイド → Amplified`). 시스템 프롬프트에도 `Amplified`는 번역·음역하지 말라는 규칙이 있다
- **nameKo 후처리**: `config.NAME_KO_REPLACEMENTS`(예: `앰플리파이드 → Amplified`)를 매 실행 시작과 번역 직후에 `nameKo`(와 피드의 `titleKo`)에 부분 문자열 치환으로 적용한다. 용어집을 고친 뒤 이미 저장된 번역을 맞추는 용도이고, 해당 글자 외에는 `updated` 포함 아무것도 바꾸지 않는다
- 수동 확인: `python -m crawler.translate --sample 20` — 실제 파이프라인과 같은 경로(가나 재요청 포함)로 fixture 제목 20개를 한 번 번역해 출력. 테스트는 실제 Claude를 호출하지 않는다(클라이언트 생성·`.env` 읽기를 `conftest`가 막음)

## 6. 사이트 — 소유자 모드와 저장
- 설정에서 **GitHub fine-grained 토큰**(이 저장소만, Contents: Read and write)을 넣으면 소유자 모드. 토큰은 그 브라우저 localStorage에만. `GET /repos/sora7942/plamo-hangar`의 `permissions.push`로 확인
- 소유자 모드는 collection.json을 GitHub API로 직접 읽는다(Pages 배포 지연 회피). 방문자는 Pages 파일
- 저장 1회 = 커밋 1개. 여러 파일이 바뀌면 Git Data API(blob → tree → commit → ref)로 한 커밋. ref 갱신이 fast-forward가 아니면 최신을 다시 읽고 알린 뒤 다시 적용할지 묻는다
- 커밋 메시지: `collection: <동작 요약>`
- 사진: 긴 변 1600px WebP(0.82) + 480px 썸네일. 여러 장, 순서 바꾸기·삭제·**대표 사진 지정**(공식·내 사진 중에서). 삭제 시 파일도 같은 커밋에서 지운다
- 저장 후 "사이트 반영까지 1~2분" 안내
- 보안: 외부 문자열(카탈로그·피드·메모)은 전부 이스케이프. CSP: script self + cdnjs, connect self + api.github.com, img self + `bandai-a.akamaihd.net` + `bandai-hobby.net`
- 외부 이미지: `referrerpolicy="no-referrer"`, `loading="lazy"`, 실패하면 자리표시

### 화면 추가·변경 (v2 대비)
- **신제품·입고 탭**: 필터 — 종류(신제품 / P-반다이 한정 / 국내 재입고 / 국내 신규), 라인(건프라/걸프라), 등급. **내 보유·위시와 연결된 항목은 맨 위에 "내 프라" 표시로 강조**. 항목에서 "위시리스트에 추가"(카탈로그 연결된 채로)
- **카탈로그 연결**: 추가·수정 폼의 "반다이 제품에서 찾기"(한국어/일본어, 등급 필터). 고르면 이름·등급·스케일·시리즈를 채우고 `catalogId` 저장. 카탈로그에 없으면 호비사이트 상품 URL을 붙여넣어 연결할 수 있다 — 이 경우 사이트는 `catalogId`만 저장하고, 다음 크롤러 실행이 `collection.json`에서 카탈로그에 없는 `catalogId`를 찾아 상세를 받아 채운다
- 기존 프라는 상세의 "반다이 제품 연결" 버튼, 설정의 "자동 연결 후보 보기"(이름이 확실히 같은 것만 제안, 확인 후 일괄 연결)
- **재판 공백** (연결된 보유·위시만):
  - 국내 입고 기록이 있으면 `국내 마지막 입고 2026-09-29 · 7일 전`
  - 없으면 `국내 입고 기록 없음 (YYYY-MM-DD 이후 기준) · 일본 발매 2022-10`
  - 일본 발매가 미래면 `일본 발매 예정 2026-12`
  - 정렬 "재판 공백 긴 순" (기록 없음은 일본 발매일 기준으로 맨 뒤 묶음), 빈 칸 모아보기에 "반다이 제품 미연결"
- **사진 보기**: 상세 갤러리. 공식 사진에는 "사진: BANDAI SPIRITS" + 원본 페이지 링크
- **리뷰 찾아보기**: 유튜브·네이버 블로그 검색 링크 (`<등급> <한국어 이름> 리뷰`)
- 엑셀 백업·가져오기에 `catalogId` 열 추가. 사진은 백업에 넣지 않는다

## 7. 디스코드 알림
- 매 실행 1회, 이번에 새로 들어온 피드 항목을 묶어 보낸다
- 순서: ① 내 보유·위시와 연결된 국내 입고 (따로 맨 앞, 강조 색) ② 국내 재입고·신규 ③ P-반다이 한정 신규 ④ 신제품 발매 일정
- 임베드: 제목 링크, 종류, 시기, 안정 이미지가 있으면 썸네일. 메시지당 10개, 실행당 3메시지, 넘치면 "외 N건 — 사이트에서 보기"
- 최초 채우기(`--bootstrap`) 중이거나 이전 feed가 비었거나 이전 카탈로그가 비어 있었으면(첫 실행) 보내지 않는다. `--dry-run`은 이 규칙으로 건너뛰는 경우에도 형식 확인용으로 보낼 내용을 출력한다
- `DISCORD_WEBHOOK_URL`이 없거나 `--dry-run`이면 콘솔 출력만. 발송 실패는 경고만

## 8. 실행 옵션
- `python main.py` / `--dry-run` / `--only hobby,joyhobby` / `--bootstrap`
  - `--only`: `hobby`(= `hobby_schedule`+`hobby_brand`+`hobby_item`), `translate` (3단계 이후 `joyhobby`)
  - `--bootstrap [--from YYYY-MM]`: 최초 채우기(5장). `--from`은 확인용으로 범위를 줄일 때(기본 `2015-01`)
  - `--max-new N` / `--max-backlog N`: 실행당 상세 상한(기본 40 / 150). `--max-details`는 폐지
  - `--data-dir DIR`: `docs/data` 대신 다른 폴더에 읽고 쓴다(로컬에서 부분 채우기를 저장소와 섞지 않으려고)
  - `--no-discord`: 발송만 끈다. `--dry-run`은 파일은 쓰고 디스코드는 보내지 않으며 **보낼 내용을 항상 출력**하고, API 비용이 드는 번역은 `--only translate`로 명시할 때만 돌린다
- 로컬 미리보기: `python -m http.server -d docs 8000`

## 9. GitHub Actions (`crawl.yml`)
- 트리거: `schedule: cron "10 22 * * *"` (KST 07:10), `workflow_dispatch`(입력: `bootstrap`, `max_backlog`(기본 150))
- `concurrency: { group: crawl }`, 권한 `contents: write`
- 단계: checkout → Python 3.12 + pip 캐시 → `python main.py` → 요청 로그 artifact(7일) → `git pull --rebase --autostash` → **허용 목록 5개만 add**(`catalog-gunpla/girl/pending.json`, `feed.json`, `meta.json`; 그 밖의 경로가 staged면 실패해 `collection.json`·`photos/`를 지킨다) → 변경이 있으면 커밋(`data: crawl YYYY-MM-DD`) → push(충돌 시 `pull --rebase` 후 최대 3회). `timeout-minutes: 45`
- 최초 채우기: 수동 실행에서 `bootstrap`을 켜고, `meta.crawl.backlog`가 0이 될 때까지 몇 번 반복한다(실행당 상세 최대 190개 + 일정·브랜드 수백 요청, 요청 간 1.2초 → 한 번에 10분 안팎)
- (Playwright가 필요해진 소스가 있을 때만) Chromium 설치 단계 추가
- Secrets: `DISCORD_WEBHOOK_URL`, `ANTHROPIC_API_KEY`
- Pages: Deploy from a branch → `main` / `/docs`
- **Actions에서 조이하비나 호비사이트가 해외 IP로 막히면**: 크롤러를 사용자 PC에서 Windows 작업 스케줄러로 돌리고 결과를 push하는 방식으로 바꾼다(사용자 결정)

## 10. 테스트 (네트워크 없이)
- fixture: `tests/fixtures/`의 0단계 저장본 (호비 일정·상세, 조이하비 목록·글)
- 파서: 일정 카드 3묶음 구분, 상세 필드, 브랜드 키 → 등급·line, 스케일 정규식, **서명 URL 제외**
- 조이하비: 반다이 리스트 글 식별, 3줄 파싱, BD 코드만
- 매칭: 0단계 표본 상품명(`[RG42] 1/144 … 샤이닝 건담(SHINING GUNDAM) …` 등)과 카탈로그 샘플, 애매한 경우 미연결
- `kr.type` 판정(60일 규칙, 발매일 없음)
- 피드: id 중복, `added` 유지, 1000개 자르기 / 알림: 내 프라 우선, bootstrap 미발송, 개수 제한
- 사이트 순수 함수(node): 재판 공백 문구, 대표 사진 순서

## 11. 완료 기준
0단계: 로컬 완료. **Actions 열 채우기 남음** (spike.yml 실행 → report 갱신)
1단계: Pages에서 v2와 같은 화면, 토큰 브라우저에서 추가·수정·삭제·사진 업로드·대표 사진 지정이 커밋으로 남고 1~2분 뒤 방문자 화면에 반영. v2 엑셀 백업을 가져와 데이터가 그대로 옮겨진다
2단계: `pytest -q` 통과. `--bootstrap`으로 카탈로그가 쌓이고(걸프라 전체, 건프라 일부) `--dry-run`에서 피드·디스코드 출력. Actions 수동 실행이 커밋을 남긴다
3단계: 조이하비 글이 피드에 들어가고 일부가 카탈로그에 매칭, `kr` 이력 누적. 과거 글 채우기 범위가 `meta.since`에 기록
4단계: 사이트에서 카탈로그 검색·연결(URL 붙여넣기 포함), 공식 사진(안정 URL)·자리표시, 재판 공백 표시·정렬, 신제품·입고 탭. 데스크톱·400px, 라이트·다크
5단계: 디스코드 실제 알림 1건 (사용자 요청 시), 다음 날 예약 실행 확인

## 12. 진행 순서
0. ~~검증~~ 로컬 완료 → **spike.yml을 Actions에서 실행해 report의 Actions 열 채우기**. 여기서 해외 IP 차단이 나오면 9장 마지막 항목을 사용자와 정한다
1. 이전 — `docs/`로 v2 옮기기, 소유자 토큰·GitHub API 저장, 사진 파일·대표 사진, v2 데이터 가져오기
2. 카탈로그·피드 — 호비 일정·상세·브랜드, 등급·line 사전(사용자 확인), 번역, 피드, 디스코드(dry-run), crawl.yml
   - **상태: 코드·테스트·로컬 실제 실행(`--bootstrap --from 2025-10`) 완료. 남은 것: 브랜드 키 분류표 사용자 확인, 번역 샘플(API 키 필요), Actions 첫 수동 실행(`bootstrap`)과 `meta.crawl.backlog`가 0이 될 때까지의 반복**
3. 국내 입고 — 조이하비 수집·과거 글 채우기·매칭·`kr` 이력
4. 사이트 연결 — 카탈로그 검색·연결, 공식 사진 갤러리·자리표시, 재판 공백, 신제품·입고 탭, 리뷰 링크
5. 마무리 — 실제 알림 1회(사용자 요청 시), README, 이전 아티팩트 정리 여부 확인
