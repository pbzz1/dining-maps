import { track } from "../../constants";
import { startLogin } from "./api";

// 상단바 오른쪽 한 칸. 서버에 로그인이 꺼져 있으면(enabled=false) 아무것도 그리지 않는다 --
// 눌러도 안 되는 버튼은 없는 것만 못하다.
export default function LoginButton({ auth }) {
  const { user, enabled, loading, logout } = auth;
  if (!enabled || loading) return null;

  if (user) {
    return (
      <button type="button" className="auth-btn" onClick={logout} title="로그아웃">
        {user.nickname ?? "내 계정"}
        <span className="auth-btn-state">로그아웃</span>
      </button>
    );
  }
  return (
    <button
      type="button"
      className="auth-btn on"
      onClick={() => {
        track("login_start", { provider: "kakao" });
        startLogin();
      }}
    >
      카카오로 로그인
    </button>
  );
}
