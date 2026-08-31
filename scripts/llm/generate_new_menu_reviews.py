"""신메뉴별 LLM 리뷰(다이어트 판정 + 예상 맛)를 생성해 new_menu_review에 저장.

"신메뉴"의 정의는 app/new_menu/router.py의 NEW_MENUS_SQL 하나뿐이다 -- 감지
로직을 여기 다시 쓰지 않고 그 쿼리를 그대로 가져와 리뷰 없는 것만 채운다.
generate_menu_reco.py와 같은 캐시 패턴: 런타임엔 LLM 호출이 없고, 크롤/재채점
후(rescore_if_changed.py)에만 돈다. ANTHROPIC_API_KEY가 없으면 조용히 건너뛴다.

리뷰는 메뉴당 1회 -- 이미 있으면 다시 만들지 않는다. 신메뉴 리뷰는 출시 시점
분석이라 영양값이 나중에 미세 조정돼도 갱신할 이유가 약하다.

    DATABASE_URL=... ANTHROPIC_API_KEY=... python scripts/llm/generate_new_menu_reviews.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from app.db import connect  # noqa: E402
from app.new_menu.router import fetch_new_menus  # noqa: E402

MODEL = "claude-opus-5"

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "diet_verdict": {"type": "string", "enum": ["추천", "무난", "비추천"]},
        "diet_comment": {
            "type": "string",
            "description": "한국어 한 문장, 80자 이내. 칼로리·단백질·당·나트륨 수치를 한두 개 들어 다이어트 관점 판정 근거.",
        },
        "taste_note": {
            "type": "string",
            "description": "한국어 한 문장, 80자 이내. 메뉴명·구성·당류/지방 수치로 추정한 예상 맛. 먹어본 것처럼 쓰지 말 것.",
        },
    },
    "required": ["diet_verdict", "diet_comment", "taste_note"],
    "additionalProperties": False,
}


def build_prompt(m) -> str:
    fmt = lambda v, unit="": "비공개" if v is None else f"{v:g}{unit}"
    return (
        f"프랜차이즈 '{m['restaurant_name']}'가 최근 출시한 신메뉴다.\n\n"
        f"- 메뉴명: {m['name']}\n"
        f"- 분류: {m['category_group'] or '기타'}\n"
        f"- 칼로리: {fmt(m['calorie'], 'kcal')} / 단백질: {fmt(m['protein'], 'g')}"
        f" / 당류: {fmt(m['sugar'], 'g')} / 포화지방: {fmt(m['saturated_fat'], 'g')}"
        f" / 나트륨: {fmt(m['sodium'], 'mg')}\n"
        f"- 다이어트 점수(0-100, WHO 기준 절대평가): "
        + (f"{m['diet_score']:.0f} (등급 {m['absolute_grade']})" if m["diet_score"] is not None else "미산정")
        + "\n\n다이어트 중인 사람 관점에서 이 신메뉴를 판정하고(추천/무난/비추천), "
        "수치를 근거로 한 문장으로 설명해라. 예상 맛도 한 문장으로 -- 실제로 먹어본 게 아니라 "
        "메뉴명과 성분으로 추정하는 것이니 단정하지 말고 추정 톤을 유지해라."
    )


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY 없음 -- 신메뉴 리뷰 생성 건너뜀")
        return

    import anthropic  # 키 없는 환경(cron)에서 import 실패로 죽지 않게 지연 import

    client = anthropic.Anthropic()

    with connect() as conn:
        pending = [m for m in fetch_new_menus(conn, limit=100) if m["diet_comment"] is None]
        if not pending:
            print("리뷰할 신메뉴 없음")
            return

        ok = 0
        for m in pending:
            try:
                resp = client.messages.create(
                    model=MODEL,
                    max_tokens=1024,
                    output_config={"format": {"type": "json_schema", "schema": REVIEW_SCHEMA}},
                    messages=[{"role": "user", "content": build_prompt(m)}],
                )
                review = json.loads(next(bl.text for bl in resp.content if bl.type == "text"))
            except Exception as e:  # 메뉴 하나 실패가 전체를 막지 않게
                print(f"  {m['restaurant_name']} {m['name']}: 실패 -- {e}")
                continue

            conn.execute(
                """INSERT INTO new_menu_review (menu_item_id, diet_verdict, diet_comment, taste_note, model)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (menu_item_id) DO NOTHING""",
                (m["id"], review["diet_verdict"], review["diet_comment"], review["taste_note"], MODEL),
            )
            conn.commit()  # 메뉴 단위 커밋 -- 중간에 죽어도 완료분은 남는다
            ok += 1
            print(f"  {m['restaurant_name']} {m['name']}: {review['diet_verdict']} -- {review['diet_comment']}")

        print(f"{ok}/{len(pending)} 신메뉴 리뷰 생성 완료")


if __name__ == "__main__":
    main()
