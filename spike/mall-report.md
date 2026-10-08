# 6-0 반다이남코코리아몰(bnkrmall.co.kr) spike 결과 (2026-10-09)

요청 **합계 23회**(상한 30; `spike/out/mall-budget.json`): robots.txt 3(프로세스를 다시 띄울 때마다 받은 낭비 포함) · 첫 화면 2 · 검색 11 · 상세 1 · 이미지 4(requests 3 + 브라우저 1) · 카테고리 목록 1 · sitemap 1. (이와 별개로 호비사이트 브랜드 목록 쪽수 확인 12회, 조이하비 링크 파라미터 확인 1회.)
도구: `spike/mall_lib.py`(크롤러와 같은 `HttpClient` 게이트: robots 준수·1.2초 간격·상한 카운터). 본문 캐시는 `spike/out/mall-cache/`(gitignore). robots.txt: `Allow: /`, `Disallow: /nmanager/ /cscenter/ /member/` — 우리가 읽은 경로(`/main/`, `/goods/search.do`, `/goods/category.do`, `/goods/detail.do`)는 모두 허용 범위.

## ① requests로 열리나 — 열린다 (JS 렌더링 아님, JSON 경로 불필요)
- `/` → JS 리다이렉트(`/main/index.do`)지만 `/main/index.do`는 서버 렌더링 HTML.
- 검색: `GET /goods/search.do?sword=<검색어>&searchType=allTotal&pageNum=N` — 결과 `<li data-childno><a class="thumb" href="../goods/detail.do?gno=N">` 안에 이미지(`background-image:url('//cdn…/goods/middle/YYYYMMDD/<hash>.jpg?resize=550&format=webp')`)·`<p class="caption">`(한국 정식 **시리즈명**)·`<h5>`(**한국어 정식 상품명**)·가격. 결과가 없으면 "검색된 결과가 없습니다". 쪽당 20개(예: 34건 중 첫 쪽 20개).
- 카테고리 목록: `GET /goods/category.do?cate=1576&page=N&cateName=건프라&soldout=Y&endGoods=Y` — 쪽당 40개, **건프라는 8쪽(≈320개)**. 다른 카테고리: 애니프라 1577, 토이 1592 등(메인 내비에서).
- 상세: `GET /goods/detail.do?gno=N` — 서버 렌더링.
- 내부 JSON(`/common/ajax/…`)은 POST 전용 추적용이라 쓰지 않는다.

## ② 상세 필드
- `제품명`(예: `HG 건담 에어리얼`), `판매코드`(`G0000058992`, 몰 내부 코드), `모델명` = **JAN 13자리**(`4573102630308`), 가격(hidden input `price`=19200), 제조사 `BANDAI SPIRITS CO.,LTD.`, 제조국 Japan, `발매년월` 칸은 주석 처리돼 비어 있음.
- **BD####### 코드는 없다.** 호비사이트 상세에도 JAN이 없다(`価格·発売日·対象年齢`뿐). → 코드로 연결(kr-arrivals `codeMap` 재사용)은 **불가**. 이름 매칭이 필요하다.

## ③ 이미지
- 호스트 `cdn.bnkrmall.co.kr`. 상품 사진 경로 `/live/data/base/goods/{big,middle}/YYYYMMDD/<32자 hash>.jpg`. 같은 페이지에 리뷰 사진(`/base/review/…`)·상세 설명 이미지(`/base/editor/…`)·배너(`/base/banner/…`)도 있어 **`goods/` 경로만** 상품 사진이다.
- **서명·만료값 없음.** `?resize=550&format=webp` 같은 변환 파라미터만 붙는다(원본 209KB → 550px WebP 16KB). 2022-10-12에 올라간 파일(`Last-Modified: 2022-10-12`)이 지금도 같은 URL로 200 — 4년 가까이 유효했다는 증거. 변환본은 `Cache-Control: max-age=31536000`. (같은 URL을 몇 시간 뒤 다시 받아 보는 확인은 하지 않았다 — 위 증거로 대신.)
- `Access-Control-Allow-Origin: *`, 서버 `GAZEL`(CDN).

## ④ 다른 출처·no-referrer
- Referer 없음 / `Referer: https://sora7942.github.io/…` 둘 다 200, 같은 바이트.
- 일반 Chrome UA의 브라우저에서 `<img referrerpolicy="no-referrer">`로 550×688 WebP가 뜬다(요청 Referer 비어 있음).

## ⑤ 2025년 이후·공식 사진 없는 제품 10개 (일반 유통 `channel=general`, 한정판 제외)
검색어는 우리 번역명에서 뽑은 짧은 한국어 낱말 1개. **0건 ≠ 없음**(표기 차이일 수 있다).

| 카탈로그 | 검색어 | 결과 |
|---|---|---|
| bh-01_6824 HG 류오마루 (2026-01) | 류오마루 | **있음** `HG 류오마루` 39,600원 (업로드 2026-02-06) |
| bh-01_5469 MG 건담 비다르 (2025-03) | 건담 비다르 | **있음** `MG 건담 비다르` 72,000원 (2025-03-28) |
| bh-01_5968 RG 윙 건담 제로 (2025-09) | 윙 건담 제로 | **있음** `RG 윙 건담 제로` 50,400원 |
| bh-01_7109 RG 1/48 잉그램 플러스 (2026-06) | 잉그램 플러스 | **있음** `RG 1/48 AV-98Plus (잉그램 플러스)` 66,000원 |
| bh-01_5487 30MS 옵션 헤어스타일 Vol.11 (2025-03) | 옵션 헤어스타일 파츠 Vol.11 | **있음** `30MS 옵션 헤어 스타일 파츠 Vol.11 전 4종` 28,800원 |
| bh-01_7033 HG 블루티시 독 (2026-06) | 블루티시 독 | 0건 |
| bh-01_5944 HG 1/100 VF-31J 지크프리트 | VF-31J 지크프리트 | 0건 (몰 표기는 `지크프리드`일 가능성) |
| bh-01_7036 HG 1/100 VF-31E 전용 데칼 | VF-31E 지크프리트 | 0건 |
| bh-01_6875 MG 풀 아머 ZZ건담 Ver.Ka (2026-02) | 풀 아머 ZZ건담 | 0건 |
| bh-01_7103 EG 우키요에 패키지 (2026-08) | 우키요에 건담 | 0건 |

→ 5/10 확인. 나머지는 검색어·표기를 바꿔 보아야 안다(구현 때 매처가 철자 변형을 흡수해야 한다).

## 부수 발견
- 카탈로그 `nameKo`에 번역 오류로 한자가 섞인 항목이 있다: `비达르`(bh-01_5469, bh-01_753). 가나 검사는 한자를 못 거른다.
- 몰의 `caption`이 곧 **한국 정식 시리즈명**(`기동전사 건담 수성의 마녀`, `신기동전기 건담W`, `SD건담 월드 히어로즈`)이라 시리즈 번역 검증·교정에 쓸 수 있다.
- 몰의 `제품명`은 한국 정식 상품명이라 `nameKo`(AI 번역)보다 정확하다(조이하비 이름을 쓰던 것과 같은 방식으로 교체 가능).
