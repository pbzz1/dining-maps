# 프론트엔드 (Vite + React)

FastAPI가 정적 파일까지 서빙하던 구조에서 분리해 나온 독립 프론트엔드.

## 실행

백엔드를 먼저 띄우고:

```bash
python -m uvicorn app.main:app --reload
```

프론트엔드를 띄운다:

```bash
npm install        # 최초 1회
npm run dev        # http://localhost:5173
```

## 왜 분리했나

이전에는 `app/main.py`에서 `StaticFiles`로 `frontend/`를 `/`에 마운트했다. 프로토타입 단계에선
합리적이었지만(빌드 단계가 없고 same-origin이라 CORS도 불필요), 두 가지 문제를 실제로 겪었다.

**1. 캐시 무효화를 손으로 관리해야 했다.** `app.js`를 고쳐도 브라우저가 옛날 파일을 계속 캐싱해서
새 기능이 아예 실행되지 않았다. 원인 찾는 데 시간을 썼고, 결국 `index.html`에
`app.js?v=3` → `?v=4` → `?v=5` 식으로 버전 쿼리를 박고 **파일을 고칠 때마다 숫자를 손으로 올려야
했다.** Vite는 빌드 시 파일명에 해시를 붙여(`index-0B231-kh.js`) 이 문제를 없앤다. 개발 중에는
HMR로 저장 즉시 반영된다.

**2. 파일 하나가 1,000줄을 넘었다.** `app.js` 443줄 + `style.css` 485줄에 지도·목록·메뉴·필터·
정렬·팝업이 전부 들어 있었고, 모듈 시스템이 없어 전역 변수로 상태를 관리했다. 실제로 같은 스코프에
`const sel`을 두 번 선언해 에러가 난 적도 있다.

## 구조

```
src/
  api.js              모든 API 호출 (베이스 URL 한 곳에서 관리)
  constants.js        등급 색상/라벨, 정렬 옵션, 포맷 헬퍼
  useKakaoMap.js      카카오맵 SDK 로드 + 지도 인스턴스 훅
  App.jsx             화면 전환 (지도 / 매장목록 / 메뉴상세)
  components/
    MapView.jsx        지도 + 필터 + 거리순 매장 리스트 + 팝업
    RestaurantList.jsx 브랜드 카드
    MenuView.jsx       메뉴 목록 + 정렬 + 영양정보
    GradeBadges.jsx    절대/상대 등급 배지, 범례
```

## API 연결 방식

개발 중에는 Vite dev server가 `/api/*`를 FastAPI(`127.0.0.1:8000`)로 프록시한다
(`vite.config.js`). 브라우저 입장에선 same-origin이라 CORS preflight가 없다.

배포 시에는 정적 파일이 별도 호스트에서 서빙되므로 실제로 cross-origin 요청이 된다. 그래서
`app/main.py`에 `CORSMiddleware`를 추가했고, 허용 origin은 `ALLOWED_ORIGINS` 환경변수로 지정한다
(기본값은 localhost:5173).

## 환경변수 (`.env`)

| 변수 | 용도 |
|---|---|
| `VITE_KAKAO_JS_KEY` | 카카오맵 JavaScript 키 |
| `VITE_API_BASE` | API 오리진. 개발 중엔 비워두면 프록시를 탄다 |

Vite는 `VITE_` 접두사가 붙은 변수만 브라우저에 노출한다. 즉 여기 넣은 값은 **번들에 그대로
포함되어 사용자에게 보인다** — 카카오 JS 키는 원래 도메인 제한으로 보호하는 공개 키라 문제없지만,
서버용 비밀키(REST API 키 등)는 절대 여기 넣으면 안 된다.

## 빌드

```bash
npm run build      # dist/ 생성 (gzip 약 64KB)
```

## 기존 `frontend/` 폴더

바닐라 JS로 만든 원래 프론트엔드가 `frontend/`에 남아 있다. FastAPI가 더 이상 서빙하지 않으므로
**동작하지 않는 상태**이며, 참고용으로만 남겨뒀다. 정리해도 무방하다.
