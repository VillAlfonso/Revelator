import React, { useEffect, useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { CATEGORY_BY_KEY } from '../categories';

// Maps a Gemini category code to its display color
function geminiColor(code) {
  if (!code) return '#3f6e4a';
  if (code === 'no_forgery_detected') return '#00ff66';
  if (code === 'not_a_document') return '#737373';
  if (code === 'other') return '#ffa040';
  return CATEGORY_BY_KEY[code]?.color || '#a78bfa';
}

// Maps a Gemini category code to a short display label
function geminiLabel(code, label) {
  if (label) return label;
  if (!code) return 'Unknown';
  if (code === 'no_forgery_detected') return 'No Forgery';
  if (code === 'not_a_document') return 'Not a Document';
  if (code === 'other') return 'Other Forgery';
  return CATEGORY_BY_KEY[code]?.title || code;
}

export default function History() {
  const [scans, setScans] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [detail, setDetail] = useState(null);
  const limit = 20;

  useEffect(() => { loadScans(); }, [page]);

  function loadScans() {
    api.getHistory(limit, page * limit).then(data => {
      setScans(data.scans);
      setTotal(data.total);
    }).catch(() => {});
  }

  function viewDetail(scanId) {
    api.getScanDetail(scanId).then(setDetail).catch(() => {});
  }

  if (detail) return <ScanDetailView detail={detail} onBack={() => setDetail(null)} />;

  const totalPages = Math.ceil(total / limit);

  return (
    <div>
      <p className="classification-bar" style={{ marginBottom: 12 }}>OPERATOR · SCAN · LOG</p>
      <h1 className="oswald glow" style={{ fontSize: 28, letterSpacing: 3, textTransform: 'uppercase', marginBottom: 24, color: '#00ff66' }}>
        Scan History
      </h1>

      {scans.length === 0 ? (
        <div className="card">
          <p className="mono" style={{ color: '#3f6e4a', textAlign: 'center', padding: 32, letterSpacing: 2 }}>▣ NO SCANS RECORDED</p>
        </div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
            {scans.map(scan => (
              <HistoryCard key={scan.scan_id} scan={scan} onClick={() => viewDetail(scan.scan_id)} />
            ))}
          </div>
          {totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 24 }}>
              <button className="btn btn-secondary" onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0} style={{ padding: '8px 16px', fontSize: 12 }}>&larr; Prev</button>
              <span className="mono" style={{ padding: '8px 16px', color: '#86efac', fontSize: 13 }}>{page + 1} / {totalPages}</span>
              <button className="btn btn-secondary" onClick={() => setPage(p => p + 1)} disabled={page >= totalPages - 1} style={{ padding: '8px 16px', fontSize: 12 }}>Next &rarr;</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function HistoryCard({ scan, onClick }) {
  const cat = scan.detected_category;
  const color = geminiColor(cat);
  const label = geminiLabel(cat, null);
  const conf = typeof scan.category_confidence === 'number' ? scan.category_confidence : scan.confidence_score;

  return (
    <button onClick={onClick} style={{
      background: '#0a120c', border: `1px solid #1a2e1e`, borderLeft: `4px solid ${color}`,
      borderRadius: 6, padding: 0, cursor: 'pointer', textAlign: 'left',
      overflow: 'hidden', color: 'inherit', font: 'inherit', width: '100%',
    }}>
      <div style={{ aspectRatio: '4/3', background: '#000', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
        {scan.has_image ? (
          <img src={api.getScanImageUrl(scan.scan_id)} alt={scan.filename}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            onError={e => { e.currentTarget.style.display = 'none'; }} />
        ) : (
          <span style={{ color: '#404040', fontSize: 12, fontFamily: "'Oswald', sans-serif", letterSpacing: 1 }}>NO IMAGE</span>
        )}
      </div>
      <div style={{ padding: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
          <span className="oswald" style={{
            fontSize: 11, color, textTransform: 'uppercase', letterSpacing: 1.5,
            background: `${color}18`, border: `1px solid ${color}44`, borderRadius: 3, padding: '2px 7px',
            textShadow: `0 0 6px ${color}66`, maxWidth: '70%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {cat ? label : '—'}
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {scan.has_llm_explanation && (
              <span className="oswald" style={{ fontSize: 9, letterSpacing: 1, textTransform: 'uppercase', color: '#c4b5fd', background: 'rgba(139,92,246,0.12)', border: '1px solid rgba(139,92,246,0.4)', borderRadius: 3, padding: '1px 5px' }}>AI</span>
            )}
            <span className="mono" style={{ fontSize: 11, color }}>
              {(conf * 100).toFixed(0)}%
            </span>
          </div>
        </div>
        <div style={{ fontSize: 13, color: '#d4d4d4', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{scan.filename}</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6 }}>
          <span className="mono" style={{ fontSize: 10, color: '#3f6e4a' }}>{scan.scan_id}</span>
          <span className="mono" style={{ fontSize: 10, color: '#3f6e4a' }}>{new Date(scan.created_at).toLocaleDateString()}</span>
        </div>
      </div>
    </button>
  );
}

function ScanDetailView({ detail, onBack }) {
  const canvasRef = useRef(null);
  const cat = detail.detected_category;
  const color = geminiColor(cat);
  const label = geminiLabel(cat, detail.detected_category_label);
  const geminiOk = typeof detail.category_confidence === 'number' && detail.category_confidence > 0;
  const geminiForgery = geminiOk && cat !== 'no_forgery_detected' && cat !== 'not_a_document';
  const hasYolo = detail.annotations?.length > 0 && geminiForgery;
  const certColor = detail.certainty_level === 'HIGH' ? '#00ff66' : detail.certainty_level === 'MEDIUM' ? '#ffa040' : '#ff5555';

  useEffect(() => {
    if (!detail.has_image || !hasYolo) return;
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const maxW = Math.min(canvas.parentElement.offsetWidth - 32, 900);
      const scale = maxW / img.naturalWidth;
      canvas.width = img.naturalWidth * scale;
      canvas.height = img.naturalHeight * scale;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      detail.annotations.forEach((ann, idx) => {
        const c = ann.coordinates;
        const x = c.x_min * scale, y = c.y_min * scale;
        const w = (c.x_max - c.x_min) * scale, h = (c.y_max - c.y_min) * scale;
        ctx.shadowColor = ann.color || color;
        ctx.shadowBlur = 8;
        ctx.strokeStyle = ann.color || color;
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, w, h);
        ctx.shadowBlur = 0;
        ctx.fillStyle = ann.color || color;
        ctx.font = 'bold 12px JetBrains Mono';
        const lbl = `${idx + 1}. ${ann.title} (${(ann.confidence * 100).toFixed(0)}%)`;
        const tw = ctx.measureText(lbl).width + 8;
        ctx.fillRect(x, Math.max(0, y - 18), tw, 18);
        ctx.fillStyle = '#000';
        ctx.fillText(lbl, x + 4, Math.max(12, y - 5));
      });
    };
    img.src = api.getScanImageUrl(detail.scan_id);
  }, [detail]);

  return (
    <div>
      <button onClick={onBack} style={{ background: 'none', border: 'none', color: '#00ff66', cursor: 'pointer', fontFamily: "'JetBrains Mono', monospace", letterSpacing: 1.5, fontSize: 13, marginBottom: 20, padding: 0, textShadow: '0 0 6px rgba(0,255,102,0.5)' }}>
        ← back to history
      </button>

      <div className="card" style={{ borderColor: color, boxShadow: `0 0 20px ${color}20`, padding: 0, overflow: 'hidden' }}>
        {/* header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 20px', borderBottom: `1px solid ${color}33` }}>
          <h2 className="oswald" style={{ fontSize: 14, letterSpacing: 2.5, textTransform: 'uppercase', margin: 0, color: '#d8ffe6' }}>◆ Forensic Report</h2>
          <span className="mono" style={{ color: '#3f6e4a', fontSize: 11 }}>{detail.scan_id}</span>
        </div>

        {/* category banner */}
        <div style={{ textAlign: 'center', padding: '28px 20px 24px', background: '#000', borderBottom: `1px solid ${color}33`, boxShadow: `inset 0 0 32px ${color}18` }}>
          <div className="oswald" style={{ fontSize: 30, fontWeight: 700, color, textTransform: 'uppercase', letterSpacing: 5, textShadow: `0 0 18px ${color}99` }}>
            {cat ? label : '—'}
          </div>
          {geminiOk && (
            <div className="mono" style={{ color: '#6dba85', marginTop: 10, fontSize: 12, letterSpacing: 1.5 }}>
              GEMINI {(detail.category_confidence * 100).toFixed(1)}% ·{' '}
              <span style={{ color: certColor }}>{detail.certainty_level}</span> CERTAINTY
            </div>
          )}
        </div>

        <div style={{ padding: '20px 20px 4px' }}>
          {/* image */}
          {detail.has_image && (
            <div style={{ marginBottom: 20 }}>
              <p className="mono" style={{ fontSize: 9, letterSpacing: 3, color: '#6dba85', margin: '0 0 8px' }}>
                {hasYolo ? '▸ YOLO · ANNOTATED IMAGE' : '▸ UPLOADED IMAGE'}
              </p>
              {hasYolo ? (
                <canvas ref={canvasRef} style={{ maxWidth: '100%', borderRadius: 3, border: '1px solid #1d3825' }} />
              ) : (
                <img src={api.getScanImageUrl(detail.scan_id)} alt={detail.filename}
                  style={{ maxWidth: '100%', borderRadius: 3, border: '1px solid #1d3825' }} />
              )}
            </div>
          )}

          {/* gemini panel */}
          {geminiOk ? (
            <div style={{ marginBottom: 20 }}>
              <p className="mono" style={{ fontSize: 9, letterSpacing: 3, color, margin: '0 0 8px', textShadow: `0 0 6px ${color}80` }}>▣ GEMINI VISION · CLASSIFICATION</p>
              <div style={{ background: `${color}08`, border: `1px solid ${color}44`, borderLeft: `3px solid ${color}`, borderRadius: 3, padding: '12px 14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                  <div>
                    <h4 className="oswald" style={{ fontSize: 17, color: '#d8ffe6', textTransform: 'uppercase', letterSpacing: 2, margin: 0 }}>{label}</h4>
                    {detail.detected_subtype && <p style={{ fontSize: 12, color, margin: '3px 0 0', fontStyle: 'italic' }}>Subtype: {detail.detected_subtype}</p>}
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span className="mono" style={{ fontSize: 11, color, letterSpacing: 1.5, display: 'block' }}>
                      {(detail.category_confidence * 100).toFixed(0)}% CONF
                    </span>
                    {detail.certainty_level && (
                      <span className="mono" style={{ fontSize: 10, color: certColor, letterSpacing: 1 }}>{detail.certainty_level} CERTAINTY</span>
                    )}
                  </div>
                </div>
                {detail.category_explanation && (
                  <p style={{ lineHeight: 1.7, fontSize: 14, color: '#d8ffe6', margin: '0 0 10px' }}>{detail.category_explanation}</p>
                )}
                {detail.category_evidence?.length > 0 && (
                  <div style={{ marginBottom: 10 }}>
                    <p className="mono" style={{ fontSize: 9, color: '#86efac', letterSpacing: 2, margin: '0 0 6px' }}>EVIDENCE</p>
                    <ul style={{ margin: 0, paddingLeft: 18, color: '#86efac', fontSize: 13, lineHeight: 1.6 }}>
                      {detail.category_evidence.map((e, i) => <li key={i}>{e}</li>)}
                    </ul>
                  </div>
                )}
                {detail.tools_likely_used && (
                  <p style={{ fontSize: 12, color: '#86efac', margin: 0, borderTop: '1px solid #112418', paddingTop: 8 }}>
                    <span className="mono" style={{ color, letterSpacing: 1.5, marginRight: 6 }}>TOOLS USED:</span>
                    {detail.tools_likely_used}
                  </p>
                )}
              </div>
            </div>
          ) : cat ? (
            <div style={{ marginBottom: 20 }}>
              <span className="mono" style={{ fontSize: 9, letterSpacing: 2, color: '#3f6e4a', padding: '4px 10px', border: '1px solid #1d3825', borderRadius: 2 }}>
                ▣ GEMINI VISION · TEMPORARILY UNAVAILABLE
              </span>
            </div>
          ) : null}

          {/* llm */}
          {detail.llm_explanation ? (
            <div style={{ marginBottom: 20 }}>
              <p className="mono" style={{ fontSize: 9, letterSpacing: 3, color: '#6dba85', margin: '0 0 8px' }}>▸ AI FORENSIC EXPLANATION</p>
              <p style={{ lineHeight: 1.7, fontSize: 14, color: '#d8ffe6', margin: 0 }}>{detail.llm_explanation}</p>
            </div>
          ) : detail.llm_locked ? (
            <div style={{ marginBottom: 20 }}>
              <div style={{ background: 'linear-gradient(135deg, rgba(139,92,246,0.1) 0%, rgba(139,92,246,0.02) 100%)', border: '1px solid rgba(139,92,246,0.4)', borderRadius: 3, padding: 14, display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <span style={{ fontSize: 22, lineHeight: 1 }}>✨</span>
                <div style={{ flex: 1 }}>
                  <div className="oswald" style={{ fontSize: 13, color: '#c4b5fd', textTransform: 'uppercase', letterSpacing: 1.5, marginBottom: 4 }}>AI Forensic Explanation</div>
                  <p style={{ fontSize: 13, color: '#86efac', lineHeight: 1.6, margin: '0 0 10px' }}>
                    Upgrade to <strong style={{ color: '#a78bfa', textTransform: 'capitalize' }}>{detail.llm_required_plan || 'pro'}</strong> for a plain-language breakdown on every scan.
                  </p>
                  <Link to="/account" style={{ display: 'inline-block', padding: '6px 14px', borderRadius: 2, background: '#8b5cf6', color: '#fff', textDecoration: 'none', fontSize: 12, fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1.5 }}>See plans →</Link>
                </div>
              </div>
            </div>
          ) : null}

          {/* yolo detections */}
          {hasYolo && (
            <div style={{ marginBottom: 16 }}>
              <p className="mono" style={{ fontSize: 9, letterSpacing: 3, color: '#6dba85', margin: '0 0 8px' }}>▸ YOLO · DETECTIONS</p>
              {detail.annotations.map((ann, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: '1px solid #112418' }}>
                  <span style={{ width: 24, height: 24, borderRadius: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', background: ann.color, color: '#000', fontSize: 10, fontWeight: 800, fontFamily: "'JetBrains Mono', monospace" }}>
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span style={{ flex: 1, fontSize: 14, color: '#d8ffe6' }}>{ann.title}</span>
                  <span className="mono" style={{ fontSize: 12, color: ann.color }}>{(ann.confidence * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}

          {detail.training_warning && (
            <div style={{ background: 'rgba(255,160,64,0.08)', border: '1px solid #ffa040', padding: '10px 14px', borderRadius: 2, fontSize: 12, color: '#ffc888', fontFamily: "'JetBrains Mono', monospace", marginBottom: 16 }}>
              ⚠ {detail.training_warning}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
