import React from 'react';

// REVELATOR logo
//   • Outer scan ring + crosshair ticks  → forensic targeting
//   • Inscribed triangle (eye-of-providence) → "revelation"
//   • Fingerprint whorl inside triangle  → forensic identity
// All-vector, scales cleanly from 16px to 256px.
export default function Logo({ size = 48, glow = true, animated = false, className = '', style = {} }) {
  const id = React.useId();
  const filterId  = `${id}-glow`;
  const clipId    = `${id}-tri`;
  const gradId    = `${id}-bg`;
  const ringClass = animated ? 'logo-ring-spin' : '';

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      className={className}
      style={{ display: 'block', ...style }}
      aria-label="Revelator"
      role="img"
    >
      <defs>
        <radialGradient id={gradId} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#0a120c" />
          <stop offset="100%" stopColor="#000" />
        </radialGradient>
        {glow && (
          <filter id={filterId} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="1.2" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        )}
        <clipPath id={clipId}>
          <polygon points="50,18 82,72 18,72" />
        </clipPath>
      </defs>

      {/* outer scan ring */}
      <g filter={glow ? `url(#${filterId})` : undefined}>
        <circle cx="50" cy="50" r="46" fill={`url(#${gradId})`} stroke="#00ff66" strokeWidth="1.6" />
      </g>
      <circle cx="50" cy="50" r="42" fill="none" stroke="#00ff66" strokeWidth="0.5" opacity="0.45"
        strokeDasharray="2 3" className={ringClass} style={{ transformOrigin: '50% 50%' }} />

      {/* crosshair ticks at cardinal points */}
      <g stroke="#00ff66" strokeWidth="1.4" strokeLinecap="round" filter={glow ? `url(#${filterId})` : undefined}>
        <line x1="50" y1="2"  x2="50" y2="9" />
        <line x1="50" y1="91" x2="50" y2="98" />
        <line x1="2"  y1="50" x2="9"  y2="50" />
        <line x1="91" y1="50" x2="98" y2="50" />
      </g>

      {/* illuminati triangle */}
      <polygon
        points="50,18 82,72 18,72"
        fill="none" stroke="#00ff66" strokeWidth="1.6"
        strokeLinejoin="round"
        filter={glow ? `url(#${filterId})` : undefined}
      />

      {/* fingerprint whorls clipped to triangle */}
      <g clipPath={`url(#${clipId})`} stroke="#00ff66" fill="none" opacity="0.92" strokeLinecap="round">
        <path d="M 28 62 Q 50 42 72 62" strokeWidth="0.8" />
        <path d="M 32 62 Q 50 46 68 62" strokeWidth="0.8" />
        <path d="M 36 62 Q 50 50 64 62" strokeWidth="0.8" />
        <path d="M 40 62 Q 50 54 60 62" strokeWidth="0.8" />
        <path d="M 44 62 Q 50 58 56 62" strokeWidth="0.8" />
        {/* core dot */}
        <circle cx="50" cy="60" r="1.4" fill="#00ff66" stroke="none" />
      </g>

      {/* tiny corner brackets — evidence frame */}
      <g stroke="#00ff66" strokeWidth="1.2" fill="none" opacity="0.7">
        <path d="M 6 14 L 6 6 L 14 6" />
        <path d="M 86 6 L 94 6 L 94 14" />
        <path d="M 94 86 L 94 94 L 86 94" />
        <path d="M 14 94 L 6 94 L 6 86" />
      </g>
    </svg>
  );
}

// Wordmark — used on auth pages. Logo on left, REVELATOR text on right.
export function LogoWordmark({ size = 64, style = {} }) {
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 14, ...style }}>
      <Logo size={size} glow animated />
      <div style={{ textAlign: 'left' }}>
        <div className="oswald glow-strong" style={{
          fontSize: size * 0.6, fontWeight: 700, color: '#00ff66',
          letterSpacing: 6, lineHeight: 1,
        }}>
          REVELATOR
        </div>
        <div className="mono" style={{
          fontSize: 9, letterSpacing: 4, color: '#6dba85', marginTop: 4,
        }}>
          FORENSIC · DOCUMENT · ENGINE
        </div>
      </div>
    </div>
  );
}
