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

## 4. 신전떡볶이 (부분 — 선택 사항, 우선순위 최하)

- **주소 (검증됨)**: `https://www.sinjeon.co.kr/doc/menu01.php` ~ `menu06.php` (서버 렌더링 HTML).
  nav는 JS `GoPage()`지만 실제 URL은 위 고정 경로라 직접 GET 하면 됨.
- **있는 것**: `li.cars` 안 `<span>`=메뉴명, `<em>` 안 열량 텍스트(`순한맛 139kcal<br>매운맛 137kcal` 또는 `152kcal`).
- **한계**: **열량만** 있고(나트륨·당류 등 전무), kcal이 있는 항목도 menu03~06에 걸쳐 **30개 남짓**. 나머지는 이미지 메뉴판.
  diet_score 채점에 필요한 다른 영양소가 없어 **수집 가치가 낮음** — 요청받은 경우에만 진행.

---

## 5. 크롤링 제외 확정 (재조사하지 말 것 — 전부 2026-09-01 실확인)

| 브랜드 | 사유 (증거) |
|---|---|
| KFC | 영양정보가 이미지 1장: 푸터 '영양정보표 및 원산지 정보' 클릭 시 `https://www.kfckorea.com/nas/kfcimg/info/info_nutrition.png` 로드. 텍스트 크롤링 불가. (가격만은 `POST https://www.kfckorea.com/kfc/interface/selectDeliveryList`로 가능 — 영양 필드는 전부 빈 문자열인 것 확인) |
| 이삭토스트 | 메뉴 구조는 열림: 목록 `menu.php?ptype=list&catcode=10101000`(토스트)/`10101100`(세트)/`10101200`(사이드)/`10101300`(음료), 상세 `menu.php?ptype=view&prdcode={code}`. 그러나 상세에 재료 구성만 있고 **영양·가격 전무**. `/menu/` 디렉터리 403은 WAF가 아니라 인덱스 차단이었음 |
| 처갓집양념치킨 | 프로모션 스플래시는 `https://www.cheogajip.co.kr/bbs/board.php?bo_table=menu` 직접 접근으로 우회 가능하나, 메뉴판에 **영양·가격 전무**("영양 간식"이라는 광고문구 2건뿐) |
| 투썸플레이스 | 영양정보가 공지사항 JPG 1장 (기존 확인) |
| 맘스터치·노브랜드버거 | 이미지 공개/빈 팝업 (기존 확인) |
| BBQ·굽네·네네·한솥·본죽 계열·미스터피자·피자헛·설빙·프랭크버거 | 사이트는 정상이나 영양정보 미공개 (기존 확인) |
| 쉐이크쉑·타코벨·뚜레쥬르·죠스떡볶이·에그드랍·슬로우캘리·노랑통닭·푸라닭·폴바셋·파파존스 | 사이트 자체 다운 (국내 IP 실크롬으로 최종 확인) |

## 6. 작업 순서 제안

1. `scripts/crawl_viable_brands.py`에 `crawl_parisbaguette` / `crawl_megacoffee` / `crawl_composecoffee` 함수 추가 (기존 함수 패턴 따르기).
2. 각각 실행 → `data/parisbaguette.csv`, `data/megacoffee.csv`, `data/composecoffee.csv` 생성.
3. `scripts/load_data.py` FILES에 3개 등록.
4. `data/brand_survey.csv`의 해당 행 status를 adopted로, notes에 실측 행 수 기록.
5. 0번 공통 규칙의 검증 3종 결과 보고.
