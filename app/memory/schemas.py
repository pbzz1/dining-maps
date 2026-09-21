from datetime import datetime

from pydantic import BaseModel, Field

from app.memory.store import MAX_FACT_LEN


class MemoryOut(BaseModel):
    id: int
    fact: str
    source: str  # ai | user -- 화면이 "AI가 알아낸 것"과 "내가 적은 것"을 구분해 보여준다
    created_at: datetime


class MemoryIn(BaseModel):
    fact: str = Field(min_length=1, max_length=MAX_FACT_LEN)
