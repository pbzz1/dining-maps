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
    # 어느 노출(reco_impression)의 몇 번째 카드에서 나온 행동인지. 학습형 추천이 "보여준 것 중
    # 이걸 골랐다"를 배우는 연결고리다. 목록 클릭처럼 노출이 없는 곳은 비워 둔다.
    impression_id: int | None = None
    surface: str | None = Field(default=None, pattern="^(personal_picks|goal_list|chat)$")
    position: int | None = Field(default=None, ge=0, le=50)
