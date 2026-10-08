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
- [ ] 4a-2 catalog.js 순수 로직 (정규화·검색·URL 파싱·로더·채우기) + node 테스트
- [ ] 4a-3 로딩 연결 + 공식 사진(카드·상세·hideOfficialPhotos 설정)
- [ ] 4a-4 폼/상세 "반다이 제품에서 찾기"·연결/해제·URL 붙여넣기·공식 대표 사진
- [ ] 4a-5 e2e(mock) + 실제 데이터 검색 샘플 20개 + 방문자 화면 확인 → 보고

## 다음에 할 일
4a-2 시작.
