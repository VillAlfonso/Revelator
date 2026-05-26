/**
 * Theme-aware color helpers.
 *
 * Many components use bright accent colors (category pastels, forensic-group
 * tints) that look great on the dark Matrix background but turn unreadable
 * on the off-white light-mode surface. The CSS attribute selectors in
 * index.css handle most of these globally, but where a component composes
 * a color into something more complex (alpha tints, computed gradients,
 * canvas drawing), the JS needs to know which color to use.
 *
 * Usage:
 *   import { themed } from '../themeColors';
 *   import { useTheme } from '../App';
 *   const { theme } = useTheme();
 *   const color = themed('#c4b5fd', theme);   // → '#4a2a92' in light, original in dark
 */

const LIGHT_MAP = {
  // ForensicsGuide group accents
  '#c4b5fd': '#4a2a92', // violet — traced signatures
  '#fbbf24': '#8c5a00', // amber  — document alteration
  '#38bdf8': '#0d4a72', // sky    — digital fabrication
  '#f87171': '#9b2030', // red    — obliteration
  '#34d399': '#0a6a4a', // mint   — sympathetic ink
  '#a78bfa': '#4a2a92', // violet (alt)

  // Category greens from categories.js
  '#00ff66': '#005a22',
  '#3df58a': '#006a30',
  '#56ff8a': '#006a35',
  '#7cffaf': '#006a3c',
  '#9bffba': '#006a48',
  '#00ffaa': '#005a3a',
  '#a3e635': '#3a5a14',

  // Common UI accents
  '#ff3344': '#9b2030',
  '#ffa040': '#8c5a00',
  '#737373': '#4a4a4a',
};

export function themed(color, theme) {
  if (!color || theme !== 'light') return color;
  return LIGHT_MAP[String(color).toLowerCase()] || color;
}

/**
 * Returns a CSS-string with a tinted background suitable for a light-on-dark
 * pill in dark mode or a dark-on-light pill in light mode.
 */
export function tintedBg(color, theme, alpha = 0.12) {
  const base = themed(color, theme);
  // Convert hex → rgb
  const hex = base.replace('#', '');
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
