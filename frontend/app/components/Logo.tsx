"use client";

import { useId } from "react";

export default function Logo({ size = 22 }: { size?: number }) {
  const uid = useId();
  const violetId = `logoViolet-${uid}`;
  const cyanId = `logoCyan-${uid}`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      style={{ flexShrink: 0 }}
    >
      <defs>
        <linearGradient id={violetId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#9b8dff" />
          <stop offset="1" stopColor="#5d4fc9" />
        </linearGradient>
        <linearGradient id={cyanId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7af0f5" />
          <stop offset="1" stopColor="#2bb8c2" />
        </linearGradient>
      </defs>

      {/* foundation: already built */}
      <rect x="13" y="37" width="38" height="16" rx="8" fill={`url(#${violetId})`} />
      <circle cx="23" cy="29" r="12" fill={`url(#${violetId})`} />
      <circle cx="41" cy="29" r="12" fill={`url(#${violetId})`} />

      {/* hub accent, hints at the circuit mesh from the full mark */}
      <circle cx="32" cy="44" r="2.2" fill={`url(#${cyanId})`} />

      {/* connector from the foundation up to the arriving piece */}
      <line x1="32" y1="15" x2="32" y2="21" stroke={`url(#${cyanId})`} strokeWidth="3" strokeLinecap="round" opacity="0.9" />

      {/* the final piece, arriving */}
      <circle cx="32" cy="11" r="8" fill={`url(#${cyanId})`} />
      <ellipse cx="29" cy="8" rx="2.6" ry="1.6" fill="#ffffff" opacity="0.35" transform="rotate(-25 29 8)" />
    </svg>
  );
}
