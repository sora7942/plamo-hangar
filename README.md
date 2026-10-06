# 프라 격납고 (plamo-hangar)

내 프라모델(건프라·걸프라) 컬렉션과 위시리스트를 관리하는 사이트. GitHub Pages(`docs/`)로 서비스하고,
소유자는 사이트에서 직접 추가·수정·삭제·사진 업로드를 하며 저장할 때마다 이 저장소에 커밋이 하나 생긴다.
요구사항과 진행 순서는 [SPEC.md](SPEC.md), 작업 규칙은 [CLAUDE.md](CLAUDE.md).

> **현재: SPEC 12장 1단계(이전) 완료.** 크롤러·카탈로그·신제품 탭은 2단계 이후에 추가된다.

## 1. GitHub Pages 켜기 (최초 1회)

1. 저장소 **Settings → Pages**
2. **Build and deployment → Source: Deploy from a branch**
3. **Branch: `main` / 폴더: `/docs`** → Save
4. 1~2분 뒤 `https://sora7942.github.io/plamo-hangar/` 가 열린다 (`docs/.nojekyll`이 있어서 `_`로 시작하는 폴더도 그대로 서빙된다)

## 2. 쓰기용 토큰 만들기 (소유자만, fine-grained)

1. GitHub 우측 위 프로필 → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
2. **Token name**: `plamo-hangar` 등 / **Expiration**: 90일 정도(만료되면 같은 방법으로 새로 만든다)
3. **Resource owner**: 본인 계정
4. **Repository access → Only select repositories → `plamo-hangar` 하나만**
5. **Permissions → Repository permissions → Contents: `Read and write`** (Metadata: Read-only는 자동으로 붙는다. 다른 권한은 주지 않는다)
6. **Generate token** → 화면에 한 번만 보이는 `github_pat_…` 값을 복사

## 3. 사이트에서 쓰기

- 사이트 맨 아래 **소유자 설정** 링크 → 토큰 붙여넣기 → **연결**. 연결되면 `+ 추가`, `가져오기`, `엑셀 백업`, `설정` 버튼이 나타난다.
- 토큰은 **그 브라우저의 localStorage에만** 저장된다. 서버로 보내지 않고(GitHub API 호출의 `Authorization` 헤더로만 사용), 화면에 다시 보여주지도 않는다. 공용 PC에서는 쓰지 말고, 쓰고 나면 설정 → **토큰 지우기**.
- **저장 1번 = 커밋 1개** (`collection: 추가 …`, `collection: 3개 일괄 수정` 같은 메시지). 사진이 있으면 사진 파일도 같은 커밋에 들어간다. 저장 후 **사이트 반영까지 1~2분** 걸린다. 소유자 화면의 목록은 GitHub API에서 바로 읽으므로 지연 없이 보이지만, 방문자는 Pages 파일을 본다. 사진 파일도 Pages 경로로 읽기 때문에, 저장 직후 **새로고침**하면 반영 전까지는 사진이 자리표시로 보일 수 있다(저장한 그 화면에서는 바로 보인다).
- 소유자 판정(`permissions.push`)은 **계정** 권한 기준이라 토큰 권한이 모자라도 소유자 버튼이 보일 수 있다. 그 경우 저장할 때 "토큰에 이 저장소의 Contents: Read and write 권한이 있는지 확인해 주세요"가 뜬다 — 토큰 권한을 다시 확인한다.
- 다른 기기나 크롤러(2단계부터)가 먼저 저장했다면: `data/collection.json`이 **안 바뀌었으면** 조용히 최신 위에 다시 저장하고, **바뀌었으면** "최신 내용 위에 다시 적용할까요?"를 묻는다.
- 사진: 긴 변 1600px WebP + 480px 썸네일로 줄여 `docs/photos/<프라ID>/`에 올린다. 한 프라에 20장까지, 순서 변경·삭제·**대표 사진** 지정 가능. 이미지는 내 사진만 저장소에 들어가고 공식 이미지·남의 사진은 저장하지 않는다.
- 이전 버전(v2)에서 옮기기: 가져오기에 v2 엑셀 백업(.xlsx) 또는 v2 데이터(JSON, 사진 포함)를 넣는다. v2 JSON의 사진(data URI)은 WebP 파일로 바뀌어 올라간다.

### 주의: 공개 저장소
저장소가 공개라서 `docs/data/collection.json`의 구매일·구매처·가격은 누구나 볼 수 있다. 설정의 "구매정보 숨기기"는 **화면에서만** 가린다. 꼭 비공개여야 하는 정보는 적지 않는다.

## 4. 로컬에서 보기·테스트

```powershell
conda activate plamo
python -m http.server -d docs 8000        # http://localhost:8000  (토큰이 없으면 방문자 화면)

node tests/site_pure.test.mjs             # 순수 함수 (사진 순서·대표, 중복 판정, 일괄 수정, 가져오기 …)
node tests/site_github.test.mjs           # GitHub 저장 로직을 가짜 GitHub으로 (한 커밋, 충돌·재시도, 권한 오류)
python tests/e2e/site_mock_check.py       # Playwright: 가짜 GitHub으로 추가·수정·삭제·사진·일괄 수정 확인 + 스크린샷(tests/e2e/out/)
```

- 위 테스트들은 **실제 토큰·실제 저장소를 쓰지 않는다.** `tests/helpers/fake-github.js`가 메모리에서 GitHub API를 흉내 낸다. 앱 코드에는 mock 모드가 없다 (Playwright가 `add_init_script`로 `api.github.com` 요청만 가로챈다).
- e2e는 Google Fonts·cdnjs(SheetJS)에 실제로 접속한다. 오프라인이면 엑셀 백업 확인만 건너뛴다.

## 5. 구조

```
docs/                 GitHub Pages 루트 (Deploy from a branch: main /docs)
  index.html          CSP 메타 + 진입점 (인라인 스크립트 없음)
  app.js              화면
  pure.js             순수 함수 (DOM·네트워크 없음)
  github.js           GitHub API 클라이언트 (소유자 판정·읽기·한 커밋 저장)
  style.css  favicon.svg  .nojekyll
  data/collection.json  내 보유·위시 (사이트가 쓴다)
  photos/<kitId>/       내 사진 (사이트가 쓴다)
tests/                node 테스트, fake-github, Playwright 확인
reference/artifact-v2.html   옮기기 전 원본 (수정하지 않는다)
spike/                0단계 검증 결과 (보존)
```
