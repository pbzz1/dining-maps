"""menu_item.released_at 1회성 백필 -- 보도자료·뉴스 기사에서 확인한 실제 출시일.

크롤 diff(menu_change_log 'added')는 "우리가 처음 본 날"만 알려준다. 이미 DB에
있던 메뉴 중 무엇이 신메뉴인지, 실제로 언제 나왔는지는 웹에 있는 보도자료가
유일한 원천이라 수동 조사 결과를 여기 박제한다 (2026-08-26 조사, 출처는 각 줄).

패턴은 ILIKE (공백 제거 후 부분일치). 이미 값이 있으면 덮어쓰지 않아서 재실행
안전하고, prod에도 그대로 한 번 돌리면 된다:

    DATABASE_URL=... python scripts/pipeline/seed_released_at.py

이후 새로 나오는 메뉴는 크롤 diff가 하루 이내로 잡으므로 이 파일에 추가할
필요 없다 -- 첫 발견일이 충분한 근사치다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from app.db import apply_schema, connect  # noqa: E402

# (브랜드, 메뉴명 패턴[공백 무시 부분일치], 출시일)
SEED = [
    # newspim 2026-08-12 "버거킹, 신제품 '데리야킹 크리스퍼' 출시"
    ("버거킹", "데리야킹크리스퍼", "2026-08-12"),
    # 한국일보 2026-07-28 "버거킹 크루아상위치 상륙" -- 7/30 아침 메뉴 개편
    ("버거킹", "크루아상위치", "2026-07-30"),
    # zdnet 2026-07-09 "bhc 커링클 전 채널 동시 출시"
    ("BHC", "커링클", "2026-07-09"),
    # mtn 2026-07-14 "무진장 슈림프 스테이크 피자 16일부터 전국 판매"
    ("도미노피자", "무진장슈림프스테이크", "2026-07-16"),
    # wowtv 2026-07-31 무신사 협업 사이드 "무진장 치킨 박스"
    ("도미노피자", "무진장치킨박스", "2026-07-31"),
    # 8월 이달의 맛
    ("배스킨라빈스", "산딸기가끌리는연유", "2026-08-01"),
    # 포케올데이 뉴스룸 2026-08-04
    ("포케올데이", "저당갈비덮밥", "2026-08-04"),
    ("포케올데이", "저당제육덮밥", "2026-08-04"),
    # KPI뉴스 2026-05-15 맘스터치 '리프레시' 신메뉴 3종
    ("맘스터치", "한라봉싸이버거", "2026-05-15"),
    # kfenews 2026-01-06 "통다리 크리스피치킨버거 2종 출시"
    ("롯데리아", "통다리크리스피치킨버거", "2026-01-06"),
]

# 메뉴 이미지 (브랜드 공식 CDN, 2026-08-26 각 사이트에서 직접 확인. 핫링크 200 확인).
# 구체적 패턴이 먼저 오도록 정렬 -- image_url IS NULL 가드와 함께 라지세트/세트가
# 기본 패턴에 덮이지 않게 한다. 포케올데이·도미노 치킨박스는 공식 이미지 URL을
# 못 찾아 비워둠 -- 프론트는 이미지 없이 렌더링한다.
BK_IMG = "https://mob-prd.burgerking.co.kr/images/menu/web/thumb"
IMAGE_SEED = [
    ("버거킹", "데리야킹크리스퍼라지세트", f"{BK_IMG}/2026/08/06/a16cf30d-a981-4116-9597-12ed0e76908f.png"),
    ("버거킹", "데리야킹크리스퍼세트", f"{BK_IMG}/2026/08/06/eb7a3e96-2c76-457a-b647-fe0714483209.png"),
    ("버거킹", "데리야킹크리스퍼", f"{BK_IMG}/2026/08/06/d6d2d8aa-7b14-4c60-bb94-0ec8fb14690c.png"),
    ("버거킹", "오믈렛크루아상위치세트", f"{BK_IMG}/2026/07/27/ae64b357-3f2e-4025-8077-49058d247a01.png"),
    ("버거킹", "오믈렛크루아상위치콤보", f"{BK_IMG}/2026/07/27/e29de508-c45b-4f93-9230-c0fad7e3614a.png"),
    ("버거킹", "BLT오믈렛크루아상위치콤보", f"{BK_IMG}/2026/07/27/da8939dc-b1a0-4e73-8cba-d2b04d094e7e.png"),
    ("버거킹", "BLT오믈렛크루아상위치세트", f"{BK_IMG}/2026/07/27/d89387bd-2506-4ce1-88c9-f83f37be2c91.png"),
    ("버거킹", "BLT오믈렛크루아상위치", f"{BK_IMG}/2026/07/27/e3802bf0-5bd4-4da0-ab73-bf162e2239f5.png"),
    ("버거킹", "잠봉햄&치즈오믈렛크루아상위치", f"{BK_IMG}/2026/07/27/af989a08-8f50-4a93-a6a5-c7385272fbee.png"),
    ("버거킹", "잠봉햄&치즈크루아상위치콤보", f"{BK_IMG}/2026/07/27/e4ad65c8-8b27-4add-9478-378539a197f0.png"),
    ("버거킹", "잠봉햄&치즈크루아상위치세트", f"{BK_IMG}/2026/07/27/fa5bcdff-5da5-4ff0-8fca-c6442041c09a.png"),
    ("버거킹", "오믈렛크루아상위치", f"{BK_IMG}/2026/07/27/aca61b90-cfc4-477c-8550-5978f0cc466d.png"),
    ("도미노피자", "무진장슈림프스테이크+랍스터", "https://cdn.dominos.co.kr/admin/upload/goods/20260706_gN8CXaTO.jpg"),
    ("도미노피자", "무진장슈림프스테이크+포테이토", "https://cdn.dominos.co.kr/admin/upload/goods/20260706_aWrcsy8I.jpg"),
    ("도미노피자", "무진장슈림프스테이크", "https://cdn.dominos.co.kr/admin/upload/goods/20260821_BGZcKnxb.jpg"),
    ("배스킨라빈스", "산딸기가끌리는연유", "https://www.baskinrobbins.co.kr/upload/product/main/e97152372159daa503e512f139644e1f.png"),
]


def main() -> None:
    with connect() as conn:
        apply_schema(conn)
        total = 0
        for brand, pattern, date in SEED:
            rows = conn.execute(
                """UPDATE menu_item mi SET released_at = %s
                   FROM restaurant r
                   WHERE r.id = mi.restaurant_id AND r.name = %s
                     AND replace(mi.name, ' ', '') ILIKE %s
                     AND mi.released_at IS NULL
                   RETURNING mi.name""",
                (date, brand, f"%{pattern}%"),
            ).fetchall()
            total += len(rows)
            print(f"  {brand} {pattern} -> {date}: {len(rows)}건")
        print(f"released_at 백필 완료: {total}건")

        img_total = 0
        for brand, pattern, url in IMAGE_SEED:
            rows = conn.execute(
                """UPDATE menu_item mi SET image_url = %s
                   FROM restaurant r
                   WHERE r.id = mi.restaurant_id AND r.name = %s
                     AND replace(mi.name, ' ', '') ILIKE %s
                     AND mi.image_url IS NULL
                   RETURNING mi.name""",
                (url, brand, f"%{pattern}%"),
            ).fetchall()
            img_total += len(rows)
        print(f"image_url 백필 완료: {img_total}건")


if __name__ == "__main__":
    main()
