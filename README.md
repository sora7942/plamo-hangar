# 프라 격납고 (plamo-hangar)

내 프라모델(건프라·걸프라) 컬렉션과 위시리스트를 관리하고, 반다이 신제품 소식과 **국내 입고(재입고) 소식**을 모아 보여주는 사이트.

- 사이트: <https://sora7942.github.io/plamo-hangar/> (GitHub Pages, 방문자는 보기만 한다)
- 요구사항·데이터 스키마·진행 순서: [SPEC.md](SPEC.md) / 작업 규칙: [CLAUDE.md](CLAUDE.md) / 진행 메모: [PROGRESS.md](PROGRESS.md)

## 목차

1. [무엇을 하나요](#1-무엇을-하나요)
2. [구조: 누가 무엇을 쓰나요](#2-구조-누가-무엇을-쓰나요)
3. [처음 설정 (한 번만)](#3-처음-설정-한-번만)
4. [소유자 모드: 토큰 만들기와 갱신](#4-소유자-모드-토큰-만들기와-갱신)
5. [사이트 쓰는 법](#5-사이트-쓰는-법)
6. [크롤러: 매일 도는 일과 수동 실행](#6-크롤러-매일-도는-일과-수동-실행)
7. [로컬 개발과 테스트](#7-로컬-개발과-테스트)
8. [운영 메모: 틀린 걸 고치는 법](#8-운영-메모-틀린-걸-고치는-법)
9. [데이터 출처와 원칙](#9-데이터-출처와-원칙)
10. [진행 상황](#10-진행-상황)

---

## 1. 무엇을 하나요

**사이트(보기·관리)**
- **보유 / 위시리스트**: 프라를 추가·수정·삭제하고 사진을 올린다(여러 장, 대표 사진 지정). 통계, 등급·상태·태그 필터, 정렬, 일괄 수정, 중복 경고, 엑셀 백업·가져오기.
- **반다이 제품 연결**: 내 프라를 반다이 제품 목록(카탈로그)의 제품과 연결하면 등급·스케일·시리즈(한국어)가 채워진다. 이름·URL로 찾고, 카탈로그에 없으면 호비사이트 상품 주소를 붙여넣어 연결만 해 둘 수 있다(다음 수집 때 채워진다). 설정의 **자동 연결 후보 보기**는 이름·등급·스케일이 똑같고 후보가 하나뿐인 것만 제안한다.
- **공식 사진**: 연결된 제품은 반다이 공식 사진이 붙는다(링크만, 저장소에 복사하지 않음). 쓸 수 있는 사진이 없는 신제품은 등급 글자 자리표시 + "공식 사진 보기" 버튼. 대표 사진은 공식·내 사진 중에서 고른다. 설정에서 공식 사진을 숨길 수 있다.
- **재판 공백**: 연결된 프라에 "국내 마지막 입고 2026-09-29 · 7일 전" 또는 "국내 입고 기록 없음 (2024-01-04 이후 기준) · 일본 발매 2022-10"을 보여주고, "재판 공백 긴 순"으로 정렬한다.
- **신제품·입고 탭**: 새로 발견된 신제품 · P-반다이 한정 · 국내 재입고 · 국내 신규 입고를 종류·라인·등급으로 걸러 본다. 내 보유·위시와 연결된 항목은 맨 위에 "내 프라"로 강조되고, "위시리스트에 추가"로 연결된 채 담을 수 있다.
- 상세에서 **리뷰 찾아보기**(유튜브·네이버 블로그 검색 링크).

**크롤러(매일 자동)**: 호비사이트의 신제품 일정·상품 상세와 조이하비(국내 매장) 공지의 반다이 입고 글을 모아 카탈로그·피드를 갱신하고, 새 소식을 디스코드로 알린다(내 프라 우선).

---

## 2. 구조: 누가 무엇을 쓰나요

```
docs/                       GitHub Pages 루트 (Deploy from a branch: main /docs). 빌드 없음
  index.html                진입점 + CSP (인라인 스크립트 없음)
  app.js                    화면 전체 (보유·위시·상세·폼·설정·연결·자동 연결)
  pure.js                   순수 함수: 데이터 정규화, 필터·정렬, 사진 순서·대표, 엑셀 가져오기·내보내기
  catalog.js                카탈로그 읽기·검색·연결 채우기·재판 공백·자동 연결 후보·리뷰 링크
  feed.js                   신제품·입고 탭
  github.js                 GitHub API 클라이언트 (소유자 판정, 한 커밋 저장)
  style.css  favicon.svg  .nojekyll
  data/                     아래 표
  photos/<프라ID>/           내 사진 (WebP + 썸네일)
crawler/                    Python 크롤러 (매일 KST 07:10, GitHub Actions)
  config.py                 URL·주기·개수 제한·알림 규칙·분류표·용어집·사람이 고치는 표 — 설정은 여기 한 곳에만
  sources/                  호비 일정·브랜드·상세, 조이하비 파서
  catalog.py  feed.py  kr.py  match.py  translate.py  series.py  discord.py  discord_test.py  mine.py  pipeline.py  store.py  http.py
main.py                     크롤러 진입점 (옵션은 `python main.py --help`)
.github/workflows/crawl.yml 매일 실행 + 수동 실행
tests/                      pytest(크롤러), node 테스트(사이트), Playwright 확인(e2e), fixtures(저장해 둔 응답)
spike/  reference/          0단계 검증 결과 / 옮기기 전 아티팩트 원본 (보존, 수정하지 않는다)
SPEC.md  CLAUDE.md  PROGRESS.md
```

### 데이터 파일 (`docs/data/`)

| 파일 | 쓰는 쪽 | 내용 |
|---|---|---|
| `collection.json` | **사이트** (소유자가 저장할 때마다 커밋) | 내 보유·위시 목록, 설정. 크롤러는 **읽기만** 한다 |
| `../photos/**` | **사이트** | 내 사진 파일. 크롤러는 손대지 않는다 |
| `catalog-gunpla.json`, `catalog-girl.json` | **크롤러** | 반다이 제품 목록(건프라·걸프라). 이름·등급·스케일·시리즈(`seriesKo`)·발매일·공식 사진 URL·국내 입고 이력(`kr`). 사용자가 URL로 연결한 비대상 상품은 `line:"other"`로 `catalog-gunpla.json`에 있다 |
| `catalog-pending.json` | **크롤러** | 아직 분류를 모르는 항목 + 비대상으로 제외된 id 목록(다시 받지 않음) |
| `feed.json` | **크롤러** | 신제품·입고 소식 (최대 1000개). `added`는 처음 발견한 시각으로 한 번 정해지면 바뀌지 않는다 |
| `kr-arrivals.json` | **크롤러** | 조이하비 원본 행, 글 처리 상태, BD 상품코드 ↔ 카탈로그 연결 |
| `series-ko.json` | **크롤러** | 시리즈 한국어 번역 사전 (seriesKey → 한국어) |
| `meta.json` | **크롤러** | 마지막 수집 시각, 소스별 성공·실패, 수집 진행 위치, 조이하비 기록 시작일 |

> 이 둘이 같은 `main` 브랜치에 커밋한다. 그래서 **크롤러는 자기 파일(위 표의 크롤러 7개)만 커밋**하고 `collection.json`·`photos/`가 섞이면 실패하도록 막아 두었다. 사이트 저장은 충돌하면 최신을 다시 읽고 묻는다.

---

## 3. 처음 설정 (한 번만)

1. **GitHub Pages**: 저장소 **Settings → Pages → Source: Deploy from a branch → `main` / `/docs`** → Save. 1~2분 뒤 사이트가 열린다.
2. **Actions Secrets** (Settings → Secrets and variables → Actions → New repository secret). 값은 절대 코드·로그·커밋에 적지 않는다.

   | 이름 | 용도 | 없으면 |
   |---|---|---|
   | `ANTHROPIC_API_KEY` | 한국어 이름·시리즈 번역 (새 제품·새 시리즈만, 비용은 미미) | 번역 단계를 건너뛴다 (나머지는 동작) |
   | `DISCORD_WEBHOOK_URL` | 디스코드 알림 (서버 설정 → 연동 → 웹후크) | 알림 없이 내용만 로그에 출력 |

3. **Actions 첫 실행**: Actions 탭 → `crawl` → Run workflow → `bootstrap` 켜기. 카탈로그가 다 찰 때까지(`meta.json`의 `crawl.backlog`가 0이 될 때까지) 몇 번 반복한다. 조이하비 과거 글은 `joy_backfill`로 한 번에 채운다. 자세한 건 [6장](#6-크롤러-매일-도는-일과-수동-실행).

---

## 4. 소유자 모드: 토큰 만들기와 갱신

소유자만 사이트에서 저장할 수 있다. 토큰은 **이 브라우저의 localStorage에만** 저장되고 서버로 보내지 않으며(GitHub API의 `Authorization` 헤더로만 쓴다) 화면에 다시 보여주지도 않는다. 공용 PC에서는 쓰지 말고, 쓴 뒤 설정 → **토큰 지우기**.

**만들기** (fine-grained)
1. GitHub 프로필 → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
2. Token name `plamo-hangar` / Resource owner 본인 / **Repository access → Only select repositories → `plamo-hangar` 하나만**
3. **Permissions → Repository permissions → Contents: `Read and write`** (Metadata: Read-only는 자동. 다른 권한은 주지 않는다)
4. Expiration 설정 → **Generate token** → 한 번만 보이는 `github_pat_…`을 복사
5. 사이트 맨 아래 **소유자 설정** → 붙여넣기 → **연결**. `+ 추가`, `가져오기`, `엑셀 백업`, `설정` 버튼이 나타난다.

**만료와 갱신**: 현재 토큰은 **2027-10-06에 만료**된다. 만료 전(GitHub가 메일로 알려 준다)에 위 방법으로 새 토큰을 만들거나, 기존 토큰 화면에 **Regenerate token**이 있으면 그것으로 다시 만들어 사이트 설정에 **붙여넣고 연결**하면 덮어써진다. 만료되면 저장할 때 "토큰이 만료됐거나 올바르지 않아요"가 뜨고 보기 전용으로 열린다 — 데이터는 안전하다. 갱신한 뒤 이 줄의 날짜도 고쳐 둔다.

**알아둘 점**
- **저장 1번 = 커밋 1개** (`collection: 추가 …`, `collection: 반다이 제품 5개 자동 연결 …`). 사진은 같은 커밋에 들어간다. 반영까지 **1~2분** 걸린다(소유자 화면은 API에서 바로 읽어 지연 없음, 방문자는 Pages 파일).
- 소유자 판정(`permissions.push`)은 계정 권한 기준이라, 토큰 권한이 모자라도 소유자 버튼이 보일 수 있다. 저장할 때 "Contents: Read and write 권한을 확인해 주세요"가 뜨면 토큰 권한을 다시 본다.
- **공개 저장소**라서 `collection.json`의 구매일·구매처·가격은 누구나 볼 수 있다. 설정의 "구매정보 숨기기"는 **화면에서만** 가린다. 꼭 비공개여야 하는 정보는 적지 않는다.

---

## 5. 사이트 쓰는 법

- **프라 추가**: `+ 추가` → 이름 입력 후 "반다이 제품에서 찾기"로 연결하면 등급·스케일·시리즈가 채워진다(새 프라는 전부, 이미 있는 프라는 빈 칸만. 이름은 체크박스를 켰을 때만 바뀐다). 연결하지 않고 직접 적어도 된다.
- **기존 프라 연결**: 상세 → "반다이 제품 연결 / 연결 변경 / 연결 해제". 설정 → "자동 연결 후보 보기"로 확실한 것만 한꺼번에.
- **사진**: 폼에서 여러 장 올리고 순서·삭제·대표 지정. 긴 변 1600px WebP + 480px 썸네일로 줄여 `docs/photos/<프라ID>/`에 올라간다(프라당 20장). 공식 사진은 저장소에 복사하지 않고 링크만 건다.
- **재판 공백 정렬**: 정렬 선택 → "재판 공백 긴 순"(국내 입고 오래된 순 → 입고 기록 없음(일본 발매 오래된 순) → 미연결). 소유자는 "빈 칸 모아보기 → 반다이 제품 미연결"로 연결할 프라를 모아 본다.
- **신제품·입고 탭**: 소식은 탭을 처음 열 때 한 번 읽는다. 연결 안 된 입고 글은 등급·라인을 몰라 필터를 켜면 빠진다(카탈로그 상세가 늘면 연결된다).
- **엑셀**: "엑셀 백업"은 `반다이 제품 ID` 열을 포함한다. 가져오기는 열 이름을 자동으로 맞추고, v2(아티팩트 시절) 백업·JSON(사진 포함)도 가져온다. 사진 파일은 백업에 넣지 않는다.
- **카탈로그에 없는 제품**: 호비사이트 상품 페이지 주소(`https://bandai-hobby.net/item/01_xxxx/`)를 붙여넣으면 `catalogId`만 저장된다. 이름은 직접 적고, 다음 수집 때 크롤러가 상세를 받아 채운다.

---

## 6. 크롤러: 매일 도는 일과 수동 실행

**매일 KST 07:10**(= UTC 22:10, GitHub 사정으로 몇 분씩 밀리고 부하가 크면 건너뛰기도 한다) `crawl` 워크플로가 돈다. 순서:

`호비 월별 일정 → 걸프라 브랜드 목록 → 상품 상세 → 조이하비 국내 입고 → 번역(이름·시리즈) → 피드 → 파일 쓰기 → 디스코드`

- 상세는 실행당 **사용자가 연결한 미등록 상품 20 + 새 상품 40 + 밀린 상품 150**까지(합계 400 이하).
- 소스 하나가 실패해도 나머지는 계속하고, 실패는 `meta.json`과 Actions 요약에 남는다.
- 바뀐 데이터 파일만 한 커밋(`data: crawl YYYY-MM-DD`)으로 올라간다. 허용 목록(7개 파일) 밖의 변경이 있으면 실패한다.
- **디스코드 알림**: 이번에 새로 발견된 항목을 묶어 보낸다 — 순서는 ① **내 프라**(내 보유·위시와 연결된 국내 입고, 맨 앞·강조) ② 국내 입고 ③ P-반다이 한정 ④ 신제품. 조이하비 항목은 글 날짜가 3일 이내인 것만, 메시지당 임베드 10개·실행당 3메시지(넘치면 "외 N건"). 최초 실행·`bootstrap` 중에는 보내지 않는다.

### 수동 실행 (Actions 탭 → `crawl` → Run workflow)

| 입력 | 기본 | 설명 |
|---|---|---|
| `bootstrap` | 꺼짐 | **최초 채우기.** 일정을 2015-01까지 거슬러 올라가고 걸프라 브랜드를 전체 쪽수로 수집. 상세는 실행당 한도만큼만 받으므로 `crawl.backlog`가 0이 될 때까지 몇 번 반복한다. 알림 없음 |
| `max_backlog` | 150 | 실행당 상세 "밀린 상품" 상한 (어떤 값이든 합계는 400을 넘지 않는다) |
| `joy_backfill` | 꺼짐 | **조이하비 과거 글 채우기만** 실행(`--bootstrap --only joyhobby`). 호비사이트는 건드리지 않는다. 게시판이 20쪽이라 한 번에 끝나고 약 7분 걸린다. 알림 없음 |
| `joy_pages` | 25 | 조이하비 과거 목록을 훑을 쪽 수. `bootstrap`과 같이 켜도 적용 |
| `discord_test` | 꺼짐 | **디스코드 테스트 알림 1건만** 보낸다. 수집·커밋은 하지 않는다. `feed.json` 최근 3개(내 프라 연결 항목이 있으면 그중 1개 포함)를 실제 알림과 같은 형식으로, 맨 앞에 `[테스트] 프라 격납고 알림 확인용`을 붙여 보낸다. 웹훅은 Secret만 쓰고, 없으면 "웹훅 없음"만 출력하고 끝난다 |

### 로컬에서 같은 일 해 보기

```powershell
conda activate plamo
python main.py --dry-run                      # 수집 + 파일 갱신, 디스코드는 보내지 않고 내용만 출력 (번역은 건너뜀)
python main.py --dry-run --only hobby_item    # 일부 단계만 (hobby, hobby_schedule, hobby_brand, hobby_item, joyhobby, translate)
python main.py --discord-test --dry-run       # 테스트 알림 내용만 출력 (보내지 않음)
```

> 실제 디스코드 발송은 사용자가 요청할 때만 한다. 개발 중에는 항상 `--dry-run`. 로컬 `--dry-run`·`--bootstrap` 결과 파일은 **커밋하지 않고** `git restore`로 되돌린다(데이터 파일은 Actions만 커밋).

---

## 7. 로컬 개발과 테스트

```powershell
# 환경 만들기 (최초 1회)
conda create -n plamo python=3.12 -y; conda activate plamo; pip install -r requirements.txt
# e2e(Playwright)까지 돌리려면: pip install -r spike/requirements.txt; playwright install chromium

conda activate plamo                        # 이후 작업 전
python -m http.server -d docs 8000          # 사이트 미리보기 http://localhost:8000 (토큰이 없으면 방문자 화면)

pytest -q                                   # 크롤러 테스트 (네트워크·디스코드·Claude 호출 없음)
node --test tests/site_pure.test.mjs tests/site_catalog.test.mjs tests/site_github.test.mjs tests/site_feed.test.mjs   # 사이트 순수 로직
python tests/e2e/site_mock_check.py         # Playwright: 가짜 GitHub으로 추가·수정·삭제·사진·일괄 수정
python tests/e2e/site_catalog_check.py      # Playwright: 카탈로그 연결·공식 사진·재판 공백·신제품·입고 탭·자동 연결
```

- 테스트는 **실제 네트워크·실제 디스코드·실제 Claude를 부르지 않는다**(`tests/conftest.py`가 막는다). 사이트 저장은 `tests/helpers/fake-github.js`가 메모리에서 흉내 낸다 — 앱 코드에는 mock 모드가 없다.
- e2e는 Google Fonts·cdnjs·공식 이미지 호스트에 실제로 접속한다. **공식 이미지 확인은 일반 Chrome UA로**(HeadlessChrome UA면 `bandai-hobby.net/images`가 이미지 대신 HTML을 줘서 막힌다). 스크린샷은 `tests/e2e/out/`(gitignore, 공식 이미지가 찍히므로 저장소에 넣지 않는다).
- 사이트를 고치면 **데스크톱·모바일(400px)·라이트·다크**에서 확인한다.
- **데이터 파일(`docs/data`의 크롤러 파일)은 Actions만 커밋한다.** 로컬에서 만든 결과는 되돌린다.
- **push 전에 `git pull --rebase`** — 크롤러(매일)와 사이트 저장이 같은 `main`에 커밋하기 때문이다.
- 로컬 `.env`(`.env.example` 참고, `.gitignore`)에 `ANTHROPIC_API_KEY`·`DISCORD_WEBHOOK_URL`을 넣을 수 있다. 개발 중 웹훅은 비워 둔다.
- Windows에서 `conda run`은 한글 출력을 깨뜨린다. `conda activate` 후 실행하거나 `conda run --no-capture-output`.

---

## 8. 운영 메모: 틀린 걸 고치는 법

모든 "사람이 고치는 표"는 `crawler/config.py`에 있다. 고치고 push하면 **다음 실행에 기존 데이터에도 반영**된다(분류표·용어집·덮어쓰기 표는 매 실행 시작에 다시 적용).

| 상황 | 고칠 곳 | 방법 |
|---|---|---|
| 조이하비 입고 글이 **엉뚱한 제품에 연결**됐다 | `KR_CODE_OVERRIDES` | `{"BD1234567": None}` = 연결 금지(`kr` 이력 제거, 한글 이름 되돌림). `{"BD1234567": "bh-01_4259"}` = 그 제품에 강제 연결. BD 코드는 `docs/data/kr-arrivals.json`의 `rows`/`codeMap`에서 찾는다. 틀린 연결 < 연결 없음이라 애매하면 연결하지 않는 게 기본 |
| **시리즈 한국어 번역**이 어색하다 | `SERIES_KO_OVERRIDES` | `{"seed-d": "기동전사 건담 SEED DESTINY"}` (키는 `docs/data/series-ko.json`의 seriesKey). 번역보다 우선하고 API를 부르지 않는다. 값에 일본어 가나 금지(테스트가 막는다) |
| **제품 이름 번역**에 같은 실수가 반복된다 | `TRANSLATE_GLOSSARY` | `{"グエル": "구엘"}` 한 줄 추가(시스템 프롬프트에 들어간다). 이미 저장된 번역은 `NAME_KO_REPLACEMENTS`(부분 문자열 치환)로 맞춘다. 값이 영문이면 영문 그대로 쓴다 |
| 어떤 브랜드가 건프라/걸프라로 **잘못 분류**됐다 | `BRAND_LINE` | 브랜드 키 → (line, 등급). 새 브랜드 키가 나오면 `meta.json`의 `unknownBrandKeys`에 남는다(분류하기 전까지 제외로 취급). 제외 → 포함 방향은 되살리지 못해 일정·브랜드 목록을 다시 훑어야 한다 |
| 번역 품질 확인 | — | `python -m crawler.translate --sample 20`, `python -m crawler.series --sample 10` (API 키 필요, 출력만 하고 파일은 쓰지 않는다) |

**자주 만나는 일**
- 저장했는데 방문자 화면에 없다 → 반영에 1~2분. 사진이 자리표시로 보이면 새로 고침.
- 공식 사진이 안 뜬다 → 서명 URL뿐인 신제품은 의도적으로 사진을 쓰지 않는다(자리표시 + "공식 사진 보기").
- 크롤러 소스 하나가 `FAIL`이다 → Actions 실행 요약과 `meta.json`의 `sources`를 본다. 다른 소스는 영향 없이 계속 돈다. 조이하비·호비사이트가 해외 IP를 막으면 그 소스만 끄고, 크롤러를 사용자 PC(작업 스케줄러)에서 돌려 push하는 방식으로 바꾼다(SPEC 9장).
- 조이하비는 EUC-KR이고, 조회수가 32767을 넘은 글은 사이트 버그로 HTTP 500이다(`broken`으로 한 번만 기록, 실패로 세지 않는다).
- Pages 배포·크롤러가 실패해도 데이터는 마지막 커밋 기준으로 다음 실행에 다시 수집된다(`added`·알림 중복이 생기지 않게 설계).

---

## 9. 데이터 출처와 원칙

- **출처**: 반다이 호비사이트(`bandai-hobby.net` — 월별 발매 일정, 상품 상세, 브랜드 목록)와 조이하비(`joyhobby.co.kr` — 국내 매장의 반다이 입고 공지). 한국어 이름·시리즈명만 Claude API로 번역한다(그 외 LLM 호출 없음).
- **비공식 사이트**다. 요청은 매일 한 번, 정중하게: robots.txt 준수, 요청 간 **1.2초 이상**, timeout 20초, 브라우저 형태 User-Agent. 차단이 의심되면(연속 실패) 그 소스를 즉시 멈춘다.
- **이미지**: 공식 이미지는 **안정 URL(`bandai-a.akamaihd.net`, `bandai-hobby.net/images`)을 링크로만** 건다. 내려받거나 재호스팅하지 않는다. 리뷰어·판매점 이미지, 조이하비 상품 이미지는 쓰지 않는다. 내 사진만 저장소에 올라간다.
- **서명 URL**(`?Expires=`)은 저장하지 않고, 살려 쓰려는 시도(주기 갱신·프록시)도 하지 않는다. 사진이 없으면 자리표시 + 공식 페이지 링크.
- **지역 제한**(P-반다이 JP 등)은 VPN·프록시·일본 서버로 **우회하지 않는다.** P-반다이 상품은 목록의 링크만 쓰고 상품 페이지를 요청하지 않는다.
- 일본 재판(再販) 일정은 공식 경로가 없어 수집하지 않는다. **재판은 조이하비 국내 입고 기준**이다.
- 비용: GitHub 무료(공개 저장소) + Claude API(새 제품·새 시리즈 번역만).

---

## 10. 진행 상황

| 단계 | 내용 | 상태 |
|---|---|---|
| 0 | 수집 가능성 검증(spike) | 완료 (`spike/report.md`) |
| 1 | `docs/`로 이전, 소유자 저장·사진·대표 사진 | 완료 |
| 2 | 카탈로그·피드 크롤러, 번역, 디스코드, `crawl.yml` | 완료 |
| 3 | 조이하비 국내 입고, 매칭, `kr` 이력 | 완료 |
| 4 | 카탈로그 연결·공식 사진·재판 공백·신제품·입고 탭·자동 연결·시리즈 한국어·내 프라 우선 알림 | 완료 |
| 5 | 디스코드 테스트 발송, README, 마무리 | 5a·5b 완료 — 실제 알림 확인(`discord_test`)과 이전 아티팩트 정리는 사용자 확인 후 |

세부는 [SPEC.md](SPEC.md) 12장, 작업 중 메모는 [PROGRESS.md](PROGRESS.md).
