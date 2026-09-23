import { useEffect, useRef, useState } from "react";
import { track } from "../../constants";
import { startLogin } from "../auth/api";
import { PLAN_LABEL, quotaLine } from "../auth/plan";
import { checkout, confirmPayment, fetchBillingMe, fetchPlans } from "./api";
import { CLIENT_KEY, requestCardPayment } from "./toss";

// 요금제 페이지 (#plans). 사이드바 NAV 에는 없고 맞춤 추천·대화의 "요금제" 링크로 들어온다.
// 30일 선불 이용권 하나를 판다. 자동 갱신 없음 -- 다시 사야 이어진다(연장은 만료일 다음부터).
// 판촉 배지·할인 문구는 쓰지 않는다(DESIGN.md). 사실만: 무엇이 되고, 얼마이고, 얼마나 남았는지.
// payReturn: 토스에서 돌아온 결과(App 이 주소에서 읽어 준다). success 면 여기서 서버 승인을 부른다.
const ROWS = [
  ["가격 (30일 선불)", "무료", (p) => `${p.price_krw.toLocaleString()}원`],
  ["맞춤 추천", "설정·기록으로 학습", () => "AI가 고르고 이유를 씀"],
  ["대화로 찾기", "조건 검색", () => "AI 대화"],
  ["AI 메모리", "—", () => "있음"],
  ["모델", "—", (p) => MODEL_LABEL[p.model] ?? p.model],
  ["하루 AI 호출", "—", (p) => `${p.daily_limit}회`],
];
const MODEL_LABEL = { "claude-haiku-4-5": "Claude Haiku 4.5", "claude-sonnet-5": "Claude Sonnet 5" };

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric" }) : "");

export default function PlansView({ auth, payReturn }) {
  const { user, enabled, loading } = auth;
  const [plans, setPlans] = useState([]);
  const [me, setMe] = useState(null); // /api/billing/me
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState(null); // { kind: "done" | "error", text }

  useEffect(() => {
    fetchPlans().then(setPlans).catch(() => setPlans([]));
  }, []);

  const reloadMe = () => (user ? fetchBillingMe().then(setMe).catch(() => setMe(null)) : Promise.resolve(setMe(null)));
  useEffect(() => {
    reloadMe();
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  // 토스 성공 주소로 돌아온 경우: 로그인 확인이 끝난 뒤 한 번만 서버 승인을 부른다.
  // user 는 승인 뒤 auth.refresh() 로 새 객체가 되어 effect 가 다시 돈다 -- ref 로 두 번째 승인을 막는다.
  const confirmStarted = useRef(false);
  useEffect(() => {
    if (!payReturn || loading || confirmStarted.current) return;
    if (payReturn.status === "fail") {
      setNotice({ kind: "error", text: `결제가 되지 않았어요. ${payReturn.message ?? ""}`.trim() });
      return;
    }
    if (!user) {
      setNotice({ kind: "error", text: "로그인 상태가 풀려 결제를 확인하지 못했어요. 다시 로그인하면 이어서 확인합니다." });
      return;
    }
    confirmStarted.current = true;
    setBusy("confirm");
    confirmPayment({ payment_key: payReturn.payment_key, order_id: payReturn.order_id, amount: payReturn.amount })
      .then((ent) => {
        track("purchase", { plan: ent.plan });
        setNotice({ kind: "done", text: `${PLAN_LABEL[ent.plan]} 이용권이 시작됐어요. ${fmtDate(ent.ends_at)}까지 AI 추천과 대화를 쓸 수 있어요.` });
        auth.refresh?.();
        return reloadMe();
      })
      .catch((e) => setNotice({ kind: "error", text: e.status === 402 ? "카드사에서 결제를 승인하지 않았어요." : "결제 확인에 실패했어요. 결제가 됐다면 잠시 뒤 다시 열어 주세요." }))
      .finally(() => setBusy(""));
  }, [payReturn, loading, user]); // eslint-disable-line react-hooks/exhaustive-deps

  async function buy(plan) {
    setNotice(null);
    setBusy(plan.key);
    track("begin_checkout", { plan: plan.key });
    try {
      const order = await checkout(plan.key);
      await requestCardPayment(order, clientKey); // 결제창으로 넘어간다. 돌아오면 payReturn 으로 이어진다.
    } catch (e) {
      // 토스 SDK 는 사용자가 창을 닫아도 reject 한다 -- 오류로 보이지 않게 조용히 둔다.
      if (e?.code === "USER_CANCEL") return setBusy("");
      setNotice({ kind: "error", text: e.status === 409 ? "지금 쓰는 요금제가 끝난 뒤에 다른 요금제를 살 수 있어요." : "결제를 시작하지 못했어요. 잠시 뒤 다시 시도해 주세요." });
      setBusy("");
    }
  }

  const current = me?.plan ?? user?.plan ?? "free";
  // 클라이언트 키는 서버가 내려 주는 게 우선(시크릿 키와 같은 곳에서 관리). 없으면 빌드 변수.
  const clientKey = me?.client_key || CLIENT_KEY;
  const canPay = !!me?.payments_enabled && !!clientKey;

  function action(plan) {
    if (!enabled) return null;
    if (!user) {
      return (
        <button type="button" className="auth-btn on" onClick={() => { track("login_start", { provider: "kakao", surface: "plans" }); startLogin(); }}>
          카카오로 로그인
        </button>
      );
    }
    const same = current === plan.key;
    const blocked = current !== "free" && !same;
    return (
      <button
        type="button"
        className="pick-btn plans-buy"
        disabled={!canPay || blocked || !!busy}
        title={!canPay ? "결제가 아직 준비되지 않았어요." : blocked ? "지금 쓰는 요금제가 끝난 뒤에 살 수 있어요." : undefined}
        onClick={() => buy(plan)}
      >
        {busy === plan.key ? "결제창 여는 중…" : same ? "30일 연장" : `${plan.label} 시작`}
      </button>
    );
  }

  return (
    <section className="plans">
      <h2>요금제</h2>
      <p className="legend-hint">
        무료로도 학습형 추천과 조건 검색 대화를 쓸 수 있어요. 유료는 30일 선불 이용권이고 자동으로 갱신되지 않아요.
      </p>

      {user && (
        <p className="plans-status" aria-live="polite">
          지금 요금제 <b>{PLAN_LABEL[current]}</b>
          {me?.plan_ends_at && <> · {fmtDate(me.plan_ends_at)}까지</>}
          {me?.ai_budget_left_pct != null && <> · {quotaLine(me.ai_budget_left_pct)}</>}
        </p>
      )}
      {busy === "confirm" && <p className="loading">결제를 확인하는 중…</p>}
      {notice && <p className={notice.kind === "done" ? "plans-done" : "loading"} role="status">{notice.text}</p>}

      <div className="about-scroll">
        <table className="dash-table plans-table">
          <thead>
            <tr>
              <th scope="col">항목</th>
              <th scope="col">Free</th>
              {plans.map((p) => <th key={p.key} scope="col">{p.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {ROWS.map(([label, free, paid]) => (
              <tr key={label}>
                <th scope="row">{label}</th>
                <td>{free}</td>
                {plans.map((p) => <td key={p.key}>{paid(p)}</td>)}
              </tr>
            ))}
            <tr>
              <th scope="row"><span className="sr-only">선택</span></th>
              <td>{user && current === "free" ? "지금 요금제" : "—"}</td>
              {plans.map((p) => <td key={p.key}>{action(p)}</td>)}
            </tr>
          </tbody>
        </table>
      </div>

      <p className="legend-hint" style={{ marginTop: 16 }}>
        AI 추천·대화는 이용권마다 정해진 AI 사용량 안에서 동작해요. 다 쓰면 그 기간에는 무료 방식(설정·기록 기반 추천, 조건 검색)으로 답해요.
        유료 기능을 쓸 때 추천 설정과 최근 본 브랜드, 대화 내용이 계정 식별자 없이 Anthropic API 로 전송돼요.
        영양정보는 브랜드 공개 자료 기준이며 의학적 조언이 아니에요.
      </p>
      {!canPay && user && (
        <p className="legend-hint">결제는 아직 준비 중이에요. 준비되면 이 자리에서 바로 시작할 수 있어요.</p>
      )}
    </section>
  );
}
