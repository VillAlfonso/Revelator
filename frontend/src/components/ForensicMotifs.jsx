import React from 'react';

// Background fingerprint watermark — large, faint, decorative.
// Place absolutely positioned with low opacity behind hero content.
export function FingerprintWatermark({ size = 320, color = '#00ff66', opacity = 0.05, style = {} }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 200 200"
      style={{ pointerEvents: 'none', opacity, ...style }}
      aria-hidden="true"
    >
      <g stroke={color} fill="none" strokeWidth="1.2" strokeLinecap="round">
        {/* concentric whorls */}
        <path d="M 100 100 m -85 0 a 85 85 0 1 1 170 0 a 85 85 0 1 1 -170 0" />
        <path d="M 100 100 m -75 5 a 75 80 0 1 1 150 -10 a 75 80 0 1 1 -150 10" />
        <path d="M 100 100 m -65 -5 a 65 75 0 1 1 130 15 a 65 75 0 1 1 -130 -15" />
        <path d="M 100 100 m -55 8 a 55 70 0 1 1 110 -18 a 55 70 0 1 1 -110 18" />
        <path d="M 100 100 m -45 -3 a 45 60 0 1 1 90 8 a 45 60 0 1 1 -90 -8" />
        <path d="M 100 100 m -35 5 a 35 50 0 1 1 70 -12 a 35 50 0 1 1 -70 12" />
        <path d="M 100 100 m -25 -2 a 25 40 0 1 1 50 4 a 25 40 0 1 1 -50 -4" />
        <path d="M 100 100 m -15 3 a 15 28 0 1 1 30 -6 a 15 28 0 1 1 -30 6" />
        {/* core */}
        <circle cx="100" cy="100" r="4" fill={color} stroke="none" />
        {/* a few breaks/minutiae points to look organic */}
        <line x1="155" y1="60" x2="170" y2="50" strokeWidth="0.7" opacity="0.6" />
        <line x1="40"  y1="140" x2="25" y2="155" strokeWidth="0.7" opacity="0.6" />
      </g>
    </svg>
  );
}

// Eye-of-providence inside circle — small accent for tier headers, etc.
export function EyeMark({ size = 22, color = '#00ff66', style = {} }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" style={style} aria-hidden="true">
      <g stroke={color} fill="none" strokeWidth="1.3" strokeLinejoin="round">
        <polygon points="12,3 22,21 2,21" />
        {/* eye */}
        <ellipse cx="12" cy="16" rx="5" ry="2.5" />
        <circle  cx="12" cy="16" r="1.4" fill={color} stroke="none" />
      </g>
    </svg>
  );
}

// Compact magnifying glass icon
export function MagnifierIcon({ size = 18, color = '#00ff66', style = {} }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" style={style} aria-hidden="true">
      <g stroke={color} fill="none" strokeWidth="2" strokeLinecap="round">
        <circle cx="10.5" cy="10.5" r="6.5" />
        <line x1="15.5" y1="15.5" x2="21" y2="21" />
        {/* lens highlight */}
        <line x1="7" y1="8" x2="7" y2="11" strokeWidth="1" opacity="0.6" />
      </g>
    </svg>
  );
}

// Crosshair / reticle — used decoratively in scan area
export function Crosshair({ size = 32, color = '#00ff66', style = {} }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" style={style} aria-hidden="true">
      <g stroke={color} fill="none" strokeWidth="1">
        <circle cx="16" cy="16" r="14" opacity="0.4" />
        <circle cx="16" cy="16" r="9" opacity="0.6" />
        <line x1="16" y1="2"  x2="16" y2="9" />
        <line x1="16" y1="23" x2="16" y2="30" />
        <line x1="2"  y1="16" x2="9"  y2="16" />
        <line x1="23" y1="16" x2="30" y2="16" />
        <circle cx="16" cy="16" r="1.5" fill={color} stroke="none" />
      </g>
    </svg>
  );
}

// Evidence-tag chip used for case-file labels.
export function EvidenceTag({ children, color = '#00ff66', style = {} }) {
  return (
    <span
      className="mono"
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 8,
        fontSize: 10, letterSpacing: 2.5, color,
        textTransform: 'uppercase',
        padding: '4px 10px 4px 6px',
        background: 'rgba(0,0,0,0.55)',
        border: `1px solid ${color}55`,
        borderRadius: 2,
        textShadow: `0 0 6px ${color}80`,
        ...style,
      }}
    >
      <span style={{
        display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
        background: color, boxShadow: `0 0 6px ${color}`,
      }} />
      {children}
    </span>
  );
}

// Animated fingerprint scan banner — used as the hero centerpiece on /scan.
// Renders a fingerprint with a horizontal sweep line that travels top→bottom.
export function FingerprintScan({ size = 200, color = '#00ff66', style = {} }) {
  return (
    <div
      style={{
        position: 'relative', width: size, height: size,
        margin: '0 auto', ...style,
      }}
      aria-hidden="true"
    >
      <FingerprintWatermark size={size} color={color} opacity={0.55} />
      <div
        className="fingerprint-sweep"
        style={{
          position: 'absolute', left: 0, right: 0, top: 0,
          height: 2,
          background: `linear-gradient(90deg, transparent, ${color}, transparent)`,
          boxShadow: `0 0 14px ${color}, 0 0 28px ${color}80`,
        }}
      />
    </div>
  );
}
