import { useState } from "react";
import { track } from "../../constants";
import { grantHealthConsent, withdrawHealthConsent } from "../auth/api";

// 성별·키·몸무게·나이(알레르기 포함)를 계정에 저장하기 전의 별도 동의 (개인정보보호법 23조 민감정보).
// 서버도 동의 없이는 이 칸을 저장·반환·AI 전달하지 않는다(app/auth/consent.py) -- 이 상자는 그걸
// 사용자에게 묻는 자리일 뿐 유일한 방어선이 아니다. 동의하지 않아도 값은 이 브라우저에 남아
// 한 끼 열량 계산은 그대로 된다. 고지 항목(목적·항목·기간·거부권과 불이익)은 법이 정한 넷이다.
export default function HealthConsent({ auth }) {
  const { user, refresh } = auth;
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!user) return null;

  async function run(fn, event) {
    setBusy(true);
    setError("");
    try {
      await fn();
      track(event, {});
      await refresh();
      setChecked(false);
    } catch {
      setError("처리하지 못했어요. 잠시 뒤 다시 시도해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  if (user.health_consent_at) {
    return (
      <p className="rec-note">
        내 정보가 계정에 저장돼 다른 기기에서도 이어집니다 ({user.health_consent_at.slice(0, 10)} 동의).{" "}
        <button
          type="button"
          className="pick-btn"
          disabled={busy}
          onClick={() => {
            if (window.confirm("동의를 철회하면 계정에 저장된 성별·키·몸무게·나이가 바로 지워지고, 이 브라우저에만 남아요. 철회할까요?"))
              run(withdrawHealthConsent, "health_consent_withdraw");
          }}
        >
          동의 철회
        </button>
        {error && <span role="status"> {error}</span>}
      </p>
    );
  }

  return (
    <div className="rec-consent">
      <p className="rec-consent-title">내 정보를 계정에도 저장할까요? (선택)</p>
      <ul>
        <li><b>항목</b> 성별, 키, 몸무게, 나이, 알레르기</li>
        <li><b>목적</b> 한 끼 적정 열량 계산, 알레르기 메뉴 제외, 다른 기기와 설정 동기화, 유료 요금제의 AI 맞춤 추천(Anthropic, 미국으로 전송)</li>
        <li><b>보관</b> 동의 철회 또는 탈퇴 즉시 삭제</li>
        <li><b>거부할 수 있어요</b> 거부해도 이 브라우저에 저장돼 추천은 그대로 쓸 수 있고, 다른 기기와 AI 추천에만 반영되지 않습니다.</li>
      </ul>
      <label className="rec-check">
        <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
        건강 관련 민감정보 수집·이용에 동의합니다
      </label>
      <button
        type="button"
        className="pick-btn"
        disabled={!checked || busy}
        onClick={() => run(grantHealthConsent, "health_consent_grant")}
      >
        {busy ? "저장하는 중…" : "동의하고 계정에 저장"}
      </button>
      {error && <span className="loading" role="status">{error}</span>}
      <p className="rec-note">
        자세한 내용은 <a href="/privacy/">개인정보 처리방침</a>에 있습니다.
      </p>
    </div>
  );
}
