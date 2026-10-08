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

## 다음에 할 일
- 4c 끝. **사용자가 4d를 지시하면 시작.** push는 사용자가 한다.
- 4d 목록: (사이트) 설정 '자동 연결 후보 보기'(이름·등급·스케일이 확실히 같고 후보 1개일 때만, 저장 1회=커밋 1개), 리뷰 찾아보기 링크(유튜브·네이버 블로그 검색), 엑셀 백업·가져오기 catalogId 열. (크롤러) 디스코드 '내 프라 우선'(collection.json 읽기만), 카탈로그에 없는 catalogId 상세 받기(`manual:true`, `line:"other"`, SPEC 4장 결정; 재분류 건너뜀, 제외 목록 id 되살림).
- 참고: 사용자가 실제 사이트에서 이미 프라 2개를 연결해 둠(collection.json) — e2e는 sanitize 사본 사용.
