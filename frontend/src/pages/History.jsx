import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function History() {
  const [scans, setScans] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [detail, setDetail] = useState(null);
  const limit = 20;

  useEffect(() => {
    loadScans();
  }, [page]);

  function loadScans() {
    api.getHistory(limit, page * limit).then(data => {
      setScans(data.scans);
      setTotal(data.total);
    }).catch(() => {});
  }

  function viewDetail(scanId) {
    api.getScanDetail(scanId).then(setDetail).catch(() => {});
  }

  const verdictColors = { forged: '#dc2626', suspicious: '#f97316', genuine: '#22c55e' };

  if (detail) {
    return (
      <div>
        <button onClick={() => setDetail(null)} style={{
          background: 'none', border: 'none', color: '#f5c518', cursor: 'pointer',
          fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1.5,
          fontSize: 13, marginBottom: 20,
        }}>
          &larr; Back to History
        </button>

        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', marginBottom: 16 }}>
            <h2 className="oswald" style={{ fontSize: 20, letterSpacing: 2, textTransform: 'uppercase' }}>
              Scan Detail
            </h2>
            <span className="mono" style={{ color: '#525252', fontSize: 13 }}>{detail.scan_id}</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, marginBottom: 20 }}>
            <div style={{ background: '#0a0a0a', padding: 14, borderRadius: 6, textAlign: 'center' }}>
              <div className="oswald" style={{ color: verdictColors[detail.verdict], fontSize: 18, textTransform: 'uppercase' }}>{detail.verdict}</div>
              <div style={{ fontSize: 11, color: '#525252', marginTop: 4 }}>Verdict</div>
            </div>
            <div style={{ background: '#0a0a0a', padding: 14, borderRadius: 6, textAlign: 'center' }}>
              <div className="mono" style={{ color: '#f5c518', fontSize: 18 }}>{(detail.confidence_score * 100).toFixed(1)}%</div>
              <div style={{ fontSize: 11, color: '#525252', marginTop: 4 }}>Confidence</div>
            </div>
            <div style={{ background: '#0a0a0a', padding: 14, borderRadius: 6, textAlign: 'center' }}>
              <div className="mono" style={{ fontSize: 14, color: '#a3a3a3' }}>{detail.filename}</div>
              <div style={{ fontSize: 11, color: '#525252', marginTop: 4 }}>File</div>
            </div>
          </div>

          {detail.llm_explanation && (
            <div style={{ marginBottom: 16 }}>
              <h4 className="oswald" style={{ fontSize: 13, color: '#a3a3a3', textTransform: 'uppercase', letterSpacing: 1.5, marginBottom: 8 }}>Analysis</h4>
              <p style={{ lineHeight: 1.7, fontSize: 14, color: '#d4d4d4' }}>{detail.llm_explanation}</p>
            </div>
          )}

          {detail.training_warning && (
            <div style={{ background: 'rgba(249,115,22,0.1)', border: '1px solid #f97316', padding: 12, borderRadius: 4, fontSize: 13, color: '#fb923c' }}>
              {detail.training_warning}
            </div>
          )}

          {detail.annotations?.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <h4 className="oswald" style={{ fontSize: 13, color: '#a3a3a3', textTransform: 'uppercase', letterSpacing: 1.5, marginBottom: 8 }}>Detections</h4>
              {detail.annotations.map((ann, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: '1px solid #1a1a1a' }}>
                  <span style={{
                    width: 22, height: 22, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: ann.color, color: '#fff', fontSize: 10, fontWeight: 700,
                  }}>{i + 1}</span>
                  <span style={{ flex: 1, fontSize: 14 }}>{ann.title}</span>
                  <span className="mono" style={{ fontSize: 12, color: '#a3a3a3' }}>{(ann.confidence * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  const totalPages = Math.ceil(total / limit);

  return (
    <div>
      <h1 className="oswald" style={{ fontSize: 26, letterSpacing: 2, textTransform: 'uppercase', marginBottom: 24 }}>
        Scan History
      </h1>

      <div className="card">
        {scans.length === 0 ? (
          <p style={{ color: '#525252', textAlign: 'center', padding: 32 }}>No scans yet.</p>
        ) : (
          <>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #262626' }}>
                    {['Scan ID', 'File', 'Category', 'Verdict', 'Confidence', 'Date', ''].map(h => (
                      <th key={h} style={{ padding: '10px 8px', textAlign: 'left', fontSize: 11, color: '#525252', textTransform: 'uppercase', letterSpacing: 1, fontFamily: "'Oswald', sans-serif" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {scans.map(scan => (
                    <tr key={scan.scan_id} style={{ borderBottom: '1px solid #1a1a1a' }}>
                      <td className="mono" style={{ padding: '12px 8px', fontSize: 12, color: '#a3a3a3' }}>{scan.scan_id}</td>
                      <td style={{ padding: '12px 8px', fontSize: 13 }}>{scan.filename}</td>
                      <td style={{ padding: '12px 8px', fontSize: 13, color: '#a3a3a3' }}>{scan.category_analyzed || 'Auto'}</td>
                      <td style={{ padding: '12px 8px' }}><span className={`badge badge-${scan.verdict}`}>{scan.verdict}</span></td>
                      <td className="mono" style={{ padding: '12px 8px', fontSize: 12 }}>{(scan.confidence_score * 100).toFixed(0)}%</td>
                      <td className="mono" style={{ padding: '12px 8px', fontSize: 12, color: '#525252' }}>{new Date(scan.created_at).toLocaleDateString()}</td>
                      <td style={{ padding: '12px 8px' }}>
                        <button onClick={() => viewDetail(scan.scan_id)} style={{
                          background: 'none', border: '1px solid #404040', color: '#a3a3a3',
                          padding: '4px 12px', cursor: 'pointer', fontSize: 11, borderRadius: 3,
                          fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1,
                        }}>View</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 20 }}>
                <button className="btn btn-secondary" onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
                  style={{ padding: '8px 16px', fontSize: 12 }}>&larr; Prev</button>
                <span className="mono" style={{ padding: '8px 16px', color: '#a3a3a3', fontSize: 13 }}>
                  {page + 1} / {totalPages}
                </span>
                <button className="btn btn-secondary" onClick={() => setPage(p => p + 1)} disabled={page >= totalPages - 1}
                  style={{ padding: '8px 16px', fontSize: 12 }}>Next &rarr;</button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
