"""브랜드별 영양정보·가격 확보 가능성 조사 대장 생성/갱신 스크립트.

새 브랜드를 조사 대상에 넣으려면 PROBE_TARGETS에 (카테고리, 후보 URL들)을
추가하고 이 스크립트를 다시 실행하면 된다. data/brand_survey.csv가 갱신된다.

자동 프로브의 한계:
  서버 렌더링 페이지는 HTML에 영양 키워드가 그대로 보이므로 자동 판정이 되지만,
  JS로 렌더링하는 사이트(버거킹·KFC·교촌 등)는 HTML만 봐서는 알 수 없다. 그런
  브랜드는 브라우저로 직접 확인한 결과를 MANUAL_FINDINGS에 적어두고, 자동
  프로브 결과보다 우선 적용한다. 즉 이 파일은 "자동 조사 + 수동 확인"의 병합
  결과다. 자세한 배경은 docs/brand_survey.md 참고.

    python scripts/survey_brands.py
"""
import concurrent.futures
import csv
import ssl
import urllib.request
from datetime import date
from pathlib import Path

# 국내 프랜차이즈 사이트 중 인증서 체인이 불완전한 곳이 많아, 검증 실패 시
# 한 번 더 검증 없이 시도한다. 공개 페이지를 읽기만 하는 조사용 스크립트이고
# 여기서 얻은 데이터를 신뢰 경계 안으로 들이지 않기 때문에 허용 가능한 수준으로 판단했다.
# (실제 크롤러를 만들 때는 브랜드별로 인증서 문제를 따로 확인할 것)
_UNVERIFIED_CTX = ssl.create_default_context()
_UNVERIFIED_CTX.check_hostname = False
_UNVERIFIED_CTX.verify_mode = ssl.CERT_NONE

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "brand_survey.csv"

NUTRITION_KEYWORDS = ["열량", "kcal", "Kcal", "칼로리", "나트륨", "단백질", "당류", "포화지방", "영양성분", "영양정보"]
PRICE_KEYWORDS = ["가격", "원)", "price", "prc"]

# 브라우저로 직접 확인한 결과. 자동 프로브보다 우선한다.
# status: adopted(이미 파이프라인에 포함) / viable(확보 가능) / rejected(불가) / unknown(재조사 필요)
MANUAL_FINDINGS = {
    "맥도날드": dict(
        category="버거", status="adopted", nutrition="Y", nutrition_format="json_api",
        nutrients="열량,단백질,당류,포화지방,나트륨,카페인", price="N",
        source="https://www.mcdonalds.co.kr/api/v1/kor/product/nutrition",
        notes="공식 API. price 필드는 있으나 179개 전부 null이고 메뉴 페이지에도 가격 표기 없음",
    ),
    "롯데리아": dict(
        category="버거", status="adopted", nutrition="Y", nutrition_format="server_html",
        nutrients="열량,단백질,당류,포화지방,나트륨,카페인", price="N",
        source="https://www.lotteeatz.com/upload/stg/etc/ria/items.html",
        notes="정적 HTML 영양성분표. rowspan/colspan 처리 필요",
    ),
    "맘스터치": dict(
        category="버거", status="adopted", nutrition="partial", nutrition_format="image",
        nutrients="열량,단백질,당류,포화지방,나트륨", price="N",
        source="공지사항 영양성분 이미지(PNG)",
        notes="영양정보가 이미지로만 공개되어 자동 크롤링 불가. 버거류만 수동 전사",
    ),
    "서브웨이": dict(
        category="샌드위치", status="adopted", nutrition="Y", nutrition_format="server_html",
        nutrients="열량,단백질,당류,포화지방,나트륨", price="N",
        source="https://www.subway.co.kr/menuView/sandwich?menuItemIdx=",
        notes="상품별 상세페이지 순회. 일부 ID는 500 에러",
    ),
    "샐러디": dict(
        category="샐러드", status="adopted", nutrition="Y", nutrition_format="server_html",
        nutrients="열량,탄수화물,당류,단백질,지방,포화지방,나트륨", price="N",
        source="https://salady.com/menu/view_1?idx=",
        notes="유일하게 탄수화물·지방까지 공개. 단 중량(g) 정보는 없음",
    ),
    "스타벅스": dict(
        category="커피", status="viable", nutrition="Y", nutrition_format="server_html",
        nutrients="열량,단백질,당류,포화지방,나트륨,카페인", price="N",
        source="https://www.starbucks.co.kr/menu/drink_view.do?product_cd=",
        notes="음료 207개 확인. Tall 사이즈 기준. 서버 렌더링이라 curl 크롤링 가능",
    ),
    "버거킹": dict(
        category="버거", status="viable", nutrition="Y", nutrition_format="json_api",
        nutrients="열량,단백질,당류,포화지방,나트륨,중량", price="Y",
        source="POST https://www.burgerking.co.kr/burgerking/BKR0632.json (목록) / BKR0634.json (상세)",
        notes="조사한 브랜드 중 영양정보와 가격(dineInprc)을 함께 제공하는 유일한 사례",
    ),
    "BHC": dict(
        category="치킨", status="viable", nutrition="Y", nutrition_format="server_html",
        nutrients="열량,당류,단백질,포화지방,나트륨", price="N",
        source="https://www.bhc.co.kr/menu/chicken.asp",
        notes="서버 렌더링 <table>. 롯데리아와 유사한 구조",
    ),
    "이디야": dict(
        category="커피", status="viable", nutrition="Y", nutrition_format="server_html",
        nutrients="열량,단백질,당류,포화지방,나트륨,카페인", price="N",
        source="https://www.ediya.com/contents/drink.html",
        notes="목록 페이지 HTML에 dl/dt/dd로 인라인 표기. 상세페이지 순회 불필요",
    ),
    "포케올데이": dict(
        category="샐러드", status="viable", nutrition="Y", nutrition_format="server_html",
        nutrients="열량,나트륨,탄수화물,당류,단백질,지방,콜레스테롤,포화지방산,트랜스지방", price="N",
        source="https://pokeallday.co.kr/nutrition_info",
        notes="조사 브랜드 중 영양소 항목이 가장 많음(9종). 콜레스테롤·트랜스지방까지 공개",
    ),
    "교촌치킨": dict(
        category="치킨", status="unknown", nutrition="partial", nutrition_format="js_rendered",
        nutrients="열량,당류,단백질,포화지방,나트륨", price="Y",
        source="https://m.kyochon.com/menu/menu_view?product_id=",
        notes="100g당 표기. 값이 비어있는 항목이 많음(예: 반반한마리는 열량·나트륨만). 권장소비자가격 표기 있음",
    ),
    "KFC": dict(
        category="버거", status="unknown", nutrition="unknown", nutrition_format="js_rendered",
        nutrients="", price="Y",
        source="https://www.kfckorea.com/menu/detail/N/{id}",
        notes="주문 페이지라 가격 표시됨(예: 복버켓 16,400). '영양정보표 및 원산지 정보' 링크가 있으나 내용 미확인 - 재조사 필요"
              " (2026-09-01, 실 크롬 재확인: 홈 화면 메뉴 카드 클릭이 배송지 미설정 때문인지 상세로 안 넘어감. "
              "홈 화면 자체엔 영양 키워드 없음. 주소 입력 후 주문 플로우를 타야 하는 것으로 보임 - 재조사 필요)",
    ),
    "메가커피": dict(
        category="커피", status="rejected", nutrition="N", nutrition_format="none",
        nutrients="", price="N",
        source="https://www.mega-mgccoffee.com/menu/",
        notes="메뉴 페이지에 이름·영문명·설명만 존재. 별도 영양 페이지 경로도 전부 404",
    ),
    "투썸플레이스": dict(
        category="커피", status="rejected", nutrition="N", nutrition_format="image",
        nutrients="", price="N",
        source="https://www.twosome.co.kr/co/annoDetail.do?annoSeqNo=1404",
        notes="2026-09-01: 공지사항에 '음료 열량 및 알레르기 유발 성분 안내(2026.09.01 ver)'가 있으나 "
              "내용이 JPG 이미지(nutrient_260901.jpg) 한 장 -- 노브랜드버거·맘스터치와 같은 이미지 공개 유형, "
              "텍스트 크롤링 불가. 실 크롬(사용자 PC)으로 재확인 완료",
    ),
    "노브랜드버거": dict(
        category="버거", status="rejected", nutrition="N", nutrition_format="none",
        nutrients="", price="N",
        source="https://www.nobrandburger.com/menu/menuList.do",
        notes="영양성분 팝업 링크(shinsegaefood.com/popup/nobrandburger_02.html)가 718바이트 빈 페이지",
    ),
    "굽네치킨": dict(
        category="치킨", status="rejected", nutrition="N", nutrition_format="none",
        nutrients="", price="Y",
        source="https://www.goobne.co.kr/menu/menu_list",
        notes="가격은 있으나 영양정보 없음",
    ),
    "한솥도시락": dict(
        category="한식", status="rejected", nutrition="N", nutrition_format="none",
        nutrients="", price="Y",
        source="https://www.hsd.co.kr/menu/menu_list",
        notes="권장가격 표기는 있으나 영양정보 없음",
    ),
    "본도시락": dict(
        category="한식", status="rejected", nutrition="N", nutrition_format="none",
        nutrients="", price="Y",
        source="https://www.bonif.co.kr/brand/menu?brdCd=BF104",
        notes="2026-09-01(실 크롬 재확인): 가격은 메뉴 카드에 다 있으나(예: 본메추리알장조림 4,900원) "
              "페이지 전체에 열량/kcal/나트륨/단백질/알레르기 키워드가 하나도 없음. 항목 클릭해도 상세 안 열림",
    ),
    "슬로우캘리": dict(
        category="샐러드", status="unknown", nutrition="unknown", nutrition_format="unknown",
        nutrients="", price="unknown",
        source="slowcalorie.co.kr",
        notes="도메인 연결 거부 (2026-09-01 실 크롬(사용자 PC) 재확인: 국내 IP에서도 동일하게 에러 페이지 -- "
              "지역 차단이 아니라 사이트 자체가 내려간 것으로 최종 확인. 도메인 자체가 살아있는지부터 재확인 필요)",
    ),
    "에그드랍": dict(
        category="샌드위치", status="unknown", nutrition="unknown", nutrition_format="unknown",
        nutrients="", price="unknown",
        source="eggdrop.co.kr",
        notes="SSL 인증서 검증 실패 (2026-09-01 실 크롬(사용자 PC) 재확인: 국내 IP에서도 동일하게 에러 페이지 -- "
              "지역 차단이 아니라 사이트 자체가 내려간 것으로 최종 확인)",
    ),
    "BBQ": dict(
        category="치킨", status="rejected", nutrition="N", nutrition_format="none",
        nutrients="", price="Y",
        source="https://www.bbq.co.kr/categories/17",
        notes="2026-09-01: 메뉴 목록 페이지 찾음(가격·조리전 중량 표기 있음, 예: 황금올리브치킨 23,000원/10호 951~1050g). "
              "영양정보 링크·페이지는 못 찾음",
    ),
    # -------------------------------------------------------------------
    # 2026-09-01 브랜드 조사 대장 전수 재조사 (30개: unknown 25 + rejected 5).
    # 1차: 이 세션 자체 IP(한국 밖)로 curl/브라우저 -- 다수 사이트가 connection
    # refused로 막힘. 2차: Claude in Chrome으로 사용자 PC(국내 IP)의 실제
    # 크롬을 직접 조작해 동일 URL 재확인 -- 그런데도 여전히 에러 페이지인 곳들은
    # 지역 차단이 아니라 사이트 자체가 다운된 것으로 최종 확인됐다(notes에 명시).
    # -------------------------------------------------------------------
    "설빙": dict(
        category="디저트", status="rejected", nutrition="N", nutrition_format="none",
        nutrients="", price="N",
        source="https://sulbing.com/menu",
        notes="메뉴 이름만 나열, 가격·영양정보·상세페이지 링크 전혀 없음",
    ),
    "쉐이크쉑": dict(
        category="버거", status="unknown", nutrition="unknown", nutrition_format="unknown",
        nutrients="", price="unknown",
        source="https://www.shakeshack.kr/menu/",
        notes="2026-09-01 실 크롬(사용자 PC, 국내 IP) 재확인: 여전히 에러 페이지 -- 지역 차단이 아니라 "
              "사이트 자체가 다운된 것으로 최종 확인",
    ),
    "타코벨": dict(
        category="버거", status="unknown", nutrition="unknown", nutrition_format="unknown",
        nutrients="", price="unknown",
        source="https://www.tacobell.co.kr/menu/",
        notes="2026-09-01 실 크롬(사용자 PC, 국내 IP) 재확인: 여전히 에러 페이지 -- 지역 차단이 아니라 "
              "사이트 자체가 다운된 것으로 최종 확인",
    ),
    "프랭크버거": dict(
        category="버거", status="rejected", nutrition="N", nutrition_format="none",
        nutrients="", price="N",
        source="https://frankburger.co.kr",
        notes="본사 브랜드 소개 페이지만 있고 실제 메뉴/영양정보 사이트로 가는 링크가 죽어있음(클릭 안 됨)",
    ),
    "뚜레쥬르": dict(
        category="베이커리", status="unknown", nutrition="unknown", nutrition_format="unknown",
        nutrients="", price="unknown",
        source="https://tlj.co.kr/menu/menu_list",
        notes="2026-09-01 실 크롬(사용자 PC, 국내 IP) 재확인: 루트 도메인까지 여전히 에러 페이지 -- "
              "지역 차단이 아니라 사이트 자체가 다운된 것으로 최종 확인. 파리바게뜨(경쟁사)가 "
              "상품 상세페이지에 영양정보를 서버 렌더링으로 공개하니, 사이트가 복구되면 뚜레쥬르도 "
              "비슷한 구조일 가능성 있어 재조사 가치는 있음",
    ),
    "파리바게뜨": dict(
        category="베이커리", status="viable", nutrition="Y", nutrition_format="server_html",
        nutrients="열량,나트륨,당류,포화지방,단백질", price="unknown",
        source="https://www.paris.co.kr/product/{slug}/",
        notes="상품 상세페이지에 '영양정보' 섹션이 curl로도 그대로 잡힘(JS 불필요, 완전 서버 렌더링) - "
              "예: 감자쫀떡(1개입) 38g/160kcal/나트륨140mg/당류13g/포화지방5g/단백질2g, 알레르기 정보도 같이 있음. "
              "단 목록 페이지(/products/?cat1=...)는 상품 링크가 JS로 주입돼 curl로는 안 보임 -- "
              "브라우저 1회로 slug 목록만 수집하면(카테고리별 42개 안팎) 이후 상세페이지는 requests만으로 충분",
    ),
    "신전떡볶이": dict(
        category="분식", status="unknown", nutrition="unknown", nutrition_format="js_rendered",
        nutrients="", price="unknown",
        source="https://www.sinjeon.co.kr",
        notes="2026-09-01 실 크롬 재확인: 옛 URL(/menu)은 호스팅사 404였지만 루트 도메인은 정상 - 사이트는 "
              "살아있음. 메뉴 nav가 실제 링크가 아니라 JS onclick(GoPage('menu03'))이라 클릭해도 페이지 전환이 "
              "안 잡힘 - 개발자도구로 GoPage() 함수가 실제로 이동시키는 URL을 추적해야 함",
    ),
    "죠스떡볶이": dict(
        category="분식", status="unknown", nutrition="unknown", nutrition_format="unknown",
        nutrients="", price="unknown",
        source="https://jawstteokbokki.com/menu",
        notes="2026-09-01 실 크롬(사용자 PC, 국내 IP) 재확인: 여전히 에러 페이지 -- 지역 차단이 아니라 "
              "사이트 자체가 다운된 것으로 최종 확인",
    ),
    "이삭토스트": dict(
        category="샌드위치", status="unknown", nutrition="unknown", nutrition_format="unknown",
        nutrients="", price="unknown",
        source="https://www.isaac-toast.co.kr/menu",
        notes="403 Forbidden (봇 차단으로 추정, connection refused와 다름 -- 사이트는 살아있음) - "
              "일반 브라우저 User-Agent/헤더로 재조사 필요",
    ),
    "네네치킨": dict(
        category="치킨", status="rejected", nutrition="N", nutrition_format="none",
        nutrients="", price="N",
        source="https://nenechicken.com",
        notes="메인 페이지에 영양정보 관련 링크·언급 전혀 없음",
    ),
    "노랑통닭": dict(
        category="치킨", status="unknown", nutrition="unknown", nutrition_format="unknown",
        nutrients="", price="unknown",
        source="https://www.norangtongdak.com/menu",
        notes="2026-09-01 실 크롬(사용자 PC, 국내 IP) 재확인: 여전히 에러 페이지 -- 지역 차단이 아니라 "
              "사이트 자체가 다운된 것으로 최종 확인",
    ),
    "처갓집양념치킨": dict(
        category="치킨", status="unknown", nutrition="unknown", nutrition_format="unknown",
        nutrients="", price="unknown",
        source="https://www.cheogajip.co.kr",
        notes="2026-09-01 실 크롬 재확인: 루트 도메인이 오늘 날짜(2026.09.01) 가맹점 프로모션 스플래시 "
              "페이지(intro.html)로 고정되어 있고 '홈페이지로 이동' 링크를 눌러도 같은 페이지로만 돎 - "
              "실제 메뉴 사이트로 못 들어감. 프로모션이 끝나면 재조사",
    ),
    "푸라닭": dict(
        category="치킨", status="unknown", nutrition="unknown", nutrition_format="unknown",
        nutrients="", price="unknown",
        source="https://www.puradak.com/menu",
        notes="2026-09-01 실 크롬(사용자 PC, 국내 IP) 재확인: 여전히 에러 페이지 -- 지역 차단이 아니라 "
              "사이트 자체가 다운된 것으로 최종 확인",
    ),
    "컴포즈커피": dict(
        category="커피", status="unknown", nutrition="unknown", nutrition_format="js_rendered",
        nutrients="", price="unknown",
        source="https://composecoffee.com/index1",
        notes="2026-09-01 실 크롬 재확인: 사이트는 정상(브랜드 홈페이지 index1 확인). 상단 nav의 MENU가 "
              "호버로 펼쳐지는 JS 드롭다운이라 클릭만으론 하위 메뉴 URL을 못 얻음 - 마우스오버 후 "
              "펼쳐진 링크를 따라가야 함",
    ),
    "폴바셋": dict(
        category="커피", status="unknown", nutrition="unknown", nutrition_format="unknown",
        nutrients="", price="unknown",
        source="https://www.paulbassett.co.kr/menu/menuList",
        notes="2026-09-01 실 크롬(사용자 PC, 국내 IP) 재확인: 여전히 에러 페이지 -- 지역 차단이 아니라 "
              "사이트 자체가 다운된 것으로 최종 확인",
    ),
    "미스터피자": dict(
        category="피자", status="rejected", nutrition="N", nutrition_format="none",
        nutrients="", price="N",
        source="https://www.mrpizza.co.kr/menu",
        notes="메뉴 이름 목록만 있고(가격·영양정보 없음) 클릭해도 상세페이지로 안 넘어가는 구식 게시판형 구조",
    ),
    "파파존스": dict(
        category="피자", status="unknown", nutrition="unknown", nutrition_format="unknown",
        nutrients="", price="unknown",
        source="http://www.papajohns.co.kr/menu/",
        notes="2026-09-01 실 크롬(사용자 PC, 국내 IP) 재확인: 여전히 에러 페이지 -- 지역 차단이 아니라 "
              "사이트 자체가 다운된 것으로 최종 확인",
    ),
    "피자헛": dict(
        category="피자", status="rejected", nutrition="N", nutrition_format="none",
        nutrients="", price="unknown",
        source="https://www.pizzahut.co.kr/menu/list",
        notes="메뉴 페이지에 영양정보 관련 내용 없음",
    ),
    "본죽": dict(
        category="한식", status="rejected", nutrition="N", nutrition_format="none",
        nutrients="", price="Y",
        source="https://www.bonif.co.kr/brand/menu?brdCd=BF101",
        notes="2026-09-01(실 크롬 재확인): 가격은 메뉴 카드에 다 있으나(예: 전복죽 13,000원) 전체 페이지에 "
              "열량/kcal/나트륨/단백질/알레르기 키워드가 하나도 없음. 항목 클릭해도 상세 안 열림",
    ),
    "본죽&비빔밥": dict(
        category="한식", status="rejected", nutrition="N", nutrition_format="none",
        nutrients="", price="unknown",
        source="https://www.bonif.co.kr/brand/menu?brdCd=BF102",
        notes="2026-09-01(실 크롬 재확인): 본죽·본도시락과 같은 bonif.co.kr 메뉴판 구조. "
              "열량/kcal/나트륨/단백질/알레르기 키워드 전혀 없음",
    ),
}

# 자동 프로브 대상. 브랜드를 늘리려면 여기에 추가한다.
PROBE_TARGETS = {
    # --- 피자 ---
    "도미노피자": ("피자", ["https://web.dominos.co.kr/contents/ingredient",
                       "https://web.dominos.co.kr/contents/deliveryIngredient",
                       "https://www.dominos.co.kr/goods/list?dsp_ctgr=001"]),
    "피자헛": ("피자", ["https://www.pizzahut.co.kr/menu/list", "https://www.pizzahut.co.kr/footer/nutrition",
                     "https://www.pizzahut.co.kr/nutrition"]),
    "미스터피자": ("피자", ["https://www.mrpizza.co.kr/menu/menuList.do", "https://www.mrpizza.co.kr/menu",
                       "https://www.mrpizza.co.kr/customer/nutrition.do"]),
    "파파존스": ("피자", ["https://www.papajohns.co.kr/menu/", "https://www.papajohns.co.kr/nutrition",
                      "https://papajohns.co.kr/menu"]),
    # --- 커피 ---
    "컴포즈커피": ("커피", ["https://composecoffee.com/menu", "https://composecoffee.com/menu/list",
                       "https://www.composecoffee.com/menu"]),
    "빽다방": ("커피", ["https://paikdabang.com/menu/", "https://paikdabang.com/menu/menu_coffee/"]),
    "할리스": ("커피", ["https://www.hollys.co.kr/menu/espresso.do", "https://www.hollys.co.kr/menu/index.do"]),
    "커피빈": ("커피", ["https://www.coffeebeankorea.com/menu/list.asp", "https://www.coffeebeankorea.com/menu",
                     "https://www.coffeebeankorea.com/menu/menu.asp"]),
    "폴바셋": ("커피", ["https://www.paulbassett.co.kr/menu/menuList", "https://www.paulbassett.co.kr/menu",
                     "https://www.paulbassett.co.kr/Menu/List"]),
    # --- 베이커리·디저트 ---
    "파리바게뜨": ("베이커리", ["https://www.paris.co.kr/menu/", "https://www.paris.co.kr/products/",
                         "https://www.paris.co.kr/nutrition/"]),
    "뚜레쥬르": ("베이커리", ["https://www.tlj.co.kr/menu/menu_list", "https://www.tlj.co.kr/product",
                        "https://www.tlj.co.kr/menu/nutrition"]),
    "배스킨라빈스": ("디저트", ["https://www.baskinrobbins.co.kr/menu/view.php?seq=7",
                         "https://www.baskinrobbins.co.kr/menu/list.php",
                         "https://www.baskinrobbins.co.kr/menu/nutrition.php"]),
    "설빙": ("디저트", ["https://sulbing.com/menu/menu.php", "https://sulbing.com/menu",
                     "https://www.sulbing.com/menu"]),
    # --- 치킨 ---
    "네네치킨": ("치킨", ["https://nenechicken.com/menu/", "https://nenechicken.com/17_new/menu.asp",
                      "https://www.nenechicken.com/menu"]),
    "푸라닭": ("치킨", ["https://www.puradak.com/menu", "https://puradak.com/menu",
                     "https://www.puradak.com/brand/menu"]),
    "처갓집양념치킨": ("치킨", ["https://www.cheogajip.co.kr/menu", "https://www.cheogajip.co.kr/menu/menuList",
                          "https://cheogajip.co.kr/menu"]),
    "노랑통닭": ("치킨", ["https://www.norangtongdak.com/menu", "https://norangtongdak.com/menu"]),
    # --- 버거 ---
    "프랭크버거": ("버거", ["https://frankburger.co.kr/menu", "https://www.frankburger.co.kr/menu",
                       "https://frankburger.co.kr/sub/menu.php"]),
    "쉐이크쉑": ("버거", ["https://www.shakeshack.kr/menu/", "https://shakeshack.kr/menu",
                      "https://www.shakeshack.kr/nutrition/"]),
    "타코벨": ("버거", ["https://www.tacobell.co.kr/menu/", "https://www.tacobell.co.kr/menu/menuList",
                     "https://tacobell.co.kr/menu"]),
    # --- 분식·한식 ---
    "신전떡볶이": ("분식", ["https://www.sinjeon.co.kr/menu", "https://sinjeon.co.kr/menu",
                       "https://www.sinjeon.co.kr/bbs/menu.php"]),
    "죠스떡볶이": ("분식", ["https://jawstteokbokki.com/menu", "https://www.jawsfood.com/menu",
                       "https://www.jawstteokbokki.com/menu"]),
    "본죽": ("한식", ["https://www.bonif.co.kr/bonjuk/menu", "https://www.bonjuk.co.kr/menu",
                    "https://www.bonif.co.kr/brand/bonjuk"]),
    "이삭토스트": ("샌드위치", ["https://www.isaac-toast.co.kr/menu", "https://isaac-toast.co.kr/menu"]),
    "본죽&비빔밥": ("한식", ["https://www.bonif.co.kr/bonjukbibimbap/menu"]),
}


def fetch(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as e:
        if not isinstance(getattr(e, "reason", None), ssl.SSLError):
            raise
        resp = urllib.request.urlopen(req, timeout=timeout, context=_UNVERIFIED_CTX)

    with resp:
        raw = resp.read()
        status = resp.status
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            return status, raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return status, raw.decode("utf-8", errors="replace")


def probe_brand(brand, category, urls):
    """가능한 URL을 순서대로 시도해 가장 정보가 많은 결과를 채택."""
    best = None
    for url in urls:
        try:
            status, html = fetch(url)
        except Exception as e:
            if best is None:
                best = dict(
                    category=category, status="unknown", nutrition="unknown",
                    nutrition_format="unreachable", nutrients="", price="unknown",
                    source=url, notes=f"접근 실패: {type(e).__name__}",
                )
            continue

        hits = [k for k in NUTRITION_KEYWORDS if k in html]
        price_hits = [k for k in PRICE_KEYWORDS if k in html]
        # 열량/kcal/칼로리는 같은 뜻이라 하나로 묶어 신호 강도를 센다
        strong = len({
            "열량" if k in ("열량", "kcal", "Kcal", "칼로리") else k
            for k in hits
        })

        if strong >= 4:
            verdict = dict(
                category=category, status="viable", nutrition="Y",
                nutrition_format="server_html", nutrients=",".join(hits),
                price="Y" if price_hits else "N", source=url,
                notes=f"자동 프로브: 영양 키워드 {strong}종 검출 (브라우저 확인 권장)",
            )
        elif strong >= 1:
            verdict = dict(
                category=category, status="unknown", nutrition="partial",
                nutrition_format="unknown", nutrients=",".join(hits),
                price="Y" if price_hits else "N", source=url,
                notes=f"자동 프로브: 영양 키워드 일부만({strong}종) 검출 - 수동 확인 필요",
            )
        else:
            verdict = dict(
                category=category, status="unknown", nutrition="unknown",
                nutrition_format="js_rendered?", nutrients="",
                price="Y" if price_hits else "N", source=url,
                notes=f"자동 프로브: 영양 키워드 없음({len(html)}자). JS 렌더링이거나 미공개 - 수동 확인 필요",
            )

        rank = {"viable": 3, "unknown": 1}.get(verdict["status"], 0) + (1 if verdict["nutrition"] == "partial" else 0)
        if best is None or rank > best.get("_rank", -1):
            verdict["_rank"] = rank
            best = verdict

    best.pop("_rank", None)
    return best


def main():
    results = {}

    print(f"자동 프로브 {len(PROBE_TARGETS)}개 브랜드...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {
            ex.submit(probe_brand, b, cat, urls): b
            for b, (cat, urls) in PROBE_TARGETS.items()
        }
        for fut in concurrent.futures.as_completed(futures):
            brand = futures[fut]
            results[brand] = fut.result()

    # 수동 확인 결과가 자동 프로브를 덮어쓴다
    for brand, info in MANUAL_FINDINGS.items():
        results[brand] = dict(info)
        results[brand]["notes"] = "[수동확인] " + results[brand]["notes"]

    today = date.today().isoformat()
    fieldnames = ["brand", "category", "status", "nutrition", "nutrition_format",
                  "nutrients", "price", "source", "notes", "surveyed_at"]
    status_order = {"adopted": 0, "viable": 1, "unknown": 2, "rejected": 3}

    rows = []
    for brand, info in results.items():
        row = {"brand": brand, "surveyed_at": today}
        row.update({k: info.get(k, "") for k in fieldnames if k not in row})
        rows.append(row)
    rows.sort(key=lambda r: (status_order.get(r["status"], 9), r["category"], r["brand"]))

    OUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"\n총 {len(rows)}개 브랜드 -> {OUT_PATH}")
    for s in ["adopted", "viable", "unknown", "rejected"]:
        if s in counts:
            print(f"  {s}: {counts[s]}")

    print("\n영양정보 확보 가능(adopted+viable):")
    for r in rows:
        if r["status"] in ("adopted", "viable"):
            print(f"  {r['brand']:10s} {r['category']:6s} 가격={r['price']}  {r['nutrition_format']}")


if __name__ == "__main__":
    main()
