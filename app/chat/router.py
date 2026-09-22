from fastapi import APIRouter, Depends

from app.auth.deps import current_user
from app.chat.schemas import ChatIn, ChatOut
from app.chat.service import chat

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatOut)
def post_chat(body: ChatIn, user: dict = Depends(current_user)):
    """대화 한 턴. 로그인 필요 -- 개인 설정·기록·숨긴 메뉴 위에서 고르기 때문이다.
    무료는 규칙 파서(LLM 없음), 유료(이용권)는 Claude 대화(예산·하루 상한 있음)."""
    return chat(user, body)
