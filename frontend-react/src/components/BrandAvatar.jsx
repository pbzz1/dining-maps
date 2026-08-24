import { useState } from "react";

const PALETTE = [
  "#c1440e", "#2f8f4e", "#2b6cb0", "#6b46c1",
  "#b7791f", "#0f766e", "#be185d", "#4b5563",
];

function colorFor(name) {
  let sum = 0;
  for (const ch of name) sum += ch.codePointAt(0);
  return PALETTE[sum % PALETTE.length];
}

function initials(name) {
  return /^[A-Za-z0-9]+$/.test(name) ? name.slice(0, 3).toUpperCase() : name.charAt(0);
}

// Renders /logos/<slug>.png when one exists (drop the file in and it just
// works, no code change) and falls back to a colored monogram otherwise --
// covers brands nobody's sourced a logo image for yet.
export default function BrandAvatar({ name, slug }) {
  const [imgFailed, setImgFailed] = useState(false);
  const showImage = slug && !imgFailed;

  return (
    <div className="brand-avatar" style={showImage ? undefined : { background: colorFor(name) }}>
      {showImage ? (
        <img src={`/logos/${slug}.png`} alt="" onError={() => setImgFailed(true)} />
      ) : (
        <span>{initials(name)}</span>
      )}
    </div>
  );
}
