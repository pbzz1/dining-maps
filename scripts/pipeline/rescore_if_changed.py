"""Re-run compute_diet_score.py only when its inputs changed.

"Inputs" = every menu_item (id/name/category -- category drives meal/drink
basis) + every nutrition_fact row + the scoring rules themselves (hash of
compute_diet_score.py). A fingerprint of all of that is kept in
diet_score_run; if it matches the last run, nothing happens.

Brand relative grades (20/30/30/20) are ranked live in app/main.py, so the
only thing that needs a scheduled refresh is the per-menu diet_score table
-- i.e. new brands getting scored at all, and menu-level percentiles.

Run by .github/workflows/rescore.yml daily; `--force` skips the check.
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from app.db import apply_schema, connect  # noqa: E402
from scripts.pipeline import compute_diet_score  # noqa: E402

SCORER = ROOT / "scripts" / "pipeline" / "compute_diet_score.py"


def fingerprint(conn) -> str:
    data = conn.execute(
        """SELECT md5(
                 (SELECT coalesce(string_agg(id || ':' || name || ':' || coalesce(category, ''), ',' ORDER BY id), '')
                    FROM menu_item)
               || '|' ||
                 (SELECT coalesce(string_agg(menu_item_id || ':' || nutrient_name || ':' || value, ',' ORDER BY menu_item_id, nutrient_name), '')
                    FROM nutrition_fact)
           ) AS h"""
    ).fetchone()["h"]
    rules = hashlib.md5(SCORER.read_bytes()).hexdigest()
    return f"{data}-{rules}"


def main(force: bool = False) -> bool:
    """Returns True if scores were recomputed."""
    with connect() as conn:
        apply_schema(conn)
        # compute_diet_score.main() opens its OWN connection (it's also run
        # standalone), so without an explicit commit here the schema changes
        # above are invisible to it -- a separate session can't see another
        # session's uncommitted DDL. This is what actually caused "column
        # basis does not exist" even though the ALTER ran moments earlier.
        conn.commit()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS diet_score_run (fingerprint TEXT NOT NULL, ran_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        fp = fingerprint(conn)
        last = conn.execute("SELECT fingerprint FROM diet_score_run ORDER BY ran_at DESC LIMIT 1").fetchone()
        changed = force or not last or last["fingerprint"] != fp
        if changed:
            print(f"inputs changed -> rescoring ({fp[:12]}…)")
            compute_diet_score.main()
            conn.execute("INSERT INTO diet_score_run (fingerprint) VALUES (%s)", (fp,))
        else:
            print(f"unchanged ({fp[:12]}…); skipping")
    # 여기부터는 conn이 닫힌 뒤다 -- 유튜브 검색처럼 몇 분 걸리는 작업을 with 블록
    # 안에서 하면 놀고 있던 연결을 Neon 풀러가 끊어 커밋에서 죽는다.
    if changed:
        # 점수가 바뀌었을 때만 LLM 추천도 재생성 (키 없으면 스스로 건너뜀)
        from scripts.llm import generate_menu_reco
        generate_menu_reco.main()
        # 신메뉴 LLM 리뷰는 화면에서 뺐다 -- 다시 켜려면 여기서
        # generate_new_menu_reviews.main() 호출을 복구하면 된다.
    # 유튜브 영상 ID 캐시는 지문과 무관하게 돈다 -- seed_released_at이 출시일만 넣어
    # 신메뉴가 생기면 지문은 그대로인데 영상 연결은 필요하다. 캐시된 메뉴는
    # 건너뛰므로 평소엔 사실상 no-op.
    from scripts.crawl import fetch_youtube_reviews
    fetch_youtube_reviews.main()
    return changed


if __name__ == "__main__":
    main(force="--force" in sys.argv)
