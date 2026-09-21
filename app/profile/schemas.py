from pydantic import BaseModel, Field

# 프로필은 전 필드가 선택이다. 비워 둔 칸은 프론트가 한국 성인 평균(bmr.js의
# KOREAN_AVG)으로 메우므로, 여기서 기본값을 정하면 두 군데가 서로 다른 '평균'을
# 갖게 된다 -- 저장은 사용자가 실제로 넣은 값만.
class ProfileIn(BaseModel):
    goal: str | None = None
    sex: str | None = None
    height_cm: float | None = Field(default=None, gt=0, le=300)
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    age: int | None = Field(default=None, ge=1, le=120)
    activity: str | None = None
    max_calorie: float | None = Field(default=None, gt=0)
    max_sodium: float | None = Field(default=None, gt=0)
    exclude_drinks: bool = False
    allergies: str | None = Field(default=None, max_length=500)
    dislikes: str | None = Field(default=None, max_length=500)


class ProfileOut(ProfileIn):
    pass


class EventIn(BaseModel):
    menu_item_id: int | None = None
    # 자유 문자열을 그대로 받으면 개인화 쿼리가 오타 값을 조용히 무시하게 된다.
    event_type: str = Field(pattern="^(view|click|save|hide|ate)$")
