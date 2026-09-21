import { useState } from "react";
import { formatDistance, track } from "../../constants";
import { logEvent } from "../auth/api";
import { nutritionLine, storeMapUrl } from "../recommend/format";
import { postChat } from "./api";

// "대화로 찾기". 무료는 조건 검색(문장 -> 조건, LLM 없음), premium 은 AI 대화.
// 대화와 조건은 이 컴포넌트가 들고 있고 서버는 저장하지 않는다 -- 새로고침하면 처음부터다.
const EXAMPLES = ["매운 거 말고 단백질 많은 거", "700kcal 이하 치킨", "맥날 빼고 버거"];
const HISTORY_SENT = 8; // 서버가 다시 6턴으로 자른다. 여기선 전송량만 줄인다.

export default function ChatPanel({ pos, premium = false }) {
  const [turns, setTurns] = useState([]); // { role, text, items?, source? }
  const [filters, setFilters] = useState(null);
  const [chips, setChips] = useState([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function send({ message = "", remove = null }) {
    if (busy) return;
    const text = message.trim();
    if (!text && !remove) return;
    setBusy(true);
    setError("");
    const history = turns.slice(-HISTORY_SENT).map((t) => ({ role: t.role, text: t.text }));
    if (text) setTurns((t) => [...t, { role: "user", text }]);
    try {
      const res = await postChat({
        message: text,
        filters,
        remove,
        history,
        ...(pos ? { lat: pos.lat, lng: pos.lng } : {}),
      });
      setFilters(res.filters);
      setChips(res.chips);
      setTurns((t) => [...t, { role: "assistant", text: res.reply, items: res.items, source: res.source }]);
      track("chat_turn", { source: res.source, understood: res.understood, removed: !!remove });
      setDraft("");
    } catch {
      setError("답을 받지 못했습니다. 잠시 뒤 다시 보내 주세요.");
      if (text) setTurns((t) => t.slice(0, -1)); // 보내지 못한 말은 입력칸에 그대로 둔다
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="chat-section" aria-labelledby="chat-title">
      <div className="pick-head">
        <h3 id="chat-title" className="pick-title">대화로 찾기</h3>
        <span className="pick-basis">{premium ? "AI 대화" : "조건 검색"}</span>
      </div>

      {turns.length === 0 && (
        <div className="chat-examples">
          <p className="rec-note">
            {premium
              ? "먹고 싶은 걸 편하게 말해 보세요. 설정과 기억을 참고해 골라 드립니다."
              : "찾는 조건을 말로 적어 보세요. 이런 말을 알아듣습니다."}
          </p>
          {EXAMPLES.map((e) => (
            <button key={e} type="button" className="pick-btn" onClick={() => send({ message: e })} disabled={busy}>
              {e}
            </button>
          ))}
        </div>
      )}

      <ol className="chat-log" aria-live="polite">
        {turns.map((t, i) => (
          <li key={i} className={`chat-turn chat-${t.role}`}>
            <span className="chat-who">{t.role === "user" ? "나" : "Dining Maps"}</span>
            <p className="chat-text">{t.text}</p>
            {t.items?.length > 0 && (
              <div className="menu-list chat-items">
                {t.items.map((m, pos) => (
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
                          onClick={() => logEvent("click", m.menu_item_id, { surface: "chat", position: pos })}
                        >
                          📍 {m.nearest_store.branch_name ?? m.restaurant_name} {formatDistance(m.nearest_store.distance_m)} ↗
                        </a>
                      )}
                      <span className="menu-item-meta" style={{ marginLeft: "auto", alignSelf: "flex-end" }}>
                        {nutritionLine(m)}
                      </span>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </li>
        ))}
        {busy && <li className="chat-turn chat-assistant chat-pending">고르는 중…</li>}
      </ol>

      {chips.length > 0 && (
        <div className="chat-chips" aria-label="지금 걸린 조건">
          {chips.map((c) => (
            <span key={c.key} className="chat-chip">
              {c.label}
              <button
                type="button"
                className="chat-chip-x"
                aria-label={`${c.label} 조건 지우기`}
                onClick={() => send({ remove: c.key })}
                disabled={busy}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <form
        className="chat-form"
        onSubmit={(e) => {
          e.preventDefault();
          send({ message: draft });
        }}
      >
        <label className="rec-field chat-input">
          <span className="sr-only">메시지</span>
          <input
            type="text"
            maxLength={300}
            placeholder={premium ? "예: 어제 과식해서 오늘은 가볍게" : "예: 700kcal 이하 치킨"}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
        </label>
        <button type="submit" className="pick-btn" disabled={busy || !draft.trim()}>
          보내기
        </button>
      </form>
      {error && <p className="loading">{error}</p>}
    </section>
  );
}
