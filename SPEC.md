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
│  │  ├─ kr-arrivals.json       # [자동] 조이하비 원본 행 + 글 상태 + BD 코드 ↔ catalogId (4장)
│  │  ├─ series-ko.json         # [자동] seriesKey → 한국어 시리즈 사전 (4장, 4단계)
│  │  └─ meta.json              # [자동]
│  └─ photos/<kitId>/<photoId>.webp, <photoId>_t.webp   # [사이트] 내 사진
├─ crawler/
│  ├─ config.py                 # URL, 브랜드 키 → line 사전, 등급 키 매핑, 개수 제한, 알림 규칙, 모델명
│  ├─ http.py                   # spike/common.py의 RateLimiter·robots 게이트·로그를 정리해 옮김
│  ├─ sources/
│  │  ├─ hobby_schedule.py      # 월별 일정 (일반·ホビーオンライン·ガンダムベース 카드)
│  │  ├─ hobby_item.py          # 상품 상세
│  │  ├─ hobby_brand.py         # 브랜드 목록 페이지 (걸프라 4개 브랜드 열거)
│  │  └─ joyhobby.py            # 공지 게시판 목록·글 본문 파서, 판매예정일 (EUC-KR)
│  ├─ catalog.py                # 병합·분류·밀린 상품 선택·저장
│  ├─ match.py                  # 조이하비 상품명 ↔ 카탈로그 매칭 (rapidfuzz)
│  ├─ kr.py                     # kr-arrivals 상태, 연결(codeMap)·재매칭, 카탈로그 kr·nameKo 교체, 조이하비 피드 항목
│  ├─ translate.py  series.py  feed.py  discord.py
│  ├─ mine.py                   # collection.json 읽기 전용 도우미 (연결된 catalogId·보유/위시 — 상세 받기·디스코드 내 프라 우선)
│  ├─ pipeline.py               # 실행 순서(일정 → 브랜드 → 상세 → 조이하비 → 번역 → 피드 → 쓰기 → 디스코드). main.py는 인자 처리만
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
- `kr`: 국내 입고 이력. **쌓기만 하고 지우지 않는다.** 같은 (post, code)는 한 번만. (예외: `KR_CODE_OVERRIDES`로 사람이 "연결 금지"한 코드의 항목만 그 상품에서 뺀다 — 틀린 연결의 교정)
  - `date` *(3단계 정의)*: **제목의 판매예정일**(`10/3(토) 판매예정…`의 `M/D`). 연도는 글 날짜 기준 전년·올해·다음 해 중 가장 가까운 날로 정한다(12월 글의 1월 판매는 다음 해). 날짜를 못 뽑거나 뽑은 날짜가 글 날짜와 60일(`KR_SALE_DATE_MAX_DIFF_DAYS`)보다 멀면 **글 날짜**를 쓴다. 글 날짜는 `kr-arrivals.json`의 `postDate`에 따로 있다
  - `type`: 카탈로그 일본 발매일보다 `KR_RESTOCK_AFTER_DAYS`(60)일 이상 뒤면 `restock`, 아니면 `new`. 발매일이 월만 알려져 있으면 그 달 마지막 날을 기준으로 본다. 발매일을 모르면 게시글(제목·소개글)에 "재입고" 문구가 있을 때만 `restock`, 없으면 `new`. **연결되는 시점에 한 번 정해지고 나중에 바뀌지 않는다**
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
- `manual` / `line:"other"` *(4단계, 구현됨)*: 사이트에서 호비사이트 상품 URL을 붙여넣어 `catalogId`만 저장한 상품을 크롤러가 상세로 받을 때, 브랜드 키가 건프라·걸프라면 해당 파일에 정상 등록한다. 제외 브랜드이거나 사전에 없는 브랜드면 `catalog-gunpla.json`에 `line:"other"`, `manual:true`로 등록한다(건프라 필터·피드 필터에 섞이지 않는다). `manual`이면 기존 항목 재분류를 건너뛰고, 제외 목록에 있던 id도 같은 방식으로 되살린다
- `seriesKo` *(4단계)*: 시리즈(`seriesKey`)가 있는 항목에 붙는 한국어 시리즈명(`series`는 호비사이트의 일본어 원문 그대로). 사전(`series-ko.json`)·`config.SERIES_KO_OVERRIDES`로 채우고, 번역 당시의 일본어와 `series`가 달라지면 지운 뒤 다시 번역한다. 사이트는 연결·채우기·검색에 `seriesKo`를 먼저 쓴다
- `manual`·`line:"other"` 항목은 `catalog-gunpla.json`에 들어가지만 신제품 피드·조이하비 매칭·번역 외의 자동 처리에는 섞이지 않는다. 사이트에서 URL을 붙여넣어 `catalogId`만 저장한 상품은 다음 실행의 `hobby_item` 단계가 **먼저**(실행당 `MANUAL_DETAIL_MAX`=20개, 새·밀린 상품 상한과 별개) 상세를 받는다. 404면 `detail-404`로 제외하고, 일시 오류면 저장하지 않고 다음 실행에 다시 시도하며(되살렸던 제외 사유는 원래대로), `pb-`(P-반다이) id는 상세를 요청하지 않아 카탈로그에 있어야만 쓸 수 있다. 결과는 `meta.sources.hobby_item.manual`(`requested`·`added`·`other`·`unsupported`·`failed`)
- `nameKo`: 번역 실패·키 없음이면 `null`. 사이트 검색은 nameKo·nameJa 모두 대상
  - `nameKoSource: "joyhobby"` *(3단계)*: 매칭 점수가 **연결 기준보다 높은 별도 기준**(`MATCH_NAME_SCORE`)을 넘었거나 사람이 연결을 확인(`KR_CODE_OVERRIDES`)한 항목은 `nameKo`를 조이하비 한글명(대괄호 코드·영문 괄호·`(프라모델)`·작품 꼬리 정리, `<등급> <스케일> <이름>` 꼴)으로 바꾸고 이 표식을 붙인다. 바꾸기 전 번역은 `nameKoAi`에 보존한다(번역 전이었으면 `null`). 이후 번역은 이 항목을 건드리지 않는다. 연결 금지(override)가 걸리면 `nameKo`를 `nameKoAi`로 되돌리고 두 필드를 지운다. **이름 교체는 `line`이 `gunpla`인 항목만** — 걸프라(`girl`)는 연결·`kr`·피드는 그대로 하되 `nameKo`는 번역을 유지하고, 이미 바뀐 걸프라 항목은 다음 실행에 `nameKoAi`로 되돌린다(`nameReverted`)

### series-ko.json (크롤러가 씀) *(4단계)*
```json
{"updatedAt":"ISO","items":{"seed-d":{"ja":"機動戦士ガンダムSEED DESTINY","ko":"기동전사 건담 SEED DESTINY"}}}
```
- seriesKey별로 한 번만 번역한 결과. `ja`는 번역 당시의 일본어라서, 호비사이트가 시리즈 이름을 바꾸면 그 시리즈만 다시 번역한다. 바뀐 게 없으면 파일도 `updatedAt`도 그대로 둔다
- 사람이 고치는 표는 `config.SERIES_KO_OVERRIDES`({seriesKey: 한국어}) — 사전·번역보다 우선하고 API를 부르지 않는다. 사이트는 이 파일을 읽지 않는다(카탈로그 항목의 `seriesKo`를 쓴다)

### kr-arrivals.json (크롤러가 씀) *(3단계)*
```json
{"updatedAt":"ISO",
 "posts":{"139506":{"date":"2026-10-02","title":"10/3(토) 판매예정 반다이 제품리스트 안내","state":"done","sale":"2026-10-03","restock":false,"rows":5}},
 "codeMap":{"BD5068558":{"catalogId":"bh-01_4259","method":"fuzzy","score":100.0,"margin":38.5,"nameOk":true,"nameApplied":true,"post":"139506","at":"ISO"}},
 "rows":[{"post":"139506","postDate":"2026-10-02","code":"BD5068558","name":"[RG42] 1/144 … 샤이닝 건담(SHINING GUNDAM) - 기동무투전 G건담(프라모델)","price":38500}]}
```
- `posts`: 후보 글(제목에 `반다이` 또는 `입고`) 상태. `state`: `pending`(아직 본문을 안 읽음) · `done`(BD 행 있음) · `no-bd`(후보였지만 BD 행 없음 = 봤음) · `gone`(404) · `broken`(조이하비 서버 버그로 영구히 못 여는 글, 아래 5장) · `error`(본문이 3번 실패해 포기). `sale`은 제목에서 뽑은 판매예정일(없으면 null), `restock`은 제목·소개글의 "재입고" 문구
- `rows`: **조이하비 원본 행**(글번호·글 날짜·BD 코드·상품명·가격). (post, code)는 한 번만. 연결 여부와 무관하게 쌓는다
- `codeMap`: **한 번 확실히 연결된 BD 코드 ↔ catalogId**. 같은 코드의 다음 글은 이름을 비교하지 않고 코드로 바로 연결한다. `method`는 `fuzzy`(이름 매칭)·`override`(사람이 지정), `score`·`margin`은 연결 당시 값, `nameOk`는 이름 교체 기준을 넘었는지, `nameApplied`는 실제로 `nameKo`를 바꿨는지
- 매 실행마다 **연결 안 된 코드를 현재 카탈로그로 다시 매칭**한다. 건프라 상세가 나중에 채워지면 과거 입고도 그때 카탈로그 `kr`에 들어간다
- `config.KR_CODE_OVERRIDES`(사람이 고치는 표): `{BD코드: catalogId}`는 강제 연결, `{BD코드: None}`은 연결 금지(굳은 연결을 풀고 `nameKo` 되돌리고 그 코드의 `kr` 제거)

### feed.json (크롤러가 씀)
```json
{"updatedAt":"ISO","items":[{
  "id":"jh-139459-BD5068846","type":"new|pb-new|kr-restock|kr-new",
  "date":"2026-10|2026-09-29","added":"ISO","catalogId":"bh-01_4257|null",
  "title":"원문 제목","titleKo":"...","url":"https://...","image":"안정 URL|null","source":"bandai-hobby|joyhobby"}]}
```
- id: 호비 신제품 `bh-new-<번호>`(예 `bh-new-01_7249`), P-반다이 `pb-new-<번호>`(예 `pb-new-item-1000249921`), 조이하비 `jh-<글번호>-<상품코드>`
- 호비 신제품 항목은 **이번 실행에서 처음 발견**됐고, 판정이 끝나 line이 gunpla/girl이며, 발매월이 이번 달 이후인 것만 만든다(지난 달 발매분을 최초 채우기로 훑을 때는 만들지 않는다). P-반다이 항목의 `url`은 P-반다이 링크(요청하지 않는다), `image`는 안정 URL이 있을 때만 — P-반다이 카드는 항상 `null`
- 조이하비 항목 *(3단계)*: type `kr-restock`/`kr-new`, id `jh-<글번호>-<상품코드>`, `date`는 `kr.date`(판매예정일), `url`은 **조이하비 글**, `image`는 연결된 카탈로그의 안정 URL뿐(조이하비 이미지는 쓰지 않는다). **연결 안 된 행도 피드에 넣는다**(type은 글의 "재입고" 문구로 정하고 `catalogId`·`image`는 null). 글 날짜가 최근 `KR_FEED_DAYS`(30)일 이내인 행만 만든다 — 과거 글은 `kr` 이력·원본 행에만 들어간다
- `added`: 처음 발견한 시각. 바꾸지 않는다. `titleKo`·`image`는 나중에 번역·상세로 채워지면 빈 칸만 보충한다. 조이하비 항목은 나중에 카탈로그와 연결되면 `catalogId`·`image`를 채우고 **`type`만 60일 규칙으로 고칠 수 있다**(`added`는 그대로)
- 보관: `added` 내림차순 최대 1000개

### meta.json
```json
{"updatedAt":"ISO","since":"조이하비 기록 시작일 YYYY-MM-DD(없으면 수집 시작일)",
 "sources":{"hobby_schedule":{"ok":true,"at":"ISO","items":21,"error":null},"hobby_brand":{...},"hobby_item":{...},
            "translate":{"ok":true,"at":"ISO","items":50,"error":null,"pending":0,"skipped":null,"model":"...","kanaRetried":0,"kanaRejected":0},"joyhobby":{...}},
 "crawl":{"scheduleFrom":"2015-01","girlBrandsDone":["30ms"],"backlog":120,"joyNext":21,"joyDone":true,"joyOldest":"2024-01-04","counts":{"gunpla":0,"girl":0,"pending":0,"excluded":0},
           "lastFixups":{"toExcluded":0,"lineChanged":0,"nameKoReplaced":0,"feedTitleKoReplaced":0}},
 "stats":{"requests":0,"byKind":{},"failures":0,"elapsedSec":0,"minGapSec":1.2},
 "unknownBrandKeys":[]}
```
- `sources`는 단계별로 나눈다(`hobby`를 `hobby_schedule`·`hobby_brand`·`hobby_item`으로). 일부 항목만 실패하면 `ok:false`와 실패 목록이 `error`에 들어간다. `--only`로 돌리지 않은 소스는 이전 값을 유지한다
- `crawl.lastFixups`: 이번 실행 시작에 적용한 기존 데이터 보정 결과(재분류로 제외된 수·line 변경 수·nameKo/피드 titleKo 치환 수). 매 실행 덮어쓴다
- `crawl`: 최초 채우기 커서(5장) — `scheduleFrom`은 "이 달부터 현재까지 일정을 다 훑었다", `girlBrandsDone`은 전체 쪽수를 끝낸 걸프라 브랜드, `backlog`는 상세를 기다리는 항목 수(0이 되면 채우기 완료)
- `crawl.joyNext`·`joyDone`·`joyOldest` *(3단계)*: 조이하비 과거 글 커서 — `joyNext`는 1쪽부터 끊김 없이 훑은 다음 쪽, `joyDone`은 게시판 끝(마지막 쪽)까지 훑었다는 뜻, `joyOldest`는 그렇게 훑은 범위의 가장 오래된 글 날짜. `meta.sources.joyhobby`에는 글·행·코드 수, 연결 수, 이번 실행의 통계가 들어간다
- `since` *(3단계 정의)*: 조이하비를 훑은 범위의 가장 오래된 글 날짜(`joyOldest`). "이 날짜 이후의 입고 기록은 본다"는 뜻이라 가장 오래된 **반다이** 글이 아니라 훑은 쪽의 가장 오래된 글 날짜를 쓴다. 조이하비를 아직 훑지 않았으면 수집 시작일
- 사이트 하단에 "마지막 수집"과 실패한 소스, 재판 공백 문구에 `since`를 쓴다

## 5. 수집 소스 (0단계에서 확인한 구조)
| 소스 | URL | 파싱 | 주기·양 |
|---|---|---|---|
| 호비 월별 일정 | `https://bandai-hobby.net/schedule/index.php?saledate=YYYYMM` | 카드 `a.p-card` (`.p-card__tit`, `.p-card__price`, `.p-card_date`). 묶음 ①일반 `/item/01_N/` ②ホビーオンライン `.p-card__tag.-online` → `p-bandai.jp/item/item-N`, 월 단위 ③ガンダムベース | 매일: 이번 달 ~ +3개월. 과거 월은 최초 채우기(`--bootstrap`) 때 `2015-01`까지 한 번만 |
| 호비 상품 상세 | `https://bandai-hobby.net/item/01_N/` | `h1.p-heading__h1-product`, `dl.pg-products__detail dt/dd`, `a.pg-products__pblink`, `li.p-card__link a.p-card__flat`(브랜드·작품 키), 갤러리 이미지 | 상세가 없는 `bh-` 항목만. 실행당 **새 상품 최대 40 + 밀린 상품 최대 150** |
| 호비 브랜드 목록 | `https://bandai-hobby.net/brand/<key>/?p=N` (`a.c-archives__pagination-list-item-link`) | 카드 `a.p-card`(일정 카드와 같은 구조, 슬라이드 `a.p-slide__link`는 제외) | 걸프라 4개 브랜드: 매일 1쪽, 최초 채우기 때 전체 쪽수 |
| 조이하비 공지 | `https://www.joyhobby.co.kr/mall/board_list.asp?siteid=joyhobby&BoardCode=notice&nowPage=N` → 글 `board_view.asp?SiteID=joyhobby&BoardCode=notice&B_iID=<번호>` | 후보 글: 제목에 `반다이` 또는 `입고`. 본문 `상품코드 / 상품명 / 가격` 3줄 반복, 반다이 코드 `BD#######` 행이 있어야 기록(없으면 "봤음"). **EUC-KR 인코딩.** 고정 공지 7개가 쪽마다 반복 | 매일 목록 1~2쪽, 처음 보는 글만 |

- 호출: `requests` + `beautifulsoup4`. Actions에서 결과가 로컬과 다르면(차단·리다이렉트) 그 소스만 Playwright로 바꾼다
- 모든 요청: robots.txt 준수, 요청 간 1.2초 이상, timeout 20초, 브라우저 형태 User-Agent, `requests.log`와 같은 형식으로 로그
- 소스 하나가 실패해도 계속하고 `meta.json`에 기록
- **최초 채우기**(`--bootstrap`) *(2단계에서 방식 변경: 카드 먼저, 상세는 나눠서)*
  1. **일정 카드만으로 먼저 카탈로그 항목을 만든다**(이름·가격·발매일·상품 번호·채널). 상세가 없어도 검색되도록 제목 앞 토큰으로 line·등급·스케일을 임시 판정한다(4장 `detailAt`이 null인 항목)
  2. 건프라는 일정을 `2015-01`(`--from`으로 변경)부터 이번 달까지 **최신 달부터 거슬러** 훑는다. 한 번에 끝나는 양(약 140개월)이고, 중간에 실패하면 거기서 멈추고 `meta.crawl.scheduleFrom` 커서를 남겨 다음 실행이 이어서 한다
  3. 걸프라 4개 브랜드는 브랜드 목록을 전체 쪽수로 훑는다(브랜드 키가 목록에서 이미 알려져 line·등급이 바로 확정된다). 끝난 브랜드는 `meta.crawl.girlBrandsDone`에 기록
  4. **상세는 실행마다 새 상품 최대 40 + 밀린 상품 최대 150**만 받는다(`--max-new`, `--max-backlog`; 합계 400 초과 불가). 밀린 상품은 임시 판정이 된 것 먼저, 발매일 최신순이다. 새 상품이 40개를 넘으면 남은 것도 밀린 슬롯에서 같은 순서로 경쟁한다(그래서 첫 실행도 190개를 받는다). 상세가 오면 브랜드 키로 line이 확정되고, 대상이 아니면 `catalog-pending.json`의 제외 목록으로 간다. `meta.crawl.backlog`가 0이 되면 채우기 끝 — 하루 1회 예약 실행만으로는 며칠 걸리므로 수동 실행(`workflow_dispatch`)을 여러 번 돌려 앞당긴다
  5. 최초 채우기 중에는 디스코드 알림이 없다. 그 이전 상품(2015-01 이전)은 사용자가 연결하려 할 때 상세 URL을 붙여넣어 추가할 수 있게 한다(6장)
- **조이하비 특이점 (3단계 확인, 2026-10)**
  - **EUC-KR**: 응답 헤더가 `text/html; Charset=euc-kr`이다. `http.decode_body`가 Content-Type → `<meta charset>` → UTF-8 순으로 문자 집합을 정한다(`euc-kr`은 상위 집합 `cp949`로 읽음). 호비사이트(UTF-8)는 그대로. fixture는 Playwright 저장본이 아니라 **응답 원본 바이트**(`tests/fixtures/joyhobby-raw-*.html`)
  - **고정 공지 7개(`Notice=true`)가 모든 쪽 맨 위에 반복**된다 → 버리고 일반 행만 쓴다. 쪽당 일반 글은 20개
  - **마지막 쪽은 20쪽**(약 396개 글, 가장 오래된 글 2024-01-04). **21쪽부터는 마지막 행만 되풀이해서 돌려준다**(오류가 아니다) → 마지막 쪽(20개 미만) 또는 새 글이 없는 쪽에서 멈춘다. 반다이 글은 2024-03-30부터 있다
  - 제목 형식이 제각각(`판매예정 반다이 제품리스트`·`반다이 입고리스트`·`반다이 입고예정 리스트`·`반다이 1차입고 안내`·`[긴급공지] …`)이라 제목으로 확정하지 않고, 후보(`반다이`|`입고`)의 본문에 BD 행이 있는지로 확정한다. 후보 제목은 쪽당 약 14개
  - 가격 표기는 `22000원`(쉼표 없음)과 `19,800원`이 섞여 있다
  - **조회수가 32767(smallint)을 넘은 글은 사이트 자체 버그로 HTTP 500**(`Microsoft SQL Server … 데이터 형식 smallint에 산술 오버플로 오류`)이 나온다. 누가 열어도 같다(2026-10 기준 6개 — 반다이 제품리스트 1개 포함: 글 139281, 9/5 판매분). 이 응답을 보면 그 글을 `broken`으로 기록하고 **다시 열지 않으며**, 연속 실패(차단 판정)로 세지 않고 다음 글로 간다. 소스 실패(`ok:false`)로도 치지 않는다. 그 글에만 있던 BD 행은 얻을 수 없다
- **조이하비 과거 글 채우기** *(3단계)*: `--bootstrap`(수동 실행 `joy_backfill`)에서 매 실행의 1~2쪽(새 글)에 더해 `meta.crawl.joyNext`부터 `--joy-pages`(기본 `JOY_BACKFILL_PAGES`=25)쪽을 이어서 훑는다. 게시판이 20쪽이라 한 번에 끝나고, 끝나면 `joyDone`. 후보 글을 새로 발견하는 즉시 pending으로 기록하고 본문은 최신 글부터 읽는다(실행당 `JOY_POSTS_PER_RUN_MAX`=300). 과거 글은 `kr` 이력과 원본 행에만 넣고 피드에는 글 날짜가 `KR_FEED_DAYS`(30)일 이내인 것만 넣는다. `bootstrap` 중에는 디스코드 알림이 없다

### 매칭 (`match.py`) — 조이하비 상품명 ↔ 카탈로그
- 상품명 형식: `[등급코드] 스케일 모델번호 한글명(영문명) - 작품(프라모델)` (0단계 표본 141건, `tests/fixtures/joyhobby-post-*.html`)
- 대괄호 코드 → 등급: `HGUC/HGAW/HGWFM/HGCE…`→HG, `RG`, `MG`, `MGSD`, `30MM_*`→30MM, `[피규어라이즈스탠다드]`→Figure-rise Standard 등 (사전은 config)
- 비교 키: 등급 + 스케일로 후보를 좁히고(등급을 모르면 매칭하지 않는다. `30MM_*`·`원피스` 등은 대상 아님) 한글명 ↔ `nameKo`를 rapidfuzz로 비교한다. **카탈로그에는 영문명이 없어서** 영문명(괄호 안) 대신 **모델번호 토큰**(`MS-09F`, `GF13-017NJ`, `ASW-G-66` …)을 쓴다 — 유사도에서는 모델번호를 빼고, 양쪽에 있으면 한쪽이 다른 쪽을 포함할 때 가산(`MATCH_MODEL_BONUS`), **서로 포함하지 않으면 연결하지 않는다**(`MSN-04` ≠ `MSN-04FF`, `GNR-010` ≠ `GNR-010/XN`). ` - 작품` 꼬리는 비교·이름에서 항상 뗀다(아래 "작품 꼬리"). 조이하비 이름에도 `NAME_KO_REPLACEMENTS`(앰플리파이드 → Amplified)를 적용한다
- **보호 규칙(guard)**: 점수가 높아도 다른 상품일 가능성이 큰 차이는 후보에서 뺀다. ① 영문·숫자 덩어리가 다름(`K9`·`F91`·`II`/`III`·`EW`·`Ver.Ka` 등 숫자가 든 것·로마숫자·3글자 이하) ② 한쪽에만 있는 낱말이나 서로 다른 낱말 — 정확히 같은 낱말이 없으면 4글자 이상이고 `MATCH_TOKEN_RATIO`(80)% 이상 비슷한 낱말만 철자 변형으로 인정(`델타`↔`제타`, `바우`↔`리바우`, `에어마스터`↔`에어마스터 버스트`, `큐리오스`↔`헬리오스` 거절). 띄어쓰기·구두점만 다르면 통과. 첫 실행에서 점수 80~92로 잘못 연결됐던 사례들에서 나온 규칙이다. **알려진 재현율 손실**: 3글자 낱말·철자 변형이 큰 쌍(`르브리스`↔`루브리스`, `발바토스`↔`바르바토스`)과 `…기` 같은 접미 차이는 맞아도 연결되지 않는다 → `KR_CODE_OVERRIDES`로 지정
- **작품 꼬리**: 이름 끝의 ` - <작품명>`(+ `(프라모델)`)은 영문 괄호 유무·반복 횟수와 관계없이 뗀다(마지막 ` - ` 뒤 하나). **예외: 꼬리에 변형 표시어가 낱말로 들어 있으면 떼지 않는다**(`config.JOY_VARIANT_MARKERS`: 전용기·커스텀·사양·타입/Type·컬러·Ver/Version·버전·장비·유닛·에디션/Edition). `큐베레이 마크2 - 플 전용기`는 변형 이름이라, 떼면 기본형으로 잘못 연결될 수 있어서다. 낱말 경계로 찾으므로 작품명 `아이돌마스터 샤이니 컬러즈`는 걸리지 않고(`컬러` ≠ `컬러즈`), 표시어가 있어도 작품명인 꼬리는 `JOY_TAIL_EXEMPT`에 넣으면 뗀다. 표시어 꼬리를 남긴 이름은 영문·낱말이 기본형과 달라 보호 규칙이 막는다. 등급 코드 뒤의 `[드래곤볼]` 같은 말머리도 뗀다. 그리스 문자는 한글 읽기로 맞춘다(`ν건담` = `뉴건담`). 알려진 재현율 손실: 영문 이름 중복 꼬리(`- SAZABI metallic coating Ver`)가 표시어 `Ver` 때문에 남아 그 상품은 연결되지 않는다
- 연결: 보호 규칙을 통과한 1등이 `MATCH_LINK_SCORE`(80) 이상이고 통과한 2등과 `MATCH_MARGIN`(10) 이상 벌어질 때만. 아니면 연결하지 않는다(`low-score`·`ambiguous`·`model-conflict`·`guard`). 연결 안 된 항목도 피드에는 넣는다
- 이름 교체(`nameKo`)는 `line`이 gunpla인 항목에서 더 엄격한 `MATCH_NAME_SCORE`(92) 이상일 때만(4장 `nameKoSource`). 임계값은 모두 `config.py`
- 연결된 코드는 `kr-arrivals.json`의 `codeMap`에 남아 다음 글부터 코드로 바로 연결된다. 틀린 연결은 `KR_CODE_OVERRIDES`로 고친다

### 번역 (`translate.py`)
- 새 카탈로그 항목만, 50개씩 Claude API. 한국 정식 명칭을 따르게 하고 JSON으로 받는다. 조이하비에서 매칭된 한국어 이름이 있으면 그걸 우선 쓴다
- 모델명은 `config.CLAUDE_MODEL` (daily-tech-digest와 같은 방식). `ANTHROPIC_API_KEY` 없으면 건너뜀
- **가나 검사**: 번역(`ko`)에 히라가나·가타카나가 남아 있으면(예: `[カラーC]`) **그 항목만 한 번** 다시 요청한다(앞선 번역을 `prev_ko`로 알려 줌). 그래도 남으면 `nameKo`를 비워 두고 다음 실행에서 다시 시도한다. 중점 `・`은 가나로 보지 않는다. 재요청 수와 비운 수는 `meta.sources.translate`의 `kanaRetried`·`kanaRejected`
- **용어집**: 자주 나오는 고유명사·표기는 `config.TRANSLATE_GLOSSARY`(일본어 → 한국어 사전)에 두고 시스템 프롬프트에 그대로 넣는다. 틀린 번역이 보이면 한 줄 추가하면 되고, 값에 가나를 쓰지 않는다(테스트가 확인)
- **영문 그대로 두는 말**: 용어집 값이 영문이면 영문 그대로 쓴다(예: `アンプリファイド → Amplified`). 시스템 프롬프트에도 `Amplified`는 번역·음역하지 말라는 규칙이 있다
- **nameKo 후처리**: `config.NAME_KO_REPLACEMENTS`(예: `앰플리파이드 → Amplified`)를 매 실행 시작과 번역 직후에 `nameKo`(와 피드의 `titleKo`)에 부분 문자열 치환으로 적용한다. 용어집을 고친 뒤 이미 저장된 번역을 맞추는 용도이고, 해당 글자 외에는 `updated` 포함 아무것도 바꾸지 않는다
- 수동 확인: `python -m crawler.translate --sample 20` — 실제 파이프라인과 같은 경로(가나 재요청 포함)로 fixture 제목 20개를 한 번 번역해 출력. 테스트는 실제 Claude를 호출하지 않는다(클라이언트 생성·`.env` 읽기를 `conftest`가 막음)
- **시리즈 번역** *(4단계, `series.py`)*: 고유 `seriesKey`(현재 74개)만 Claude API로 한 번 번역한다(`translate` 단계 안에서, 새 시리즈가 없으면 호출하지 않음). 한국 정식 제목을 따르고 영문·숫자 표기(`SEED DESTINY`, `Re:RISE`)는 그대로 두며, 같은 용어집·가나 검사(남으면 그 항목만 한 번 재요청, 그래도 남으면 저장하지 않고 다음 실행에 재시도)를 쓴다. 키가 없거나 dry-run이어도 사전에 있는 시리즈는 항상 항목에 채운다. 수동 확인: `python -m crawler.series --sample 10`(번역해 출력만, 파일은 쓰지 않음)

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
- 엑셀 백업·가져오기에 `catalogId` 열(`반다이 제품 ID`) 추가. 열이 없는 예전 백업도 그대로 가져오고, 형식이 맞지 않는 값은 버린다. 사진은 백업에 넣지 않는다
- **자동 연결 후보** *(4단계 구현)*: 설정 → "자동 연결 후보 보기". 아직 연결 안 된 프라 중 정규화한 이름(등급·스케일 머리말 무시)·등급·스케일이 모두 같은 카탈로그 제품이 **정확히 1개**일 때만 제안한다(등급 `기타`·후보 2개 이상은 제외, 카탈로그에 스케일이 없으면 `논스케일`끼리). 체크한 것만 한 커밋으로 연결하고 빈 칸(시리즈 등)만 채운다. 같은 화면에서 "시리즈를 한국어로 바꾸기": 연결된 프라 중 시리즈 칸이 카탈로그의 일본어 `series`와 **정확히 같은** 것만 제안한다(직접 적은 값은 건드리지 않음)
- **리뷰 찾아보기** *(4단계 구현)*: 상세에 `<등급> <이름> 리뷰` 유튜브·네이버 블로그 검색 링크(새 탭, noopener)

## 7. 디스코드 알림
- 매 실행 1회, 이번에 새로 들어온 피드 항목을 묶어 보낸다
- 순서: ① 내 보유·위시와 연결된 국내 입고 (따로 맨 앞, 강조 색) ② 국내 재입고·신규 ③ P-반다이 한정 신규 ④ 신제품 발매 일정
  - **①(내 프라 우선) 구현됨(4단계)**: 크롤러가 `collection.json`을 **읽기만** 해서(`mine.py`) 보유·위시의 `catalogId`와 같은 **국내 입고(kr-restock·kr-new)**를 맨 앞에 놓고 `[내 프라]` 제목·`내 프라(보유·위시)` 설명·강조 색(`config.MINE_COLOR`)으로 보낸다. 첫 메시지에 `내 프라가 국내에 입고됐어요! (N건)`을 붙이고, 한도를 넘어도 내 프라가 먼저 살아남는다. 신제품·P-반다이는 내 프라여도 우선 대상이 아니다. 나머지는 ②~④ 순서(`config.FEED_TYPES` 우선순위)
- 조이하비 항목은 **글 날짜가 최근 `KR_NOTIFY_DAYS`(3)일 이내**인 것만 알린다. 피드 노출 기간(`KR_FEED_DAYS`, 30일)과 별개다 — 배포 직후 예약 실행이 최근 한 달 글을 한꺼번에 알리지 않게 한다
- 임베드: 제목 링크, 종류, 시기, 안정 이미지가 있으면 썸네일. 메시지당 10개, 실행당 3메시지, 넘치면 "외 N건 — 사이트에서 보기"
- 최초 채우기(`--bootstrap`) 중이거나 이전 feed가 비었거나 이전 카탈로그가 비어 있었으면(첫 실행) 보내지 않는다. `--dry-run`은 이 규칙으로 건너뛰는 경우에도 형식 확인용으로 보낼 내용을 출력한다
- `DISCORD_WEBHOOK_URL`이 없거나 `--dry-run`이면 콘솔 출력만. 발송 실패는 경고만

## 8. 실행 옵션
- `python main.py` / `--dry-run` / `--only hobby,joyhobby` / `--bootstrap`
  - `--only`: `hobby`(= `hobby_schedule`+`hobby_brand`+`hobby_item`), `joyhobby`, `translate`
  - `--bootstrap [--from YYYY-MM]`: 최초 채우기(5장). `--from`은 확인용으로 범위를 줄일 때(기본 `2015-01`)
  - `--max-new N` / `--max-backlog N`: 실행당 상세 상한(기본 40 / 150). `--max-details`는 폐지
  - `--joy-pages N`: `--bootstrap` 때 조이하비 과거 목록을 훑을 쪽 수(기본 25). 조이하비 과거 글만 채우려면 `--bootstrap --only joyhobby`
  - `--data-dir DIR`: `docs/data` 대신 다른 폴더에 읽고 쓴다(로컬에서 부분 채우기를 저장소와 섞지 않으려고)
  - `--no-discord`: 발송만 끈다. `--dry-run`은 파일은 쓰고 디스코드는 보내지 않으며 **보낼 내용을 항상 출력**하고, API 비용이 드는 번역은 `--only translate`로 명시할 때만 돌린다
  - `--discord-test` *(5단계)*: 수집 없이 테스트 알림 **1메시지**만 보낸다. `feed.json` 최근 3개(내 프라 연결 항목이 있으면 그중 1개 포함)를 실제 알림과 같은 형식으로 묶고 맨 앞에 `[테스트] 프라 격납고 알림 확인용`을 붙인다. `docs/data`는 바꾸지 않고(커밋도 없음) 웹훅은 `DISCORD_WEBHOOK_URL`(Actions Secret)만 쓴다 — 없으면 "웹훅 없음"만 출력하고 성공 종료, 발송 실패는 종료 코드 1. `--dry-run`을 같이 주면 내용만 출력. 수집 옵션과는 함께 쓸 수 없다
- 로컬 미리보기: `python -m http.server -d docs 8000`

## 9. GitHub Actions (`crawl.yml`)
- 트리거: `schedule: cron "10 22 * * *"` (KST 07:10), `workflow_dispatch`(입력: `bootstrap`, `max_backlog`(기본 150), `joy_backfill`(조이하비 과거 글만: `--bootstrap --only joyhobby`), `joy_pages`(기본 25), `discord_test`(기본 꺼짐: 수집·커밋 없이 테스트 알림 1건만 — 8장 `--discord-test`))
- `concurrency: { group: crawl }`, 권한 `contents: write`
- 단계: checkout → Python 3.12 + pip 캐시 → `python main.py` → 요청 로그 artifact(7일) → `git pull --rebase --autostash` → **허용 목록 7개만 add**(`catalog-gunpla/girl/pending.json`, `feed.json`, `kr-arrivals.json`, `series-ko.json`, `meta.json`; 그 밖의 경로가 staged면 실패해 `collection.json`·`photos/`를 지킨다) → 변경이 있으면 커밋(`data: crawl YYYY-MM-DD`) → push(충돌 시 `pull --rebase` 후 최대 3회). `timeout-minutes: 45`
- 조이하비 과거 글 채우기: 수동 실행에서 `joy_backfill`을 켠다(한 번에 끝남, 약 320요청 ≈ 6.5분 — 후보 글의 2/3가 BD 행이 없는 글이라 대부분이 "봤음"용 요청이다). 호비사이트 채우기와 독립이다
- 최초 채우기: 수동 실행에서 `bootstrap`을 켜고, `meta.crawl.backlog`가 0이 될 때까지 몇 번 반복한다(실행당 상세 최대 190개 + 일정·브랜드 수백 요청, 요청 간 1.2초 → 한 번에 10분 안팎)
- (Playwright가 필요해진 소스가 있을 때만) Chromium 설치 단계 추가
- Secrets: `DISCORD_WEBHOOK_URL`, `ANTHROPIC_API_KEY`
- Pages: Deploy from a branch → `main` / `/docs`
- **Actions에서 조이하비나 호비사이트가 해외 IP로 막히면**: 크롤러를 사용자 PC에서 Windows 작업 스케줄러로 돌리고 결과를 push하는 방식으로 바꾼다(사용자 결정)

## 10. 테스트 (네트워크 없이)
- fixture: `tests/fixtures/`의 0단계 저장본 (호비 일정·상세, 조이하비 목록·글)
- 파서: 일정 카드 3묶음 구분, 상세 필드, 브랜드 키 → 등급·line, 스케일 정규식, **서명 URL 제외**
- 조이하비: EUC-KR 디코딩(응답 원본 바이트 fixture), 후보 제목 규칙, 고정 공지 제외, 마지막 쪽, 3줄 파싱(쉼표 없는 가격·깨진 행·중복), BD 코드만, 판매예정일 연도 추정(12월→1월, 60일 초과)
- 매칭: 0단계 표본 상품명(`[RG42] 1/144 … 샤이닝 건담(SHINING GUNDAM) …` 등)과 카탈로그 샘플, 애매한 경우 미연결
- `kr.type` 판정(60일 규칙 경계, 월만 아는 발매일, 발매일 없음), 재매칭으로 나중에 연결, codeMap 재사용, (post, code) 중복, nameKo 교체·`nameKoAi` 보존·override 되돌리기, 피드 30일·알림 3일
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
   - **상태 (2026-10-08): 코드·테스트(299개)·로컬 실제 실행 완료.** 로컬 실행 결과는 커밋하지 않았다(데이터는 Actions만 쓴다) — 과거 글 채우기는 push 후 수동 실행 `joy_backfill`(`joy_pages` 25). 로컬 첫 실행 `--bootstrap --dry-run --only joyhobby`(319요청, 6.5분): 후보 글 298개 중 BD 행 있음 99·없음 193·사이트 버그 6, 행 2,382, 코드 1,260개 중 **161개 연결**(등급을 아는 919개 중 17.5% — 카탈로그 상세 backlog 2,144가 줄면 매 실행 재매칭으로 오른다), `kr` 329건, `nameKo` 교체 157건. 남은 것: 연결 결과 사용자 확인(`crawler/out/joy-links.txt`), 커밋·push 후 Actions 수동 실행(`joy_backfill`)과 다음 날 예약 실행 확인. "내 프라 우선" 알림은 4단계
4. 사이트 연결 — 카탈로그 검색·연결, 공식 사진 갤러리·자리표시, 재판 공백, 신제품·입고 탭, 리뷰 링크
   - **상태 (2026-10-08): 코드·테스트 완료.** 4a 카탈로그 로딩·검색·연결·공식 사진, 4b 재판 공백·정렬, 4c 신제품·입고 탭, 4d 자동 연결·시리즈 한국어·리뷰 링크·엑셀 `catalogId`·크롤러(내 프라 우선 알림, 미등록 `catalogId` 상세, `seriesKo`). 남은 것: push 후 Actions 수동 실행으로 `seriesKo` 번역(API 키 필요)·미등록 `catalogId` 상세 확인, 사이트에서 실제 연결·알림 확인
   - 사이트 로딩: `collection.json`만으로 먼저 그리고, 연결된 프라가 있을 때(또는 찾기·신제품 탭을 열 때) `meta.json` → `catalog-gunpla/girl.json?v=<meta.updatedAt>`을 뒤에서 받는다. `kr-arrivals`·`pending`은 읽지 않는다(pending은 4d에서 URL 붙여넣기 확인용으로만 검토)
5. 마무리 — 실제 알림 1회(사용자 요청 시), README, 이전 아티팩트 정리 여부 확인
   - **상태 (2026-10-08)**: 5a 디스코드 테스트 발송(`--discord-test`, 수동 실행 입력 `discord_test`) **코드·테스트 완료**, 5b README **완료**. 남은 것: push 후 Actions 수동 실행(`discord_test` 켜기)으로 실제 알림 1건 확인(사용자가 요청할 때만), 다음 날 예약 실행 확인(11장 5단계), 이전 Claude 아티팩트 정리 여부 확인
