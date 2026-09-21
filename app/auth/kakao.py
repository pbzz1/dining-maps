"""카카오 OAuth 호출. 카카오 서버와 말을 섞는 코드는 이 파일에만 있다.

stdlib urllib 만 쓴다 -- scripts/pipeline/notify_kakao.py 와 같은 방식이고,
Lambda 번들에 HTTP 라이브러리를 하나 더 넣지 않기 위해서다.

필요한 환경변수 (developers.kakao.com 앱 설정과 짝을 맞춰야 한다):
    KAKAO_REST_API_KEY   -- 크롤/알림이 이미 쓰는 그 키와 동일한 앱의 REST API 키
    KAKAO_REDIRECT_URI   -- 이 API의 /api/auth/kakao/callback 전체 URL.
                            카카오 앱에 등록된 값과 문자 하나까지 같아야 한다.
    KAKAO_CLIENT_SECRET  -- 앱 [보안]에서 Client Secret을 '사용함'으로 켠 경우만
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
PROFILE_URL = "https://kapi.kakao.com/v2/user/me"

PROVIDER = "kakao"


class KakaoError(RuntimeError):
    """카카오 쪽 실패. 라우터가 502로 바꿔 내보낸다."""


def is_configured() -> bool:
    """로그인 기능을 켤 수 있는 상태인지. 프론트가 로그인 버튼을 보일지 결정한다."""
    return bool(os.environ.get("KAKAO_REST_API_KEY") and os.environ.get("KAKAO_REDIRECT_URI"))


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise KakaoError(f"{name} 환경변수가 없어 카카오 로그인을 쓸 수 없습니다.")
    return value


def authorize_url(state: str) -> str:
    params = {
        "client_id": _require("KAKAO_REST_API_KEY"),
        "redirect_uri": _require("KAKAO_REDIRECT_URI"),
        "response_type": "code",
        # 닉네임만 받는다. 이메일·생일 등은 추천에 쓰지 않으므로 요구하지 않는다 --
        # 동의 항목이 많을수록 로그인 이탈이 늘고, 안 쓰는 개인정보는 부채다.
        "scope": "profile_nickname",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def _post(url: str, data: dict, headers: dict | None = None) -> dict:
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        # 카카오는 실패 원인을 본문 JSON(error_code)에 담아 준다. 사용자에겐 안 보이고
        # 서버 로그로만 남긴다 -- 본문에 코드/키 힌트가 섞여 나올 수 있다.
        body = e.read().decode(errors="replace")[:500]
        raise KakaoError(f"kakao HTTP {e.code}: {body}") from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise KakaoError(f"kakao 호출 실패: {e}") from e


def exchange_code(code: str) -> str:
    """인가 코드 -> 카카오 액세스 토큰. 이 토큰은 프로필 조회 한 번에만 쓰고 버린다."""
    body = {
        "grant_type": "authorization_code",
        "client_id": _require("KAKAO_REST_API_KEY"),
        "redirect_uri": _require("KAKAO_REDIRECT_URI"),
        "code": code,
    }
    if os.environ.get("KAKAO_CLIENT_SECRET"):
        body["client_secret"] = os.environ["KAKAO_CLIENT_SECRET"]
    token = _post(TOKEN_URL, body)
    if "access_token" not in token:
        raise KakaoError("kakao 토큰 응답에 access_token이 없습니다.")
    return token["access_token"]


def fetch_profile(access_token: str) -> tuple[str, str | None]:
    """(provider_uid, nickname). 닉네임은 동의를 거부하면 None 으로 온다."""
    req = urllib.request.Request(PROFILE_URL, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            me = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise KakaoError(f"kakao 프로필 HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise KakaoError(f"kakao 프로필 조회 실패: {e}") from e
    if "id" not in me:
        raise KakaoError("kakao 프로필 응답에 id가 없습니다.")
    nickname = (me.get("kakao_account") or {}).get("profile", {}).get("nickname")
    return str(me["id"]), nickname
