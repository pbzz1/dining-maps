import { useEffect, useState } from "react";
import { formatDistance } from "../../constants";
import { fetchGoals, fetchRecommendedMenus } from "./api";
import { ACTIVITY_FACTORS, perMealCalorie } from "./bmr";
import { useLocalStorage } from "./useLocalStorage";

// Step 0: 목표 선택 -> Step 2: 하드 제약(한 끼 상한, 음료 제외) -> Step 1: 근처 매장
// -> Step 3: 신체정보는 새 화면이 아니라 위 '한 끼 상한'의 기본값 계산기.
// 전부 localStorage 에 남아서 재방문 시 그대로 복원된다. 로그인 없음.
const DEFAULT_PREFS = { goal: "diet", maxCalorie: "", maxSodium: "", excludeDrinks: true };
const DEFAULT_PROFILE = { heightCm: "", weightKg: "", age: "", sex: "male", activity: "sedentary" };

export default function RecommendView() {
  const [goals, setGoals] = useState([]);
  const [prefs, setPrefs] = useLocalStorage("recommend.prefs", DEFAULT_PREFS);
  const [pos, setPos] = useLocalStorage("recommend.pos", null); // {lat,lng} | null
  const [profile, setProfile] = useLocalStorage("recommend.profile", DEFAULT_PROFILE);
  const [showProfile, setShowProfile] = useState(false);
  const [items, setItems] = useState([]);
  const [openId, setOpenId] = useState(null); // 펼쳐진 메뉴 (영양정보 표시)
  const [status, setStatus] = useState("");

  const update = (patch) => setPrefs((p) => ({ ...p, ...patch }));
  const updateProfile = (patch) => setProfile((p) => ({ ...p, ...patch }));
  const suggestedKcal = perMealCalorie(profile);

  useEffect(() => {
    fetchGoals().then(setGoals).catch(() => setGoals([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setStatus("불러오는 중...");
    const params = { goal: prefs.goal, exclude_drinks: prefs.excludeDrinks, limit: 20 };
    if (prefs.maxCalorie) params.max_calorie = prefs.maxCalorie;
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
  }, [prefs, pos]);

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
          <span className="filter-label">한 끼 상한</span>
          <input
            type="number"
            placeholder="kcal"
            min="100"
            step="50"
            value={prefs.maxCalorie}
            onChange={(e) => update({ maxCalorie: e.target.value })}
            style={{ width: 90 }}
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
        </div>
        <label className="filter-group">
          <input
            type="checkbox"
            checked={prefs.excludeDrinks}
            onChange={(e) => update({ excludeDrinks: e.target.checked })}
          />
          <span className="filter-label">음료 제외</span>
        </label>
        <div className="filter-group">
          <button className="grade-type-btn" onClick={locate}>
            {pos ? "내 위치 다시 찾기" : "내 주변 매장 보기"}
          </button>
          {pos && (
            <button className="grade-type-btn" onClick={() => setPos(null)}>
              위치 지우기
            </button>
          )}
        </div>
        <div className="filter-group">
          <button className="grade-type-btn" onClick={() => setShowProfile((v) => !v)}>
            내 정보로 상한 계산 {showProfile ? "▲" : "▼"}
          </button>
        </div>
      </div>

      {showProfile && (
        <div className="filter-controls" style={{ marginTop: 8 }}>
          <div className="filter-group">
            <input
              type="number"
              placeholder="키 cm"
              value={profile.heightCm}
              onChange={(e) => updateProfile({ heightCm: e.target.value })}
              style={{ width: 80 }}
            />
            <input
              type="number"
              placeholder="몸무게 kg"
              value={profile.weightKg}
              onChange={(e) => updateProfile({ weightKg: e.target.value })}
              style={{ width: 90 }}
            />
            <input
              type="number"
              placeholder="나이"
              value={profile.age}
              onChange={(e) => updateProfile({ age: e.target.value })}
              style={{ width: 70 }}
            />
            <select value={profile.sex} onChange={(e) => updateProfile({ sex: e.target.value })}>
              <option value="male">남성</option>
              <option value="female">여성</option>
            </select>
            <select value={profile.activity} onChange={(e) => updateProfile({ activity: e.target.value })}>
              {Object.entries(ACTIVITY_FACTORS).map(([key, a]) => (
                <option key={key} value={key}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>
          <div className="filter-group">
            {suggestedKcal ? (
              <button className="grade-type-btn active" onClick={() => update({ maxCalorie: String(suggestedKcal) })}>
                한 끼 {suggestedKcal}kcal로 적용
              </button>
            ) : (
              <span className="filter-label">키·몸무게·나이를 입력하면 한 끼 kcal을 계산해 드립니다</span>
            )}
          </div>
        </div>
      )}

      {status && <p className="loading">{status}</p>}

      <div className="menu-list" style={{ marginTop: 16 }}>
        {items.map((m, i) => (
          <div key={m.menu_item_id} className="menu-item">
            <div
              className="menu-item-head"
              style={{ cursor: "pointer" }}
              onClick={() => {
                window.gtag?.("event", "toggle_nutrition", { menu: m.name, goal: prefs.goal });
                setOpenId(openId === m.menu_item_id ? null : m.menu_item_id);
              }}
            >
              <span className="menu-item-name">
                {i + 1}. {m.restaurant_name} · {m.name}
              </span>
              <span className="menu-item-meta">
                {m.category} {openId === m.menu_item_id ? "▲" : "▼"}
              </span>
            </div>
            {openId === m.menu_item_id && (
              <div className="nutrition-row">
                {[["열량", m.calorie, "kcal"], ["단백질", m.protein, "g"], ["당류", m.sugar, "g"], ["나트륨", m.sodium, "mg"]].map(
                  ([label, v, unit]) => (
                    <span key={label} className="nutrient-badge">
                      {label} <b>{v == null ? "-" : `${Math.round(v)}${unit}`}</b>
                    </span>
                  )
                )}
              </div>
            )}
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
