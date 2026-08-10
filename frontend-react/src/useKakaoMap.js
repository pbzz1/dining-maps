import { useEffect, useRef, useState } from "react";

const SDK_ID = "kakao-maps-sdk";

// Loads the Kakao Maps SDK once and initializes a map into `containerRef`.
// The SDK is a global singleton, so mounting/unmounting the map view must not
// re-inject the script tag -- we reuse the existing one if it's already there.
export function useKakaoMap(containerRef, center) {
  const mapRef = useRef(null);
  const placesRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const appKey = import.meta.env.VITE_KAKAO_JS_KEY;
    if (!appKey) {
      setError("VITE_KAKAO_JS_KEY가 설정되지 않았습니다 (.env 확인)");
      return;
    }

    function init() {
      window.kakao.maps.load(() => {
        if (!containerRef.current || mapRef.current) return;
        mapRef.current = new window.kakao.maps.Map(containerRef.current, {
          center: new window.kakao.maps.LatLng(center.lat, center.lng),
          level: 5,
        });
        placesRef.current = new window.kakao.maps.services.Places();
        setReady(true);
      });
    }

    if (window.kakao?.maps) {
      init();
      return;
    }

    let script = document.getElementById(SDK_ID);
    if (!script) {
      script = document.createElement("script");
      script.id = SDK_ID;
      script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${appKey}&autoload=false&libraries=services`;
      document.head.appendChild(script);
    }
    script.addEventListener("load", init);
    script.addEventListener("error", () =>
      setError("카카오맵 SDK를 불러오지 못했습니다. API 키/도메인 등록을 확인하세요.")
    );
    return () => script.removeEventListener("load", init);
    // center is only the *initial* center; later moves go through map.setCenter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { map: mapRef.current, places: placesRef.current, ready, error };
}
