import { useCallback, useEffect, useState } from "react";
import { getToken, setToken } from "../../api";
import { fetchAuthStatus, fetchMe } from "./api";

// 카카오 콜백이 프론트를 ?token=... 으로 열어 준다. 토큰을 localStorage로 옮긴 즉시
// 주소창에서 지운다 -- 주소를 공유하거나 히스토리에 남으면 그게 곧 계정 유출이다.
// 해시(#recommend 등)는 라우팅이라 건드리지 않는다.
function takeTokenFromUrl() {
  const params = new URLSearchParams(location.search);
  const token = params.get("token");
  const failed = params.get("auth_error");
  if (!token && !failed) return { failed: false };
  if (token) setToken(token);
  params.delete("token");
  params.delete("auth_error");
  const qs = params.toString();
  history.replaceState(null, "", `${location.pathname}${qs ? `?${qs}` : ""}${location.hash}`);
  return { failed: !!failed };
}

/** 로그인 상태 한 곳. App에서 한 번만 부르고 필요한 화면에 내려 준다. */
export function useAuth() {
  const [user, setUser] = useState(null);
  const [enabled, setEnabled] = useState(false); // 서버가 로그인을 켜 뒀는지
  const [error, setError] = useState("");
  // 첫 렌더에서 "로그인 안 됨"을 잠깐 보여줬다가 사용자가 뜨면 화면이 튄다.
  // 토큰이 있으면 확인이 끝날 때까지 loading으로 둔다.
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (takeTokenFromUrl().failed) setError("로그인에 실패했습니다. 다시 시도해 주세요.");

    fetchAuthStatus()
      .then((s) => setEnabled(!!s.enabled))
      .catch(() => setEnabled(false));

    if (!getToken()) return setLoading(false);
    fetchMe()
      .then(setUser)
      .catch((e) => {
        // 만료·위조 토큰은 들고 있어 봐야 매 요청이 401이다. 조용히 버리고 비로그인으로.
        if (e.status === 401) setToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return { user, enabled, loading, error, logout };
}
