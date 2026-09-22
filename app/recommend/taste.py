"""학습형 개인 취향 모델 (무료 개인화의 "AI"). LLM 없음, 순수 파이썬, 호출 비용 0.

사용자마다 요청 때 즉석에서 학습한다: 최근 60일의 노출(reco_impression)과 행동(user_event)으로
"보여준 것 중 무엇을 골랐고 무엇을 빼거나 무시했나"를 로지스틱 회귀로 푼다. 사용자당 예시가
수백 개를 넘지 않아 매 요청 다시 학습해도 수 ms 다 -- 모델 파일도, 배치 학습도 필요 없다.

  score(메뉴) = 기존 규칙 점수(personal_rank)  +  clip(w_u · φ(메뉴), ±CLIP)

- 기록이 없으면 w_u = 0 이라 결과가 기존 규칙과 정확히 같다(시작점이 안전하다).
- 보정 폭을 ±CLIP(0.6, 목표 점수 폭 1.0보다 작게)으로 묶는다. 배운 취향은 목표 안에서 순서를
  바꿀 뿐 목표를 뒤집지 못한다.
- 목표와 반대로 배우지 않게 부호를 묶는다(SIGN). 저나트륨 목표인 사람이 짠 메뉴를 몇 번 눌러도
  "짠 걸 더"로 배우지 않는다 -- 취향은 분류·브랜드·열량대에서 배운다.
- 베이지안 로지스틱 회귀(라플라스 근사)라 가중치마다 불확실성(분산)이 같이 나온다. 이유 문장은
  확신이 충분하고 실제 근거가 2건 이상인 특징만 인용한다(explain).
"""
import math
from collections import defaultdict
from dataclasses import dataclass, field

MODEL_VERSION = "taste-v1"
CLIP = 0.6
# 14일 전 행동은 절반 무게. 처음엔 45일이었는데, 시뮬레이션(scripts/eval, 시드 5개)에서 취향이
# 바뀐 사용자를 못 따라갔다(바뀐 뒤 8일째 참여율 22.5%, 기존 규칙 28.9%). 14일이면 27.3%로
# 따라가고 전체 평균 참여율은 29.4% -> 29.3%로 거의 그대로다. 7일은 전체가 29.0%로 내려가기 시작.
HALF_LIFE_DAYS = 14
LOOKBACK_DAYS = 60
MAX_EXAMPLES = 200
ITERATIONS = 15

NUTRIENTS = ("protein", "sodium", "sugar", "saturated_fat")
NUTRIENT_TOPIC = {"protein": "단백질이", "sodium": "나트륨이", "sugar": "당류가", "saturated_fat": "포화지방이"}
KCAL_BANDS = ((0, 300), (300, 500), (500, 700), (700, 900), (900, None))

# 사전 강도 λ (클수록 0에 붙잡는다). 브랜드는 26개로 쪼개져 한 칸당 근거가 적으니 더 보수적으로.
# 절편은 "이 사람이 원래 잘 누르나"를 흡수해서, 나머지가 상대적인 취향만 배우게 한다.
PRIOR = {"nut": 1.0, "kcal": 1.0, "group": 1.0, "brand": 3.0, "bias": 0.01}

# 목표와 같은 방향만 허용: -1 이면 w <= 0, +1 이면 w >= 0.
SIGN = {
    "low_sodium": {"nut:sodium": -1},
    "protein": {"nut:protein": +1},
    "diet": {"nut:sugar": -1, "nut:saturated_fat": -1},
}

# 행동별 라벨 무게. 저장은 "다음에도 먹겠다"라 클릭보다 강하다. 보여줬는데 무반응은 약한 부정 --
# 그냥 배가 안 고팠을 수도 있다.
POSITIVE = {"save": 1.5, "click": 1.0, "ate": 1.0}
HIDE_WEIGHT = 1.0
IGNORED_WEIGHT = 0.3
LEGACY_POSITIVE = 0.5  # 노출과 연결되지 않은(P0 이전·목록·대화) 긍정 행동
# 이보다 최근 노출은 "무반응"으로 치지 않는다. 보여주자마자 무반응으로 배우면 사용자가 반응할 틈도
# 없이 새로고침마다 모델이 바뀐다(검증에서 실제로 그랬다). 저장·빼기처럼 명시적 행동은 즉시 반영한다.
IGNORED_AFTER_HOURS = 1

# 이유 문장에 인용할 최소 확신도(|평균| / 표준편차)와 최소 근거 수. 문장 자체는 사용자 행동
# 횟수라 항상 사실이지만, 우연히 튄 특징을 "취향"이라 부르지 않으려는 문턱이다.
# ponytail: 1.0. 저장 4 · 무시 4 정도에서 넘는다(1.5 는 그 정도 증거도 못 넘었다).
CONFIDENCE = 1.0
MIN_EVIDENCE = 2

# 탐색. 배운 대로만 보여주면 한 번 치킨을 배운 사람에게 치킨만 보여주고, 샐러드를 누를 기회가
# 없으니 취향이 바뀌어도 영영 못 배운다(시뮬레이션에서 실제로 갇혔다 -- scripts/eval).
# 1) 톰슨 샘플링: 채점할 때 가중치를 사후분포에서 뽑는다. 확신이 없는 취향일수록 흔들려서
#    자연히 다양하게 보여 주고, 확신이 쌓이면 수렴한다.
# 2) 탐색 칸: 이 확률로 세 번째 칸을 최근에 고른 적 없는 분류에서 채우고, 그렇다고 밝힌다.
EXPLORE_RATE = 0.3
EXPLORE_REASON = "평소와 다른 선택지"


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x)) if x >= 0 else math.exp(x) / (1 + math.exp(x))


def density_stats(rows) -> dict:
    """카탈로그 전체의 100kcal당 영양 밀도 평균·표준편차. 특징을 z점수로 맞추는 데 쓴다."""
    acc = {k: [] for k in NUTRIENTS}
    for r in rows:
        n = r["nutrients"]
        kcal = n.get("calorie")
        if not kcal or kcal <= 0:
            continue
        for k in NUTRIENTS:
            if n.get(k) is not None:
                acc[k].append(n[k] / kcal * 100)
    out = {}
    for k, vs in acc.items():
        if len(vs) < 2:
            out[k] = (0.0, 1.0)
            continue
        m = sum(vs) / len(vs)
        s = math.sqrt(sum((v - m) ** 2 for v in vs) / (len(vs) - 1)) or 1.0
        out[k] = (m, s)
    return out


def featurize(row, stats) -> dict:
    """메뉴 한 행 -> 희소 특징 {이름: 값}. 영양 결측은 특징을 빼서 0(=평균)으로 둔다."""
    phi = {"bias": 1.0}
    n = row["nutrients"]
    kcal = n.get("calorie")
    if kcal and kcal > 0:
        for k in NUTRIENTS:
            if n.get(k) is not None:
                m, s = stats[k]
                phi[f"nut:{k}"] = max(-3.0, min(3.0, (n[k] / kcal * 100 - m) / s))
        for lo, hi in KCAL_BANDS:
            if kcal >= lo and (hi is None or kcal < hi):
                phi[f"kcal:{lo}"] = 1.0
                break
    phi[f"group:{row.get('category_group') or '기타'}"] = 1.0
    phi[f"brand:{row['restaurant_name']}"] = 1.0
    return phi


def load_examples(conn, user_id) -> list[tuple[int, int, float]]:
    """(menu_item_id, y, weight) 최신순. 노출에 연결된 행동이 주재료이고, 노출과 안 이어진
    예전·목록·대화 행동은 약한 긍정(저장·클릭)이나 부정(빼기)으로 보탠다."""
    impressions = conn.execute(
        """SELECT id, menu_item_ids, EXTRACT(EPOCH FROM now() - created_at) / 86400 AS age
           FROM reco_impression
           WHERE user_id = %s AND created_at > now() - make_interval(days => %s)
           ORDER BY created_at DESC LIMIT 100""",
        (user_id, LOOKBACK_DAYS),
    ).fetchall()
    events = conn.execute(
        """SELECT menu_item_id, event_type, impression_id, EXTRACT(EPOCH FROM now() - created_at) / 86400 AS age
           FROM user_event
           WHERE user_id = %s AND menu_item_id IS NOT NULL AND created_at > now() - make_interval(days => %s)
           ORDER BY created_at DESC LIMIT 500""",
        (user_id, LOOKBACK_DAYS),
    ).fetchall()
    decay = lambda age: 0.5 ** (float(age) / HALF_LIFE_DAYS)

    by_imp = defaultdict(lambda: {"pos": {}, "hide": set()})
    loose = []
    shown = {imp["id"] for imp in impressions}
    for e in events:
        if e["impression_id"] in shown:
            slot = by_imp[e["impression_id"]]
            if e["event_type"] == "hide":
                slot["hide"].add(e["menu_item_id"])
            elif e["event_type"] in POSITIVE:
                # 한 노출에서 같은 메뉴를 여러 번 눌러도 한 번 -- 가장 강한 행동만 센다
                slot["pos"][e["menu_item_id"]] = max(slot["pos"].get(e["menu_item_id"], 0), POSITIVE[e["event_type"]])
        elif e["event_type"] == "hide":
            loose.append((e["menu_item_id"], 0, HIDE_WEIGHT * decay(e["age"]), float(e["age"])))
        elif e["event_type"] in POSITIVE:
            loose.append((e["menu_item_id"], 1, LEGACY_POSITIVE * POSITIVE[e["event_type"]] * decay(e["age"]), float(e["age"])))

    out = list(loose)
    for imp in impressions:
        slot, d = by_imp[imp["id"]], decay(imp["age"])
        for mid in imp["menu_item_ids"]:
            if mid in slot["hide"]:
                out.append((mid, 0, HIDE_WEIGHT * d, float(imp["age"])))
            elif mid in slot["pos"]:
                out.append((mid, 1, slot["pos"][mid] * d, float(imp["age"])))
            elif float(imp["age"]) * 24 >= IGNORED_AFTER_HOURS:
                out.append((mid, 0, IGNORED_WEIGHT * d, float(imp["age"])))
    out.sort(key=lambda x: x[3])
    return [(mid, y, w) for mid, y, w, _ in out[:MAX_EXAMPLES]]


@dataclass
class Taste:
    mu: dict = field(default_factory=dict)
    var: dict = field(default_factory=dict)
    examples: list = field(default_factory=list)  # [(phi, y, w, menu_item_id)]
    stats: dict = field(default_factory=dict)

    @property
    def active(self) -> bool:
        """행동 근거가 하나라도 있나. 없으면 기존 규칙과 같게 동작해야 한다."""
        return any(y == 1 for _, y, _, _ in self.examples) or any(y == 0 and w >= HIDE_WEIGHT * 0.5 for _, y, w, _ in self.examples)

    def phi(self, row) -> dict:
        return featurize(row, self.stats)

    def score(self, phi, weights=None) -> float:
        """weights: sample() 로 뽑은 가중치(톰슨). 없으면 사후 평균."""
        w = weights or self.mu
        s = sum(w.get(k, 0.0) * v for k, v in phi.items() if k != "bias")
        return max(-CLIP, min(CLIP, s))

    def sample(self, rng) -> dict:
        """사후분포 N(평균, 분산)에서 가중치 한 벌. 확신이 낮은 특징일수록 크게 흔들린다."""
        return {k: mu + math.sqrt(self.var[k]) * rng.gauss(0, 1) for k, mu in self.mu.items()}

    def liked_groups(self) -> set:
        """고른 적 있는 분류. 탐색 칸은 이 밖에서 채운다."""
        return {k.partition(":")[2] for phi, y, _, _ in self.examples if y == 1 for k in phi if k.startswith("group:")}

    def _evidence(self, key) -> int:
        """이 특징 값을 가진 '고른' 메뉴 수(서로 다른 메뉴). 영양 특징은 같은 방향으로 뚜렷한 것만."""
        ids = set()
        for phi, y, _, mid in self.examples:
            if y != 1 or key not in phi:
                continue
            v = phi[key]
            if key.startswith("nut:"):
                if (self.mu.get(key, 0) > 0 and v > 0.5) or (self.mu.get(key, 0) < 0 and v < -0.5):
                    ids.add(mid)
            elif v:
                ids.add(mid)
        return len(ids)

    def _confident(self, key) -> bool:
        mu, var = self.mu.get(key, 0.0), self.var.get(key)
        return bool(var) and abs(mu) / math.sqrt(var) > CONFIDENCE and self._evidence(key) >= MIN_EVIDENCE

    def _sentence(self, key) -> str:
        kind, _, value = key.partition(":")
        n_pos = len({mid for _, y, _, mid in self.examples if y == 1})
        k = self._evidence(key)
        if kind == "group":
            return f"최근 저장·클릭 {n_pos}개 중 {k}개가 {value} 메뉴"
        if kind == "brand":
            return f"{value} 메뉴를 {k}번 저장·클릭"
        if kind == "kcal":
            lo = int(value)
            hi = dict(KCAL_BANDS)[lo]
            return f"평소 고른 메뉴와 비슷한 {lo}~{hi}kcal대" if hi else f"평소 고른 메뉴처럼 {lo}kcal 이상"
        if kind == "nut":
            return f"평소 {NUTRIENT_TOPIC[value]} {'많은' if self.mu[key] > 0 else '적은'} 메뉴를 골라서"
        return ""

    def explain(self, phi, pool_mean) -> str | None:
        """이 메뉴가 다른 후보보다 앞선 이유 중, 확신할 수 있는 것 하나. 없으면 None."""
        contrib = []
        for key, mu in self.mu.items():
            if key == "bias":
                continue
            c = mu * (phi.get(key, 0.0) - pool_mean.get(key, 0.0))
            if c > 0.05:
                contrib.append((c, key))
        for _, key in sorted(contrib, reverse=True):
            if self._confident(key):
                return self._sentence(key)
        return None

    def summary(self, limit=4) -> list[str]:
        """확신이 높은 취향 문장 (premium 프롬프트·메모리 패널용)."""
        keys = [k for k in self.mu if k != "bias" and self.mu[k] > 0 and self._confident(k)]
        keys.sort(key=lambda k: abs(self.mu[k]) / math.sqrt(self.var[k]), reverse=True)
        return [self._sentence(k) for k in keys[:limit]]


def fit(examples, goal, stats) -> Taste:
    """examples: [(phi, y, w, menu_item_id)]. 좌표별 뉴턴(가우스-자이델)로 MAP 을 푼 뒤
    대각 헤시안으로 분산을 잡는다. 좌표별로 풀면 원-핫끼리 상관이 있어도 진동하지 않는다."""
    taste = Taste(stats=stats, examples=list(examples))
    if not examples:
        return taste
    sign = SIGN.get(goal, {})
    index = defaultdict(list)  # 특징 -> [(예시 번호, 값)]
    for i, (phi, _, _, _) in enumerate(examples):
        for k, v in phi.items():
            index[k].append((i, v))
    lam = {k: PRIOR[k.partition(":")[0]] for k in index}
    w = {k: 0.0 for k in index}
    margin = [0.0] * len(examples)
    ys = [y for _, y, _, _ in examples]
    ss = [s for _, _, s, _ in examples]

    def grad_hess(k):
        g, h = -lam[k] * w[k], lam[k]
        for i, v in index[k]:
            p = _sigmoid(margin[i])
            g += ss[i] * (ys[i] - p) * v
            h += ss[i] * p * (1 - p) * v * v
        return g, h

    for _ in range(ITERATIONS):
        for k in index:
            g, h = grad_hess(k)
            new = w[k] + g / h
            if sign.get(k) == -1:
                new = min(new, 0.0)
            elif sign.get(k) == +1:
                new = max(new, 0.0)
            delta = new - w[k]
            if delta:
                w[k] = new
                for i, v in index[k]:
                    margin[i] += delta * v
    taste.mu = w
    taste.var = {k: 1 / grad_hess(k)[1] for k in index}
    return taste


if __name__ == "__main__":
    stats = {k: (0.0, 1.0) for k in NUTRIENTS}
    row = lambda i, brand, group, kcal=400, protein=10, sodium=300: {
        "id": i, "restaurant_name": brand, "category_group": group,
        "nutrients": {"calorie": kcal, "protein": protein, "sodium": sodium, "sugar": 2, "saturated_fat": 1},
    }
    # 특징: 원-핫과 z점수, 열량 구간
    phi = featurize(row(1, "샐러디", "샐러드·샌드위치", kcal=450), stats)
    assert phi["group:샐러드·샌드위치"] == 1 and phi["brand:샐러디"] == 1 and phi["kcal:300"] == 1 and phi["bias"] == 1
    assert featurize({"id": 2, "restaurant_name": "X", "category_group": None, "nutrients": {}}, stats).keys() == {"bias", "group:기타", "brand:X"}

    # 기록 없음 -> 비활성, 점수 0
    t0 = fit([], "diet", stats)
    assert not t0.active and t0.score(phi) == 0

    # 샐러드만 고르고 치킨은 무시하는 사용자 -> 샐러드 가중치 양수, 치킨 음수
    salad = [row(10 + i, "샐러디", "샐러드·샌드위치") for i in range(4)]
    chicken = [row(20 + i, "BHC", "치킨") for i in range(4)]
    ex = [(featurize(r, stats), 1, 1.0, r["id"]) for r in salad] + [(featurize(r, stats), 0, 1.0, r["id"]) for r in chicken]
    t = fit(ex, "diet", stats)
    assert t.active and t.mu["group:샐러드·샌드위치"] > 0 > t.mu["group:치킨"], t.mu
    assert t.score(featurize(salad[0], stats)) > t.score(featurize(chicken[0], stats))
    assert abs(t.score({"group:샐러드·샌드위치": 100.0})) <= CLIP  # 보정 폭 상한

    # 설명: 확신 + 근거 2건 이상인 특징만. 샐러드는 4건이라 인용된다.
    pool_mean = {"group:샐러드·샌드위치": 0.5, "group:치킨": 0.5}
    why = t.explain(featurize(salad[0], stats), pool_mean)
    assert why and "샐러드·샌드위치" in why, why
    assert t.explain(featurize(chicken[0], stats), pool_mean) is None  # 뒤처지는 쪽은 이유가 없다
    # 근거 1건이면 인용하지 않는다
    t1 = fit([(featurize(salad[0], stats), 1, 1.0, 10)], "diet", stats)
    assert t1.explain(featurize(salad[0], stats), {"group:샐러드·샌드위치": 0.0}) is None

    # 부호 제약: 저나트륨 목표인데 짠 것만 누른 사용자 -> 나트륨 가중치는 0 이하에 머문다
    salty = [(featurize(row(30 + i, "A", "치킨", sodium=2000), {**stats, "sodium": (100.0, 50.0)}), 1, 1.0, 30 + i) for i in range(5)]
    bland = [(featurize(row(40 + i, "B", "치킨", sodium=100), {**stats, "sodium": (100.0, 50.0)}), 0, 1.0, 40 + i) for i in range(5)]
    tl = fit(salty + bland, "low_sodium", stats)
    assert tl.mu["nut:sodium"] <= 0, tl.mu
    th = fit(salty + bland, "diet", stats)  # 목표가 다르면 제약 없음 -> 양수로 배운다
    assert th.mu["nut:sodium"] > 0

    # 수렴: 반복을 늘려도 거의 같은 값
    a =fit(ex, "diet", stats).mu["group:샐러드·샌드위치"]
    ITERATIONS = 60  # noqa: N806 -- 모듈 상수를 테스트에서만 바꿔 본다
    b = fit(ex, "diet", stats).mu["group:샐러드·샌드위치"]
    assert abs(a - b) < 1e-3, (a, b)
    print("ok")
