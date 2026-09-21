import { get } from "../../api";

export const fetchGoals = () => get("/recommend/goals");
// params: goal, max_calorie, max_sodium, max_sugar, exclude_drinks, lat, lng, radius_m, limit
export const fetchRecommendedMenus = (params) => get("/recommend/menus", params);
// 로그인 사용자 전용 "오늘 당신에겐" 3개. params: lat?, lng?
// 서버가 수 초간 LLM을 부를 수 있고, 숨기기 직후엔 답이 달라야 해서 캐시하지 않는다.
export const fetchPersonalPicks = (params) => get("/recommend/personal", params, { fresh: true });
