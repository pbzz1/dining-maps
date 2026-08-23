import { get } from "../../api";

export const fetchGoals = () => get("/recommend/goals");
// params: goal, max_calorie, max_sodium, max_sugar, exclude_drinks, lat, lng, radius_m, limit
export const fetchRecommendedMenus = (params) => get("/recommend/menus", params);
