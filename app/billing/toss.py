"""토스페이먼츠 서버 API. 토스와 말을 섞는 코드는 이 파일에만 있다.

app/auth/kakao.py 와 같이 stdlib urllib 만 쓴다 -- Lambda 번들에 HTTP 라이브러리를 더 넣지 않는다.

환경변수:
    TOSS_SECRET_KEY  -- 시크릿 키. 테스트 키(test_sk_...)면 실제 결제 없이 끝까지 돈다.
                        없으면 결제 API 전체가 503 이고 프론트는 요금제 페이지에서 결제 버튼을 비활성화한다.
프론트의 클라이언트 키(VITE_TOSS_CLIENT_KEY)와 같은 상점의 짝이어야 한다.

테스트는 transport 를 바꿔 끼운다 -- 실제 네트워크 없이 승인 성공·실패·중복을 흉내 낸다.
"""
import base64
import json
import os
import urllib.error
import urllib.request

API_BASE = "https://api.tosspayments.com/v1"
TIMEOUT_SECONDS = 15

# 취소·환불·만료로 볼 토스 결제 상태. 이 중 하나면 이용권을 즉시 무효화한다.
REVOKING_STATUSES = ("CANCELED", "PARTIAL_CANCELED", "EXPIRED", "ABORTED")


class TossError(RuntimeError):
    """토스 쪽 실패(HTTP 4xx/5xx, 네트워크). code 는 토스 오류 코드(있으면)."""

    def __init__(self, message: str, code: str | None = None, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


def is_configured() -> bool:
    return bool(os.environ.get("TOSS_SECRET_KEY"))


def _auth_header() -> str:
    secret = os.environ.get("TOSS_SECRET_KEY")
    if not secret:
        raise TossError("TOSS_SECRET_KEY 환경변수가 없어 결제를 쓸 수 없습니다.")
    return "Basic " + base64.b64encode(f"{secret}:".encode()).decode()


def _urllib_transport(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode(errors="replace") or "{}")
        except json.JSONDecodeError:
            return e.code, {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise TossError(f"toss 호출 실패: {e}") from e


# 테스트가 갈아 끼우는 자리. (method, url, headers, body) -> (status, json)
transport = _urllib_transport


def _call(method: str, path: str, body: dict | None = None) -> dict:
    headers = {"Authorization": _auth_header(), "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    status, payload = transport(method, f"{API_BASE}{path}", headers, data)
    if status >= 400:
        # 토스 오류 본문: {"code": "...", "message": "..."}. 메시지는 사용자에게 그대로 보여도 되는 문장이다.
        raise TossError(payload.get("message") or f"toss HTTP {status}", payload.get("code"), status)
    return payload


def confirm(payment_key: str, order_id: str, amount: int) -> dict:
    """결제 승인. 금액·주문번호가 토스 쪽 기록과 다르면 토스가 거절한다(우리도 승인 전에 대조한다)."""
    return _call("POST", "/payments/confirm", {"paymentKey": payment_key, "orderId": order_id, "amount": amount})


def fetch_payment(payment_key: str) -> dict:
    """결제 조회. 웹훅은 서명이 없으므로 본문을 믿지 않고 이걸로 다시 확인한다."""
    return _call("GET", f"/payments/{payment_key}")
