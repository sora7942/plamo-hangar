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
│  │  ├─ feed.json              # [자동]
│  │  └─ meta.json              # [자동]
│  └─ photos/<kitId>/<photoId>.webp, <photoId>_t.webp   # [사이트] 내 사진
├─ crawler/
│  ├─ config.py                 # URL, 브랜드 키 → line 사전, 등급 키 매핑, 개수 제한, 알림 규칙, 모델명
│  ├─ http.py                   # spike/common.py의 RateLimiter·robots 게이트·로그를 정리해 옮김
│  ├─ sources/
│  │  ├─ hobby_schedule.py      # 월별 일정 (일반·ホビーオンライン·ガンダムベース 카드)
│  │  ├─ hobby_item.py          # 상품 상세
│  │  ├─ hobby_brand.py         # 브랜드 목록 페이지 (최초 채우기용)
│  │  └─ joyhobby.py            # 공지 게시판 반다이 제품리스트
│  ├─ catalog.py  match.py  translate.py  feed.py  discord.py
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
  "firstSeen":"ISO","updated":"ISO"}]}
```
- `id`: `bh-` + 호비사이트 상품 번호(`01_N`). ホビーオンライン 카드처럼 호비 상세가 없는 상품은 `pb-` + P-반다이 번호(`item-N`)
- `release`: 일본 최초 발매. 날짜를 모르면 `month`만
- `kr`: 국내 입고 이력. **쌓기만 하고 지우지 않는다.** 같은 (post, code)는 한 번만
  - `type`: 카탈로그 발매일보다 60일 이상 뒤면 `restock`, 아니면 `new` (발매일을 모르면 게시글에 "재입고" 문구가 있을 때만 `restock`, 없으면 `new`)
- `images`: **안정 URL만** (호스트가 `bandai-a.akamaihd.net`, `bandai-hobby.net`). 서명 URL(`?Expires=`)은 저장하지 않는다. 사이트 갤러리 순서 그대로
- `grade`: 브랜드 키 → 등급 매핑(`hg`/`hg-c`/`pb_hg`→HG, `rg`/`rg-c`→RG …)은 `config.py`. 없으면 상품명 앞 토큰
- `scale`: 상품명의 `1/N` 정규식. 없으면 `null`
- `line`: `config.py`의 브랜드 키 사전으로만 정한다. 어느 쪽에도 없는 브랜드는 카탈로그에서 제외
  - girl: `30ms`, `30mp`, `figurerise-standard`, `figurerise-standard-amp`
  - gunpla: 건프라 등급·라인 키 전부(0단계 `hobby-summary.json`의 `filters` 기준으로 작성하고, 사용자에게 목록 확인)
- `nameKo`: 번역 실패·키 없음이면 `null`. 사이트 검색은 nameKo·nameJa 모두 대상

### feed.json (크롤러가 씀)
```json
{"updatedAt":"ISO","items":[{
  "id":"jh-139459-BD5068846","type":"new|pb-new|kr-restock|kr-new",
  "date":"2026-10|2026-09-29","added":"ISO","catalogId":"bh-01_4257|null",
  "title":"원문 제목","titleKo":"...","url":"https://...","image":"안정 URL|null","source":"bandai-hobby|joyhobby"}]}
```
- id: 호비 신제품 `bh-new-<번호>`, P-반다이 `pb-new-<번호>`, 조이하비 `jh-<글번호>-<상품코드>`
- `added`: 처음 발견한 시각. 바꾸지 않는다
- 보관: `added` 내림차순 최대 1000개

### meta.json
`{"updatedAt":"ISO","since":"수집 시작 YYYY-MM-DD","sources":{"hobby":{"ok":true,"at":"ISO","items":21,"error":null},"joyhobby":{...}}}`
- 사이트 하단에 "마지막 수집"과 실패한 소스, 재판 공백 문구에 `since`를 쓴다

## 5. 수집 소스 (0단계에서 확인한 구조)
| 소스 | URL | 파싱 | 주기·양 |
|---|---|---|---|
| 호비 월별 일정 | `https://bandai-hobby.net/schedule/index.php?saledate=YYYYMM` | 카드 `a.p-card` (`.p-card__tit`, `.p-card__price`, `.p-card_date`). 묶음 ①일반 `/item/01_N/` ②ホビーオンライン `.p-card__tag.-online` → `p-bandai.jp/item/item-N`, 월 단위 ③ガンダムベース | 매일: 이번 달 ~ +3개월. 과거 월은 최초 채우기 때만 |
| 호비 상품 상세 | `https://bandai-hobby.net/item/01_N/` | `h1.p-heading__h1-product`, `dl.pg-products__detail dt/dd`, `a.pg-products__pblink`, `li.p-card__link a.p-card__flat`(브랜드·작품 키), 갤러리 이미지 | **처음 보는 번호만**, 실행당 최대 40개 |
| 호비 브랜드 목록 | `https://bandai-hobby.net/brand/<key>/` (페이저) | 상품 번호 열거 | 최초 채우기용 |
| 조이하비 공지 | `https://www.joyhobby.co.kr/mall/board_list.asp?siteid=joyhobby&BoardCode=notice&nowPage=N` → 글 `board_view.asp?SiteID=joyhobby&BoardCode=notice&B_iID=<번호>` | 제목에 `반다이 제품리스트`가 있는 글. 본문 `상품코드 / 상품명 / 가격` 3줄 반복. 반다이 코드 `BD#######`만 | 매일 목록 1~2쪽, 처음 보는 글만 |

- 호출: `requests` + `beautifulsoup4`. Actions에서 결과가 로컬과 다르면(차단·리다이렉트) 그 소스만 Playwright로 바꾼다
- 모든 요청: robots.txt 준수, 요청 간 1.2초 이상, timeout 20초, 브라우저 형태 User-Agent, `requests.log`와 같은 형식으로 로그
- 소스 하나가 실패해도 계속하고 `meta.json`에 기록
- **최초 채우기**(`--bootstrap`): 걸프라는 브랜드 목록으로 전체, 건프라는 일정 페이지를 2015-01부터 이번 달까지 거슬러 상세를 나눠 받는다(실행당 40개, 여러 날 또는 수동 실행 여러 번). 그 이전 상품은 사용자가 연결하려 할 때 상세 URL을 붙여넣어 추가할 수 있게 한다(6장)
- 조이하비 과거 글: 최초 채우기 때 공지 게시판을 거슬러 올라가 반다이 제품리스트 글을 모은다. 몇 쪽까지 가능한지는 3단계에서 확인하고 `meta.since`에 기록

### 매칭 (`match.py`) — 조이하비 상품명 ↔ 카탈로그
- 상품명 형식: `[등급코드] 스케일 모델번호 한글명(영문명) - 작품(프라모델)` (0단계 표본 141건, `tests/fixtures/joyhobby-post-*.html`)
- 대괄호 코드 → 등급: `HGUC/HGAW/HGWFM/HGCE…`→HG, `RG`, `MG`, `MGSD`, `30MM_*`→30MM, `[피규어라이즈스탠다드]`→Figure-rise Standard 등 (사전은 config)
- 비교 키: 등급 + 스케일 + 영문명(괄호 안)을 우선, 없으면 한글명 ↔ `nameKo`. rapidfuzz, 임계값 config
- 애매하면(후보 2개 이상·점수 차 작음) 연결하지 않는다. 연결 안 된 항목도 피드에는 넣는다

### 번역 (`translate.py`)
- 새 카탈로그 항목만, 50개씩 Claude API. 한국 정식 명칭을 따르게 하고 JSON으로 받는다. 조이하비에서 매칭된 한국어 이름이 있으면 그걸 우선 쓴다
- 모델명은 `config.CLAUDE_MODEL` (daily-tech-digest와 같은 방식). `ANTHROPIC_API_KEY` 없으면 건너뜀

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
- 최초 채우기(`--bootstrap`) 중이거나 이전 feed가 비었으면 보내지 않는다
- `DISCORD_WEBHOOK_URL`이 없거나 `--dry-run`이면 콘솔 출력만. 발송 실패는 경고만

## 8. 실행 옵션
- `python main.py` / `--dry-run` / `--only hobby,joyhobby` / `--bootstrap --max-details 40`
- 로컬 미리보기: `python -m http.server -d docs 8000`

## 9. GitHub Actions (`crawl.yml`)
- 트리거: `schedule: cron "10 22 * * *"` (KST 07:10), `workflow_dispatch`(입력: bootstrap)
- `concurrency: { group: crawl }`, 권한 `contents: write`
- 단계: checkout → Python 3.12 + pip 캐시 → `python main.py` → 바뀐 `docs/data/*`만 커밋(`data: crawl YYYY-MM-DD`) → `git pull --rebase` 후 push
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
3. 국내 입고 — 조이하비 수집·과거 글 채우기·매칭·`kr` 이력
4. 사이트 연결 — 카탈로그 검색·연결, 공식 사진 갤러리·자리표시, 재판 공백, 신제품·입고 탭, 리뷰 링크
5. 마무리 — 실제 알림 1회(사용자 요청 시), README, 이전 아티팩트 정리 여부 확인
