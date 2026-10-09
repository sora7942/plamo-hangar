# PROGRESS — 4단계(사이트 연결)

규칙: 작은 단계가 끝날 때마다 로컬 커밋 + 이 파일 갱신. push는 사용자가 한다. docs/data는 커밋하지 않는다(collection.json은 읽기만).

## 결정 사항 (사용자 확인됨)
- URL 붙여넣기: 건프라/걸프라 브랜드면 정상 등록, 제외·미등록 브랜드는 catalog-gunpla.json에 `line:"other"`, `manual:true` (재분류 건너뜀, 제외 목록 id도 동일) — 크롤러 쪽은 4d
- 등급 추가(FULL MECHANICS→FM), 엑셀 가져오기 등급 매핑도 맞춤
- 기존 프라 연결은 빈 칸만 채움, 이름 교체는 체크박스(기본 꺼짐)
- 미래 kr.date 문구: "국내 입고 예정 YYYY-MM-DD"
- 월만 아는 발매일: 정렬에만 월 말일, 화면은 "2022-10"
- 재판 공백 기준일: meta.crawl.joyOldest (=2024-01-04, meta.since와 같음 확인) — 다르면 joyOldest
- 공식 카드 이미지: `bandai-a.akamaihd.net/bc/img/model/xl/` → `/m/` (12KB vs 187KB, 2026-10-08 확인), 실패 시 xl로 되돌림

## 4a 하위 단계
- [x] 4a-1 등급 확장 (pure.js GRADES·catalogGrade·glabel, normGrade, CSS 색)
- [x] 4a-2 catalog.js 순수 로직 + node 테스트 (검색에 scale 힌트 포함)
- [x] 4a-3 로딩 연결 + 공식 사진(카드·상세·hideOfficialPhotos 설정). e2e: `python tests/e2e/site_catalog_check.py` (40개 통과, 방문자 화면 공식 사진 확인)
- [x] 4a-4 폼/상세 "반다이 제품에서 찾기"·연결/해제·URL 붙여넣기·공식 대표 사진 (e2e 96개 통과, 기존 site_mock_check 186개도 통과)
- [x] 4a-5 e2e + 실제 데이터 검색 샘플 22개 + 방문자 화면 확인 → 사용자에게 보고(대기: 사용자가 4b 진행하라고 하면 시작)

## 4b 하위 단계 (재판 공백·정렬)
- [x] 4b-1 catalog.js `gapInfo`·월 말일 정렬키·문구 + node 테스트
- [x] 4b-2 pure.js `filterSort(kits, ui, ctx)`의 gap 정렬, GAPS.unlinked + 테스트
- [x] 4b-3 app.js UI: 카드·상세 재판 공백 줄, 정렬 '재판 공백 긴 순', 빈 칸 '반다이 제품 미연결' + e2e(117개) + 400px·다크
- [x] 4b-4 보고 (사용자가 4c 진행하라고 하면 시작)

## 4c 하위 단계 (신제품·입고 탭)
- [x] 4c-1 docs/feed.js 순수 로직(normalize·safeLink·build·filter·sort·문구·wishPrefill) + tests/site_feed.test.mjs
- [x] 4c-2 app.js 연결: 3번째 탭, feed-root 마운트, 위시 추가(openForm prefill/openPicker), CSS
- [x] 4c-3 e2e(site_catalog_check.py 157개 통과, e2e는 실제 컬렉션의 catalogId를 지운 사본으로 시험) + 400px·다크 + 보고 (사용자가 4d 진행하라고 하면 시작)

## 4d 하위 단계
- [x] 4d-1 사이트 순수 로직: catalog.js `autoLinks`·`seriesKoSuggestions`·`applyAuto`·`reviewLinks`·seriesKo(`seriesText`), pure.js 엑셀 catalogId 열·'autolink' 커밋 메시지 + 테스트
- [x] 4d-2 사이트 UI: 설정 '자동 연결 후보 보기'(연결 + 시리즈 한국어, 커밋 1개), 상세 리뷰 링크, 상세 linkbox에 시리즈, e2e
- [x] 4d-3 크롤러 seriesKo: crawler/series.py (고유 seriesKey만 번역, docs/data/series-ko.json 사전 + config.SERIES_KO_OVERRIDES), 카탈로그 항목에 seriesKo, crawl.yml 허용 목록, 테스트(Claude 호출 차단), --sample 10개
- [x] 4d-4 크롤러 미등록 catalogId: collection.json 읽기만 → 카탈로그에 없는 bh- id 상세 받기 (manual:true, 제외 브랜드면 line:"other" → catalog-gunpla.json, 재분류 건너뜀, 제외 목록 id 되살림, pb-는 안내만)
- [x] 4d-5 디스코드 '내 프라 우선' (collection.json 읽기만, 국내 입고 항목, 강조 색, 맨 앞)
- [x] 4d-6 SPEC·CLAUDE.md 갱신 + 보고(번역 샘플 10개 포함)

## 4d-3 메모 (보고에 사용)
번역 샘플 10개(실제 API, 2026-10-08, 파일 쓰지 않음): SDガンダムワールド ヒーローズ→SD건담 월드 히어로즈 / ガンダムビルドダイバーズ Re:RISE→건담 빌드 다이버즈 Re:RISE / 機動戦士ガンダムSEED FREEDOM→기동전사 건담 SEED FREEDOM / スーパーロボット大戦OG→슈퍼로봇대전 OG / ケロロ軍曹→케로로 중사 / ドラゴンボールシリーズ→드래곤볼 시리즈 / コードギアスシリーズ→코드 기아스 시리즈 / 怪獣8号→괴수 8호 / ブルーアーカイブ→블루 아카이브 / 機動戦士ガンダム0080 ポケットの中の戦争→기동전사 건담 0080 포켓 속의 전쟁. 고유 시리즈 74개(토큰 in/out 약 1.5k/0.3k는 10개 기준 → 전체 한 번에 약 10k).

## 5단계 (마무리)
- [x] 5a 디스코드 테스트 발송: `python main.py --discord-test`(crawler/discord_test.py), crawl.yml 입력 discord_test + 커밋 단계 건너뜀, tests/test_discord_test.py(9개). 로컬에서는 `--dry-run`으로만 확인(실제 발송은 Actions 수동 실행 `discord_test`로, 사용자가 요청할 때만)
- [x] 5b README.md 새로 쓰기 (구조·소유자 토큰·수동 실행 입력·로컬 개발·운영 메모·출처 원칙·Secrets)
- [x] 5c SPEC 8·9·12장 5단계 반영 + 보고

## 6단계 (결정 반영, 구현 중) — 순서: 6-1 → 6-7 → 6-4 → 6-3 → 6-5 → 6-2. 6-0b 몰 연동은 사용자가 이용약관 확인 후 따로 지시 (그때까지 CLAUDE.md·SPEC·README 규칙 문구는 바꾸지 않는다)
결정: "나중에"=이 브라우저 localStorage에 기억(목록 끝에서 다시 보기), 6-4에서 BB(bb) 제외(SD=sdgundamseries·sdcs·sdex), 6-1은 `&bd=<코드>`.
- [x] 6-1 디스코드 embed url 구별 (`discord.embed_url`, 조이하비 `&bd=BD…`, 겹치면 `#id`) — 발송 확인은 사용자가 Actions `discord_test`로
- [x] 6-7 한자 혼입: translate.stray_han·bad_translation(가나+원문에 없는 한자), 기존 nameKo/series-ko 비워 같은 실행에서 재번역(`fixups.strayHanReset`), 용어집 ヴィダール→비다르. 현재 데이터에서 걸린 것: bh-01_5469·bh-01_753 (`비达르`) 2건, 시리즈 0건
- [x] 6-4 2015년 이전 카탈로그: `hobby_backfill` 단계(옵션 단계, 기본 실행에 안 들어감) + `python main.py --brand-backfill` + workflow 입력 `brand_backfill`. 커서 `meta.crawl.brandBackfill`, 대상 `config.OLD_BRANDS`(hg·hguc·hgce·hg-c·mg·mgka·rg·mgsd·sdgundamseries·sdcs·sdex, bb 제외), 목록 카드만(약 366쪽≈8분), 피드·알림 제외. 상세 순서를 발매월 최신순(같은 달이면 line 있는 것 먼저)으로 변경, 연결된 프라는 manual 경로가 먼저. 번역 비용 추정: 20제목 샘플 입력 2,506/출력 846 토큰 → 2,000건 ≈ 입력 17만·출력 8.4만 토큰 ≈ $1.2 (Sonnet 5.5 $2/$10 per 1M), 실행당 600건 상한이라 4번에 나눠 번역. (문서는 7번 시작 전까지 SPEC/README/CLAUDE.md를 바꾸지 않기로 해서 여기에만 적음: README 수동 실행 표에 brand_backfill 추가 필요)
- [x] 6-3 검색 별칭 `docs/aliases.js`(묶음·줄임말·꼬리말·일반어) + catalog.js search 개편(별칭·꼬리말 가산·일반어만 맞으면 탈락·등급/스케일 낱말은 이름 일치로 안 침) + stripPrefix가 HGCE·HGUC·HGBD:R 머리말도 뗌. 미연결 124개 눈 판정 (정답/애매/오답/후보없음): 전 41/10/38/35 → 후 46/22/25/31, 연결된 7개는 7/7 유지. tests/site_aliases.test.mjs
- [x] 6-5 빈 칸 채우기: catalog.js fillCandidates·applyAuto(fillIds), 자동 연결 화면의 세 번째 구역(등급 기타·스케일 논스케일·시리즈 빈 칸만, 직접 적은 값은 안 건드림), 커밋 메시지 "빈 칸 N개 채움". e2e 191개 통과(현재 실제 연결 7개엔 후보 0건)
- [x] 6-2 연결 도우미: 6-2a 순수 상태 `docs/assist.js` + 6-2b 화면 `openAssist`(설정 '연결 도우미 시작' · '반다이 제품 미연결' 모아보기의 '연결 도우미로 시작', 후보 5개+검색, [연결][건너뛰기][나중에][이전], 중간 저장=커밋 1개 후 이어서, 닫을 때 확인, '나중에'는 localStorage `plamo-later`, 끝 화면에서 건너뛴/나중에 다시 보기). e2e 223개 통과
- [ ] (보류) 6-0b 몰 연동 — spike/mall-report.md 참고

## 6단계 마무리 (push 전 수정 2건)
- [x] 6-3 보정: 후보 목록·연결 도우미·이름 채우기에 보이는 이름은 카탈로그 원래 이름 그대로(`title`, 등급·스케일 머리말만 뗌). `HGUC`·`HGCE`·`HGBD:R` 머리말은 비교용(`kn`/`jn`/`cmp`, `stripPrefix(..., loose=true)`)에서만 뗀다. 미연결 124개 판정 수치는 그대로.
- [x] 문서 동기화: CLAUDE.md·SPEC.md·README.md에 6단계 반영(brand_backfill 입력·커서·`--brand-backfill`, 상세 받기 순서, strayHanReset·한자 검사, aliases.js, 연결 도우미, 빈 칸 채우기, 디스코드 url 구별). **몰 관련 규칙 문구(CLAUDE.md Critical 첫 항목·SPEC 2장·README 9장 이미지)는 7번 전까지 그대로.**

## 번역 품질 (6-8, 점검만 — 반영은 사용자 선택 후)
- [x] 6-8 용어 일관성 점검 도구 `python -m crawler.audit_terms [--top 50] [--min-items 3] [--out crawler/out/term-audit.md]` (읽기 전용, 자음 골격으로 같은 가타카나 단어의 한국어 표기 갈림을 찾고 조이하비 표기를 근거로 제안 + 내 컬렉션 별칭 후보). 테스트 `tests/test_audit_terms.py`. 사람이 확인하는 보조 도구라 오탐(フェクト·ジオン 등)이 있다
- [x] 사용자 선택 반영: TRANSLATE_GLOSSARY 32개 추가(번호 1·6·7…47, 보류 6개·오탐 9개 제외; 21번은 `アクシ`→`アクシズ`로 낱말 전체, 9번은 `티탄즈의`의 `의`가 조사라 `티탄즈`만). 용어집 변경 시 기존 nameKo·series-ko를 한 번만 비워 재번역(`Catalog.reset_glossary`·`series.drop_glossary`, `meta.crawl.glossaryApplied`, `fixups.glossaryReset`) — 실제 데이터 기준 이름 87개, 번역 대기 1,277→1,364
- [x] aliases.js: 퀀터↔퀀타↔콴타↔쿠안타, 즈곡그↔즈곡↔즈고크, 턴에이↔턴A↔∀(norm이 ∀를 ターンエー로 읽음), 턴엑스↔턴X↔ターンX. 스탠드→스탠다드는 넣지 않음. 부수 수정: 전각 `ＭＧ` 일본어 이름의 등급 머리말이 안 떼어져 등급 글자만으로 후보가 되던 `stripPrefix` 버그
- [x] Actions 입력 `translate_only`·`translate_max`(`--translate-only`·`--translate-max`, 최대 3000)
- [x] MG ∀ガンダム(MG 1/100 WD-M01 ターンエーガンダム, `01_1663`, 2007-08): 호비사이트에는 있으나 상품 페이지에 브랜드 키가 없어 브랜드 목록(mg)에 안 나온다 → brand_backfill로는 안 들어옴. 연결하려면 사이트에서 URL 붙여넣기(manual)
- [x] MG 비다르(bh-01_5469) 확인: 한자 리셋 후 재번역 대기(상세는 완료, 안정 이미지 없음) — 그대로 둠

## 7a 반다이남코코리아몰 — 가격·한국 공식 이름 (7b 사진은 사용자가 약관 확인 후 따로 지시, 이미지 규칙·CSP 그대로)
- [x] 7a-1 수집 `crawler/sources/mall.py`: 목록 페이지만(건프라 cate=1576 8쪽 + 애니프라 cate=1577 brandIdx=205 3쪽·202,203,407,386 1쪽, 요청 12회 + robots), 구조 변경은 소스 실패로 기록, `config.MALL_*`
- [x] 7a-2 매칭 `crawler/mall_link.py`: 등급 낱말 → `match.best_match` + 가격 비율(`MALL_PRICE_RATIO`) + 항목당 몰 상품 하나, `docs/data/mall.json`, crawl.yml 허용 목록에 mall 추가, `MALL_OVERRIDES`
- [x] 7a-3 카탈로그 필드 `priceKrw`·`priceKrwAt`·`mallGno`·`mallSoldOut`·`mallEnded`, 몰 이름(`nameKoSource:"bnkrmall"`, 몰 > 조이하비 > AI, `nameKoAi`/`nameKoJoy` 보존)·`seriesKo`(`seriesKoSource`) — 조이하비·번역·용어집·한자 재번역이 몰 이름을 건드리지 않게
- [x] 7a-4 사이트: 상세 "정가" 줄(₩ 몰 링크 / 품절 / 판매 종료(마지막 확인) / ¥ 일본 정가), 연결 후보 목록에 작은 가격, 카드에는 없음
- 로컬 dry-run(`--dry-run --only mall --data-dir <임시 사본>`): 몰 상품 397, 연결 76(19%) · 이름 교체 75 · 연결된 76개 모두 가격 비율 10.91 · 미연결 사유 no-grade 133(30MM 86 포함)·low-score 125·guard 62·ambiguous 1
- [ ] 남은 것: push 후 Actions 실행 → `meta.sources.mall` 확인, 미연결 중 맞는 것은 `MALL_OVERRIDES`·용어집으로 보강(예: 발바토스)

## 7a 후속 (push 전 3건)
- [x] 용어집 몰 대조(몰 > 조이하비): ズゴック 즈곡→즈고크, クアンタ 콴타→퀀터, バルバトス 발바토스 추가 (나머지 29개는 몰과 일치하거나 몰에 없음). 변경 단어가 든 nameKo 재번역 대상: 퀀터 13·즈고크 2·발바토스 23 (기존 용어집 변경 반영 방식)
- [x] 이름 교체 뒤에도 비교: match.CatalogIndex가 nameKo·nameKoAi·nameKoJoy 후보 + 모든 이름·nameJa의 모델번호, 사이트 검색(`it.alts`/`it.ka`)·자동 연결 후보도 같은 이름들 — 테스트 추가
- [x] MALL_OVERRIDES 5개(7223664·56457·59201·68326863·48650462) → 몰 연결 76→81

## 다음에 할 일
- 6단계 1~6번 + 보정·문서 끝(로컬 커밋). **6-0b 몰 연동은 사용자가 이용약관 확인 후 따로 지시.** push는 사용자가.
- push 후 사용자 확인 거리: (1) Actions `discord_test`로 embed 3개가 따로 보이는지 (2) Actions `brand_backfill`(약 8분, 알림 없음) → 이후 매일 실행이 상세·번역을 나눠 채움(번역 약 $1.2) (3) 한자 혼입 `비达르` 2건이 다음 실행에서 재번역되는지 (4) 사이트 연결 도우미·검색 별칭.

## 7a 후속 — 몰 수집이 Actions에서 실패 (2026-10-09)
증상: Actions `meta.sources.mall` = `ok:false`, "gunpla 1쪽: 상품 줄 0개"(3개 카테고리 모두 1쪽에서), requests 3, goods 0. 로컬은 396~397개 정상.

### 1단계: 진단 (구현됨, 로컬 커밋)
- [x] `mall.scan`이 실패한 쪽마다 응답 요약 `diag`를 남긴다: HTTP 상태·오류 이름·최종 URL·리다이렉트 수·바이트·Content-Type·`<title>`(100자)·본문 텍스트 앞 200자(script·style·title 제외). 구조 오류(200인데 줄 0개)와 HTTP 오류 모두. `meta.sources.mall.diag`에 저장(성공한 실행에서는 사라짐), 실행 요약(Step Summary)에 "몰 실패 진단" 표, 로그에 경고 한 줄
- [x] `HttpClient`: `Fetched.size`·`content_type`, `robots_info`(robots.txt 응답의 상태·바이트·HTML 여부·앞 200자 — robots.txt 자리에 차단 페이지가 오는지 확인용)
- [x] `--mall-dump DIR`: 받은 목록 HTML(`<카테고리>-p<쪽>.html`)과 `summary.json`(쪽별 요약 + robots)을 저장. `crawler/out/`는 gitignore
- [x] crawl.yml 입력 `mall_debug`(기본 꺼짐): `--only mall --dry-run --mall-dump crawler/out/mall-debug` → artifact `mall-debug`(보존 3일) 업로드, 커밋 단계 건너뜀. 몰 이미지 요청 없음(목록 HTML만)
- [x] 테스트: 진단 요약 필드·길이 제한·script/style 제외, dump 파일, 파이프라인 meta.diag, 워크플로 구조(커밋 건너뜀). 429개 통과. 실제 몰 로컬 dry-run(임시 폴더 사본)으로 12쪽 덤프·summary.json 확인
- **사용자가 할 일**: push → Actions → crawl → Run workflow → `mall_debug` 켜고 실행 → 실행 요약의 "몰 실패 진단" 표, artifact `mall-debug`의 `summary.json`·`gunpla-p1.html`을 확인해서 알려 주기

### 결과 해석 (2단계를 정하는 기준)
| 진단에 보이는 것 | 판단 | 다음 |
|---|---|---|
| 403/406/429, title `Access Denied`·`Forbidden`·보안 문구, 짧은 본문 | 해외 IP(데이터센터) 차단 | 아래 2단계 |
| 200이지만 title/본문이 점검·로그인·동의·봇 확인 | 응답이 다름(쿠키·리다이렉트·봇 검사) — 차단과 같으면 2단계, 헤더/쿠키로 풀리는지는 HTML 확인 후 판단. **우회 시도(프록시·VPN)는 하지 않는다** | 사용자와 결정 |
| 200이고 `li[data-childno]`가 있는데 파서만 실패 | 구조 차이(모바일/언어 분기 등) | 파서 수정 |
| 5xx·timeout·ConnectionError | 일시 장애 또는 연결 차단 | 한 번 더 실행해 재현되면 2단계 |
| robots.txt가 차단 페이지(`html:true`가 아닌 본문인데 규칙이 이상함) | robots 해석 문제 | 확인 후 수정 |

### 2단계: 계획 (구현됨 — 아래 "2단계 구현" 참고. 여기는 당시 계획 원문)
원칙: 한국 IP인 내 PC에서 평소처럼 요청하는 것이지 우회가 아니다. VPN·프록시·해외 서버 없음. robots.txt·요청 간격(1.2초)·상한(20회)은 그대로. Actions가 **카탈로그 파일의 유일한 작성자**라는 규칙을 지킨다.

**결정 (사용자 확인됨, 2026-10-09)**: PC는 `docs/data/mall-scan.json`만, Actions는 `mall.json`만 쓴다. 2단계는 사용자가 진단 결과를 보고 시작하라고 지시할 때만 시작한다.

(결정 전 검토 내용)
- 지금 `mall.json`은 `goods`(스캔 원본)와 `links`(Actions가 만든 gno↔catalogId 연결)를 함께 가진다. PC가 `goods`를, Actions가 `links`를 같은 파일에 쓰면 파일 작성자가 둘이라 push 충돌이 날 수 있다(JSON을 한 항목 한 줄로 쓰므로 자동 병합되는 날도 있지만 보장되지 않는다).
- **권장**: PC는 `docs/data/mall-scan.json`(스냅샷: `scan{at, complete, requests, count}` + `goods`)만 쓰고, `mall.json`(links·상태)은 Actions만 쓴다. 파일이 갈리므로 충돌이 없다. 지시하신 "mall.json만 커밋"과 다르니 확인 부탁.

**동작**
1. `python main.py --only mall --mall-local` (PC 전용): 몰 목록을 스캔해 `mall-scan.json`만 쓴다. 카탈로그·`mall.json`·`meta.json`·디스코드는 건드리지 않고 연결 계산도 하지 않는다(PC에는 최신 카탈로그가 없을 수 있다). 스캔이 불완전(`complete:false`, 상품 수가 이전의 50% 미만)이면 이전 스냅샷을 덮어쓰지 않는다.
2. Actions의 `mall` 단계: 스캔(요청)을 하지 않고 `mall-scan.json`을 읽는다. `scan.at`이 이미 흡수한 스캔과 같으면(PC가 안 올린 날) `absorb`·연결 계산·"판매 종료" 판정을 건너뛰고 기존 상태를 유지한다. 새 스냅샷이면 지금과 똑같이 `absorb → link_all`로 카탈로그에 가격·이름·시리즈·`mallEnded`를 적용한다. `priceKrwAt`은 Actions 실행 시각이 아니라 **스캔 시각(`scan.at`)**으로 적는다. `meta.sources.mall`에 `snapshotAt`·`snapshotAgeDays`를 남긴다. Actions는 `mall-scan.json`을 커밋하지 않는다(커밋 허용 목록은 그대로).
3. PC 스크립트 `scripts/mall_local.ps1`(PowerShell): ① 저장소 폴더로 이동, 작업 트리에 이 파일 외 변경이 있으면 중단 ② `git pull --rebase --autostash` ③ conda 환경 `plamo`의 `python.exe`를 직접 호출(Windows에서 `conda run`은 한글을 깨뜨린다) ④ `git add docs/data/mall-scan.json`만 → 허용 목록 밖 staged가 있으면 실패(`collection.json`·`photos/` 보호, crawl.yml과 같은 방식) ⑤ 변경이 있으면 `data: mall scan (local) YYYY-MM-DD` 커밋 → push, 실패하면 `pull --rebase` 후 최대 3회 ⑥ 로그를 `crawler/out/mall-local.log`에 남김. 변경이 없으면 커밋하지 않는다.
4. 작업 스케줄러 등록(관리자 권한 불필요, 사용자 계정으로) — 구현 시 README에도 넣는다:
   ```powershell
   $py  = "powershell.exe"
   $arg = '-NoProfile -ExecutionPolicy Bypass -File "C:\Users\woori\plamo-hangar\scripts\mall_local.ps1"'
   $act = New-ScheduledTaskAction -Execute $py -Argument $arg -WorkingDirectory "C:\Users\woori\plamo-hangar"
   $trg = New-ScheduledTaskTrigger -Daily -At 06:30            # Actions 07:10(KST)보다 먼저
   $set = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
   Register-ScheduledTask -TaskName "plamo-hangar-mall" -Action $act -Trigger $trg -Settings $set -Description "몰 목록 스캔 → mall-scan.json push"
   # 확인: Start-ScheduledTask -TaskName plamo-hangar-mall ; Get-ScheduledTaskInfo -TaskName plamo-hangar-mall
   # 해제: Unregister-ScheduledTask -TaskName plamo-hangar-mall -Confirm:$false
   ```
5. **PC가 꺼져 있던 날**: `-StartWhenAvailable`이라 켜진 뒤 바로 한 번 실행된다. 스캔은 커서 없는 전체 스냅샷(12쪽)이라 놓친 날을 메울 필요가 없고 다음 실행이 곧 최신이다. 그 사이 Actions는 `scan.at`이 안 바뀐 것을 보고 마지막 가격을 그대로 둔다(`mallEnded`를 잘못 판정하지 않음).
6. **신선도 표시**: 스냅샷이 7일(`config.MALL_STALE_DAYS`) 넘게 오래되면 사이트 정가 줄에 `가격 확인 YYYY-MM-DD`를 붙인다(기준 `priceKrwAt`, 방문 시각과 비교 — `catalog.js` `priceInfo`, node 테스트 추가). 그 이하면 지금처럼 표시한다. 디스코드·알림은 바꾸지 않는다.

**테스트(네트워크 없이)**: `--mall-local`이 `mall-scan.json`만 쓰고 카탈로그를 건드리지 않음, 불완전 스캔은 이전 스냅샷 유지, Actions 단계가 파일을 읽어 연결(요청 0회), 같은 `scan.at` 재실행은 변화 없음, `priceKrwAt = scan.at`, 오래된 스냅샷 문구(node), 스크립트의 허용 목록 검사는 PowerShell 로직이라 수동 확인.

**문서 갱신(구현 때)**: CLAUDE.md "크롤러가 쓰는 파일 … Actions만 커밋" 규칙에 `mall-scan.json`(PC만) 예외, SPEC 3·4·8·9장, README(작업 스케줄러 절차·문제 해결).


### 진단 결과 (2026-10-09, 사용자 실행)
Actions에서 몰 목록 3쪽 + robots.txt 모두 HTTP 200 `Request Rejected / Your support ID is …`(247바이트) — 웹 방화벽이 클라우드 IP를 차단. 로컬은 정상 → 2단계 진행. 이 응답은 "200인데 상품 줄 0개"라서 상태 코드만으로는 못 거른다 → 차단 문구 감지(`mall.looks_blocked`).

## 2단계 구현 (2026-10-09, 로컬 커밋 — push는 사용자가)
파일 분리는 권장안대로: **PC는 `mall-scan.json`만, Actions는 `mall.json`·카탈로그만**. 우회(VPN·프록시·헤더 위장)는 없다.
- [x] `python main.py --only mall --mall-local` (`crawler/mall_scan.py`): 몰 목록만 읽어 `docs/data/mall-scan.json`(`lastTry`: 시도 시각·쪽별 결과·오류·진단 / `scan`·`goods`: 마지막 스냅샷 / `blocked`)만 쓴다. 카탈로그·`mall.json`·`meta.json`은 건드리지 않는다. `--dry-run`은 파일을 쓰지 않는다. `--mall-dump DIR`로 받은 HTML 저장(진단)
- [x] 차단 감지: 403/429 또는 짧은 본문의 `Request Rejected`/`support ID`/`Access Denied`/`Forbidden`(상품 줄 없을 때) → **첫 차단에서 전체 스캔 중단**(재시도·다른 카테고리 요청 없음), `blocked:true` 기록, 이전 스냅샷은 지우지 않음. 429·연속 실패(SourceAborted)·robots 거부도 기록하고 정상 종료
- [x] Actions `mall` 단계는 **요청 없이** 파일을 읽어 `absorb → link_all`. 같은 스냅샷이면 `mall.json`·카탈로그 변화 없음(테스트: 바이트 비교). `priceKrwAt` = 스냅샷 시각. 7일(`config.MALL_STALE_DAYS`) 넘으면 "판매 종료" 판정 안 함 + meta 경고(`stale`, `snapshotAgeDays`), `blocked`·파일 없음도 경고(`ok:false`+`error`). 실제 데이터(PC 스냅샷 396개)로 확인: 연결 139, 같은 스냅샷 재실행은 파일 변화 없음
- [x] 사이트: `priceInfo(item, today)` — `priceKrwAt`이 7일보다 오래되면 정가 줄에 `가격 확인 YYYY-MM-DD`(품절이면 `품절 · 가격 확인 …`, 판매 종료·엔 정가에는 붙이지 않음)
- [x] `scripts/mall_local.ps1`: python 찾기 → 수집 → `mall-scan.json`만 `git add` + `git commit -- <경로>`(경로 지정 커밋; 다른 staged 파일은 같이 안 들어감, 커밋 후 파일 1개인지 재확인) → `git pull --rebase --autostash` → `git push`(실패 시 1회 재시도). main이 아니거나 rebase/merge 중이면 건너뜀. 로그 `crawler\out\mall_local.log`. **임시 저장소(로컬 bare remote)에서 실제 몰로 end-to-end 확인**: 작업 중 수정·staged 파일 유지, 커밋에는 `mall-scan.json`만, 원격이 앞서 있어도 rebase 후 push, 다른 브랜치면 종료 코드 3으로 건너뜀
- [x] crawl.yml: 커밋 허용 목록은 그대로(`mall-scan.json` 없음, 테스트로 고정). `mall_debug` 입력은 Actions가 더는 몰을 요청하지 않아 의미가 없어 제거(`--mall-dump`는 `--mall-local`용으로 유지)
- [x] 문서: CLAUDE.md Gotchas·명령·Structure, SPEC(3·4·5·8·9장), README(2·6·8장). 테스트 pytest 439개 + node 125개 통과

### 사용자가 할 순서
1. **push** (코드 + 스크립트 + 문서). 아직 `docs/data/mall-scan.json`이 저장소에 없으므로 3번 전까지 Actions의 `mall`은 "mall-scan.json 없음" 경고만 낸다(다른 소스는 정상)
2. **PC에서 첫 수동 실행** (PowerShell, 저장소 폴더, `main` 브랜치):
   ```powershell
   conda activate plamo
   python main.py --only mall --mall-local --dry-run     # 파일은 안 쓰고 읽히는지만 (약 12요청, 20초)
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\mall_local.ps1      # 수집 + mall-scan.json만 커밋·push
   Get-Content crawler\out\mall_local.log -Tail 20 -Encoding UTF8       # 끝에 "완료: push 됨"
   ```
   작업 트리에 다른 변경이 있어도 괜찮다(그 파일은 커밋되지 않고, `--autostash`가 잠깐 치웠다 되돌린다).
3. **Actions 실행**: Actions → `crawl` → Run workflow(기본값) → 실행 요약의 `mall` 행이 `ok`, `meta.sources.mall`에 `snapshotAt`·`links`(약 139)가 보이는지 확인. 다음 날 07:10 예약 실행도 같은 파일이면 변화 없음.
4. **작업 스케줄러 등록**(README 6장 "몰 수집"과 같은 명령, 매일 06:30):
   ```powershell
   $repo = "C:\Users\woori\plamo-hangar"
   $act  = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $repo `
             -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$repo\scripts\mall_local.ps1`""
   $trg  = New-ScheduledTaskTrigger -Daily -At 06:30
   $set  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
             -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
   Register-ScheduledTask -TaskName "plamo-hangar-mall" -Action $act -Trigger $trg -Settings $set -Description "몰 목록을 읽어 docs/data/mall-scan.json만 push"
   Start-ScheduledTask -TaskName plamo-hangar-mall                # 등록 직후 한 번 시험
   Get-ScheduledTaskInfo -TaskName plamo-hangar-mall | Select LastRunTime, LastTaskResult, NextRunTime     # LastTaskResult 0 = 정상
   Unregister-ScheduledTask -TaskName plamo-hangar-mall -Confirm:$false                                   # 삭제
   ```
5. 알아 둘 점: PC가 꺼져 있던 날은 `-StartWhenAvailable`로 켜진 뒤 한 번 실행된다(커서 없는 전체 스냅샷이라 놓친 날을 메울 필요 없음). 06:30에 `main`이 아닌 브랜치에서 작업 중이면 그날은 건너뛴다(로그에 남음, 종료 코드 3). 로그온하지 않은 상태에서는 로그온 후 실행된다.


## 몰 수집 범위 확장 + 구매 가격 기본값 (2026-10-09, 로컬 커밋 — push는 사용자가)
### 0. 원인과 수정
- 증상: MGSD 윙 건담 제로 EW가 엔화로 나옴. `mall-scan.json`에 MGSD·크샤트리아 0개(건프라 282개뿐).
- 몰 확인(요청 10회: 검색 2, 카테고리 목록 8, 상세 0 — 예산 안): **목록 URL의 `soldout=Y`는 품절 상품을 *빼는* 값**이었다(사이트 "전체상품" 링크가 그 값을 쓰지만 판매 중인 것만 나온다). MGSD 윙 건담 제로 EW(gno 11362547, ₩54,000)·RG 윙 건담 제로 EW·PG 등 윙 제로 계열이 전부 품절이라 빠졌다. `soldout=`(빈 값)이면 품절도 나온다. `endGoods`는 `Y`든 빈 값이든 같았다.
- 수정(a): `soldout=` 로 변경, 품절 표시는 `.badge`가 아니라 `.thumb-dim`의 `SOLD OUT`(파서 수정), 쪽수 상한 12→60·요청 상한 20→70. **요청 수 12 → 49** (건프라 40쪽 + 30MM 5쪽 + Figure-rise 4쪽, 상품 1,939개 = 판매 중 398 + 품절 1,541).
- **속도 제한**: 간격 1.2초로 읽자 22쪽 뒤 23번째부터 `ConnectionError`(스캔이 일부만 읽힘). `MALL_MIN_INTERVAL`=3초로 늦추니 49요청이 끝까지 정상(약 2분 30초). `--mall-local`만 3초를 쓴다.
- (b) 내 프라 검색(`/goods/search.do`)은 **구현하지 않았다**: (a) 뒤에 연결된 내 프라 24개 중 남은 ¥ 12개는 건담베이스 한정 클리어·메탈릭·코팅 컬러(몰에서 안 판다) 8개 + 몰에 아예 없는 제품(켐퍼 슈베어·큐베레이 댐드·풀 아머 ZZ Ver.Ka — 검색으로도 0건 확인, 츠키루나) + 연결 규칙에 걸린 2개(내러티브 C팩 `guard`, HG 레전드 건담 `ambiguous`)뿐이라 검색이 찾아줄 제품이 없다. 필요해지면 그때 추가.
- 후보(사용자 확인 필요, 아직 `MALL_OVERRIDES`에 넣지 않음): `"33247684": "bh-01_5164"` — 몰 `MG 내러티브 건담 C팩 Ver.Ka` ₩84,000 ↔ 호비 `ナラティブガンダム C装備 Ver.Ka` ¥7,700 (비율 10.91).

### 보고: 내 컬렉션 131개 (own 131 / wish 0)
| | 반다이 제품 연결 | ₩ 정가 있음 | ¥만 있음 |
|---|---|---|---|
| 적용 전 (배포 상태, 몰 396개) | 24 | 2 | 22 |
| 적용 후 (몰 1,939개, 로컬 시뮬레이션) | 24 | 12 | 12 |
- MGSD 윙 건담 제로 EW(`bh-01_5377`) → **₩54,000**, 품절 표시(`mallSoldOut`), 이름도 몰 표기 `MGSD 윙 건담 제로EW`.
- 몰 연결 전체 139 → 618(새 연결 479, 이름 교체 474). 최저 점수 연결을 훑어봤는데 틀린 연결은 보이지 않았다(점수 80~95는 철자 차이 정도, 가격 비율 9.5~12.5 통과).
- 연결된 프라가 24개뿐이라 나머지 107개는 `연결 도우미`로 연결해야 가격이 보인다.

### 1. 구매 가격 기본값 = 몰 정가 (사이트)
- `catalog.js` `purchasePrice(kit, item)`·`purchaseTotal(kits, itemOf)`: 직접 입력 > 몰 정가(`priceKrw`), 엔 정가만 있으면 없음(환산 안 함). collection.json에는 저장하지 않는다.
- 상세 `가격 ₩33,600 정가 기준`(작게)·위시 카드 `정가 ₩…`·통계 "총 구매액"/"예상 합계" = 직접 입력 + 정가 기준 + `정가 기준 N개 포함`·가격순 정렬도 같은 값. 수정 폼 가격 칸은 비우고 placeholder `정가 ₩33,600`(연결을 바꾸면 따라 바뀜). "구매 정보 빈 칸"과 엑셀 백업 가격 열은 직접 입력 기준 그대로(엑셀 "정가(참고)" 열은 넣지 않았다). `hidePurchase`는 정가 기준 값에도 적용(e2e로 확인).
- 카탈로그가 늦게 도착해도 통계를 다시 그린다.

### 테스트
pytest 441개, node 127개, e2e `site_mock_check` 186개·`site_catalog_check`(구매 가격 기본값 구역 추가). 실제 몰 49요청 스캔 + 파이프라인(`--only mall --dry-run`)을 임시 폴더에서 확인.

### 사용자가 할 일 (push 뒤)
1. `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\mall_local.ps1` (약 3분, 1,939개를 mall-scan.json으로 push) → 2. Actions `crawl` 수동 실행 → 3. 작업 스케줄러 등록은 README 6장 "몰 수집"의 명령 그대로(변경 없음, 실행 시간 제한 20분이면 충분).

## 엔 정가 → 원화 추정가 (2026-10-09, 로컬 커밋 — push는 사용자가)
- 근거: 반다이 프라모델 국내 정가 = 일본 세전 가격 × 12, 호비 `priceJpy`는 세금 10% 포함 → `round(priceJpy / 1.1) × 12` (¥3,080 → ₩33,600, ¥4,950 → ₩54,000, ¥1,760 → ₩19,200).
- 일치율(`python -m crawler.price`, 몰 연결 + 엔 정가 모두 있는 619개): **정확히 같음 617개(99.7%)**, 다름 2개 — 둘 다 품절 상품:
  `bh-01_108 HGUC 크샤트리아 리페어드 ¥8,030 → 추정 ₩87,600 / 몰 ₩78,000`, `bh-01_2653 Figure-rise Standard 프리저 최종형태 ¥2,640 → 추정 ₩28,800 / 몰 ₩26,400`(몰 가격이 한 단계 낮은 구판 가격으로 보임). 주의: 몰 연결은 가격 비율 9.5~12.5 보호 규칙을 통과한 것만 만들어지므로 표본이 그 범위로 걸러져 있다 — 그래도 범위 안에서 619개 중 617개가 소수점 없이 정확히 같다는 점이 식의 근거.
- 구현(사이트, 저장하지 않음): `catalog.js` `estimateKrw`·`isBandaiBrand`·`purchasePrice`(직접 입력 > 몰 정가 `listed` > 추정 `estimated`)·`purchaseTotal`(`listed`·`estimated` 개수). 상수는 `catalog.js`의 `KR_PRICE_RATE`(12)·`JP_TAX_DIVISOR`(1.1) 한 곳이고 `config.py`에 같은 값을 두어 테스트가 일치를 확인한다. 연결 = 반다이 제품이므로 연결 여부로 판단하되 브랜드를 반다이 외로 적은 프라는 제외(비워 두면 포함).
- 표시: 상세 정가 줄 `정가 ₩54,000 추정 · ¥4,950 일본 정가(세금 포함)`, 구매 가격 `₩54,000 추정 · 일본 세전 ×12`, 수정 폼 placeholder `추정 ₩54,000`(브랜드 바꾸면 따라 바뀜), 위시 카드 `추정 ₩…`, 총 구매액/예상 합계 `정가 기준 N개 · 추정 M개 포함`. `hidePurchase`·엑셀(직접 입력만)·"구매 정보 빈 칸"(직접 입력 기준)은 그대로.
- 내 컬렉션(131개 보유, 직접 입력 가격 0개) 영향: 연결 25개 = 몰 정가 14 + **추정 새로 적용 11** (브랜드 제외 0, 엔화도 없음 0). 총 구매액 **₩734,400 → ₩1,412,400** (+₩678,000). 11개는 대부분 건담베이스 한정(클리어·코팅 등)이라 실제 국내 판매가와 다를 수 있다.
- 테스트: pytest `tests/test_price_estimate.py`(식·상수 일치·저장소 카탈로그 일치율 ≥95%), node(식·브랜드 제외·합계·실데이터 일치율), e2e 264개(정가 줄·합계·placeholder·브랜드 제외·hidePurchase).
