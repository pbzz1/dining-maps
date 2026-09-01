import { useEffect, useState } from "react";
import { formatDistance } from "../../constants";
import { fetchGoals, fetchRecommendedMenus } from "./api";
import { ACTIVITY_FACTORS, perMealCalorie } from "./bmr";
import { useLocalStorage } from "./useLocalStorage";
import { IconPin } from "../../components/NavIcons";

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

      <div className="rec-bar">
        <div className="rec-goal">
          <span className="filter-label">목표</span>
          {/* 목표는 4지선다 단일 선택이라 개별 버튼이 아니라 세그먼트 트랙으로 묶는다.
              트랙이 있어야 "이 중 하나"라는 사실이 눌러보기 전에 읽힌다. */}
          <div className="rec-segmented">
            {goals.map((g) => (
              <button
                key={g.key}
                type="button"
                className={`rec-segmented-btn ${prefs.goal === g.key ? "active" : ""}`}
                aria-pressed={prefs.goal === g.key}
                onClick={() => {
                  window.gtag?.("event", "recommend_goal", { goal: g.key });
                  update({ goal: g.key });
                }}
              >
                {g.label}
              </button>
            ))}
          </div>
        </div>

        {/* 켜고 끄는 스위치라 세그먼트와 다른 모양이어야 한다. 이전의 "켜짐 ✕"는
            칩 삭제로 읽혀서, 상태를 오른쪽 배지로 분리했다. */}
        <button
          type="button"
          className={`rec-nearby ${pos ? "on" : ""}`}
          aria-pressed={!!pos}
          onClick={pos ? () => setPos(null) : locate}
        >
          <IconPin size={16} />
          내 주변 매장 보기
          <span className="rec-nearby-state">{pos ? "켜짐" : "꺼짐"}</span>
        </button>
      </div>

      {/* details/summary -- 펼침 상태·키보드·스크린리더를 브라우저가 처리한다. */}
      <details className="rec-detail">
        <summary className="rec-detail-summary">
          <span className="rec-detail-title">상세 설정</span>
          <span className="rec-detail-hint">
            한 끼 {effectiveMaxCalorie ? `${Number(effectiveMaxCalorie).toLocaleString()}kcal` : "제한 없음"}
            {prefs.maxSodium && ` · 나트륨 ${Number(prefs.maxSodium).toLocaleString()}mg`}
            {prefs.excludeDrinks && " · 음료 제외"}
          </span>
        </summary>

        <div className="rec-detail-body">
          <div className="rec-fieldset">
            <p className="rec-fieldset-title">한 끼 상한</p>
            <div className="rec-grid">
              <label className="rec-field">
                <span className="rec-field-label">열량</span>
                <span className="rec-input">
                  <input
                    type="number"
                    placeholder={suggestedKcal ? String(suggestedKcal) : ""}
                    min="100"
                    step="50"
                    value={prefs.maxCalorie}
                    onChange={(e) => update({ maxCalorie: e.target.value })}
                  />
                  <span className="rec-unit">kcal</span>
                </span>
              </label>
              <label className="rec-field">
                <span className="rec-field-label">나트륨</span>
                <span className="rec-input">
                  <input
                    type="number"
                    placeholder="제한 없음"
                    min="0"
                    step="100"
                    value={prefs.maxSodium}
                    onChange={(e) => update({ maxSodium: e.target.value })}
                  />
                  <span className="rec-unit">mg</span>
                </span>
              </label>
              <label className="rec-check">
                <input
                  type="checkbox"
                  checked={prefs.excludeDrinks}
                  onChange={(e) => update({ excludeDrinks: e.target.checked })}
                />
                음료 제외
              </label>
            </div>
            {suggestedKcal && (
              <p className="rec-note">
                열량을 비우면 아래 내 정보로 계산한 <b>{suggestedKcal.toLocaleString()}kcal</b>이 적용됩니다.
              </p>
            )}
          </div>

          <div className="rec-fieldset">
            <p className="rec-fieldset-title">
              내 정보
              <span className="rec-fieldset-sub">한 끼 상한 계산용 · 한국 성인 평균이 기본값</span>
            </p>
            <div className="rec-grid">
              <label className="rec-field">
                <span className="rec-field-label">성별</span>
                <select value={profile.sex} onChange={(e) => onSexChange(e.target.value)}>
                  <option value="male">남성</option>
                  <option value="female">여성</option>
                </select>
              </label>
              <label className="rec-field">
                <span className="rec-field-label">키</span>
                <span className="rec-input">
                  <input
                    type="number"
                    value={profile.heightCm}
                    onChange={(e) => updateProfile({ heightCm: e.target.value })}
                  />
                  <span className="rec-unit">cm</span>
                </span>
              </label>
              <label className="rec-field">
                <span className="rec-field-label">몸무게</span>
                <span className="rec-input">
                  <input
                    type="number"
                    value={profile.weightKg}
                    onChange={(e) => updateProfile({ weightKg: e.target.value })}
                  />
                  <span className="rec-unit">kg</span>
                </span>
              </label>
              <label className="rec-field">
                <span className="rec-field-label">나이</span>
                <span className="rec-input">
                  <input
                    type="number"
                    value={profile.age}
                    onChange={(e) => updateProfile({ age: e.target.value })}
                  />
                  <span className="rec-unit">세</span>
                </span>
              </label>
              <label className="rec-field rec-field-wide">
                <span className="rec-field-label">활동량</span>
                <select value={profile.activity} onChange={(e) => updateProfile({ activity: e.target.value })}>
                  {Object.entries(ACTIVITY_FACTORS).map(([key, a]) => (
                    <option key={key} value={key}>
                      {a.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
        </div>
      </details>

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
