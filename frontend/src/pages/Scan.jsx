import React, { useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Camera, CameraResultType, CameraSource } from '@capacitor/camera';
import { api } from '../api/client';
import { MagnifierIcon } from '../components/ForensicMotifs';
import { CATEGORY_BY_KEY } from '../categories';

export default function Scan() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [documentType, setDocumentType] = useState('other');
  const [documentTypes, setDocumentTypes] = useState([]);
  const fileRef = useRef();
  const canvasRef = useRef();

  // Load document types on mount
  React.useEffect(() => {
    api.getDocumentTypes()
      .then(data => setDocumentTypes(data.document_types))
      .catch(err => console.error('Failed to load document types:', err));
  }, []);

  function resetScan() {
    setFile(null);
    setPreview(null);
    setResult(null);
    setError('');
  }

  function handleFileChange(e) {
    const f = e.target.files[0];
    if (!f) return;
    setFile(f);
    setResult(null);
    setError('');
    const reader = new FileReader();
    reader.onload = ev => setPreview(ev.target.result);
    reader.readAsDataURL(f);
  }

  async function handleTakePhoto() {
    setError('');
    setResult(null);
    try {
      const photo = await Camera.getPhoto({
        quality: 90, allowEditing: false,
        resultType: CameraResultType.Uri, source: CameraSource.Camera,
      });
      const res = await fetch(photo.webPath);
      const blob = await res.blob();
      const f = new File([blob], `scan-${Date.now()}.${photo.format || 'jpg'}`, { type: blob.type });
      setFile(f);
      setPreview(photo.webPath);
    } catch (err) {
      if (err?.message && !/cancel/i.test(err.message)) setError(err.message);
    }
  }

  async function handlePickFromGallery() {
    setError('');
    setResult(null);
    try {
      const photo = await Camera.getPhoto({
        quality: 90, allowEditing: false,
        resultType: CameraResultType.Uri, source: CameraSource.Photos,
      });
      const res = await fetch(photo.webPath);
      const blob = await res.blob();
      const f = new File([blob], `photo-${Date.now()}.${photo.format || 'jpg'}`, { type: blob.type });
      setFile(f);
      setPreview(photo.webPath);
    } catch (err) {
      if (err?.message && !/cancel/i.test(err.message)) setError(err.message);
    }
  }

  function drawAnnotations(annotations, imgW, imgH) {
    const canvas = canvasRef.current;
    if (!canvas || !preview) return;
    const img = new Image();
    img.onload = () => {
      const maxW = Math.min(canvas.parentElement.offsetWidth - 32, 800);
      const scale = maxW / imgW;
      canvas.width = imgW * scale;
      canvas.height = imgH * scale;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      annotations.forEach((ann, idx) => {
        const c = ann.coordinates;
        const x = c.x_min * scale;
        const y = c.y_min * scale;
        const w = (c.x_max - c.x_min) * scale;
        const h = (c.y_max - c.y_min) * scale;
        ctx.shadowColor = ann.color || '#00ff66';
        ctx.shadowBlur = 8;
        ctx.strokeStyle = ann.color || '#00ff66';
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, w, h);
        ctx.shadowBlur = 0;
        ctx.fillStyle = ann.color || '#00ff66';
        ctx.font = 'bold 12px JetBrains Mono';
        const label = `${idx + 1}. ${ann.title} (${(ann.confidence * 100).toFixed(0)}%)`;
        const tw = ctx.measureText(label).width + 8;
        ctx.fillRect(x, y - 18, tw, 18);
        ctx.fillStyle = '#000';
        ctx.fillText(label, x + 4, y - 5);
      });
    };
    img.src = preview;
  }

  async function handleAnalyze() {
    if (!file) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const data = await api.analyze(file, null, documentType !== 'other' ? documentType : null);
      setResult(data);
      if (data.annotations?.length > 0) {
        setTimeout(() => drawAnnotations(data.annotations, data.original_image_dimensions.width, data.original_image_dimensions.height), 100);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const verdictColors = {
    forged: '#ff3344',
    suspicious: '#ffa040',
    no_forgery_detected: '#00ff66',
    not_a_document: '#737373',
  };
  const verdictLabels = {
    forged: 'Forged',
    suspicious: 'Suspicious',
    no_forgery_detected: 'No Forgery Detected',
    not_a_document: 'Not a Document',
  };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <p className="classification-bar" style={{ marginBottom: 6 }}>FORENSIC · SCAN · PIPELINE</p>
        <h2 className="oswald glow" style={{ fontSize: 26, color: '#00ff66', letterSpacing: 4, textTransform: 'uppercase', margin: 0 }}>
          Scan Forgery
        </h2>
        <p style={{ color: '#6dba85', fontSize: 13, marginTop: 6 }}>
          Upload a document image — all 16 forgery detectors will run automatically.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 24, maxWidth: 800 }}>
        {/* Document Type Selection */}
        <div className="card">
          <h3 className="oswald" style={{
            fontSize: 13, textTransform: 'uppercase', letterSpacing: 2.5, marginBottom: 16,
            color: '#6dba85',
            display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <span style={{ fontSize: 18 }}>📄</span>
            Document Type
          </h3>
          <p style={{ fontSize: 13, color: '#86efac', marginBottom: 14 }}>
            What kind of document are you scanning? This helps Gemini focus on document-specific forgery patterns.
          </p>
          <select
            value={documentType}
            onChange={(e) => setDocumentType(e.target.value)}
            style={{
              width: '100%',
              padding: '12px 14px',
              background: '#0a1605',
              border: '1px solid #1d3825',
              borderRadius: 3,
              color: '#d8ffe6',
              fontSize: 13,
              fontFamily: "'JetBrains Mono', monospace",
              cursor: 'pointer',
              transition: 'border-color 0.2s',
            }}
            onFocus={(e) => e.target.style.borderColor = '#00ff66'}
            onBlur={(e) => e.target.style.borderColor = '#1d3825'}
          >
            {documentTypes.map(dt => (
              <option key={dt.key} value={dt.key} style={{ background: '#0a1605', color: '#d8ffe6' }}>
                {dt.title}
              </option>
            ))}
          </select>
          {documentType !== 'other' && (
            <p style={{ fontSize: 12, color: '#3f6e4a', marginTop: 10, fontStyle: 'italic' }}>
              {documentTypes.find(dt => dt.key === documentType)?.description}
            </p>
          )}
        </div>

        <div className="card">
          <h3 className="oswald" style={{
            fontSize: 13, textTransform: 'uppercase', letterSpacing: 2.5, marginBottom: 16,
            color: '#6dba85',
            display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <MagnifierIcon size={16} color="#6dba85" />
            Capture Document
          </h3>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10, marginBottom: 16 }}>
            <button type="button" className="btn btn-primary" onClick={handleTakePhoto} style={{ padding: '14px 16px' }}>
              ⌖ Take Photo
            </button>
            <button type="button" className="btn btn-secondary" onClick={handlePickFromGallery} style={{ padding: '14px 16px' }}>
              ▥ Gallery
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => fileRef.current.click()} style={{ padding: '14px 16px' }}>
              ⎙ File
            </button>
          </div>
          <input ref={fileRef} type="file" accept="image/*" onChange={handleFileChange} style={{ display: 'none' }} />

          <div
            onClick={() => fileRef.current.click()}
            style={{
              border: `1px dashed ${preview ? '#1d3825' : '#1f5d39'}`,
              borderRadius: 3, padding: preview ? 16 : 48, textAlign: 'center',
              cursor: 'pointer', transition: 'border-color 0.2s, background 0.2s',
              background: preview ? 'transparent' : 'rgba(0,255,102,0.02)',
            }}
            onMouseEnter={e => { if (!preview) { e.currentTarget.style.borderColor = '#00ff66'; e.currentTarget.style.background = 'rgba(0,255,102,0.04)'; } }}
            onMouseLeave={e => { if (!preview) { e.currentTarget.style.borderColor = '#1f5d39'; e.currentTarget.style.background = 'rgba(0,255,102,0.02)'; } }}
          >
            {preview ? (
              <img src={preview} alt="Preview" style={{ maxWidth: '100%', maxHeight: 320, borderRadius: 3, border: '1px solid #1d3825' }} />
            ) : (
              <div>
                <div className="mono glow" style={{ fontSize: 32, marginBottom: 12, color: '#00ff66' }}>+</div>
                <p className="mono" style={{ color: '#86efac', fontSize: 13, letterSpacing: 1.5 }}>NO IMAGE LOADED</p>
                <p style={{ color: '#3f6e4a', fontSize: 12, marginTop: 6 }}>Click to select a file, or use a button above</p>
              </div>
            )}
          </div>
        </div>

        <button className="btn btn-primary" onClick={handleAnalyze} disabled={!file || loading} style={{ fontSize: 16, padding: '18px 0' }}>
          {loading ? '◌ Running detection…' : '▶ Scan Forgery'}
        </button>

        {error && (
          <div style={{
            background: 'rgba(255,51,68,0.1)', border: '1px solid #ff3344', padding: 14, borderRadius: 2,
            fontSize: 13, color: '#ff8a99', fontFamily: "'JetBrains Mono', monospace", letterSpacing: 0.5,
          }}>
            ⚠ {error}
          </div>
        )}

        {result && (
          <ForensicResultCard
            result={result}
            canvasRef={canvasRef}
            verdictColors={verdictColors}
            verdictLabels={verdictLabels}
          />
        )}

        {result && (
          <button className="btn" onClick={resetScan} style={{ fontSize: 13 }}>
            ← New Scan
          </button>
        )}
      </div>
    </div>
  );
}

function LlmUpgradePrompt({ requiredPlan = 'premium' }) {
  return (
    <div style={{
      background: 'linear-gradient(135deg, rgba(139,92,246,0.1) 0%, rgba(139,92,246,0.02) 100%)',
      border: '1px solid rgba(139,92,246,0.4)', borderRadius: 3, padding: 14,
      display: 'flex', gap: 12, alignItems: 'flex-start',
    }}>
      <span style={{ fontSize: 22, lineHeight: 1 }}>✨</span>
      <div style={{ flex: 1 }}>
        <div className="oswald" style={{ fontSize: 13, color: '#c4b5fd', textTransform: 'uppercase', letterSpacing: 1.5, marginBottom: 4 }}>
          AI Forensic Explanation
        </div>
        <p style={{ fontSize: 13, color: '#86efac', lineHeight: 1.6, margin: 0, marginBottom: 10 }}>
          Upgrade to <strong style={{ color: '#a78bfa', textTransform: 'capitalize' }}>{requiredPlan}</strong> to
          get a plain-language breakdown of every detection — what was flagged, where, and why it matters.
        </p>
        <Link to="/account" style={{
          display: 'inline-block', padding: '6px 14px', borderRadius: 2,
          background: '#8b5cf6', color: '#fff', textDecoration: 'none',
          fontSize: 12, fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1.5,
        }}>
          See plans →
        </Link>
      </div>
    </div>
  );
}

function ForensicResultCard({ result, canvasRef, verdictColors, verdictLabels }) {
  const cat = result.detected_category;

  // Gemini succeeded only when confidence > 0 (0 = fallback/error/unavailable)
  const geminiOk = typeof result.category_confidence === 'number' && result.category_confidence > 0;
  const geminiForgery = geminiOk && cat !== 'no_forgery_detected' && cat !== 'not_a_document';

  const geminiAccent = !cat || !geminiOk ? '#737373'
    : cat === 'no_forgery_detected' ? '#00ff66'
    : cat === 'not_a_document' ? '#737373'
    : cat === 'other' ? '#ffa040'
    : (CATEGORY_BY_KEY[cat]?.color || '#a78bfa');

  const vc = geminiOk ? (CATEGORY_BY_KEY[cat]?.color || (cat === 'no_forgery_detected' ? '#00ff66' : cat === 'not_a_document' ? '#737373' : cat === 'other' ? '#ffa040' : '#a78bfa')) : (verdictColors[result.verdict] || '#1d3825');

  // Show YOLO only when Gemini confirms a forgery AND (if a specific category was
  // scanned) the Gemini category matches what YOLO was analyzing.
  const categoryMatch = !result.category_analyzed || result.detected_category === result.category_analyzed;
  const hasYolo = result.annotations?.length > 0 && geminiForgery && categoryMatch;

  return (
    <div className="card" style={{ borderColor: vc, boxShadow: `0 0 24px ${vc}30`, padding: 0, overflow: 'hidden' }}>
      {/* ── Verdict ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 20px', borderBottom: `1px solid ${vc}33` }}>
        <h3 className="oswald" style={{ fontSize: 14, textTransform: 'uppercase', letterSpacing: 2.5, color: '#d8ffe6', margin: 0 }}>◆ Forensic Report</h3>
        <span className="mono" style={{ fontSize: 11, color: '#3f6e4a' }}>{result.scan_id}</span>
      </div>

      <div style={{ textAlign: 'center', padding: '28px 20px 24px', background: '#000', borderBottom: `1px solid ${geminiAccent}33`, boxShadow: `inset 0 0 32px ${geminiAccent}18` }}>
        <div className="oswald" style={{ fontSize: 32, fontWeight: 700, color: geminiAccent, textTransform: 'uppercase', letterSpacing: 5, textShadow: `0 0 18px ${geminiAccent}99` }}>
          {geminiOk ? (result.detected_category_label || cat || '—') : (verdictLabels[result.verdict] || result.verdict)}
        </div>
        {geminiOk && (
          <div className="mono" style={{ color: '#6dba85', marginTop: 10, fontSize: 12, letterSpacing: 1.5 }}>
            {(result.category_confidence * 100).toFixed(1)}% CONF
            {result.certainty_level && (
              <span style={{ marginLeft: 10, color: result.certainty_level === 'HIGH' ? '#00ff66' : result.certainty_level === 'MEDIUM' ? '#ffa040' : '#ff5555' }}>
                · {result.certainty_level}
              </span>
            )}
          </div>
        )}
        {hasYolo && (
          <div className="mono" style={{ color: '#3f6e4a', marginTop: 6, fontSize: 10, letterSpacing: 1.5 }}>
            YOLO {(result.confidence_score * 100).toFixed(1)}%
          </div>
        )}
      </div>

      {result.training_warning && (
        <div style={{ background: 'rgba(255,160,64,0.08)', borderBottom: '1px solid #ffa040', padding: '10px 20px', fontSize: 12, color: '#ffc888', fontFamily: "'JetBrains Mono', monospace" }}>
          ⚠ {result.training_warning}
        </div>
      )}

      <div style={{ padding: '20px 20px 4px' }}>
        {/* ── Gemini Vision ── */}
        {geminiOk ? (
          <div style={{ marginBottom: 20 }}>
            <p className="mono" style={{ fontSize: 9, letterSpacing: 3, color: geminiAccent, margin: '0 0 8px', textShadow: `0 0 6px ${geminiAccent}99` }}>
              ▣ GEMINI VISION · CLASSIFICATION
            </p>
            <div style={{ background: `${geminiAccent}08`, border: `1px solid ${geminiAccent}44`, borderLeft: `3px solid ${geminiAccent}`, borderRadius: 3, padding: '12px 14px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                <div>
                  <h4 className="oswald" style={{ fontSize: 17, color: '#d8ffe6', textTransform: 'uppercase', letterSpacing: 2, margin: 0 }}>
                    {result.detected_category_label || cat}
                  </h4>
                  {result.detected_subtype && (
                    <p style={{ fontSize: 12, color: geminiAccent, margin: '3px 0 0', fontStyle: 'italic' }}>Subtype: {result.detected_subtype}</p>
                  )}
                </div>
                <span className="mono" style={{ fontSize: 11, color: geminiAccent, letterSpacing: 1.5 }}>
                  {(result.category_confidence * 100).toFixed(0)}% CONF
                </span>
              </div>
              {result.category_explanation && (
                <p style={{ lineHeight: 1.7, fontSize: 14, color: '#d8ffe6', margin: '0 0 10px' }}>{result.category_explanation}</p>
              )}
              {result.category_evidence?.length > 0 && (
                <ul style={{ margin: '0 0 10px', paddingLeft: 18, color: '#86efac', fontSize: 13, lineHeight: 1.6 }}>
                  {result.category_evidence.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              )}
              {result.tools_likely_used && (
                <p style={{ fontSize: 12, color: '#86efac', margin: 0, borderTop: '1px solid #112418', paddingTop: 8 }}>
                  <span className="mono" style={{ color: geminiAccent, letterSpacing: 1.5, marginRight: 6 }}>TOOLS USED:</span>
                  {result.tools_likely_used}
                </p>
              )}
            </div>
          </div>
        ) : (
          <div style={{ marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="mono" style={{ fontSize: 9, letterSpacing: 2, color: '#3f6e4a', padding: '4px 10px', border: '1px solid #1d3825', borderRadius: 2 }}>
              ▣ GEMINI VISION · TEMPORARILY UNAVAILABLE
            </span>
          </div>
        )}

        {/* ── LLM Explanation ── */}
        {result.llm_explanation && (
          <div style={{ marginBottom: 20 }}>
            <p className="mono" style={{ fontSize: 9, letterSpacing: 3, color: '#6dba85', margin: '0 0 8px' }}>▸ AI FORENSIC EXPLANATION</p>
            <p style={{ lineHeight: 1.7, fontSize: 14, color: '#d8ffe6', margin: 0 }}>{result.llm_explanation}</p>
          </div>
        )}
        {!result.llm_explanation && result.llm_locked && (
          <div style={{ marginBottom: 20 }}>
            <LlmUpgradePrompt requiredPlan={result.llm_required_plan} />
          </div>
        )}

        {/* ── YOLO Detections — only when bounding boxes exist ── */}
        {hasYolo && (
          <div style={{ marginBottom: 16 }}>
            <p className="mono" style={{ fontSize: 9, letterSpacing: 3, color: '#6dba85', margin: '0 0 8px' }}>▸ YOLO · DETECTED REGIONS</p>
            <canvas ref={canvasRef} style={{ maxWidth: '100%', borderRadius: 2, border: '1px solid #1d3825', marginBottom: 12 }} />
            {result.annotations.map((ann, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: '1px solid #112418' }}>
                <span style={{ width: 26, height: 26, borderRadius: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', background: ann.color, color: '#000', fontSize: 11, fontWeight: 800, boxShadow: `0 0 8px ${ann.color}80`, fontFamily: "'JetBrains Mono', monospace" }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span style={{ flex: 1, fontSize: 14, color: '#d8ffe6' }}>{ann.title}</span>
                <span className="mono" style={{ fontSize: 12, color: ann.color }}>{(ann.confidence * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

