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
- 조이하비 과거 글 채우기(한 번에 끝남): `python main.py --bootstrap --dry-run --only joyhobby` (`--joy-pages N`으로 쪽 수 조절, 진행 위치는 `meta.crawl.joyNext`). 전체 보고서는 `crawler/out/joy-report.json`
- 최초 카탈로그 채우기: `python main.py --bootstrap` (상세는 실행당 새 40 + 밀린 150. 확인용으로 범위를 줄일 때: `--bootstrap --from 2025-10 --data-dir <임시폴더>`)
- 2015년 이전 상품 채우기(수동 실행 `brand_backfill`): `python main.py --brand-backfill` (= `--only hobby_backfill`. 목록 약 366쪽을 카드만으로, 약 8분. 진행 위치는 `meta.crawl.brandBackfill`, 알림 없음. 대상 브랜드는 `config.OLD_BRANDS`, bb 제외)
- 번역만(수집 없음): `python main.py --translate-only --translate-max 1500` (밀린 번역을 최신 발매순으로 한 번에. Actions 입력 `translate_only`·`translate_max`)
- 용어 일관성 점검(읽기 전용): `python -m crawler.audit_terms --top 50` → 표기가 갈린 가타카나 단어 표. 결과는 `crawler/out/term-audit.md`
- 몰 수집(내 PC에서만): `python main.py --only mall --mall-local` → `docs/data/mall-scan.json`만 쓴다(`--dry-run`이면 쓰지 않음, `--mall-dump DIR`로 받은 HTML 저장). 매일은 작업 스케줄러가 `scripts/mall_local.ps1`로 돌려 그 파일만 커밋·push (README 6장)
- 디스코드 테스트(수집 없음): `python main.py --discord-test --dry-run` (실제 발송은 Actions `discord_test`로, 사용자가 요청할 때만)
- 사이트 미리보기: `python -m http.server -d docs 8000` → http://localhost:8000
- 테스트: `pytest -q` (사이트 순수 함수는 `node --test tests/site_*.test.mjs`, 화면은 `python tests/e2e/site_mock_check.py`·`site_catalog_check.py`)

## Structure
- 사이트가 쓰는 파일: `docs/data/collection.json`, `docs/photos/**` — 크롤러는 읽기만 한다
- 크롤러가 쓰는 파일: `docs/data/catalog-*.json`, `feed.json`, `kr-arrivals.json`, `series-ko.json`, `mall.json`, `meta.json` — 사이트는 읽기만 한다. **이 파일들은 Actions만 커밋한다**(예외 하나: `mall-scan.json`은 내 PC만 커밋한다 — Actions의 커밋 허용 목록에 넣지 않는다) — 로컬 `--dry-run`/`--bootstrap` 결과는 `git restore`로 되돌리고 커밋하지 않는다
- 크롤러는 `docs/data/collection.json`을 **읽기만 한다**(`crawler/mine.py`) — 연결된 `catalogId`로 미등록 상품의 상세를 받고(`manual:true`, 제외 브랜드는 `line:"other"`), 디스코드에서 "내 프라"를 먼저 보낸다
- 시리즈 한국어: `crawler/series.py`가 seriesKey별로 한 번만 번역해 `series-ko.json`에 보관하고 카탈로그 항목의 `seriesKo`를 채운다. 틀린 번역은 `config.SERIES_KO_OVERRIDES`에 한 줄 추가
- 반다이남코코리아몰(7a): **몰 방화벽이 클라우드 IP를 막아(Actions는 `Request Rejected`) 목록은 내 PC가 읽는다** — `crawler/sources/mall.py`(목록 페이지만, 품절 상품 포함 49요청·3초 간격, 상세·이미지 요청 없음, 실행당 `MALL_MAX_REQUESTS`)를 `crawler/mall_scan.py`의 `--mall-local`이 불러 `docs/data/mall-scan.json`(PC만 씀)에 스냅샷을 남긴다. Actions의 `mall` 단계는 **요청 없이** 그 파일을 읽어 `crawler/mall_link.py`가 gno ↔ catalogId 연결·가격(`priceKrw`, `priceKrwAt` = 스냅샷 시각; 사이트는 내 프라의 직접 입력 가격이 비면 이 값을 "정가 기준" 구매 가격으로 화면에서만 보여 준다 — collection.json에는 저장하지 않고 엔 정가는 환산하지 않는다)·몰 이름(`nameKoSource:"bnkrmall"`, 몰 > 조이하비 > AI)·시리즈·판매 종료(`mallEnded`)를 카탈로그에 반영하고 `docs/data/mall.json`(Actions만 씀)에 상태를 둔다. 틀린 연결은 `config.MALL_OVERRIDES`. **몰 이미지는 저장하지 않는다 — 7b(소유자 화면 전용 링크)만 허용, Critical 참고. 목록 카드의 사진 경로 `imgPath`는 `mall-scan.json`·`mall.json`에만 두고 `catalog-*.json`의 `images`(공식 사진)에는 섞지 않는다**
- 검색 별칭은 `docs/aliases.js`(사이트 쪽 사전 — config가 아니다; 일본어 가나는 묶음에서만, 한국어 표기와 짝으로. `∀`는 `norm`이 `ターンエー`로 읽는다): 철자·줄임말 묶음, 무시할 꼬리말(클리어·코팅 — 가산만), 일반어. 연결 도우미의 진행 상태는 순수 로직 `docs/assist.js`, 화면은 app.js `openAssist`
- 상세 받는 순서: ① 사이트에서 연결한 미등록 상품(`manual`, 실행당 `MANUAL_DETAIL_MAX`) ② 새 상품 ③ 밀린 상품은 **발매월 최신순**(같은 달이면 line이 있는 항목 먼저)
- URL·대상 라인·주기·개수 제한·알림 규칙·모델명·매칭 임계값은 `crawler/config.py` 한 곳에만 둔다. 사람이 고치는 표(`BRAND_LINE`, `JOY_BRACKET_GRADES`, `KR_CODE_OVERRIDES` …)도 거기 있다
- 수집기는 `crawler/sources/`에 소스별 파일로 두고 SPEC 4장 형식을 반환한다
- 테스트용 저장 응답은 `tests/fixtures/`
- `reference/artifact-v2.html`은 옮기기 전 원본. 고치지 않는다

## Rules
- 모든 외부 요청: robots.txt 준수, 요청 간 1.2초 이상, timeout 20초, 브라우저 형태 User-Agent (spike/common.py의 게이트를 crawler/http.py로 옮겨 재사용)
- 소스 하나가 실패해도 전체 실행은 계속하고 `meta.json`에 기록한다
- 시간은 timezone-aware, 저장은 `+09:00` ISO 문자열. JSON은 `encoding="utf-8"`, `ensure_ascii=False`
- 카탈로그 `kr` 이력과 피드 `added`는 한 번 들어가면 지우거나 바꾸지 않는다 (예외: `KR_CODE_OVERRIDES`로 사람이 "연결 금지"한 코드의 kr만 뺀다). 피드 항목의 `type`만 조이하비 연결 후 60일 규칙으로 고칠 수 있다
- 조이하비 이름 매칭은 애매하면 연결하지 않는다. 연결(`MATCH_LINK_SCORE`)과 `nameKo` 교체(`MATCH_NAME_SCORE`, 더 높음)는 기준이 다르다. 교체 전 번역은 `nameKoAi`에 보존한다. 교체는 `line`이 gunpla인 항목만(걸프라는 번역 유지). 이름 끝의 ` - <작품명>` 꼬리는 뗀다(단 꼬리에 변형 표시어 `JOY_VARIANT_MARKERS`가 있으면 변형 이름이라 떼지 않는다)
- 사이트에 넣는 외부 문자열(카탈로그·피드·내 메모)은 전부 이스케이프한다 — localStorage에 GitHub 토큰이 있다
- 사이트를 고치면 데스크톱·모바일(400px), 라이트·다크 모드에서 확인한다
- 매칭이 애매하면 연결하지 않는다 (틀린 연결 < 연결 없음)

## Critical
- NEVER: 공식 이미지나 다른 사람의 사진을 내려받아 저장소에 넣지 않는다. 공식 이미지는 안정 URL 링크만, 리뷰어 사진·판매점 이미지는 쓰지 않는다
- NEVER: **몰(bnkrmall.co.kr) 이미지는 소유자 화면에서만 링크로 표시한다.** 다운로드·저장소 저장·방문자 화면 표시 금지(몰 이용약관 제23조②(사전 승낙 없는 복제·송신·배포·제3자 이용 금지)). 승낙을 받기 전까지 유지. 방문자 화면 DOM에는 img·URL·배경 어디에도 몰 이미지가 없어야 한다(e2e로 확인). 대표 사진(cover)으로 고를 수도 없다. 쓰는 것은 목록 카드의 상품 사진 경로(`imgPath`)뿐이고 리뷰·상세설명·배너 이미지는 쓰지 않는다
- NEVER: 서명 URL(`?Expires=`)을 저장하거나 살리려 하지 않는다 (갱신·프록시 금지)
- NEVER: 지역 제한(P-반다이 JP 등)을 VPN·프록시·일본 서버로 우회하지 않는다
- NEVER: GitHub 토큰·`DISCORD_WEBHOOK_URL`·`ANTHROPIC_API_KEY`를 코드·로그·커밋에 남기지 않는다 (`.env`는 `.gitignore`)
- NEVER: 테스트에서 실제 네트워크·디스코드·Claude API를 호출하지 않는다
- NEVER: 실제 디스코드 발송은 사용자가 요청할 때만. 개발 중에는 `--dry-run`
- NEVER: `collection.json`을 크롤러가 고치지 않는다
- 단계는 SPEC 12장 순서대로, 사용자가 다음 단계를 지시할 때만 넘어간다

## Gotchas
- **몰(bnkrmall.co.kr)은 클라우드 IP를 막는다**: Actions에서 robots.txt·목록 모두 HTTP 200 `Request Rejected / Your support ID is …`(247바이트)가 온다(2026-10 진단) → 몰은 Actions가 요청하지 않고 내 PC가 `--mall-local`로 읽는다. 로컬에서도 차단 응답이 오면 `mall-scan.json`에 `blocked:true`만 기록하고 **재시도·헤더 위장·프록시·VPN 없이 멈춘다**(`mall.scan`이 첫 차단에서 전체를 중단). Actions는 blocked·스냅샷 7일 초과(`MALL_STALE_DAYS`, 이때는 "판매 종료" 판정 안 함 + 사이트가 "가격 확인 날짜" 표시)·파일 없음을 `meta.sources.mall`의 경고로 남긴다
- 0단계 결과(`spike/report.md`)가 사이트 구조의 기준이다. 셀렉터·URL은 거기와 fixture를 따른다
- 조이하비는 **EUC-KR**(응답 헤더 `Charset=euc-kr`)이다. `crawler/http.py`의 `decode_body`가 Content-Type → `<meta charset>` → UTF-8 순으로 읽는다. `r.text`나 UTF-8 고정 디코딩을 쓰면 한글이 깨진다. fixture도 `joyhobby-raw-*.html`은 응답 원본 바이트(`joyhobby-post-*`/`joyhobby-board-notice-p1`은 Playwright 저장본 UTF-8)
- 조이하비 공지 목록: **고정 공지 7개(`Notice=true`)가 쪽마다 맨 위에 반복**된다(버릴 것). 쪽당 일반 글 20개, **마지막 쪽은 20쪽(2026-10)**, **21쪽부터는 마지막 행만 되풀이**해서 돌려준다(오류가 아님 — 새 글이 없거나 20개 미만인 쪽에서 멈춘다). 제목 형식이 제각각이라 `반다이`|`입고` 후보의 본문에 `BD#######` 행이 있는지로 확정한다
- 조이하비 상품명에는 영문명(괄호)이 있지만 **카탈로그에는 영문명이 없다** → 모델번호 토큰(`MS-09F` 등)으로 보강한다. 모델번호가 양쪽에 있는데 서로 포함하지 않으면(`MSN-04` vs `MSN-04FF`) 연결하지 않는다
- **이름 점수만으로는 틀린 연결을 못 막는다**(델타↔제타 80점, 자쿠 III↔자쿠 II 91점, 더블오라이저↔잔라이저 92점이 첫 실행에서 연결됐다). `match.guard`가 영문·숫자 덩어리와 낱말 차이를 본다. 임계값(`MATCH_LINK_SCORE`/`MATCH_NAME_SCORE`/`MATCH_TOKEN_RATIO`)을 고칠 때는 `crawler/out/joy-report.json`의 `newLinks`·`nearMiss`로 틀린 연결이 없는지 본다
- 조이하비 글 중 **조회수가 32767을 넘은 글은 사이트 버그로 HTTP 500**(smallint 오버플로 메시지)이다. 재시도해도 소용없고 `state: broken`으로 한 번만 기록한다(차단 판정과 별개)
- 호비사이트는 재판(再販) 정보가 없다. 일정은 최초 발매 기준이고 같은 상품이 다시 올라오지 않는다
- **몰 목록의 `soldout=Y`는 품절 상품을 *빼는* 값이다**(사이트 "전체상품" 링크가 그 값을 쓰는데도). 그 값으로는 판매 중인 상품만 나와 건프라가 8쪽·282개뿐이었고 MGSD 윙 건담 제로 EW·RG 윙 건담 제로 EW 같은 품절 상품이 통째로 빠졌다(2026-10 확인). `soldout=`(빈 값)이면 품절도 나와 건프라 40쪽(≈1,600개)·30MM 5쪽·Figure-rise 4쪽 = **49요청**, 상품 약 1,940개(80%가 품절). 품절 표시는 `.badge`가 아니라 `.thumb-dim`의 `SOLD OUT`이다. **요청 간격 1.2초로 22쪽을 읽자 23번째부터 연결이 끊겼다**(ConnectionError, 속도 제한으로 보임) → 몰은 `MALL_MIN_INTERVAL`=3초로 느리게(약 2분 30초). 연결이 끊기면 그 실행은 일부만 읽은 스냅샷(`complete:false`)이 되고 "판매 종료"를 판정하지 않는다
- 몰 판매가(원) ÷ 호비 정가(엔, 세금 포함)는 연결이 맞으면 거의 항상 10.91이라 `MALL_PRICE_RATIO` 밖이면 연결하지 않는다. 몰은 일부 상품(30MM 등)을 이름에 등급 낱말 없이 올리고, 건담베이스 한정 클리어·메탈릭·코팅 컬러는 몰에서 팔지 않아 엔 정가로 남는 게 정상이다. 호비사이트 상품 중에는 브랜드 키가 아예 없어 브랜드 목록·`brand_backfill`에 안 잡히는 것(MG ∀ガンダム 기본판 `01_1663`)이 있다. 몰 이름이 카탈로그 AI 번역과 철자가 달라(`발바토스`/`바르바토스`) 보호 규칙에 막힌 쌍은 `MALL_OVERRIDES`로 지정하거나 `TRANSLATE_GLOSSARY`에 표기를 정한다
- 호비 2025년 이후 상품 이미지는 CloudFront 서명 URL(만료 40~299초). 안정 호스트는 `bandai-a.akamaihd.net`, `bandai-hobby.net/images/`
- 호비 og:image는 전 상품 공통 ogp.png라 쓸 수 없다
- 같은 등급이 브랜드 키 여러 개로 갈린다(`hg`/`hg-c`/`pb_hg`) → config 매핑표
- 조이하비 공지 글마다 재입고/신규 문구가 다르다. 판정은 카탈로그 발매일 기준(SPEC 4장)
- 조이하비 상품명에 `(프라모델)` 꼬리표, 대괄호 등급 코드, 스케일이 없는 경우가 섞여 있다
- 사이트 저장과 크롤러 커밋이 같은 브랜치에 들어간다. 크롤러는 push 전에 `git pull --rebase`, 사이트는 ref 갱신 충돌 시 최신을 다시 읽는다
- Pages 반영은 커밋 후 1~2분 걸린다. 소유자 모드는 GitHub API로 직접 읽어 지연을 피한다
- GitHub contents API는 파일당 1MB 넘으면 내용 대신 download_url을 준다 → collection.json이 커지면 blob API로 읽는다
- 외부 이미지는 `referrerpolicy="no-referrer"`가 있어야 뜨는 경우가 많다
- 공식 이미지 카드·썸네일은 akamai `/bc/img/model/xl/…`(약 187KB) 대신 `/bc/img/model/m/…`(약 12KB, 2026-10-08 확인)을 쓰고, 안 뜨면 xl로 되돌린다(`catalog.js` `thumbUrl` + `data-alt`). `bandai-hobby.net/images`는 작은 사이즈 경로를 모르므로 그대로 쓴다
- 사이트 확인 e2e: `python tests/e2e/site_mock_check.py`(빈 컬렉션 전제, 가짜 GitHub), `python tests/e2e/site_catalog_check.py`(카탈로그 연결·공식 사진·방문자 화면, 실제 이미지 호스트 사용 — 일반 Chrome UA). `loading="lazy"`라서 화면에 들어와야 이미지 요청이 나가니 스크롤해서 확인한다
- 디스코드는 **`url`이 같은 embed를 한 카드로 합친다**(첫 번째만 보임). 조이하비는 한 글에 상품 여럿이라 `discord.embed_url`이 `&bd=<BD코드>`를 붙여 구별한다(조이하비는 모르는 파라미터를 무시한다). embed를 만들 때 `url`이 겹치지 않는지 항상 본다
- 번역에 **원문에 없는 한자**가 섞이기도 한다(`ヴィダール`→`비达르`). 가나 검사가 못 거르므로 `translate.stray_han`이 따로 거르고, 기존 데이터는 매 실행 시작에 비워 재번역한다(`fixups.strayHanReset`). 원문에도 있는 한자(`89式`·`改`)는 정상
- 용어집(`TRANSLATE_GLOSSARY`) 키는 **낱말 전체**로 쓴다(`アクシ`는 `アクション`에도 걸린다). 용어집에 새 용어를 넣으면 그 용어가 원문에 있는데 번역에 지정 표기가 없는 `nameKo`·`series-ko`가 다음 실행 시작에 비워져 재번역된다(용어마다 한 번 — `meta.crawl.glossaryApplied`, `fixups.glossaryReset`). 조사 붙은 표기(`티탄즈의 깃발 아래`)는 지정 표기를 포함하므로 정상으로 본다
- 용어집 표기의 **근거 1순위는 몰 상품명**이다(몰 > 조이하비 > 사용자 지정 > AI). 몰에 같은 단어가 다른 표기로 나오면 몰 쪽으로 맞춘다. 조이하비 매칭·사이트 검색·자동 연결 후보는 `nameKo`뿐 아니라 `nameKoAi`·`nameKoJoy`·`nameJa`도 비교에 쓴다(몰 이름으로 바뀌며 모델번호·옛 표기가 빠지기 때문. 모델번호 보호 규칙은 모든 이름에서 모델번호를 모은다)
- 호비 브랜드 목록의 페이저는 첫·끝 쪽만 링크로 보여 준다(`hg`는 143쪽, 쪽당 10개). `BRAND_MAX_PAGES`(60)는 걸프라용이고 과거 채우기는 `BRAND_BACKFILL_MAX_PAGES`를 쓴다
- 검색은 **비교용 이름**(`HG 1/144`뿐 아니라 `HGUC`·`HGCE`·`HGBD:R` 머리말도 뗀 `kn`/`jn`/`cmp`)과 **화면용 이름**(`title` — 카탈로그 원래 이름, 등급·스케일 머리말만 뗌)이 다르다. 화면·이름 채우기에는 `title`을, 비교에는 `kn`/`jn`/`cmp`를 쓴다
- `bandai-hobby.net/images`는 UA에 `HeadlessChrome`이 있으면 이미지 대신 HTML을 줘서 `ERR_BLOCKED_BY_ORB`로 막힌다 → Playwright 확인은 일반 Chrome UA로 (akamai는 무관, 일반 브라우저 방문자도 무관)
- GitHub Actions cron은 UTC 기준이고 몇 분씩 늦게 돈다
- Windows에서 `conda run`은 한글 출력을 깨뜨린다. `conda activate` 후 실행하거나 `conda run --no-capture-output`

## Compaction
- When compacting, always preserve the list of modified files, the current step in SPEC.md section 12, and test commands.
