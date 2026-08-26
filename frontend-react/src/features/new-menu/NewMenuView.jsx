import { useEffect, useState } from "react";
import { fetchNewMenus } from "../../api";
import { track } from "../../constants";

// 신메뉴 피드. 데이터 파이프라인이 매 크롤마다 이전 스냅샷과 diff해서 기록하는
// menu_change_log의 'added'가 원천이라, 브랜드가 공식 사이트에 메뉴를 올리면
// 다음 크롤에서 자동으로 여기 뜬다. 카드의 다이어트 판정·예상 맛은 LLM 배치
// (generate_new_menu_reviews.py) 결과 캐시고, 유튜브는 검색 링크다 --
// 특정 영상을 박제하면 삭제·비공개 때 죽은 링크가 되지만 검색은 항상 최신이다.

const num = (v, digits = 0) =>
  v == null ? "-" : v.toLocaleString("ko-KR", { maximumFractionDigits: digits });

const BASIS_LABEL = { per_100g: "100g당", per_total: "전체", per_serving: "" };
const VERDICT_CLASS = { 추천: "good", 무난: "mid", 비추천: "bad" };

const youtubeUrl = (m) =>
  `https://www.youtube.com/results?search_query=${encodeURIComponent(
    `${m.restaurant_name} ${m.name} 리뷰`
  )}`;

export default function NewMenuView() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchNewMenus().then(setRows).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="nm-page">
      <h2 className="nm-title">신메뉴</h2>
      <p className="dash-sub">
        매일 크롤이 브랜드 공식 영양정보를 이전 회차와 비교해 새로 올라온 메뉴를 잡아낸다.
        다이어트 판정과 예상 맛은 공개된 영양 수치·메뉴명 기반 AI 분석이다 (실제 시식 아님).
      </p>

      {error && <p className="dash-status">신메뉴 불러오기 실패: {error}</p>}
      {!error && rows === null && <p className="dash-status">불러오는 중…</p>}
      {rows?.length === 0 && (
        <p className="dash-status">
          최근 90일 안에 감지된 신메뉴가 없습니다. 브랜드가 새 메뉴를 공식 사이트에
          올리면 다음 크롤 때 자동으로 나타납니다.
        </p>
      )}

      <div className="nm-grid">
        {rows?.map((m) => (
          <article key={m.id} className="nm-card">
            <div className="nm-head">
              <span className="nm-brand">{m.restaurant_name}</span>
              {/* 보도자료로 확인된 출시일이 우선, 없으면 크롤이 처음 본 날 */}
              <span className="nm-date">
                {m.released_at ? `${m.released_at} 출시` : `${m.first_seen_at} 발견`}
              </span>
            </div>
            <h3 className="nm-name">
              {m.name}
              {BASIS_LABEL[m.nutrition_basis] && (
                <span className="mx-basis">{BASIS_LABEL[m.nutrition_basis]}</span>
              )}
            </h3>

            <div className="nm-nutrition">
              <span><b>{num(m.calorie)}</b> kcal</span>
              <span>단백질 <b>{num(m.protein, 1)}</b>g</span>
              <span>당류 <b>{num(m.sugar, 1)}</b>g</span>
              <span>나트륨 <b>{num(m.sodium)}</b>mg</span>
              {m.diet_score != null && (
                <span>다이어트 <b>{m.diet_score.toFixed(0)}</b>{m.absolute_grade && ` (${m.absolute_grade})`}</span>
              )}
            </div>

            {m.diet_comment ? (
              <div className="nm-review">
                <p>
                  <span className={`nm-verdict ${VERDICT_CLASS[m.diet_verdict] ?? "mid"}`}>
                    다이어트 {m.diet_verdict}
                  </span>
                  {m.diet_comment}
                </p>
                <p className="nm-taste">예상 맛 — {m.taste_note}</p>
              </div>
            ) : (
              <p className="nm-review nm-pending">AI 분석 준비 중 — 영양정보를 먼저 확인하세요.</p>
            )}

            <a
              className="nm-yt"
              href={youtubeUrl(m)}
              target="_blank"
              rel="noreferrer"
              onClick={() => track("youtube_review_search", { menu: m.name })}
            >
              ▶ 유튜브 리뷰 검색
            </a>
          </article>
        ))}
      </div>

      <p className="dash-footnote">
        영양정보는 브랜드 공식 공개값 그대로이며, AI 분석은 그 수치와 메뉴명만으로 만든
        참고 의견입니다. 실제 맛·구성은 유튜브 리뷰로 확인하세요.
      </p>
    </div>
  );
}
