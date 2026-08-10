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
        notes="주문 페이지라 가격 표시됨(예: 복버켓 16,400). '영양정보표 및 원산지 정보' 링크가 있으나 내용 미확인 - 재조사 필요",
    ),
    "메가커피": dict(
        category="커피", status="rejected", nutrition="N", nutrition_format="none",
        nutrients="", price="N",
        source="https://www.mega-mgccoffee.com/menu/",
        notes="메뉴 페이지에 이름·영문명·설명만 존재. 별도 영양 페이지 경로도 전부 404",
    ),
    "투썸플레이스": dict(
        category="커피", status="rejected", nutrition="N", nutrition_format="none",
        nutrients="", price="N",
        source="https://www.twosome.co.kr/mn/menuInfoList.do",
        notes="PC/모바일 모두 영양정보 노출 없음",
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
        category="한식", status="unknown", nutrition="unknown", nutrition_format="unknown",
        nutrients="", price="unknown",
        source="https://www.bonif.co.kr",
        notes="SSL 인증서 검증 실패로 접근 불가 - 재조사 필요",
    ),
    "슬로우캘리": dict(
        category="샐러드", status="unknown", nutrition="unknown", nutrition_format="unknown",
        nutrients="", price="unknown",
        source="slowcalorie.co.kr",
        notes="도메인 연결 거부 - 정확한 도메인 재확인 필요",
    ),
    "에그드랍": dict(
        category="샌드위치", status="unknown", nutrition="unknown", nutrition_format="unknown",
        nutrients="", price="unknown",
        source="eggdrop.co.kr",
        notes="SSL 인증서 검증 실패 - 재조사 필요",
    ),
    "BBQ": dict(
        category="치킨", status="unknown", nutrition="unknown", nutrition_format="unknown",
        nutrients="", price="unknown",
        source="https://www.bbq.co.kr",
        notes="메뉴 페이지 경로를 찾지 못함(시도한 URL 전부 404) - 재조사 필요",
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
