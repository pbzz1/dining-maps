"""건강 관련 민감정보의 별도 동의 (개인정보보호법 23조).

성별·키·몸무게·나이는 한 끼 열량 계산용, 알레르기는 메뉴 제외용이지만 합쳐 보면
건강 상태를 드러내는 정보라 민감정보로 다룬다. 동의(app_user.health_consent_at)가
없으면 이 칸들은 서버에 저장하지도(PUT /api/profile), 돌려주지도(GET), LLM 에
보내지도(app/recommend/personal.py load_profile) 않는다. 프론트는 브라우저에만 두고
계속 쓴다 -- 동의를 안 해도 기능이 막히지 않아야 동의가 강제가 아니다.

동의를 철회하면 저장돼 있던 값을 그 자리에서 지운다(withdraw). 동의 없이 남아 있는
예전 행은 매일 도는 scripts/maintenance/purge_expired.py 가 지운다.
"""

HEALTH_FIELDS = ("sex", "height_cm", "weight_kg", "age", "allergies")


def has_health_consent(conn, user_id: int) -> bool:
    row = conn.execute("SELECT health_consent_at FROM app_user WHERE id = %s", (user_id,)).fetchone()
    return bool(row and row["health_consent_at"])


def strip_health(profile: dict) -> dict:
    """민감 칸을 None 으로 비운 사본."""
    return {**profile, **{f: None for f in HEALTH_FIELDS if f in profile}}


def grant(conn, user_id: int) -> None:
    conn.execute(
        "UPDATE app_user SET health_consent_at = COALESCE(health_consent_at, now()) WHERE id = %s", (user_id,)
    )


def withdraw(conn, user_id: int) -> None:
    conn.execute("UPDATE app_user SET health_consent_at = NULL WHERE id = %s", (user_id,))
    conn.execute(
        f"UPDATE user_profile SET {', '.join(f'{f} = NULL' for f in HEALTH_FIELDS)}, updated_at = now() WHERE user_id = %s",
        (user_id,),
    )
    # 캐시된 AI 추천은 그 값으로 만든 결과다 -- 동의를 거둔 정보가 결과로 남아 있으면 안 된다.
    conn.execute("DELETE FROM llm_reco_cache WHERE user_id = %s", (user_id,))
