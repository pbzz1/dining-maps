import { useEffect, useState } from "react";
import { addMemory, deleteMemory, fetchMemory } from "./api";

// "AI가 기억하는 것" -- premium 추천이 행동에서 알아낸 취향 + 사용자가 직접 적은 것.
// 무엇을 믿고 추천하는지 사용자가 보고 지울 수 있어야 한다(특히 신체정보를 다루는 서비스라서).
// refreshKey: 추천이 새로 기억할 때마다 바뀐다.
// premium: 아니면 추가 입력칸을 숨긴다(추천에 쓰이지 않으니). 남아 있는 기억은 보고 지울 수 있다.
export default function MemoryPanel({ premium, refreshKey }) {
  const [facts, setFacts] = useState(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchMemory()
      .then((list) => !cancelled && setFacts(list))
      .catch(() => !cancelled && setFacts([]));
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  async function add(e) {
    e.preventDefault();
    const fact = draft.trim();
    if (!fact) return;
    setError("");
    try {
      setFacts(await addMemory(fact));
      setDraft("");
    } catch {
      setError("저장하지 못했습니다. 60자 이내로 적어 주세요.");
    }
  }

  async function remove(id) {
    setFacts((list) => list.filter((f) => f.id !== id)); // 먼저 지우고, 실패하면 다시 불러온다
    try {
      await deleteMemory(id);
    } catch {
      setFacts(await fetchMemory().catch(() => []));
    }
  }

  // free 이고 남은 기억도 없으면 보여줄 게 없다.
  if (facts === null || (!premium && facts.length === 0)) return null;

  return (
    <details className="rec-detail mem-panel">
      <summary className="rec-detail-summary">
        <span className="rec-detail-title">AI가 기억하는 것</span>
        <span className="rec-detail-hint">{facts.length ? `${facts.length}개` : "아직 없음"}</span>
      </summary>
      <div className="rec-detail-body">
        <p className="rec-note">
          오늘의 추천을 고를 때 참고합니다. 틀린 건 지우면 다음 추천부터 빠집니다.
        </p>
        {facts.length > 0 && (
          <ul className="mem-list">
            {facts.map((f) => (
              <li key={f.id} className="mem-item">
                <span className="mem-fact">{f.fact}</span>
                <span className="mem-source">{f.source === "ai" ? "AI가 알아냄" : "직접 적음"}</span>
                <button type="button" className="pick-btn" onClick={() => remove(f.id)} aria-label={`"${f.fact}" 지우기`}>
                  지우기
                </button>
              </li>
            ))}
          </ul>
        )}
        {premium && (
          <form className="mem-add" onSubmit={add}>
            <label className="rec-field mem-add-field">
              <span className="rec-field-label">직접 알려주기</span>
              <input
                type="text"
                maxLength={60}
                placeholder="예: 점심은 회사 근처에서 먹어요"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
            </label>
            <button type="submit" className="pick-btn" disabled={!draft.trim()}>
              추가
            </button>
          </form>
        )}
        {error && <p className="loading">{error}</p>}
      </div>
    </details>
  );
}
