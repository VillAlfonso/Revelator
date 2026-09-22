import React from 'react';

/**
 * Shared password policy + live strength UI.
 *
 * Requirements (hard, block submit): 8+ chars, one letter, one number.
 * The remaining checks (uppercase, symbol, 12+) are strength boosters only, so
 * the frontend never rejects a password the backend would accept.
 */

export const PASSWORD_MIN = 8;

export function passwordChecks(pw) {
  const p = pw || '';
  return {
    length:    p.length >= PASSWORD_MIN,
    letter:    /[A-Za-z]/.test(p),
    number:    /\d/.test(p),
    upperLower: /[a-z]/.test(p) && /[A-Z]/.test(p),
    symbol:    /[^A-Za-z0-9]/.test(p),
    long:      p.length >= 12,
  };
}

/** true when the hard requirements are met */
export function passwordMeetsPolicy(pw) {
  const c = passwordChecks(pw);
  return c.length && c.letter && c.number;
}

/** First failing hard requirement, as a message. '' when the password passes. */
export function passwordPolicyError(pw) {
  if (!pw) return 'Password is required';
  const c = passwordChecks(pw);
  if (!c.length) return `Minimum ${PASSWORD_MIN} characters`;
  if (!c.letter || !c.number) return 'Include at least one letter and one number';
  return '';
}

/** 0-4 score -> {score, label, color} */
export function passwordStrength(pw) {
  const p = pw || '';
  if (!p) return { score: 0, label: '', color: '#3f6e4a' };

  const c = passwordChecks(p);
  let score = 0;
  if (c.length) score += 1;
  if (c.upperLower) score += 1;
  if (c.number) score += 1;
  if (c.symbol) score += 1;
  if (c.long) score += 1;

  // Anything failing the hard policy can never read better than Weak.
  if (!passwordMeetsPolicy(p)) score = Math.min(score, 1);

  // Obvious junk (all one character, straight sequences) is capped too.
  if (/^(.)\1+$/.test(p) || /^(?:0123456789|abcdefghij|qwertyuiop|password\d*)$/i.test(p)) {
    score = Math.min(score, 1);
  }

  if (score <= 1) return { score: 1, label: 'Weak', color: '#ff8a99' };
  if (score === 2) return { score: 2, label: 'Fair', color: '#ffaa00' };
  if (score === 3) return { score: 3, label: 'Good', color: '#86efac' };
  if (score === 4) return { score: 4, label: 'Strong', color: '#00ff66' };
  return { score: 5, label: 'Very Strong', color: '#00ff66' };
}

function Rule({ ok, children, optional }) {
  return (
    <li style={{
      display: 'flex', alignItems: 'flex-start', gap: 7, marginBottom: 3,
      color: ok ? '#86efac' : (optional ? '#3f6e4a' : '#6dba85'),
    }}>
      <span style={{ width: 10, flexShrink: 0, color: ok ? '#00ff66' : '#3f6e4a' }}>
        {ok ? '✓' : '·'}
      </span>
      <span>{children}{optional ? ' (recommended)' : ''}</span>
    </li>
  );
}

/**
 * Meter + requirement checklist. Renders nothing until the user starts typing
 * unless `always` is set.
 */
export default function PasswordStrength({ password, always = false }) {
  const pw = password || '';
  if (!pw && !always) return null;

  const c = passwordChecks(pw);
  const { score, label, color } = passwordStrength(pw);
  const segments = 5;

  return (
    <div style={{ marginTop: 9 }}>
      <div style={{ display: 'flex', gap: 4, marginBottom: 6 }}>
        {Array.from({ length: segments }).map((_, i) => (
          <div
            key={i}
            style={{
              flex: 1, height: 4, borderRadius: 2,
              background: pw && i < score ? color : '#112418',
              transition: 'background 160ms linear',
            }}
          />
        ))}
      </div>
      {pw && (
        <div className="mono" style={{
          fontSize: 10, letterSpacing: 2, textTransform: 'uppercase',
          color, marginBottom: 8,
        }}>
          Strength: {label}
        </div>
      )}
      <ul className="mono" style={{
        listStyle: 'none', padding: 0, margin: 0, fontSize: 11, lineHeight: 1.5,
      }}>
        <Rule ok={c.length}>At least {PASSWORD_MIN} characters</Rule>
        <Rule ok={c.letter}>Contains a letter</Rule>
        <Rule ok={c.number}>Contains a number</Rule>
        <Rule ok={c.upperLower} optional>Upper and lower case</Rule>
        <Rule ok={c.symbol} optional>A symbol (!@#$...)</Rule>
      </ul>
    </div>
  );
}
