# 신규 브랜드 크롤링 인수인계서 (2026-09-01)

다른 AI 모델(또는 사람)이 이 문서만 보고 크롤러를 작성할 수 있도록, 대상 브랜드 전부에 대해
**크롤링 주소·요청 방법·파싱 구조를 실제 요청으로 검증**해서 정리한 문서다.
아래 URL·셀렉터·응답 구조는 전부 2026-09-01에 curl/브라우저로 직접 확인한 것이다.

## 0. 공통 규칙 (반드시 지킬 것)

- **재사용**: `scripts/crawl_common.py`의 `fetch()`(UA·SSL 폴백 내장), `num()`, `clean()`,
  `extract_nutrients()`, `write_csv()`를 그대로 쓴다. 새 fetch/정규화 코드를 만들지 말 것.
  기존 크롤러 예시는 `scripts/crawl_viable_brands.py` 참조.
- **산출물**: `data/<brand>.csv`, 스키마는 `crawl_common.STANDARD_COLUMNS`
  (`restaurant,menu_name,menu_category,weight_g,price_krw,calorie_kcal,protein_g,sugar_g,saturated_fat_g,sodium_mg,caffeine_mg,nutrition_basis`),
  인코딩 utf-8-sig. `write_csv()`를 쓰면 자동으로 맞는다.
- **DB 반영**: 새 CSV는 `scripts/load_data.py`의 `FILES` 매핑에 등록해야 DB에 들어간다(등록 안 하면 조용히 누락).
- **값 규칙**: "-"·빈값은 0이 아니라 미공개 → 빈칸 유지(`num()`이 처리). 영양소가 하나도 없는 행은 버린다(`has_any_nutrient`).
- **예의**: 요청 간 0.3~0.5초 지연. User-Agent는 `crawl_common.DESKTOP_UA`.
- **검증**: 크롤링 후 (1) 행 수가 아래 명시한 기대 규모와 비슷한지 (2) kcal 최솟값/최댓값이 상식적인지
  (음료 0~700, 빵 100~600) (3) 같은 메뉴명 중복이 의도된 것인지(HOT/ICE 등) 확인하고 결과를 보고할 것.

---

## 1. 파리바게뜨 (신규, 우선순위 1)

- **왜 쉬움**: WordPress 사이트. 상세페이지가 완전 서버 렌더링이라 JS 불필요.
- **상품 목록 (JS 없이)**: `https://www.paris.co.kr/product-sitemap.xml`
  — `<loc>` 519개가 전 상품 상세 URL. 목록 페이지(`/products/?cat1=...`)는 JS 주입이라 **쓰지 말 것**.
  slug가 URL 인코딩된 한글이므로 **재인코딩 없이 그대로** 요청한다.
- **상세 페이지 파싱** (예: `/product/cream-cheese-pretzel/`):
  - 이름: `h1.product-name` ("크림치즈 프레즐")
  - 영양: `div.product-info-group.product-nutrition` 안 `.product-info-group-description`의 `<p>` 2개:
    - `총 내용량: 55g · 총 내용량당 칼로리(kcal): 160`
    - `총 내용량당 - 나트륨(mg): 390 · 당류(g): 3 · 포화지방(g): 2.6 · 단백질(g): 4`
    - 정규식으로 `라벨(단위): 값` 쌍 추출. `extract_nutrients()`로도 잡히는 포맷.
  - 알레르기(선택): `div.product-info-group.product-allergy`
- **매핑**: 총 내용량→`weight_g`, `nutrition_basis`는 빈칸(내용량당=1회 제공 관례). 가격 없음(앱 링크만). 카테고리 정보는 sitemap에 없음 → 빈칸.
- **함정**: 영양 블록이 없는 상품(케이크·상품권류)이 섞여 있음 → 블록 없으면 건너뛰기. 519회 요청이니 지연 필수.
- **기대 규모**: 영양 있는 상품 300~500개.

## 2. 메가커피 (신규, 우선순위 1)

- **엔드포인트 (검증됨)**:
  `GET https://mega-mgccoffee.com/menu/menu.php?page={n}&menu_category1=&menu_category2=&category=&list_checkbox_all=`
  - **카테고리 파라미터는 전부 빈 값으로** 보내야 전체 메뉴가 나온다. `menu_category1=1`처럼 값을 넣으면 빈 템플릿(366B)이 온다.
  - 페이지당 20개, 응답 하단 `board_page_last`의 `data-page` 속성이 마지막 페이지(2026-09-01 기준 **12**).
    하드코딩하지 말고 `data-page`를 읽어서 1..last 순회.
- **파싱 (li 하나당)** — 카드와 모달이 중복돼 같은 항목이 두 번 나옴 → `cont_text_title` 기준 dedupe:
  - 이름: `.cont_text_title b` (예: `복숭아 퐁당 요거트 스무디`)
  - HOT/ICE: `.cont_gallery_list_label` 텍스트
  - 컵용량: `.cont_text_inner` 중 `컵용량 : 591ml` 텍스트 (ml라서 `weight_g`엔 넣지 않음)
  - 열량: `.cont_text_inner` 중 `1회 제공량 506.8kcal`
  - 나머지: `.cont_list_small ul li` 텍스트 — `포화지방 0.1g` / `당류 0.0g` / `나트륨 11.7mg` / `단백질 1.3g` / `카페인 181.6g`
    - **함정**: 카페인 단위가 `g`로 표기돼 있으나 실제 값은 **mg** (아메리카노 181.6 → mg가 맞음). 그대로 mg로 기록.
  - 알레르기(선택): `.cont_text_info`
- **매핑**: `nutrition_basis` 빈칸(1회 제공량 기준). 가격 없음.
- **기대 규모**: 12페이지 × 20 ≈ 230개(중복 제거 후).

## 3. 컴포즈커피 (신규 발견 — 이전 조사가 틀렸음, 우선순위 1)

이전 대장에 "js_rendered·영양정보 없음"으로 기록돼 있었으나 **오판**. 상세페이지가 서버 렌더링이고
영양정보가 **8종+카페인**까지 있다(탄수화물·지방 포함 — 샐러디급으로 항목이 많음). curl만으로 전부 수집 가능.

- **카테고리 목록 (검증됨)** — `https://composecoffee.com/index1` 상단 nav에서 추출한 `category_srl`:
  | srl | 카테고리 |
  |---|---|
  | 301298 | 추천메뉴 (다른 카테고리와 중복 → **건너뛰거나 dedupe**) |
  | 303364 | 커피·콜드브루 |
  | 303365 | 베버리지 |
  | 303366 | 프라페·스무디 |
  | 303367 | 밀크쉐이크 |
  | 303368 | 에이드·주스 |
  | 303369 | 티 |
  | 308857 | 푸드·디저트 |
  | 303371 | 아이스크림 |
- **목록**: `GET https://composecoffee.com/index.php?mid=compose&act=dispCafemenuGalleryList&category_srl={srl}&page={n}`
  — 페이지당 20개, `page=2` 링크가 응답에 있으면 다음 페이지 존재. 항목 링크 형식:
  `...act=dispCafemenuGalleryItem&category_srl={srl}&item_srl={item_srl}`
- **상세**: 위 `dispCafemenuGalleryItem` URL을 그대로 GET.
  - 이름: `h1.cafemenu-detail-title#detailTitle` (예: `에스프레소`)
  - 영양: `.cafemenu-nutrition-item` 반복 — `.cafemenu-nutrition-label`(라벨) + `.cafemenu-nutrition-value`(값, 안쪽 `.cafemenu-nutrition-unit`은 단위).
    확인된 value id: `capacity`(용량), `calories`, `carbohydrates`, `sugars`, `protein`, `fat`, `saturated_fat`, `sodium`, 커피류엔 `caffeine`.
    **id로 찍지 말고 label 텍스트→컬럼 매핑**(`match_nutrient`)으로 파싱할 것(리뉴얼 내성).
  - 알레르기(선택): `.cafemenu-allergen-list`
- **매핑**: 탄수화물·지방은 STANDARD_COLUMNS에 없음 → 수집하려면 `write_csv(extra_columns=("carb_g","fat_g"))` +
  load_data.py 등록까지 같이. 아니면 버려도 됨(현재 샐러디만 보유한 항목). `nutrition_basis` 빈칸. 가격 없음.
- **기대 규모**: 카테고리 8개(추천 제외) × 1~3페이지 ≈ 150~250개.

## 4. 설빙 (신규 발견 — 이전 조사가 틀렸음, 우선순위 1)

이전 대장에 "메뉴 이름만 나열, 영양정보 없음"으로 기록돼 있었으나 **오판**(목록 페이지만 보고 판정).
상세페이지 `menu_view.php`가 완전 서버 렌더링 PHP이고 영양정보 5종 + 알레르기가 인라인으로 있다. curl만으로 수집 가능.

- **목록 (검증됨)**: `https://sulbing.com/menu/?type={설빙|음료|사이드}` — type 파라미터는 한글(URL 인코딩해서 요청).
  각 목록에 `menu_view.php?menu={id}` 링크가 그대로 들어 있음(기본 페이지 기준 33개). 3개 type 전부 돌면서 id 수집 후 dedupe.
- **상세**: `GET https://sulbing.com/menu/menu_view.php?menu={id}` (예: 157 = 오레오초코컵설빙)
  - 이름: `.productTitle`
  - 영양: `ul.infomation` 안 `li` — `.title`이 `영양정보`인 li의 `.con` 텍스트:
    `열량(Kcal) 355 | 당류(g) 42 | 단백질(g) 10 | 포화지방(g) 7 | 나트륨(mg) 130`
    — 파이프 구분 한 줄. `extract_nutrients()`로 잡히는 포맷.
  - 알레르기(선택): `.title`이 `알레르기 정보`인 li의 `.con` (`우유 · 대두 · 밀`)
- **매핑**: `menu_category` = type 값(설빙/음료/사이드). `nutrition_basis` 빈칸(1컵/1잔 기준). 가격·중량 없음.
- **기대 규모**: 3개 카테고리 합쳐 40~80개.

## 5. 에그드랍 (신규 발견 — 이전 조사가 틀렸음, 우선순위 1)

이전 대장에 "사이트 다운(SSL 실패)"으로 기록돼 있었으나 **도메인이 틀렸던 것**: `eggdrop.co.kr`(죽음)이 아니라
**`eggdrop.com`**이 실서비스 도메인이다. 완전 서버 렌더링 PHP + 표준 `<table>`이라 가장 파싱하기 쉬운 축에 속한다.

- **목록 (검증됨)**: `https://eggdrop.com/menu/list.php?category={cat}`
  — 카테고리 7개: `NEW`, `SANDWICH`, `BAGEL`, `BRUNCH`, `SET MENU`, `SIDE`, `DRINK, COFFEE`
  (공백·쉼표 포함이므로 **URL 인코딩** 필수). 각 목록에 `view.php?seq={seq}` 링크가 인라인.
  NEW는 다른 카테고리와 중복 가능 → seq 기준 dedupe.
- **상세**: `GET https://eggdrop.com/menu/view.php?seq={seq}` (예: 225 = BRIOCHE)
  - 이름: `header h2`(영문명) + 바로 아래 `p`(한글명) → menu_name은 한글명 우선
  - 영양: 표준 `<table>` — thead에 `중량/열량/당/단백질/포화지방/나트륨/카페인`, tbody `함량` 행에 값
    (예: 40 / 103kcal / 1.2g / 3.6g / 1.2g / 108.0mg / 0). `parse_table()` + `row_from_headers()`가 그대로 먹는 구조.
  - 알레르기(선택): 영양정보 표 아래 접힘 섹션
- **매핑**: 중량→`weight_g`, `menu_category` = category 값. `nutrition_basis` 빈칸(1개 제공량 기준). 가격 없음.
- **함정**: `/menu/` 디렉터리는 아파치 인덱스 노출(list.php·view.php·도쿄메뉴 PDF가 그대로 보임) — 목록 진입점은 반드시 `list.php`.
- **기대 규모**: 카테고리 7개 합쳐 40~80개.

## 6. 뚜레쥬르 (신규 발견 — 이전 조사가 틀렸음, 우선순위 1)

이전 대장에 "사이트 다운"으로 기록돼 있었으나 **접속 방법 문제**: `https://www.tlj.co.kr`(www 필수)는 정상.
ASP 사이트, **EUC-KR 인코딩**(`fetch(url, encoding="euc-kr")` 필수 — utf-8로 읽으면 조용히 모지바케).

- **카테고리**: `/inc/js/menu.js`(역시 EUC-KR)의 `MenuInfo` 배열에 전체 맵. 빵 계열(검증됨):
  `/product/list.asp?ref=2&cg_num={11 간식빵|12 식빵|13 건강빵|14 조리빵|15 파이·패스트리|16 도넛·고로케}`.
  케이크·음료 등 다른 ref 값은 list.asp 페이지의 카테고리 nav에서 수집.
- **목록 → id**: 목록의 `viewDetail('5165')` 링크에서 prod_num 수집.
- **상세 (검증됨)**: `GET /product/detail.asp?prod_num={id}` — `div.table_nutrition table`:
  `총중량(g) 105` / `1회 제공량(개) 1` / `열량(kcal)` / `당류(g/%)` / `단백질(g/%)` / `포화지방(g/%)` / `나트륨(mg/%)`
  값이 `값/퍼센트` 병기라도 `num()`이 첫 숫자만 뽑으므로 그대로 사용 가능. 알레르기: `tr.is-allergy td`.
- **매핑**: 총중량→`weight_g`, `nutrition_basis` 빈칸(1회 제공량 기준). 가격 없음(매장 상품).
- **함정**: 영양표 없는 상품(케이크류 추정) 존재 가능 → `has_any_nutrient` 필터.

## 7. 폴바셋 (신규 발견 — 이전 조사가 틀렸음, 우선순위 1)

이전 대장에 "사이트 다운"으로 기록돼 있었으나 **도메인 착오**: `paulbassett.co.kr`(죽음)이 아니라
**`www.baristapaulbassett.co.kr`**. 루트는 JS 리다이렉트로 `/Index.pb`.

- **목록 (검증됨)**: `GET /menu/List.pb?cid1={A|B|C|D|E}` (+`cid2` 서브카테고리, cid1=A에만 상품 56개).
  아이템은 `goView('PB183714')` 형태 → dpid 수집. (cid1 5개만 돌면 되는지 cid2까지 돌아야 하는지는 개수 대조로 확인)
- **상세 (검증됨)**: `GET /menu/View.pb?dpid={PBxxxxxx}` — 원래 POST form이지만 **GET 쿼리로도 동작 확인됨**.
  `ul li`: `span.tit`(라벨) + `span.num`(값) — `열량(kcal) 30 / 당류(g) 0.4 / 나트륨(mg) 1 / 단백질(g) 1.3 / 포화지방(g) 0.1 / 카페인(mg) 308`.
  아이스크림·푸드류는 제공량(g) 표기가 추가된다는 주석이 소스에 있음.
- **매핑**: `nutrition_basis` 빈칸. 가격 없음.
- **기대 규모**: 100~200개.

## 8. 파파존스 (신규 발견 — 유일하게 Playwright 필요, 하지만 1페이지로 전 제품)

이전 대장에 "사이트 다운"으로 기록돼 있었으나 **도메인 이전**: `papajohns.co.kr`(https 죽음, http는 리다이렉트)이 아니라
**`https://pji.co.kr`**. Next.js 사이트이고 영양 데이터는 서버액션(POST + next-action 해시)으로 오기 때문에
해시가 배포마다 바뀌어 curl 재현이 취약 — **Playwright로 탭 클릭 스크레이핑** 권장. 대신 요청 수가 극단적으로 적다:

- **방법 (검증됨)**: 아무 메뉴 상세(예: `https://pji.co.kr/menu/pizza/1000`) 접속 →
  화면 가장자리의 세로 고정 버튼 **'영양 정보 · 원산지 정보 · 알레르기 유발 재료'** 클릭(모달 열림) →
  모달 탭 `원산지 | 영양성분 | 알레르기 유발성분` 중 **영양성분** 클릭 →
  서브탭 `피자 | 사이드 | 음료 | 소스 | 세트`를 순회하며 테이블 스크레이핑. **모달 하나에 전 제품이 들어있음.**
- **테이블 컬럼 (검증됨)**: 제품명 / 구분(사이즈 R·L·F·P, 도우) / 총 열량 범위(Kcal) / 총 중량(g)(총 제공 횟수) /
  1회 제공량(g)(기준 조각수) / 열량(Kcal) / 당류(g) / 단백질(g) / 포화지방(g) / 나트륨(mg)
  예: `수퍼 파파스 | L 오리지널 | 1043~2918 | 778(4) | 195(2) | 468 | 8 | 21 | 8 | 1030`
- **매핑**: 사이즈·도우 조합별 행이 여러 개 → `menu_name`을 "수퍼 파파스(L·오리지널)"식으로 병기.
  1회 제공량→`weight_g`, `nutrition_basis` 빈칸(1회 제공량=조각 기준). 가격은 메뉴 목록/상세에 사이즈별로 있음(예: L 28,500원) —
  단 크롤 시점의 상시가격인지 확인 필요.
- **함정**: 제품명에 rowspan처럼 첫 행에만 이름이 있고 이후 행은 사이즈만 있는 구조 — 이전 행의 이름을 carry-forward 할 것.

## 9. 한솥도시락 (부분 — 열량·가격·알레르기만, 우선순위 낮음)

이전 대장에 "가격만 있고 영양정보 없음"으로 기록돼 있었으나 **상세페이지에 열량이 있다**(단, 다른 영양소는 없음).

- **목록**: 목록은 JS 렌더링 — 데이터 API `POST /api/menu/menu_list/{cate1}/{cate2}`는 curl에 403(WAF, 쿠키로도 안 뚫림).
  → **Playwright로 목록 페이지(`/menu/menu_list`) 1회 로드** 후 `onclick="goDetail(cate1, cate2, idx)"` 파라미터를 전부 수집.
- **상세 (curl 가능, 검증됨)**: `GET https://www.hsd.co.kr/menu/menu_view/{idx}?cate1={c1}&cate2={c2}` —
  `div.menu_info.quantity`에 `열량` 제목 + `<p><span>904.3</span>Kcal</p>`, `div.menu_info.allergy`에 알레르기. 가격도 페이지에 있음.
- **한계**: 열량 단독이라 diet_score 채점 불가. 가격+열량 데이터로서만 가치. 수집 여부는 선택.

## 10. 신전떡볶이 (부분 — 선택 사항, 우선순위 최하)

- **주소 (검증됨)**: `https://www.sinjeon.co.kr/doc/menu01.php` ~ `menu06.php` (서버 렌더링 HTML).
  nav는 JS `GoPage()`지만 실제 URL은 위 고정 경로라 직접 GET 하면 됨.
- **있는 것**: `li.cars` 안 `<span>`=메뉴명, `<em>` 안 열량 텍스트(`순한맛 139kcal<br>매운맛 137kcal` 또는 `152kcal`).
- **한계**: **열량만** 있고(나트륨·당류 등 전무), kcal이 있는 항목도 menu03~06에 걸쳐 **30개 남짓**. 나머지는 이미지 메뉴판.
  diet_score 채점에 필요한 다른 영양소가 없어 **수집 가치가 낮음** — 요청받은 경우에만 진행.

---

## 11. 크롤링 제외 확정 (재조사하지 말 것 — 전부 2026-09-01 상세페이지 수준까지 실확인)

| 브랜드 | 사유 (증거) |
|---|---|
| KFC | 영양정보가 이미지 1장: 푸터 '영양정보표 및 원산지 정보' 클릭 시 `https://www.kfckorea.com/nas/kfcimg/info/info_nutrition.png` 로드. 텍스트 크롤링 불가. (가격만은 `POST https://www.kfckorea.com/kfc/interface/selectDeliveryList`로 가능 — 영양 필드는 전부 빈 문자열인 것 확인) |
| 이삭토스트 | 메뉴 구조는 열림: 목록 `menu.php?ptype=list&catcode=10101000`(토스트)/`10101100`(세트)/`10101200`(사이드)/`10101300`(음료), 상세 `menu.php?ptype=view&prdcode={code}`. 그러나 상세에 재료 구성만 있고 **영양·가격 전무**. `/menu/` 디렉터리 403은 WAF가 아니라 인덱스 차단이었음 |
| 처갓집양념치킨 | 프로모션 스플래시는 `https://www.cheogajip.co.kr/bbs/board.php?bo_table=menu` 직접 접근으로 우회 가능하나, 메뉴판에 **영양·가격 전무**("영양 간식"이라는 광고문구 2건뿐) |
| 굽네치킨 | 상세의 '조리 전 중량/원산지/영양성분 및 알레르기' 링크(`/menu/menu_info?itemId={id}`)까지 확인 — 실제로는 **중량·원산지·알레르기만 있고 영양성분 값 없음** |
| 네네치킨 | 상세 `https://nenechicken.com/home_menu_detail.asp?no={n}&subid={s}&GUBUN=MENU`까지 확인 — 영양 키워드 0 |
| 피자헛 | 메뉴 경로가 `/menu/pizza/best` 등으로 개편됨. 목록·상세·주문 플로우 전부에서 영양 키워드 0 (가격만 있음) |
| 노랑통닭 | 도메인 정정: `norangtongdak.co.kr`(살아있음). 상세 `/menu/chicken_view.html?mode=VIEW_FORM&p_no={n}&p=1&s_p_type=A`에 **가격·조리 전 중량·알레르기는 있음**(curl 가능, BBQ와 같은 유형). 그러나 열량·나트륨 등 영양성분 값은 상세·`/about/`(원산지·알레르기·중량 안내) 어디에도 없음 — 영양 기준으로만 제외. 가격·중량 데이터가 나중에 필요해지면 이 URL로 수집 가능 |
| 푸라닭 | 도메인 정정: `puradakchicken.com`(살아있음). 목록 `/menu/product.asp?sermode={n}`, 상세 `view.asp?idx={n}`까지 확인 — 영양·가격 전무 |
| 죠스떡볶이 | 도메인 정정: 브랜드 사이트는 `jawstopokki.co.kr`(WordPress, 살아있음). `/menu/` 페이지에 영양 키워드 0 (이미지 갤러리) |
| 슬로우캘리 | 도메인 정정: `www.slowcalorie.com`(살아있음)은 본사·프랜차이즈 안내 사이트 — 메뉴/영양 데이터 자체가 없음 |
| 투썸플레이스 | 영양정보가 공지사항 JPG 1장 (기존 확인) |
| 맘스터치·노브랜드버거 | 이미지 공개/빈 팝업 (기존 확인) |
| BBQ·본죽 계열·미스터피자·프랭크버거 | 사이트는 정상이나 영양정보 미공개 (기존 확인) |
| 쉐이크쉑·타코벨 | 대체 도메인(shakeshack.co.kr / tacobell.kr 등)까지 전부 접속 불가 — 진짜 다운 |

## 12. 작업 순서 제안

1. `scripts/crawl_viable_brands.py`에 `crawl_parisbaguette` / `crawl_megacoffee` / `crawl_composecoffee` / `crawl_sulbing` / `crawl_eggdrop` / `crawl_tlj` / `crawl_paulbassett` 함수 추가 (기존 함수 패턴 따르기). 파파존스·한솥은 Playwright가 필요하므로 별도 스크립트(예: `scripts/crawl_browser_brands.py`)로 분리해도 됨.
2. 각각 실행 → `data/parisbaguette.csv`, `data/megacoffee.csv`, `data/composecoffee.csv`, `data/sulbing.csv`, `data/eggdrop.csv`, `data/tlj.csv`, `data/paulbassett.csv`, `data/papajohns.csv` (+선택: `hsd_calorie.csv`) 생성.
3. `scripts/load_data.py` FILES에 생성한 파일 전부 등록.
4. `data/brand_survey.csv`의 해당 행 status를 adopted로, notes에 실측 행 수 기록.
5. 0번 공통 규칙의 검증 3종 결과 보고.
