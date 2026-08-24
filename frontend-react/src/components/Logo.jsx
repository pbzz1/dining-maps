// Pin (지도) + fork (메뉴 비교) in one mark. Single accent color so it drops
// into a dark topbar or a light one without a separate "reversed" asset.
export default function LogoMark({ size = 36 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
      <rect x="2" y="2" width="44" height="44" rx="13" fill="var(--accent)" />
      <path
        d="M24 40 C24 40 12 27 12 18 C12 10.8 17.4 6 24 6 C30.6 6 36 10.8 36 18 C36 27 24 40 24 40 Z"
        fill="#ffffff"
      />
      <rect x="18.9" y="10" width="2.2" height="12" rx="1.1" fill="var(--accent)" />
      <rect x="22.9" y="10" width="2.2" height="24" rx="1.1" fill="var(--accent)" />
      <rect x="26.9" y="10" width="2.2" height="12" rx="1.1" fill="var(--accent)" />
    </svg>
  );
}
