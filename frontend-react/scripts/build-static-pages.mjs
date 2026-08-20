// 검색엔진 유입용 정적 페이지 생성기. `vite build` 뒤에 돌아서 dist/에 브랜드별
// HTML을 굽는다.
//
// 왜 필요한가: 이 앱은 SPA라 서버가 보내는 HTML이 <div id="root"></div> 뿐이다.
// 크롤러 상당수는 JS를 실행하지 않으므로 "빅맥 칼로리" 같은 검색에 잡힐 내용이
// 아예 없다. 브랜드/메뉴 데이터는 하루 한 번 크롤링할 때만 바뀌므로 빌드 시점에
// 미리 구워두면 SSR 프레임워크를 들일 이유가 없다.
//
//   VITE_API_BASE=https://... [SITE_URL=https://...] node scripts/build-static-pages.mjs
//
// API가 안 뜨면 경고만 남기고 통과한다 -- SEO 페이지 때문에 앱 배포 전체를
// 막지는 않는다. 대신 배포 로그에서 눈에 띄게 찍는다.
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const DIST = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const API = process.env.VITE_API_BASE;
const SITE = (process.env.SITE_URL ?? "https://dining-maps.taehun0147.workers.dev").replace(/\/$/, "");

// Render 무료 티어는 유휴 시 잠들어서 첫 요청이 50초쯤 걸린다.
const TIMEOUT_MS = 90_000;

const NUTRIENTS = [
  { key: "calorie", label: "열량" },
  { key: "sodium", label: "나트륨" },
  { key: "sugar", label: "당류" },
  { key: "protein", label: "단백질" },
];

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 잠든 Render를 깨우는 첫 요청은 타임아웃으로 죽는 경우가 있어 재시도한다.
// 재시도가 없으면 콜드 스타트일 때 SEO 페이지가 통째로 안 생긴 채 배포된다
// (실제로 한 번 그렇게 조용히 넘어갔다).
const RETRY_DELAYS_MS = [5_000, 15_000];

async function api(path) {
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(`${API}/api${path}`, { signal: AbortSignal.timeout(TIMEOUT_MS) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (e) {
      if (attempt >= RETRY_DELAYS_MS.length) throw new Error(`${path} -> ${e.message}`);
      console.warn(`[seo] ${path} 실패(${e.message}), ${RETRY_DELAYS_MS[attempt] / 1000}초 후 재시도`);
      await sleep(RETRY_DELAYS_MS[attempt]);
    }
  }
}

const STYLE = `
:root{color-scheme:light dark}
*{box-sizing:border-box}
body{margin:0 auto;padding:1.5rem 1rem 4rem;max-width:60rem;
  font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:#0b6bcb}
h1{font-size:1.6rem;margin:.2rem 0 .4rem}
h2{font-size:1.15rem;margin:2rem 0 .6rem}
.lead{color:#555;margin:0 0 1.2rem}
.grade{display:inline-block;min-width:1.6rem;padding:.1rem .45rem;border-radius:.3rem;
  font-weight:700;text-align:center;color:#fff;font-size:.85rem}
.A{background:#1a7f37}.B{background:#4a9d3f}.C{background:#c58a00}.D{background:#b4341f}
table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{padding:.45rem .5rem;border-bottom:1px solid #ddd;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left;white-space:normal}
th{background:#f4f4f5;font-weight:600}
.wrap{overflow-x:auto}
nav{margin-top:2rem;padding-top:1rem;border-top:1px solid #ddd;font-size:.9rem}
nav a{display:inline-block;margin:0 .7rem .4rem 0}
@media(prefers-color-scheme:dark){
  body{background:#111;color:#e6e6e6}a{color:#69b7ff}.lead{color:#aaa}
  th{background:#1d1d20}th,td{border-color:#333}nav{border-color:#333}}
`.trim();

function page({ title, description, canonical, body }) {
  return `<!doctype html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}">
<link rel="canonical" href="${esc(canonical)}">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(description)}">
<meta property="og:type" content="website">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>${STYLE}</style>
</head>
<body>
${body}
</body>
</html>
`;
}

const nutrientMap = (item) =>
  Object.fromEntries(item.nutrition.map((n) => [n.nutrient_name, n]));

const fmt = (n) =>
  n === undefined ? "-" : `${Math.round(n.value).toLocaleString("ko-KR")}${n.unit}`;

function brandPage(brand, grade, menu, allBrands) {
  const url = `${SITE}/brand/${encodeURIComponent(brand.name)}/`;
  const scored = menu.filter((m) => m.absolute_grade);
  const g = grade.absolute_grade;

  const summary = g
    ? `${brand.name} 메뉴 ${grade.scored_item_count}개를 WHO 기준으로 채점한 결과 평균 ${g}등급입니다.` +
      ` A·B등급 메뉴는 ${grade.good_menu_count}개(${Math.round((grade.good_menu_ratio ?? 0) * 100)}%)입니다.`
    : `${brand.name} 메뉴 ${menu.length}개의 열량·나트륨·당류·단백질 영양성분표입니다.`;

  const rows = menu
    .map((m) => {
      const n = nutrientMap(m);
      const badge = m.absolute_grade
        ? `<span class="grade ${m.absolute_grade}">${m.absolute_grade}</span>`
        : "-";
      return `<tr><td>${esc(m.name)}</td><td>${esc(m.category ?? "-")}</td>` +
        NUTRIENTS.map((x) => `<td>${fmt(n[x.key])}</td>`).join("") +
        `<td>${badge}</td></tr>`;
    })
    .join("\n");

  const others = allBrands
    .filter((b) => b.id !== brand.id)
    .map((b) => `<a href="/brand/${encodeURIComponent(b.name)}/">${esc(b.name)}</a>`)
    .join("");

  return page({
    title: `${brand.name} 메뉴 칼로리·나트륨 영양성분표 | Dining Maps`,
    description: summary,
    canonical: url,
    body: `<h1>${esc(brand.name)} 영양성분표</h1>
<p class="lead">${esc(summary)}</p>
<p><a href="/">지도에서 내 주변 ${esc(brand.name)} 매장 보기 &rarr;</a></p>

<h2>메뉴 ${menu.length}개 (등급 있는 메뉴 ${scored.length}개)</h2>
<div class="wrap">
<table>
<thead><tr><th>메뉴</th><th>분류</th>${NUTRIENTS.map((x) => `<th>${x.label}</th>`).join("")}<th>등급</th></tr></thead>
<tbody>
${rows}
</tbody>
</table>
</div>
<p class="lead">등급은 WHO 권고 기준(절대평가)으로 매긴 값입니다. A가 가장 좋고 D가 가장 나쁩니다.
100kcal 미만 항목은 채점에서 제외됩니다.</p>

<nav><strong>다른 브랜드</strong><br>${others}</nav>`,
  });
}

function indexPage(rows) {
  const list = rows
    .map(({ brand, grade, menu }) => {
      const g = grade.absolute_grade;
      const badge = g ? `<span class="grade ${g}">${g}</span>` : "-";
      return `<tr><td><a href="/brand/${encodeURIComponent(brand.name)}/">${esc(brand.name)}</a></td>` +
        `<td>${menu.length}</td><td>${badge}</td>` +
        `<td>${grade.avg_score === null ? "-" : Math.round(grade.avg_score)}</td></tr>`;
    })
    .join("\n");

  return page({
    title: "프랜차이즈 브랜드별 메뉴 영양성분 비교 | Dining Maps",
    description: `국내 프랜차이즈 ${rows.length}개 브랜드의 메뉴 열량·나트륨·당류를 한자리에서 비교합니다.`,
    canonical: `${SITE}/brand/`,
    body: `<h1>브랜드별 영양성분 비교</h1>
<p class="lead">국내 프랜차이즈 ${rows.length}개 브랜드의 메뉴를 WHO 기준으로 채점했습니다.</p>
<p><a href="/">지도에서 내 주변 매장 보기 &rarr;</a></p>
<div class="wrap">
<table>
<thead><tr><th>브랜드</th><th>메뉴 수</th><th>평균 등급</th><th>평균 점수</th></tr></thead>
<tbody>
${list}
</tbody>
</table>
</div>`,
  });
}

async function write(relPath, content) {
  const full = join(DIST, relPath);
  await mkdir(dirname(full), { recursive: true });
  await writeFile(full, content, "utf8");
}

async function main() {
  if (!API) {
    console.warn("[seo] VITE_API_BASE 미설정 -- 정적 페이지 생성 건너뜀");
    return;
  }

  const brands = await api("/restaurants");
  const rows = [];
  for (const brand of brands) {
    const [grade, menu] = await Promise.all([
      api(`/restaurants/${brand.id}/diet-grade`),
      api(`/restaurants/${brand.id}/menu`),
    ]);
    rows.push({ brand, grade, menu });
  }

  for (const { brand, grade, menu } of rows) {
    await write(`brand/${brand.name}/index.html`, brandPage(brand, grade, menu, brands));
  }
  await write("brand/index.html", indexPage(rows));

  const urls = [`${SITE}/`, `${SITE}/brand/`,
    ...brands.map((b) => `${SITE}/brand/${encodeURIComponent(b.name)}/`)];
  await write("sitemap.xml",
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
    urls.map((u) => `  <url><loc>${esc(u)}</loc></url>`).join("\n") +
    `\n</urlset>\n`);
  await write("robots.txt", `User-agent: *\nAllow: /\n\nSitemap: ${SITE}/sitemap.xml\n`);

  const items = rows.reduce((s, r) => s + r.menu.length, 0);
  console.log(`[seo] ${brands.length}개 브랜드 페이지 + 목차 + sitemap 생성 (메뉴 ${items}개)`);
}

main().catch((e) => {
  console.warn(`[seo] 정적 페이지 생성 실패 -- 앱 배포는 계속합니다: ${e.message}`);
});
