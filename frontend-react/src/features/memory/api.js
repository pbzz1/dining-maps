import { del, get, post } from "../../api";

// AI 메모리. 추천 호출이 새로 기억하거나 사용자가 지우면 곧바로 달라지므로 캐시하지 않는다.
export const fetchMemory = () => get("/memory", undefined, { fresh: true });
// 목록 전체를 돌려준다 -- 추가한 뒤 다시 부를 필요가 없다.
export const addMemory = (fact) => post("/memory", { fact });
export const deleteMemory = (id) => del(`/memory/${id}`);
