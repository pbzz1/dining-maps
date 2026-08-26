import { useEffect, useState } from "react";
import { formatDistance } from "../../constants";
import { fetchGoals, fetchRecommendedMenus } from "./api";
import { ACTIVITY_FACTORS, perMealCalorie } from "./bmr";
import { useLocalStorage } from "./useLocalStorage";

// Step 0: 목표 선택 -> Step 2: 하드 제약(한 끼 상한, 음료 제외) -> Step 1: 근처 매장
// -> Step 3: 신체정보는 새 화면이 아니라 위 '한 끼 상한'의 기본값 계산기.
// 전부 localStorage 에 남아서 재방문 시 그대로 복원된다. 로그인 없음.
const DEFAULT_PREFS = { goal: "diet", maxCalorie: "", maxSodium: "", excludeDrinks: true };

// 질병관리청 국민건강영양조사 성인 평균 근사치. 신체정보를 한 번도 안 만진
// 유저도 처음부터 "내 한 끼 상한"이 채워져 있도록 하는 기본값이다.
const KOREAN_AVG = {
  male: { heightCm: 173, weightKg: 74, age: 35 },
  female: { heightCm: 160, weightKg: 59, age: 35 },
};
const DEFAULT_PROFILE = { ...KOREAN_AVG.male, sex: "male", activity: "light" };

export default function RecommendView() {
  const [goals, setGoals] = useState([]);
  const [prefs, setPrefs] = useLocalStorage("recommend.prefs", DEFAULT_PREFS);
  const [pos, setPos] = useLocalStorage("recommend.pos", null); // {lat,lng} | null
  const [profile, setProfile] = useLocalStorage("recommend.profile", DEFAULT_PROFILE);
  const [showDetail, setShowDetail] = useState(false);
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("");

  const update = (patch) => setPrefs((p) => ({ ...p, ...patch }));
  const updateProfile = (patch) => setProfile((p) => ({ ...p, ...patch }));
  // 성별을 바꾸면 그 성별의 표준 체형으로 리셋한다 -- 커스텀 값을 유지하고 싶으면
  // 그 뒤에 직접 다시 고치면 된다 (ponytail: "직전 값이 기본값이었는지" 추적 안 함).
  const onSexChange = (sex) => updateProfile({ sex, ...KOREAN_AVG[sex] });
  const suggestedKcal = perMealCalorie(profile);
  // 한 끼 상한을 직접 입력하지 않았으면 신체정보 기준 계산값을 그대로 쓴다.
  const effectiveMaxCalorie = prefs.maxCalorie || suggestedKcal;

  useEffect(() => {
    fetchGoals().then(setGoals).catch(() => setGoals([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setStatus("불러오는 중...");
    const params = { goal: prefs.goal, exclude_drinks: prefs.excludeDrinks, limit: 20 };
    if (effectiveMaxCalorie) params.max_calorie = effectiveMaxCalorie;
    if (prefs.maxSodium) params.max_sodium = prefs.maxSodium;
    if (pos) Object.assign(params, { lat: pos.lat, lng: pos.lng });
    fetchRecommendedMenus(params)
      .then((list) => {
        if (cancelled) return;
        setItems(list);
        setStatus(list.length ? "" : "조건에 맞는 메뉴가 없습니다. 상한을 올려보세요.");
      })
      .catch((e) => !cancelled && setStatus(`불러오지 못했습니다: ${e.message}`));
    return () => {
      cancelled = true;
    };
  }, [prefs, pos, effectiveMaxCalorie]);

  function locate() {
    if (!navigator.geolocation) return setStatus("이 브라우저는 위치 정보를 지원하지 않습니다.");
    setStatus("내 위치 확인 중...");
    navigator.geolocation.getCurrentPosition(
      (p) => setPos({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => setStatus("위치 권한이 거부되었습니다.")
    );
  }

  return (
    <section>
      <h2>맞춤 추천</h2>
      <p className="legend-hint">
        목표와 한 끼 상한만 고르면 됩니다. 선택은 이 브라우저에 저장되고 로그인은 필요 없습니다.
      </p>

      <div className="filter-controls">
        <div className="filter-group">
          <span className="filter-label">목표</span>
          {goals.map((g) => (
            <button
              key={g.key}
              className={`grade-type-btn ${prefs.goal === g.key ? "active" : ""}`}
              onClick={() => {
                window.gtag?.("event", "recommend_goal", { goal: g.key });
                update({ goal: g.key });
              }}
            >
              {g.label}
            </button>
          ))}
        </div>
        <div className="filter-group">
          <button className={`grade-type-btn ${pos ? "active" : ""}`} onClick={pos ? () => setPos(null) : locate}>
            {pos ? "내 주변 매장 보기 켜짐 ✕" : "내 주변 매장 보기"}
          </button>
        </div>
        <div className="filter-group">
          <button className="grade-type-btn" onClick={() => setShowDetail((v) => !v)}>
            상세 설정 {showDetail ? "▲" : "▼"}
          </button>
        </div>
      </div>

      {showDetail && (
        <div className="filter-controls" style={{ marginTop: 8 }}>
          <div className="filter-group">
            <span className="filter-label">한 끼 상한</span>
            <input
              type="number"
              placeholder={suggestedKcal ? `${suggestedKcal}kcal` : "kcal"}
              min="100"
              step="50"
              value={prefs.maxCalorie}
              onChange={(e) => update({ maxCalorie: e.target.value })}
              style={{ width: 100 }}
            />
            <input
              type="number"
              placeholder="나트륨 mg"
              min="0"
              step="100"
              value={prefs.maxSodium}
              onChange={(e) => update({ maxSodium: e.target.value })}
              style={{ width: 110 }}
            />
            <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <input
                type="checkbox"
                checked={prefs.excludeDrinks}
                onChange={(e) => update({ excludeDrinks: e.target.checked })}
              />
              <span className="filter-label">음료 제외</span>
            </label>
          </div>
          <div className="filter-group">
            <span className="filter-label">내 정보 (상한 자동 계산 · 한국 평균 기본값)</span>
            <select value={profile.sex} onChange={(e) => onSexChange(e.target.value)}>
              <option value="male">남성</option>
              <option value="female">여성</option>
            </select>
            <input
              type="number"
              placeholder="키 cm"
              value={profile.heightCm}
              onChange={(e) => updateProfile({ heightCm: e.target.value })}
              style={{ width: 70 }}
            />
            <input
              type="number"
              placeholder="몸무게 kg"
              value={profile.weightKg}
              onChange={(e) => updateProfile({ weightKg: e.target.value })}
              style={{ width: 80 }}
            />
            <input
              type="number"
              placeholder="나이"
              value={profile.age}
              onChange={(e) => updateProfile({ age: e.target.value })}
              style={{ width: 60 }}
            />
            <select value={profile.activity} onChange={(e) => updateProfile({ activity: e.target.value })}>
              {Object.entries(ACTIVITY_FACTORS).map(([key, a]) => (
                <option key={key} value={key}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {status && <p className="loading">{status}</p>}

      <div className="menu-list" style={{ marginTop: 16 }}>
        {items.map((m, i) => (
          <div key={m.menu_item_id} className="menu-item">
            <div className="menu-item-head">
              <span className="menu-item-name">
                {i + 1}. {m.restaurant_name} · {m.name}
              </span>
              <span className="menu-item-meta">{m.category}</span>
            </div>
            <div className="nutrition-row">
              <span className="nutrient-badge">
                <b>{m.reason}</b>
              </span>
              {m.nearest_store ? (
                <a
                  className="nutrient-badge"
                  href={`https://map.kakao.com/link/map/${encodeURIComponent(
                    m.nearest_store.branch_name ?? m.restaurant_name
                  )},${m.nearest_store.lat},${m.nearest_store.lng}`}
                  target="_blank"
                  rel="noreferrer"
                  onClick={() =>
                    window.gtag?.("event", "open_store", {
                      brand: m.restaurant_name,
                      goal: prefs.goal,
                      distance_m: Math.round(m.nearest_store.distance_m),
                    })
                  }
                >
                  📍 {m.nearest_store.branch_name ?? m.restaurant_name}{" "}
                  {formatDistance(m.nearest_store.distance_m)} ↗
                </a>
              ) : (
                pos && <span className="nutrient-badge">반경 3km 내 매장 없음</span>
              )}
              {/* 영양정보는 항상 박스 우측 하단에 -- 클릭해야 보이면 비교가 안 된다 */}
              <span className="menu-item-meta" style={{ marginLeft: "auto", alignSelf: "flex-end" }}>
                {[["열량", m.calorie, "kcal"], ["단백질", m.protein, "g"], ["당류", m.sugar, "g"], ["포화지방", m.saturated_fat, "g"], ["나트륨", m.sodium, "mg"]]
                  .map(([label, v, unit]) => `${label} ${v == null ? "-" : Math.round(v) + unit}`)
                  .join(" · ")}
              </span>
            </div>
          </div>
        ))}
      </div>
      <p className="legend-hint" style={{ marginTop: 16 }}>
        영양정보는 각 브랜드 공개 자료 기준이며 의학적 조언이 아닙니다.
      </p>
    </section>
  );
}
