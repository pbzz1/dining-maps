import { post } from "../../api";

// 대화 한 턴. body: { message, filters, remove?, history?, lat?, lng? }
// 서버는 대화도 조건도 저장하지 않는다 -- 여기(브라우저)가 들고 매번 보낸다.
export const postChat = (body) => post("/chat", body);
