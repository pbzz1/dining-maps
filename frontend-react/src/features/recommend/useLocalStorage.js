import { useEffect, useState } from "react";

// 로그인 없이 '기억되는' 설정. 같은 브라우저에서만 유지된다 -- 나중에 로그인을
// 붙이면 첫 로그인 때 이 값을 서버로 한 번 올려주면 끊김 없이 이어진다.
export function useLocalStorage(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem(key);
      // 저장된 null도 "없음"으로 -- 같은 키를 다른 초기값으로 쓰는 화면(신메뉴는 null,
      // 맞춤 추천은 DEFAULT_PROFILE)이 있어서, 신메뉴가 먼저 저장한 null을 맞춤 추천이
      // 그대로 받으면 프로필 계산에서 죽는다.
      return raw === null ? initial : (JSON.parse(raw) ?? initial);
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(value));
  }, [key, value]);
  return [value, setValue];
}
