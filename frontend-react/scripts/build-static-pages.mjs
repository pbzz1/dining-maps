// 검색엔진 유입용 정적 페이지 생성기. `vite build` 뒤에 돌아서 dist/에 HTML을 굽는다.
//
//   /brand/                      브랜드 목차
//   /brand/<브랜드>/              브랜드 영양성분표
//   /brand/<브랜드>/<메뉴>/        메뉴 1개 = 1페이지 ("빅맥 칼로리" 같은 검색의 착지점)
//   /best/<목표>/<분류>/           목표별 랭킹 ("다이어트 버거 추천" 계열)
//   /data/                       데이터셋 안내 (VITE_CONTACT_EMAIL 이 있을 때만)
//   sitemap.xml (index) + sitemap-*.xml, robots.txt, ads.txt(애드센스 켰을 때만)
//
// 왜 필요한가: 이 앱은 SPA라 서버가 보내는 HTML이 <div id="root"></div> 뿐이다.
// 크롤러 상당수는 JS를 실행하지 않으므로 "빅맥 칼로리" 같은 검색에 잡힐 내용이
// 아예 없다. 브랜드/메뉴 데이터는 하루 한 번 크롤링할 때만 바뀌므로 빌드 시점에
// 미리 구워두면 SSR 프레임워크를 들일 이유가 없다.
//
//   VITE_API_BASE=https://... [SITE_URL=https://...] node scripts/build-static-pages.mjs
//
// 선택 환경변수 -- 전부 없어도 빌드는 통과하고, 해당 요소만 빠진다:
//   VITE_GOOGLE_SITE_VERIFICATION / VITE_NAVER_SITE_VERIFICATION  검색엔진 소유 확인 메타
//   VITE_ADSENSE_CLIENT (ca-pub-...) [+ VITE_ADSENSE_SLOT]        애드센스 (커스텀 도메인 필요)
//   VITE_DONATE_URL                                               푸터 후원 링크
//   VITE_CONTACT_EMAIL                                            /data/ 페이지 문의처
// 제휴 링크는 src/affiliate.json 에서 읽는다 (url 이 빈 링크는 안 나온다).
//
// 실패하면 0이 아닌 코드로 죽는다 = 배포가 멈춘다. 예전엔 경고만 남기고 통과했는데,
// 그 바람에 검색용 페이지가 통째로 빠진 채 배포된 적이 있고(아래 재시도 주석 참고)
// 아무도 몰랐다. 검색 유입이 이 페이지들에만 달려 있으니 조용히 넘어가면 안 된다.
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const DIST = join(HERE, "..", "dist");
const API = process.env.VITE_API_BASE;
const SITE = (process.env.SITE_URL ?? "https://dining-maps.taehun0147.workers.dev").replace(/\/$/, "");

const env = (k) => (process.env[k] ?? "").trim();
const GOOGLE_VERIFY = env("VITE_GOOGLE_SITE_VERIFICATION");
const NAVER_VERIFY = env("VITE_NAVER_SITE_VERIFICATION");
const ADSENSE_CLIENT = env("VITE_ADSENSE_CLIENT");
const ADSENSE_SLOT = env("VITE_ADSENSE_SLOT");
const DONATE_URL = env("VITE_DONATE_URL");
const CONTACT_EMAIL = env("VITE_CONTACT_EMAIL");

// Render 무료 티어는 유휴 시 잠들어서 첫 요청이 50초쯤 걸린다.
const TIMEOUT_MS = 90_000;

// 표·핵심 수치에 쓰는 4종. 브랜드 대부분이 공개하는 최소 공통분모다.
const NUTRIENTS = [
  { key: "calorie", label: "열량" },
  { key: "sodium", label: "나트륨" },
  { key: "sugar", label: "당류" },
  { key: "protein", label: "단백질" },
];

// 메뉴 페이지의 전체 성분표 순서. schema.org NutritionInformation 속성명도 같이 둔다.
const ALL_NUTRIENTS = [
  { key: "calorie", label: "열량", ld: "calories" },
  { key: "protein", label: "단백질", ld: "proteinContent" },
  { key: "carb", label: "탄수화물", ld: "carbohydrateContent" },
  { key: "fat", label: "지방", ld: "fatContent" },
  { key: "sugar", label: "당류", ld: "sugarContent" },
  { key: "saturated_fat", label: "포화지방", ld: "saturatedFatContent" },
  { key: "sodium", label: "나트륨", ld: "sodiumContent" },
  { key: "caffeine", label: "카페인", ld: null },
];

const BASIS_LABEL = {
  per_serving: "1회 제공량 기준",
  per_100g: "100g당 기준",
  per_total: "제품(용기·한 판) 전체 기준",
};

// 의도 페이지 정의. sort 는 app/menus/router.py 의 MENU_SORTS 키 그대로다.
// 절대값 정렬(sodium_asc)은 per_100g·per_total 브랜드가 섞이면 순위가 거짓말이 되므로
// servingOnly 로 1회 제공량 기준 메뉴만 남긴다. 비율·점수 정렬은 스케일이 상쇄돼 상관없다.
const CATEGORY_SLUG = {
  "버거": "burger", "치킨": "chicken", "피자": "pizza",
  "샐러드·샌드위치": "salad-sandwich", "음료": "drink", "디저트": "dessert",
};
const MEAL_CATS = ["버거", "치킨", "피자", "샐러드·샌드위치"];
const BEST_GOALS = [
  {
    slug: "diet", label: "다이어트", affiliate: "diet", sort: "score_desc",
    cats: [...MEAL_CATS, "음료", "디저트"],
    title: (c) => `다이어트 중 고를 만한 ${c} 메뉴 TOP 20`,
    lead: (c) => `프랜차이즈 ${c} 메뉴를 WHO·식약처 기준 다이어트 점수가 높은 순으로 줄 세웠습니다.`,
    metric: { head: "점수", cell: (m) => (m.diet_score == null ? "-" : Math.round(m.diet_score)) },
  },
  {
    slug: "protein", label: "고단백", affiliate: "protein", sort: "protein_per_100kcal_desc",
    cats: MEAL_CATS,
    title: (c) => `단백질 많은 ${c} 메뉴 TOP 20 (100kcal당)`,
    lead: (c) => `같은 열량을 먹을 때 단백질을 가장 많이 얻는 ${c} 메뉴입니다. 100kcal 미만 메뉴는 반올림 오차가 커서 제외했습니다.`,
    metric: { head: "단백질/100kcal", cell: (m) => (m.sort_value == null ? "-" : `${m.sort_value}g`) },
  },
  {
    slug: "low-sodium", label: "저나트륨", affiliate: "low_sodium", sort: "sodium_asc",
    cats: MEAL_CATS, servingOnly: true, minCalorie: 100,
    title: (c) => `나트륨 낮은 ${c} 메뉴 TOP 20`,
    lead: (c) => `1회 제공량 기준으로 나트륨이 가장 낮은 ${c} 메뉴입니다. 100g당·한 판 기준으로만 공개한 브랜드와 100kcal 미만 메뉴는 비교가 성립하지 않아 제외했습니다.`,
    metric: null,
  },
];
const BEST_SIZE = 20;
const BEST_PER_BRAND = 4; // 동점이 많은 정렬(제로 음료 100점 등)에서 한 브랜드가 표를 독식하지 않게

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
body{margin:0 auto;padding:0 1rem 3rem;max-width:60rem;
  font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:#0b6bcb}
h1{font-size:1.6rem;margin:.2rem 0 .4rem}
h2{font-size:1.15rem;margin:2rem 0 .6rem}
.lead{color:#555;margin:0 0 1.2rem}
.top{display:flex;flex-wrap:wrap;align-items:center;gap:.3rem 1rem;padding:.9rem 0;margin-bottom:1rem;
  border-bottom:1px solid #ddd;font-size:.95rem}
.top .logo{font-weight:700;font-size:1.05rem;text-decoration:none;color:inherit;margin-right:auto}
.crumb{font-size:.85rem;color:#555;margin:0 0 .6rem}
.grade{display:inline-block;min-width:1.6rem;padding:.1rem .45rem;border-radius:.3rem;
  font-weight:700;text-align:center;color:#fff;font-size:.85rem}
.A{background:#1a7f37}.B{background:#4a9d3f}.C{background:#c58a00}.D{background:#b4341f}
.facts{display:grid;grid-template-columns:repeat(4,1fr);gap:.6rem;margin:1rem 0}
.facts div{padding:.7rem .5rem;border:1px solid #ddd;border-radius:.5rem;text-align:center}
.facts b{display:block;font-size:1.35rem;line-height:1.3}
.facts span{font-size:.8rem;color:#555}
@media(max-width:30rem){.facts{grid-template-columns:repeat(2,1fr)}}
.cta{display:inline-block;margin:.4rem 0;padding:.55rem .9rem;border-radius:.5rem;background:#0b6bcb;
  color:#fff;text-decoration:none;font-weight:600}
table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{padding:.45rem .5rem;border-bottom:1px solid #ddd;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left;white-space:normal}
th{background:#f4f4f5;font-weight:600}
.wrap{overflow-x:auto}
.aff{margin:2.2rem 0 0;padding:.9rem 1rem;border:1px solid #ddd;border-radius:.5rem}
.aff strong{display:block;margin-bottom:.4rem}
.aff a{display:inline-block;margin:0 .8rem .3rem 0}
.aff small,.ad small{display:block;margin-top:.5rem;color:#777;font-size:.75rem}
.ad{margin:2rem 0 0}
nav.more{margin-top:2rem;padding-top:1rem;border-top:1px solid #ddd;font-size:.9rem}
nav.more a{display:inline-block;margin:0 .7rem .4rem 0}
footer{margin-top:2.5rem;padding-top:1rem;border-top:1px solid #ddd;font-size:.82rem;color:#555}
footer a{margin-right:.8rem}
@media(prefers-color-scheme:dark){
  body{background:#111;color:#e6e6e6}a{color:#69b7ff}.lead,.crumb,.facts span,footer{color:#aaa}
  th{background:#1d1d20}th,td,.top,.facts div,.aff,nav.more,footer{border-color:#333}
  .cta{background:#2b7fd6;color:#fff}}
`.trim();

// 페이지 4.7천 장에 같은 CSS를 인라인하면 그것만 14MB라 /seo.css 하나로 뺀다.
// 파일명이 고정이라 내용 해시를 쿼리로 붙여 CloudFront·브라우저 캐시를 갈아끼운다.
const STYLE_VER = createHash("md5").update(STYLE).digest("hex").slice(0, 8);

// --- 공통 조각 -------------------------------------------------------------

// <head> 에 조건부로 들어가는 것들. dist/index.html(SPA)에도 같은 문자열을 주입한다.
function headExtras() {
  const out = [];
  if (GOOGLE_VERIFY) out.push(`<meta name="google-site-verification" content="${esc(GOOGLE_VERIFY)}">`);
  if (NAVER_VERIFY) out.push(`<meta name="naver-site-verification" content="${esc(NAVER_VERIFY)}">`);
  if (ADSENSE_CLIENT) {
    out.push(`<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(ADSENSE_CLIENT)}" crossorigin="anonymous"></script>`);
  }
  return out.join("\n");
}

function adBlock() {
  if (!ADSENSE_CLIENT || !ADSENSE_SLOT) return "";
  return `<div class="ad"><ins class="adsbygoogle" style="display:block" data-ad-client="${esc(ADSENSE_CLIENT)}"
 data-ad-slot="${esc(ADSENSE_SLOT)}" data-ad-format="auto" data-full-width-responsive="true"></ins>
<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script><small>광고</small></div>`;
}

let AFFILIATE = { disclosure: "", slots: {} };

function affiliateBlock(slotKey) {
  const slot = AFFILIATE.slots?.[slotKey];
  const links = (slot?.links ?? []).filter((l) => l.url);
  if (!links.length) return "";
  return `<aside class="aff"><strong>${esc(slot.title)}</strong>
${links.map((l) => `<a href="${esc(l.url)}" target="_blank" rel="sponsored nofollow noopener" data-aff="${esc(slotKey)}">${esc(l.label)}</a>`).join("")}
<small>${esc(AFFILIATE.disclosure)}</small></aside>`;
}

// 메뉴 분류 -> 제휴 슬롯. 분류를 모르면 식사 슬롯.
const affiliateSlotFor = (m) =>
  m.grade_basis === "drink" || m.category_group === "음료" ? "drink"
    : m.category_group === "디저트" ? "dessert" : "meal";

function page({ title, description, canonical, body, pageType, jsonLd = [] }, ctx) {
  const ld = jsonLd
    .map((o) => `<script type="application/ld+json">${JSON.stringify(o).replace(/</g, "\\u003c")}</script>`)
    .join("\n");
  const footLinks = [
    `<a href="/brand/">브랜드별 영양성분</a>`,
    `<a href="/best/">목표별 추천 랭킹</a>`,
    `<a href="/#about" data-app="about">등급 기준</a>`,
    ctx.hasDataPage ? `<a href="/data/">데이터 안내</a>` : "",
    DONATE_URL ? `<a href="${esc(DONATE_URL)}" target="_blank" rel="noopener" data-aff="donate">서버비 후원</a>` : "",
  ].join("");
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
<meta property="og:url" content="${esc(canonical)}">
<meta property="og:image" content="${esc(SITE)}/og.png">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
${headExtras()}
<script async src="https://www.googletagmanager.com/gtag/js?id=G-B8QRKP6DTW"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-B8QRKP6DTW');
  // SPA의 page_view 와 섞이지 않게 정적 페이지 조회를 따로 센다.
  gtag('event', 'static_page_view', { page_type: ${JSON.stringify(pageType)} });
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[data-aff],a[data-app]');
    if (!a) return;
    if (a.dataset.aff) gtag('event', 'affiliate_click', { slot: a.dataset.aff, label: a.textContent, page_type: ${JSON.stringify(pageType)} });
    else gtag('event', 'deeplink_from_seo', { target: a.dataset.app, page_type: ${JSON.stringify(pageType)} });
  });
</script>
<script type="text/javascript">
  (function(c,l,a,r,i,t,y){
  c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
  t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
  y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
  })(window, document, "clarity", "script", "y8c5l2er6s");
</script>
${ld}
<link rel="stylesheet" href="/seo.css?v=${STYLE_VER}">
</head>
<body>
<header class="top"><a class="logo" href="/" data-app="map">Dining Maps</a>
<a href="/#new" data-app="new">신메뉴</a><a href="/#recommend" data-app="recommend">맞춤 추천</a><a href="/best/">랭킹</a><a href="/brand/">브랜드</a><a href="/#map" data-app="map">내 주변 지도</a></header>
${body}
<footer>
<p>모든 수치는 각 브랜드가 공식 홈페이지에 공개한 영양성분표를 옮긴 것이며 의학적 조언이 아닙니다.${ctx.dataDate ? ` 데이터 기준일 ${esc(ctx.dataDate)}.` : ""}</p>
<p>${footLinks}</p>
</footer>
</body>
</html>
`;
}

const nutrientMap = (item) =>
  Object.fromEntries(item.nutrition.map((n) => [n.nutrient_name, n]));

// 0.5g 을 1g 으로 올려 적으면 원문과 달라진다 -- 10 미만의 비정수만 소수 첫째 자리까지.
const fmtNum = (v) =>
  (v < 10 && !Number.isInteger(v) ? Math.round(v * 10) / 10 : Math.round(v)).toLocaleString("ko-KR");
const fmt = (n) => (n === undefined ? "-" : `${fmtNum(n.value)}${n.unit}`);
const fmtRank = (v, unit) => (v == null ? "-" : `${fmtNum(v)}${unit}`);

const badge = (g) => (g ? `<span class="grade ${g}">${g}</span>` : "-");
const brandUrl = (name) => `/brand/${encodeURIComponent(name)}/`;

// --- 슬러그 ---------------------------------------------------------------
//
// 한글·영문·숫자만 남기고 나머지는 '-'. 빼는 이유가 글자마다 다르다:
//   .      CloudFront 함수가 '.'이 있는 URI를 파일로 보고 index.html 을 안 붙인다 ("1.5L")
//   +      S3 가 경로의 '+'를 공백으로 읽어 404
//   / \ : * ? " < > |   경로 구분자이거나 윈도에서 파일명으로 못 쓴다 (로컬 배포는 윈도에서 돈다)
//   ® ™ 괄호 등  검색어에 안 들어가는 장식
// 같은 브랜드 안에서 슬러그가 겹치면 id 가 가장 작은 메뉴가 맨 슬러그를 갖고 나머지는
// '-<id>' 를 붙인다. 순번(-2, -3)이 아니라 id 인 이유: 앞 메뉴가 단종돼도 뒤 메뉴의 URL이
// 안 바뀐다 -- 색인된 주소가 빌드마다 흔들리면 검색 순위를 매번 새로 쌓아야 한다.
function slugify(name) {
  const s = name.normalize("NFC").toLowerCase()
    .replace(/[^0-9a-z가-힣]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80).replace(/-+$/, "");
  return s || "menu";
}

function assignSlugs(brandName, menu) {
  const taken = new Set();
  let collisions = 0;
  for (const m of [...menu].sort((a, b) => a.id - b.id)) {
    let slug = slugify(m.name);
    if (taken.has(slug)) { slug = `${slug}-${m.id}`; collisions++; }
    taken.add(slug);
    m.slug = slug;
    m.path = `${brandUrl(brandName)}${encodeURIComponent(slug)}/`;
    m.brandName = brandName;
  }
  return collisions;
}

// --- 페이지들 --------------------------------------------------------------

function gradeExplain(m, n) {
  if (m.absolute_grade) {
    const how = m.grade_basis === "drink"
      ? "음료는 1잔에 든 열량·당류·포화지방의 절대량으로 채점합니다."
      : "식사 메뉴는 100kcal당 단백질·당류·포화지방·나트륨으로 채점합니다.";
    const rel = m.relative_grade && m.percentile != null
      ? ` 전체 프랜차이즈 메뉴 안에서는 상대 등급 ${m.relative_grade}(상위 ${Math.max(1, Math.round(100 - m.percentile))}%)입니다.`
      : "";
    return `WHO·식약처 등 공개 기준으로 매긴 절대 등급은 <b>${m.absolute_grade}</b>` +
      `(${Math.round(m.diet_score)}점/100점)입니다.${rel} ${how}`;
  }
  if (n.calorie && n.calorie.value < 100) {
    return "100kcal 미만 메뉴는 영양 밀도 계산이 왜곡되기 때문에 채점하지 않습니다.";
  }
  return "채점에 필요한 영양성분(열량·단백질·당류·포화지방·나트륨)이 모두 공개되지 않아 등급을 매길 수 없습니다. 나쁘다는 뜻이 아니라 알 수 없다는 뜻입니다.";
}

function altList(title, items) {
  if (!items.length) return "";
  return `<h2>${esc(title)}</h2>
<div class="wrap"><table>
<thead><tr><th>메뉴</th><th>열량</th><th>나트륨</th><th>등급</th></tr></thead>
<tbody>
${items.map((x) => {
    const xn = nutrientMap(x);
    return `<tr><td><a href="${x.path}">${esc(x.brandName === items.ownBrand ? x.name : `${x.brandName} ${x.name}`)}</a></td>` +
      `<td>${fmt(xn.calorie)}</td><td>${fmt(xn.sodium)}</td><td>${badge(x.absolute_grade)}</td></tr>`;
  }).join("\n")}
</tbody></table></div>`;
}

function menuPage(brand, m, siblings, byGroup, ctx) {
  const n = nutrientMap(m);
  const url = `${SITE}${m.path}`;
  const basis = BASIS_LABEL[m.nutrition_basis ?? "per_serving"] ?? BASIS_LABEL.per_serving;

  const headline = NUTRIENTS.filter((x) => n[x.key])
    .map((x) => `${x.label} ${fmt(n[x.key])}`).join(", ");
  const description = `${brand.name} ${m.name} 영양성분: ${headline || "공개된 수치 없음"} (${basis}).` +
    (m.absolute_grade ? ` 다이어트 등급 ${m.absolute_grade}.` : "");

  const facts = NUTRIENTS
    .map((x) => `<div><b>${fmt(n[x.key])}</b><span>${x.label}</span></div>`).join("");

  const rows = ALL_NUTRIENTS.filter((x) => n[x.key]).map((x) => {
    const per = m.nutrition_per_serving?.find((p) => p.nutrient_name === x.key);
    return `<tr><td>${x.label}</td><td>${fmt(n[x.key])}</td>${m.nutrition_per_serving ? `<td>${fmt(per)}</td>` : ""}</tr>`;
  }).join("\n");
  const perHead = m.nutrition_per_serving ? `<th>1회분(${m.serving_ml}ml) 환산</th>` : "";

  // 같은 브랜드·같은 분류에서 점수 높은 메뉴. category_group 이 없으면(구 API) 원본 category 로.
  const groupOf = (x) => x.category_group ?? x.category ?? "";
  const same = siblings
    .filter((x) => x.id !== m.id && x.diet_score != null && groupOf(x) === groupOf(m))
    .sort((a, b) => b.diet_score - a.diet_score || a.id - b.id).slice(0, 5);
  same.ownBrand = brand.name;
  const others = (m.category_group ? byGroup.get(m.category_group) ?? [] : [])
    .filter((x) => x.brandName !== brand.name).slice(0, 5);

  const group = m.category_group && m.category_group !== "기타" ? m.category_group : "메뉴";
  const ld = [
    {
      "@context": "https://schema.org", "@type": "MenuItem", name: m.name, url,
      description,
      ...(m.price_krw ? { offers: { "@type": "Offer", price: m.price_krw, priceCurrency: "KRW" } } : {}),
      nutrition: {
        "@type": "NutritionInformation",
        ...(m.weight_g && m.nutrition_basis !== "per_100g" ? { servingSize: `${fmtNum(m.weight_g)} g` } : {}),
        ...Object.fromEntries(ALL_NUTRIENTS.filter((x) => x.ld && n[x.key])
          .map((x) => [x.ld, `${n[x.key].value} ${n[x.key].unit}`])),
      },
    },
    {
      "@context": "https://schema.org", "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "브랜드", item: `${SITE}/brand/` },
        { "@type": "ListItem", position: 2, name: brand.name, item: `${SITE}${brandUrl(brand.name)}` },
        { "@type": "ListItem", position: 3, name: m.name, item: url },
      ],
    },
  ];

  return page({
    title: `${m.name} 칼로리·영양성분 (${brand.name}) | Dining Maps`,
    description,
    canonical: url,
    pageType: "menu",
    jsonLd: ld,
    body: `<p class="crumb"><a href="/brand/">브랜드</a> › <a href="${brandUrl(brand.name)}">${esc(brand.name)}</a></p>
<h1>${esc(m.name)} 칼로리·영양성분</h1>
<p class="lead">${esc(brand.name)} 공식 영양성분표 · ${esc(basis)}${m.weight_g ? ` · 중량 ${fmtNum(m.weight_g)}g` : ""}${m.price_krw ? ` · ${m.price_krw.toLocaleString("ko-KR")}원` : ""}</p>
<div class="facts">${facts}</div>

<h2>다이어트 등급 ${badge(m.absolute_grade)}</h2>
<p>${gradeExplain(m, n)} <a href="/#about" data-app="about">기준 자세히</a></p>
<p><a class="cta" href="/#map" data-app="map">내 주변 ${esc(brand.name)} 매장 찾기 &rarr;</a></p>

<h2>전체 영양성분</h2>
<div class="wrap"><table>
<thead><tr><th>성분</th><th>${esc(basis)}</th>${perHead}</tr></thead>
<tbody>
${rows || `<tr><td colspan="2">공개된 영양성분이 없습니다.</td></tr>`}
</tbody></table></div>
${m.allergy_info ? `<p class="lead">알레르기 유발 성분: ${esc(m.allergy_info)}</p>` : ""}

${altList(`${brand.name}의 다른 ${group} — 점수 높은 순`, same)}
${altList(`다른 브랜드의 ${group} — 점수 높은 순`, others)}
${affiliateBlock(affiliateSlotFor(m))}
${adBlock()}`,
  }, ctx);
}

function brandPage(brand, grade, menu, allBrands, ctx) {
  const url = `${SITE}${brandUrl(brand.name)}`;
  const scored = menu.filter((m) => m.absolute_grade);
  const g = grade.absolute_grade;

  const summary = g
    ? `${brand.name} 메뉴 ${grade.scored_item_count}개를 WHO 기준으로 채점한 결과 평균 ${g}등급입니다.` +
      ` A·B등급 메뉴는 ${grade.good_menu_count}개(${Math.round((grade.good_menu_ratio ?? 0) * 100)}%)입니다.`
    : `${brand.name} 메뉴 ${menu.length}개의 열량·나트륨·당류·단백질 영양성분표입니다.`;

  const rows = menu
    .map((m) => {
      const n = nutrientMap(m);
      return `<tr><td><a href="${m.path}">${esc(m.name)}</a></td><td>${esc(m.category ?? "-")}</td>` +
        NUTRIENTS.map((x) => `<td>${fmt(n[x.key])}</td>`).join("") +
        `<td>${badge(m.absolute_grade)}</td></tr>`;
    })
    .join("\n");

  const others = allBrands
    .filter((b) => b.id !== brand.id)
    .map((b) => `<a href="${brandUrl(b.name)}">${esc(b.name)}</a>`)
    .join("");

  return page({
    title: `${brand.name} 메뉴 칼로리·나트륨 영양성분표 | Dining Maps`,
    description: summary,
    canonical: url,
    pageType: "brand",
    body: `<p class="crumb"><a href="/brand/">브랜드</a></p>
<h1>${esc(brand.name)} 영양성분표</h1>
<p class="lead">${esc(summary)}</p>
<p><a class="cta" href="/#map" data-app="map">지도에서 내 주변 ${esc(brand.name)} 매장 보기 &rarr;</a></p>

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
${adBlock()}
<nav class="more"><strong>다른 브랜드</strong><br>${others}</nav>`,
  }, ctx);
}

function indexPage(rows, ctx) {
  const list = rows
    .map(({ brand, grade, menu }) =>
      `<tr><td><a href="${brandUrl(brand.name)}">${esc(brand.name)}</a></td>` +
      `<td>${menu.length}</td><td>${badge(grade.absolute_grade)}</td>` +
      `<td>${grade.avg_score === null ? "-" : Math.round(grade.avg_score)}</td></tr>`)
    .join("\n");

  return page({
    title: "프랜차이즈 브랜드별 메뉴 영양성분 비교 | Dining Maps",
    description: `국내 프랜차이즈 ${rows.length}개 브랜드의 메뉴 열량·나트륨·당류를 한자리에서 비교합니다.`,
    canonical: `${SITE}/brand/`,
    pageType: "brand_index",
    body: `<h1>브랜드별 영양성분 비교</h1>
<p class="lead">국내 프랜차이즈 ${rows.length}개 브랜드의 메뉴를 WHO 기준으로 채점했습니다.</p>
<p><a class="cta" href="/#map" data-app="map">지도에서 내 주변 매장 보기 &rarr;</a></p>
<div class="wrap">
<table>
<thead><tr><th>브랜드</th><th>메뉴 수</th><th>평균 등급</th><th>평균 점수</th></tr></thead>
<tbody>
${list}
</tbody>
</table>
</div>`,
  }, ctx);
}

const bestPath = (goal, cat) => `/best/${goal.slug}/${CATEGORY_SLUG[cat]}/`;

function bestPage(goal, cat, items, menuById, ctx) {
  const title = goal.title(cat);
  const rows = items.map((r, i) => {
    const m = menuById.get(r.id);
    const name = m ? `<a href="${m.path}">${esc(r.name)}</a>` : esc(r.name);
    return `<tr><td>${i + 1}. ${name}</td><td><a href="${brandUrl(r.restaurant_name)}">${esc(r.restaurant_name)}</a></td>` +
      (goal.metric ? `<td>${goal.metric.cell(r)}</td>` : "") +
      `<td>${fmtRank(r.calorie_kcal, "kcal")}</td><td>${fmtRank(r.protein_g, "g")}</td>` +
      `<td>${fmtRank(r.sodium_mg, "mg")}</td><td>${fmtRank(r.sugar_g, "g")}</td><td>${badge(r.absolute_grade)}</td></tr>`;
  }).join("\n");

  const sameGoal = goal.cats.filter((c) => c !== cat)
    .map((c) => `<a href="${bestPath(goal, c)}">${esc(goal.label)} · ${esc(c)}</a>`).join("");
  const sameCat = BEST_GOALS.filter((x) => x !== goal && x.cats.includes(cat))
    .map((x) => `<a href="${bestPath(x, cat)}">${esc(x.label)} · ${esc(cat)}</a>`).join("");

  return page({
    title: `${title} | Dining Maps`,
    description: `${goal.lead(cat)} 1위 ${items[0].restaurant_name} ${items[0].name}.`,
    canonical: `${SITE}${bestPath(goal, cat)}`,
    pageType: "best",
    jsonLd: [{
      "@context": "https://schema.org", "@type": "ItemList", name: title,
      itemListElement: items.map((r, i) => ({
        "@type": "ListItem", position: i + 1, name: `${r.restaurant_name} ${r.name}`,
        ...(menuById.get(r.id) ? { url: `${SITE}${menuById.get(r.id).path}` } : {}),
      })),
    }],
    body: `<p class="crumb"><a href="/best/">목표별 랭킹</a></p>
<h1>${esc(title)}</h1>
<p class="lead">${esc(goal.lead(cat))} 한 브랜드가 표를 독식하지 않도록 브랜드당 ${BEST_PER_BRAND}개까지만 실었습니다.</p>
<p><a class="cta" href="/#recommend" data-app="recommend">내 주변 매장 기준으로 맞춤 추천 받기 &rarr;</a></p>
<div class="wrap"><table>
<thead><tr><th>메뉴</th><th>브랜드</th>${goal.metric ? `<th>${goal.metric.head}</th>` : ""}<th>열량</th><th>단백질</th><th>나트륨</th><th>당류</th><th>등급</th></tr></thead>
<tbody>
${rows}
</tbody></table></div>
${affiliateBlock(goal.affiliate)}
${adBlock()}
<nav class="more"><strong>다른 랭킹</strong><br>${sameGoal}${sameCat}</nav>`,
  }, ctx);
}

function bestIndexPage(built, ctx) {
  const sections = BEST_GOALS.map((goal) => {
    const links = built.filter((b) => b.goal === goal)
      .map((b) => `<li><a href="${bestPath(goal, b.cat)}">${esc(goal.title(b.cat))}</a></li>`).join("\n");
    return links ? `<h2>${esc(goal.label)}</h2>\n<ul>\n${links}\n</ul>` : "";
  }).join("\n");
  return page({
    title: "목표별 프랜차이즈 메뉴 랭킹 — 다이어트·고단백·저나트륨 | Dining Maps",
    description: "다이어트, 고단백, 저나트륨 목표별로 프랜차이즈 버거·치킨·피자·샐러드·음료·디저트 메뉴를 공식 영양성분 기준으로 줄 세웠습니다.",
    canonical: `${SITE}/best/`,
    pageType: "best_index",
    body: `<h1>목표별 메뉴 랭킹</h1>
<p class="lead">브랜드 공식 영양성분을 같은 기준으로 정규화해 목표별로 줄 세운 표입니다. 매 크롤마다 다시 계산됩니다.</p>
${sections}`,
  }, ctx);
}

function dataPage(rows, sample, ctx) {
  const menus = rows.reduce((s, r) => s + r.menu.length, 0);
  const facts = rows.reduce((s, r) => s + r.menu.reduce((t, m) => t + m.nutrition.length, 0), 0);
  return page({
    title: "프랜차이즈 영양성분 데이터셋 안내 | Dining Maps",
    description: `국내 프랜차이즈 ${rows.length}개 브랜드 메뉴 ${menus.toLocaleString("ko-KR")}개의 영양성분을 같은 스키마로 정규화한 데이터셋. 주 2회 갱신, 변경 이력 보관.`,
    canonical: `${SITE}/data/`,
    pageType: "data",
    body: `<h1>프랜차이즈 영양성분 데이터셋</h1>
<p class="lead">브랜드마다 형식이 다른 공식 영양성분표를 하나의 스키마로 정규화해 매주 갱신합니다.</p>
<div class="facts"><div><b>${rows.length}</b><span>브랜드</span></div><div><b>${menus.toLocaleString("ko-KR")}</b><span>메뉴</span></div>
<div><b>${facts.toLocaleString("ko-KR")}</b><span>영양성분 행</span></div><div><b>주 2회</b><span>갱신</span></div></div>
<h2>담긴 것</h2>
<ul>
<li>메뉴별 열량·단백질·당류·포화지방·나트륨 (브랜드에 따라 탄수화물·지방·카페인 포함), 기준 단위 라벨(1회 제공량 / 100g / 제품 전체)</li>
<li>버거·치킨·피자 등으로 정규화한 메뉴 분류, 100kcal 기준 다이어트 점수와 절대·상대 등급</li>
<li>크롤 회차별 스냅샷과 변경 로그 — 신메뉴 출시·리뉴얼·단종 추적</li>
<li>적재 전 품질 검사 결과 (행 수 안정성, 성분 커버리지, 물리적 범위, 파서 오류 판정)</li>
</ul>
<h2>샘플</h2>
<p><a href="/data/sample.csv" download>${esc(sample.brand)} 샘플 CSV 내려받기</a> (${sample.count}행, UTF-8)</p>
<h2>문의</h2>
<p>전체 데이터·API 연동·맞춤 가공이 필요하면 <a href="mailto:${esc(CONTACT_EMAIL)}?subject=${encodeURIComponent("Dining Maps 데이터 문의")}">${esc(CONTACT_EMAIL)}</a> 로 용도와 필요한 범위를 알려주세요.</p>
<p class="lead">원자료의 출처는 각 브랜드 공식 홈페이지이며, 수치에 대한 권리는 해당 브랜드에 있습니다.</p>`,
  }, ctx);
}

const csvCell = (v) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));

function sampleCsv(brand, menu) {
  const keys = ALL_NUTRIENTS.map((x) => x.key);
  const head = ["brand", "menu", "category_group", "nutrition_basis", ...keys, "diet_score", "absolute_grade", "relative_grade"];
  const lines = menu.map((m) => {
    const n = nutrientMap(m);
    return [brand.name, m.name, m.category_group, m.nutrition_basis ?? "per_serving",
      ...keys.map((k) => n[k]?.value), m.diet_score, m.absolute_grade, m.relative_grade].map(csvCell).join(",");
  });
  return `\uFEFF${head.join(",")}\n${lines.join("\n")}\n`; // BOM: 엑셀이 한글을 깨뜨리지 않게
}

// --- 출력 -----------------------------------------------------------------

async function write(relPath, content) {
  const full = join(DIST, relPath);
  await mkdir(dirname(full), { recursive: true });
  await writeFile(full, content, "utf8");
}

// paths 는 전부 이미 퍼센트 인코딩된 경로다 (brandUrl / m.path / ASCII 고정 경로).
function urlset(paths, lastmod) {
  const mod = lastmod ? `<lastmod>${lastmod}</lastmod>` : "";
  return `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
    paths.map((p) => `  <url><loc>${esc(SITE + p)}</loc>${mod}</url>`).join("\n") +
    `\n</urlset>\n`;
}

// SPA 의 index.html 후처리: 메타의 브랜드·메뉴 수를 실제 값으로, 소유 확인 메타 주입.
// 자리표시자가 없으면(누가 index.html 을 고쳤으면) 조용히 넘어가지 않고 죽는다.
async function patchSpaIndex(brandCount, menuCount) {
  const file = join(DIST, "index.html");
  let html = await readFile(file, "utf8");
  for (const [mark, value] of [
    ["__BRAND_COUNT__", String(brandCount)],
    ["__MENU_COUNT__", menuCount.toLocaleString("ko-KR")],
    ["<!--head-extras-->", headExtras()],
  ]) {
    if (!html.includes(mark)) throw new Error(`dist/index.html 에 ${mark} 자리표시자가 없다`);
    html = html.replaceAll(mark, value);
  }
  await writeFile(file, html, "utf8");
}

async function main() {
  if (!API) throw new Error("VITE_API_BASE 미설정 -- 정적 페이지를 만들 데이터 출처가 없다");

  AFFILIATE = JSON.parse(await readFile(join(HERE, "..", "src", "affiliate.json"), "utf8"));

  const brands = await api("/restaurants");
  // 0개면 API는 떴는데 DB가 비었거나 응답 모양이 바뀐 것. 빈 sitemap을 올리면
  // 색인돼 있던 주소가 통째로 빠지므로, 덮어쓰기 전에 여기서 멈춘다.
  if (!brands.length) throw new Error("/restaurants 가 0개 -- 기존 페이지를 덮어쓰지 않고 중단");

  // 기준일 = 마지막으로 품질 게이트를 통과한 크롤 날짜 (App.jsx 와 같은 규칙). 실패해도 페이지는 굽는다.
  const dataDate = await api("/stats/quality")
    .then((q) => q.filter((r) => r.status === "passed").at(-1)?.started_at.slice(0, 10) ?? "")
    .catch(() => "");
  const ctx = { dataDate, hasDataPage: Boolean(CONTACT_EMAIL) };

  const rows = [];
  for (const brand of brands) {
    const [grade, menu] = await Promise.all([
      api(`/restaurants/${brand.id}/diet-grade`),
      api(`/restaurants/${brand.id}/menu`),
    ]);
    rows.push({ brand, grade, menu });
  }

  let collisions = 0;
  const menuById = new Map();
  const byGroup = new Map(); // category_group -> 점수 높은 순 (브랜드당 2개까지: 교차 링크가 한 브랜드로 쏠리지 않게)
  for (const { brand, menu } of rows) {
    collisions += assignSlugs(brand.name, menu);
    for (const m of menu) menuById.set(m.id, m);
  }
  const scoredAll = [...menuById.values()].filter((m) => m.diet_score != null && m.category_group)
    .sort((a, b) => b.diet_score - a.diet_score || a.id - b.id);
  for (const m of scoredAll) {
    const list = byGroup.get(m.category_group) ?? [];
    if (list.filter((x) => x.brandName === m.brandName).length < 2 && list.length < 40) list.push(m);
    byGroup.set(m.category_group, list);
  }

  const sitemaps = []; // [파일명, 경로들]
  const pagePaths = ["/", "/brand/", "/best/"];

  for (const { brand, grade, menu } of rows) {
    await write(`brand/${brand.name}/index.html`, brandPage(brand, grade, menu, brands, ctx));
    pagePaths.push(brandUrl(brand.name));
    for (const m of menu) {
      await write(`brand/${brand.name}/${m.slug}/index.html`, menuPage(brand, m, menu, byGroup, ctx));
    }
    if (menu.length) sitemaps.push([`sitemap-menus-${brand.id}.xml`, menu.map((m) => m.path)]);
  }
  await write("brand/index.html", indexPage(rows, ctx));
  await write("seo.css", STYLE);

  const built = [];
  for (const goal of BEST_GOALS) {
    for (const cat of goal.cats) {
      const qs = new URLSearchParams({ sort: goal.sort, category: cat, limit: "100" });
      const perBrand = new Map();
      const items = (await api(`/menus?${qs}`))
        .filter((r) => !goal.servingOnly || (r.nutrition_basis ?? "per_serving") === "per_serving")
        .filter((r) => !goal.minCalorie || (r.calorie_kcal ?? 0) >= goal.minCalorie)
        .filter((r) => {
          const k = perBrand.get(r.restaurant_name) ?? 0;
          perBrand.set(r.restaurant_name, k + 1);
          return k < BEST_PER_BRAND;
        })
        .slice(0, BEST_SIZE);
      if (items.length < 5) { // 표본이 너무 적은 조합은 얇은 페이지가 되므로 만들지 않는다
        console.warn(`[seo] /best/${goal.slug}/${CATEGORY_SLUG[cat]}/ 건너뜀 (${items.length}건)`);
        continue;
      }
      await write(`best/${goal.slug}/${CATEGORY_SLUG[cat]}/index.html`, bestPage(goal, cat, items, menuById, ctx));
      built.push({ goal, cat });
      pagePaths.push(bestPath(goal, cat));
    }
  }
  await write("best/index.html", bestIndexPage(built, ctx));

  if (ctx.hasDataPage) {
    // 샘플은 메뉴 수가 가장 적은 브랜드 -- 형태를 보여주는 용도지 데이터를 통째로 푸는 자리가 아니다.
    const smallest = rows.filter((r) => r.menu.length >= 10).sort((a, b) => a.menu.length - b.menu.length)[0] ?? rows[0];
    await write("data/sample.csv", sampleCsv(smallest.brand, smallest.menu));
    await write("data/index.html", dataPage(rows, { brand: smallest.brand.name, count: smallest.menu.length }, ctx));
    pagePaths.push("/data/");
  }

  sitemaps.unshift(["sitemap-pages.xml", pagePaths]);
  for (const [name, paths] of sitemaps) await write(name, urlset(paths, dataDate));
  const mod = dataDate ? `<lastmod>${dataDate}</lastmod>` : "";
  await write("sitemap.xml",
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
    sitemaps.map(([name]) => `  <sitemap><loc>${esc(`${SITE}/${name}`)}</loc>${mod}</sitemap>`).join("\n") +
    `\n</sitemapindex>\n`);
  await write("robots.txt", `User-agent: *\nAllow: /\n\nSitemap: ${SITE}/sitemap.xml\n`);
  if (ADSENSE_CLIENT) {
    await write("ads.txt", `google.com, ${ADSENSE_CLIENT.replace(/^ca-/, "")}, DIRECT, f08c47fec0942fa0\n`);
  }

  const items = menuById.size;
  await patchSpaIndex(brands.length, items);

  const urlCount = sitemaps.reduce((s, [, p]) => s + p.length, 0);
  console.log(`[seo] 브랜드 ${brands.length} · 메뉴 페이지 ${items} · 랭킹 ${built.length} · sitemap URL ${urlCount}` +
    ` · 슬러그 충돌 ${collisions}건(id 접미로 해소) · 기준일 ${dataDate || "?"}` +
    ` · 제휴 ${Object.values(AFFILIATE.slots).some((s) => s.links.some((l) => l.url)) ? "on" : "off"}` +
    ` · 애드센스 ${ADSENSE_CLIENT ? "on" : "off"} · 소유확인 G:${GOOGLE_VERIFY ? "y" : "n"} N:${NAVER_VERIFY ? "y" : "n"}`);
}

main().catch((e) => {
  console.error(`[seo] 정적 페이지 생성 실패 -- 배포를 중단합니다: ${e.message}`);
  process.exitCode = 1;
});
