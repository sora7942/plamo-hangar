# plamo-hangar
프라모델 컬렉션 관리 + 반다이 신제품·재판·국내 입고 알림. 정적 사이트(GitHub Pages, `docs/`) + 하루 1회 도는 Python 크롤러(GitHub Actions).
요구사항, 데이터 스키마, 완료 기준, 진행 순서는 @SPEC.md 참고. 지금 몇 단계인지는 SPEC 12장 기준으로 말한다.

## Stack
- 사이트: `docs/index.html` (+ 필요하면 `app.js`, `style.css`) — 바닐라 HTML/CSS/JS, 빌드 없음. 엑셀은 SheetJS(cdnjs, 필요할 때만 로드)
- 저장: 소유자 브라우저 → GitHub REST API(contents, Git Data API)로 `docs/data/collection.json`, `docs/photos/` 커밋
- 크롤러: Python 3.12 (로컬 conda env: `plamo`) — requests, beautifulsoup4, rapidfuzz, anthropic, python-dotenv, pytest (playwright는 0단계 spike용. 크롤러는 Actions에서 막힌 소스가 있을 때만 사용)
- 실행 환경: GitHub Actions (ubuntu-latest), 로컬은 Windows + PowerShell

## Commands
- 환경: 0단계에서 만든 `plamo` env를 쓴다. 새로 만들 때: `conda create -n plamo python=3.12 -y; conda activate plamo; pip install -r requirements.txt`
- 이후 작업 전: `conda activate plamo`
- 수집, 알림 없이: `python main.py --dry-run`
- 일부 소스만: `python main.py --dry-run --only joyhobby`
- 최초 카탈로그 채우기: `python main.py --bootstrap` (상세는 실행당 새 40 + 밀린 150. 확인용으로 범위를 줄일 때: `--bootstrap --from 2025-10 --data-dir <임시폴더>`)
- 사이트 미리보기: `python -m http.server -d docs 8000` → http://localhost:8000
- 테스트: `pytest -q` (사이트 순수 함수는 `node tests/site_*.test.mjs`)

## Structure
- 사이트가 쓰는 파일: `docs/data/collection.json`, `docs/photos/**` — 크롤러는 읽기만 한다
- 크롤러가 쓰는 파일: `docs/data/catalog-*.json`, `feed.json`, `meta.json` — 사이트는 읽기만 한다
- URL·대상 라인·주기·개수 제한·알림 규칙·모델명은 `crawler/config.py` 한 곳에만 둔다
- 수집기는 `crawler/sources/`에 소스별 파일로 두고 SPEC 4장 형식을 반환한다
- 테스트용 저장 응답은 `tests/fixtures/`
- `reference/artifact-v2.html`은 옮기기 전 원본. 고치지 않는다

## Rules
- 모든 외부 요청: robots.txt 준수, 요청 간 1.2초 이상, timeout 20초, 브라우저 형태 User-Agent (spike/common.py의 게이트를 crawler/http.py로 옮겨 재사용)
- 소스 하나가 실패해도 전체 실행은 계속하고 `meta.json`에 기록한다
- 시간은 timezone-aware, 저장은 `+09:00` ISO 문자열. JSON은 `encoding="utf-8"`, `ensure_ascii=False`
- 카탈로그 `kr` 이력과 피드 `added`는 한 번 들어가면 지우거나 바꾸지 않는다
- 사이트에 넣는 외부 문자열(카탈로그·피드·내 메모)은 전부 이스케이프한다 — localStorage에 GitHub 토큰이 있다
- 사이트를 고치면 데스크톱·모바일(400px), 라이트·다크 모드에서 확인한다
- 매칭이 애매하면 연결하지 않는다 (틀린 연결 < 연결 없음)

## Critical
- NEVER: 공식 이미지나 다른 사람의 사진을 내려받아 저장소에 넣지 않는다. 공식 이미지는 안정 URL 링크만, 리뷰어 사진·판매점 이미지는 쓰지 않는다
- NEVER: 서명 URL(`?Expires=`)을 저장하거나 살리려 하지 않는다 (갱신·프록시 금지)
- NEVER: 지역 제한(P-반다이 JP 등)을 VPN·프록시·일본 서버로 우회하지 않는다
- NEVER: GitHub 토큰·`DISCORD_WEBHOOK_URL`·`ANTHROPIC_API_KEY`를 코드·로그·커밋에 남기지 않는다 (`.env`는 `.gitignore`)
- NEVER: 테스트에서 실제 네트워크·디스코드·Claude API를 호출하지 않는다
- NEVER: 실제 디스코드 발송은 사용자가 요청할 때만. 개발 중에는 `--dry-run`
- NEVER: `collection.json`을 크롤러가 고치지 않는다
- 단계는 SPEC 12장 순서대로, 사용자가 다음 단계를 지시할 때만 넘어간다

## Gotchas
- 0단계 결과(`spike/report.md`)가 사이트 구조의 기준이다. 셀렉터·URL은 거기와 fixture를 따른다
- 호비사이트는 재판(再販) 정보가 없다. 일정은 최초 발매 기준이고 같은 상품이 다시 올라오지 않는다
- 호비 2025년 이후 상품 이미지는 CloudFront 서명 URL(만료 40~299초). 안정 호스트는 `bandai-a.akamaihd.net`, `bandai-hobby.net/images/`
- 호비 og:image는 전 상품 공통 ogp.png라 쓸 수 없다
- 같은 등급이 브랜드 키 여러 개로 갈린다(`hg`/`hg-c`/`pb_hg`) → config 매핑표
- 조이하비 공지 글마다 재입고/신규 문구가 다르다. 판정은 카탈로그 발매일 기준(SPEC 4장)
- 조이하비 상품명에 `(프라모델)` 꼬리표, 대괄호 등급 코드, 스케일이 없는 경우가 섞여 있다
- 사이트 저장과 크롤러 커밋이 같은 브랜치에 들어간다. 크롤러는 push 전에 `git pull --rebase`, 사이트는 ref 갱신 충돌 시 최신을 다시 읽는다
- Pages 반영은 커밋 후 1~2분 걸린다. 소유자 모드는 GitHub API로 직접 읽어 지연을 피한다
- GitHub contents API는 파일당 1MB 넘으면 내용 대신 download_url을 준다 → collection.json이 커지면 blob API로 읽는다
- 외부 이미지는 `referrerpolicy="no-referrer"`가 있어야 뜨는 경우가 많다
- `bandai-hobby.net/images`는 UA에 `HeadlessChrome`이 있으면 이미지 대신 HTML을 줘서 `ERR_BLOCKED_BY_ORB`로 막힌다 → Playwright 확인은 일반 Chrome UA로 (akamai는 무관, 일반 브라우저 방문자도 무관)
- GitHub Actions cron은 UTC 기준이고 몇 분씩 늦게 돈다
- Windows에서 `conda run`은 한글 출력을 깨뜨린다. `conda activate` 후 실행하거나 `conda run --no-capture-output`

## Compaction
- When compacting, always preserve the list of modified files, the current step in SPEC.md section 12, and test commands.
