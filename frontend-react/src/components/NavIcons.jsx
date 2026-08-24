// Stroke-based line icons for the sidebar nav -- replaces the old dingbat
// glyphs (▦ ★ ◎ ☰), which render inconsistently across fonts/platforms.
const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" };

export function IconDashboard({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...common}>
      <rect x="3.5" y="3.5" width="7.5" height="7.5" rx="1.5" />
      <rect x="13" y="3.5" width="7.5" height="7.5" rx="1.5" />
      <rect x="3.5" y="13" width="7.5" height="7.5" rx="1.5" />
      <rect x="13" y="13" width="7.5" height="7.5" rx="1.5" />
    </svg>
  );
}

export function IconStar({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...common}>
      <path d="M12 3.5l2.6 5.6 6 .7-4.5 4.2 1.2 6-5.3-3-5.3 3 1.2-6-4.5-4.2 6-.7z" />
    </svg>
  );
}

export function IconPin({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...common}>
      <path d="M12 21s-7-6.1-7-11.5A7 7 0 0 1 19 9.5C19 14.9 12 21 12 21z" />
      <circle cx="12" cy="9.5" r="2.4" />
    </svg>
  );
}

export function IconList({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...common}>
      <line x1="4" y1="6.5" x2="20" y2="6.5" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="4" y1="17.5" x2="20" y2="17.5" />
    </svg>
  );
}
