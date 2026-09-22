import { del, get } from "../../api";

// 즐겨찾기 = 추천 카드에서 "저장"한 메뉴(app/profile/router.py). 저장 자체는 logEvent("save")가 한다.
// 해제·저장 직후에 다시 불러야 목록이 맞으므로 캐시하지 않는다.
export const fetchFavorites = () => get("/favorites", undefined, { fresh: true });

// 해제가 서버에 반영되면 알린다. 뷰는 숨겨진 채 살아 있어서(App 의 Pane) 내 정보에서 해제해도
// 맞춤 추천 카드는 그 사실을 모른다 -- 이 이벤트를 듣고 "저장됨"을 끈다. detail = menu_item_id.
export const FAVORITE_REMOVED = "favorite:removed";
const notifyRemoved = (id) => window.dispatchEvent(new CustomEvent(FAVORITE_REMOVED, { detail: id }));

export const removeFavorite = (menuItemId) =>
  del(`/favorites/${menuItemId}`).then(
    (res) => {
      notifyRemoved(menuItemId);
      return res;
    },
    (e) => {
      if (e.status === 404) notifyRemoved(menuItemId); // 이미 없음 -- 어차피 저장 상태가 아니다
      throw e;
    }
  );
