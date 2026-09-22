# 검색 유입 · 수익화 설정

코드는 전부 들어가 있고, 값이 비어 있으면 해당 요소만 빠진 채 배포된다.
아래는 **콘솔에서 사람이 해야 하는 일**과 그 값을 어디에 넣는지다.

## 1. 검색엔진 등록 (가장 먼저)

정적 페이지는 `frontend-react/scripts/build-static-pages.mjs`가 빌드 때마다 굽는다.

| 경로 | 내용 | 수 |
|---|---|---|
| `/brand/<브랜드>/<메뉴>/` | 메뉴 1개 = 1페이지. "빅맥 칼로리" 검색의 착지점. JSON-LD `MenuItem`+`NutritionInformation` | 약 4,700 |
| `/brand/<브랜드>/`, `/brand/` | 브랜드 영양성분표, 목차 | 27 |
| `/best/<목표>/<분류>/`, `/best/` | 다이어트·고단백·저나트륨 × 버거·치킨·피자… 랭킹 | 15 |
| `/data/` | 데이터셋 안내 + 샘플 CSV + 문의 (`VITE_CONTACT_EMAIL` 있을 때만) | 1 |
| `sitemap.xml` | sitemap index → `sitemap-pages.xml` + 브랜드별 `sitemap-menus-<id>.xml` | |

1. [Google Search Console](https://search.google.com/search-console) → 속성 추가 → **URL 접두어** → HTML 태그 → `content` 값을 GitHub secret `VITE_GOOGLE_SITE_VERIFICATION`에.
2. [네이버 서치어드바이저](https://searchadvisor.naver.com) → 사이트 등록 → HTML 태그 → `content` 값을 `VITE_NAVER_SITE_VERIFICATION`에.
3. `deploy` 워크플로를 수동 실행(또는 master push)해 메타가 실린 채 배포 → 두 콘솔에서 소유 확인 → `sitemap.xml` 제출.

색인에는 몇 주가 걸린다. 첫 4주는 서치콘솔의 "노출이 1 이상인 페이지 수"만 보면 된다.

## 2. 쿠팡 파트너스

도메인 소유를 요구하지 않아 지금 주소로도 된다.

1. [partners.coupang.com](https://partners.coupang.com) 가입, 사이트 URL 등록.
2. 링크 생성 → 검색어(예: "닭가슴살 샐러드")의 검색 결과 또는 상품 → 단축 URL 복사.
3. `frontend-react/src/affiliate.json`의 해당 `url`에 붙여 넣고 커밋. 빈 `url`은 렌더링되지 않는다.

노출 위치는 메뉴 페이지 하단, 랭킹 페이지 하단, 앱의 맞춤 추천 결과 아래 — 세 곳뿐이다. 수치·등급 사이에는 넣지 않는다.
고지문은 블록 안에 고정돼 있다. Open API로 자동화하지 않은 이유는 `affiliate.json` 머리말 참고.

## 3. 후원 링크 · 데이터 문의

- `VITE_DONATE_URL` — 토스 송금 링크 등. About 화면과 정적 페이지 푸터.
- `VITE_CONTACT_EMAIL` — 있으면 `/data/` 페이지가 생긴다. **공개 페이지에 그대로 노출되는 주소**다.

## 4. 애드센스 (커스텀 도메인 이후)

애드센스는 `*.cloudfront.net`을 승인하지 않는다. 도메인을 붙인 뒤:

1. CloudFront 대체 도메인 + ACM 인증서(us-east-1), 카카오 개발자 콘솔에 새 도메인 등록, `ALLOWED_ORIGINS`·`FRONTEND_URL` 갱신.
2. 옛 주소 색인을 옮기려면 CloudFront 함수(`dining-maps-index`)에서 Host가 `*.cloudfront.net`이면 새 도메인으로 301.
3. 신청 전: `/privacy/`가 떠 있는지 확인(심사 거절 흔한 사유). `VITE_ADSENSE_CLIENT`를 넣으면 처리방침에 AdSense 국외 이전·광고 쿠키 문단이 자동으로 붙는다.
4. 승인 후 `VITE_ADSENSE_CLIENT`(`ca-pub-…`) → 자동 광고 스크립트와 `ads.txt`가 생긴다. `VITE_ADSENSE_SLOT`까지 넣으면 고정 단위(`AdSlot`)도 그려진다.

## 5. 측정 (GA4 이벤트)

| 이벤트 | 뜻 |
|---|---|
| `static_page_view` (`page_type`: menu/brand/best/…) | 정적 페이지 조회. SPA의 `page_view`와 분리 |
| `deeplink_from_seo` | 정적 페이지 → 앱(지도·추천) 진입 |
| `affiliate_click` (`slot`, `label`) | 제휴 링크 클릭 |
| `donate_click` | 후원 링크 클릭 |

## 비용 메모

배포마다 HTML 약 4,800개(50MB)를 S3에 올린다. `aws s3 sync`는 크기·수정시각으로 비교해서 매번 전부 다시 올라가고, 시드니 리전 PUT 단가로 월 1달러 안쪽이다. 거슬리면 내용 해시 매니페스트로 바뀐 파일만 올리게 바꿀 수 있다.
