import { useEffect, useRef, useState } from "react";
import { formatDistance, track } from "../../constants";
import Skel, { SkelBlock } from "../../components/Skeleton";
import { logEvent } from "../auth/api";
import { quotaLine } from "../auth/plan";
import { fetchPersonalPicks } from "./api";
import MemoryPanel from "../memory/MemoryPanel";
import { FAVORITE_REMOVED, fetchFavorites, removeFavorite } from "../profile/api";
import { nutritionLine, storeMapUrl } from "./format";

// 로그인 사용자에게만 뜨는 "오늘 당신에겐" 3개. source 로 누가 골랐는지가 온다:
//   personal -- 설정·기록 기반 룰 (무료, 기본)   llm -- Claude가 고르고 이유를 씀 (Standard·High 이용권)
//   ml       -- 위 룰 + 이 사람의 저장·빼기·무시 기록으로 학습한 취향 (무료, 기록이 있을 때만)
//   rule     -- 후보가 없음. 이땐 칸을 접는다(아래 목록이 "조건에 맞는 메뉴 없음"을 이미 말한다).
// refreshKey: 프로필 저장이 끝날 때마다 바뀐다. 저장 전에 다시 부르면 옛 설정으로 고른다.
// paid: 유료 이용권. AI 메모리 패널의 직접 추가를 열고, "이번 기간 AI 남은 양"을 글자로 보여준다.
// 메모리 목록 자체는 요금제와 무관하게 보인다.
const BASIS = { llm: "AI 추천", ml: "내 기록으로 학습", personal: "내 설정·기록 기반" };
// 유료인데 AI 가 고르지 않은 이유(서버 limit_reason). 막힌 걸 숨기지 않고 왜 무료 방식으로 골랐는지 말한다.
const LIMIT_NOTE = {
  budget: "이번 기간 AI 사용량을 다 써서 설정·기록으로 골랐어요.",
  daily: "오늘 AI 호출 횟수를 다 써서 설정·기록으로 골랐어요.",
  input: "입력이 너무 길어 설정·기록으로 골랐어요.",
  no_plan: "이용권이 끝나 설정·기록으로 골랐어요.",
};

export default function PersonalPicks({ pos, refreshKey, paid = false }) {
  const [data, setData] = useState(null); // { source, goal, comment, items }
  const [loading, setLoading] = useState(true);
  // 저장한 메뉴 = 내 정보의 즐겨찾기. 서버 목록으로 채워 둬야 새로고침 뒤에도 "저장됨"이 남는다.
  const [saved, setSaved] = useState(() => new Set());
  const pendingSave = useRef(new Map()); // id -> 기록 중인 save 요청. 곧바로 취소하면 기록이 끝난 뒤 지운다
  const [reloadKey, setReloadKey] = useState(0);
  const [memoryKey, setMemoryKey] = useState(0); // 추천이 새로 기억하면 패널을 다시 불러온다
  const shownIds = useRef([]); // 서버가 보여준 순서 -- 이벤트의 position 기준
  // 마지막으로 새로 기억한 것. 응답마다 덮지 않는다 -- 곧이어 오는 캐시 응답(memory_added 빈 배열)이
  // 방금 띄운 알림을 지워 버리면 사용자는 AI가 뭘 기억했는지 못 보고 지나간다.
  const [remembered, setRemembered] = useState([]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchPersonalPicks(pos ? { lat: pos.lat, lng: pos.lng } : undefined)
      .then((d) => {
        // 새로 기억했다는 건 서버에서 이미 일어난 일이라, 이 응답이 뒤이은 재조회에 밀려 취소됐어도
        // 알린다. 첫 로그인은 설정 업로드 뒤 곧바로 다시 부르는데, 그때 첫 응답만 memory_added 를
        // 갖고 두 번째(캐시)는 빈 배열이라 여기서 버리면 알림이 영영 안 뜬다.
        if (d.memory_added?.length) {
          setRemembered(d.memory_added);
          setMemoryKey((k) => k + 1);
        }
        if (!cancelled) {
          shownIds.current = d.items.map((i) => i.menu_item_id);
          setData(d);
        }
      })
      .catch(() => !cancelled && setData(null))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [pos, refreshKey, reloadKey]);

  useEffect(() => {
    fetchFavorites()
      .then((list) => setSaved(new Set(list.map((f) => f.menu_item_id))))
      .catch(() => {}); // 못 불러와도 저장 단추는 그대로 쓸 수 있다
    // 내 정보에서 해제하면 이 카드도 "저장"으로 돌아와야 한다 -- 이 뷰는 숨겨진 채 살아 있어 다시 불리지 않는다.
    const onRemoved = (e) =>
      setSaved((s) => {
        if (!s.has(e.detail)) return s;
        const next = new Set(s);
        next.delete(e.detail);
        return next;
      });
    window.addEventListener(FAVORITE_REMOVED, onRemoved);
    return () => window.removeEventListener(FAVORITE_REMOVED, onRemoved);
  }, []);

  // 이벤트에 붙일 문맥: 어느 노출의 몇 번째 카드였나. 위치는 "처음 보여준 순서" 기준이라
  // 빼기로 카드가 줄어든 뒤의 화면 인덱스가 아니라 서버가 준 순서(shownIds)에서 찾는다.
  const ctx = (m) => ({
    impression_id: data?.impression_id ?? null,
    surface: "personal_picks",
    position: shownIds.current.indexOf(m.menu_item_id),
  });

  // 다시 누르면 저장 취소(= 즐겨찾기 해제). 서버에서 save 기록을 지워 학습에서도 빠진다.
  function toggleSave(m) {
    const id = m.menu_item_id;
    if (saved.has(id)) {
      setSaved((s) => {
        const next = new Set(s);
        next.delete(id);
        return next;
      });
      track("personal_pick_unsave", { source: data?.source, variant: data?.variant });
      // 404 = 이미 없음. 실패해도 내 정보에서 다시 해제할 수 있다
      Promise.resolve(pendingSave.current.get(id)).then(() => removeFavorite(id)).catch(() => {});
      return;
    }
    setSaved((s) => new Set(s).add(id));
    track("personal_pick_save", { source: data?.source, variant: data?.variant });
    const p = logEvent("save", id, ctx(m));
    pendingSave.current.set(id, p);
    p.finally(() => pendingSave.current.get(id) === p && pendingSave.current.delete(id));
  }

  async function hide(m) {
    const context = ctx(m); // 화면에서 빼기 전에 잡아 둔다
    // 먼저 화면에서 뺀다 -- 서버 응답(LLM 수 초)을 기다리면 누른 게 안 먹은 것처럼 보인다.
    setData((d) => ({ ...d, items: d.items.filter((i) => i.menu_item_id !== m.menu_item_id) }));
    track("personal_pick_hide", { source: data?.source, variant: data?.variant });
    await logEvent("hide", m.menu_item_id, context); // 기록이 끝난 뒤에 다시 불러야 후보에서 빠진다
    setReloadKey((k) => k + 1);
  }

  const items = data?.items ?? [];
  // 첫 로딩(스켈레톤)이거나 고른 결과가 있을 때만 칸을 편다. 불러오기 실패도 접는다 --
  // 아래 목록이 그대로 있으니 에러 문구로 자리를 차지할 이유가 없다. 메모리 패널은 따로 산다.
  const showPicks = (loading && !data) || !!BASIS[data?.source];

  return (
    <>
    {showPicks && (
    <section className="pick-section" aria-labelledby="pick-title" aria-busy={loading}>
      <div className="pick-head">
        <h3 id="pick-title" className="pick-title">오늘 당신에겐</h3>
        {/* 이 칸의 문장을 누가 썼는지가 이 배지의 전제다 -- 강조가 아니라 기준 표시. */}
        {data && <span className="pick-basis">{BASIS[data.source]}</span>}
        {/* 남은 양은 막대가 아니라 글자로 -- 등급처럼 측정값이지 점수판이 아니다. */}
        {paid && data?.ai_budget_left_pct != null && <span className="pick-quota">{quotaLine(data.ai_budget_left_pct)}</span>}
        {loading && data && <span className="pick-status">다시 고르는 중…</span>}
        {/* 무료 사용자에게 유료 기능이 있다는 걸 알리는 유일한 자리. 배지·강조 없이 링크 한 줄. */}
        {!paid && data && <a className="pick-plans-link" href="#plans">AI가 고르는 추천은 요금제에서</a>}
      </div>
      {data?.limit_reason && LIMIT_NOTE[data.limit_reason] && <p className="pick-limit">{LIMIT_NOTE[data.limit_reason]}</p>}
      {data?.comment && <p className="pick-comment">{data.comment}</p>}
      {/* 새로 기억한 게 있으면 그 자리에서 말한다 -- 몰래 쌓지 않는다는 게 보여야 한다. */}
      {remembered.length > 0 && <p className="pick-memory">기억해 둘게요: {remembered.join(" · ")}</p>}

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
                  onClick={() => logEvent("click", m.menu_item_id, ctx(m))}
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
                onClick={() => toggleSave(m)}
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
    )}
    <MemoryPanel premium={paid} refreshKey={memoryKey} />
    {/* 두 칸이 한 목록처럼 섞여 보이지 않게, 이 칸이 펼쳐졌을 때만 아래 목록에 이름을 붙인다. */}
    {showPicks && <h3 className="pick-title rec-list-title">목표 점수 순 전체</h3>}
    </>
  );
}
