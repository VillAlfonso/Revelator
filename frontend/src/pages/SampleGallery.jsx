import React, { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client';

// Categories duplicated from Scan.jsx for now — extract to a shared module later if needed.
const GROUPS = {
  traced:          { code: 'TRC', icon: '📋', color: '#3b82f6', title: 'Traced Forgery',  backend: 'Traced' },
  alteration:      { code: 'ALT', icon: '✏️', color: '#dc2626', title: 'Alteration',       backend: 'Alteration' },
  digital:         { code: 'DIG', icon: '💻', color: '#8b5cf6', title: 'Digital Forgery',  backend: 'Digital' },
  obliteration:    { code: 'OBL', icon: '◼',  color: '#f97316', title: 'Obliteration',     backend: 'Obliteration' },
  sympathetic_ink: { code: 'SYM', icon: '🔬', color: '#22c55e', title: 'Sympathetic Ink',  backend: 'Sympathetic Ink' },
  currency:        { code: 'CUR', icon: '💵', color: '#eab308', title: 'Currency Forgery', backend: 'Currency' },
};

const GUIDANCE = {
  traced: {
    shooting: [
      'Lay the document flat — no curls or folds in frame',
      'Even, diffuse light (window light works, avoid harsh shadows)',
      'Phone parallel to the page, full document visible',
    ],
    detector: 'Looks for repeated stroke patterns, ink overlay artifacts, and signatures that follow guide-lines too cleanly.',
  },
  alteration: {
    shooting: [
      'Get close enough that text is sharp at full resolution',
      'Capture the entire altered region plus surrounding context',
      'No flash — it can wash out erasure marks the model relies on',
    ],
    detector: 'Looks for ink-color drift, eraser ghosts, paper-texture breaks, and fields that don\'t align with the form grid.',
  },
  digital: {
    shooting: [
      'For printed digital forgeries, scan or photograph at ≥300 DPI equivalent',
      'For PDFs: export each page as a PNG and upload',
      'Avoid moiré — slightly tilt the page if photographing a print',
    ],
    detector: 'Looks for resampling artifacts, font inconsistency, JPEG compression seams, and copy-paste edges.',
  },
  obliteration: {
    shooting: [
      'Side-lighting often reveals indents under blacked-out areas — try multiple angles',
      'Capture the obliterated region centered, not at the edge of frame',
      'Don\'t correct exposure — the underlying tone matters',
    ],
    detector: 'Looks for ink-density anomalies, residual character outlines, and pressure marks beneath cover-ups.',
  },
  sympathetic_ink: {
    shooting: [
      'A UV/blacklight image will give the strongest signal — capture under that lamp',
      'Otherwise, capture in normal light first; the model will flag suspect zones',
      'Submit both visible and UV captures as separate scans for cross-check',
    ],
    detector: 'Looks for fluorescence patterns, hidden writing residue, and suspicious blank zones on official paper.',
  },
  currency: {
    shooting: [
      'Both sides — submit two scans (front + back)',
      'Bring the security strip into frame; don\'t crop the edges',
      'Tilt slightly so optically-variable inks read correctly',
    ],
    detector: 'Looks for missing watermarks, off-color security threads, microprinting blur, and cut-out registration errors.',
  },
};

export default function SampleGallery() {
  const { categoryId } = useParams();
  const navigate = useNavigate();
  const cat = GROUPS[categoryId];
  const [stats, setStats] = useState(null);

  useEffect(() => {
    if (!cat) return;
    api.getCategories().then(data => {
      const total = (data.category_dataset_totals || {})[cat.backend] || 0;
      const classes = (data.categories || {})[cat.backend] || [];
      const trained = classes.filter(c => c.is_trained).length;
      setStats({ total, classes: classes.length, trained, threshold: data.limited_data_threshold || 200 });
    }).catch(() => {});
  }, [categoryId]);

  if (!cat) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <p style={{ color: '#a3a3a3' }}>Unknown category.</p>
        <Link to="/scan" style={{ color: '#f5c518' }}>← Back to scan</Link>
      </div>
    );
  }

  const guidance = GUIDANCE[categoryId] || { shooting: [], detector: '' };
  const samples = [1, 2, 3, 4, 5];

  return (
    <div>
      <button
        onClick={() => navigate(-1)}
        style={{
          background: 'none', border: 'none', color: '#a3a3a3', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16, padding: 0, fontSize: 14,
        }}
      >
        ← Back
      </button>

      <div style={{
        background: '#151515',
        borderLeft: `4px solid ${cat.color}`,
        padding: 20, marginBottom: 24, borderRadius: 4,
        display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
      }}>
        <span style={{ fontSize: 36 }}>{cat.icon}</span>
        <div style={{ flex: 1, minWidth: 200 }}>
          <p className="mono" style={{ fontSize: 10, letterSpacing: 2, color: cat.color, margin: 0 }}>
            {cat.code} · SAMPLE GALLERY
          </p>
          <h1 className="oswald" style={{ fontSize: 24, fontWeight: 700, letterSpacing: 1, margin: '4px 0 0', textTransform: 'uppercase' }}>
            {cat.title}
          </h1>
        </div>
        <Link
          to={`/scan?category=${categoryId}`}
          className="btn btn-primary"
          style={{ fontSize: 12, padding: '10px 16px' }}
        >
          Start Scan →
        </Link>
      </div>

      {stats && (
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10, marginBottom: 24,
        }}>
          <DatasetStat
            label="Training Images"
            value={stats.total.toLocaleString()}
            color={stats.total >= stats.threshold ? '#22c55e' : (stats.total > 0 ? '#f97316' : '#dc2626')}
          />
          <DatasetStat
            label="Trained Classes"
            value={`${stats.trained} / ${stats.classes}`}
            color={stats.trained === stats.classes ? '#22c55e' : '#f97316'}
          />
          <DatasetStat
            label="Min for Reliability"
            value={stats.threshold.toLocaleString()}
            color="#a3a3a3"
          />
          <Link to="/about" style={{
            background: '#0a0a0a', border: '1px solid #262626', borderRadius: 6,
            padding: '14px 12px', textAlign: 'center', textDecoration: 'none',
            display: 'flex', flexDirection: 'column', justifyContent: 'center',
          }}>
            <div className="oswald" style={{ fontSize: 13, color: '#f5c518', letterSpacing: 1.5, textTransform: 'uppercase' }}>
              Full breakdown →
            </div>
            <div style={{ fontSize: 10, color: '#525252', marginTop: 4 }}>About page</div>
          </Link>
        </div>
      )}

      {stats && stats.total < stats.threshold && (
        <div style={{
          background: 'rgba(249,115,22,0.08)', border: '1px solid rgba(249,115,22,0.4)',
          padding: 12, borderRadius: 6, marginBottom: 24, fontSize: 13, color: '#fb923c',
          display: 'flex', gap: 10, alignItems: 'flex-start',
        }}>
          <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>⚠</span>
          <span>
            <strong>Limited data:</strong> this category has fewer than {stats.threshold.toLocaleString()} training images
            ({stats.total.toLocaleString()} so far). Verdicts in this category may be less reliable.
            More samples are being collected.
          </span>
        </div>
      )}

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 className="oswald" style={{ fontSize: 14, textTransform: 'uppercase', letterSpacing: 2, color: '#a3a3a3', marginBottom: 12 }}>
          📷 Take the picture like this
        </h2>
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {guidance.shooting.map((tip, i) => (
            <li key={i} style={{
              padding: '8px 0', borderBottom: i < guidance.shooting.length - 1 ? '1px solid #1a1a1a' : 'none',
              fontSize: 14, color: '#d4d4d4', display: 'flex', gap: 10,
            }}>
              <span style={{ color: cat.color, fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
                {String(i + 1).padStart(2, '0')}
              </span>
              <span>{tip}</span>
            </li>
          ))}
        </ul>

        {guidance.detector && (
          <div style={{ marginTop: 16, padding: 12, background: '#0a0a0a', borderRadius: 4, borderLeft: `2px solid ${cat.color}` }}>
            <p className="oswald" style={{ fontSize: 11, color: '#a3a3a3', textTransform: 'uppercase', letterSpacing: 1.5, margin: 0, marginBottom: 4 }}>
              What the detector looks for
            </p>
            <p style={{ fontSize: 13, color: '#d4d4d4', margin: 0, lineHeight: 1.6 }}>
              {guidance.detector}
            </p>
          </div>
        )}
      </div>

      <h2 className="oswald" style={{ fontSize: 14, textTransform: 'uppercase', letterSpacing: 2, color: '#a3a3a3', marginBottom: 12 }}>
        Annotated examples
      </h2>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {samples.map(n => (
          <SamplePair key={n} categoryId={categoryId} index={n} catColor={cat.color} />
        ))}
      </div>
    </div>
  );
}

function DatasetStat({ label, value, color }) {
  return (
    <div style={{ background: '#0a0a0a', border: '1px solid #262626', borderRadius: 6, padding: 14, textAlign: 'center' }}>
      <div className="mono" style={{ fontSize: 18, fontWeight: 600, color }}>{value}</div>
      <div className="oswald" style={{ fontSize: 10, letterSpacing: 1.5, textTransform: 'uppercase', color: '#525252', marginTop: 4 }}>
        {label}
      </div>
    </div>
  );
}

function SamplePair({ categoryId, index, catColor }) {
  return (
    <div className="card" style={{ padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span className="oswald" style={{ fontSize: 12, letterSpacing: 1.5, color: '#a3a3a3', textTransform: 'uppercase' }}>
          Sample {String(index).padStart(2, '0')}
        </span>
        <span className="mono" style={{ fontSize: 10, color: '#525252', letterSpacing: 1 }}>
          ANNOTATED · ORIGINAL
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <SampleImage
          src={`/samples/${categoryId}/${index}-annotated.jpg`}
          label="ANNOTATED"
          catColor={catColor}
          variant="annotated"
        />
        <SampleImage
          src={`/samples/${categoryId}/${index}-original.jpg`}
          label="ORIGINAL"
          catColor={catColor}
          variant="original"
        />
      </div>
    </div>
  );
}

function SampleImage({ src, label, catColor, variant }) {
  const [errored, setErrored] = useState(false);

  return (
    <div style={{
      aspectRatio: '4/3',
      background: '#0a0a0a',
      border: '1px solid #262626',
      borderRadius: 4,
      position: 'relative',
      overflow: 'hidden',
    }}>
      {!errored && (
        <img
          src={src}
          alt={label}
          onError={() => setErrored(true)}
          style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
        />
      )}
      {errored && (
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          background:
            variant === 'annotated'
              ? `repeating-linear-gradient(45deg, #0a0a0a 0 12px, #111 12px 24px)`
              : '#0a0a0a',
          color: '#404040',
          gap: 6,
        }}>
          <span className="mono" style={{ fontSize: 10, color: catColor, letterSpacing: 2 }}>
            {label}
          </span>
          <span style={{ fontSize: 11, color: '#525252' }}>image not yet provided</span>
        </div>
      )}
      <span className="mono" style={{
        position: 'absolute', top: 6, left: 6,
        fontSize: 9, padding: '2px 6px', borderRadius: 2,
        background: 'rgba(0,0,0,0.7)', color: variant === 'annotated' ? catColor : '#a3a3a3',
        letterSpacing: 1.5,
      }}>
        {label}
      </span>
    </div>
  );
}
