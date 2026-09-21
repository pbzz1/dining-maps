import { useEffect, useState } from "react";
import { formatDistance, track } from "../../constants";
import Skel, { SkelBlock } from "../../components/Skeleton";
import { logEvent } from "../auth/api";
import { fetchPersonalPicks } from "./api";
import { nutritionLine, storeMapUrl } from "./format";

// 로그인 사용자에게만 뜨는 "오늘 당신에겐" 3개. 서버가 프로필·최근 기록을 보고 고른다.
// 서버는 키가 없거나 실패하면 목표 점수 상위 3개(source="rule")를 주는데, 그건 바로 아래
// 목록의 1~3위와 똑같다 -- 같은 걸 두 번 보여주며 목록만 밀어내게 되므로 그땐 칸을 접는다.
// refreshKey: 프로필 저장이 끝날 때마다 바뀐다. 저장 전에 다시 부르면 옛 설정으로 고른다.
export default function PersonalPicks({ pos, refreshKey }) {
  const [data, setData] = useState(null); // { source, goal, comment, items }
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(() => new Set());
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchPersonalPicks(pos ? { lat: pos.lat, lng: pos.lng } : undefined)
      .then((d) => !cancelled && setData(d))
      .catch(() => !cancelled && setData(null))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [pos, refreshKey, reloadKey]);

  function save(m) {
    if (saved.has(m.menu_item_id)) return;
    setSaved((s) => new Set(s).add(m.menu_item_id));
    track("personal_pick_save", { source: data?.source });
    logEvent("save", m.menu_item_id);
  }

  async function hide(m) {
    // 먼저 화면에서 뺀다 -- 서버 응답(LLM 수 초)을 기다리면 누른 게 안 먹은 것처럼 보인다.
    setData((d) => ({ ...d, items: d.items.filter((i) => i.menu_item_id !== m.menu_item_id) }));
    track("personal_pick_hide", { source: data?.source });
    await logEvent("hide", m.menu_item_id); // 기록이 끝난 뒤에 다시 불러야 후보에서 빠진다
    setReloadKey((k) => k + 1);
  }

  const items = data?.items ?? [];
  // 첫 로딩(스켈레톤) 또는 AI가 고른 결과일 때만 칸을 편다. 불러오기 실패도 접는다 --
  // 아래 목록이 그대로 있으니 에러 문구로 자리를 차지할 이유가 없다.
  if (!(loading && !data) && data?.source !== "llm") return null;

  return (
    <>
    <section className="pick-section" aria-labelledby="pick-title" aria-busy={loading}>
      <div className="pick-head">
        <h3 id="pick-title" className="pick-title">오늘 당신에겐</h3>
        {/* 이 칸의 문장을 누가 썼는지가 이 배지의 전제다 -- 강조가 아니라 기준 표시. */}
        {data && <span className="pick-basis">AI 추천</span>}
        {loading && data && <span className="pick-status">다시 고르는 중…</span>}
      </div>
      {data?.comment && <p className="pick-comment">{data.comment}</p>}

      {loading && !data && (
        <SkelBlock label="내 설정과 최근 기록으로 고르는 중">
          <div className="menu-list">
            {[0, 1, 2].map((i) => <Skel key={i} h={96} r={12} />)}
          </div>
        </SkelBlock>
      )}
      {data && !loading && items.length === 0 && (
        <p className="loading">조건에 맞는 메뉴가 없습니다. 상세 설정에서 상한을 올려보세요.</p>
      )}

      <div className="menu-list">
        {items.map((m) => (
          <article key={m.menu_item_id} className="menu-item">
            <div className="menu-item-head">
              <span className="menu-item-name">
                {m.restaurant_name} · {m.name}
              </span>
              <span className="menu-item-meta">{m.category}</span>
            </div>
            <p className="pick-reason">{m.reason}</p>
            <div className="nutrition-row">
              {m.nearest_store && (
                <a
                  className="nutrient-badge"
                  href={storeMapUrl(m)}
                  target="_blank"
                  rel="noreferrer"
                  onClick={() => logEvent("click", m.menu_item_id)}
                >
                  📍 {m.nearest_store.branch_name ?? m.restaurant_name} {formatDistance(m.nearest_store.distance_m)} ↗
                </a>
              )}
              <span className="menu-item-meta" style={{ marginLeft: "auto", alignSelf: "flex-end" }}>
                {nutritionLine(m)}
              </span>
            </div>
            <div className="pick-actions">
              <button
                type="button"
                className="pick-btn"
                aria-pressed={saved.has(m.menu_item_id)}
                onClick={() => save(m)}
              >
                {saved.has(m.menu_item_id) ? "저장됨" : "저장"}
              </button>
              <button type="button" className="pick-btn" onClick={() => hide(m)}>
                이 메뉴 빼기
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
    {/* 두 칸이 한 목록처럼 섞여 보이지 않게, 이 칸이 펼쳐졌을 때만 아래 목록에 이름을 붙인다. */}
    <h3 className="pick-title rec-list-title">목표 점수 순 전체</h3>
    </>
  );
}
