"""메모리 읽고 쓰기. 라우터(사용자 조작)와 개인 추천(AI 추출)이 같은 규칙을 쓰도록 한 곳에 둔다."""

# ponytail: 사용자당 20개. 프롬프트에 전부 들어가므로 무한히 늘면 비용과 지연이 같이 는다.
# 넘치면 AI가 적은 오래된 것부터 지운다 -- 사용자가 직접 적은 건 사용자만 지운다.
MAX_FACTS = 20
MAX_FACT_LEN = 60


def normalize(fact: str) -> str | None:
    """공백 정리 + 길이 제한. 쓸 수 없으면 None."""
    fact = " ".join((fact or "").split())
    if not fact or len(fact) > MAX_FACT_LEN:
        return None
    return fact


def list_facts(conn, user_id) -> list[dict]:
    return conn.execute(
        "SELECT id, fact, source, created_at FROM user_memory WHERE user_id = %s ORDER BY created_at, id",
        (user_id,),
    ).fetchall()


def add_facts(conn, user_id, facts, source) -> list[str]:
    """새로 들어간 사실만 돌려준다(이미 있던 건 조용히 건너뜀). 커밋은 호출부가 한다."""
    added = []
    for raw in facts:
        fact = normalize(raw)
        if not fact:
            continue
        row = conn.execute(
            """INSERT INTO user_memory (user_id, fact, source) VALUES (%s, %s, %s)
               ON CONFLICT (user_id, fact) DO NOTHING RETURNING id""",
            (user_id, fact, source),
        ).fetchone()
        if row:
            added.append(fact)
    # 상한 초과분 정리: AI가 적은 것 중 오래된 순. 사용자 입력만으로 넘치면 그대로 둔다.
    conn.execute(
        """DELETE FROM user_memory WHERE id IN (
               SELECT id FROM user_memory WHERE user_id = %s AND source = 'ai'
               ORDER BY created_at, id
               LIMIT GREATEST((SELECT count(*) FROM user_memory WHERE user_id = %s) - %s, 0))""",
        (user_id, user_id, MAX_FACTS),
    )
    return added
