import { useEffect, useState } from "react";
import { track } from "../../constants";
import Skel, { SkelBlock } from "../../components/Skeleton";
import { deleteAccount, startLogin } from "../auth/api";
import { PLAN_LABEL } from "../auth/plan";
import { nutritionLine } from "../recommend/format";
import { fetchFavorites, removeFavorite } from "./api";

// 내 정보 (#me). 사이드바 NAV 에는 없고 상단바의 닉네임 단추로 들어온다.
// 탭 두 개: 즐겨찾기(맞춤 추천에서 "저장"한 메뉴) / 계정(요금제·로그아웃·탈퇴).
// 즐겨찾기가 기본 탭이다 -- 저장만 되고 다시 볼 곳이 없던 걸 메우려고 만든 화면이라서.
const TABS = [
  { key: "favorites", label: "즐겨찾기" },
  { key: "account", label: "계정" },
];

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric" }) : "");
const brandSearchUrl = (f) => `https://map.kakao.com/link/search/${encodeURIComponent(f.restaurant_name)}`;

export default function ProfileView({ auth, visible }) {
  const { user, enabled, loading, logout } = auth;
  const [tab, setTab] = useState("favorites");

  if (loading) return null;
  if (!user) {
    return (
      <section className="profile">
        <h2>내 정보</h2>
        <p className="legend-hint">로그인하면 맞춤 추천에서 저장한 메뉴를 여기서 모아 볼 수 있어요.</p>
        {enabled && (
          <button
            type="button"
            className="auth-btn on profile-login"
            onClick={() => {
              track("login_start", { provider: "kakao", surface: "profile" });
              startLogin();
            }}
          >
            카카오로 로그인
          </button>
        )}
      </section>
    );
  }

  return (
    <section className="profile">
      <h2>{user.nickname ?? "내 정보"}</h2>
      <p className="legend-hint">
        {PLAN_LABEL[user.plan] ?? "Free"} 요금제 · {fmtDate(user.created_at)} 가입
      </p>

      <div className="dash-tabs" role="tablist" aria-label="내 정보">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            id={`profile-tab-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls={`profile-panel-${t.key}`}
            className={`dash-tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`profile-panel-${tab}`} aria-labelledby={`profile-tab-${tab}`}>
        {tab === "favorites" ? (
          <Favorites visible={visible} />
        ) : (
          <Account user={user} logout={logout} />
        )}
      </div>
    </section>
  );
}

// visible: 이 화면은 한 번 열면 숨겨진 채 살아 있다(App 의 Pane). 맞춤 추천에서 새로 저장하고
// 돌아왔을 때 옛 목록이 보이지 않게, 다시 보일 때마다 불러온다.
function Favorites({ visible }) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    fetchFavorites()
      .then((list) => !cancelled && (setItems(list), setError("")))
      .catch(() => !cancelled && setError("즐겨찾기를 불러오지 못했어요. 잠시 뒤 다시 열어 주세요."));
    return () => {
      cancelled = true;
    };
  }, [visible]);

  async function remove(f) {
    setItems((list) => list.filter((i) => i.menu_item_id !== f.menu_item_id)); // 먼저 빼고, 실패하면 다시 불러온다
    track("favorite_remove", {});
    try {
      await removeFavorite(f.menu_item_id);
    } catch (e) {
      if (e.status === 404) return; // 이미 없음 -- 화면과 서버가 같은 상태다
      setError("해제하지 못했어요. 다시 시도해 주세요.");
      setItems(await fetchFavorites().catch(() => []));
    }
  }

  if (error && !items) return <p className="loading">{error}</p>;
  if (!items) {
    return (
      <SkelBlock label="즐겨찾기를 불러오는 중">
        <div className="menu-list">
          {[0, 1, 2].map((i) => <Skel key={i} h={88} r={12} />)}
        </div>
      </SkelBlock>
    );
  }
  if (items.length === 0) {
    return (
      <p className="rec-note">
        아직 저장한 메뉴가 없어요. <a href="#recommend">맞춤 추천</a>의 "오늘 당신에겐"에서 저장을 누르면 여기에 모여요.
      </p>
    );
  }

  return (
    <>
      <p className="rec-note">맞춤 추천에서 저장한 메뉴 {items.length}개 · 최근 저장한 순</p>
      {error && <p className="loading" role="status">{error}</p>}
      <div className="menu-list">
        {items.map((f) => (
          <article key={f.menu_item_id} className="menu-item">
            <div className="menu-item-head">
              <span className="menu-item-name">
                {f.restaurant_name} · {f.name}
              </span>
              <span className="menu-item-meta">
                {f.category}
                {f.price_krw != null && ` · ${f.price_krw.toLocaleString()}원`}
              </span>
            </div>
            <div className="nutrition-row">
              <a className="nutrient-badge" href={brandSearchUrl(f)} target="_blank" rel="noreferrer">
                📍 근처 {f.restaurant_name} 찾기 ↗
              </a>
              <span className="menu-item-meta" style={{ marginLeft: "auto", alignSelf: "flex-end" }}>
                {nutritionLine(f)}
              </span>
            </div>
            <div className="pick-actions">
              <span className="menu-item-meta">{fmtDate(f.saved_at)} 저장</span>
              <button
                type="button"
                className="pick-btn"
                onClick={() => remove(f)}
                aria-label={`${f.restaurant_name} ${f.name} 즐겨찾기 해제`}
              >
                즐겨찾기 해제
              </button>
            </div>
          </article>
        ))}
      </div>
    </>
  );
}

function Account({ user, logout }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function withdraw() {
    // 되돌릴 수 없는 동작이라 한 번 더 묻는다. 신체정보·기록·즐겨찾기가 전부 같이 지워진다.
    if (!window.confirm("탈퇴하면 추천 설정, 저장한 메뉴, AI 메모리가 모두 지워지고 되돌릴 수 없어요. 탈퇴할까요?")) return;
    setBusy(true);
    setError("");
    try {
      await deleteAccount();
      track("account_delete", {});
      logout();
    } catch {
      setError("탈퇴하지 못했어요. 잠시 뒤 다시 시도해 주세요.");
      setBusy(false);
    }
  }

  return (
    <dl className="profile-account">
      <div className="profile-row">
        <dt>요금제</dt>
        <dd>
          {PLAN_LABEL[user.plan] ?? "Free"}
          {user.plan_ends_at && ` · ${fmtDate(user.plan_ends_at)}까지`}
          {" "}
          <a href="#plans">요금제 보기</a>
        </dd>
      </div>
      <div className="profile-row">
        <dt>추천 설정</dt>
        <dd>
          목표·한 끼 상한·신체정보는 <a href="#recommend">맞춤 추천</a>에서 바꿔요.
        </dd>
      </div>
      <div className="profile-row">
        <dt>로그인</dt>
        <dd>
          카카오 계정
          <button type="button" className="pick-btn" onClick={logout}>
            로그아웃
          </button>
        </dd>
      </div>
      <div className="profile-row">
        <dt>탈퇴</dt>
        <dd>
          <button type="button" className="pick-btn" onClick={withdraw} disabled={busy}>
            {busy ? "탈퇴하는 중…" : "회원 탈퇴"}
          </button>
          {error && <span className="loading" role="status">{error}</span>}
        </dd>
      </div>
    </dl>
  );
}
