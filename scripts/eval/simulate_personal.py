"""학습형 개인 추천(taste.py) 오프라인 시뮬레이션. DB는 읽기만 한다(메뉴 목록).

가상 사용자 8유형 x 목표 3개가 30일 동안 매일 "오늘 당신에겐" 3개를 받고, 숨은 취향(utility)에
따라 저장·빼기·무시를 한다. 같은 사용자·같은 날에는 같은 난수를 써서(공통 난수) 기존 규칙(control)과
학습형(ml)의 차이가 운이 아니라 방식에서 나오게 한다.

    DATABASE_URL=postgresql://... python scripts/eval/simulate_personal.py

통과 조건(하나라도 어기면 exit 1 -- 머지 전 관문):
  - 기록 0개면 학습형 결과 = 기존 규칙 결과 (시작점이 안전하다)
  - 하드 제약 위반 0 (열량 상한·음료 제외·빼기한 메뉴), 부호 제약 위반 0
  - 무작위로 누르는 사용자에서 기존 규칙보다 나빠지지 않는다 (규제가 헛배움을 막는다)
  - 30일 동안 서로 다른 브랜드 6개 이상을 보여준다 (한 브랜드에 갇히지 않는다)
  - 취향이 바뀐 사용자를 8일 안에 따라간다
  - 학습 + 채점 p95 50ms 미만 (Lambda 요청 안에서 돈다)
"""
import math
import random
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from app.db import get_connection  # noqa: E402
from app.menu_category import is_drink  # noqa: E402
from app.recommend import taste as T  # noqa: E402
from app.recommend.personal import POOL_LIMIT, personal_rank, select_candidates  # noqa: E402
from app.recommend.ranking import fetch_menus  # noqa: E402

DAYS = 30
MAX_KCAL = 700
DRIFT_DAY = 15


def kcal(r):
    return r["nutrients"].get("calorie") or 0


# 숨은 취향: 메뉴 -> 효용. 참여 확률 = sigmoid(효용 - 1.5) -> 효용 0 이면 약 18%, 2 면 약 62%.
ARCHETYPES = {
    "치킨 좋아함": lambda r, d: 2.0 if r["category_group"] == "치킨" else -0.5,
    "샐러드만": lambda r, d: 2.0 if r["category_group"] == "샐러드·샌드위치" else -1.0,
    "대식가": lambda r, d: 1.5 if kcal(r) >= 500 else -0.5,
    "디저트·음료 싫음": lambda r, d: -2.0 if r["category_group"] in ("디저트", "음료") else 0.5,
    "한 브랜드 충성": lambda r, d: 2.5 if r["restaurant_name"] == "서브웨이" else -0.5,
    "무작위": lambda r, d: 0.0,
    "드문 사용자": lambda r, d: 2.0 if r["category_group"] == "샐러드·샌드위치" else -1.0,
    "취향 변화": lambda r, d: (2.0 if r["category_group"] == "치킨" else -0.5) if d < DRIFT_DAY
    else (2.0 if r["category_group"] == "샐러드·샌드위치" else -0.5),
}


def simulate(rows, stats, archetype, goal, use_taste, seed):
    utility = ARCHETYPES[archetype]
    profile = {"goal": goal, "max_calorie": MAX_KCAL, "exclude_drinks": True}
    events = []  # (day, menu_item_id, y, weight)
    hidden, saved, liked = set(), set(), Counter()
    by_id = {r["id"]: r for r in rows}
    log = []  # 날마다 (보여준 행들, 참여 수)
    violations, sign_violations, latencies = 0, 0, []
    for day in range(DAYS):
        rng = random.Random(f"{seed}:{archetype}:{goal}:{day}")  # 두 방식이 같은 날 같은 난수
        history = {"hidden": hidden, "saved": saved, "liked_brands": [b for b, _ in liked.most_common(5)],
                   "recent_hidden": [], "recent_saved": []}
        _, pool, _ = select_candidates(None, rows, profile, history, None, None, 3000, limit=POOL_LIMIT)
        t0 = time.perf_counter()
        taste = None
        if use_taste:
            ex = [(T.featurize(by_id[mid], stats), y, w * 0.5 ** ((day - d) / T.HALF_LIFE_DAYS), mid)
                  for d, mid, y, w in events[-T.MAX_EXAMPLES:]]
            taste = T.fit(ex, goal, stats)
            for key, s in T.SIGN.get(goal, {}).items():
                if (s < 0 and taste.mu.get(key, 0) > 1e-9) or (s > 0 and taste.mu.get(key, 0) < -1e-9):
                    sign_violations += 1
        # 탐색 난수는 행동 난수와 따로 -- 그래야 두 방식이 같은 날 같은 "사용자 반응 주사위"를 쓴다
        explore_rng = random.Random(f"explore:{seed}:{archetype}:{goal}:{day}") if use_taste else None
        picks = personal_rank(goal, pool, profile, history, taste=taste, rng=explore_rng)
        latencies.append((time.perf_counter() - t0) * 1000)

        engaged = 0
        shown = [t[2] for _, _, t in picks]
        for r in shown:
            if kcal(r) > MAX_KCAL or is_drink(r["category"], r["name"]) or r["id"] in hidden:
                violations += 1
            active_today = archetype != "드문 사용자" or day % 3 == 0
            p = 1 / (1 + math.exp(-(utility(r, day) - 1.5))) if archetype != "무작위" else 0.2
            if active_today and rng.random() < p:
                engaged += 1
                saved.add(r["id"])
                liked[r["restaurant_name"]] += 1
                events.append((day, r["id"], 1, T.POSITIVE["save"]))
            elif active_today and utility(r, day) < 0 and rng.random() < 0.3:
                hidden.add(r["id"])
                events.append((day, r["id"], 0, T.HIDE_WEIGHT))
            else:
                events.append((day, r["id"], 0, T.IGNORED_WEIGHT))
        log.append((shown, engaged))
    return log, violations, sign_violations, latencies


def main():
    conn = get_connection()
    rows = fetch_menus(conn)
    conn.close()
    stats = T.density_stats(rows)
    failures = []

    # 불변식: 기록 0개 -> 학습형 = 기존 규칙
    for goal in ("diet", "protein", "low_sodium"):
        profile = {"goal": goal, "max_calorie": MAX_KCAL, "exclude_drinks": True}
        history = {"hidden": set(), "saved": set(), "liked_brands": [], "recent_hidden": [], "recent_saved": []}
        _, pool, _ = select_candidates(None, rows, profile, history, None, None, 3000, limit=POOL_LIMIT)
        a = personal_rank(goal, pool, profile, history)
        b = personal_rank(goal, pool, profile, history, taste=T.fit([], goal, stats))
        if [x[2][2]["id"] for x in a] != [x[2][2]["id"] for x in b] or [x[1] for x in a] != [x[1] for x in b]:
            failures.append(f"기록 0개인데 결과가 다름 ({goal})")

    # 시드 하나로 판정하면 운에 따라 통과·실패가 뒤집힌다(실제로 그랬다). 여러 시드 평균으로 본다.
    seeds = range(1, 6)
    rate_of = lambda log, start=0: sum(e for _, e in log[start:]) / max(1, sum(len(s) for s, _ in log[start:]))
    print(f"시드 {len(seeds)}개 평균\n{'유형':12} {'목표':10} {'규칙':>6} {'학습형':>6} {'차이':>6}  브랜드수")
    rates = {"control": [], "ml": []}
    all_lat, total_viol, total_sign = [], 0, 0
    for archetype in ARCHETYPES:
        for goal in ("diet", "protein", "low_sodium"):
            res = {"control": [], "ml": []}
            for arm, use in (("control", False), ("ml", True)):
                for seed in seeds:
                    log, viol, sign, lat = simulate(rows, stats, archetype, goal, use, seed=seed)
                    total_viol += viol
                    total_sign += sign
                    if use:
                        all_lat += lat
                    brands = len({r["restaurant_name"] for s, _ in log for r in s})
                    res[arm].append((rate_of(log), brands, rate_of(log, DRIFT_DAY + 8)))
            mean = lambda arm, i: statistics.mean(x[i] for x in res[arm])
            rc, rm = mean("control", 0), mean("ml", 0)
            bc, bm = mean("control", 1), mean("ml", 1)
            rates["control"].append(rc)
            rates["ml"].append(rm)
            print(f"{archetype:12} {goal:10} {rc:6.1%} {rm:6.1%} {rm - rc:+6.1%}  {bc:.1f}->{bm:.1f}")
            if bm < 6:
                failures.append(f"브랜드 다양성 부족: {archetype}/{goal} 평균 {bm:.1f}개")
            if archetype == "무작위" and rm < rc - 0.02:
                failures.append(f"무작위 사용자에서 학습형이 더 나쁨: {archetype}/{goal} {rm:.1%} < {rc:.1%}")
            if archetype == "취향 변화":
                # 바뀐 뒤 8일째부터(23~29일) 참여율. 칸 하나에 노출이 100개 남짓이라 시드 5개로는
                # 표준오차가 4%p -- 판정이 운에 따라 뒤집혔다. 시드 20개 짝 차이로 보고, 학습형이
                # 통계적으로 유의하게 나쁠 때(95% 상한 < 0)만 못 따라간 것으로 친다.
                diffs = []
                for seed in range(1, 21):
                    c = rate_of(simulate(rows, stats, archetype, goal, False, seed)[0], DRIFT_DAY + 8)
                    m = rate_of(simulate(rows, stats, archetype, goal, True, seed)[0], DRIFT_DAY + 8)
                    diffs.append(m - c)
                d, se = statistics.mean(diffs), statistics.stdev(diffs) / math.sqrt(len(diffs))
                print(f"{'':12} {'':10} 변화 8일 뒤 참여율 차이 {d:+.1%} ± {se:.1%} (시드 20개)")
                if d + 1.96 * se < 0:
                    failures.append(f"취향 변화를 8일 안에 못 따라감 ({goal}: {d:+.1%}, 95% 상한 {d + 1.96 * se:+.1%})")

    p95 = statistics.quantiles(all_lat, n=20)[18]
    print(f"\n평균 참여율: 규칙 {statistics.mean(rates['control']):.1%} -> 학습형 {statistics.mean(rates['ml']):.1%}")
    print(f"하드 제약 위반 {total_viol}, 부호 제약 위반 {total_sign}, 학습+채점 p95 {p95:.1f}ms")
    if total_viol:
        failures.append(f"하드 제약 위반 {total_viol}")
    if total_sign:
        failures.append(f"부호 제약 위반 {total_sign}")
    if p95 >= 50:
        failures.append(f"p95 {p95:.1f}ms >= 50ms")
    if failures:
        print("\nFAIL\n  " + "\n  ".join(failures))
        sys.exit(1)
    print("\nPASS -- 모든 통과 조건 만족")


if __name__ == "__main__":
    main()
