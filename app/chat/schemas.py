from pydantic import BaseModel, Field

from app.recommend.schemas import RecommendedMenuOut


class ChatFilters(BaseModel):
    """대화로 쌓인 조건. 서버는 저장하지 않고 브라우저가 들고 다니며 매번 보낸다."""

    goal: str | None = None
    max_calorie: float | None = None
    max_sodium: float | None = None
    exclude_drinks: bool | None = None
    include_groups: list[str] = []
    exclude_groups: list[str] = []
    include_brands: list[str] = []
    exclude_brands: list[str] = []
    include_words: list[str] = []
    spicy: str | None = Field(default=None, pattern="^(avoid|want)$")


class ChatTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    text: str = Field(max_length=600)


class ChatIn(BaseModel):
    # 빈 메시지 + remove 는 "칩 하나 지우고 다시 골라줘"다.
    message: str = Field(default="", max_length=300)
    filters: ChatFilters | None = None
    remove: str | None = Field(default=None, max_length=60)
    # premium 대화의 이전 턴. 무료는 쓰지 않는다. 길이는 서버가 다시 자른다.
    history: list[ChatTurn] = Field(default=[], max_length=20)
    lat: float | None = None
    lng: float | None = None


class Chip(BaseModel):
    key: str  # 지울 때 remove 로 되돌려 보내는 식별자
    label: str


class ChatOut(BaseModel):
    reply: str
    # filter: 규칙 파서(무료, LLM 없음) / llm: Claude 대화(premium)
    source: str
    understood: bool
    filters: ChatFilters
    chips: list[Chip]
    items: list[RecommendedMenuOut]
    memory_added: list[str] = []
    # premium 이 오늘 AI 대화 한도를 다 써서 이번 답은 규칙 파서가 했다는 뜻
    limit_reached: bool = False
