import { GRADE_CLASS } from "../constants";

// Two grades sit side by side everywhere in the UI: the solid badge is the
// absolute (WHO/논문 기준) grade, the faded one is the relative rank among
// currently-listed menus. See docs/diet_score.md for why both exist.
// basis: "meal" | "drink" -- which rule set produced the grade. Drinks are
// judged per cup on calorie/sugar/satfat only (no protein, no sodium), so an
// americano can be A while a sweet latte is D. Meals keep the per-100kcal rules.
export const BASIS_LABEL = { meal: "식사 기준", drink: "음료 기준" };

// mode: "relative" | "absolute" | undefined -- undefined (or omitted) shows
// both side by side, as every screen except the store list still does.
export function GradeBadges({ absolute, relative, basis, mode }) {
  const basisLabel = BASIS_LABEL[basis];
  const showAbsolute = mode !== "relative" && absolute;
  const showRelative = mode !== "absolute" && relative;
  return (
    <>
      {showAbsolute && (
        <span
          className={`grade-badge ${GRADE_CLASS[absolute]}`}
          title="절대 기준(WHO/논문 고정 기준)"
        >
          {absolute}
        </span>
      )}
      {showRelative && (
        <span
          className={`grade-badge ${GRADE_CLASS[relative]}`}
          style={mode ? undefined : { opacity: 0.65 }}
          title="상대 기준(현재 등록 매장 중 순위)"
        >
          {relative}
        </span>
      )}
      {basisLabel && <span className="menu-item-meta">{basisLabel}</span>}
    </>
  );
}

const MODE_LEGEND = {
  relative: (
    <>
      <span className="grade-badge grade-b">B</span> 상대 기준: 등록 브랜드 중 순위 — 상위 20% A · 30% B · 30% C · 하위 20% D
    </>
  ),
  absolute: (
    <>
      <span className="grade-badge grade-b">B</span> 절대 기준: WHO/논문 고정 기준 (매장 수가 늘어도 안 바뀜)
    </>
  ),
};

// mode: same as GradeBadges -- pass it to show only that criterion's legend
// line instead of both.
export function GradeLegend({ mode }) {
  return (
    <p className="legend-hint">
      {mode ? (
        MODE_LEGEND[mode]
      ) : (
        <>
          <span className="grade-badge grade-b">B</span> 절대 기준(WHO/논문 고정 기준) ·{" "}
          <span className="grade-badge grade-b" style={{ opacity: 0.65 }}>
            B
          </span>{" "}
          상대 기준(등록 브랜드 중 순위 — 상위 20% A · 30% B · 30% C · 하위 20% D)
        </>
      )}
      <br />
      <b>식사 기준</b>: 100kcal당 단백질·당류·포화지방·나트륨 · <b>음료 기준</b>: 1잔의 열량·당류·포화지방만
      (단백질·나트륨 미반영 — 아메리카노/에스프레소는 A)
    </p>
  );
}
