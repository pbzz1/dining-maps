import { useEffect, useRef, useState } from "react";
import { track } from "../../constants";
import { startLogin } from "../auth/api";
import ChatPanel, { CloseButton } from "./ChatPanel";

// "대화로 찾기"를 어느 탭에서든 여는 떠 있는 단추. 맞춤 추천 탭 안에 묻혀 있으면
// 그 탭을 끝까지 내려야 보였다 -- 필요할 때 부르는 도구라 화면 구석에 둔다.
// 서버에 로그인이 꺼져 있으면 쓸 수 없는 기능이라 단추도 그리지 않는다(LoginButton과 같은 이유).
// 비로그인은 단추는 보이고, 열면 로그인 안내 -- 이런 기능이 있다는 걸 알리는 게 목적.

// 위치는 맞춤 추천이 localStorage에 둔 것을 연 순간에 읽는다. useLocalStorage 훅은
// 인스턴스끼리 동기화되지 않아서, 훅으로 들면 마운트 시점 값에 멈춰 버린다.
function readPos() {
  try {
    return JSON.parse(localStorage.getItem("recommend.pos")) ?? null;
  } catch {
    return null;
  }
}

export default function ChatFab({ auth, hidden = false }) {
  const { user, enabled, loading } = auth;
  const [open, setOpen] = useState(false);
  // 한 번 열면 닫아도 언마운트하지 않는다 -- 닫았다 다시 열었을 때 대화가 남아 있게.
  const [opened, setOpened] = useState(false);
  const [pos, setPos] = useState(null);
  const fabRef = useRef(null);
  const panelRef = useRef(null);

  function show() {
    setPos(readPos());
    setOpen(true);
    setOpened(true);
    track("chat_open", { logged_in: !!user });
  }

  const close = () => setOpen(false);

  // 열리면 입력칸(비로그인은 로그인 단추)으로, 닫히면 다시 단추로 포커스를 옮긴다.
  // 단추는 열려 있는 동안 그리지 않으니 닫힌 뒤 렌더에서 잡아야 한다.
  useEffect(() => {
    if (open) panelRef.current?.querySelector("input, .auth-btn")?.focus();
    else if (opened) fabRef.current?.focus();
  }, [open, opened]);

  if (!enabled || loading) return null;

  const premium = user?.plan === "premium";
  return (
    <div className="chat-fab-root" style={hidden ? { display: "none" } : undefined}>
      {opened && (
        <div
          ref={panelRef}
          id="chat-fab-panel"
          className="chat-fab-panel"
          hidden={!open}
          onKeyDown={(e) => e.key === "Escape" && close()}
        >
          {user ? (
            // 계정이 바뀌면 이전 사람의 대화를 이어 보여주지 않는다.
            <ChatPanel key={user.id} pos={pos} premium={premium} onClose={close} />
          ) : (
            <section className="chat-section" aria-labelledby="chat-title">
              <div className="pick-head">
                <h3 id="chat-title" className="pick-title">대화로 찾기</h3>
                <CloseButton onClick={close} />
              </div>
              <p className="rec-note">
                "700kcal 이하 치킨"처럼 말로 적으면 조건에 맞는 메뉴를 골라 드립니다. 로그인하면 쓸 수 있어요.
              </p>
              <button
                type="button"
                className="auth-btn on"
                onClick={() => {
                  track("login_start", { provider: "kakao", surface: "chat_fab" });
                  startLogin();
                }}
              >
                카카오로 로그인
              </button>
            </section>
          )}
        </div>
      )}
      {!open && (
        <button
          ref={fabRef}
          type="button"
          className="chat-fab"
          aria-expanded={false}
          aria-controls={opened ? "chat-fab-panel" : undefined}
          onClick={show}
        >
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />
          </svg>
          대화로 찾기
        </button>
      )}
    </div>
  );
}
