import { GRADE_CLASS } from "../constants";

// Two grades sit side by side everywhere in the UI: the solid badge is the
// absolute (WHO/논문 기준) grade, the faded one is the relative rank among
// currently-listed menus. See docs/diet_score.md for why both exist.
export function GradeBadges({ absolute, relative }) {
  return (
    <>
      {absolute && (
        <span className={`grade-badge ${GRADE_CLASS[absolute]}`} title="절대 기준(WHO/논문)">
          {absolute}
        </span>
      )}
      {relative && (
        <span
          className={`grade-badge ${GRADE_CLASS[relative]}`}
          style={{ opacity: 0.65 }}
          title="상대 기준(현재 등록 매장 중 순위)"
        >
          {relative}
        </span>
      )}
    </>
  );
}

export function GradeLegend() {
  return (
    <p className="legend-hint">
      <span className="grade-badge grade-b">B</span> 절대 기준(WHO/논문 고정 기준) ·{" "}
      <span className="grade-badge grade-b" style={{ opacity: 0.65 }}>
        B
      </span>{" "}
      상대 기준(현재 등록 매장 중 순위, B가 가장 많도록 설계)
    </p>
  );
}
