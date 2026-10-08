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

## 다음에 할 일
- 4b 끝. **사용자가 4c(신제품·입고 탭)를 지시하면 시작.** push는 사용자가 한다.
- 4c 메모: `docs/feed.js` 별도 파일(읽기 전용, kits·위시 추가 콜백만 받음). feed.json은 탭을 처음 열 때 로드, 썸네일은 feed.image(6건뿐) 대신 catalogId→카탈로그 images[0](`C.thumbUrl`). 필터: 종류(new/pb-new/kr-restock/kr-new)·라인(건프라/걸프라)·등급. 내 보유·위시와 catalogId 같은 항목은 맨 위 '내 프라' 강조. '위시리스트에 추가'는 catalogId 연결 + `C.fillPatch(fillAll)`. 재판 공백 문구는 `C.gapInfo` 재사용 가능.
- 4d 메모: 크롤러가 collection.json 읽기 전용으로 catalogId 중 카탈로그에 없는 것 상세 받기(`manual:true`, `line:"other"`는 SPEC 4장), 디스코드 내 프라 우선, 엑셀 catalogId 열, 자동 연결 후보, 리뷰 링크
