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
- [ ] 6-4 2015년 이전 카탈로그 (workflow_dispatch `brand_backfill`, 번역 토큰·비용 보고)
- [ ] 6-3 검색 별칭 docs/aliases.js (미연결 124개 눈 판정 전/후)
- [ ] 6-5 빈 칸 채우기
- [ ] 6-2 연결 도우미
- [ ] (보류) 6-0b 몰 연동 — spike/mall-report.md 참고

## 다음에 할 일
- 5단계 코드·문서 끝. push 후 사용자가: (1) Actions 수동 실행 `discord_test` 켜서 실제 알림 1건 확인(요청할 때만) (2) 다음 날 예약 실행으로 `마지막 관측`·meta 갱신 확인 (3) 이전 Claude 아티팩트 정리 여부 결정.
- 토큰 만료 2027-10-06 (README 4장에 갱신 방법).
