import React, { useState, useRef, useEffect } from 'react';
import { api } from '../api/client';

export default function Scan() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [category, setCategory] = useState('');
  const [categories, setCategories] = useState({});
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const fileRef = useRef();
  const canvasRef = useRef();

  useEffect(() => {
    api.getCategories().then(data => setCategories(data.categories)).catch(() => {});
  }, []);

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

  function drawAnnotations(annotations, imgW, imgH) {
    const canvas = canvasRef.current;
    if (!canvas || !preview) return;
    const img = new Image();
    img.onload = () => {
      // Fit to container
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
        ctx.strokeStyle = ann.color || '#dc2626';
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, w, h);
        ctx.fillStyle = ann.color || '#dc2626';
        ctx.font = 'bold 12px JetBrains Mono';
        const label = `${idx + 1}. ${ann.title} (${(ann.confidence * 100).toFixed(0)}%)`;
        const tw = ctx.measureText(label).width + 8;
        ctx.fillRect(x, y - 18, tw, 18);
        ctx.fillStyle = '#fff';
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
      const data = await api.analyze(file, category || null);
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

  const verdictColors = { forged: '#dc2626', suspicious: '#f97316', genuine: '#22c55e' };

  return (
    <div>
      <h1 className="oswald" style={{ fontSize: 26, letterSpacing: 2, textTransform: 'uppercase', marginBottom: 24 }}>
        Document Scan
      </h1>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 24, maxWidth: 800 }}>
        {/* Upload area */}
        <div className="card">
          <h3 className="oswald" style={{ fontSize: 14, textTransform: 'uppercase', letterSpacing: 1.5, marginBottom: 16, color: '#a3a3a3' }}>
            Upload Document
          </h3>
          <div
            onClick={() => fileRef.current.click()}
            style={{
              border: '2px dashed #404040', borderRadius: 8, padding: 40, textAlign: 'center',
              cursor: 'pointer', transition: 'border-color 0.2s',
            }}
            onMouseEnter={e => e.target.style.borderColor = '#f5c518'}
            onMouseLeave={e => e.target.style.borderColor = '#404040'}
          >
            <input ref={fileRef} type="file" accept="image/*" onChange={handleFileChange} style={{ display: 'none' }} />
            {preview ? (
              <img src={preview} alt="Preview" style={{ maxWidth: '100%', maxHeight: 300, borderRadius: 4 }} />
            ) : (
              <div>
                <div style={{ fontSize: 36, marginBottom: 8 }}>+</div>
                <p style={{ color: '#a3a3a3' }}>Tap to select an image</p>
                <p style={{ color: '#525252', fontSize: 13, marginTop: 4 }}>JPG, PNG supported</p>
              </div>
            )}
          </div>
        </div>

        {/* Category selector */}
        <div className="card">
          <h3 className="oswald" style={{ fontSize: 14, textTransform: 'uppercase', letterSpacing: 1.5, marginBottom: 12, color: '#a3a3a3' }}>
            Category (optional)
          </h3>
          <select
            className="input"
            value={category}
            onChange={e => setCategory(e.target.value)}
            style={{ background: '#1a1a1a' }}
          >
            <option value="">Auto-detect (scan all)</option>
            {Object.entries(categories).map(([catName, items]) => (
              <optgroup key={catName} label={catName}>
                {items.map(item => (
                  <option key={item.api_key} value={item.api_key}>
                    {item.title} {item.is_trained ? '' : '(limited data)'}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>

        {/* Analyze button */}
        <button className="btn btn-primary" onClick={handleAnalyze} disabled={!file || loading} style={{ fontSize: 16, padding: '18px 0' }}>
          {loading ? 'Analyzing...' : 'Analyze Document'}
        </button>

        {error && (
          <div style={{ background: 'rgba(220,38,38,0.15)', border: '1px solid #dc2626', padding: 14, borderRadius: 4, fontSize: 13, color: '#f87171' }}>
            {error}
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="card" style={{ borderColor: verdictColors[result.verdict] || '#262626' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h3 className="oswald" style={{ fontSize: 18, textTransform: 'uppercase', letterSpacing: 2 }}>
                Analysis Result
              </h3>
              <span className="mono" style={{ fontSize: 12, color: '#525252' }}>{result.scan_id}</span>
            </div>

            {/* Verdict */}
            <div style={{
              textAlign: 'center', padding: 24, background: '#0a0a0a', borderRadius: 6, marginBottom: 20,
              border: `1px solid ${verdictColors[result.verdict]}`,
            }}>
              <div className="oswald" style={{
                fontSize: 32, fontWeight: 700, color: verdictColors[result.verdict],
                textTransform: 'uppercase', letterSpacing: 4,
              }}>
                {result.verdict}
              </div>
              <div className="mono" style={{ color: '#a3a3a3', marginTop: 8 }}>
                Confidence: {(result.confidence_score * 100).toFixed(1)}%
              </div>
            </div>

            {/* Warning */}
            {result.training_warning && (
              <div style={{ background: 'rgba(249,115,22,0.1)', border: '1px solid #f97316', padding: 12, borderRadius: 4, marginBottom: 16, fontSize: 13, color: '#fb923c' }}>
                {result.training_warning}
              </div>
            )}

            {/* LLM Explanation */}
            <div style={{ marginBottom: 20 }}>
              <h4 className="oswald" style={{ fontSize: 13, textTransform: 'uppercase', letterSpacing: 1.5, color: '#a3a3a3', marginBottom: 8 }}>
                Forensic Analysis
              </h4>
              <p style={{ lineHeight: 1.7, fontSize: 14, color: '#d4d4d4' }}>{result.llm_explanation}</p>
            </div>

            {/* Annotated image */}
            {result.annotations?.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <h4 className="oswald" style={{ fontSize: 13, textTransform: 'uppercase', letterSpacing: 1.5, color: '#a3a3a3', marginBottom: 8 }}>
                  Detected Regions
                </h4>
                <canvas ref={canvasRef} style={{ maxWidth: '100%', borderRadius: 4, border: '1px solid #262626' }} />
              </div>
            )}

            {/* Annotations list */}
            {result.annotations?.length > 0 && (
              <div>
                {result.annotations.map((ann, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: '1px solid #1a1a1a' }}>
                    <span style={{
                      width: 24, height: 24, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: ann.color, color: '#fff', fontSize: 11, fontWeight: 700,
                    }}>
                      {i + 1}
                    </span>
                    <span style={{ flex: 1, fontSize: 14 }}>{ann.title}</span>
                    <span className="mono" style={{ fontSize: 12, color: '#a3a3a3' }}>
                      {(ann.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
