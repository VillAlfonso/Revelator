import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import PromptDashboard from '../components/PromptDashboard';

// Backend groups stay 6 (Digital, Alteration, Traced, Obliteration, Sympathetic Ink, Currency).
// Each backend group maps to several leaf classes that the user picks individually on /scan.
const CATEGORY_META = {
  Digital:           { code: 'DIG', icon: '⌨', color: '#00ff66' },
  Alteration:        { code: 'ALT', icon: '✎', color: '#3df58a' },
  Traced:            { code: 'TRC', icon: '◤', color: '#a3e635' },
  Obliteration:      { code: 'OBL', icon: '▮', color: '#00ffaa' },
  'Sympathetic Ink': { code: 'SYM', icon: '☢', color: '#e2f8a3' },
  Currency:          { code: 'CUR', icon: '₱', color: '#f0ffbe' },
};

export default function About() {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState('');
  const [showDashboard, setShowDashboard] = useState(false);

  useEffect(() => {
    api.getAbout()
      .then(setInfo)
      .catch(err => setError(err.message || 'Failed to load info.'));
  }, []);

  if (error) return <div style={{ padding: 32, color: '#f87171' }}>{error}</div>;
  if (!info) return <div style={{ padding: 32, color: '#86efac' }}>Loading…</div>;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <p className="classification-bar" style={{ marginBottom: 12 }}>
          FORENSIC · DOCUMENT · ANALYSIS
        </p>
        <h1 className="oswald glow" style={{
          fontSize: 30, letterSpacing: 3, textTransform: 'uppercase', marginBottom: 8,
          color: '#00ff66',
        }}>
          About Revelator
        </h1>
        <p style={{ color: '#86efac', maxWidth: 700, lineHeight: 1.7, fontSize: 14 }}>
          Learn about the forensic models powering Revelator and the tiers available to you.
        </p>
      </div>

      {info.model_tiers && info.model_tiers.length > 0 && (
        <Section title="The Three Forensic Tiers">
          <p style={{ color: '#86efac', fontSize: 13, marginBottom: 18, lineHeight: 1.7 }}>
            Revelator offers three progressively more capable analysis tiers. The{' '}
            <strong style={{ color: '#00ff66' }}>Analyst</strong> tier is live now — powered by
            Gemini Vision and available on all plans. The{' '}
            <strong style={{ color: '#ffaa00' }}>Detective</strong> and{' '}
            <strong style={{ color: '#ffaa00' }}>Sherlock</strong> tiers are{' '}
            <span style={{ color: '#ffaa00', fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1 }}>
              coming soon
            </span>{' '}
            — they will add fine-tuned, domain-specialized forensic models on top of the Gemini baseline.
          </p>
          <div style={{ display: 'grid', gap: 16 }}>
            {info.model_tiers.map(tier => <TierCard key={tier.key} tier={tier} />)}
          </div>
        </Section>
      )}

      <div className="card" style={{ marginBottom: 20 }}>
        <div
          onClick={() => setShowDashboard(s => !s)}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            cursor: 'pointer', userSelect: 'none',
          }}
        >
          <div>
            <h2 className="oswald" style={{
              fontSize: 13, letterSpacing: 2.5, textTransform: 'uppercase',
              color: '#6dba85', margin: 0,
            }}>
              ▸ How the Analyst Reasons — Live Prompt Analytics
            </h2>
            <p style={{ fontSize: 12, color: '#86efac', margin: '6px 0 0 0', lineHeight: 1.6 }}>
              Behind every classification is a prompt that defines 19 forgery categories, branching rules, and
              user-context variables. This dashboard reads the live prompt and shows how each category is
              described, where overlaps exist, and which categories tend to dominate when evidence is ambiguous.
            </p>
          </div>
          <span className="mono" style={{
            fontSize: 11, color: '#00ff66', padding: '4px 12px',
            border: '1px solid #00ff66', borderRadius: 2, letterSpacing: 1.5,
            whiteSpace: 'nowrap', marginLeft: 16,
          }}>
            {showDashboard ? '▲ HIDE' : '▼ OPEN DASHBOARD'}
          </span>
        </div>

        {showDashboard && (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid #112418' }}>
            <PromptDashboard />
          </div>
        )}
      </div>

      <div style={{
        background: 'rgba(255,51,68,0.06)', border: '1px solid rgba(255,51,68,0.4)',
        padding: 16, borderRadius: 3, marginTop: 24,
      }}>
        <h4 className="oswald" style={{ fontSize: 13, letterSpacing: 2.5, color: '#ff8a99', textTransform: 'uppercase', marginBottom: 8 }}>
          ▸ Disclaimer
        </h4>
        <p style={{ fontSize: 13, color: '#d8ffe6', lineHeight: 1.7, margin: 0 }}>
          Revelator is a screening and triage tool intended to support — not replace — qualified
          document examination. Findings here are not by themselves admissible as forensic evidence.
          For legal proceedings, consult a certified document examiner.
        </p>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <h2 className="oswald" style={{ fontSize: 13, letterSpacing: 2.5, textTransform: 'uppercase', color: '#6dba85', marginBottom: 14 }}>
        ▸ {title}
      </h2>
      {children}
    </div>
  );
}

function Stat({ label, value, color = '#d8ffe6' }) {
  return (
    <div style={{
      background: '#0a120c', border: '1px solid #112418', borderRadius: 3,
      padding: 14, textAlign: 'center',
    }}>
      <div className="mono" style={{ fontSize: 22, fontWeight: 600, color, textShadow: `0 0 8px ${color}40` }}>{value}</div>
      <div className="oswald" style={{ fontSize: 10, letterSpacing: 1.5, textTransform: 'uppercase', color: '#3f6e4a', marginTop: 4 }}>
        {label}
      </div>
    </div>
  );
}

function VerdictRow({ level, color, text }) {
  const badgeKey = level.replace(/ /g, '_');
  return (
    <div style={{ display: 'flex', gap: 16, padding: '12px 0', borderBottom: '1px solid #112418' }}>
      <span className={`badge badge-${badgeKey}`} style={{ flex: '0 0 auto', alignSelf: 'flex-start' }}>{level}</span>
      <span style={{ fontSize: 13, color: '#d8ffe6', lineHeight: 1.6 }}>{text}</span>
    </div>
  );
}

function TierCard({ tier }) {
  const tierColors = {
    1: { primary: '#86efac', glow: 'rgba(134,239,172,0.25)', bg: 'rgba(134,239,172,0.04)' },
    2: { primary: '#00ffaa', glow: 'rgba(0,255,170,0.3)',    bg: 'rgba(0,255,170,0.05)' },
    3: { primary: '#00ff66', glow: 'rgba(0,255,102,0.4)',    bg: 'rgba(0,255,102,0.07)' },
  };
  const c = tierColors[tier.rank] || tierColors[1];
  return (
    <div style={{
      background: c.bg,
      border: `1px solid ${c.primary}40`,
      borderLeft: `4px solid ${c.primary}`,
      borderRadius: 3,
      padding: 18,
      boxShadow: `inset 0 1px 0 ${c.primary}10`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12, marginBottom: 12 }}>
        <div>
          <p className="mono" style={{ fontSize: 10, letterSpacing: 2, color: c.primary, margin: 0 }}>
            TIER {tier.rank}
          </p>
          <h3 className="oswald" style={{
            fontSize: 22, color: c.primary, margin: '4px 0 0 0',
            textTransform: 'uppercase', letterSpacing: 3,
            textShadow: `0 0 10px ${c.glow}`,
          }}>
            {tier.name}
          </h3>
          <p style={{ fontSize: 13, color: '#86efac', marginTop: 6, marginBottom: 0, fontStyle: 'italic' }}>
            {tier.tagline}
          </p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
          {!tier.available && (
            <span className="mono" style={{
              fontSize: 9, color: '#ffaa00', letterSpacing: 1.5,
              padding: '3px 8px', border: '1px solid #ffaa00',
              borderRadius: 2, textTransform: 'uppercase',
            }}>
              Coming Soon
            </span>
          )}
          <span className="mono" style={{ fontSize: 10, color: c.primary, letterSpacing: 1, textAlign: 'right' }}>
            {(tier.plans || []).join(' · ').toUpperCase()}
          </span>
        </div>
      </div>

      <div style={{ marginBottom: 14 }}>
        <p style={{ fontSize: 13, color: '#d8ffe6', lineHeight: 1.7, margin: 0 }}>
          {tier.description}
        </p>
      </div>

      <div style={{ marginBottom: 14 }}>
        <h4 className="oswald" style={{ fontSize: 11, letterSpacing: 2, color: '#6dba85', textTransform: 'uppercase', margin: '0 0 6px 0' }}>
          ▸ Models in this tier
        </h4>
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {(tier.models || []).map((m, i) => (
            <li key={i} style={{ fontSize: 12, color: '#86efac', lineHeight: 1.7, fontFamily: "'JetBrains Mono', monospace" }}>{m}</li>
          ))}
        </ul>
      </div>

      <div style={{ marginBottom: 14 }}>
        <h4 className="oswald" style={{ fontSize: 11, letterSpacing: 2, color: '#6dba85', textTransform: 'uppercase', margin: '0 0 6px 0' }}>
          ▸ How it's trained
        </h4>
        <p style={{ fontSize: 12, color: '#d8ffe6', lineHeight: 1.7, margin: 0 }}>
          {tier.training}
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
        <div>
          <h4 className="oswald" style={{ fontSize: 11, letterSpacing: 2, color: '#00ff66', textTransform: 'uppercase', margin: '0 0 6px 0' }}>
            ▸ Strengths
          </h4>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {(tier.strengths || []).map((s, i) => (
              <li key={i} style={{ fontSize: 12, color: '#d8ffe6', lineHeight: 1.7 }}>{s}</li>
            ))}
          </ul>
        </div>
        <div>
          <h4 className="oswald" style={{ fontSize: 11, letterSpacing: 2, color: '#ffa040', textTransform: 'uppercase', margin: '0 0 6px 0' }}>
            ▸ Limitations
          </h4>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {(tier.limitations || []).map((l, i) => (
              <li key={i} style={{ fontSize: 12, color: '#d8ffe6', lineHeight: 1.7 }}>{l}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function ClassRow({ cls, threshold }) {
  const pct = Math.min((cls.dataset_count / threshold) * 100, 100);
  const barColor = cls.dataset_count >= threshold ? '#00ff66' : (cls.dataset_count > 0 ? '#ffa040' : '#ff3344');

  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 12,
      alignItems: 'center', padding: '6px 0',
    }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#d8ffe6' }}>
          {cls.title}
        </div>
        <div style={{ position: 'relative', height: 3, background: '#112418', borderRadius: 2, marginTop: 4 }}>
          <div style={{
            position: 'absolute', top: 0, left: 0, height: '100%',
            width: `${pct}%`, background: barColor, borderRadius: 2,
            boxShadow: `0 0 6px ${barColor}80`,
          }} />
        </div>
      </div>
      <span className="mono" style={{ fontSize: 12, color: '#86efac', textAlign: 'right' }}>
        {cls.dataset_count.toLocaleString()}
      </span>
      <span className="mono" style={{
        fontSize: 9, padding: '2px 6px', borderRadius: 2, letterSpacing: 1.5,
        textTransform: 'uppercase',
        background: cls.is_trained ? 'rgba(0,255,102,0.12)' : 'rgba(82,82,82,0.2)',
        color: cls.is_trained ? '#00ff66' : '#525252',
        border: `1px solid ${cls.is_trained ? 'rgba(0,255,102,0.4)' : '#262626'}`,
        whiteSpace: 'nowrap',
      }}>
        {cls.is_trained ? '● TRAINED' : '○ PENDING'}
      </span>
    </div>
  );
}
