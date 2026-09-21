"""사용자가 AI 메모리를 보고, 직접 적고, 지우는 API. 전부 로그인 필요.

요금제와 무관하게 열어 둔다 -- 메모리를 추천에 쓰는 건 premium 뿐이지만, 자기 정보를 보고
지울 권리는 요금제로 가를 게 아니다(다운그레이드한 사용자도 남은 기억을 지울 수 있어야 한다).
"""
from fastapi import APIRouter, Depends, HTTPException, Response

from app.auth.deps import current_user
from app.db import connect, get_connection
from app.memory import store
from app.memory.schemas import MemoryIn, MemoryOut

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("", response_model=list[MemoryOut])
def list_memory(user: dict = Depends(current_user)):
    conn = get_connection()
    try:
        return [MemoryOut(**r) for r in store.list_facts(conn, user["id"])]
    finally:
        conn.close()


@router.post("", response_model=list[MemoryOut], status_code=201)
def add_memory(payload: MemoryIn, user: dict = Depends(current_user)):
    """사용자가 직접 적는 한 줄("점심은 회사 근처에서 먹음"). 목록 전체를 돌려준다 --
    프론트가 다시 부를 필요 없이 그대로 그린다."""
    if not store.normalize(payload.fact):
        raise HTTPException(status_code=422, detail="빈 내용은 저장할 수 없습니다.")
    with connect() as conn:
        store.add_facts(conn, user["id"], [payload.fact], source="user")
        return [MemoryOut(**r) for r in store.list_facts(conn, user["id"])]


@router.delete("/{memory_id}", status_code=204, response_class=Response)
def delete_memory(memory_id: int, user: dict = Depends(current_user)):
    with connect() as conn:
        # user_id 조건을 같이 건다 -- 남의 id 를 넣어도 지워지지 않고 404가 난다.
        deleted = conn.execute(
            "DELETE FROM user_memory WHERE id = %s AND user_id = %s", (memory_id, user["id"])
        ).rowcount
    if not deleted:
        raise HTTPException(status_code=404, detail="없는 메모리입니다.")
    return Response(status_code=204)
