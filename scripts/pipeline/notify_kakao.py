"""카카오톡 '나에게 보내기'로 알림 전송 (크롤 실패 등).

    KAKAO_REST_API_KEY=... KAKAO_REFRESH_TOKEN=... python scripts/pipeline/notify_kakao.py "메시지"

- refresh token으로 access token을 발급받아 메모 API로 보낸다 (stdlib만 사용).
- 환경변수가 없으면 조용히 건너뛴다 -- 알림 미설정이 크롤 파이프라인을 깨면 안 된다.
- 카카오 refresh token은 유효기간 2개월이고, 만료 1개월 전부터는 갱신 응답에
  새 refresh_token이 실려 온다. Actions에서는 secret을 스스로 못 바꾸므로
  로그에 경고만 남긴다 -- 경고가 보이면 GitHub secret을 새 값으로 갱신할 것.
  (갱신을 놓치면 카톡 알림만 죽고 크롤은 정상 -- GitHub 기본 실패 메일이 백업.)

최초 토큰 발급 방법은 docs/kakao_notify_setup.md 참고.
"""
import json
import os
import sys
import urllib.parse
import urllib.request


def post(url, data, headers=None):
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    api_key = os.environ.get("KAKAO_REST_API_KEY")
    refresh = os.environ.get("KAKAO_REFRESH_TOKEN")
    if not api_key or not refresh:
        print("KAKAO_REST_API_KEY/KAKAO_REFRESH_TOKEN 없음 -- 카톡 알림 건너뜀")
        return
    message = sys.argv[1] if len(sys.argv) > 1 else "(빈 메시지)"

    token_req = {"grant_type": "refresh_token", "client_id": api_key, "refresh_token": refresh}
    # 카카오 앱의 [보안]에서 Client Secret을 "사용함"으로 켠 경우에만 필요
    if os.environ.get("KAKAO_CLIENT_SECRET"):
        token_req["client_secret"] = os.environ["KAKAO_CLIENT_SECRET"]
    tok = post("https://kauth.kakao.com/oauth/token", token_req)
    if "refresh_token" in tok:
        print("::warning::카카오 refresh token이 곧 만료됩니다. "
              "GitHub secret KAKAO_REFRESH_TOKEN을 로그의 새 값으로 갱신하세요.")
        print(f"NEW_REFRESH_TOKEN={tok['refresh_token']}")

    template = {"object_type": "text", "text": message[:1900],
                "link": {"web_url": "https://github.com/pbzz1/dining-maps/actions"}}
    post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        {"template_object": json.dumps(template, ensure_ascii=False)},
        headers={"Authorization": f"Bearer {tok['access_token']}"},
    )
    print("카톡 알림 전송 완료")


if __name__ == "__main__":
    main()
