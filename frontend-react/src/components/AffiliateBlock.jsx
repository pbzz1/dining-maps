// 쿠팡 파트너스 제휴 링크 블록. 링크·문구는 src/affiliate.json 에서 읽고, 같은 파일을
// 정적 SEO 페이지(scripts/build-static-pages.mjs)도 읽는다 -- 두 곳의 링크가 따로 놀지 않게.
//
// url 이 채워진 링크가 하나도 없으면 아무것도 그리지 않는다. 그래서 affiliate.json 을
// 채우기 전까지는 이 컴포넌트를 어디에 꽂아도 화면이 변하지 않는다.
// 고지문은 공정위 추천·보증 심사지침상 링크와 같은 블록 안에 있어야 해서 여기 고정돼 있다.
import affiliate from "../affiliate.json";
import { track } from "../constants";

export default function AffiliateBlock({ slot }) {
  const def = affiliate.slots[slot];
  const links = (def?.links ?? []).filter((l) => l.url);
  if (!links.length) return null;
  return (
    <aside className="aff-block" aria-label="제휴 링크">
      <strong>{def.title}</strong>
      <div className="aff-links">
        {links.map((l) => (
          <a
            key={l.label}
            href={l.url}
            target="_blank"
            rel="sponsored nofollow noopener"
            onClick={() => track("affiliate_click", { slot, label: l.label, page_type: "app" })}
          >
            {l.label}
          </a>
        ))}
      </div>
      <small>{affiliate.disclosure}</small>
    </aside>
  );
}
