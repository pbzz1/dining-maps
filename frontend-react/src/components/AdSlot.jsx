// 애드센스 광고 단위. VITE_ADSENSE_CLIENT·VITE_ADSENSE_SLOT 이 둘 다 있어야 그려진다.
// 애드센스는 *.cloudfront.net 같은 공용 서브도메인을 승인하지 않으므로, 커스텀 도메인을
// 붙이기 전까지는 두 값을 비워 두는 게 정상이다 (그동안 이 컴포넌트는 null).
// 로더 스크립트(adsbygoogle.js)는 빌드 후처리가 index.html <head> 에 넣는다
// (scripts/build-static-pages.mjs 의 headExtras).
import { useEffect } from "react";

const CLIENT = import.meta.env.VITE_ADSENSE_CLIENT;
const SLOT = import.meta.env.VITE_ADSENSE_SLOT;

export default function AdSlot() {
  useEffect(() => {
    if (!CLIENT || !SLOT) return;
    try {
      (window.adsbygoogle = window.adsbygoogle || []).push({});
    } catch {
      // 광고 차단기 등 -- 광고가 안 뜨는 것 말고는 영향 없다
    }
  }, []);
  if (!CLIENT || !SLOT) return null;
  return (
    <div className="ad-slot">
      <ins
        className="adsbygoogle"
        style={{ display: "block" }}
        data-ad-client={CLIENT}
        data-ad-slot={SLOT}
        data-ad-format="auto"
        data-full-width-responsive="true"
      />
      <small>광고</small>
    </div>
  );
}
