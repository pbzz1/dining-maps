import { useEffect, useRef } from "react";
import { fetchProfile, saveProfile } from "../auth/api";

// localStorage 두 덩어리(prefs, profile) <-> 서버 user_profile 한 행의 변환.
// 이름이 다른 이유: 프론트는 camelCase, 서버 컬럼은 추천 API 쿼리 파라미터명을 따른다.
// 변환을 이 파일에만 두면 필드가 늘어도 고칠 곳이 한 군데다.
export function toServer(prefs, profile) {
  const num = (v) => (v === "" || v == null ? null : Number(v));
  return {
    goal: prefs.goal ?? null,
    sex: profile?.sex ?? null,
    height_cm: num(profile?.heightCm),
    weight_kg: num(profile?.weightKg),
    age: num(profile?.age),
    activity: profile?.activity ?? null,
    max_calorie: num(prefs.maxCalorie),
    max_sodium: num(prefs.maxSodium),
    exclude_drinks: !!prefs.excludeDrinks,
    allergies: null,
    dislikes: null,
  };
}

export function fromServer(row, prefs, profile) {
  // 서버에 없는 칸(null)은 지금 화면 값을 유지한다 -- 빈 칸으로 덮어쓰면 다른 기기에서
  // 로그인했을 때 멀쩡하던 설정이 지워진 것처럼 보인다.
  const keep = (v, cur) => (v == null ? cur : v);
  return {
    prefs: {
      ...prefs,
      goal: keep(row.goal, prefs.goal),
      maxCalorie: keep(row.max_calorie, prefs.maxCalorie),
      maxSodium: keep(row.max_sodium, prefs.maxSodium),
      excludeDrinks: !!row.exclude_drinks,
    },
    profile: {
      ...profile,
      sex: keep(row.sex, profile.sex),
      heightCm: keep(row.height_cm, profile.heightCm),
      weightKg: keep(row.weight_kg, profile.weightKg),
      age: keep(row.age, profile.age),
      activity: keep(row.activity, profile.activity),
    },
  };
}

// 서버에 저장된 적이 있는지. goal 조차 없으면 "이 계정은 아직 빈 프로필"로 보고
// 브라우저에 쌓여 있던 설정을 한 번 올려 준다 (useLocalStorage 주석이 예고한 그 경로).
const isEmpty = (row) => !row || Object.values(row).every((v) => v == null || v === false);

/**
 * 로그인하면 서버 프로필을 끌어오고, 이후 변경은 서버로 밀어 올린다.
 * 비로그인이면 아무 일도 하지 않는다 -- 기존 localStorage 동작 그대로.
 */
export function useProfileSync({ user, prefs, profile, setPrefs, setProfile }) {
  // 서버에서 받은 값을 state에 넣는 것 자체가 "변경"으로 보여서 곧바로 다시 저장되는
  // 왕복을 막는다. 아직 pull이 안 끝났으면 push도 하지 않는다.
  const pulled = useRef(false);

  useEffect(() => {
    if (!user) {
      pulled.current = false;
      return;
    }
    let cancelled = false;
    fetchProfile()
      .then((row) => {
        if (cancelled) return;
        if (isEmpty(row)) return saveProfile(toServer(prefs, profile)); // 첫 로그인 업로드
        const next = fromServer(row, prefs, profile);
        setPrefs(next.prefs);
        setProfile(next.profile);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) pulled.current = true;
      });
    return () => {
      cancelled = true;
    };
    // user가 바뀔 때만 -- prefs/profile을 의존성에 넣으면 입력할 때마다 다시 끌어온다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  useEffect(() => {
    if (!user || !pulled.current) return;
    // 숫자 입력은 한 글자마다 바뀐다 -- 멈춘 뒤에 한 번만 보낸다.
    const t = setTimeout(() => saveProfile(toServer(prefs, profile)).catch(() => {}), 800);
    return () => clearTimeout(t);
  }, [user, prefs, profile]);
}
