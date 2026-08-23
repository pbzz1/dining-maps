import { useEffect, useState } from "react";

// 로그인 없이 '기억되는' 설정. 같은 브라우저에서만 유지된다 -- 나중에 로그인을
// 붙이면 첫 로그인 때 이 값을 서버로 한 번 올려주면 끊김 없이 이어진다.
export function useLocalStorage(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? initial : JSON.parse(raw);
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(value));
  }, [key, value]);
  return [value, setValue];
}
