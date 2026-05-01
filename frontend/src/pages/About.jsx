import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

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

  useEffect(() => {
    api.getAbout()
      .then(setInfo)
      .catch(err => setError(err.message || 'Failed to load info.'));
  }, []);

  if (error) return <div style={{ padding: 32, color: '#f87171' }}>{error}</div>;
  if (!info) return <div style={{ padding: 32, color: '#86efac' }}>Loading…</div>;

  const totals = info.totals;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <p className="classification-bar" style={{ marginBottom: 12 }}>
          HOW IT WORKS · LIMITATIONS · DATASET
        </p>
        <h1 className="oswald glow" style={{
          fontSize: 30, letterSpacing: 3, textTransform: 'uppercase', marginBottom: 8,
          color: '#00ff66',
        }}>
          About Revelator
        </h1>
        <p style={{ color: '#86efac', maxWidth: 700, lineHeight: 1.7, fontSize: 14 }}>
          A transparent look at what the system does, what it doesn't, and exactly how much
          training data each detector has seen.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 28 }}>
        <Stat label="Classes" value={totals.classes} color="#d8ffe6" />
        <Stat label="Trained" value={`${totals.trained_classes} / ${totals.classes}`} color="#00ff66" />
        <Stat label="Dataset Images" value={totals.total_dataset_images.toLocaleString()} color="#00ffaa" />
        <Stat label="Min Acceptable" value={totals.limited_data_threshold.toLocaleString()} color="#86efac" />
      </div>

      <Section title="How a scan works">
        <ol style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {info.pipeline.map(p => (
            <li key={p.step} style={{ display: 'flex', gap: 16, padding: '12px 0', borderBottom: '1px solid #1a1a1a' }}>
              <span className="oswald" style={{
                flex: '0 0 auto', width: 36, height: 36, borderRadius: 2,
                background: '#00ff66', color: '#001005', display: 'flex',
                alignItems: 'center', justifyContent: 'center', fontWeight: 800,
                boxShadow: '0 0 12px rgba(0,255,102,0.5)',
              }}>{p.step}</span>
              <div>
                <div className="oswald" style={{ fontSize: 14, letterSpacing: 1.5, textTransform: 'uppercase', marginBottom: 2 }}>
                  {p.name}
                </div>
                <div style={{ fontSize: 13, color: '#86efac', lineHeight: 1.6 }}>{p.detail}</div>
              </div>
            </li>
          ))}
        </ol>
      </Section>

      <Section title="What the verdicts mean">
        <VerdictRow level="forged"               color="#ff3344" text={info.verdict_meaning.forged} />
        <VerdictRow level="suspicious"           color="#ffa040" text={info.verdict_meaning.suspicious} />
        <VerdictRow level="no forgery detected"  color="#00ff66" text={info.verdict_meaning.no_forgery_detected} />
        <VerdictRow level="not a document"       color="#737373" text={info.verdict_meaning.not_a_document} />
      </Section>

      <Section title="Limitations">
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {info.limitations.map((l, i) => (
            <li key={i} style={{
              display: 'flex', gap: 12, padding: '10px 0',
              borderBottom: i < info.limitations.length - 1 ? '1px solid #112418' : 'none',
              fontSize: 14, color: '#d8ffe6', lineHeight: 1.6,
            }}>
              <span style={{ color: '#ffa040', fontFamily: "'JetBrains Mono', monospace", fontSize: 12, flex: '0 0 auto' }}>
                ⚠
              </span>
              <span>{l}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Training data — full disclosure">
        <p style={{ color: '#86efac', fontSize: 13, marginBottom: 16, lineHeight: 1.7 }}>
          Each forgery <em>class</em> has its own detector trained on its own dataset. Counts below
          are the number of labeled training images per class. Anything under
          {' '}<strong style={{ color: '#ffa040' }}>{totals.limited_data_threshold.toLocaleString()}</strong>{' '}
          is flagged as <em>limited data</em> — these classes will produce less reliable verdicts
          and are surfaced as a warning on every scan.
        </p>

        {Object.entries(info.categories).map(([catName, catInfo]) => {
          const meta = CATEGORY_META[catName] || { code: '?', icon: '·', color: '#86efac' };
          return (
            <div key={catName} style={{
              background: '#000', borderRadius: 3, padding: 16, marginBottom: 14,
              borderLeft: `3px solid ${meta.color}`,
              border: '1px solid #112418', borderLeftWidth: 3,
              boxShadow: `inset 0 1px 0 ${meta.color}15`,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span style={{ fontSize: 22, color: meta.color, textShadow: `0 0 10px ${meta.color}80`, lineHeight: 1 }}>{meta.icon}</span>
                  <div>
                    <p className="mono" style={{ fontSize: 9, letterSpacing: 2.5, color: meta.color, margin: 0 }}>{meta.code}</p>
                    <h3 className="oswald" style={{ fontSize: 16, fontWeight: 700, letterSpacing: 2, margin: 0, textTransform: 'uppercase', color: '#d8ffe6' }}>
                      {catName}
                    </h3>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 14, fontSize: 12, alignItems: 'center' }}>
                  <span className="mono" style={{ color: '#86efac' }}>
                    <span style={{ color: meta.color, textShadow: `0 0 6px ${meta.color}60` }}>{catInfo.total_images.toLocaleString()}</span> img
                  </span>
                  <span className="mono" style={{ color: '#86efac' }}>
                    <span style={{ color: '#00ff66' }}>{catInfo.trained_classes}/{catInfo.classes.length}</span> trained
                  </span>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {catInfo.classes.map(cls => (
                  <ClassRow key={cls.api_key} cls={cls} threshold={totals.limited_data_threshold} />
                ))}
              </div>
            </div>
          );
        })}
      </Section>

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
