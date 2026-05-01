import React, { useState, useRef, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { Camera, CameraResultType, CameraSource } from '@capacitor/camera';
import { api } from '../api/client';
import { CATEGORIES, CATEGORY_BY_ID, TIER_COLORS, TIER_META, categoriesByTier } from '../categories';
import {
  FingerprintWatermark, EyeMark, MagnifierIcon, Crosshair, FingerprintScan, EvidenceTag,
} from '../components/ForensicMotifs';

export default function Scan() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryCatId = searchParams.get('category');
  const initialCat = CATEGORY_BY_ID[queryCatId] || null;
  const initialStep = queryCatId === 'auto' ? 'upload' : (initialCat ? 'upload' : 'select');

  const [step, setStep] = useState(initialStep);
  const [category, setCategory] = useState(initialCat);
  const [datasetTotals, setDatasetTotals] = useState({});
  const [trainedKeys, setTrainedKeys] = useState({});
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const fileRef = useRef();
  const canvasRef = useRef();

  useEffect(() => {
    api.getCategories().then(data => {
      setDatasetTotals(data.category_dataset_totals || {});
      const keys = {};
      Object.values(data.categories || {}).forEach(arr => {
        arr.forEach(item => { keys[item.api_key] = !!item.is_trained; });
      });
      setTrainedKeys(keys);
    }).catch(() => {});
  }, []);

  function pickCategory(cat) {
    setCategory(cat);
    setStep('upload');
    setSearchParams({ category: cat.id }, { replace: true });
  }

  function pickAutoDetect() {
    setCategory(null);
    setStep('upload');
    setSearchParams({ category: 'auto' }, { replace: true });
  }

  function backToSelect() {
    setStep('select');
    setCategory(null);
    setFile(null);
    setPreview(null);
    setResult(null);
    setError('');
    setSearchParams({}, { replace: true });
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
      const data = await api.analyze(file, category?.apiKey || null);
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

  if (step === 'select') {
    return <SelectForgeryType onPick={pickCategory} onAutoDetect={pickAutoDetect} datasetTotals={datasetTotals} trainedKeys={trainedKeys} />;
  }

  // ───── upload step ─────
  const accentColor = category?.color || '#00ff66';
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
      <button
        onClick={backToSelect}
        style={{
          background: 'transparent', border: 'none', color: '#6dba85', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, padding: 0, fontSize: 13,
          fontFamily: "'JetBrains Mono', monospace", letterSpacing: 1,
        }}
      >
        ← back to forgery types
      </button>

      <div style={{
        background:
          `linear-gradient(135deg, ${accentColor}10 0%, transparent 60%), #0a120c`,
        borderLeft: `3px solid ${accentColor}`,
        border: '1px solid #112418',
        borderLeftWidth: 3,
        padding: 20, marginBottom: 24, borderRadius: 3,
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12,
        boxShadow: `0 0 20px ${accentColor}20, inset 0 1px 0 ${accentColor}15`,
      }}>
        <div>
          <p className="mono" style={{
            fontSize: 10, letterSpacing: 3, color: accentColor, margin: 0,
            textShadow: `0 0 8px ${accentColor}80`,
          }}>
            ▣ {category ? `CATEGORY · ${category.code}` : 'AUTO-DETECT'}
          </p>
          <h2 className="oswald" style={{
            fontSize: 24, fontWeight: 700, letterSpacing: 2, margin: '4px 0 0',
            textTransform: 'uppercase', color: '#d8ffe6',
          }}>
            {category ? category.title : 'Auto-Detect Forgery'}
          </h2>
          {category && (
            <p style={{ fontSize: 12, color: '#6dba85', margin: '4px 0 0', maxWidth: 520, lineHeight: 1.5 }}>
              {category.description}
            </p>
          )}
        </div>
        {category && (
          <Link
            to={`/samples/${category.id}`}
            style={{
              fontSize: 11, fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase',
              letterSpacing: 2, color: accentColor, textDecoration: 'none',
              border: `1px solid ${accentColor}`, padding: '8px 14px', borderRadius: 2,
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = `${accentColor}20`;
              e.currentTarget.style.boxShadow = `0 0 16px ${accentColor}60`;
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = 'transparent';
              e.currentTarget.style.boxShadow = 'none';
            }}
          >
            ▸ Examples
          </Link>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 24, maxWidth: 800 }}>
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
          {loading ? '◌ Running detection…' : '▶ Analyze Document'}
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
          <div className="card" style={{
            borderColor: verdictColors[result.verdict] || '#1d3825',
            boxShadow: `0 0 24px ${verdictColors[result.verdict]}30`,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h3 className="oswald" style={{ fontSize: 18, textTransform: 'uppercase', letterSpacing: 2.5, color: '#d8ffe6' }}>
                ◆ Analysis Result
              </h3>
              <span className="mono" style={{ fontSize: 11, color: '#3f6e4a' }}>{result.scan_id}</span>
            </div>

            <div style={{
              textAlign: 'center', padding: 28, background: '#000', borderRadius: 2, marginBottom: 20,
              border: `1px solid ${verdictColors[result.verdict]}`,
              boxShadow: `inset 0 0 32px ${verdictColors[result.verdict]}20`,
            }}>
              <div className="oswald" style={{
                fontSize: 34, fontWeight: 700, color: verdictColors[result.verdict],
                textTransform: 'uppercase', letterSpacing: 5,
                textShadow: `0 0 18px ${verdictColors[result.verdict]}99`,
              }}>
                {verdictLabels[result.verdict] || result.verdict}
              </div>
              <div className="mono" style={{ color: '#6dba85', marginTop: 10, fontSize: 13, letterSpacing: 1.5 }}>
                CONFIDENCE · {(result.confidence_score * 100).toFixed(1)}%
              </div>
            </div>

            {result.training_warning && (
              <div style={{
                background: 'rgba(255,160,64,0.08)', border: '1px solid #ffa040', padding: 12, borderRadius: 2,
                marginBottom: 16, fontSize: 12, color: '#ffc888', fontFamily: "'JetBrains Mono', monospace",
              }}>
                ⚠ {result.training_warning}
              </div>
            )}

            <div style={{ marginBottom: 20 }}>
              <h4 className="oswald" style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: 2, color: '#6dba85', marginBottom: 10 }}>
                ▸ Forensic Analysis
              </h4>
              {result.llm_explanation ? (
                <p style={{ lineHeight: 1.7, fontSize: 14, color: '#d8ffe6' }}>{result.llm_explanation}</p>
              ) : result.llm_locked ? (
                <LlmUpgradePrompt requiredPlan={result.llm_required_plan} />
              ) : null}
            </div>

            {result.annotations?.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <h4 className="oswald" style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: 2, color: '#6dba85', marginBottom: 10 }}>
                  ▸ Detected Regions
                </h4>
                <canvas ref={canvasRef} style={{ maxWidth: '100%', borderRadius: 2, border: '1px solid #1d3825' }} />
              </div>
            )}

            {result.annotations?.length > 0 && (
              <div>
                {result.annotations.map((ann, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '10px 0', borderBottom: '1px solid #112418',
                  }}>
                    <span style={{
                      width: 26, height: 26, borderRadius: 2, display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: ann.color, color: '#000', fontSize: 11, fontWeight: 800,
                      boxShadow: `0 0 8px ${ann.color}80`,
                      fontFamily: "'JetBrains Mono', monospace",
                    }}>
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span style={{ flex: 1, fontSize: 14, color: '#d8ffe6' }}>{ann.title}</span>
                    <span className="mono" style={{ fontSize: 12, color: ann.color }}>
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

function SelectForgeryType({ onPick, onAutoDetect, datasetTotals = {}, trainedKeys = {} }) {
  const totalTrained = Object.values(trainedKeys).filter(Boolean).length;

  return (
    <div>
      {/* hero with fingerprint scan + watermark */}
      <div style={{
        position: 'relative', textAlign: 'center', marginBottom: 36,
        padding: '12px 0 4px',
      }}>
        <FingerprintWatermark
          size={420} opacity={0.045}
          style={{ position: 'absolute', top: -40, left: '50%', transform: 'translateX(-50%)', zIndex: 0 }}
        />
        <div style={{ position: 'relative' }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 18 }}>
            <FingerprintScan size={150} color="#00ff66" />
          </div>
          <p className="classification-bar" style={{ marginBottom: 14 }}>
            CASE FILE · FORENSIC PIPELINE · CLASSIFIED
          </p>
          <h2 className="oswald glow-strong" style={{
            fontSize: 'clamp(28px, 5.5vw, 46px)', fontWeight: 700, letterSpacing: 5, marginBottom: 12,
            color: '#00ff66', textTransform: 'uppercase',
          }}>
            Select Forgery Type
          </h2>
          <p style={{ color: '#86efac', maxWidth: 580, margin: '0 auto', lineHeight: 1.7, fontSize: 14 }}>
            Sixteen forensic detectors, one per known forgery class. Pick the category you want
            to scan against, or run automatic detection across the entire pipeline.
          </p>

          <div style={{
            display: 'inline-flex', gap: 24, marginTop: 20, padding: '10px 22px',
            border: '1px solid #1d3825', borderRadius: 2, background: 'rgba(0,255,102,0.03)',
            boxShadow: 'inset 0 0 18px rgba(0,255,102,0.06)',
          }}>
            <Stat label="DETECTORS" value="16" color="#00ff66" />
            <Divider />
            <Stat label="ACTIVE"    value={String(totalTrained)} color="#00ffaa" />
            <Divider />
            <Stat label="TIERS"     value="3" color="#a3e635" />
          </div>
        </div>
      </div>

      <div style={{
        display: 'grid', gap: 12, marginBottom: 32,
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
      }}>
        <button
          onClick={onAutoDetect}
          className="lift"
          style={{
            background:
              'linear-gradient(135deg, rgba(0,255,102,0.08) 0%, rgba(0,255,170,0.04) 100%), #050a07',
            border: '1px solid #00ff66',
            color: '#d8ffe6', cursor: 'pointer', padding: '20px 24px',
            borderRadius: 3, textAlign: 'left',
            boxShadow: '0 0 20px rgba(0,255,102,0.15)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Crosshair size={42} color="#00ff66" style={{ filter: 'drop-shadow(0 0 8px rgba(0,255,102,0.7))' }} />
            <div style={{ flex: 1 }}>
              <div className="mono" style={{ fontSize: 10, letterSpacing: 3, color: '#00ff66', marginBottom: 4 }}>
                AUTO · ALL DETECTORS
              </div>
              <div className="oswald" style={{ fontSize: 18, letterSpacing: 2, textTransform: 'uppercase', color: '#d8ffe6' }}>
                Auto-Detect Forgery
              </div>
              <div style={{ fontSize: 12, color: '#86efac', marginTop: 4, lineHeight: 1.5 }}>
                Run every detector and surface the strongest match.
              </div>
            </div>
            <MagnifierIcon size={22} color="#00ff66" style={{ opacity: 0.7 }} />
          </div>
        </button>
      </div>

      {[1, 2, 3].map(tier => (
        <TierBucket
          key={tier}
          tier={tier}
          categories={categoriesByTier(tier)}
          onPick={onPick}
          datasetTotals={datasetTotals}
          trainedKeys={trainedKeys}
        />
      ))}
    </div>
  );
}

function Stat({ label, value, color }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div className="oswald" style={{ fontSize: 20, fontWeight: 700, color, lineHeight: 1, textShadow: `0 0 10px ${color}80` }}>
        {value}
      </div>
      <div className="mono" style={{ fontSize: 9, letterSpacing: 2, color: '#3f6e4a', marginTop: 2 }}>
        {label}
      </div>
    </div>
  );
}

function Divider() {
  return <div style={{ width: 1, background: '#1d3825', alignSelf: 'stretch', minHeight: 28 }} />;
}

function TierBucket({ tier, categories, onPick, datasetTotals, trainedKeys }) {
  const accent = TIER_COLORS[tier];
  const meta = TIER_META[tier];
  const trainedCount = categories.filter(c => trainedKeys[c.apiKey]).length;

  return (
    <section style={{ marginBottom: 36 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 14, marginBottom: 14,
        paddingBottom: 10, borderBottom: `1px solid ${accent}33`,
      }}>
        <div className="eye-blink" style={{
          width: 40, height: 40,
          background: `${accent}18`, border: `1px solid ${accent}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          borderRadius: 2, boxShadow: `0 0 14px ${accent}50`,
          padding: 7,
        }}>
          <EyeMark size={24} color={accent} />
        </div>
        <div style={{ flex: 1 }}>
          <h3 className="oswald" style={{
            fontSize: 17, fontWeight: 700, letterSpacing: 3, margin: 0,
            color: accent, textTransform: 'uppercase',
            textShadow: `0 0 10px ${accent}66`,
          }}>
            {meta.label}
          </h3>
          <p style={{ fontSize: 12, color: '#6dba85', margin: '2px 0 0', lineHeight: 1.4 }}>
            {meta.sublabel}
          </p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
          <span className="mono" style={{
            fontSize: 9, color: accent, padding: '3px 8px',
            border: `1px solid ${accent}66`, borderRadius: 2, letterSpacing: 1.5,
          }}>
            {categories.length} CLASSES
          </span>
          <span className="mono" style={{ fontSize: 9, color: '#3f6e4a', letterSpacing: 1.5 }}>
            {trainedCount}/{categories.length} ACTIVE
          </span>
        </div>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
        gap: 14,
      }}>
        {categories.map((cat, i) => (
          <CategoryCard
            key={cat.id}
            cat={cat}
            index={i + 1}
            datasetCount={datasetTotals[cat.apiKey] || 0}
            trained={trainedKeys[cat.apiKey]}
            onClick={() => onPick(cat)}
          />
        ))}
      </div>
    </section>
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

function CategoryCard({ cat, index, onClick, datasetCount = 0, trained }) {
  const [hover, setHover] = useState(false);
  const accent = cat.color;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); } }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background:
          hover
            ? `linear-gradient(135deg, ${accent}10 0%, transparent 70%), #0a120c`
            : 'linear-gradient(135deg, rgba(0,255,102,0.015) 0%, transparent 70%), #0a120c',
        border: `1px solid ${hover ? accent : '#112418'}`,
        borderLeft: `3px solid ${accent}`,
        padding: 0, textAlign: 'left', cursor: 'pointer',
        transition: 'all 0.2s ease', position: 'relative', overflow: 'hidden',
        borderRadius: 3, color: 'inherit', font: 'inherit', width: '100%',
        boxShadow: hover
          ? `0 6px 28px ${accent}30, 0 0 18px ${accent}20, inset 0 1px 0 ${accent}25`
          : `inset 0 1px 0 ${accent}10`,
        transform: hover ? 'translateY(-2px)' : 'translateY(0)',
      }}
    >
      {/* corner glyph */}
      <div className="oswald hex-badge" style={{
        position: 'absolute', top: 12, right: 12, width: 28, height: 28,
        color: '#001005', fontWeight: 800, fontSize: 11,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: accent,
        boxShadow: hover ? `0 0 14px ${accent}` : 'none',
        transition: 'box-shadow 0.2s',
        fontFamily: "'JetBrains Mono', monospace",
      }}>
        {String(index).padStart(2, '0')}
      </div>

      {/* scan-line decoration */}
      {hover && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: 1,
          background: `linear-gradient(90deg, transparent, ${accent}, transparent)`,
          animation: 'scan-pulse 1.4s ease-in-out infinite',
        }} />
      )}

      <div style={{ padding: '18px 18px 14px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 10, paddingRight: 36 }}>
          <span style={{
            fontSize: 24, color: accent,
            textShadow: `0 0 ${hover ? 14 : 8}px ${accent}99`,
            transition: 'text-shadow 0.2s',
            lineHeight: 1, marginTop: 2,
          }}>{cat.icon}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <p className="mono" style={{
              fontSize: 9, letterSpacing: 2.5, margin: 0, color: accent,
              textShadow: `0 0 6px ${accent}80`,
            }}>{cat.code}</p>
            <h3 className="oswald" style={{
              fontSize: 17, fontWeight: 600, margin: 0, letterSpacing: 1,
              color: '#d8ffe6', textTransform: 'uppercase',
            }}>{cat.title}</h3>
          </div>
        </div>
        <p style={{ fontSize: 12, color: '#86efac', margin: 0, lineHeight: 1.5, opacity: 0.85 }}>
          {cat.description}
        </p>
      </div>

      <div style={{
        borderTop: '1px solid #112418', padding: '10px 16px', background: 'rgba(0,0,0,0.4)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8,
      }}>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
          <span className="mono" style={{
            fontSize: 9, letterSpacing: 1.5,
            color: trained ? accent : '#3f6e4a',
            textShadow: trained ? `0 0 6px ${accent}80` : 'none',
          }}>
            {trained ? '● ACTIVE' : '○ PENDING'}
          </span>
          <span className="mono" style={{ fontSize: 9, color: '#3f6e4a', letterSpacing: 1.5 }}>
            {datasetCount.toLocaleString()} IMG
          </span>
        </div>
        <Link
          to={`/samples/${cat.id}`}
          onClick={e => e.stopPropagation()}
          style={{
            fontSize: 9, color: accent, textDecoration: 'none',
            fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1.5,
            padding: '3px 7px', border: `1px solid ${accent}40`, borderRadius: 2,
          }}
        >
          Examples
        </Link>
      </div>
    </div>
  );
}
