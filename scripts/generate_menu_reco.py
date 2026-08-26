"""브랜드별 "다이어트 추천 메뉴 + 한 문장 이유"를 Claude로 생성해 brand_menu_reco에 저장.

지도 팝업/매장 카드가 읽는 캐시 테이블이라 런타임엔 LLM 호출이 없다. 크롤/재채점
후에만 다시 돌리면 된다 -- rescore_if_changed.py가 재채점했을 때 자동 호출한다.

환각 방지: structured output의 menu_name을 그 브랜드 실제 메뉴명 enum으로 강제해서
없는 메뉴가 응답에 나올 수 없게 한다. DB의 menu_item_id FK가 이중 안전장치.

ANTHROPIC_API_KEY가 없으면 아무것도 하지 않고 넘어간다 -- 파이프라인(cron)에
키가 아직 없어도 rescore가 실패하지 않게.

    DATABASE_URL=... ANTHROPIC_API_KEY=... python scripts/generate_menu_reco.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.db import connect  # noqa: E402

MODEL = "claude-opus-5"
# ponytail: 브랜드당 score 상위 40개만 후보로 제시 -- 추천은 어차피 상위권에서
# 나오고, enum·프롬프트가 무한정 길어지는 것을 막는다. 전 메뉴 비교가 필요해지면 해제.
CANDIDATE_LIMIT = 40

RECO_SCHEMA = {
    "type": "object",
    "properties": {
        "menu_name": {"type": "string"},  # 브랜드별 enum이 런타임에 채워진다
        "reason": {
            "type": "string",
            "description": "한국어 한 문장, 60자 이내. 영양 수치를 근거로 왜 다이어트에 나은 선택인지.",
        },
    },
    "required": ["menu_name", "reason"],
    "additionalProperties": False,
}


def fetch_candidates(conn, restaurant_id):
    """score 상위 후보 메뉴 + 주요 영양성분. 영양성분은 행으로 저장돼 있어 피벗한다."""
    return conn.execute(
        """SELECT mi.id, mi.name, ds.score, ds.absolute_grade,
                  MAX(CASE WHEN nf.nutrient_name = 'calorie' THEN nf.value END) AS kcal,
                  MAX(CASE WHEN nf.nutrient_name = 'protein' THEN nf.value END) AS protein_g,
                  MAX(CASE WHEN nf.nutrient_name = 'sugar' THEN nf.value END) AS sugar_g,
                  MAX(CASE WHEN nf.nutrient_name = 'sodium' THEN nf.value END) AS sodium_mg
           FROM menu_item mi
           JOIN diet_score ds ON ds.menu_item_id = mi.id
           LEFT JOIN nutrition_fact nf ON nf.menu_item_id = mi.id
           WHERE mi.restaurant_id = %s
           GROUP BY mi.id, mi.name, ds.score, ds.absolute_grade
           ORDER BY ds.score DESC
           LIMIT %s""",
        (restaurant_id, CANDIDATE_LIMIT),
    ).fetchall()


def build_prompt(brand_name, rows):
    lines = [f"| 메뉴명 | kcal | 단백질g | 당류g | 나트륨mg | 점수(0-100) | 등급 |"]
    for r in rows:
        fmt = lambda v: "-" if v is None else f"{v:g}"
        lines.append(
            f"| {r['name']} | {fmt(r['kcal'])} | {fmt(r['protein_g'])} | {fmt(r['sugar_g'])} |"
            f" {fmt(r['sodium_mg'])} | {r['score']:.0f} | {r['absolute_grade']} |"
        )
    return (
        f"다음은 프랜차이즈 '{brand_name}'의 메뉴 영양정보다 (다이어트 점수 상위 {len(rows)}개).\n\n"
        + "\n".join(lines)
        + "\n\n다이어트 중인 사람에게 이 브랜드에서 딱 하나 추천할 메뉴를 골라라. "
        "점수만 따르지 말고 포만감(단백질), 당류, 나트륨, 실제 한 끼로서의 적절성을 함께 봐라. "
        "reason은 한국어 한 문장(60자 이내)으로, 구체적 수치를 한두 개 들어 근거를 말해라."
    )


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY 없음 -- 추천 생성 건너뜀")
        return

    import anthropic  # 키 없는 환경(cron)에서 import 실패로 죽지 않게 지연 import

    client = anthropic.Anthropic()

    with connect() as conn:
        brands = conn.execute(
            """SELECT DISTINCT r.id, r.name FROM restaurant r
               JOIN menu_item mi ON mi.restaurant_id = r.id
               JOIN diet_score ds ON ds.menu_item_id = mi.id
               ORDER BY r.name"""
        ).fetchall()

        ok = 0
        for b in brands:
            rows = fetch_candidates(conn, b["id"])
            if not rows:
                continue
            id_by_name = {r["name"]: r["id"] for r in rows}
            schema = {**RECO_SCHEMA, "properties": {**RECO_SCHEMA["properties"],
                      "menu_name": {"type": "string", "enum": list(id_by_name)}}}
            try:
                resp = client.messages.create(
                    model=MODEL,
                    max_tokens=1024,
                    output_config={"format": {"type": "json_schema", "schema": schema}},
                    messages=[{"role": "user", "content": build_prompt(b["name"], rows)}],
                )
                import json
                reco = json.loads(next(bl.text for bl in resp.content if bl.type == "text"))
            except Exception as e:  # 브랜드 하나 실패가 전체를 막지 않게
                print(f"  {b['name']}: 실패 -- {e}")
                continue

            conn.execute(
                """INSERT INTO brand_menu_reco (restaurant_id, menu_item_id, reason, model, generated_at)
                   VALUES (%s, %s, %s, %s, now())
                   ON CONFLICT (restaurant_id) DO UPDATE
                   SET menu_item_id = EXCLUDED.menu_item_id, reason = EXCLUDED.reason,
                       model = EXCLUDED.model, generated_at = now()""",
                (b["id"], id_by_name[reco["menu_name"]], reco["reason"], MODEL),
            )
            conn.commit()  # 브랜드 단위 커밋 -- 중간에 죽어도 완료분은 남는다
            ok += 1
            print(f"  {b['name']}: {reco['menu_name']} -- {reco['reason']}")

        print(f"{ok}/{len(brands)} 브랜드 추천 생성 완료")


if __name__ == "__main__":
    main()
