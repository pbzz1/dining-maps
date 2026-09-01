---
name: Dining Maps
description: 따뜻한 종이 위에 놓인 편집자의 지도 — 무채색 뉴트럴과 1px 괘선이 데이터를 떠받치고, 가마 테라코타 한 색과 4단계 등급색만이 판단을 말한다.
colors:
  bg: "#f6f5f2"
  card-bg: "#ffffff"
  text: "#23201b"
  muted: "#74706a"
  border: "#e4e0d8"
  accent: "#c1440e"
  accent-press: "#a83a0c"
  accent-soft: "#fbe9e0"
  grade-a: "#2f8f4e"
  grade-b: "#6fa83d"
  grade-c: "#d99a2b"
  grade-d: "#c1440e"
  verdict-good-bg: "#e3f2e6"
  verdict-good-text: "#1d7a33"
  pin-gold: "#ffc53d"
  pin-gold-text: "#5c4300"
  locator-blue: "#2b6cf0"
  chart-blue: "#2a78d6"
typography:
  wordmark:
    fontFamily: "Newsreader, Noto Serif KR, serif"
    fontSize: "21px"
    fontWeight: 500
    letterSpacing: "-0.01em"
  display:
    fontFamily: "-apple-system, Segoe UI, Apple SD Gothic Neo, Noto Sans KR, sans-serif"
    fontSize: "1.7rem"
    fontWeight: 600
    lineHeight: "1.1"
  headline:
    fontFamily: "-apple-system, Segoe UI, Apple SD Gothic Neo, Noto Sans KR, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: "1.3"
  title:
    fontFamily: "-apple-system, Segoe UI, Apple SD Gothic Neo, Noto Sans KR, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: "1.4"
  body:
    fontFamily: "-apple-system, Segoe UI, Apple SD Gothic Neo, Noto Sans KR, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: "1.6"
  label:
    fontFamily: "-apple-system, Segoe UI, Apple SD Gothic Neo, Noto Sans KR, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: "1.4"
  caption:
    fontFamily: "-apple-system, Segoe UI, Apple SD Gothic Neo, Noto Sans KR, sans-serif"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: "1.5"
  data:
    fontFamily: "-apple-system, Segoe UI, Apple SD Gothic Neo, Noto Sans KR, sans-serif"
    fontSize: "0.85rem"
    fontWeight: 400
    fontFeature: "tabular-nums"
rounded:
  sm: "6px"
  md: "8px"
  lg: "10px"
  xl: "12px"
  xxl: "16px"
  pill: "999px"
  circle: "50%"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  xxl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#ffffff"
    typography: "{typography.label}"
    rounded: "{rounded.lg}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.accent-press}"
    textColor: "#ffffff"
  button-secondary:
    backgroundColor: "{colors.card-bg}"
    textColor: "{colors.text}"
    typography: "{typography.label}"
    rounded: "{rounded.lg}"
    padding: "10px 16px"
  button-secondary-hover:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.text}"
  nav-item:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
  nav-item-active:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
  segmented-item-active:
    backgroundColor: "{colors.text}"
    textColor: "{colors.card-bg}"
    rounded: "{rounded.sm}"
    padding: "5px 12px"
  input-text:
    backgroundColor: "{colors.card-bg}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.lg}"
    padding: "10px 14px"
  card-brand:
    backgroundColor: "{colors.card-bg}"
    textColor: "{colors.text}"
    rounded: "{rounded.xxl}"
    padding: "22px 16px 18px"
  card-store:
    backgroundColor: "{colors.card-bg}"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
    padding: "10px 12px"
  card-menu-item:
    backgroundColor: "{colors.card-bg}"
    textColor: "{colors.text}"
    rounded: "{rounded.xl}"
    padding: "14px 18px"
  chip-stat:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "6px 12px"
  grade-badge:
    backgroundColor: "{colors.grade-b}"
    textColor: "#ffffff"
    rounded: "{rounded.circle}"
    size: "20px"
---

# Design System: Dining Maps

## Overview

**Creative North Star: "편집자의 지도 (The Editor's Map)"**

이 인터페이스는 앱이라기보다 **한 명의 편집자가 데이터를 추려 놓은 지면**이다. 따뜻한 종이빛 바탕 위에 흰 카드가 얹히고, 1px 괘선이 칸을 나누며, 이탤릭 세리프 워드마크가 상단에서 "이건 누군가 관점을 갖고 정리한 것"이라고 서명한다. 화면 어디에도 설득하려는 장치가 없다. 브랜드마다 흩어진 영양정보를 같은 자로 재어 놓은 것이 이 제품의 전부이고, 디자인의 일도 그 자를 흐리지 않는 것이다.

색은 극도로 아낀다. 실질 팔레트는 무채색 뉴트럴 다섯 개와 **가마 테라코타** 한 색, 그리고 등급을 말하는 4단계 색뿐이다. 테라코타는 지금 어디를 보고 있는지(활성 탭)와 무엇이 강조된 수치인지에만 쓰이고, 등급색은 오직 등급에만 쓰인다. 색이 의미를 독점하기 때문에, 색이 늘어나는 순간 이 시스템은 읽히기를 멈춘다.

밀도는 정보 쪽으로 기울어 있다. 숫자는 tabular-nums로 자릿수를 맞춰 세로로 비교되고, 표는 페이지를 밀어내지 않고 자기 안에서 가로 스크롤한다. 실사용은 이동 중 모바일이므로 760px에서 사이드바가 가로 탭으로 접히고 지도와 목록이 위아래로 쌓인다. 컴포넌트의 손맛은 **단단하고 확신 있게** — 누를 수 있는 것은 눌러도 되는 것처럼 분명하게 보이고, 애매하게 흐린 상태는 두지 않는다.

**Key Characteristics:**
- 종이빛 바탕 + 흰 카드 + 1px 괘선의 3층 구조. 배경 그라데이션 없음.
- 액센트 한 색(가마 테라코타)과 등급 4색. 그 외 색은 목적이 정해진 것만(지도 위치 점, 차트 막대, 1~3위 골드).
- 이탤릭 세리프 워드마크 하나로 브랜드를 감당하고, 본문은 전부 시스템 산세리프.
- 숫자는 항상 tabular-nums. 표와 배지가 화면의 주인공.
- 등급은 색과 **문자**로 동시에 표기한다 — 색만으로 등급을 전달하지 않는다.

## Colors

무채색 뉴트럴이 지면을 만들고, 색은 판단에만 쓰인다.

### Primary
- **가마 테라코타 (Kiln Terracotta)** (#c1440e): 구운 흙의 붉은 주황. 활성 내비게이션, 주요 실행 버튼(검색), 포커스 링, 강조된 수치, 통계 칩. 화면 전체에서 이 색이 칠해진 면적은 좁게 유지한다.
- **테라코타 프레스 (Terracotta Press)** (#a83a0c): 주요 버튼의 눌림·호버 상태에만.
- **테라코타 소프트 (Terracotta Soft)** (#fbe9e0): 액센트의 옅은 배경면 — 활성 탭 바탕, 통계 칩 바탕, 포커스 링, 정렬 중인 표 열 강조, 추천 한 줄.

### Neutral
- **웜 페이퍼 (Warm Paper)** (#f6f5f2): 앱 바탕. 카드가 아닌 모든 여백.
- **카드 화이트 (Card White)** (#ffffff): 카드·툴바·사이드바·팝업의 면.
- **잉크 (Ink)** (#23201b): 본문과 제목. 순검정이 아닌 따뜻한 흑갈색.
- **뮤티드 (Muted)** (#74706a): 보조 설명, 라벨, 단위, 비활성 내비게이션, 각주.
- **괘선 (Rule)** (#e4e0d8): 1px 테두리와 구분선 전용. 이 시스템에서 구획은 그림자가 아니라 선이 만든다.

### Tertiary — 등급 스케일
등급은 팔레트가 아니라 **척도**다. 초록에서 주황으로 내려가는 4단계 외의 값을 여기에 추가하지 않는다.
- **A — 딥 그린** (#2f8f4e) · **B — 리프 그린** (#6fa83d) · **C — 앰버** (#d99a2b) · **D — 테라코타** (#c1440e)
- D가 액센트와 같은 값인 것은 의도다. 나쁜 등급과 브랜드색이 같은 색이라 화면에 붉은 점이 늘어나지 않는다.

### 목적색 (그 외 허용되는 유일한 색)
- **로케이터 블루** (#2b6cf0): 지도 위 현 위치 점과 확산 링. 여기 말고는 쓰지 않는다.
- **차트 블루** (#2a78d6): 대시보드 막대. 등급색과 섞이면 막대가 등급으로 오독되기 때문에 일부러 계열이 다르다.
- **핀 골드** (#ffc53d) / **골드 잉크** (#5c4300): 추천 상위 3곳 핀의 테두리·순위 배지에만.
- **판정 그린** (#e3f2e6 면 / #1d7a33 글자): 신메뉴 표의 긍정 판정 배지.

### Named Rules
**한 목소리 규칙 (The One Voice Rule).** 테라코타는 "지금 여기" 또는 "이게 중요하다"만 말한다. 장식으로 칠하지 않으며, 한 화면에 테라코타로 칠해진 면이 여럿이면 하나만 남기고 지운다.

**등급색 독점 규칙 (The Grade-Only Rule).** #2f8f4e·#6fa83d·#d99a2b는 등급 이외의 어떤 의미에도 쓰지 않는다. 성공 메시지도, 긍정 지표도, 링크도 이 색을 빌려 쓸 수 없다.

**색만으로 말하지 않기 규칙 (The Never-Color-Alone Rule).** 등급을 전달하는 모든 요소는 색과 함께 A/B/C/D 문자를 반드시 노출한다. 지도 핀 안에 흰 칩으로 등급 글자를 박아 넣은 것이 이 규칙의 원형이다.

## Typography

**Wordmark Font:** Newsreader (fallback: Noto Serif KR, serif) — 이탤릭 500, 워드마크 전용
**Body Font:** 시스템 스택 (-apple-system, Segoe UI, Apple SD Gothic Neo, Noto Sans KR, sans-serif)

**Character:** 서체는 딱 한 번만 목소리를 낸다. 상단 워드마크의 이탤릭 세리프가 편집자의 서명이고, 그 아래 전부는 한글이 가장 정확히 렌더링되는 시스템 산세리프다. 웹폰트를 본문에 들이지 않는 것은 미학이자 성능 결정이다.

### Hierarchy
- **Wordmark** (Newsreader italic 500, 21px, letter-spacing -0.01em): 상단바 로고 옆. 이 서체가 등장하는 유일한 자리.
- **Display** (600, 1.7rem): 대시보드 KPI 수치. 화면에서 가장 큰 글자는 항상 숫자다.
- **Headline** (600, 18px): 섹션 제목(h2).
- **Title** (600, 15~16px): 카드 이름, 메뉴 이름, 매장 이름.
- **Body** (400, 14px, line-height 1.6): 본문과 폼 입력.
- **Label** (600, 12px): 내비게이션, 필터 라벨, 칩, 셀렉트, 상태 표기.
- **Caption** (400, 11px): 거리, 주소, 각주, 영양소 배지.
- **Data** (400, 0.85rem, `font-variant-numeric: tabular-nums`): 표 셀과 막대 수치.

### Named Rules
**세리프 1회 규칙 (The Single Serif Rule).** Newsreader는 워드마크에서만 쓴다. 제목·인용·강조로 세리프를 확장하는 순간 "편집자의 서명"이 흔한 장식이 된다.

**자릿수 규칙 (The Tabular Rule).** 세로로 비교될 모든 숫자는 `font-variant-numeric: tabular-nums`를 쓴다. 표의 수치 열은 우측 정렬, 이름·브랜드 등 텍스트 열은 좌측 정렬.

**한글 줄바꿈 규칙 (The Keep-All Rule).** 좁은 오버레이(지도 팝업 등)는 `word-break: keep-all`로 단어 중간이 끊기지 않게 한다.

## Layout

**앱 셸** — CSS Grid 3영역: 상단바 68px 고정, 좌측 사이드바 200px, 나머지가 main. 높이는 `100vh`로 고정되고 스크롤은 main 안에서만 일어난다. 지도 뷰는 `overflow: hidden`으로 화면을 꽉 채우고, 나머지 페이지 뷰는 `overflow-y: auto`.

**읽기 폭** — 페이지형 뷰(목록·메뉴·대시보드)는 최대 960px(대시보드 56rem)에서 가운데 정렬로 멈춘다. 지도만 이 제한을 받지 않는다.

**지도 뷰** — 상단 툴바(검색 + 필터) → 지도와 매장 목록이 좌우 분할. 매장 목록은 300px 고정, 지도가 나머지를 흡수. 검색창은 `flex: 0 1 440px`로 넓은 화면에서도 늘어나지 않는다 — 전체 폭으로 벌어지면 버튼과 필터가 양끝으로 흩어져 한 덩어리로 읽히지 않기 때문이다.

**리듬** — 간격은 4px 배수(4·8·12·16·24·32). 카드 그리드는 `repeat(auto-fill, minmax(180px, 1fr))`, 간격 14px.

**반응형** — 주 분기점은 **760px**. 이 아래에서 사이드바가 상단 가로 탭으로 바뀌고(테두리도 우측에서 하단으로 이동), 지도와 목록이 세로로 쌓이며(지도 `min-height: 55vh`, 목록 `max-height: 40vh`), 상단 서브타이틀은 숨는다. 보조 분기점 640px에서 대시보드 막대 행의 라벨 열이 좁아진다.

### Named Rules
**표만 스크롤 규칙 (The Table-Scrolls-Alone Rule).** 넓은 표는 페이지 전체를 가로로 밀지 않는다. 래퍼에 `overflow-x: auto`를 걸어 표가 자기 안에서만 스크롤하게 한다. 모바일에서 body가 가로로 흔들리는 것은 결함으로 취급한다.

**지도는 살아 있다 규칙 (The Map Stays Mounted Rule).** 탭을 옮겨도 지도는 언마운트하지 않고 `display: none`으로 숨긴다. 지도 인스턴스와 마커, 현재 중심을 잃지 않기 위한 규칙이며 레이아웃 전제이기도 하다.

## Elevation & Depth

기본은 **선으로 만든 깊이**다. 구획은 1px 괘선이 만들고, 그림자는 두 가지 일만 한다: ①정말로 떠 있는 것(오버레이·지도 핀)을 띄우고 ②카드가 만질 수 있는 물건임을 알린다.

카드는 쉬는 상태에서도 아주 얕은 그림자를 갖는다 — 종이 위에 얹힌 카드가 완전히 평평할 수는 없다. 다만 그 그림자는 알아채기 전에 느껴지는 정도(alpha 0.05 내외)여야 하고, 호버에서 한 단계 올라가며 2px 떠오른다. 이보다 진한 그림자는 오버레이의 몫이다.

### Shadow Vocabulary
- **rest** (`--shadow-rest: 0 1px 3px rgba(35, 32, 27, 0.05)`): 카드·패널의 쉬는 상태. 잉크색 기반이라 종이 바탕에서 회색으로 뜨지 않는다.
- **hover** (`box-shadow: 0 6px 18px rgba(0, 0, 0, 0.06)` + `transform: translateY(-2px)`): 클릭 가능한 카드의 호버.
- **topbar** (`box-shadow: 0 1px 0 var(--border), 0 6px 14px -10px rgba(35, 32, 27, 0.12)`): 상단바가 스크롤되는 본문 위에 있음을 알리는 헤어라인 + 극도로 눌린 확산.
- **overlay-soft** (`box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1)`): 지도 위 범례처럼 지도에 얹힌 정보 패널.
- **overlay** (`box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15)`): 팝오버(대시보드 설명 말풍선).
- **overlay-strong** (`box-shadow: 0 6px 20px rgba(0, 0, 0, 0.18)`): 지도 매장 팝업.
- **pin** (`box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3)`) / **pin-top** (`0 4px 14px rgba(0, 0, 0, 0.35)`): 지도 핀. 지도 타일이라는 시각적 소음 위에서 읽혀야 해서 유일하게 진하다.
- **focus** (`box-shadow: 0 0 0 3px var(--accent-soft)` + `border-color: var(--accent)`): 포커스 링. 깊이가 아니라 상태다.

### Named Rules
**얹힌 만큼만 규칙 (The Weight-of-Being-Above Rule).** 그림자의 세기는 장식이 아니라 "무엇 위에 떠 있는가"로 정한다. 종이 위 카드는 rest, 본문 위 오버레이는 overlay, 지도 타일 위 핀은 pin. 이 순서를 뒤집는 그림자는 잘못된 그림자다.

**포커스는 링으로 규칙 (The Ring-Not-Glow Rule).** 포커스는 3px 소프트 액센트 링 + 액센트 테두리로만 표현한다. `outline: none`만 걸고 대체 표시를 두지 않는 것은 금지다.

## Shapes

모서리는 **크기에 비례**한다. 작은 조각일수록 각지고, 손에 쥐는 큰 카드일수록 둥글다: 배지·영양소 칩 6px → 내비게이션·셀렉트·토글 8px → 입력창·버튼·매장 카드 10px → 메뉴 항목·팝업 12px → 티어 라벨 14px → 브랜드 카드·아바타 16px. 완전한 알약(999px)은 상태를 말하는 칩(통계 칩, 대시보드 탭, 지도 상태 표시)에만, 완전한 원(50%)은 등급 배지와 순위 배지에만.

테두리는 언제나 1px 실선 괘선색이다. 2px 이상의 테두리는 지도 핀(흰 2px 외곽선)과 추천 상위 핀(골드 3px)에만 허용된다 — 지도 위에서 배경과 분리되어야 하기 때문이다.

**시그니처 형태**: 지도 핀의 `border-radius: 12px 12px 12px 2px`. 좌하단만 각져서 말풍선 꼬리처럼 지면을 가리킨다. 이 비대칭이 이 제품의 유일한 형태적 서명이다.

**데이터 막대**는 기준선 쪽을 각지게, 값 쪽만 둥글게(`border-radius: 0 4px 4px 0`) 한다. 0에서 시작한다는 사실을 형태가 말한다.

### Named Rules
**작을수록 각지게 규칙 (The Smaller-Is-Sharper Rule).** 새 요소의 반경은 크기에서 유도한다. 20px 배지에 12px 반경을 주지 않고, 180px 카드에 6px 반경을 주지 않는다.

## Components

### Buttons
- **Shape:** 완만한 둥근 모서리(10px). 라벨은 12~13px, weight 600.
- **Primary:** 테라코타 면에 흰 글자, 테두리도 같은 색. 패딩 `10px 16px`. 한 화면에 하나가 원칙(지도 툴바의 "검색").
- **Secondary:** 흰 면 + 1px 괘선 + 잉크 글자. 호버 시 면이 종이색으로 가라앉는다.
- **Hover / Focus:** Primary는 테라코타 프레스로 어두워지고, Secondary는 배경만 바뀐다. 키보드 포커스는 어느 쪽이든 3px 소프트 링.
- **Text button:** 되돌아가기처럼 흐름을 방해하면 안 되는 동작은 테두리 없이 테라코타 글자만.

### Navigation
- **사이드바 항목:** 아이콘 18px + 라벨 14px/600, 패딩 `10px 12px`, 반경 8px. 기본은 뮤티드 글자에 투명 배경, 호버 시 종이색 배경, **활성 시 소프트 테라코타 배경 + 테라코타 글자**.
- **모바일(≤760px):** 같은 항목이 가로 탭 줄로 바뀐다. 아이콘과 라벨을 함께 유지한다 — 아이콘만 남기지 않는다.
- **드릴다운 규칙:** 메뉴 상세는 목록의 하위 화면이므로 "매장 목록" 항목이 활성 상태를 유지한다.

### Segmented Control (절대·상대 전환)
- 흰 면에 1px 괘선, 반경 8px, 안쪽 여백 3px의 트랙 안에 버튼 2개.
- 선택된 쪽은 **잉크 면에 흰 글자**, weight 600. 액센트를 쓰지 않는 것이 의도다 — 이 토글은 "지금 어떤 기준으로 보는가"라는 중립적 선택이지 강조가 아니다.
- 툴바처럼 흰 배경 위에 놓일 때는 트랙 배경을 종이색으로 낮춰 구분한다.

### Chips
- **통계 칩:** 소프트 테라코타 면 + 테라코타 글자, 알약(999px), `6px 12px`, 12px/600. 브랜드 요약 수치용.
- **필터 탭 칩:** 흰 면 + 괘선 + 알약. 활성 시 테라코타 면 + 흰 글자.
- **영양소 배지:** 종이색 면 + 괘선, 반경 6px, 11px. 수치만 테라코타.
- **기준 배지:** 100g당·전체처럼 값의 전제를 밝히는 아주 작은 배지(0.68rem, 뮤티드, 괘선). 전제가 다른 값은 배지 없이 나란히 놓지 않는다.

### Cards / Containers
- **Corner:** 브랜드 카드 16px, 메뉴 항목 12px, 매장 카드 10px, 대시보드 카드 0.6rem.
- **Background / Border:** 흰 면 + 1px 괘선이 기본. 예외는 티어 목록의 브랜드 카드 하나로, 그 브랜드의 등급색을 9% 틴트로 깔고 테두리도 같은 등급색 33%를 쓴다(`gradeTint`/`gradeBorder`). 등급별로 줄 세운 화면에서 카드 자체가 그 줄의 색을 옅게 물고 있어야 티어 라벨과 한 덩어리로 읽히기 때문이다. 이 예외를 다른 카드로 확장하지 않는다.
- **Shadow:** rest 그림자를 기본으로 갖는다(Elevation 참조). 클릭 가능한 카드만 호버에서 `translateY(-2px)` + hover 그림자, 테두리는 테라코타로. 전이는 `0.12s ease`.
- **Padding:** 브랜드 카드 `22px 16px 18px`, 메뉴 항목 `14px 18px`, 매장 카드 `10px 12px`.
- **브랜드 아바타:** 56px 흰 타일, 반경 16px, 안쪽 여백 7px, 로고는 `object-fit: contain`. 브랜드 로고마다 자체 여백과 비율이 제각각이라 `cover`는 글자를 잘라낸다 — 타일의 여백이 시각적 무게를 대신 맞춘다.

### Inputs / Fields
- 흰 면, 1px 괘선, 반경 10px(대시보드 폼은 0.4rem), 패딩 `10px 14px`, 14px 본문.
- **Focus:** `outline: none` + 테두리 테라코타 + 3px 소프트 테라코타 링. 예외 없다.
- **Select:** 같은 언어를 12px/600 라벨 크기로 축소한 형태.

### Grade Badge (시그니처)
- 20px 원, 흰 글자 700, 등급색 면. **절대 등급은 불투명, 상대 등급은 같은 배지를 opacity 0.65로** 나란히 놓는다 — 두 기준이 함께 산다는 제품의 핵심 논거가 이 한 쌍의 배지로 표현된다.
- 배지 옆에는 언제나 기준을 밝히는 툴팁 또는 범례 한 줄이 따른다.
- 티어 라벨(68px, 반경 14px)은 같은 등급색 면에 24px/700 글자 + 10px 캡션으로, 그 등급이 무엇을 뜻하는지(상위 25% / 80점 이상)를 함께 적는다.

### Map Pin (시그니처)
- 등급색 면, 흰 2px 외곽선, `border-radius: 12px 12px 12px 2px`, 흰 글자 700/12px, pin 그림자.
- 안에 **흰 칩으로 등급 문자**를 박는다(색만으로 전달하지 않기 위해).
- 추천 상위 3곳: 골드 3px 테두리 + 반경 14px + 왕관 + 골드 원형 순위 배지. 이 강조는 상위 3개까지만이며 늘리지 않는다.
- **현 위치**: 로케이터 블루 점 + 흰 2.5px 테두리 + 2초 확산 링. 지도 위에서 파란색은 오직 "나"다.

### Map Popup
- 흰 면, 1px 괘선, 반경 12px, 폭 220px, overlay-strong 그림자, `word-break: keep-all`.
- 우상단에 테두리 없는 닫기 버튼, 하단에 폭 100% 테라코타 실행 버튼(반경 8px).

### Data Table
- 헤더는 뮤티드 12~13px/600, 셀은 0.85rem tabular-nums. 행 구분은 `border-bottom: 1px solid` 괘선뿐 — 세로선도 줄무늬 배경도 없다.
- 수치 열 우측 정렬, 텍스트 열(이름·브랜드·카테고리) 좌측 정렬.
- **정렬 중인 열**은 소프트 테라코타 배경 + 600, 헤더 글자도 테라코타. 지금 무엇으로 줄 세웠는지가 표 자체에 보인다.
- 부가 설명은 접이식(`<details>`)으로 숨긴다.

### Named Rules
**전제를 붙여 보내는 규칙 (The Basis-Travels-With-Value Rule).** 기준이 다른 수치(1인분·100g당·용기 전체, 식사 기준·음료 기준)는 반드시 기준 배지 또는 캡션과 함께 렌더한다. 전제 없는 숫자는 이 시스템에서 미완성이다.

## Do's and Don'ts

### Do:
- **Do** 새 색이 필요하면 먼저 뉴트럴 5색과 소프트 테라코타로 해결되는지 확인한다. 색은 판단(등급)과 초점(액센트)에만 쓴다.
- **Do** 등급을 표시할 때 색과 A/B/C/D 문자를 함께 낸다.
- **Do** 절대 등급과 상대 등급을 한 쌍으로 놓고, 상대 쪽을 opacity 0.65로 낮춰 위계를 준다.
- **Do** 세로로 비교되는 숫자에 `font-variant-numeric: tabular-nums`를 건다.
- **Do** 포커스 상태를 3px 소프트 테라코타 링 + 테라코타 테두리로 표현한다.
- **Do** 넓은 표는 자체 래퍼에서 가로 스크롤시키고, 760px 이하에서 지도와 목록을 세로로 쌓는다.
- **Do** 새 요소의 모서리 반경을 크기에서 유도한다(작을수록 각지게).
- **Do** 기준이 다른 수치에 기준 배지를 붙여 보낸다.

### Don't:
- **Don't** 배달앱의 언어를 빌리지 않는다 — 채도 높은 빨강·노랑, 큰 음식 사진 타일, 할인·프로모션 배지. 이 제품은 파는 곳이 아니라 재는 곳이다.
- **Don't** 게이미피케이션을 넣지 않는다 — 링 차트, 달성 배지, 연속 기록, 축하 애니메이션. 등급은 점수판이 아니라 측정값이다.
- **Don't** 등급색(#2f8f4e·#6fa83d·#d99a2b)을 등급 이외의 의미로 재사용하지 않는다.
- **Don't** 워드마크 밖에서 Newsreader를 쓰지 않는다. 본문 웹폰트를 추가하지 않는다.
- **Don't** 배경 그라데이션, 유리 효과(backdrop-blur), 둥둥 떠다니는 큰 그림자를 쓰지 않는다. 지도 위 범례의 92% 흰 배경이 반투명의 상한이다.
- **Don't** `outline: none`을 대체 포커스 표시 없이 남기지 않는다.
- **Don't** 로케이터 블루를 현 위치 외의 것에 쓰지 않는다.
- **Don't** 상위 3위 골드 강조를 4위 이하로 확장하지 않는다.
- **Don't** px 스케일과 rem 스케일을 한 화면 안에서 섞지 않는다. 앱 셸·지도는 px, 대시보드·탐색기는 rem이 현재의 경계선이며, 새 화면은 둘 중 하나를 택해 일관되게 간다.
