import React, { useEffect, useState } from 'react';

import { useAuth } from '../auth/AuthContext';
import { getHistory } from '../lib/firestore';

export default function History() {
  const { user } = useAuth();
  const [scans, setScans] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!user) return;
    getHistory(user.uid).then(setScans).catch(e => setError(e.message));
  }, [user]);

  if (error) return <Banner kind="error">⚠ {error}</Banner>;
  if (scans === null) return <Banner>Loading…</Banner>;
  if (scans.length === 0) return <Banner>No scans yet. Run your first analysis on the Scan page.</Banner>;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <p className="classification-bar" style={{ marginBottom: 6 }}>FORENSIC · ARCHIVE</p>
        <h2 className="oswald glow" style={{ fontSize: 26, color: '#00ff66', letterSpacing: 4, textTransform: 'uppercase', margin: 0 }}>
          Scan History
        </h2>
        <p style={{ color: '#6dba85', fontSize: 13, marginTop: 6 }}>{scans.length} past scans</p>
      </div>

      <div style={{ display: 'grid', gap: 12, maxWidth: 800 }}>
        {scans.map(s => <Row key={s.id} scan={s} />)}
      </div>
    </div>
  );
}

function Row({ scan }) {
  const verdictColor = {
    forged: '#ff3344',
    suspicious: '#ffa040',
    no_forgery_detected: '#00ff66',
    not_a_document: '#737373',
  }[scan.verdict] || '#737373';

  const ts = scan.created_at?.toDate?.() ?? scan.created_at;
  const date = ts ? new Date(ts).toLocaleString() : '';

  return (
    <div className="card" style={{ padding: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="oswald" style={{
          fontSize: 13, color: verdictColor, letterSpacing: 2, textTransform: 'uppercase',
          textShadow: `0 0 8px ${verdictColor}80`,
        }}>
          {(scan.detected_category_label || scan.verdict || '—').replace(/_/g, ' ')}
        </div>
        <div className="mono" style={{ fontSize: 11, color: '#6dba85', marginTop: 4 }}>
          {scan.scan_id} · {date}
        </div>
        {scan.filename && (
          <div style={{ fontSize: 12, color: '#3f6e4a', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {scan.filename}
          </div>
        )}
      </div>
      <div style={{ textAlign: 'right' }}>
        <span className="mono" style={{ fontSize: 12, color: verdictColor, letterSpacing: 1.5 }}>
          {scan.category_confidence ? `${(scan.category_confidence * 100).toFixed(0)}%` : '—'}
        </span>
      </div>
    </div>
  );
}

function Banner({ kind = 'info', children }) {
  const colors = kind === 'error'
    ? { bg: 'rgba(255,51,68,0.1)', border: '#ff3344', fg: '#ff8a99' }
    : { bg: 'rgba(0,255,102,0.04)', border: '#1d3825', fg: '#86efac' };
  return (
    <div style={{
      background: colors.bg, border: `1px solid ${colors.border}`, padding: 14,
      borderRadius: 2, fontSize: 13, color: colors.fg,
      fontFamily: "'JetBrains Mono', monospace", maxWidth: 800,
    }}>
      {children}
    </div>
  );
}
